# EveryAction / NGP VAN

> **No executable script. This is a manual process guide.** EveryAction and NGP VAN are paid Democratic-vendor products with no free tier or public sandbox we can test against. We're not willing to publish a script for the platform that runs national-level Democratic infrastructure without testing it end-to-end first. If your org can grant a partner test instance with API access, we'd love to build one. Open an issue.
>
> **What this doc covers instead:** three manual paths to apply the suppression list, each suited to a different kind of org. Pick the one that matches your situation, then follow the step-by-step.

---

## What "applying the list" means in EveryAction

Like Action Network, EveryAction has no native domain-level suppression feature. Suppression lives at the person level. Two approaches work:

- **Tag matched people with an activist code** (e.g., `EXCLUDED_DOMAIN_SUPPRESSION_LIST`), then use the activist code as a filter when building mailing lists. **Reversible.** Recommended for a first run.
- **Flip matched people's email subscription status to "Unsubscribed"** via the email address subobject. **Not reversible at the API level** without a separate process to re-subscribe them.

In both cases, the suppression list is the input. EA's People API has no server-side filter for "email domain in (...)", so any approach has to fetch records and filter client-side.

---

## Pick a path

| Your situation | Path |
|---|---|
| Non-technical admin, no in-house data team, NGP-paid support | **Path 1: Ask NGP support** |
| You have a data team with API access and SQL fluency | **Path 2: Custom API recipe** |
| Limited API access, but you can export and re-import via the AnyImport pipeline | **Path 3: Export → filter → re-import** |

---

## Path 1: Ask NGP support

If your org pays for NGP VAN's premium support, this is by far the easiest path. NGP support has run domain-based suppressions for other orgs in the past. They'll typically:

1. Accept a CSV of bad domains (your list)
2. Run a backend SQL job that finds matching people in your database
3. Apply an activist code or flip subscription status, depending on what you ask for
4. Send you a count of records affected

**How to ask:**

> Hi [NGP rep's name],
>
> We're applying a domain-level email suppression list to our database (~66,000 disposable, typo, and spam-trap domains) to clean up existing records and to be more careful about future imports. The list is from progressive-email-suppression on GitHub (CC0-licensed).
>
> Can you run a one-time backend job to:
> 1. Find any existing person record whose primary email's domain matches one of the entries in the attached CSV
> 2. Apply the activist code `EXCLUDED_DOMAIN_SUPPRESSION_LIST` (or a name of your choosing) to those records
> 3. Send back a count of records affected
>
> We're starting with the activist-code approach so we can verify and reverse if needed. After we've validated, we may follow up to also flip subscription status on flagged records.
>
> The CSV is attached. ~66k rows, one domain per line.

**What to verify when they confirm:**

- The activist code was created (or already existed) at the right level (org-wide vs committee-specific)
- The count of records affected is in a reasonable range (typically <5% of your DB; if it's higher, ask NGP what their query found before approving)
- They didn't change subscription status on anything (that's a separate request)

**If they say no:** ask for the SQL query they would have run, or ask whether your data team could run it through your read/write API access. That's Path 2.

---

## Path 2: Custom API recipe (for orgs with a data team)

Verify against the official docs before running anything: https://docs.everyaction.com/. EA's API surface and enum values evolve; this recipe is a current-as-of-2026-05 outline, not a substitute for reading their reference.

### Prerequisites

- An EA API key with read + activist-code-apply permissions (and write permissions to People, if you'll later flip subscription status)
- Python 3.9+ (or any HTTP client your team is comfortable with)
- The list: clone progressive-email-suppression and use `data/combined.txt`

### Recipe outline

**Step 1: Verify the activist code exists, or create it.**

```
GET /v4/activistCodes?name=EXCLUDED_DOMAIN_SUPPRESSION_LIST
```

If it doesn't exist:

```
POST /v4/activistCodes
{
  "name": "EXCLUDED_DOMAIN_SUPPRESSION_LIST",
  "description": "Email domain matched the progressive-email-suppression list. Auto-applied YYYY-MM-DD.",
  "type": "Activist"
}
```

**Verify the create response.** Save the returned `activistCodeId`.

**Step 2: Page through People.**

EA's People list endpoint paginates with `?$top=N&$skip=M` (verify on your version). The hard `$top` ceiling has historically been 200; newer versions may differ. Page size matters: bigger pages mean fewer round trips.

Pseudocode:

```python
top = 200
skip = 0
while True:
    page = GET(f"/v4/people?$top={top}&$skip={skip}&$expand=emails")
    items = page.get("items", [])
    if not items:
        break
    for person in items:
        process(person)
    skip += top
```

**Step 3: For each person, check their primary email's domain.**

```python
def primary_email_domain(person):
    for email in person.get("emails", []):
        if email.get("isPreferred"):
            addr = (email.get("email") or "").lower()
            return addr.split("@", 1)[-1] if "@" in addr else ""
    return ""
```

If `domain in suppression_set` and `domain not in allowlist_set`, flag the person.

**Step 4: Apply the activist code to flagged people.**

```
POST /v4/people/{vanId}/activistCodes
{
  "activistCodeId": <from step 1>
}
```

**Important:** EA's docs use multiple person-identifier types (`vanId`, `extendedSourceCode`, etc.). Use whatever ID you got from the People list response, most commonly `vanId`.

**Step 5: Throttle.**

EA does not document a public rate limit. Empirically, ~2 req/sec is safe; 5+ may surface 429s on shared instances. Start at 2/sec, watch for 429s, dial up if clean.

**Step 6: Audit log.**

Write every change to a CSV. Minimum columns: `timestamp, vanId, email, domain, activist_code_id, status`. This is your only path to a rollback later. If you don't capture it, you have no way to find the records you tagged.

### Sanity-check before scaling up

- Run against your first 200 people only (`top=200`, no loop).
- Verify the activist code shows up on the matched people in EA's UI.
- Verify a non-matched person did NOT get the code applied.
- Spot-check 10 of the matched people. Do their domains look like real junk?

If everything looks right, proceed to a full run. **Do not skip the sample step.** The consequences of a bad query in EA are slow to undo.

---

## Path 3: Export → filter → re-import

If your API access is limited (some EA tenants restrict API write permissions to specific roles) but you have data export and AnyImport access:

1. **Export your People list** to CSV via the UI's data export. Include `vanId`, `email`, and any custom fields you care about.
2. **Filter locally** against `combined.txt`:
   ```python
   bad = set(open("combined.txt").read().splitlines())
   matches = [row for row in people if row["email"].split("@")[-1].lower() in bad]
   ```
3. **Re-import via AnyImport** with a single column added: `ApplyActivistCode = EXCLUDED_DOMAIN_SUPPRESSION_LIST`. AnyImport's "match on vanId, apply activist code" mode does not modify any other field.
4. **Verify.** Check 10 records via the UI. Confirm the activist code is applied and nothing else changed.

This path trades velocity for safety. It's slower than the API recipe but easier to QA, because you can review the input CSV before re-importing.

---

## Verifying `subscriptionStatus` enum values (if you later flip status)

If your org decides to also flip subscription status on flagged records (separate from tagging), do NOT just PATCH at scale based on a value you saw in another vendor's docs. EA's `subscriptionStatus` field has historically used different enum values across API versions; examples in the wild include `"U"`, `"Unsubscribed"`, and `"NotSubscribed"`. **Confirm your instance's accepted values before running at scale:**

1. Pick one test person in EA's UI. Note their current subscription status.
2. PATCH them with the value you intend to use:
   ```
   PATCH /v4/people/{vanId}
   {
     "emails": [
       {"email": "<their address>", "isPreferred": true, "subscriptionStatus": "<value>"}
     ]
   }
   ```
3. Check the response: 200 means accepted. Verify the change in EA's UI within a few minutes.
4. PATCH them back to their original status. Now you know the right enum value.

Only after this PATCH-PATCH-back round-trip succeeds should you script anything at scale.

---

## Questions to ask your NGP account manager

If your org pays for premium support, ask:

- "Can you run a one-time SQL suppression against a domain list we provide?" (Yes, in our experience.)
- "Is there a way to create a `Do Not Email` rule at the domain level that applies to all future imports automatically?" (Usually no, but ask. Features change.)
- "What's the exact enum value for `subscriptionStatus = unsubscribed` in our instance's API?" (They can answer this immediately; saves a debugging round-trip.)
- "If we apply an activist code to ~5,000 people, will that affect any existing automations or campaign queries that filter on activist codes?" (Worth checking before triggering downstream side effects.)

---

## Internal forms (Online Actions / OLAs, MiniVAN)

If the offending signups are coming through VAN's own hosted forms (Online Actions / OLAs, MiniVAN, etc.), pre-filtering at signup-time isn't possible: the platform creates the record before any external system sees it. Your only option is periodic cleanup (any of the three paths above).

---

## Why we don't ship a script for this, and what would change that

We want to ship one. We don't ship one yet because:

- EveryAction has no free tier we can test against.
- Shipping an untested suppression script for the platform that runs national-scale Democratic infrastructure is the kind of thing that ends careers when it goes wrong.
- The 2026-05-07 incident with our ActionKit script (a 6-hour timeout caused by serial POSTs) was on a script we *had* tested end-to-end. The failure modes for an untested EA script would be worse and harder to roll back.

**What changes that:** a partner org with an EA instance who's willing to grant us API access for testing. If that's you, [open an issue on GitHub](https://github.com/jordankrueger/progressive-email-suppression/issues).
