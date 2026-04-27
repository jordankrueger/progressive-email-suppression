# Security policy

If you find a security issue with the build script, the AK import workflow, or anything else in this repo, please email **jordan@campaign.help** rather than opening a public issue.

Examples of things worth reporting privately:

- A way to inject domains into the output through a malicious upstream PR
- A bug in `scripts/import_to_actionkit.py` that could expose credentials in workflow logs, commits, or error output
- A vulnerability in a dependency (none expected — the build script and import script use Python stdlib only — but worth reporting if found)
- Anything that could let an attacker pollute or poison the suppression list as it propagates downstream

For everything else (false positives, missing domains, integration questions, feature requests), please open a public [issue](https://github.com/jordankrueger/progressive-email-suppression/issues) or [discussion](https://github.com/jordankrueger/progressive-email-suppression/discussions).

I aim to respond to security reports within a few business days.
