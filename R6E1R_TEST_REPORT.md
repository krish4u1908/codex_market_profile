# R6E1R Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 LOCAL REPAIR TESTS COMPLETE — HOST ACCEPTANCE PENDING**

The authoritative status and sealed identities are in
`R6E1R_CURRENT_STATUS.md`.

## Current v2 results

| Suite | Passed | Failed | Skipped | Standing |
|---|---:|---:|---:|---|
| Orchestrator module | 114 | 0 | 0 | PASS |
| Ingestion + orchestrator + equivalence harness | 278 | 3 | 0 | NOT ACCEPTED locally; the three clean-B file-open tests require permitted `ptrace`/`strace` |
| New provisional-publication, restart, refresh, tamper, and bounded-diagnostic selections | 7 | 0 | 0 | PASS |
| Projection reuse, gateway limit, and GUI parity selections | 27 | 0 | 0 | PASS |
| Engine/package manifest selections | 3 | 0 | 0 | PASS |

The three failures were retained as failures. No test was weakened, skipped,
deselected, or reclassified to claim acceptance.

The current v2 source was not run through the complete host repository suite,
browser/geometry suite, user-systemd/bubblewrap boundary, focused all-nine
equivalence, or full six-session all-nine equivalence. Those gates are
mandatory before deployment.

## Regression coverage added

- Provisional expiration is absent from immutable ledgers during periodic
  refresh.
- Later standalone Index evidence can remove the provisional lifecycle and its
  linked participation/cross-layer rows without leaving ghosts.
- Restart before that later response matches one-shot artifacts and all eight
  material ledgers.
- Restart before seal publishes surviving deferred rows exactly once.
- Session-local refresh targets are exact, distinct, dirty, recomputed, and
  causally advancing.
- Closure opportunities, no-opportunity cases, finalization-only changes, and
  tampered trace fields are distinguished.
- Failed schedules retain bounded analytical IDs and content hashes without raw
- Failed schedules retain bounded analytical IDs and content hashes without raw
  rows or source paths.
