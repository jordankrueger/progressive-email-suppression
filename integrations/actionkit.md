# ActionKit

ActionKit is the only major progressive ESP with a native domain-level exclusion feature — they call it **Blackhole Domains**. Good news. The less-good news: bulk import isn't documented as self-serve.

## The feature

**Mailings > List Hygiene > Blackhole**. Three sub-lists:

- Blackholed Emails (full addresses)
- Blackholed Domains (domain-level exclusion — what this list targets)
- Blackholed Patterns (regex patterns)

Under the hood, matches are recorded in `core_blackholedhistory` and matched users get `subscription_status='blocked'` on `core_user`. AK's docs note there's a propagation delay — typically under 20 minutes — between adding a domain or pattern and the `subscription_status` actually updating for existing users.

## Loading this list

Three paths, in order of preference:

### 1. Ask the Walkers

Best option today. Send ActionKit support the `combined.txt` file (or the raw URL) and ask them to bulk-import it into your instance's Blackholed Domains list. In our experience they'll do it — they just need a clean file.

A draft email template for this ask lives outside this repo in Jordan's local notes. If you want a copy, open an issue.

### 2. Paste via UI (small additions only)

For a handful of domains, the UI works fine. For thousands, don't. This exists as a reality check, not a recommendation.

### 3. API (possibly available, undocumented)

There's an unconfirmed reference suggesting AK added API support for blackhole domain management in a past release, but the ActionKit REST API docs don't list such an endpoint. If the endpoint exists in your instance, a loop like this might work:

```python
# Hypothetical — confirm endpoint exists and verify payload shape
# with AK support (the Walkers) before running at scale
import requests

TOKEN = "your-ak-api-token"
BASE = "https://yourinstance.actionkit.com/rest/v1"

with open("combined.txt") as f:
    domains = [line.strip() for line in f if line.strip() and not line.startswith("#")]

for d in domains:
    r = requests.post(
        f"{BASE}/blackholed_domain/",
        auth=("username", TOKEN),
        json={"domain": d},
    )
    if not r.ok:
        print(f"{d}: {r.status_code} {r.text}")
```

The endpoint name and payload shape are guesses based on AK's REST naming patterns, not a verified contract. Confirm with the Walkers first.

## Keeping it fresh

Once the initial bulk import is done, a quarterly refresh is usually enough. This repo rebuilds nightly, but AK's exclusion list doesn't need to stay that fresh — the rate of net-new bad domains is slow.

A light automated approach: a GitHub Action or n8n workflow that fetches `combined.txt` quarterly, diffs against the last run, and POSTs only the new additions to AK (if the API is available) or emails a fresh delta file to the Walkers.
