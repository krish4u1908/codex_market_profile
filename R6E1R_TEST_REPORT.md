# R6E1R Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT TARGETED AND FOCUSED GATES PASS; COMPLETE REGRESSION PENDING**

No failing or skipped test may be weakened, deselected, reclassified, or omitted to obtain acceptance.

## Recorded test history

| Invocation | Result | Standing |
|---|---|---|
| Repaired backend focused verification | 74 backend/harness plus 18 GUI/API passed | Valid historical targeted evidence |
| Callback/ingestion durability regression | 69 passed in 2.77s | Valid historical targeted evidence |
| Live API, shadow API, browser, preserved R6D GUI | 79 passed in 48.82s; zero browser console/page errors | Valid historical integration evidence |
| Environment-incomplete complete-suite attempt | 261 passed, 8 failed, 20 skipped | Invocation failure retained; not acceptance |
| Correctly provisioned complete suite | 289 passed, 0 failed, 0 skipped in 62.29s | Passed at that source checkpoint |
| Focused A/B v8 | Exit 0 | Rejected as final evidence after comparator audit |
| Focused one-record probe | 668 out-of-order refusals | Repair-triggering diagnostic failure |
| Repaired-engine current targeted gate | 216/216 passed: 120 callback/runner, 28 equivalence-harness, 68 engine/API/runtime/cross-layer | Current accepted targeted evidence |
| Historical-availability reference comparator | 29/29 targeted tests; separate preserved-v3 check matched A and B 24/24 rows each to Reference C with zero remainder | Current accepted targeted evidence |
| R6D-parity engine/GUI/API/browser gate | 135/135 passed at pushed GUI milestone `5efe70e`; three current fixture screenshots visually inspected; no tracked GUI/browser bytes changed afterward | Accepted targeted evidence |
| Focused all-nine v12 | 21/21 components, 8/8 ledgers, 9/9 schedules, 9/9 invariants, 72/72 checkpoint rows, 2/2 recovery probes | Current accepted focused evidence |

Source, test, GUI, and harness files changed after several results above. Final counts must therefore come from a new current-source run.

## Required adversarial/regression coverage

| Case | Final test/result |
|---|---|
| Partial final JSONL line deferral/retry | PASS — targeted suite and focused inside-line schedule |
| Malformed complete record refusal | PASS — repaired-engine targeted suite |
| File truncation/replacement/same-inode rewrite | PASS — quarantine/integrity targeted suite |
| Hourly rotation | PASS — focused v12 schedule |
| Duplicate replay | PASS — targeted exactly-once suite |
| Callback exception before acknowledgement | PASS — targeted replayability suite |
| Restart after ingestion before analytical flush | PASS — targeted suite and focused recovery probes |
| Restart after each material ledger append | PASS — seven nonempty focused material ledgers exactly once |
| Out-of-order visibility/candidate barrier | PASS — targeted barrier suite and focused zero refusals |
| Exact-second and fractional timestamps | PASS — strict-parser targeted fixtures |
| Naive/future timestamp refusal | PASS — targeted refusal fixtures |
| Stale Index/Futures suspension | PASS — targeted engine/API fixtures |
| Missing CE/PE isolation | PASS — targeted engine/API fixtures |
| Missing fixed horizons with Intraday | PASS — targeted GUI/API and Intraday-only fixture |
| Current-session fixed-profile exclusion | PASS — targeted fixed-context suite; final six confirmation pending |
| August 17 rejection | PASS — targeted/preload validation; final six confirmation pending |
| Toggle persistence | PASS — 135/135 parity suite at unchanged GUI/browser bytes |
| Independent Index/Futures sorting | PASS — 135/135 parity suite at unchanged GUI/browser bytes |
| Price/Basis clock alignment | PASS — focused causality matrix and targeted fixtures |
| No browser-side analytical recomputation | PASS — 135/135 parity suite at unchanged GUI/browser bytes |
| No secrets/raw records in payloads/logs | PASS — 135/135 parity suite at unchanged GUI/browser bytes |
| Replay retention and finalized bucket compaction | PASS — repaired-engine targeted suite |

All rows above are accepted targeted/focused evidence. The complete current-source regression rerun remains `PENDING_FINAL_EVIDENCE`.

## Final test summary

| Suite | Passed | Failed | Skipped | Elapsed | Peak RSS | Command/evidence |
|---|---:|---:|---:|---:|---:|---|
| Callback/runner targeted portion | 120 | 0 | Not separately reported | Recorded within 216/216 gate | Not separately recorded | Exact final command rerun `PENDING_FINAL_EVIDENCE` |
| Equivalence harness targeted | 29 | 0 | Not separately reported | Current comparator gate recorded | Not separately recorded | Historical-availability comparator at pushed head `89f1350` |
| Engine/API/runtime/cross-layer targeted portion | 68 | 0 | Not separately reported | Recorded within 216/216 gate | Not separately recorded | Exact final command rerun `PENDING_FINAL_EVIDENCE` |
| R6D-parity engine/GUI/API/browser targeted | 135 | 0 | Not separately reported | GUI milestone gate recorded | Not separately recorded | Three tracked fixtures visually inspected; GUI/browser bytes unchanged afterward |
| Deployment package plus live GUI/API | 98 | 0 | 0 | 19.50 s | 135,972 KiB | Current 34-file package, systemd/bubblewrap, readiness, redaction, API contract |
| Browser acceptance | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Complete repository regression | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| `git diff --check` | `PENDING_FINAL_EVIDENCE` | — | — | — | — | `PENDING_FINAL_EVIDENCE` |
| Credential scan | `PENDING_FINAL_EVIDENCE` | — | — | — | — | `PENDING_FINAL_EVIDENCE` |
| Oversized-file scan | `PENDING_FINAL_EVIDENCE` | — | — | — | — | `PENDING_FINAL_EVIDENCE` |

Final aggregate: `PENDING_FINAL_EVIDENCE`.
