# EveryAction / NGP VAN

Like Action Network, EveryAction (and its NGP VAN sibling) has no native domain-level suppression feature. Suppression lives at the person level via the `doNotEmail` flag and activist-code suppressions. The integration patterns are similar to Action Network.

## Pattern A: API proxy at signup (recommended)

If your signup forms POST to EveryAction via the API, put your own endpoint in front and insert a domain check there. The relevant EA endpoints for signup creation include `POST /v4/people/findOrCreate` (confirmed) and `/v4/onlineActionsForms/...` (endpoint exists; verify the specific create shape in EA's API reference).

1. Receive form submission on your own endpoint (n8n, serverless function, API route)
2. Extract email domain
3. Check against `combined.txt` (cache daily)
4. On match: reject with a "please verify your email" response
5. Otherwise: POST to the EA endpoint as normal

## Pattern B: scheduled sweep (for existing records)

For people already in the database:

1. Fetch `combined.txt`
2. Query EveryAction for people whose email domain matches (you'll likely need to iterate and filter client-side — see below)
3. Mark each matching person's email as unsubscribed via `PATCH /v4/people/{vanId}` — the email address object exposes a `subscriptionStatus` field (it replaced the deprecated `isSubscribed` boolean). **Verify the exact enum value your EA instance accepts** (e.g., `"U"`, `"Unsubscribed"`) against EA's current API reference before running at scale — the value is not documented publicly in a way I could verify.
4. Optionally apply an activist code (e.g., `EXCLUDED_DOMAIN`) for reporting

The EveryAction People API doesn't let you filter by email substring server-side, so you'll either need to export and filter locally, or iterate over recent records. For many orgs, a one-time export + filter + re-import is easier than building a live API sweep.

## Questions to ask your NGP account manager

If your org pays for premium support, ask:

- Can they run a one-time SQL suppression against a domain list you provide?
- Is there a way to create a "Do Not Email" rule at the domain level that applies to all future uploads?

In our experience the answer to both is usually "not really, but we can run a one-time cleanup if you send us the list." That's still useful — just not self-serve.

## Internal forms

If the offending signups are coming through VAN's own hosted forms (Online Actions / OLAs, MiniVAN, etc.), pre-filtering isn't possible. Pattern B is your only option.
