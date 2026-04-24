# Action Network

Action Network has no native domain-level suppression feature. Subscription status is per-person only. Two patterns work:

## Pattern A: API proxy at signup (recommended)

**Important AN quirks that shape the integration:**

- **You cannot `POST` directly to `/api/v2/people/`.** The People collection is read-only for creates. The supported path for creating a person is the **Person Signup Helper** resource — each AN form has its own signup helper action URL. That means you can't generically "proxy the People API" — you proxy your *own* signup form, and from your proxy you POST to the specific signup helper endpoint for the AN form you're feeding.
- **Webhooks fire *after* creation** (up to a 5-minute delay per AN's docs) and cannot be used to gate signups. They're for notifications, not interception.

### Flow

1. User submits your signup form (hosted on your own site, posting to your endpoint — not directly to an AN hosted form)
2. Your endpoint extracts the email domain
3. Check against `combined.txt` (cache daily in your infra — Redis, a local file, or in-memory)
4. If match, reject with a friendly "please verify your email" message — do **not** call Action Network
5. If no match, POST to the Person Signup Helper action URL for your AN form

### n8n skeleton

- **Webhook** node — receives form submission from your site
- **HTTP Request** node — fetch `combined.txt` (cache it; don't re-fetch per signup)
- **Code** node — check submitted email's domain against the list
- **If** node — branch on match
- **HTTP Request** node — on the clean branch, POST to your AN form's Person Signup Helper URL

### Rate limits

Action Network rate-limits at **4 requests per second**. The docs recommend exponential backoff on 429 responses. A nightly sweep across tens of thousands of records will need to throttle; a live signup filter won't hit this in normal use.

## Pattern B: scheduled sweep (for existing records)

For people already in AN whose email is on the suppression list, run a periodic cleanup via the People API.

1. Fetch `combined.txt`
2. Page through the People API (GET is allowed; only POST to the collection is restricted)
3. For each person whose email domain matches, PUT their record with `email_addresses[0].status = "unsubscribed"`
4. Optionally add a tag for tracking

**Use the `self` URL from the GET response, not a URL you construct.** Every AN resource returns a `_links.self.href` that is the canonical URL for updates — follow the hypermedia rather than building `/people/{numeric_id}`. AN's internal identifiers are UUIDs surfaced in `identifiers`, and their URL structure is not guaranteed to be stable. Example:

```python
# GET a page of people, then for each match:
self_url = person["_links"]["self"]["href"]
requests.put(self_url, headers=..., json={
    "email_addresses": [{"address": person_email, "status": "unsubscribed"}]
})
```

Valid `status` values per AN's docs: `subscribed`, `unsubscribed`, `bouncing`, `previous bounce`, `spam complaint`, `previous spam complaint`. Only `subscribed` and `unsubscribed` can be set by API callers — the others are system-managed.

Throttle at 3-4 requests/sec and back off on 429s.

## A note on AN's hosted forms

If your signup forms live on `actionnetwork.org/forms/...` (AN-hosted, not your own site), you can't pre-filter at all. AN creates the record before any external system sees it, and the webhook that notifies you fires minutes later. In that case, stick with Pattern B and run the scheduled sweep.
