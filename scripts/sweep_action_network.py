#!/usr/bin/env python3
"""Tag people in an Action Network group whose email domain is on the
suppression list. Does NOT change subscription status — applies a tag the
admin can use to exclude people from mailings.

Reads credentials from environment variables:
    AN_API_KEY    Action Network API key for the target group

Modes:
    (no flags)        Run the sweep: paginate people, find matches, apply tag.
    --check           Pre-flight only — verify env, DNS, TLS, auth, and read
                      access. Doesn't make any changes.
    --dry-run         Page through people; print first 20 matches; change nothing.

Optional flags:
    --limit N         Cap the number of people tagged (useful for first runs).
    --workers N       Concurrent taggers (default 2, max 4). AN rate-limits
                      around 4 req/sec so going higher is counterproductive.
    --force           Allow runs that match >25% of fetched people (default:
                      halt with an error and require explicit override).
    --tag NAME        Override the default tag name. Default: psup_YYYY-MM-DD.
    --audit-log PATH  Where to write the CSV audit log. Default:
                      ./audit-an-sweep-<tag>.csv. Save this file — it is
                      required to roll back the sweep with rollback_action_network.py.

Stdlib only. Requires Python 3.9+.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from _an_common import (
    AN_API_ROOT,
    DEFAULT_WORKERS,
    MAX_WORKERS,
    PAGE_SIZE,
    PROGRESS_EVERY,
    PROGRESS_INTERVAL_SECONDS,
    AuditWriter,
    _format_eta,
    apply_tag,
    check_connection,
    extract_domain,
    find_or_create_tag,
    get_credentials_and_headers,
    load_allowlist,
    load_combined,
    paginate,
    tag_uuid_from,
    validate_workers,
)

ANOMALY_THRESHOLD = 0.25  # halt if more than this fraction of fetched people match


def primary_email(person: dict) -> str:
    """Return the primary email address, or first if no primary marked."""
    addresses = person.get("email_addresses") or []
    for a in addresses:
        if a.get("primary"):
            return (a.get("address") or "").strip().lower()
    if addresses:
        return (addresses[0].get("address") or "").strip().lower()
    return ""


def person_self_url(person: dict) -> str:
    return ((person.get("_links") or {}).get("self") or {}).get("href", "")


def find_matches(headers: dict, suppression: set[str], allowlist: set[str],
                 force: bool) -> tuple[list[dict], int]:
    """Paginate through people, return (matches, total_seen).

    Each match is {"person_self_url", "email", "domain"}. Halts on anomaly
    if match rate exceeds ANOMALY_THRESHOLD and force is False.
    """
    print(f"Scanning Action Network group (page size {PAGE_SIZE}, no server-side filter — this can take a while)...")
    matches: list[dict] = []
    seen = 0
    last_print = time.monotonic()
    start_url = f"{AN_API_ROOT}/people/"

    for person in paginate(start_url, headers, embed_key="osdi:people"):
        seen += 1
        email = primary_email(person)
        domain = extract_domain(email)
        if not domain or domain in allowlist:
            continue
        if domain in suppression:
            self_url = person_self_url(person)
            if not self_url:
                continue  # malformed; skip
            matches.append({
                "person_self_url": self_url,
                "email": email,
                "domain": domain,
            })

        # Periodic progress print so admins watching the workflow log see life
        now = time.monotonic()
        if seen % PROGRESS_EVERY == 0 or (now - last_print) >= PROGRESS_INTERVAL_SECONDS:
            ratio = (len(matches) / seen) if seen else 0
            print(f"  scanned {seen:,} people, {len(matches):,} matches so far ({ratio*100:.1f}%)", flush=True)
            last_print = now

        # Halt-on-anomaly: only meaningful after a sample. Don't trip on the
        # first few people if the group happens to have a junk record at the top.
        if seen >= 200 and not force:
            ratio = len(matches) / seen
            if ratio > ANOMALY_THRESHOLD:
                sys.exit(
                    f"\nERROR: Match rate is {ratio*100:.1f}% after scanning {seen:,} people.\n"
                    f"This is above the {int(ANOMALY_THRESHOLD*100)}% safety threshold. The most likely causes:\n"
                    f"  - data/combined.txt was modified/corrupted\n"
                    f"  - allowlist filtering didn't apply (e.g., your group is mostly disposable signups)\n"
                    f"  - You truly do have a lot of bad records and want to proceed — re-run with --force.\n"
                )

    print(f"\nDone scanning. {seen:,} people seen, {len(matches):,} match the suppression list ({(len(matches)/seen*100 if seen else 0):.1f}%).")
    return matches, seen


def run_sweep(args: argparse.Namespace) -> int:
    headers = get_credentials_and_headers()

    suppression = load_combined()
    allowlist = load_allowlist()
    leaked = allowlist & suppression
    if leaked:
        sys.exit(
            f"ERROR: Allowlist domains found in combined.txt: {sorted(leaked)}\n"
            f"This indicates a build script bug. Re-run scripts/build.py and try again."
        )

    suppression -= allowlist  # belt-and-suspenders; build.py already does this
    print(f"Loaded {len(suppression):,} suppression domains and {len(allowlist):,} allowlist entries.")

    tag_name = args.tag or f"psup_{date.today().isoformat()}"
    print(f"Tag: {tag_name}")

    audit_path = Path(args.audit_log) if args.audit_log else Path(f"audit-an-sweep-{tag_name}.csv")
    print(f"Audit log: {audit_path}")
    print()

    matches, seen = find_matches(headers, suppression, allowlist, args.force)

    if not matches:
        print("\n✓ No matches found. Nothing to tag.")
        return 0

    if args.limit is not None and args.limit < len(matches):
        print(f"\n[--limit {args.limit}] Capping at first {args.limit:,} of {len(matches):,} matches.")
        matches = matches[:args.limit]

    if args.dry_run:
        print(f"\n[--dry-run] Would tag {len(matches):,} person(s). First 20:")
        for m in matches[:20]:
            print(f"  + {m['email']}  (domain: {m['domain']})")
        if len(matches) > 20:
            print(f"  ... and {len(matches) - 20:,} more")
        print(f"\nNo changes made. Drop --dry-run to apply tag '{tag_name}'.")
        return 0

    # Phase 2: find-or-create tag, then apply concurrently.
    print(f"\nFinding or creating tag '{tag_name}' in Action Network...")
    tag = find_or_create_tag(headers, tag_name)
    tag_uuid = tag_uuid_from(tag)
    tag_self_url = ((tag.get("_links") or {}).get("self") or {}).get("href", "")
    if not tag_uuid:
        sys.exit("ERROR: Couldn't extract tag UUID from AN response.")
    print(f"  ✓ Tag ready (uuid={tag_uuid})")

    total = len(matches)
    print(f"\nApplying tag to {total:,} person(s) with {args.workers} parallel worker(s)...\n")

    added = 0
    failed = 0
    failures: list[tuple[str, int, str]] = []
    start = time.monotonic()
    last_print = start

    def log_progress(done: int) -> None:
        elapsed = time.monotonic() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = _format_eta(int((total - done) / rate)) if rate > 0 else "—"
        print(f"  {done:,}/{total:,}  ({added:,} tagged, {failed:,} failed)  "
              f"{rate:.1f}/sec  ETA {eta}", flush=True)

    with AuditWriter(audit_path) as audit, ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_match = {
            pool.submit(apply_tag, headers, tag_uuid, m["person_self_url"]): m
            for m in matches
        }
        for i, fut in enumerate(as_completed(future_to_match), start=1):
            m = future_to_match[fut]
            try:
                status, body, tagging = fut.result()
            except Exception as e:
                failed += 1
                failures.append((m["email"], 0, f"{type(e).__name__}: {e}"[:200]))
                audit.write(action="tag_apply_failed",
                            person_self_url=m["person_self_url"], email=m["email"],
                            domain=m["domain"], tag_name=tag_name, tag_self_url=tag_self_url,
                            status="0", note=str(e)[:200])
            else:
                if 200 <= status < 300:
                    added += 1
                    tagging_self = ""
                    if tagging:
                        tagging_self = ((tagging.get("_links") or {}).get("self") or {}).get("href", "")
                    audit.write(action="tag_applied",
                                person_self_url=m["person_self_url"], email=m["email"],
                                domain=m["domain"], tag_name=tag_name, tag_self_url=tag_self_url,
                                tagging_self_url=tagging_self, status=str(status))
                else:
                    failed += 1
                    failures.append((m["email"], status, body[:200]))
                    audit.write(action="tag_apply_failed",
                                person_self_url=m["person_self_url"], email=m["email"],
                                domain=m["domain"], tag_name=tag_name, tag_self_url=tag_self_url,
                                status=str(status), note=body[:200])
            now = time.monotonic()
            if i % PROGRESS_EVERY == 0 or (now - last_print) >= PROGRESS_INTERVAL_SECONDS:
                log_progress(i)
                last_print = now

    elapsed = time.monotonic() - start
    overall_rate = (added + failed) / elapsed if elapsed > 0 else 0
    print(f"\nDone. {added:,} tagged, {failed:,} failed in {elapsed:.0f}s ({overall_rate:.1f}/sec).")
    print(f"Audit log written to {audit_path}")
    print(f"\n  → To roll back this sweep: python3 scripts/rollback_action_network.py --audit-log {audit_path}")

    if failures:
        print(f"\nFirst 10 failures (out of {len(failures)}):")
        for email, s, b in failures[:10]:
            print(f"  {email}  HTTP {s}  {b}")
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="Pre-flight only: test env, DNS, TLS, auth, and read access. "
                             "Don't change anything. Use before your first real sweep.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't apply tag; just print what would be tagged.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N matches. Useful for first-time testing.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Concurrent taggers (default {DEFAULT_WORKERS}, max {MAX_WORKERS}).")
    parser.add_argument("--force", action="store_true",
                        help=f"Allow runs that match >{int(ANOMALY_THRESHOLD*100)}%% of fetched people.")
    parser.add_argument("--tag", type=str, default=None,
                        help="Override the default tag name. Default: psup_YYYY-MM-DD.")
    parser.add_argument("--audit-log", type=str, default=None,
                        help="Path to write the CSV audit log. Default: audit-an-sweep-<tag>.csv.")
    args = parser.parse_args()

    if args.check:
        return check_connection()

    validate_workers(args.workers)
    return run_sweep(args)


if __name__ == "__main__":
    sys.exit(main())
