#!/usr/bin/env python3
"""Import data/combined.txt into an ActionKit instance's Blackhole Domains.

Reads credentials from environment variables:
    AK_INSTANCE   e.g. "yourorg.actionkit.com" (no scheme, no path)
    AK_USERNAME   ActionKit API username
    AK_PASSWORD   ActionKit API password

Optional flags:
    --dry-run     Don't POST anything; just show what would be added.
    --limit N     Cap at N new domains (useful for first-time testing).

Idempotent: pages through the existing Blackhole Domains list first and
only POSTs domains that are not already present. Safe to re-run.

Stdlib only. Requires Python 3.9+.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMBINED = REPO / "data" / "combined.txt"

# Be polite to AK. ~20 POSTs/sec is well under typical limits.
POST_DELAY_SECONDS = 0.05
PROGRESS_EVERY = 200
PAGE_SIZE = 200
HTTP_TIMEOUT = 30


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


def http(method: str, url: str, headers: dict, body: dict | None = None,
         retries: int = 3) -> tuple[int, str]:
    payload = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if body is not None:
        h["Content-Type"] = "application/json"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=payload, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Network error talking to ActionKit after {retries} attempts: {last_err}")


def fetch_existing(instance: str, headers: dict) -> set[str]:
    """Page through GET /blackholeddomain/ and return all existing domains."""
    seen: set[str] = set()
    next_path = f"/rest/v1/blackholeddomain/?_limit={PAGE_SIZE}"
    while next_path:
        url = next_path if next_path.startswith("http") else f"https://{instance}{next_path}"
        status, body = http("GET", url, headers)
        if status == 401:
            sys.exit(
                "ERROR: ActionKit rejected the credentials (HTTP 401).\n"
                "Double-check AK_USERNAME and AK_PASSWORD in your repository secrets."
            )
        if status >= 400:
            sys.exit(f"ERROR: GET existing list failed: HTTP {status}\n{body[:400]}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            sys.exit(f"ERROR: ActionKit returned non-JSON for {url}\n{body[:400]}")
        for obj in data.get("objects", []):
            domain = (obj.get("domain") or "").strip().lower()
            if domain:
                seen.add(domain)
        next_path = (data.get("meta") or {}).get("next") or ""
    return seen


def load_combined() -> set[str]:
    if not COMBINED.exists():
        sys.exit(f"ERROR: {COMBINED} not found. Run scripts/build.py first.")
    out: set[str] = set()
    for line in COMBINED.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.add(line)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't POST; just show what would be added.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N new domains. Useful for first-time testing.")
    args = parser.parse_args()

    instance = env_required("AK_INSTANCE").replace("https://", "").replace("http://", "").rstrip("/")
    username = env_required("AK_USERNAME")
    password = env_required("AK_PASSWORD")

    headers = {
        "Authorization": basic_auth(username, password),
        "Accept": "application/json",
        "User-Agent": "progressive-email-suppression/1.0 (+https://github.com/jordankrueger/progressive-email-suppression)",
    }

    desired = load_combined()
    print(f"Loaded {len(desired):,} domains from data/combined.txt")
    print(f"Connecting to {instance} as {username}...")

    existing = fetch_existing(instance, headers)
    print(f"Found {len(existing):,} domains already in your Blackhole list")

    to_add = sorted(desired - existing)
    if not to_add:
        print("\n✓ Your instance is already up to date. Nothing to add.")
        return 0

    if args.limit is not None and args.limit < len(to_add):
        print(f"\n[--limit {args.limit}] Capping at first {args.limit:,} of {len(to_add):,} new domains.")
        to_add = to_add[:args.limit]

    if args.dry_run:
        print(f"\n[--dry-run] Would add {len(to_add):,} domain(s):")
        for domain in to_add[:20]:
            print(f"  + {domain}")
        if len(to_add) > 20:
            print(f"  ... and {len(to_add) - 20:,} more")
        print("\nNo changes made. Drop --dry-run to actually POST.")
        return 0

    print(f"\nAdding {len(to_add):,} new domain(s)...\n")
    added = 0
    failed = 0
    failures: list[tuple[str, int, str]] = []
    for i, domain in enumerate(to_add, start=1):
        status, body = http("POST", f"https://{instance}/rest/v1/blackholeddomain/", headers, {"domain": domain})
        if 200 <= status < 300:
            added += 1
        else:
            failed += 1
            failures.append((domain, status, body[:200]))
        if i % PROGRESS_EVERY == 0:
            print(f"  {i:,}/{len(to_add):,}  ({added:,} added, {failed:,} failed)")
        time.sleep(POST_DELAY_SECONDS)

    print(f"\nDone. {added:,} added, {failed:,} failed.")

    if failures:
        print(f"\nFirst 10 failures (out of {len(failures)}):")
        for d, s, b in failures[:10]:
            print(f"  {d}  HTTP {s}  {b}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
