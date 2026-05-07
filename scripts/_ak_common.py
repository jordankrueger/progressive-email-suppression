"""Shared helpers for the ActionKit import and remove scripts.

Stdlib only; lives next to the scripts that import it. The leading underscore
marks this as private (not a CLI entry point — don't run directly).
"""

from __future__ import annotations

import base64
import json
import os
import random
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from http.client import HTTPException, HTTPSConnection

HTTP_TIMEOUT = 30
MAX_RETRIES = 5
PAGE_SIZE = 200

USER_AGENT = "progressive-email-suppression/1.0 (+https://github.com/jordankrueger/progressive-email-suppression)"


def env_required(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(
            f"ERROR: {name} environment variable is not set.\n"
            f"In GitHub Actions, add it under Settings → Secrets and variables → Actions."
        )
    return v


def basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def normalize_instance(raw: str) -> str:
    """Strip scheme, trailing slash, and common path mistakes from AK_INSTANCE.

    Users sometimes paste the full admin URL. We normalize to bare hostname.
    """
    s = raw.strip().lower()
    s = s.removeprefix("https://").removeprefix("http://")
    # Drop any path component (yourorg.actionkit.com/admin -> yourorg.actionkit.com)
    s = s.split("/", 1)[0]
    # Drop port if present (rare but possible)
    return s


def get_credentials_and_headers() -> tuple[str, str, dict]:
    """Read AK_INSTANCE/USERNAME/PASSWORD from env, build auth headers.

    Returns (instance, username, headers). Exits with a friendly message if
    any required env var is missing.
    """
    raw_instance = env_required("AK_INSTANCE")
    instance = normalize_instance(raw_instance)
    if not instance or "." not in instance:
        sys.exit(
            f"ERROR: AK_INSTANCE doesn't look like a hostname.\n"
            f"You set: {raw_instance!r}\n"
            f"It should look like: yourorg.actionkit.com (just the hostname,\n"
            f"no https://, no /admin, no trailing slash)."
        )
    username = env_required("AK_USERNAME")
    password = env_required("AK_PASSWORD")
    headers = {
        "Authorization": basic_auth(username, password),
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    return instance, username, headers


def _retry_sleep(attempt: int, retry_after: str | None) -> float:
    """Exponential backoff with jitter; honors Retry-After if present."""
    if retry_after:
        try:
            return min(60.0, float(retry_after))
        except ValueError:
            pass
    return min(30.0, (2 ** attempt) + random.uniform(0, 1))


# Per-thread HTTPSConnection so each worker reuses one keep-alive connection
# across all of its requests. Avoids paying TCP+TLS handshake on every POST.
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
    """Raised when http() can't get a response after retries.

    The cause chain (`__cause__`) holds the last underlying exception so
    callers can render a friendly diagnosis.
    """


def http(method: str, url: str, headers: dict, body: dict | None = None,
         retries: int = MAX_RETRIES) -> tuple[int, str]:
    """Send an HTTP request via a per-thread keep-alive connection.

    `url` must be a full URL (https://host/path?query). Returns (status, body).
    Retries automatically on 429 and 5xx with exponential backoff + jitter.
    Raises TransportError after exhausting retries on connection-level failures.
    """
    u = urllib.parse.urlparse(url)
    host = u.netloc
    path = u.path + (("?" + u.query) if u.query else "")
    payload = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if body is not None:
        h["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(retries):
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
            _drop_conn()  # connection may be in a bad state; reopen on retry
            if attempt + 1 < retries:
                time.sleep(_retry_sleep(attempt, None))
    raise TransportError(f"Network error talking to {host} after {retries} attempts: {last_err}") from last_err


def diagnose_transport_error(err: BaseException, instance: str) -> str:
    """Translate a TransportError (or its cause) into a friendly diagnosis."""
    cause = err.__cause__ or err
    if isinstance(cause, socket.gaierror):
        return (
            f"Could not look up '{instance}' in DNS.\n"
            f"Most common causes:\n"
            f"  - Typo in AK_INSTANCE\n"
            f"  - Wrong subdomain (your AK might be at a different name)\n"
            f"You set: {instance}\n"
            f"It should look like: yourorg.actionkit.com"
        )
    if isinstance(cause, ConnectionRefusedError):
        return (
            f"Reached {instance} but the server refused the connection.\n"
            f"Most common cause: the hostname is wrong, or your AK instance is offline.\n"
            f"You set: {instance}\n"
            f"It should look like: yourorg.actionkit.com (no https://, no /admin)."
        )
    if isinstance(cause, ssl.SSLError) or "certificate" in str(cause).lower() or "ssl" in str(cause).lower():
        return (
            f"TLS/SSL error connecting to {instance}.\n"
            f"Most common cause: a typo in AK_INSTANCE — the hostname doesn't match\n"
            f"the certificate ActionKit serves. Double-check the spelling."
        )
    if isinstance(cause, TimeoutError) or "timed out" in str(cause).lower():
        return (
            f"Connection to {instance} timed out after {HTTP_TIMEOUT}s.\n"
            f"This is often transient — re-run the workflow. If it keeps happening,\n"
            f"your AK instance may be slow or having an outage."
        )
    return f"Network error talking to {instance}: {cause}"


def diagnose_response_error(status: int, body: str, instance: str, url: str) -> str:
    """Translate an unexpected HTTP response into a friendly diagnosis."""
    if status == 401:
        return (
            "ActionKit rejected the credentials (HTTP 401).\n"
            "  - Double-check AK_USERNAME and AK_PASSWORD in your repository secrets.\n"
            "  - If your API user has 2FA enabled, Basic auth won't work — use a\n"
            "    dedicated API user without 2FA."
        )
    if status == 403:
        return (
            "ActionKit authenticated the user but refused the request (HTTP 403).\n"
            "  - The user account doesn't have API permissions on this resource.\n"
            "  - Ask whoever administers your AK instance to grant API access."
        )
    if status == 404:
        return (
            f"ActionKit returned 404 for {url}.\n"
            "  - The endpoint isn't where we expected — possibly an unusual AK setup.\n"
            "  - Open an issue at https://github.com/jordankrueger/progressive-email-suppression/issues"
        )
    # Heuristic: response looks like HTML, probably hit a non-API endpoint.
    body_start = body.lstrip()[:80].lower()
    if body_start.startswith("<!doctype") or body_start.startswith("<html"):
        return (
            f"ActionKit returned HTML, not JSON (HTTP {status}).\n"
            f"Most common cause: AK_INSTANCE has a path or trailing junk in it.\n"
            f"You set: {instance}\n"
            f"Set it to JUST the hostname (e.g. yourorg.actionkit.com — no /admin)."
        )
    return f"GET {url} returned HTTP {status}.\n{body[:400]}"


def fetch_existing(instance: str, headers: dict) -> dict[str, int]:
    """Page through GET /blackholeddomain/ and return {domain: id}.

    Exits with a friendly message on auth failures or non-JSON responses.
    """
    seen: dict[str, int] = {}
    next_path = f"/rest/v1/blackholeddomain/?_limit={PAGE_SIZE}"
    while next_path:
        url = next_path if next_path.startswith("http") else f"https://{instance}{next_path}"
        try:
            status, body = http("GET", url, headers)
        except TransportError as e:
            sys.exit(f"ERROR: {diagnose_transport_error(e, instance)}")
        if status >= 400:
            sys.exit(f"ERROR: {diagnose_response_error(status, body, instance, url)}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            sys.exit(
                f"ERROR: ActionKit returned non-JSON for {url}.\n"
                f"Most common cause: AK_INSTANCE has a path or extra characters.\n"
                f"You set: {instance}\n"
                f"Set it to just the hostname (e.g. yourorg.actionkit.com).\n"
                f"\nFirst 200 chars of response:\n{body[:200]}"
            )
        for obj in data.get("objects", []):
            domain = (obj.get("domain") or "").strip().lower()
            obj_id = obj.get("id")
            if domain and obj_id is not None:
                seen[domain] = int(obj_id)
        next_path = (data.get("meta") or {}).get("next") or ""
    return seen


def check_connection() -> int:
    """Verify env, DNS, TLS, auth, and read access to /blackholeddomain/.

    Prints a friendly summary on success, friendly diagnosis on failure.
    Returns an exit code (0 = OK, non-zero = something to fix).
    """
    print("Checking ActionKit connection...\n")
    try:
        instance, username, headers = get_credentials_and_headers()
    except SystemExit:
        raise
    print(f"  ✓ Environment variables set (AK_INSTANCE, AK_USERNAME, AK_PASSWORD)")
    print(f"  ✓ AK_INSTANCE looks like a hostname: {instance}")

    # One small GET — confirms DNS, TLS, auth, and API access in one shot.
    url = f"https://{instance}/rest/v1/blackholeddomain/?_limit=1"
    try:
        status, body = http("GET", url, headers)
    except TransportError as e:
        print()
        print(f"  ✗ Couldn't reach {instance}\n")
        print(diagnose_transport_error(e, instance))
        return 2

    print(f"  ✓ DNS + HTTPS connection to {instance} OK")

    if status == 401:
        print()
        print(diagnose_response_error(status, body, instance, url))
        return 3
    if status == 403:
        print()
        print(diagnose_response_error(status, body, instance, url))
        return 3
    if status >= 400:
        print()
        print(diagnose_response_error(status, body, instance, url))
        return 4

    print(f"  ✓ Authenticated as {username}")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print()
        print(
            "  ✗ ActionKit returned non-JSON.\n\n"
            f"Most common cause: AK_INSTANCE has a path or extra characters.\n"
            f"You set: {instance}\n"
            f"First 200 chars of response:\n{body[:200]}"
        )
        return 5

    total = (data.get("meta") or {}).get("total_count")
    if total is None:
        # Some AK responses don't return total_count; fall back to len of objects (best effort).
        total = len(data.get("objects", []))
    print(f"  ✓ API access OK — read /rest/v1/blackholeddomain/ successfully")
    print(f"\nYour Blackhole list currently has {total:,} domain(s).")
    print()
    print("Connection check passed. You're ready to run Import to ActionKit.")
    return 0
