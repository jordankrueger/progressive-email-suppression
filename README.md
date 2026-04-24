# Progressive email suppression list

A consolidated, regularly-updated list of email domains that progressive organizations should exclude from their mailings — disposable email services, spam traps, and typos of major providers that never deliver.

**Latest build:** see [`data/combined.txt`](data/combined.txt) — one domain per line, ready to drop into most email platforms.

## Why this exists

If you run mailings for a progressive nonprofit, you already know the problem. A signup form collects `jdoe@gmial.com`, `activist@aol.con`, `fan@yahooo.com` — a slow drip of typos and throwaways that never deliver, bounce your sender reputation, or in the worst case hit spam traps that get your domain blocklisted. Most large orgs have built an internal exclude list over the years. Most small orgs haven't.

This repo is an attempt to fix that: one well-maintained public list, drawn from lists that progressive orgs have been quietly passing around for years, plus the big community-maintained disposable-email lists, all normalized and deduplicated.

It's purely defensive. The list exists so you can *not* send mail to these domains. Don't use it as a target list for anything else.

## Who put this together

Curated by [Jordan Krueger](https://jordankrueger.com) — operations consultant for progressive nonprofits and advocacy orgs, running [CampaignHelp](https://campaign.help). Nearly two decades in the progressive movement, and one of the people who sketched out the "Blackhole Domains" feature in ActionKit back in the day.

The list draws on two progressive advocacy orgs' historical internal exclude lists (shared years ago through a community spreadsheet), plus the big community-maintained disposable-email repos. Per-source provenance and licensing is in [`sources.yaml`](sources.yaml).

## What's in the list

Four files live in `data/`:

| File | Size | What it is |
|------|------|------------|
| `combined.txt` | ~66k | The one most people want. Everything below, deduped. |
| `historical-a.txt` | ~1.2k | Historical snapshot of an internal exclude list from a progressive advocacy org (circa 2019). |
| `historical-b.txt` | ~4.4k | Historical snapshot of an internal exclude list from a second progressive advocacy org, heavily typo-derived. |
| `typos.txt` | ~3.2k | Subset of combined that looks like typos of Gmail/Yahoo/Hotmail/iCloud/AOL/Outlook across TLDs. |

All files are one-domain-per-line plain text, with a comment header.

## Using the list

### Raw download

Pin your tool to the `main` branch raw URL and it'll always have the latest:

```
https://raw.githubusercontent.com/jordankrueger/progressive-email-suppression/main/data/combined.txt
```

### Integration guides

Detailed instructions for specific platforms live in [`integrations/`](integrations/):

- **ActionKit** — uses native "Blackhole Domains" feature
- **Action Network** — no native support; use an API proxy at signup or a scheduled sweep
- **EveryAction / NGP VAN** — no native support; use an API proxy at signup or a scheduled sweep
- **Listmonk** — API-proxy pattern at signup, or SQL cleanup
- **Sendy, Mailchimp, Klaviyo** — coming soon

## Contributing

If your org maintains an internal list you'd like to fold in, open an issue or PR. I'll merge it, normalize it, and credit your org in `sources.yaml`. Contributions should be:

- Plain text, one domain per line, lowercase
- Domains only (no local parts — `gmail.com`, not `abuse@gmail.com`)
- Defensive in nature (domains *you* exclude from sends) — not a target list

## Licensing

Mixed-license compilation. Short version:

- **This repository's original work** — build scripts, integration guides, docs, and the two historical snapshots contributed directly to this repo — is [CC0 1.0](LICENSE) (public domain, no attribution required).
- **`data/combined.txt`** also folds in upstream community lists licensed under MIT (mailchecker), BSD 3-Clause (fakefilter), and CC0 (disposable-email-domains). Their original license texts are preserved in [`LICENSES/`](LICENSES/).

If you redistribute `combined.txt`, carry the `LICENSES/` directory alongside it (or point consumers at the upstream sources in [`sources.yaml`](sources.yaml)).

Individual domain strings are facts and aren't copyrightable on their own, but the *selection and arrangement* of a list can be — which is why we preserve each upstream's license rather than relicensing under CC0.

## How the list is built

A [GitHub Action](.github/workflows/rebuild.yml) runs `scripts/build.py` nightly. The script reads the local historical snapshots (`sources/historical-a.txt`, `sources/historical-b.txt`) and fetches upstream community lists, normalizes every entry (lowercase, strip, punycode for IDNs, validate), deduplicates, and writes the output files. If an upstream source is unavailable, the build soft-fails for that source and continues — the list never goes dark because one upstream went down.

To rebuild locally:

```bash
python3 scripts/build.py               # fetches upstream
python3 scripts/build.py --no-fetch    # uses local snapshots only
```

No dependencies — pure Python stdlib.

## Questions and known limits

- **This is not a threat feed.** For known malicious or phishing domains, use [URLhaus](https://urlhaus.abuse.ch/), [PhishTank](https://phishtank.org/), or [OpenPhish](https://openphish.com/). This list is about *mail you shouldn't bother sending*, not *domains that are attacking you*.
- **Expect false positives on the typo list.** The typo-detection regex is intentionally aggressive. If you see a legitimate domain flagged, open an issue.
- **Spamhaus DBL, SURBL, and URIBL are deliberately not included** — those are commercial licenses we can't redistribute. If your sending platform offers them as a paid add-on, use them alongside this list.
