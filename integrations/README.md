# Integration guides

How to load the suppression list into the ESPs and campaign tools most progressive orgs use.

| Platform | Native support | Guide |
|---|---|---|
| ActionKit | Yes — "Blackhole Domains" feature | [actionkit.md](actionkit.md) |
| Action Network | No — API-proxy pattern at signup, or scheduled sweep | [action-network.md](action-network.md) |
| EveryAction / NGP VAN | No — API-proxy pattern at signup, or scheduled sweep | [everyaction.md](everyaction.md) |
| Listmonk | Partial — per-email blocklist; domain filter via API proxy | [listmonk.md](listmonk.md) |
| Sendy | Via custom SQL or API proxy | _coming soon_ |
| Mailchimp | No — API proxy or compliance block | _coming soon_ |
| Klaviyo | No — API proxy or suppression profile | _coming soon_ |

## The raw URL

Every integration below ultimately just needs this:

```
https://raw.githubusercontent.com/jordankrueger/progressive-email-suppression/main/data/combined.txt
```

One domain per line, updated nightly. Any fetch-and-filter pattern you already use can pull from that.
