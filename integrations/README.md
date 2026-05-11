# Integration guides

How to load the suppression list into the ESPs and campaign tools most progressive orgs use.

| Platform | Native support | Self-serve workflow | Guide |
|---|---|---|---|
| ActionKit | Yes — "Blackhole Domains" feature | ✓ [self-serve import](actionkit-self-serve.md) | [actionkit.md](actionkit.md) |
| Action Network | No — tag-based pattern, or API proxy at signup | ✓ [self-serve sweep](action-network-self-serve.md) | [action-network.md](action-network.md) |
| EveryAction / NGP VAN | No — manual process via NGP support, custom API recipe, or export-and-reimport | — | [everyaction.md](everyaction.md) |
| Listmonk | Partial — per-email blocklist; domain filter via API proxy | — | [listmonk.md](listmonk.md) |
| Sendy | Via custom SQL or API proxy | — | _coming soon_ |
| Mailchimp | No — API proxy or compliance block | — | _coming soon_ |
| Klaviyo | No — API proxy or suppression profile | — | _coming soon_ |

## The raw URL

Every integration below ultimately just needs this:

```
https://raw.githubusercontent.com/jordankrueger/progressive-email-suppression/main/data/combined.txt
```

One domain per line, updated nightly. Any fetch-and-filter pattern you already use can pull from that.
