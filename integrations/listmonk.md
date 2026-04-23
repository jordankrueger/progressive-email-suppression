# Listmonk

Listmonk's blocklist works at the individual email-address level. There's no native domain-level exclusion, and importantly Listmonk has no pre-creation webhook — its webhook/messenger support is outbound only. The cleanest pattern is an API-proxy: put your own signup endpoint in front, validate the domain there, and only call Listmonk's subscriber API on success.

## Pattern A: API proxy at signup

1. User submits your signup form, which POSTs to your own endpoint (n8n, serverless function, API route — anything you control)
2. Your endpoint extracts the email domain
3. Check against `combined.txt` (cache daily)
4. If match, reject with a friendly "please verify your email" response — do **not** call Listmonk
5. If no match, POST to `/api/subscribers` on your Listmonk instance

Listmonk's subscribers API accepts `status` values of `enabled` or `blocklisted` on create (POST), and `enabled`, `disabled`, or `blocklisted` on update (PATCH). These are distinct from subscription/opt-in state (`unconfirmed`, `confirmed`, `unsubscribed`) — don't confuse the two. For signups that pass your check, use `enabled`.

## Pattern B: SQL cleanup for existing records

For subscribers already in your Listmonk database:

```sql
-- Preview what would be affected — always run this first
SELECT id, email FROM subscribers
WHERE split_part(email, '@', 2) IN (
  'example-disposable.com',
  'example-typo.com'
  -- one domain per line from combined.txt
);

-- Flag them
UPDATE subscribers
SET status = 'blocklisted'
WHERE split_part(email, '@', 2) IN (...);
```

Listmonk requires Postgres, so `split_part` is always available. For a list this large (~66k domains), load `combined.txt` into a temp table and join rather than using a giant `IN` clause:

```sql
CREATE TEMP TABLE bad_domains (domain text PRIMARY KEY);
\copy bad_domains FROM 'combined.txt' WITH (FORMAT text);

-- Preview
SELECT s.id, s.email
FROM subscribers s
JOIN bad_domains b ON split_part(s.email, '@', 2) = b.domain;

-- Flag
UPDATE subscribers
SET status = 'blocklisted'
WHERE split_part(email, '@', 2) IN (SELECT domain FROM bad_domains);
```

(Remember to strip the `#`-prefixed comment lines from `combined.txt` before `\copy` if your file has the header.)
