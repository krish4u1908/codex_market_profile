# R6E1R Six-Session Equivalence Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **IN PROGRESS — CURRENT-REPAIR A/B AND REFERENCE MATRICES PASS; EIGHT ALTERNATE SCHEDULES AND TERMINAL GATES PENDING**

This report records only immutable evidence already published by the persistent
current-repair v9 verifier. It does not promote the full six-session gate to
PASS. A verified tag and deployment preload remain prohibited until every
pending schedule and terminal artifact below is sealed and independently
validated.

## Current authority

The active evidence run is pinned to clean repair commit
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`. The repaired engine aggregate is
`eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947`;
its 38-file manifest SHA-256 is
`866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210`.
The combined runtime-configuration identity is
`b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41`.

The persistent verifier is `market-profile-history-verifier-v9.service`,
invocation `ce9595fd18b344ab8ab2765ae509f8fa`. Its clean checkout is
`/home/codexuser/mp-engine-e1d-v9`; its evidence output root is
`/opt/banknifty/research/vpoc_oi_price_response_v2/historical_callback_acceptance_v9`.
The service is intentionally left running while the eight alternate schedules
complete. Values below are read only from marker-last immutable seals and
matrices; mutable SQLite state is not acceptance evidence.

## Focused prerequisite

The fresh post-repair August 19 focused fixture completed all nine schedules
before the full-six run was admitted. Its summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.

| Focused gate | Result |
|---|---:|
| Canonical components | 21/21 PASS |
| Append-only ledgers | 8/8 PASS |
| Causality invariants | 9/9 PASS |
| Schedules | 9/9 PASS |
| Fresh/final storage rows | 16/16 PASS |
| Checkpoint rows | 72/72 PASS |
| Truncation/replacement recovery | 2/2 PASS |
| Source-integrity rows | 8/8 PASS |
| Prohibited / unmeasured runtime opens | 0 / 0 |

The focused open audit contained 2,508 rows, including 2,499 runtime rows and
1,190,240 represented opens. Elapsed harness time was 3,839.101 seconds;
parent/child peak RSS was 1,730,828/891,172 KiB and cgroup peak memory was
2,965,729,280 bytes. This is a prerequisite only; it does not substitute for
fresh full-six schedule evidence.

## Raw projection and causal scope

The v9 projection was rebuilt read-only from
`/opt/banknifty-collector/data-prod-v4`. It selected 746,890 complete outer
JSON records into 139 projection files from 141 authoritative source files,
representing 34,709,921 complete physical rows and 541,091,186 projected
bytes. Projection construction took 117.675 seconds and peaked at 189,924 KiB
RSS. Malformed selected records and observed source mutations were both zero.

The six evaluation sessions are 2026-08-11, 2026-08-12, 2026-08-13,
2026-08-18, 2026-08-19, and 2026-08-20. Causal source discovery also selected
August 10 and August 17 as context. The August 17 policy is exactly
`PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`; it was not promoted
into the accepted predecessor chain. Contracts were selected by
`banknifty_profiler.raw_io.reader.select_contracts`, not hard-coded. No derived
R2-R6 analytical table was used as A/B input.

| Projection evidence | SHA-256 |
|---|---|
| Raw projection manifest | `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426` |
| Projection provenance | `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0` |
| Pre-run source comparison | `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56` |

All 141 source-comparison rows were unchanged at projection time. The distinct
terminal post-run source rehash remains pending and is not inferred from this
pre-run comparison.

## Sealed original-source A/B baseline

Incremental A used the repository's production ingestor callback/checkpoint
path. Clean B used three independently invoked repository-owned chronological
batch processors against the same selected bytes and a clean state root. Both
sides were sealed before verified R6C2R or R6D reference packages were opened.

| Measure | Incremental A | Clean B |
|---|---:|---:|
| Schedule | Original source chunks | Independent clean canonical batch |
| Source files / JSON records | 104 / 543,329 | Same selected bytes |
| Source bytes / complete physical rows | 396,713,521 / 25,293,503 | Same selected bytes |
| Harness polls | 65 | Not applicable |
| Processor command return codes | Not applicable | 0 / 0 / 0 |
| Elapsed seconds | 5,893.937 | 741.789 |
| Peak RSS KiB | 6,481,416 | 7,153,156 child-process peak |
| Seal SHA-256 | `fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7` | `99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568` |
| Snapshot SHA-256 | `c03d1e3ef195a70df83221897bf7d1e73a63790b46629825ffc3ef3731c5ce87` | `285256f5438eaebd86916aabcee7413aa668e1d8d57a1c4fab281f87dffe2526` |
| Whole-snapshot semantic SHA-256 | `bd8bdbaaeac3db54c289575d7c0d3f3fca73934f0830ab974656ded3c6175527` | `26d16e78e44b3de3849c7af6b73305a92fd6f1df0565276e980f19a40049d1a7` |
| Append-only ledger SHA-256 | `4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65` | `4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65` |

Incremental A sealed 26 state files. Its state-manifest SHA-256 is
`5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173`
and its state-tree SHA-256 is
`f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6`.
Checkpoint failures, analytical refusals, undrained causal checkpoint
remainders, dirty sessions, unexpected sessions, future joins, timestamp
backdating, and duplicate analytical IDs in the sealed A record were all zero.

The whole-snapshot semantic hashes differ because the two execution modes
seal different orchestration surfaces; byte identity of those wrapper
snapshots is not the canonical equality test. The independently projected
21-component, eight-ledger, nine-causality, and GUI/reference matrices below
compare the required analytical artifacts and are exact.

## Canonical A/B artifact equivalence

The component matrix passes 21/21 rows with zero A-only rows, B-only rows,
field mismatches, or unexplained remainder.

| Artifact | Frozen count | Incremental A | Clean B | Differences | Result |
|---|---:|---:|---:|---:|---|
| Synchronized basis | — | 158,746 | 158,746 | 0 | PASS |
| Inventory | 255 | 255 | 255 | 0 | PASS |
| Divergence episodes | 65 | 65 | 65 | 0 | PASS |
| GREEN / RED | 41 / 24 | 41 / 24 | 41 / 24 | 0 | PASS |
| Dependency groups / dependent retriggers | 65 / 14 | 65 / 14 | 65 / 14 | 0 | PASS |
| Lifecycle transitions | 14,201 | 14,201 | 14,201 | 0 | PASS |
| Dense resolution observations | 164,668 | 164,668 | 164,668 | 0 | PASS |
| Response observations | 65 | 65 | 65 | 0 | PASS |
| Dense participation | 69,225 | 69,225 | 69,225 | 0 | PASS |
| Participation transitions | 32,068 | 32,068 | 32,068 | 0 | PASS |
| Participation summaries / compatibility snapshots | 65 / 65 | 65 / 65 | 65 / 65 | 0 | PASS |
| Cross-layer material transitions | 60,659 | 60,659 | 60,659 | 0 | PASS |
| Availability states / GUI-visible sessions | — | 24 / 6 | 24 / 6 | 0 | PASS |

The remaining component rows prove graceful degradation on both sides: 118
Intraday inventory rows, 118 linked Intraday cross-layer rows, 21 partial-fixed
inventory rows, and 21 linked partial-fixed cross-layer rows. Therefore the
complete live surface has 394 inventory and 60,798 cross-layer rows. Those 139
permitted live-extension rows do not replace the frozen 255/60,659 contract.

The ledger matrix passes 8/8 rows with zero identity/content difference:
65 divergence confirmations, 65 dependency/retrigger records, 14,201
lifecycle transitions, 394 inventory-winner transitions, 32,068 participation
transitions, 60,798 cross-layer transitions, 72 availability transitions, and
39 stale-recovery transitions.

The causality matrix passes 9/9 with zero future joins, synchronization
tolerance violations, timestamp backdating, duplicate analytical IDs, valid
timestamps becoming `NaT`, analytical refusals, GUI clock violations, GUI
display-contract violations, or GUI path-clock violations.

## Frozen reference equivalence

Both pinned verified manifests passed before comparison:

- `r6c2r-full-stack-equivalence-verified` target
  `9cbe46fea6e3a44f3cf574955f21b5b1ebb6aa96`: 74 files verified.
- `r6d-offline-gui-verified` target
  `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14`: 40 files verified.

R6C2R comparison passes 30/30 rows with zero target-only, reference-only, or
unexplained rows. R6D GUI comparison passes 180/180 rows: 174,080 target-only
rows exactly equal 174,080 permitted live-extension rows, with zero
reference-only or unexplained rows. The reference-package verification file
SHA-256 is
`ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.

| Published matrix | Rows passing | SHA-256 |
|---|---:|---|
| A/B canonical components | 21/21 | `fd5fad066510b5fe01f5914f55aa3fa2b7fbac9b27af9a9caa4da76b658cf388` |
| Append-only ledger identities | 8/8 | `e68f5f098b6157160b2a27e51c4bc709a6bc0fc25aa71e7fcb39617c8cb77e48` |
| Causality invariants | 9/9 | `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2` |
| R6C2R reference comparison | 30/30 | `0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8` |
| R6D GUI comparison | 180/180 | `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467` |

## Current scoped zero gates

These are established for sealed original-source A, independent clean B, and
the published canonical/reference matrices only. They are not a substitute for
the pending alternate-schedule and terminal audits.

| Measure | Current value | Scope |
|---|---:|---|
| Stream-versus-batch canonical component differences | 0 | 21/21 baseline rows |
| Canonical R6C2R unexplained mismatches | 0 | 30/30 rows |
| Append-only ledger identity/content differences | 0 | 8/8 rows |
| GUI-visible unexplained differences | 0 | 180/180 rows |
| Future joins | 0 | Sealed A/B causality matrix |
| Synchronization tolerance violations | 0 | Sealed A/B causality matrix |
| Timestamp backdating | 0 | Sealed A/B causality matrix |
| Duplicate analytical IDs | 0 | Sealed A/B causality matrix |
| Analytical refusals | 0 | Sealed A/B causality matrix |
| Malformed selected records | 0 | Projection |
| Source mutations | 0 | Projection-time comparison only |

Final values for schedule failures, bundle failures, checkpoint failures,
recovery failures, prohibited/unmeasured runtime opens, and post-run source
mutations remain pending.

## Alternate schedules still pending

The original-source A/B baseline above is sealed, but the terminal scheduling
matrix has not been published. Every alternate schedule is therefore retained
as explicitly pending; historical results are not imported.

| Schedule | Current v9 status |
|---|---|
| Original source chunks | `SEALED_BASELINE_PASS; TERMINAL_SCHEDULE_BUNDLE_PENDING` |
| One complete JSONL record per increment | `PENDING_V9_EVIDENCE` |
| Deterministic variable chunks | `PENDING_V9_EVIDENCE` |
| Chunk boundaries inside JSONL lines | `PENDING_V9_EVIDENCE` |
| Empty/repeated polls | `PENDING_V9_EVIDENCE` |
| Multiple checkpoint restarts | `PENDING_V9_EVIDENCE` |
| Restart at analytical transition boundaries | `PENDING_V9_EVIDENCE` |
| Hourly file rotation | `PENDING_V9_EVIDENCE` |
| Large chronological chunks | `PENDING_V9_EVIDENCE` |

The published schedule contract file SHA-256 is
`9579ec8a4dc5d3b06e3f0caf6005903a83a12804711aff3f8b01d05ce5663020`;
its embedded canonical contract SHA-256 is
`af10b6130ef38ca42c79be8aad0ebef3df4bbb9494ac974321cd315ae94583d0`.
The feasibility CSV is planning evidence only and labels unexecuted schedules
`REQUIRED_NOT_SATISFIED`; it is not a completion matrix.

## Terminal publication gates still pending

| Required terminal artifact | Current status |
|---|---|
| Fresh/final bundle-storage matrix and marker-last revalidation | `PENDING_V9_EVIDENCE` |
| Full checkpoint-accounting matrix | `PENDING_V9_EVIDENCE` |
| Truncation/replacement recovery matrix | `PENDING_V9_EVIDENCE` |
| Complete runtime file-open audit | `PENDING_V9_EVIDENCE` |
| Post-run authoritative-source hash comparison | `PENDING_V9_EVIDENCE` |
| Terminal all-gates equivalence summary | `PENDING_V9_EVIDENCE` |
| Incremental-A deployment-preload validation | `PENDING_V9_EVIDENCE` |

Until these artifacts and all eight alternate schedule bundles pass, this
report must remain `IN PROGRESS`. No elapsed total, terminal peak RSS, output
tree total, final full-six test count, deployment package result, or verified
tag is claimed here.

## Rejected historical evidence

The complete `81b0836fe50939246ae210bb62780ac4e163e100` run remains useful historical
evidence, but it predates repair `e1d67c5...` and cannot establish equivalence
for the repaired callback path. None of its schedule, terminal-audit,
performance, summary, or preload values populates current v9 cells.

Post-repair attempts v2 through v6 were interrupted or externally cleaned
before terminal publication; although v2 reached sealed A/B/reference
matrices, it was interrupted during the one-record schedule and its evidence
tree was subsequently removed. Direct v7 received an external interrupt before
a seal. Persistent v8 failed closed in preflight because its required v7
projection was already absent. These runs are rejected diagnostics only. No
partial or inherited schedule result is carried into v9.

Per-artifact status will be reconciled in
[R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md](R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md)
after terminal v9 publication.
