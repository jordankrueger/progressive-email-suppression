# Self-serve Action Network sweep

> ℹ️ **Verified against AN's documented API contract; awaiting first real-org end-to-end validation.** Action Network's API access is a partner-tier feature, so we couldn't run this against a fresh test account before shipping. The scripts hit AN's documented endpoints (POST `/api/v2/tags/`, POST `/api/v2/tags/{uuid}/taggings/`, paginated GET `/api/v2/people/`) with the documented request shapes. If you're the first to run it against a live AN instance and something doesn't match, please [open an issue](https://github.com/jordankrueger/progressive-email-suppression/issues/new/choose) — we'll fix it the same day.

This guide walks you through tagging existing people in your Action Network group whose primary email domain is on the suppression list — **without writing any code**. You fork this repo into your own GitHub account, add one secret (your AN API key), and click a button.

The sweep applies a tag (default name: `psup_YYYY-MM-DD`). It does **not** unsubscribe anyone. You then use the tag in AN's standard mailing filters to exclude tagged people from sends. If you want to undo the sweep, a rollback workflow removes every tagging it applied.

## The short version

Four phases, in order:

1. **Set up** (about 10 minutes, once) — fork the repo, add one secret, enable Actions.
2. **Test the connection** (5 seconds) — confirm your secret works before running anything that makes changes.
3. **Sanity-check** (2 minutes) — dry-run + a 10-person test sweep so you can see entries get tagged in AN.
4. **Run the full sweep** (varies by group size, 20 minutes – 2 hours typical) — kick it off, walk away, check back later.

There are three workflows in the Actions tab once you fork:

- **Test Action Network connection** — read-only pre-flight check. Use this first.
- **Sweep Action Network** — the main event. Tags people whose email matches the suppression list.
- **Rollback Action Network sweep** — destructive undo. Removes every tagging that a previous sweep applied. Reads from the audit-log artifact uploaded by the sweep run.

A nightly **rebuild** workflow also exists; you do *not* need to enable or run it. It only matters for keeping your fork's local copy of the data current, which the sweep workflow handles automatically when you check "rebuild first".

> **Why tag, not unsubscribe?** Subscription-state changes are not reversible at the API level. Tagging is. We tag matched people and let you decide how to use the tag — exclude them from a single mailing, exclude them permanently via a query, or run a separate "really unsubscribe these" step after you've spot-checked. If anything goes wrong, the rollback workflow restores the previous state.

---

## What you need before you start

**One piece of information about your Action Network group:**

- **API key** — a long random string in the OSDI-API-Token header format. Find it in your AN group's admin under **Start Organizing → API & Sync**.

> **Don't see API & Sync?** Action Network gates API access behind their partner / Integration Partnership program. If your org doesn't see the page, contact AN at `support@actionnetwork.org` to request API access. Most active orgs running on AN at any meaningful scale already have this; it's typically a quick yes for orgs with real campaigns. If you're trying this on a brand-new free Individual account, you'll need to apply first.

A few practical notes:

- **Each AN group has its own API key.** If your org runs multiple groups (chapters, committees), pick the group you actually want suppressed. You can re-run this against multiple groups by updating the secret between runs, or by maintaining multiple forks.
- **Treat the key like a password.** Anyone with it can read and modify every person in your group. The setup steps below put it in GitHub's encrypted secret store; it's never written to logs.

You also need a **GitHub account**. Free is fine. If you don't have one, create it at [github.com](https://github.com).

---

## One-time setup

### Step 1: Fork this repository

A "fork" is your own personal copy of this repository. Your secret will live in your fork — it never gets sent back to us.

1. Go to **https://github.com/jordankrueger/progressive-email-suppression**
2. Click the **Fork** button in the top-right corner
3. On the next page, leave everything as default and click **Create fork**

You now have your own copy at `https://github.com/YOUR-USERNAME/progressive-email-suppression`.


### Step 2: Add your AN API key as a secret

GitHub stores this in an encrypted vault inside your fork. Only your workflow runs can read it; it isn't visible to anyone (not even to you, after you save it).

1. In **your fork**, click **Settings** (top tab, far right)
2. In the left sidebar, click **Secrets and variables**, then **Actions**
3. Click the green **New repository secret** button
4. Add:
   - **Name:** `AN_API_KEY`
   - **Secret:** your Action Network API key
   - Click **Add secret**


### Step 3: Enable Actions in your fork

GitHub disables Actions in newly-created forks by default. Turn them on.

1. In your fork, click the **Actions** tab (top of the page)
2. You'll see a yellow banner: **"Workflows aren't being run on this forked repository."**
3. Click the green **I understand my workflows, go ahead and enable them** button


### Step 4: Test the connection

Before running a sweep, run the pre-flight check. It takes a few seconds and confirms your secret works without changing anything in AN.

1. In your fork, click the **Actions** tab
2. In the left sidebar, click **Test Action Network connection**
3. On the right, click the **Run workflow** dropdown, then click the green **Run workflow** button
4. A run appears in the list within a few seconds. Click it, then click into the **test** job to see the live log.

A successful run looks like this:

```
AN_API_KEY is present.
Checking Action Network connection...

  ✓ Environment variable set (AN_API_KEY)
  ✓ DNS + HTTPS connection to actionnetwork.org OK
  ✓ Authenticated to AN — "Welcome to the Action Network API!"
  ✓ API access OK — read /api/v2/ HAL root successfully

Connection check passed. You're ready to run the sweep workflow.
```

If you see a **✗** anywhere, the log includes a friendly diagnosis pointing at the most common cause. Read it, fix the secret it points at, and run **Test Action Network connection** again. **Don't move on to the sweep until this is fully green** — every problem this catches will *also* show up in the sweep, but with much more wasted time.

---

## Run the sweep

Once the connection test is green, run the sweep:

1. In your fork, click the **Actions** tab
2. In the left sidebar, click **Sweep Action Network**
3. On the right, click the **Run workflow** dropdown
4. **For your first run:** leave **dry_run** checked, set **limit** to `50`, leave everything else as default
5. Click the green **Run workflow** button


A new run appears in the list within a few seconds. Click it, then click into the **sweep** job to see the live log. The scan walks every person in your group at AN's hard 25-per-page limit — for a 10k-person group, expect ~5 minutes of scanning before any matches are reported.

**A successful first dry-run looks like this:**

```
Loaded 66,169 suppression domains and 37 allowlist entries.
Tag: psup_2026-05-10
Audit log: audit-an-sweep-psup_2026-05-10.csv

Scanning Action Network group (page size 25, no server-side filter — this can take a while)...
  scanned 500 people, 28 matches so far (5.6%)
  scanned 1,000 people, 53 matches so far (5.3%)
  ...

Done scanning. 8,432 people seen, 421 match the suppression list (5.0%).

[--limit 50] Capping at first 50 of 421 matches.

[--dry-run] Would tag 50 person(s). First 20:
  + jane@disposable.io  (domain: disposable.io)
  + bob@gnail.com       (domain: gnail.com)
  ...
  ... and 30 more

No changes made. Drop --dry-run to apply tag 'psup_2026-05-10'.
```

### Recommended first-real-run: 10 entries, with apply

After dry-run looks right, do a small real sweep to confirm the round-trip works end-to-end:

1. Run **Sweep Action Network** again
2. **Uncheck `dry_run`**
3. **Check `apply_changes`** (this belt-and-suspenders flag is required to make any actual changes)
4. Set **limit** to `10`
5. Click **Run workflow**

This tags 10 actual people. Open AN admin, navigate to **Tags**, find your `psup_2026-05-10` tag, and click into it. You should see exactly 10 people tagged. **Spot-check 3-4 of them** — confirm their email addresses look like junk (disposable / typo / spam-trap domains).

If those 10 look right: run the full sweep with the same flags but `limit` set to `0`.


### What success looks like

A successful full run ends with something like this in the workflow log:

```
Done. 421 tagged, 0 failed in 134s (3.1/sec).
Audit log written to audit-an-sweep-psup_2026-05-10.csv

  → To roll back this sweep: python3 scripts/rollback_action_network.py --audit-log audit-an-sweep-psup_2026-05-10.csv
```

Scroll back up in the run page to the **Artifacts** section — you'll see `audit-log` listed. **Download it now** (or note the run ID — the Rollback workflow can find it later by run ID). The CSV inside lists every person tagged.

In Action Network admin, navigate to **Tags → psup_YYYY-MM-DD** to see all tagged people in one view.

### Using the tag

Tagging doesn't suppress anything by itself — you still have to use the tag. Two common patterns:

- **Mailing-by-mailing:** when sending an email blast, exclude `psup_YYYY-MM-DD` from the recipient query.
- **Permanent suppression query:** create a saved query that always excludes `psup_*` tags. Use this query as the basis for any future blast.

Some orgs prefer to also flip subscription status on tagged people (more permanent). That's a separate step we don't automate here — see the manual recipe in [everyaction.md](everyaction.md) for the equivalent process; the AN version is structurally identical.

---

## Undoing a sweep

If you tagged the wrong group, want to start over, or no longer want the suppression applied, run **Rollback Action Network sweep** to remove every tagging the sweep applied.

> ⚠️ **Read the audit log first.** The rollback only undoes what's in the audit log it reads. If the log is truncated (e.g., a workflow timeout), only the recorded portion gets rolled back. The CSV is line-buffered, so even a hard kill should preserve all rows up to the moment of failure — but verify the row count looks right before running rollback.

To run the rollback:

1. Find the **Sweep Action Network** run you want to undo. Copy its run ID from the URL — the number after `/actions/runs/` (e.g., the URL `https://github.com/yourorg/.../actions/runs/12345678` → run ID `12345678`).
2. In your fork, click the **Actions** tab
3. In the left sidebar, click **Rollback Action Network sweep**
4. Click **Run workflow**, paste the run ID into **sweep_run_id**
5. **Leave `confirm` unchecked.** This first run is a dry-run preview — it lists what would be removed but takes no action.
6. Read the dry-run log. Confirm the count matches what you tagged.
7. Run **Rollback** again with the same `sweep_run_id` AND **`confirm` checked**. This actually removes the taggings.

After rollback, the audit log of removals is uploaded as a `rollback-audit-log` artifact (90-day retention). The tag entity itself remains in your AN — Action Network does not allow deleting tags via API. Hide it from the AN UI's tags list manually if it's in the way.

---

## If something goes wrong

This is a decision tree. Find what you saw, follow the fix.

**"Missing required repository secret: AN_API_KEY"**
You skipped Step 2, or the secret name is misspelled. The name is case-sensitive: `AN_API_KEY`. Go back to **Settings → Secrets and variables → Actions** and check.

**Test connection says ✗ "Action Network rejected the API key (HTTP 401)"**
The key is wrong, expired, or revoked. Re-copy it from your AN admin (**Start Organizing → Details → API & Sync**) and update the secret. Note that each AN group has its own key — make sure you're using the right group's key.

**Test connection says ✗ "Action Network authenticated but refused the request (HTTP 403)"**
The key is valid but doesn't have permission for the API. Check your AN group's API settings — some tiers restrict API access; contact AN support if you can't enable it.

**Sweep refuses to run with "Both 'dry_run' and 'apply_changes' are unchecked"**
This is a safety guard. To run, you must either leave `dry_run` checked (preview only) OR uncheck `dry_run` AND check `apply_changes`. The double-flag prevents accidental destructive runs.

**Sweep says "ERROR: Match rate is 47.3% after scanning 200 people"**
The halt-on-anomaly safety net kicked in. This is almost always a data problem, not a real "47% of your AN database is bad". Most likely causes:
- `combined.txt` was edited or corrupted
- Your test group was seeded entirely with disposable-domain addresses (in which case re-run with **`force`** checked)
- The allowlist isn't being applied (open an issue with your run log)

**Sweep finishes with `0 tagged, X failed` and X is most or all of them**
Something's structurally wrong — possibly an AN outage, a key revocation mid-run, or a bug in our handling. Check status.actionnetwork.org first. If AN is up, open an issue with the workflow log link.

**Sweep was running fine, then the GitHub job timed out at 6h**
Unusual at the default settings — AN's pagination caps the scan rate. If your group is large enough to hit this, contact us via an issue and we'll add explicit checkpoint/resume support. In the meantime, you can re-run; the sweep is idempotent (re-tagging an already-tagged person is a no-op via AN's natural API behavior).

**Rollback says "No audit log CSV found in the downloaded artifact"**
The sweep run you pointed at didn't produce an audit log — possibly because it failed before any tagging happened, or it was a dry-run (dry-runs don't write the log). Pick a different sweep run that actually applied tags.

**Something else**
Open an issue using the **I need help with the AN sweep** template at https://github.com/jordankrueger/progressive-email-suppression/issues/new/choose. Include the workflow log link (secrets are never logged, but glance at it before sharing just in case).

---

## FAQ

**Will tagged people stop receiving mail immediately?**
No — tagging by itself doesn't change subscription status. Use the tag as an exclusion in your mailing queries (per "Using the tag" above). This is intentional: it gives you full control over when and how the suppression takes effect.

**Can I undo a sweep?**
Yes — see the **Undoing a sweep** section above. The rollback only operates on the audit log it reads, so it can never affect anything else in your group.

**Can I run this against multiple AN groups?**
Yes. Two ways:
- Run multiple times against the same fork by updating `AN_API_KEY` between runs (manual, but each run uses a different group's key)
- Fork the repo multiple times, each with its own `AN_API_KEY` pointing at a different group (cleaner — no swapping)

**Can I customize the tag name?**
Yes. Set the **tag_name** input on the workflow form. Useful for orgs running multiple sweeps or who want to namespace by purpose (e.g., `auto-suppress-disposable-2026-05`).

**Will Jordan or anyone else see my API key?**
No. GitHub stores repository secrets in an encrypted vault inside *your* fork. They aren't visible to other accounts (including Jordan's), they aren't visible to anyone after you save them (you can't read them back, only update or delete), and they aren't logged in workflow output. The only system that sees them is GitHub Actions itself, which uses the key to talk directly to Action Network's API.

**What if my AN API key rotates?**
Update the `AN_API_KEY` secret in **Settings → Secrets and variables → Actions** (click the pencil icon, paste the new value, save). Then run **Test Action Network connection** to confirm.

**Should I enable the nightly rebuild action?**
No, you don't need to. The rebuild action would keep your fork's data files current, but the sweep workflow already handles this when **rebuild_first** is checked. Save the Actions minutes.

**What if my AN group has hundreds of thousands of people?**
The bottleneck is AN's hard 25-per-page limit on the People collection. A 100k-person group needs ~4,000 GET requests just to scan. With the rate limit, that's roughly 20-25 minutes of scanning before any tagging happens. A million-person group could push 3-4 hours. Both should fit comfortably inside GitHub's 6h workflow ceiling, but if you're at the upper end and concerned, run with `limit` set to a fraction of your DB size first to gauge.

**How does this interact with AN's hosted forms?**
The sweep cleans up records that are already in your group, regardless of how they got there. It doesn't prevent new bad signups via AN-hosted forms — that requires the API proxy pattern (Pattern A in [action-network.md](action-network.md)).

**How do I sync updates from upstream?**
Your fork doesn't auto-update. To pull in changes (new sources, script improvements, etc.), use GitHub's **Sync fork** button at the top of your fork's main page, then click **Update branch** in the dropdown. It's safe — your secret is stored separately and isn't affected. You don't *need* to sync regularly; the sweep workflow uses upstream data via the **rebuild_first** step regardless of when you last synced.

**Is there a way to test against a staging AN group before production?**
Yes — point your fork at staging first (set `AN_API_KEY` to the staging group's key). Run **Test Action Network connection** + a `--limit 10` sweep. Once you're satisfied, update the secret to point at production and run again.

---

## Privacy

Your Action Network API key lives only inside your GitHub fork's encrypted secret store. It never leaves your fork; it isn't sent to this project's maintainers; it isn't logged in workflow output. The only system that sees it is GitHub Actions itself, which uses it to talk directly to Action Network's API.

The audit log uploaded as a workflow artifact contains the email addresses and AN URLs of tagged people. Workflow artifacts are visible only to people with read access to your fork — for most forks (default settings), that's you and anyone you've explicitly added as a collaborator. If you'd like the audit log redacted before download (e.g., for compliance), open an issue.

---

## Running locally instead

If you'd rather not put credentials in GitHub, the same scripts run locally. Set the environment variable and run:

```sh
export AN_API_KEY="your-key-here"

# Pre-flight check
python3 scripts/sweep_action_network.py --check

# Dry-run with a small limit
python3 scripts/sweep_action_network.py --dry-run --limit 50

# Real sweep with a small limit (sanity check)
python3 scripts/sweep_action_network.py --limit 10

# Full sweep
python3 scripts/sweep_action_network.py

# Roll back from the audit log
python3 scripts/rollback_action_network.py --audit-log audit-an-sweep-psup_2026-05-10.csv          # dry-run
python3 scripts/rollback_action_network.py --audit-log audit-an-sweep-psup_2026-05-10.csv --yes   # actually delete
```

No `pip install` needed — stdlib only.
