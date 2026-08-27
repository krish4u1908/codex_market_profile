# R6E1R Causality Audit

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

## Frozen clock contract

| Analytical fact | Evidence clock |
|---|---|
| Divergence confirmation | Frozen synchronized Index/Futures clock |
| Index response | Standalone raw Index receipt strictly after confirmation |
| Basis resolution | Valid synchronized Index/Futures clock |
| Stalled extreme | Timezone-aware wall-clock duration from causal evidence clocks |
| Participation | Constituent Futures/CE/PE receipt clocks |
| Availability | Evaluation reference clock with separate latest-valid receipt per instrument |
| Snapshot/display | Presentation only; never replaces or backdates evidence |

Every parsed timestamp must be timezone-aware and normalized to `Asia/Kolkata` without rounding. Mixed exact-second and fractional forms use the verified strict parser. Naive, invalid, and future live receipt timestamps are refused.

## Synchronization contract

- Index and Futures are independently sorted by receipt/source coordinates.
- Each Futures observation may match only the latest Index receipt at or before it.
- Valid match age is inclusive from 0 through exactly 2,000 ms.
- A negative age is a future join and is prohibited.
- Stale Index or Futures inputs suspend divergence as `STALE_DATA` while the last valid chart may remain visible with a warning.

The frozen BN-reference inventory contract is separate: it permits a backward Index as-of match through 5,000 ms. A targeted real 3-4 second fixture verifies that inventory remains eligible while synchronized basis and divergence remain unmatched beyond exactly 2,000 ms.

## Candidate-selection causality

The one-record diagnostic probe exposed 668 out-of-order refusals: a raw Futures candidate was durably deferred pending canonical depth selection while later observations advanced the acknowledged high-water. The repair makes the earliest unresolved candidate receipt a strict causal publication barrier, including equal-clock rows, until repository-owned selection releases or rejects candidates. Restart coverage retains the barrier in durable state.

Current local adversarial and functional tests verify the repair logic. Focused
v12 is historical because the engine identity changed; fresh current-commit
focused and six-session all-nine causality measurements remain pending.

Full-six v6 exposed a separate test-orchestration visibility defect, not a production-clock defect. Its one-record scheduler supplied only the newly changed explicit path, so an already-visible raw file held behind its checkpoint could be omitted while OI advanced the high-water. The repaired harness retains only paths with staged bytes beyond their durable checkpoints and includes them on every nonempty causal-prefix poll; intentional empty polls remain empty. The regression uses byte-exact blank coordinate rows, a 512-byte read bound, and an OI hourly rotation to prove that the old path generated one `OUT_OF_ORDER_RECEIPT` plus one `OUT_OF_ORDER_ANALYTICAL_RECEIPT`, while the repair produces zero, survives restart, drains every checkpoint remainder, and matches the original-chunk snapshot and ledgers exactly. Production discovery, frozen clocks, and refusal semantics were not changed.

## Evidence and publication durability

- Evidence is never backdated to calculation, snapshot, or display time.
- A source observation is acknowledged only after callback processing and durable analytical staging succeed.
- An exception before acknowledgement leaves durable replay state.
- Material publication uses deterministic IDs and append-only ledger deduplication.
- An exception after a durable append reconciles the identity before retry.
- Current-session raw bytes are excluded from fixed 1D/2D/3D context.

## Historical focused-v12 measured invariants

| Invariant | Required | Final value |
|---|---:|---|
| Future joins | 0 | 0 — PASS |
| Synchronization tolerance violations | 0 | 0 — PASS |
| Timestamp backdating | 0 | 0 — PASS |
| Duplicate analytical IDs | 0 | 0 — PASS |
| Valid timestamps converted to `NaT` | 0 | 0 — PASS |
| Analytical refusals | 0 | 0 — PASS |
| GUI clock-contract violations | 0 | 0 — PASS |
| GUI display-contract violations | 0 | 0 — PASS |
| GUI path-clock violations | 0 | 0 — PASS |

Focused causality matrix SHA-256: `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2`.

## Pending six-session-only invariants

| Invariant | Required | Final value |
|---|---:|---|
| Analytical refusals on accepted six-session run | 0 | `PENDING_FINAL_EVIDENCE` |
| August 17 forced acceptance | 0 | `PENDING_FINAL_EVIDENCE` |
| Current-session fixed-profile inclusion | 0 | `PENDING_FINAL_EVIDENCE` |

Fresh six-session causality matrix and SHA-256: `PENDING_FINAL_EVIDENCE`.

Focused v8 remains rejected. Focused v12 passed its own source identity but
cannot substitute for any current-commit focused or six-session value.

## Adversarial evidence checklist

| Case | Local/historical evidence; final Hostinger gate pending |
|---|---|
| Partial final line deferral/retry | PASS — targeted suite and focused inside-line schedule |
| Malformed complete record hard refusal | PASS — targeted repaired-engine suite |
| Truncation and same-inode replacement | PASS — targeted replacement/quarantine/integrity suite |
| Duplicate replay | PASS — targeted exactly-once suite |
| Callback exception before acknowledgement | PASS — targeted replayability suite |
| Failure after durable append for each material ledger | PASS — seven nonempty focused ledger boundaries exactly once |
| Restart after ingestion before analytical flush | PASS — targeted and focused recovery probes |
| Out-of-order visibility, candidate barrier, and checkpoint-lagging peers | PASS — targeted barrier fixtures, semantic hourly-peer regression, and focused zero refusals |
| Exact-second/fractional timestamps | PASS — strict-parser targeted fixtures |
| Naive/future timestamp refusal | PASS — targeted refusal fixtures |
| Stale market suspension | PASS — targeted engine/API fixtures |
| Missing options/fixed context isolation | PASS — targeted engine/API fixtures |

The pre-final-repair local R6E functional selection passed 416/416, including the
adversarial code paths above. Hostinger must repeat them with ptrace/open audit
available and bind the results to the pushed commit.
