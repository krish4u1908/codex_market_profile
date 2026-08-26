# R6E1R Artifact Equivalence Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED V12 VERIFIED; FINAL SIX-SESSION EVIDENCE PENDING**

Incremental A and clean chronological B must consume the same selected raw bytes from independent state roots. Comparison is an exact canonical multiset/identity comparison; floating tolerance, count-only equivalence, and inherited R6C2R output are insufficient.

## Accepted focused evidence

The accepted August 19 focused v12 run passed all 21 component comparisons and all eight append-only ledger comparisons. It reported zero A-only rows, B-only rows, field mismatches, unexplained remainders, identity/content differences, and schedule-dependent semantic differences across all nine schedules. This establishes the focused callback/comparator path; it does not populate the six-session final-result column below.

- Component matrix SHA-256: `7f66920bf67df12767b2b93e5115cd357bc6f12df37c35e799a62ae6b0e8c742`
- Ledger matrix SHA-256: `8d2c8706637a15ba12d230307e09ec1138ab134f4dc02ee624f25bc82fa22da6`
- Equivalence summary SHA-256: `19b6c15f426b925fa6ec018d65477f4364242d65cfaaa5425423098d3861de15`
- Evidence root: `/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_evidence/focused_nine_final_v12`

The historical-availability reference comparator added at pushed commit `89f135064417ba537dc302027442a110477b5d03` passed 29/29 targeted harness tests. A separate check over preserved v3 material matched incremental A and batch B 24/24 rows each against Reference C with zero remainder. Final Reference-C status remains pending the fresh six-session run.

| Artifact | Incremental A publication | Independent B authority | Frozen count when applicable | Required final result |
|---|---|---|---:|---|
| Synchronized basis | Orchestrator session output | Clean raw `causal_basis` | — | `PENDING_FINAL_EVIDENCE` |
| BN-reference inventory | Live inventory output | Clean inventory engine | 255 | `PENDING_FINAL_EVIDENCE` |
| Divergence episodes | Live frozen detector | Clean stack native episodes | 65 | `PENDING_FINAL_EVIDENCE` |
| GREEN episodes | Episode colour projection | Clean episode rows | 41 | `PENDING_FINAL_EVIDENCE` |
| RED episodes | Episode colour projection | Clean episode rows | 24 | `PENDING_FINAL_EVIDENCE` |
| Dependency groups | Live dependency output | Clean stack native groups | 65 | `PENDING_FINAL_EVIDENCE` |
| Dependent retriggers | Dependency classification | Clean group projection | 14 | `PENDING_FINAL_EVIDENCE` |
| Lifecycle transitions | Live lifecycle output | Clean stack lifecycle | 14,201 | `PENDING_FINAL_EVIDENCE` |
| Dense resolution | Live resolution output | Clean stack resolution | 164,668 | `PENDING_FINAL_EVIDENCE` |
| Response observations | Live response output | Clean stack responses | 65 | `PENDING_FINAL_EVIDENCE` |
| Dense participation | Live participation view | Clean batch dense view | 69,225 | `PENDING_FINAL_EVIDENCE` |
| Participation transitions | Live transition view | Clean batch transition ledger | 32,068 | `PENDING_FINAL_EVIDENCE` |
| Participation summaries | Live summary view | Clean batch summary | 65 | `PENDING_FINAL_EVIDENCE` |
| Compatibility snapshots | Live compatibility view | Clean legacy view | 65 | `PENDING_FINAL_EVIDENCE` |
| Cross-layer transitions | Live cross-layer output | Clean layer builder plus raw-only fallback where required | 60,659 | `PENDING_FINAL_EVIDENCE` |
| Intraday fallback inventory | Live partial-context rows | Independently rebuilt raw-byte fallback | Context-dependent | `PENDING_FINAL_EVIDENCE` |
| Intraday fallback cross-layer | Live partial-context transitions | Independently rebuilt fallback transitions | Context-dependent | `PENDING_FINAL_EVIDENCE` |
| Availability states | Live sealed availability | Independent raw-clock/context projection | Context-dependent | `PENDING_FINAL_EVIDENCE` |
| GUI-visible state | Live GUI payload | Independent clean-B payload projection | Six sessions | `PENDING_FINAL_EVIDENCE` |
| Divergence ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | 65 expected episode publications | `PENDING_FINAL_EVIDENCE` |
| Dependency ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | 65 expected group publications | `PENDING_FINAL_EVIDENCE` |
| Lifecycle ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | 14,201 expected publications | `PENDING_FINAL_EVIDENCE` |
| Inventory ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | Context-dependent | `PENDING_FINAL_EVIDENCE` |
| Participation ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | 32,068 expected publications | `PENDING_FINAL_EVIDENCE` |
| Cross-layer ledger IDs/content | Append-only ledger | Independently derived deterministic IDs | 60,659 expected publications | `PENDING_FINAL_EVIDENCE` |
| Availability/stale ledger IDs | Append-only ledger | Independent final-state clock/identity projection | Context-dependent | `PENDING_FINAL_EVIDENCE` |

## Global invariant gate

| Measure | Required | Final |
|---|---:|---|
| A-only canonical rows | 0 | `PENDING_FINAL_EVIDENCE` |
| B-only canonical rows | 0 | `PENDING_FINAL_EVIDENCE` |
| Field mismatches | 0 | `PENDING_FINAL_EVIDENCE` |
| Identity/content differences | 0 | `PENDING_FINAL_EVIDENCE` |
| Reference remainders | 0 | `PENDING_FINAL_EVIDENCE` |
| Schedule-dependent state hashes | 0 | `PENDING_FINAL_EVIDENCE` |

The final matrix must link each row to the sealed comparison CSV/JSON and its SHA-256.
