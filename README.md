# Progressive email suppression list

A regularly-updated list of email domains your org should skip when sending: disposable addresses, spam traps, and typos of providers like Gmail and Yahoo that never deliver mail.

The current list is in [`data/combined.txt`](data/combined.txt), one domain per line, ready to load into most email platforms.

## Why this exists

If you run mailings for a progressive nonprofit, you know the problem. A signup form collects `jdoe@gmial.com`, `activist@aol.con`, `fan@yahooo.com`. These are typos and throwaways that never deliver, hurt your reputation with mail providers, and in the worst case hit spam traps that get your whole domain blocked. Most large orgs have built an internal exclude list over the years. Most small orgs haven't.

This repo pulls together the internal exclude lists progressive orgs have been quietly passing around for years, adds the big community-maintained disposable-email lists, and ships one clean deduped file you can load into almost any email platform.

It's purely defensive. The list exists so you can *not* send mail to these domains. Please don't use it for anything else.

## Who put this together

Curated by [Jordan Krueger](https://jordankrueger.com), an operations consultant for progressive nonprofits and advocacy orgs, running [CampaignHelp](https://campaign.help). Nearly two decades in the progressive movement, and one of the people who sketched out the "Blackhole Domains" feature in ActionKit back in the day.

The list draws on two progressive advocacy orgs' historical internal exclude lists (shared years ago through a community spreadsheet), plus the big community-maintained disposable-email repos. Per-source provenance and licensing is in [`sources.yaml`](sources.yaml).

## What's in the list

Most people just want `data/combined.txt`. The other three files are there for curiosity or specialized uses:

| File | Size | What it is |
|------|------|------------|
| `combined.txt` | ~66k | The one most people want. Everything below, deduped. |
| `historical-a.txt` | ~1.2k | Historical snapshot of an internal exclude list from a progressive advocacy org (circa 2019). |
| `historical-b.txt` | ~4.4k | Historical snapshot of an internal exclude list from a second progressive advocacy org, heavily typo-derived. |
| `typos.txt` | ~3.2k | Subset of combined that looks like typos of Gmail/Yahoo/Hotmail/iCloud/AOL/Outlook across TLDs. |

All files are plain text, one domain per line, with a comment header.

## Using the list

### Getting the current list

Point your tool at this URL to always get the latest build:

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

## How the list is built

A [GitHub Action](.github/workflows/rebuild.yml) runs `scripts/build.py` nightly. The script reads the local historical snapshots (`sources/historical-a.txt`, `sources/historical-b.txt`) and fetches upstream community lists, normalizes every entry (lowercase, strip, punycode for IDNs, validate), deduplicates, and writes the output files. If an upstream source is unavailable, the build soft-fails for that source and continues, so the list never goes dark because one upstream went down.

### Major-provider safety net

The build also strips a small allowlist of major email providers — Gmail, Outlook, Yahoo, iCloud, AOL, Proton, the big German/French/Russian/Chinese/Korean/Indian providers, plus Apple's `privaterelay.appleid.com` — out of every output file before writing. About 37 entries, listed in [`sources/allowlist.txt`](sources/allowlist.txt).

This is defensive. If an upstream community list ever got vandalized and shipped `gmail.com` as a "bad" domain, the build silently drops it (with a stderr warning), and a self-test fails the build outright if any allowlisted domain leaks into output. By the time you read `combined.txt`, the filter has already run — nothing to do on your end.

### Rebuilding locally

```bash
python3 scripts/build.py               # fetches upstream
python3 scripts/build.py --no-fetch    # uses local snapshots only
```

No dependencies — pure Python stdlib.

## Questions and known limits

- **This is not a threat feed.** For known malicious or phishing domains, use [URLhaus](https://urlhaus.abuse.ch/), [PhishTank](https://phishtank.org/), or [OpenPhish](https://openphish.com/). This list is about *mail you shouldn't bother sending*, not *domains that are attacking you*.
- **Expect false positives on the typo list.** The typo-detection regex is intentionally aggressive. If you see a legitimate domain flagged, open an issue.
- **Spamhaus DBL, SURBL, and URIBL are deliberately not included.** They're under commercial licenses we can't redistribute. If your sending platform offers them as a paid add-on, use them alongside this list.

## Licensing

**For campaigners, the short version:**

- **Using this list inside your own org?** Load `combined.txt` into your ESP, filter your signups, use it however helps your mission. Free, no attribution required.
- **Republishing the list?** (Mirroring the repo, posting `combined.txt` on your own site, bundling it into a product you ship.) Also fine. Just carry the [`LICENSES/`](LICENSES/) folder with it so the upstream authors stay credited.

That's it. No lawyers needed.

### The details

This repo is a mixed-license compilation:

- Everything this repo creates (build scripts, integration guides, docs, and the two progressive-advocacy-org historical snapshots contributed directly) is released under [CC0 1.0](LICENSE), public domain.
- `data/combined.txt` also folds in upstream community lists: MIT ([mailchecker](https://github.com/FGRibreau/mailchecker)), BSD 3-Clause ([fakefilter](https://github.com/7c/fakefilter)), and CC0 ([disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains)). Their license texts are in [`LICENSES/`](LICENSES/).

Individual domain strings are facts and aren't copyrightable on their own. But the *selection and arrangement* of a list can be, which is why we keep each upstream's license rather than relicensing everything as CC0. Full breakdown in [LICENSE](LICENSE); per-source provenance in [`sources.yaml`](sources.yaml).
