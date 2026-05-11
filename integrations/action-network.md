# Action Network

Action Network has no native domain-level suppression feature. Subscription status is per-person only, so applying the suppression list takes one of two patterns. Pick based on the problem you're solving.

| Problem | Pattern | What you do |
|---|---|---|
| **You already have a bunch of bad records in your AN database** and want to clean them up | **Pattern B**: scheduled sweep | Tag matching people; use the tag to exclude them from mailings. **Recommended.** Self-serve: see [action-network-self-serve.md](action-network-self-serve.md). |
| **You want to prevent new bad signups going forward** | **Pattern A**: API proxy at signup | Put your own endpoint in front of your signup form; reject signups that match the list before they reach AN |

Most orgs need Pattern B first (cleanup), then optionally adopt Pattern A (prevention) later. The two are independent.

---

## Pattern B: scheduled sweep (recommended path)

For people already in AN whose primary email is on the suppression list, our self-serve workflow tags them with a dated tag (`psup_YYYY-MM-DD`). The admin then uses the tag to exclude tagged people from mailings via AN's standard mailing filters.

We deliberately do NOT change subscription status during the sweep. Tagging is reversible (the rollback workflow removes every tagging it applied) and keeps you in control of when and how the suppression actually affects sends. Subscription-state changes are not.

**To run it:** see [action-network-self-serve.md](action-network-self-serve.md). You fork the repo, add one secret (`AN_API_KEY`), and click a button.

If you'd rather run it manually:

```python
# Each match comes from paginating the People API. Use the self URL.
person_self_url = person["_links"]["self"]["href"]
# To tag: POST to the tag's taggings endpoint with the person's self URL
requests.post(
    f"https://actionnetwork.org/api/v2/tags/{tag_uuid}/taggings/",
    headers={"OSDI-API-Token": api_key},
    json={"_links": {"osdi:person": {"href": person_self_url}}}
)
```

**Important constraints:**

- **People collection has no server-side filtering.** No `?filter=email_domain` parameter exists. You must paginate through every person and filter client-side.
- **Page size is hard-capped at 25.** A 100k-person AN database needs ~4,000 GET requests just to scan, ignoring the rate limit.
- **Rate limit:** community-known as 4 req/sec. We cap our scripts at 3.5 QPS to leave headroom. AN's official docs don't document a rate limit, but exceeding ~4/sec returns 429s in practice.
- **Tag dedup is built into the API.** POSTing a tag with an existing name returns the existing tag's resource. No "find or create" pre-check needed.
- **Tag deletion is not allowed via API.** After rollback, the empty tag stays in your group. Hide it from the AN UI's tags list manually if it's in the way.

---

## Pattern A: API proxy at signup

**When to use this:** you're building a new signup form, or you control your existing form's submission endpoint, and you want to filter at signup-time so bad records never enter AN in the first place.

**Important AN quirks that shape the integration:**

- **You cannot `POST` directly to `/api/v2/people/`.** The People collection is read-only for creates. The supported path for creating a person is the **Person Signup Helper** resource. Each AN form has its own signup helper action URL, which means you can't generically "proxy the People API". You proxy your *own* signup form, and from your proxy you POST to the specific signup helper endpoint for the AN form you're feeding.
- **Webhooks fire *after* creation** (up to a 5-minute delay per AN's docs) and cannot be used to gate signups. They're for notifications, not interception.

### Flow

1. User submits your signup form (hosted on your own site, posting to your endpoint, not directly to an AN hosted form).
2. Your endpoint extracts the email domain.
3. Check against `combined.txt` (cache daily in your infra: Redis, a local file, or in-memory).
4. If match, reject with a friendly "please verify your email" message. Do **not** call Action Network.
5. If no match, POST to the Person Signup Helper action URL for your AN form.

### n8n skeleton

- **Webhook** node: receives form submission from your site
- **HTTP Request** node: fetch `combined.txt` (cache it; don't re-fetch per signup)
- **Code** node: check submitted email's domain against the list
- **If** node: branch on match
- **HTTP Request** node: on the clean branch, POST to your AN form's Person Signup Helper URL

### Rate limits at signup

Live signup filtering won't hit AN's rate limits in normal use, since you only POST when a signup passes the domain check. Backed off properly on 429s, AN's API can handle bursts during traffic spikes.

---

## A note on AN's hosted forms

If your signup forms live on `actionnetwork.org/forms/...` (AN-hosted, not your own site), Pattern A isn't possible. AN creates the record before any external system sees it, and the webhook that notifies you fires minutes later. In that case, run Pattern B periodically to clean up bad signups after the fact.
