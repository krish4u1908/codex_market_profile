# R6E1R Artifact Equivalence Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FRESH V9 ORIGINAL-CHUNK A/B AND FROZEN REFERENCES PASS; TERMINAL FULL-SIX SCHEDULE EQUIVALENCE AND DEPLOYMENT PENDING**

Evidence lineage:

- Branch snapshot at this refresh: `612d3ebb8fad818386f4b2a6a9b6f519ac837ada`.
- Analytical commit exercised by v9: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.
- V9 invocation: `ce9595fd18b344ab8ab2765ae509f8fa`.

Fresh v9 incremental A consumed original source chunks through the production
checkpoint/callback path. Fresh v9 clean B used an independently clean
chronological batch over the same selected raw bytes. Their published baseline
comparisons are exact canonical multiset/identity comparisons; no floating
tolerance, count-only inference, derived R2-R6 tables, or inherited R6C2R A/B
output was accepted as stream/batch equivalence.

This document distinguishes the immutable original-chunk A/B and reference
slice, which has passed, from the eight remaining full-six schedules and the
terminal summary, which remain pending.

## Fresh v9 canonical component matrix

| Artifact | Frozen expected | Incremental A | Clean B | Matched | A-only | B-only | Field mismatch | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Synchronized basis | — | 158,746 | 158,746 | 158,746 | 0 | 0 | 0 | PASS |
| BN-reference inventory | 255 | 255 | 255 | 255 | 0 | 0 | 0 | PASS |
| Divergence episodes | 65 | 65 | 65 | 65 | 0 | 0 | 0 | PASS |
| GREEN | 41 | 41 | 41 | 41 | 0 | 0 | 0 | PASS |
| RED | 24 | 24 | 24 | 24 | 0 | 0 | 0 | PASS |
| Dependency groups | 65 | 65 | 65 | 65 | 0 | 0 | 0 | PASS |
| Dependent retriggers | 14 | 14 | 14 | 14 | 0 | 0 | 0 | PASS |
| Lifecycle transitions | 14,201 | 14,201 | 14,201 | 14,201 | 0 | 0 | 0 | PASS |
| Dense resolution observations | 164,668 | 164,668 | 164,668 | 164,668 | 0 | 0 | 0 | PASS |
| Response observations | 65 | 65 | 65 | 65 | 0 | 0 | 0 | PASS |
| Dense participation | 69,225 | 69,225 | 69,225 | 69,225 | 0 | 0 | 0 | PASS |
| Participation transitions | 32,068 | 32,068 | 32,068 | 32,068 | 0 | 0 | 0 | PASS |
| Participation summaries | 65 | 65 | 65 | 65 | 0 | 0 | 0 | PASS |
| Compatibility snapshots | 65 | 65 | 65 | 65 | 0 | 0 | 0 | PASS |
| Cross-layer material transitions | 60,659 | 60,659 | 60,659 | 60,659 | 0 | 0 | 0 | PASS |
| Availability states | — | 24 | 24 | 24 | 0 | 0 | 0 | PASS |
| GUI-visible session state | — | 6 | 6 | 6 | 0 | 0 | 0 | PASS |

The complete component CSV contains 21/21 passing rows because its four
fallback-extension rows are itemized separately below. Unexplained remainder is
zero. Component-matrix SHA-256:
`fd5fad066510b5fe01f5914f55aa3fa2b7fbac9b27af9a9caa4da76b658cf388`.

## Graceful-degradation extension

The canonical frozen surface excludes live fallback rows by design. Both fresh
v9 A and B independently produced:

| Live extension | Incremental A | Clean B | Matched | Differences | Result |
|---|---:|---:|---:|---:|---|
| Intraday fallback inventory | 118 | 118 | 118 | 0 | PASS |
| Partial-fixed fallback inventory | 21 | 21 | 21 | 0 | PASS |
| Intraday fallback cross-layer | 118 | 118 | 118 | 0 | PASS |
| Partial-fixed fallback cross-layer | 21 | 21 | 21 | 0 | PASS |

The baseline live publication therefore has 394 inventory rows
(`255 + 118 + 21`) and 60,798 cross-layer rows
(`60,659 + 118 + 21`). The frozen-reference contract remains exactly 255 and
60,659.

## Fresh v9 append-only analytical ledgers

| Ledger | Incremental A | Clean B | Identity/content differences | Result |
|---|---:|---:|---:|---|
| Divergence confirmations | 65 | 65 | 0 | PASS |
| Dependency retriggers/groups | 65 | 65 | 0 | PASS |
| Lifecycle transitions | 14,201 | 14,201 | 0 | PASS |
| Inventory winner transitions, including fallback | 394 | 394 | 0 | PASS |
| Participation transitions | 32,068 | 32,068 | 0 | PASS |
| Cross-layer transitions, including fallback | 60,798 | 60,798 | 0 | PASS |
| Availability transitions | 72 | 72 | 0 | PASS |
| Stale-recovery transitions | 39 | 39 | 0 | PASS |

All 8/8 ledger rows pass. A-only, B-only, field mismatch, and
identity/content-difference counts are zero. Ledger-matrix SHA-256:
`e68f5f098b6157160b2a27e51c4bc709a6bc0fc25aa71e7fcb39617c8cb77e48`.
The common analytical-ledger aggregate is
`4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65`.

## Fresh v9 causality and GUI invariants

| Invariant | Incremental A | Clean B | Result |
|---|---:|---:|---|
| Future joins | 0 | 0 | PASS |
| Synchronization tolerance violations | 0 | 0 | PASS |
| Timestamp backdating | 0 | 0 | PASS |
| Duplicate analytical IDs | 0 | 0 | PASS |
| Valid timestamps becoming `NaT` | 0 | 0 | PASS |
| Analytical refusals | 0 | 0 | PASS |
| GUI clock-contract violations | 0 | 0 | PASS |
| GUI display-contract violations | 0 | 0 | PASS |
| GUI path-clock violations | 0 | 0 | PASS |

Causality passes 9/9; matrix SHA-256:
`f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2`.

The empty-Index repair in `e1d67c5` is represented by this baseline. It uses a
timezone-aware all-missing match timestamp when no Index row is eligible and
refuses naive availability clocks. The zero `valid_timestamps_becoming_nat`,
future-join, tolerance, and backdating rows demonstrate that the repair did not
alter a frozen analytical or clock rule.

## Fresh v9 frozen-reference matrices

| Comparator | Rows | Target-only | Reference-only | Unexplained | Result | SHA-256 |
|---|---:|---:|---:|---:|---|---|
| R6C2R canonical stack | 30/30 | 0 | 0 | 0 | PASS | `0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8` |
| R6D GUI | 180/180 | 174,080 permitted live extensions | 0 | 0 | PASS | `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467` |

For R6D, target-only rows equal the independently enumerated 174,080 permitted
live extensions exactly. Both frozen package manifests were verified before
comparison: R6C2R 74/74 and R6D 40/40. Reference-manifest verification SHA-256:
`ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.

## Fresh v9 source and immutable baseline identities

The raw projection contains 141 authoritative source files, 139 projection
files, and 746,890 byte-exact selected records across six evaluation sessions
and eight causal source sessions. Malformed candidate records and source
mutations are zero. August 17 is present for the canonical predecessor decision
and is explicitly `PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`.

| Evidence | SHA-256 |
|---|---|
| Raw projection manifest | `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426` |
| Raw projection provenance | `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0` |
| Source hash comparison | `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56` |
| Incremental-A seal | `fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7` |
| Incremental-A snapshot | `c03d1e3ef195a70df83221897bf7d1e73a63790b46629825ffc3ef3731c5ce87` |
| Incremental-A state manifest | `5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173` |
| Incremental-A state tree | `f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6` |
| Clean-B seal | `99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568` |
| Clean-B snapshot | `285256f5438eaebd86916aabcee7413aa668e1d8d57a1c4fab281f87dffe2526` |

Incremental A processed 543,329 evaluation JSON records from 104 source files
and sealed 26 state files. Its checkpoint failures, analytical refusals,
future joins, timestamp backdating, duplicate analytical IDs, checkpoint
remainders, dirty sessions, and unexpected sessions were all zero. Its elapsed
time was 5,893.937 seconds with process peak RSS 6,481,416 KiB. Clean B elapsed
741.789 seconds with child-process peak RSS 7,153,156 KiB.

## Terminal schedules, storage, recovery, and preload

| Matrix or gate | Fresh v9 result |
|---|---|
| Original source chunks | Immutable A/B and references PASS as recorded above |
| One record per increment | `PENDING_FINAL_EVIDENCE` |
| Deterministic variable chunks | `PENDING_FINAL_EVIDENCE` |
| Boundaries inside JSONL lines | `PENDING_FINAL_EVIDENCE` |
| Empty/repeated polls | `PENDING_FINAL_EVIDENCE` |
| Multiple checkpoint restarts | `PENDING_FINAL_EVIDENCE` |
| Restart at analytical transition boundaries | `PENDING_FINAL_EVIDENCE` |
| Hourly file rotation | `PENDING_FINAL_EVIDENCE` |
| Large chronological chunks | `PENDING_FINAL_EVIDENCE` |
| Terminal checkpoint accounting | `PENDING_FINAL_EVIDENCE` |
| Terminal bundle-storage matrix | `PENDING_FINAL_EVIDENCE` |
| Terminal truncation/replacement recovery matrix | `PENDING_FINAL_EVIDENCE` |
| Real preload validation of final accepted state | `PENDING_FINAL_EVIDENCE` |
| Terminal equivalence summary and SHA-256 | `PENDING_FINAL_EVIDENCE` |

No pre-repair schedule, checkpoint, storage, recovery, summary, or preload hash
is relabelled as fresh v9 evidence. Until every row above passes and the final
bundle is sealed, the required result “stream versus batch differences: 0” is
proven only for the original-chunk baseline, not for all nine full-six
schedules.

## Focused prerequisite

The clean post-repair August 19 focused run against `e1d67c5` passed 21/21
components, 8/8 ledgers, 9/9 causality groups, 9/9 focused schedules, 16/16
storage rows, 72/72 checkpoint rows, 2/2 recovery probes, and 8/8 source rows.
Every comparison and safety counter was zero. Its summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
This is prerequisite evidence, not a substitute for the pending full-six
schedule matrix.

## Historical evidence retained as historical

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` full-six result is
pre-repair historical evidence and is not the current terminal result.
Historical focused merged-v2/full-six-v1 GUI-compaction failures, v6 one-record
visibility/refusal failure, and interrupted v2-v8 attempts remain rejected
diagnostics. Their counts and hashes are not reused in any fresh v9 pending
cell.
