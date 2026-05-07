#!/usr/bin/env python3
"""Remove every domain in data/combined.txt from your AK Blackhole list.

This is the undo for import_to_actionkit.py — useful if you imported to the
wrong instance, want to start over, or no longer want the suppression list
applied.

WARNING — this is destructive. The script removes EVERY domain that's both
in data/combined.txt AND in your AK Blackhole list. If your AK had any of
those domains in its Blackhole list before our import (someone added them
manually, or an earlier batch put them there), this script removes them too.
There's no way to tell which entries were added by our import vs. by other
means once they're in AK.

If pre-existing entries matter, back up your Blackhole list first:
  - Admin UI:  Mailings → List Hygiene → Blackhole, take note of any entries
               you want to preserve.
  - Or via API:  GET /rest/v1/blackholeddomain/?_limit=200 (paginated).

Reads credentials from environment variables:
    AK_INSTANCE   e.g. "yourorg.actionkit.com" (no scheme, no path)
    AK_USERNAME   ActionKit API username
    AK_PASSWORD   ActionKit API password

You MUST pass --yes to confirm. Without it the script lists what would be
removed but takes no destructive action.

Optional flags:
    --yes             Required to actually delete. Without it, dry-run only.
    --limit N         Stop after N deletions (useful for safety-checking).
    --workers N       Parallel DELETE workers (default: 8).

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
    fetch_existing,
    get_credentials_and_headers,
    http,
    load_combined,
)


def delete_domain(instance: str, headers: dict, domain: str, obj_id: int) -> tuple[str, int, str]:
    url = f"https://{instance}/rest/v1/blackholeddomain/{obj_id}/"
    try:
        status, body = http("DELETE", url, headers)
    except TransportError as e:
        return domain, 0, f"TransportError: {e.__cause__ or e}"[:200]
    return domain, status, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true",
                        help="Required to actually delete. Without it, dry-run only.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N deletions.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel DELETE workers (default: {DEFAULT_WORKERS}).")
    args = parser.parse_args()

    if args.workers < 1:
        sys.exit("ERROR: --workers must be >= 1")

    instance, username, headers = get_credentials_and_headers()

    target = load_combined()
    print(f"Loaded {len(target):,} domains from data/combined.txt")
    print(f"Connecting to {instance} as {username}...")

    existing = fetch_existing(instance, headers)
    print(f"Found {len(existing):,} domains in your Blackhole list")

    to_remove = sorted((d for d in existing if d in target))
    if not to_remove:
        print("\n✓ None of the suppression-list domains are in your Blackhole list. Nothing to remove.")
        return 0

    if args.limit is not None and args.limit < len(to_remove):
        print(f"\n[--limit {args.limit}] Capping at first {args.limit:,} of {len(to_remove):,} matches.")
        to_remove = to_remove[:args.limit]

    if not args.yes:
        print(f"\n[dry-run — pass --yes to actually delete]")
        print(f"Would remove {len(to_remove):,} domain(s) from your AK Blackhole list:")
        for d in to_remove[:20]:
            print(f"  - {d}")
        if len(to_remove) > 20:
            print(f"  ... and {len(to_remove) - 20:,} more")
        print(
            "\nWARNING: this removes EVERY domain in combined.txt from your Blackhole list,\n"
            "including any that were there before our import. There's no way to distinguish\n"
            "after-the-fact. If pre-existing entries matter, back them up first.\n\n"
            "When ready, re-run with --yes."
        )
        return 0

    total = len(to_remove)
    print(f"\nRemoving {total:,} domain(s) with {args.workers} parallel worker(s)...\n")
    removed = 0
    failed = 0
    failures: list[tuple[str, int, str]] = []

    start = time.monotonic()
    last_print = start

    def log_progress(done: int) -> None:
        elapsed = time.monotonic() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = _format_eta(int((total - done) / rate)) if rate > 0 else "—"
        print(f"  {done:,}/{total:,}  ({removed:,} removed, {failed:,} failed)  "
              f"{rate:.1f}/sec  ETA {eta}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(delete_domain, instance, headers, d, existing[d]): d for d in to_remove}
        for i, fut in enumerate(as_completed(futures), start=1):
            try:
                domain, status, body = fut.result()
            except Exception as e:
                failed += 1
                failures.append((futures[fut], 0, f"{type(e).__name__}: {e}"[:200]))
            else:
                if 200 <= status < 300:
                    removed += 1
                else:
                    failed += 1
                    failures.append((domain, status, body[:200]))
            now = time.monotonic()
            if i % PROGRESS_EVERY == 0 or (now - last_print) >= PROGRESS_INTERVAL_SECONDS:
                log_progress(i)
                last_print = now

    elapsed = time.monotonic() - start
    overall_rate = (removed + failed) / elapsed if elapsed > 0 else 0
    print(f"\nDone. {removed:,} removed, {failed:,} failed in {elapsed:.0f}s "
          f"({overall_rate:.1f}/sec).")

    if failures:
        print(f"\nFirst 10 failures (out of {len(failures)}):")
        for d, s, b in failures[:10]:
            print(f"  {d}  HTTP {s}  {b}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
