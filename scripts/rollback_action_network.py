#!/usr/bin/env python3
"""Roll back an Action Network sweep by reading the audit log it produced
and removing every tagging that was applied. The tag entity itself is
left in place — Action Network's API does not allow tag deletion.

This is the undo for sweep_action_network.py — useful if the sweep tagged
the wrong people, you ran against the wrong group, or you just want to
back out the change.

Reads credentials from environment variables:
    AN_API_KEY    Action Network API key for the target group

Required:
    --audit-log PATH   The CSV produced by sweep_action_network.py.
                       The rollback only removes taggings recorded in this
                       log, so it can't accidentally affect anything else.

You MUST pass --yes to actually delete. Without it, the script lists what
would be removed but takes no destructive action.

Optional flags:
    --yes              Required to actually delete. Without it, dry-run only.
    --workers N        Concurrent DELETE workers (default 2, max 4).

Stdlib only. Requires Python 3.9+.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from _an_common import (
    DEFAULT_WORKERS,
    MAX_WORKERS,
    PROGRESS_EVERY,
    PROGRESS_INTERVAL_SECONDS,
    AuditWriter,
    _format_eta,
    check_connection,
    get_credentials_and_headers,
    remove_tagging,
    validate_workers,
)


def load_taggings_to_remove(audit_log: Path) -> list[dict]:
    """Read the sweep's audit log and return the rows worth rolling back.

    We only roll back successful tag_applied rows. Apply-failures didn't
    create a tagging in AN, so there's nothing to remove for those.
    Deduplicates by tagging_self_url in case the same row appears twice.
    """
    if not audit_log.exists():
        sys.exit(f"ERROR: audit log not found at {audit_log}")

    seen_urls: set[str] = set()
    rows: list[dict] = []
    with audit_log.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("action") != "tag_applied":
                continue
            tagging_url = (row.get("tagging_self_url") or "").strip()
            if not tagging_url:
                continue
            if tagging_url in seen_urls:
                continue
            seen_urls.add(tagging_url)
            rows.append(row)
    return rows


def remove_one(headers: dict, row: dict) -> tuple[dict, int, str]:
    status, body = remove_tagging(headers, row["tagging_self_url"])
    return row, status, body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--audit-log", type=str, required=True,
                        help="Path to the CSV produced by sweep_action_network.py.")
    parser.add_argument("--yes", action="store_true",
                        help="Required to actually delete. Without it, dry-run only.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Concurrent DELETE workers (default {DEFAULT_WORKERS}, max {MAX_WORKERS}).")
    parser.add_argument("--check", action="store_true",
                        help="Pre-flight only: test env, DNS, TLS, auth. Don't change anything.")
    args = parser.parse_args()

    if args.check:
        return check_connection()

    validate_workers(args.workers)

    audit_path = Path(args.audit_log)
    rows = load_taggings_to_remove(audit_path)

    if not rows:
        print(f"No tag_applied rows with a tagging_self_url found in {audit_path}.\nNothing to roll back.")
        return 0

    headers = get_credentials_and_headers()

    tag_names = sorted({row.get("tag_name", "") for row in rows if row.get("tag_name")})
    print(f"Audit log: {audit_path}")
    print(f"Tags affected: {', '.join(tag_names) or '(unknown)'}")
    print(f"Taggings to remove: {len(rows):,}")

    if not args.yes:
        print("\n[dry-run — pass --yes to actually delete]")
        print(f"Would remove {len(rows):,} tagging(s). First 20:")
        for row in rows[:20]:
            print(f"  - {row.get('email','')}  (tag: {row.get('tag_name','')})")
        if len(rows) > 20:
            print(f"  ... and {len(rows) - 20:,} more")
        print(
            "\nWhen ready, re-run with --yes.\n"
            "\nNote: Action Network does not allow tag deletion via API. Even after rollback,\n"
            "the tag entity itself remains in your AN. It will be empty (no people tagged).\n"
            "You can hide it from the AN UI's tags list manually if it's in the way."
        )
        return 0

    rollback_log = audit_path.with_name(audit_path.stem + ".rollback.csv")
    print(f"\nRolling back. Audit log of removals: {rollback_log}")
    print(f"Removing {len(rows):,} tagging(s) with {args.workers} parallel worker(s)...\n")

    total = len(rows)
    removed = 0
    already_gone = 0
    failed = 0
    failures: list[tuple[str, int, str]] = []
    start = time.monotonic()
    last_print = start

    def log_progress(done: int) -> None:
        elapsed = time.monotonic() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = _format_eta(int((total - done) / rate)) if rate > 0 else "—"
        print(f"  {done:,}/{total:,}  ({removed:,} removed, {already_gone:,} already gone, "
              f"{failed:,} failed)  {rate:.1f}/sec  ETA {eta}", flush=True)

    with AuditWriter(rollback_log) as audit, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(remove_one, headers, row): row for row in rows}
        for i, fut in enumerate(as_completed(futures), start=1):
            row = futures[fut]
            try:
                _, status, body = fut.result()
            except Exception as e:
                failed += 1
                failures.append((row.get("email", ""), 0, f"{type(e).__name__}: {e}"[:200]))
                audit.write(action="tag_remove_failed",
                            person_self_url=row.get("person_self_url", ""),
                            email=row.get("email", ""), domain=row.get("domain", ""),
                            tag_name=row.get("tag_name", ""), tag_self_url=row.get("tag_self_url", ""),
                            tagging_self_url=row.get("tagging_self_url", ""),
                            status="0", note=str(e)[:200])
            else:
                if 200 <= status < 300:
                    removed += 1
                    audit.write(action="tag_removed",
                                person_self_url=row.get("person_self_url", ""),
                                email=row.get("email", ""), domain=row.get("domain", ""),
                                tag_name=row.get("tag_name", ""), tag_self_url=row.get("tag_self_url", ""),
                                tagging_self_url=row.get("tagging_self_url", ""),
                                status=str(status))
                elif status == 404:
                    already_gone += 1
                    audit.write(action="tag_remove_already_gone",
                                person_self_url=row.get("person_self_url", ""),
                                email=row.get("email", ""), domain=row.get("domain", ""),
                                tag_name=row.get("tag_name", ""),
                                tagging_self_url=row.get("tagging_self_url", ""),
                                status="404", note="already gone — treated as success")
                else:
                    failed += 1
                    failures.append((row.get("email", ""), status, body[:200]))
                    audit.write(action="tag_remove_failed",
                                person_self_url=row.get("person_self_url", ""),
                                email=row.get("email", ""), domain=row.get("domain", ""),
                                tag_name=row.get("tag_name", ""), tag_self_url=row.get("tag_self_url", ""),
                                tagging_self_url=row.get("tagging_self_url", ""),
                                status=str(status), note=body[:200])
            now = time.monotonic()
            if i % PROGRESS_EVERY == 0 or (now - last_print) >= PROGRESS_INTERVAL_SECONDS:
                log_progress(i)
                last_print = now

    elapsed = time.monotonic() - start
    overall_rate = (removed + already_gone + failed) / elapsed if elapsed > 0 else 0
    print(f"\nDone. {removed:,} removed, {already_gone:,} already gone, {failed:,} failed in "
          f"{elapsed:.0f}s ({overall_rate:.1f}/sec).")
    print(f"Rollback audit log: {rollback_log}")
    print(
        "\nNote: Action Network does not allow tag deletion via API. The tag entity remains\n"
        "in your AN, now empty. Hide it from the UI's tags list manually if needed."
    )

    if failures:
        print(f"\nFirst 10 failures (out of {len(failures)}):")
        for email, s, b in failures[:10]:
            print(f"  {email}  HTTP {s}  {b}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
