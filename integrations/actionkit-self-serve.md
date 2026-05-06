# Self-serve ActionKit import

This guide walks you through importing the suppression list into your ActionKit instance's Blackhole Domains list, **without writing any code or asking ActionKit support to do it for you**.

You'll fork this repo into your own GitHub account, add three secret values that tell GitHub how to reach your ActionKit instance, and click a button. GitHub Actions runs the import on its servers, then tells you what happened.

Estimated time:

- **One-time setup:** about 10 minutes of clicking around in GitHub.
- **First full import run:** 30–60 minutes. You start it with a click, then walk away — the work happens on GitHub's servers, not your computer.
- **Future re-imports:** 30 seconds of clicking; the run itself is usually quick because almost everything is already in your list.

---

## What you need before you start

You need three pieces of information about your ActionKit instance. Get these from your engineering team or whoever set up your AK instance:

| Name | What it is | Example |
|---|---|---|
| **Instance hostname** | The web address of your AK admin panel, *without* `https://` and *without* any path | `yourorg.actionkit.com` |
| **API username** | The ActionKit user account that has API access. Often a dedicated "api" user. | `api-bot` |
| **API password** | The password for that user account. | (a long string) |

If you're not sure what these are, ask whoever administers your ActionKit instance. They'll know.

You also need a **GitHub account**. Free is fine. If you don't have one, create it at [github.com](https://github.com).

---

## One-time setup (do this once)

### Step 1: Fork this repository

A "fork" is your own personal copy of this repository. Your secrets will live in your fork — they never get sent back to us.

1. Go to **https://github.com/jordankrueger/progressive-email-suppression**
2. Click the **Fork** button in the top-right corner
3. On the next page, leave everything as default and click **Create fork**

You now have your own copy at `https://github.com/YOUR-USERNAME/progressive-email-suppression`.

### Step 2: Add your three ActionKit secrets

GitHub stores these in an encrypted vault inside your fork. Only your workflow runs can read them; they aren't visible to anyone (not even to you, after you save them) and they aren't visible to us.

1. In **your fork**, click **Settings** (top tab, far right)
2. In the left sidebar, click **Secrets and variables**, then **Actions**
3. Click the green **New repository secret** button
4. Add the first secret:
   - **Name:** `AK_INSTANCE`
   - **Secret:** your instance hostname (e.g. `yourorg.actionkit.com` — no `https://`, no trailing `/`)
   - Click **Add secret**
5. Click **New repository secret** again. Add:
   - **Name:** `AK_USERNAME`
   - **Secret:** your AK API username
   - Click **Add secret**
6. Click **New repository secret** one more time. Add:
   - **Name:** `AK_PASSWORD`
   - **Secret:** your AK API password
   - Click **Add secret**

When you're done, the Secrets page should list three secrets: `AK_INSTANCE`, `AK_PASSWORD`, `AK_USERNAME`. (GitHub sorts them alphabetically.)

### Step 3: Enable Actions in your fork

GitHub disables Actions in newly-created forks by default. Turn them on.

1. In your fork, click the **Actions** tab (top of the page)
2. You'll see a yellow banner: **"Workflows aren't being run on this forked repository."**
3. Click the green **I understand my workflows, go ahead and enable them** button

---

## Running the import (do this every time)

Once the one-time setup above is done, importing is three clicks:

1. In your fork, click the **Actions** tab
2. In the left sidebar, click **Import to ActionKit**
3. On the right side, click the **Run workflow** dropdown button
4. Leave the **rebuild first** checkbox checked (recommended — uses the freshest list)
5. Click the green **Run workflow** button

A new run will appear in the list within a few seconds. Click it, then click into the **import** job to see the live log. You'll see lines like `200/53,766 (200 added, 0 failed)` ticking up as it works.

**A full first-time import takes 30–60 minutes.** That's normal — there's a small built-in pause between calls so the script doesn't hammer ActionKit. As long as the count keeps climbing, it's working. If the log is completely silent for 10+ minutes, something's stuck; open an issue and include the log.

You can close the browser tab and come back later — the run continues on GitHub's servers either way.

### Recommended for first-time runs: sanity-check first

Before importing all 66k domains, do a small test run to confirm everything works:

- **Dry-run first.** Check the **dry-run** box on the **Run workflow** form. Nothing gets POSTed; the log just shows the first 20 domains it *would* add. If that looks right, you know the credentials and connection are working.
- **Then import a handful.** Set **limit** to `10` (instead of the default `0`) and run again. This adds 10 real entries — visible in **Mailings → List Hygiene → Blackhole** within seconds. If you see them, you're good to go.
- **Then run the full import.** Run once more with **limit** back at `0` and **dry-run** unchecked. The first full run takes 30–60 minutes.

### What you'll see when it finishes

A successful run looks like this in the workflow logs:

```
Loaded 66,169 domains from data/combined.txt
Connecting to yourorg.actionkit.com as api-bot...
Found 12,403 domains already in your Blackhole list

Adding 53,766 new domain(s)...

  200/53,766  (200 added, 0 failed)
  400/53,766  (400 added, 0 failed)
  ...
Done. 53,766 added, 0 failed.
```

The first run may take 30–60 minutes depending on how many domains need to be added (the script is intentionally polite about rate). Future runs typically take seconds because almost everything is already there.

### Re-running

The import is **idempotent** — re-running it is always safe. It checks what's already in your AK instance and only adds what's new. You can re-run it any time you want a fresh top-up. A reasonable cadence is once a quarter.

---

## Troubleshooting

### "Missing required repository secret(s)"

You skipped step 2 above, or one of the secret names is misspelled. Names are case-sensitive: `AK_INSTANCE`, `AK_USERNAME`, `AK_PASSWORD`. Go back to **Settings → Secrets and variables → Actions** and check.

### "ActionKit rejected the credentials (HTTP 401)"

The username or password is wrong, or the user account doesn't have API access. Verify with whoever administers your AK instance, then update the secret values:

1. **Settings → Secrets and variables → Actions**
2. Click the pencil icon next to `AK_PASSWORD` (or whichever is wrong)
3. Click **Update secret**, paste the new value, save

### The workflow ran but nothing happened

If the log says **"Your instance is already up to date. Nothing to add."** — that's success. Your AK instance already has every domain from the list.

### Some domains failed to add

The log will show the first 10 failures with their HTTP status codes. Common cases:
- **HTTP 400** with "domain already exists" — harmless; that domain was added in a previous run
- **HTTP 422** — usually a malformed domain. Open an issue on the upstream repo with the failing domain
- **HTTP 5xx** — ActionKit had a temporary issue. Re-run the workflow

### Something else is wrong

Open an issue at https://github.com/jordankrueger/progressive-email-suppression/issues with the workflow log (with secrets redacted — the workflow never prints them, but double-check).

---

## How to tell what was loaded

After the import finishes, log into ActionKit and go to **Mailings → List Hygiene → Blackhole**. The Blackholed Domains tab should show the new entries.

ActionKit's docs note there's typically a propagation delay (under 20 minutes) before existing users with matching email domains get their subscription state updated. Be patient.

---

## Updating the list later

This repo rebuilds nightly. To pick up new additions, just re-run the workflow — the **rebuild first** checkbox makes sure you're importing the freshest version. A quarterly re-run is plenty for most orgs; the rate of net-new bad domains is slow.

---

## Privacy note

Your ActionKit credentials live only inside your GitHub fork's encrypted secret store. They never leave your fork; they aren't sent to this project's maintainers; they aren't logged in workflow output. The only system that sees them is GitHub Actions itself, which uses them to talk directly to your ActionKit instance.

If you'd rather not put credentials in GitHub at all, the same script in `scripts/import_to_actionkit.py` runs locally — set the three environment variables and run `python3 scripts/import_to_actionkit.py`.
