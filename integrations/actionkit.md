# ActionKit

ActionKit is the only major progressive ESP with a native domain-level exclusion feature — they call it **Blackhole Domains**.

## The feature

**Mailings > List Hygiene > Blackhole**. Three sub-lists:

- Blackholed Emails (full addresses)
- Blackholed Domains (domain-level exclusion — what this list targets)
- Blackholed Patterns (regex patterns)

On many AK installs the match is recorded in a history table and the affected user's subscription status gets flipped to a blocked state — the exact table and column names are version-specific, so verify against your own schema before writing queries. What's consistent across installs is the behavior: AK's docs note there's a propagation delay — typically under 20 minutes — between adding a domain or pattern and existing users' subscription state actually updating.

## Loading this list

### Recommended: self-serve via GitHub Actions

**👉 Step-by-step guide: [actionkit-self-serve.md](./actionkit-self-serve.md)**

The short version: fork this repo, add three secrets (`AK_INSTANCE`, `AK_USERNAME`, `AK_PASSWORD`), and click "Run workflow." Your credentials live only in your fork's encrypted secret store; the workflow runs on GitHub's servers and talks directly to your AK instance. Idempotent — safe to re-run.

Designed to work without writing any code. About 10 minutes the first time, 30 seconds after that.

### Alternative: run the import script locally

If you'd rather not put credentials in GitHub, `scripts/import_to_actionkit.py` runs anywhere with Python 3.9+ and stdlib only. Set `AK_INSTANCE`, `AK_USERNAME`, `AK_PASSWORD` as environment variables and run it.

### Alternative: paste via UI (handful of domains only)

For a small number of additions, ActionKit's UI works fine. For thousands, don't. This exists as a reality check, not a recommendation.

## API reference

The script and workflow above use the documented `/rest/v1/blackholeddomain/` endpoint. If you want to build your own integration:

- `GET /rest/v1/blackholeddomain/` — list current entries (paginated; use `_limit=` and follow `meta.next`)
- `POST /rest/v1/blackholeddomain/` — add a domain. Body: `{"domain": "example.com"}`
- `GET /rest/v1/blackholeddomain/schema/` — column names and filter options for your specific AK version
- `GET /rest/v1/` — full list of supported REST resources

Authentication is HTTP Basic with your AK API username and password.

## Keeping it fresh

Once the initial bulk import is done, a quarterly refresh is usually enough. This repo rebuilds nightly, but AK's exclusion list doesn't need to stay that fresh — the rate of net-new bad domains is slow. Just re-run the workflow with **rebuild first** checked.
