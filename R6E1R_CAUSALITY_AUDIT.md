# R6E1R Causality Audit

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

## Terminal disposition

The v9 run was externally stopped before all-nine publication. The operator
stop applied its runtime mask at `20:39:00.999`; systemd recorded a
client-requested `SIGINT` at `20:39:01` and client-requested `SIGTERM` at
`20:39:06`. There was no OOM kill, swap use was zero, and the observed peak was
14.5 GiB. The v9 evidence, work, and control roots were externally deleted
after the operator stop. A post-stop
search found zero surviving alternate-schedule bundles, no bundle marker, and
no terminal all-gates summary.

The v9 causality and reference hashes retained below are independently
observed and pushed baseline facts only. They are not surviving final all-nine
artifacts and cannot support terminal schedule-invariance or six-session
equivalence claims. A fresh run requires an explicit uninterrupted root-agreed
window and must not evade an active root operator. Deployment and the verified
tag were not performed.

Evidence lineage:

- Branch snapshot at this refresh: `612d3ebb8fad818386f4b2a6a9b6f519ac837ada`.
- Repair commit: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.
- Fresh focused summary SHA-256: `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
- Fresh v9 causality-matrix SHA-256: `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2`.

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

Every parsed timestamp must be timezone-aware and normalized to
`Asia/Kolkata` without rounding. Mixed exact-second and fractional forms use the
verified strict parser. Naive, invalid, and future live receipt timestamps are
refused.

## Synchronization contract

- Index and Futures are independently sorted by receipt/source coordinates.
- Each Futures observation may match only the latest Index receipt at or before
  it.
- Valid synchronized-basis match age is inclusive from 0 through exactly 2,000
  ms.
- A negative age is a future join and is prohibited.
- Stale Index or Futures input suspends divergence as `STALE_DATA`; the last
  valid chart may remain visible with a warning.

The frozen BN-reference inventory contract is separate: it permits a backward
Index as-of match through 5,000 ms. The targeted 3-4 second fixture continues to
prove that inventory can remain eligible while synchronized basis and
divergence are unmatched beyond exactly 2,000 ms.

### Empty-Index aware-clock behavior

The no-eligible-Index path previously assigned a generic timezone-naive
`pd.NaT`, which could create a pandas datetime-dtype failure before the canonical
unmatched result was represented. Commit `e1d67c5` now assigns an all-missing
`matched_price_timestamp` Series using the timezone-aware dtype of
`availability_timestamp`. A naive availability clock is explicitly refused.

The repaired path still produces no match, no underlying price, no join age,
and `future_join == False`. It does not invent or backdate evidence. The
backward direction, inclusive tolerances, independent path sorting,
future-join prohibition, and all frozen clocks are unchanged.

## Candidate-selection causality

The one-record historical diagnostic exposed a durable raw Futures candidate
held for canonical depth selection while later observations could advance the
acknowledged high-water. The repaired causal publication barrier holds equal or
later receipts until repository-owned selection releases or rejects the
candidate, including after restart.

A separate historical v6 harness defect supplied only the newly changed path to
the one-record scheduler, allowing an already-visible checkpoint-lagging peer to
be omitted. The repaired harness retains any path with staged bytes beyond its
durable checkpoint on each nonempty causal-prefix poll; intentional empty polls
remain empty. Production discovery, frozen clocks, and refusal semantics were
not changed.

The clean post-repair focused run exercised all nine focused schedules with
analytical refusals zero. The complete post-repair repository regression passed
660/660 with no failure or skip.

## Evidence and publication durability

- Evidence is never backdated to calculation, snapshot, or display time.
- A source observation is acknowledged only after callback processing and
  durable analytical staging succeed.
- An exception before acknowledgement leaves replayable durable state.
- Material publication uses deterministic IDs and append-only ledger
  deduplication.
- An exception after a durable append reconciles the identity before retry.
- Current-session raw bytes are excluded from fixed 1D/2D/3D context.

## Fresh focused measured invariants

| Invariant | Required | Focused result |
|---|---:|---:|
| Future joins | 0 | 0 — PASS |
| Synchronization tolerance violations | 0 | 0 — PASS |
| Timestamp backdating | 0 | 0 — PASS |
| Duplicate analytical IDs | 0 | 0 — PASS |
| Valid timestamps converted to `NaT` | 0 | 0 — PASS |
| Analytical refusals | 0 | 0 — PASS |
| GUI clock-contract violations | 0 | 0 — PASS |
| GUI display-contract violations | 0 | 0 — PASS |
| GUI path-clock violations | 0 | 0 — PASS |

The fresh focused run passed 9/9 causality groups, 9/9 focused schedules,
72/72 checkpoint rows, 2/2 recovery probes, and 8/8 source rows. This closes
the focused gate only; it is not a substitute for all six-session schedules.

## Observed v9 six-session baseline/reference invariants

Incremental A used original source chunks through the production checkpoint
path. Clean B was an independently clean chronological batch over the same
selected raw bytes. Before deletion, both baselines were observed to pass:

| Invariant | Required | Incremental A | Clean B | Result |
|---|---:|---:|---:|---|
| Future joins | 0 | 0 | 0 | PASS |
| Synchronization tolerance violations | 0 | 0 | 0 | PASS |
| Timestamp backdating | 0 | 0 | 0 | PASS |
| Duplicate analytical IDs | 0 | 0 | 0 | PASS |
| Valid timestamps becoming `NaT` | 0 | 0 | 0 | PASS |
| Analytical refusals | 0 | 0 | 0 | PASS |
| GUI clock-contract violations | 0 | 0 | 0 | PASS |
| GUI display-contract violations | 0 | 0 | 0 | PASS |
| GUI path-clock violations | 0 | 0 | 0 | PASS |

The v9 projection contains six evaluation sessions and eight causal source
sessions, 141 authoritative source files, 139 projection files, and 746,890
byte-exact selected records. Malformed candidate records and source mutations
are zero. Its explicit August 17 policy is
`PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`. Projection-manifest
and source-comparison SHA-256 values are
`4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426`
and `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56`.

The v9 analytical components matched A to B 21/21, append-only ledgers
matched 8/8, the R6C2R analytical reference matched 30/30, and the R6D GUI
reference matched 180/180 with no unexplained remainder. These retained
baseline/reference facts show the repaired empty-Index representation did not
alter canonical analytical or display semantics.

## Blocked terminal six-session invariants

| Requirement | Current value |
|---|---|
| One-record-per-increment causality result | `BLOCKED_NO_SURVIVING_BUNDLE` |
| Deterministic-variable-chunk causality result | `BLOCKED_NO_SURVIVING_BUNDLE` |
| Inside-line and empty/repeated-poll causality results | `BLOCKED_NO_SURVIVING_BUNDLE` |
| Multiple-checkpoint and transition-boundary restart invariance | `BLOCKED_NO_SURVIVING_BUNDLE` |
| Hourly-rotation and large-chunk invariance | `BLOCKED_NO_SURVIVING_BUNDLE` |
| Terminal schedule/checkpoint/storage summary | `BLOCKED_NO_TERMINAL_SUMMARY` |

No partial schedule count is promoted. The retained original-chunk A/B and
reference observations do not, by themselves, establish all-nine full-six
schedule equivalence.

## Adversarial evidence checklist

| Case | Current evidence; remaining boundary |
|---|---|
| Partial final line deferral/retry | Regression/focused PASS; full-six inside-line proof blocked |
| Malformed complete record refusal | Regression PASS; v9 projection malformed candidates zero |
| Truncation and same-inode replacement | Regression/focused 2/2 PASS; terminal six-session recovery matrix blocked |
| Duplicate replay | Regression/focused PASS; v9 baseline ledger differences zero |
| Callback exception before acknowledgement | Regression PASS; full-six restart schedules blocked |
| Failure after durable append | Regression/focused PASS; full-six transition-boundary proof blocked |
| Restart after ingestion before analytical flush | Regression/focused PASS; full-six checkpoint restart blocked |
| Out-of-order visibility and candidate barrier | Regression/focused PASS with refusals zero; full-six one-record proof blocked |
| Exact-second/fractional timestamps | Regression strict-parser fixtures PASS |
| Naive/future timestamp refusal | Regression fixtures PASS, including the new naive availability-clock refusal |
| Empty Index matching | New aware-`NaT` regression fixture PASS; v9 baseline causality 9/9 PASS |
| Stale market suspension | Engine/API regression fixtures PASS; deployed-live check not performed |
| Missing options/fixed context isolation | Engine/API regression fixtures PASS; deployed-live check not performed |

## Historical evidence retained as historical

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` terminal run is
pre-repair historical evidence, not the current acceptance identity. Historical
focused merged-v2/full-six-v1 GUI-compaction failures, v6 one-record visibility
failure, and interrupted v2-v8 attempts remain rejected diagnostics. They are
useful provenance for the comparator and harness repairs but contribute no
current terminal schedule count.
