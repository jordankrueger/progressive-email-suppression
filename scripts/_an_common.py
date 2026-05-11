"""Shared helpers for the Action Network sweep and rollback scripts.

Stdlib only; lives next to the scripts that import it. The leading underscore
marks this as private (not a CLI entry point — don't run directly except for
the inline self-tests at the bottom).

API conventions:
    - Auth: single OSDI-API-Token header. One key per AN group.
    - Pagination: walk _links.next.href until absent. Page size capped at 25.
    - The People collection does NOT return total_records / total_pages.
    - Tags are deduplicated by name on POST — POSTing a duplicate name returns
      the existing resource, so "find or create" is a single POST.
    - Tag DELETE is not supported. Rollback removes taggings, leaves the tag.
    - Rate limit not officially documented; community-reported as 4 req/sec.
      We cap at 3.5 QPS to leave headroom.
"""

from __future__ import annotations

import csv
import json
import os
import random
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from typing import Iterator

HTTP_TIMEOUT = 30
MAX_RETRIES = 5
PAGE_SIZE = 25  # AN hard cap
DEFAULT_WORKERS = 2
MAX_WORKERS = 4  # ceiling — refuse to go above this even if user asks
PROGRESS_EVERY = 100
PROGRESS_INTERVAL_SECONDS = 30
RATE_LIMIT_QPS = 3.5  # under AN's documented community-known 4/sec

AN_HOST = "actionnetwork.org"
AN_API_ROOT = f"https://{AN_HOST}/api/v2"

USER_AGENT = "progressive-email-suppression/1.1 (+https://github.com/jordankrueger/progressive-email-suppression)"

REPO = Path(__file__).resolve().parent.parent
COMBINED = REPO / "data" / "combined.txt"
ALLOWLIST = REPO / "sources" / "allowlist.txt"


def validate_workers(workers: int) -> None:
    """Validate the --workers argument; sys.exit with a clear message if out of range."""
    if workers < 1:
        sys.exit("ERROR: --workers must be >= 1")
    if workers > MAX_WORKERS:
        sys.exit(f"ERROR: --workers must be <= {MAX_WORKERS} (AN's rate limit makes higher counterproductive)")


def env_required(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(
            f"ERROR: {name} environment variable is not set.\n"
            f"In GitHub Actions, add it under Settings → Secrets and variables → Actions."
        )
    return v


def get_credentials_and_headers() -> dict:
    """Read AN_API_KEY from env, build OSDI auth headers."""
    api_key = env_required("AN_API_KEY")
    return {
        "OSDI-API-Token": api_key,
        "Accept": "application/hal+json",
        "User-Agent": USER_AGENT,
    }


def load_combined() -> set[str]:
    if not COMBINED.exists():
        sys.exit(f"ERROR: {COMBINED} not found. Run scripts/build.py first.")
    out: set[str] = set()
    for line in COMBINED.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


def load_allowlist() -> set[str]:
    if not ALLOWLIST.exists():
        sys.exit(f"ERROR: {ALLOWLIST} not found. The repo seems incomplete.")
    out: set[str] = set()
    for line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


def extract_domain(email: str) -> str:
    """Return the lowercased, IDNA-encoded domain of an email, or '' if invalid."""
    if not email or "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1].strip().lower()
    if not domain:
        return ""
    try:
        return domain.encode("idna").decode("ascii")
    except (UnicodeError, ValueError):
        return domain  # fall back to raw lowercased domain on encode failure


def _format_eta(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ----- Rate limiter -----------------------------------------------------------

class _RateLimiter:
    """Simple thread-safe min-interval limiter shared across workers."""

    def __init__(self, qps: float):
        self._min_interval = 1.0 / qps
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_time = self._next_at - now
            if wait_time > 0:
                time.sleep(wait_time)
                now = time.monotonic()
            self._next_at = now + self._min_interval


_global_rate_limiter = _RateLimiter(RATE_LIMIT_QPS)


# ----- HTTP plumbing ----------------------------------------------------------

def _retry_sleep(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(60.0, float(retry_after))
        except ValueError:
            pass
    return min(30.0, (2 ** attempt) + random.uniform(0, 1))


_thread_local = threading.local()


def _get_conn(host: str) -> HTTPSConnection:
    cached_host = getattr(_thread_local, "host", None)
    conn = getattr(_thread_local, "conn", None)
    if conn is None or cached_host != host:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        conn = HTTPSConnection(host, timeout=HTTP_TIMEOUT)
        _thread_local.host = host
        _thread_local.conn = conn
    return conn


def _drop_conn() -> None:
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _thread_local.conn = None


class TransportError(RuntimeError):
    """Raised when http() can't get a response after retries."""


def http(method: str, url: str, headers: dict, body: dict | None = None,
         retries: int = MAX_RETRIES) -> tuple[int, str]:
    """Send an HTTPS request via per-thread keep-alive connection.

    Applies the global rate limit before each attempt. Retries on 429/5xx.
    Returns (status, body_text). Raises TransportError on connection failure.
    """
    u = urllib.parse.urlparse(url)
    host = u.netloc or AN_HOST
    path = u.path + (("?" + u.query) if u.query else "")
    payload = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if body is not None:
        h["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(retries):
        _global_rate_limiter.wait()
        try:
            conn = _get_conn(host)
            conn.request(method, path, body=payload, headers=h)
            resp = conn.getresponse()
            retry_after = resp.getheader("Retry-After")
            status = resp.status
            data = resp.read().decode("utf-8", errors="replace")
            if status == 429 or 500 <= status < 600:
                if attempt + 1 < retries:
                    time.sleep(_retry_sleep(attempt, retry_after))
                    continue
            return status, data
        except (HTTPException, OSError, TimeoutError) as e:
            last_err = e
            _drop_conn()
            if attempt + 1 < retries:
                time.sleep(_retry_sleep(attempt, None))
    raise TransportError(f"Network error talking to {host} after {retries} attempts: {last_err}") from last_err


# ----- Friendly error diagnostics ---------------------------------------------

def diagnose_transport_error(err: BaseException) -> str:
    cause = err.__cause__ or err
    if isinstance(cause, socket.gaierror):
        return (
            f"Could not look up '{AN_HOST}' in DNS.\n"
            f"This usually means GitHub Actions briefly couldn't resolve the hostname.\n"
            f"Re-run the workflow; if it keeps happening, check status.actionnetwork.org."
        )
    if isinstance(cause, ConnectionRefusedError):
        return (
            f"Reached {AN_HOST} but the server refused the connection.\n"
            f"This is rare for AN. Check status.actionnetwork.org for an outage."
        )
    if isinstance(cause, ssl.SSLError) or "certificate" in str(cause).lower() or "ssl" in str(cause).lower():
        return (
            f"TLS/SSL error connecting to {AN_HOST}.\n"
            f"This is unusual — re-run the workflow. If persistent, check\n"
            f"status.actionnetwork.org or open an issue."
        )
    if isinstance(cause, TimeoutError) or "timed out" in str(cause).lower():
        return (
            f"Connection to {AN_HOST} timed out after {HTTP_TIMEOUT}s.\n"
            f"Often transient — re-run the workflow."
        )
    return f"Network error talking to {AN_HOST}: {cause}"


def diagnose_response_error(status: int, body: str, url: str) -> str:
    if status == 401:
        return (
            "Action Network rejected the API key (HTTP 401).\n"
            "  - Double-check AN_API_KEY in your repository secrets.\n"
            "  - Confirm the key is enabled in your AN group's API settings.\n"
            "  - Each AN group has its own key — make sure you used the right group's key."
        )
    if status == 403:
        return (
            "Action Network authenticated but refused the request (HTTP 403).\n"
            "  - The API key doesn't have permission for this resource.\n"
            "  - Check your AN group's API settings and confirm the key has full access."
        )
    if status == 404:
        return (
            f"Action Network returned 404 for {url}.\n"
            "  - The resource doesn't exist or has been removed.\n"
            "  - Open an issue at https://github.com/jordankrueger/progressive-email-suppression/issues"
        )
    if status == 422:
        return (
            f"Action Network rejected the request body (HTTP 422).\n"
            f"  Response: {body[:300]}"
        )
    body_start = body.lstrip()[:80].lower()
    if body_start.startswith("<!doctype") or body_start.startswith("<html"):
        return (
            f"Action Network returned HTML, not JSON (HTTP {status}).\n"
            f"This usually means a maintenance page or an outage. Check\n"
            f"status.actionnetwork.org and re-run the workflow."
        )
    return f"{url} returned HTTP {status}.\n{body[:400]}"


# ----- Pagination -------------------------------------------------------------

def paginate(start_url: str, headers: dict, embed_key: str) -> Iterator[dict]:
    """Walk _links.next.href until absent; yield each embedded resource.

    `embed_key` is e.g. "osdi:people" or "osdi:tags" — the key under
    `_embedded` in each page's response.
    """
    next_url = start_url
    while next_url:
        try:
            status, body = http("GET", next_url, headers)
        except TransportError as e:
            sys.exit(f"ERROR: {diagnose_transport_error(e)}")
        if status >= 400:
            sys.exit(f"ERROR: {diagnose_response_error(status, body, next_url)}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            sys.exit(
                f"ERROR: Action Network returned non-JSON for {next_url}.\n"
                f"First 200 chars:\n{body[:200]}"
            )
        for item in (data.get("_embedded") or {}).get(embed_key, []):
            yield item
        next_url = ((data.get("_links") or {}).get("next") or {}).get("href") or ""


# ----- Tag operations ---------------------------------------------------------

def find_or_create_tag(headers: dict, name: str) -> dict:
    """POST to /api/v2/tags/ with the tag name. AN dedupes by name, so this is
    safe to call repeatedly — it returns the existing tag if the name is taken.
    Returns the tag JSON (containing identifiers, _links.self, _links.osdi:taggings).
    """
    url = f"{AN_API_ROOT}/tags/"
    try:
        status, body = http("POST", url, headers, body={"name": name})
    except TransportError as e:
        sys.exit(f"ERROR: {diagnose_transport_error(e)}")
    if status >= 400:
        sys.exit(f"ERROR: Couldn't create tag '{name}'.\n{diagnose_response_error(status, body, url)}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        sys.exit(f"ERROR: AN returned non-JSON when creating tag.\n{body[:200]}")


def tag_uuid_from(tag: dict) -> str:
    """Extract the AN UUID from a tag's identifiers list."""
    for identifier in tag.get("identifiers", []):
        if identifier.startswith("action_network:"):
            return identifier.split(":", 1)[1]
    self_href = ((tag.get("_links") or {}).get("self") or {}).get("href", "")
    return self_href.rstrip("/").rsplit("/", 1)[-1]


def apply_tag(headers: dict, tag_uuid: str, person_self_url: str) -> tuple[int, str, dict | None]:
    """POST a tagging that links the given person to the given tag.

    Returns (status, body, tagging_dict_or_None).
    """
    url = f"{AN_API_ROOT}/tags/{tag_uuid}/taggings/"
    payload = {"_links": {"osdi:person": {"href": person_self_url}}}
    try:
        status, body = http("POST", url, headers, body=payload)
    except TransportError as e:
        return 0, f"TransportError: {e.__cause__ or e}"[:200], None
    if 200 <= status < 300:
        try:
            return status, body, json.loads(body)
        except json.JSONDecodeError:
            return status, body, None
    return status, body, None


def remove_tagging(headers: dict, tagging_self_url: str) -> tuple[int, str]:
    """DELETE a tagging by its self URL. Returns (status, body).

    AN returns 200 (not 204) on success. 404 means already gone — treat as success.
    """
    try:
        status, body = http("DELETE", tagging_self_url, headers)
    except TransportError as e:
        return 0, f"TransportError: {e.__cause__ or e}"[:200]
    return status, body


# ----- Audit log --------------------------------------------------------------

AUDIT_FIELDS = [
    "timestamp", "action", "person_self_url", "email", "domain",
    "tag_name", "tag_self_url", "tagging_self_url", "status", "note",
]


class AuditWriter:
    """CSV audit log writer. One row per action. Append-mode, line-buffered, lock-protected."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        new = not path.exists()
        # line-buffered so kills / timeouts don't lose recent rows
        self._fh = path.open("a", newline="", buffering=1, encoding="utf-8")
        self._writer = csv.DictWriter(self._fh, fieldnames=AUDIT_FIELDS)
        if new:
            self._writer.writeheader()

    def write(self, **fields) -> None:
        row = {k: fields.get(k, "") for k in AUDIT_FIELDS}
        row["timestamp"] = row["timestamp"] or datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock:
            self._writer.writerow(row)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "AuditWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# ----- Connection check -------------------------------------------------------

def check_connection() -> int:
    """Verify env, DNS, TLS, auth, and read access to AN's HAL root."""
    print("Checking Action Network connection...\n")
    try:
        headers = get_credentials_and_headers()
    except SystemExit:
        raise
    print("  ✓ Environment variable set (AN_API_KEY)")

    url = AN_API_ROOT + "/"
    try:
        status, body = http("GET", url, headers)
    except TransportError as e:
        print()
        print(f"  ✗ Couldn't reach {AN_HOST}\n")
        print(diagnose_transport_error(e))
        return 2

    print(f"  ✓ DNS + HTTPS connection to {AN_HOST} OK")

    if status in (401, 403):
        print()
        print(diagnose_response_error(status, body, url))
        return 3
    if status >= 400:
        print()
        print(diagnose_response_error(status, body, url))
        return 4

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print()
        print("  ✗ Action Network returned non-JSON.")
        print(f"\nFirst 200 chars:\n{body[:200]}")
        return 5

    motd = data.get("motd") or "(no greeting)"
    print(f"  ✓ Authenticated to AN — \"{motd[:80]}\"")
    print("  ✓ API access OK — read /api/v2/ HAL root successfully")
    print()
    print("Connection check passed. You're ready to run the sweep workflow.")
    return 0


# ----- Inline self-tests (run this file directly to exercise) -----------------

def _self_test() -> int:
    """Minimal self-tests covering the parts that don't need network access."""
    print("Running _an_common.py self-tests...")
    failures = []

    # extract_domain
    cases = [
        ("user@example.com", "example.com"),
        ("USER@EXAMPLE.COM", "example.com"),
        ("  spaced@gmail.com  ".strip(), "gmail.com"),
        ("noatsign.com", ""),
        ("", ""),
        ("a@b@c.com", "c.com"),
    ]
    for inp, want in cases:
        got = extract_domain(inp)
        if got != want:
            failures.append(f"extract_domain({inp!r}) → {got!r}, want {want!r}")

    # allowlist + combined disjointness (belt-and-suspenders)
    try:
        allowlist = load_allowlist()
        combined = load_combined()
        leaked = allowlist & combined
        if leaked:
            failures.append(f"Allowlist domains found in combined.txt: {sorted(leaked)}")
        if "gmail.com" not in allowlist:
            failures.append("gmail.com missing from allowlist.txt")
    except SystemExit as e:
        failures.append(f"Could not load list files: {e}")

    # rate limiter actually rate-limits
    rl = _RateLimiter(10.0)  # 100ms between calls
    t0 = time.monotonic()
    rl.wait()
    rl.wait()
    rl.wait()
    elapsed = time.monotonic() - t0
    # Three waits at 100ms apart should take ~200ms (first is free, then two intervals)
    if elapsed < 0.18:
        failures.append(f"RateLimiter too fast: 3 waits took {elapsed:.3f}s, expected >= 0.18s")

    # tag_uuid_from extraction
    fake_tag = {
        "identifiers": ["action_network:71f8feef-61c8-4e6b-9745-ec1d7752f298"],
        "_links": {"self": {"href": "https://actionnetwork.org/api/v2/tags/71f8feef-61c8-4e6b-9745-ec1d7752f298"}},
    }
    if tag_uuid_from(fake_tag) != "71f8feef-61c8-4e6b-9745-ec1d7752f298":
        failures.append("tag_uuid_from didn't extract the UUID correctly")

    if failures:
        print()
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("  ✓ extract_domain handles common cases")
    print("  ✓ allowlist and combined are disjoint")
    print("  ✓ rate limiter enforces minimum interval")
    print("  ✓ tag_uuid_from extracts UUID from identifiers")
    print()
    print("All self-tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
