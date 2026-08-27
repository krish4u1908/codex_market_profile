# R6E1R Final Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Final status: **R6E1R_REPAIRED_HOST_VERIFICATION_PENDING**

The authoritative code/seal/test status is recorded in
`R6E1R_CURRENT_STATUS.md`.

## Outcome

The compound large-chunk failure is repaired on the sanitized v2 branch.
Diagnostic evidence proved that periodic refresh had irreversibly published an
absence-derived lifecycle expiration and linked material that later causal
Index evidence removed. The repair defers only those provisional immutable
publications while keeping current GUI/API state live. The harness now places
exact session-local refreshes and treats closure evolution as mandatory only
when final causal clocks prove that a refresh opportunity existed.

The v2 repair also retains a bounded, row-free ledger difference summary before
failed schedule snapshots are removed. It contains only counts, deterministic
analytical IDs, and hashes.

## Current verified scope

- Source repair and restart regressions: passed locally.
- Engine allowlist: 38/38 exact.
- Deployment package: 47/47 exact.
- Secret/path sanitation for the v2 handoff: passed.
- Historical large-only repaired run: passed on its exact historical commit.

## Not yet verified

- Exact v2 focused all-nine equivalence.
- Exact v2 six-session all-nine equivalence and frozen-reference comparison.
- Complete host regression, browser, user-systemd/bubblewrap, and file-open
  audit.
- Service installation, external health/readiness, restart recovery, public
  URL, and verification tag.

Therefore no deployment or verification tag is authorized from this report
alone.

## Git record

| Item | Value |
|---|---|
| Branch | `fix/r6e1r-final-live-shadow-v2` |
| Sanitized base | `c91df5a660195fa7b4595e0da02488c9db7cb8b1` |
| Projection/GUI hardening | `9669842054ec74b63b86576e4b5540b1a2c9dd63` |
| Ledger/harness repair | `a3c20bc2ea1a6251a84f41737d5b21413305bbd6` |
| Deployment digest/package repair | `bf182fa008a3b477c30a77b01f9a445ac2a8cc4a` |
| Tag | Not created |

The diagnostic and contaminated merge branches were not merged into v2.
Protected ports and collectors were not modified.
