---
name: False positive — legit domain flagged
about: A legitimate email domain ended up on the suppression list and shouldn't have
title: "[false positive] <domain>"
labels: ["false-positive"]
---

**Domain in question:**
<!-- e.g. yourorg.org -->

**Which file does it appear in?**
<!-- combined.txt / historical-a.txt / historical-b.txt / typos.txt -->

**Why is this a real domain?**
<!-- e.g. it's our org's mail domain, it's a working ESP, etc. -->

**If you know which upstream source it came from, paste a clue here:**
<!-- e.g. "I see it in mailchecker's list.txt", or leave blank if unsure -->

---

Note: the [allowlist](../../sources/allowlist.txt) already protects ~37 major providers (Gmail, Outlook, Yahoo, iCloud, Proton, etc.) from ever being flagged — so that class of false positive is already handled. This template is for everything else.
