#!/usr/bin/env python3
"""Rebuild the data/ files from the local snapshots and upstream community lists.

Run:     python3 scripts/build.py
Options: --no-fetch   (skip upstream HTTP pulls; use local snapshots only)
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO / "sources"
DATA_DIR = REPO / "data"

SNAPSHOTS = {
    "historical_a": SOURCES_DIR / "historical-a.txt",
    "historical_b": SOURCES_DIR / "historical-b.txt",
}

UPSTREAM_URLS = {
    "disposable-email-domains": (
        "https://raw.githubusercontent.com/disposable-email-domains/"
        "disposable-email-domains/master/disposable_email_blocklist.conf"
    ),
    "mailchecker": (
        "https://raw.githubusercontent.com/FGRibreau/mailchecker/master/list.txt"
    ),
    "fakefilter": (
        "https://raw.githubusercontent.com/7c/fakefilter/main/txt/data.txt"
    ),
}

DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z0-9-]{2,}$")

TYPO_PATTERNS = [
    re.compile(p) for p in [
        r".*g?mail[a-z0-9]*\.com$",
        r".*yahoo[a-z0-9]*\.[a-z]{2,}$",
        r".*hotmail[a-z0-9]*\.[a-z]{2,}$",
        r".*icloud[a-z0-9]*\.com$",
        r".*aol[a-z0-9]*\.com$",
        r".*outlook[a-z0-9]*\.com$",
    ]
]


def normalize(raw: object) -> str | None:
    if not raw:
        return None
    d = str(raw).strip().lower().lstrip("@")
    if not d or d.startswith("."):
        return None
    # Internationalized domains (e.g. "café.com") → punycode ASCII form
    # ("xn--caf-dma.com") so dedupe works regardless of which form a source uses.
    if any(ord(c) > 127 for c in d):
        try:
            d = d.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    if not DOMAIN_RE.match(d):
        return None
    return d


def _parse_lines(text: str) -> set[str]:
    out = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        d = normalize(line)
        if d:
            out.add(d)
    return out


def read_list_file(path: Path) -> set[str]:
    return _parse_lines(path.read_text(encoding="utf-8"))


def fetch_upstream(url: str, timeout: int = 20) -> set[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "progressive-email-suppression/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", errors="replace")
    return _parse_lines(text)


def classify_typo(domain: str) -> bool:
    return any(p.match(domain) for p in TYPO_PATTERNS)


def write_list(path: Path, domains: set[str], header: str) -> None:
    body = "\n".join(sorted(domains))
    path.write_text(f"{header}\n{body}\n", encoding="utf-8")


def build(fetch: bool = True) -> dict[str, int]:
    historical_a = read_list_file(SNAPSHOTS["historical_a"])
    historical_b = read_list_file(SNAPSHOTS["historical_b"])

    combined = historical_a | historical_b

    upstream_summary = {}
    if fetch:
        for name, url in UPSTREAM_URLS.items():
            try:
                upstream = fetch_upstream(url)
                combined.update(upstream)
                upstream_summary[name] = len(upstream)
            except Exception as e:  # noqa: BLE001 — soft-fail on network errors
                print(f"[warn] skipping {name}: {e}", file=sys.stderr)
                upstream_summary[name] = -1

    typos = {d for d in combined if classify_typo(d)}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    base_stamp = (
        f"# progressive-email-suppression — generated {today}\n"
        f"# Source: https://github.com/jordankrueger/progressive-email-suppression"
    )
    cc0_stamp = f"{base_stamp}\n# License: CC0 1.0 (public domain)"
    mixed_stamp = (
        f"{base_stamp}\n"
        f"# License: mixed — see LICENSE and LICENSES/ in the source repo.\n"
        f"# Compilation: CC0 1.0 where permissible; portions from\n"
        f"# mailchecker (MIT), fakefilter (BSD 3-Clause), disposable-email-domains (CC0)."
    )

    write_list(DATA_DIR / "combined.txt", combined,
               f"{mixed_stamp}\n# {len(combined)} domains (two progressive advocacy orgs' historical lists + upstream community lists)")
    write_list(DATA_DIR / "historical-a.txt", historical_a,
               f"{cc0_stamp}\n# Historical internal exclude list from a progressive advocacy org, circa 2019 ({len(historical_a)} domains)")
    write_list(DATA_DIR / "historical-b.txt", historical_b,
               f"{cc0_stamp}\n# Historical internal exclude list from a second progressive advocacy org ({len(historical_b)} domains)")
    write_list(DATA_DIR / "typos.txt", typos,
               f"{mixed_stamp}\n# {len(typos)} domains matching typosquat patterns of major providers")

    return {
        "combined": len(combined),
        "historical_a": len(historical_a),
        "historical_b": len(historical_b),
        "typos": len(typos),
        **{f"upstream:{k}": v for k, v in upstream_summary.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-fetch", action="store_true",
                        help="Skip upstream HTTP pulls")
    args = parser.parse_args()
    summary = build(fetch=not args.no_fetch)
    print("Build summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
