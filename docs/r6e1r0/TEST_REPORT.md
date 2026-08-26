# R6E1R0 Test Report

| Gate | Result |
|---|---|
| Sample completeness/provenance | PASS — 46,550 identities, 8 source hashes |
| Classification and field preservation | PASS |
| Poll callback and canonical stages | PASS |
| Batch/eight-poll/restart equivalence | PASS — identical semantic hash |
| Retry/restart idempotency | PASS — zero duplicate analytical IDs |
| Partial line, duplicate, out-of-order, stale handling | PASS |
| Truncation/replacement recovery | PASS |
| Future joins/backdating | PASS — zero/zero |
| Intraday-only degradation | PASS |
| Focused R6E suite | PASS — 64 tests |
| Complete suite | PASS — 190 passed, 20 skipped |
| `git diff --check` | PASS |

Skipped tests were fixture-gated historical cases, not failures.
