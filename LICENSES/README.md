# Upstream licenses

This directory preserves the original license text from each upstream source
whose data is folded into `data/combined.txt`. See the root [LICENSE](../LICENSE)
file for the overall licensing posture.

| File | Upstream | License |
|------|----------|---------|
| [mailchecker.MIT.txt](mailchecker.MIT.txt) | [FGRibreau/mailchecker](https://github.com/FGRibreau/mailchecker) | MIT |
| [fakefilter.BSD-3-Clause.txt](fakefilter.BSD-3-Clause.txt) | [7c/fakefilter](https://github.com/7c/fakefilter) | BSD 3-Clause |
| [disposable-email-domains.CC0-1.0.txt](disposable-email-domains.CC0-1.0.txt) | [disposable-email-domains/disposable-email-domains](https://github.com/disposable-email-domains/disposable-email-domains) | CC0 1.0 |

## What this means in practice

A list of domains isn't copyrightable at the entry level — individual
facts. But the *selection and arrangement* of a list can carry a copyright
interest, and the upstream projects chose MIT / BSD / CC0 licenses for their
work. The safe posture: if you redistribute `combined.txt`, carry these
license files with it, or at least point readers to the upstream sources.

The two historical snapshots contributed directly to this repo are
released under CC0 by their contributors' attestation — see
[sources.yaml](../sources.yaml) for per-source provenance.
