#!/usr/bin/env python3
"""Import data/combined.txt into an ActionKit instance's Blackhole Domains.

Reads credentials from environment variables:
    AK_INSTANCE   e.g. "yourorg.actionkit.com" (no scheme, no path)
    AK_USERNAME   ActionKit API username
    AK_PASSWORD   ActionKit API password

Modes:
    (no flags)        Run the import: GET existing, diff, POST what's new.
    --check           Pre-flight test only — verify env vars, DNS, TLS, auth,
                      and read access. Doesn't POST anything. Use this BEFORE
                      your first real import to confirm setup.
    --dry-run         Don't POST anything; just show what would be added.

Optional flags:
    --limit N         Cap at N new domains (useful for first-time testing).
    --workers N       Parallel POST workers (default: 8). Lower if you see
                      429 (rate limit) errors or want to be gentler on AK.

Idempotent: pages through the existing Blackhole Domains list first and
only POSTs domains that are not already present. Safe to re-run — if a
previous run timed out (e.g., GitHub Actions' 6-hour job ceiling), just
run again and it picks up where it left off.

Stdlib only. Requires Python 3.9+.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from _ak_common import (
    DEFAULT_WORKERS,
    PROGRESS_EVERY,
    PROGRESS_INTERVAL_SECONDS,
    TransportError,
    _format_eta,
    check_connection,
    fetch_existing,
    get_credentials_and_headers,
    http,
    load_combined,
)


def post_domain(instance: str, headers: dict, domain: str) -> tuple[str, int, str]:
    try:
        status, body = http("POST", f"https://{instance}/rest/v1/blackholeddomain/", headers, {"domain": domain})
    except TransportError as e:
        return domain, 0, f"TransportError: {e.__cause__ or e}"[:200]
    return domain, status, body


def run_import(args: argparse.Namespace) -> int:
    instance, username, headers = get_credentials_and_headers()

    desired = load_combined()
    print(f"Loaded {len(desired):,} domains from data/combined.txt")
    print(f"Connecting to {instance} as {username}...")

    existing = fetch_existing(instance, headers)
    print(f"Found {len(existing):,} domains already in your Blackhole list")

    to_add = sorted(desired - existing.keys())
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

    total = len(to_add)
    print(f"\nAdding {total:,} new domain(s) with {args.workers} parallel worker(s)...\n")
    added = 0
    failed = 0
    failures: list[tuple[str, int, str]] = []

    start = time.monotonic()
    last_print = start

    def log_progress(done: int) -> None:
        elapsed = time.monotonic() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = _format_eta(int((total - done) / rate)) if rate > 0 else "—"
        print(f"  {done:,}/{total:,}  ({added:,} added, {failed:,} failed)  "
              f"{rate:.1f}/sec  ETA {eta}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(post_domain, instance, headers, d): d for d in to_add}
        for i, fut in enumerate(as_completed(futures), start=1):
            try:
                domain, status, body = fut.result()
            except Exception as e:
                failed += 1
                failures.append((futures[fut], 0, f"{type(e).__name__}: {e}"[:200]))
            else:
                if 200 <= status < 300:
                    added += 1
                else:
                    failed += 1
                    failures.append((domain, status, body[:200]))
            now = time.monotonic()
            if i % PROGRESS_EVERY == 0 or (now - last_print) >= PROGRESS_INTERVAL_SECONDS:
                log_progress(i)
                last_print = now

    elapsed = time.monotonic() - start
    overall_rate = (added + failed) / elapsed if elapsed > 0 else 0
    print(f"\nDone. {added:,} added, {failed:,} failed in {elapsed:.0f}s "
          f"({overall_rate:.1f}/sec).")

    if failures:
        print(f"\nFirst 10 failures (out of {len(failures)}):")
        for d, s, b in failures[:10]:
            print(f"  {d}  HTTP {s}  {b}")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="Pre-flight only: test env, DNS, TLS, auth, and read access. "
                             "Don't POST anything. Use before your first real import.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't POST; just show what would be added.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N new domains. Useful for first-time testing.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel POST workers (default: {DEFAULT_WORKERS}). "
                             "Lower if you see 429 errors or want to be gentler on AK.")
    args = parser.parse_args()

    if args.check:
        return check_connection()

    if args.workers < 1:
        sys.exit("ERROR: --workers must be >= 1")

    return run_import(args)


if __name__ == "__main__":
    sys.exit(main())
