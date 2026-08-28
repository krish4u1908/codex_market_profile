# R6E1R Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` full-six result is
historical only. An authenticated engine byte changed after the sparse
empty-Index repair, so that run cannot establish final equivalence for the
current engine.

No failing or skipped test has been weakened, deselected, reclassified, or
omitted to obtain a pass.

## Terminal infrastructure stop

The operator stop applied the v9 runtime mask at `20:39:00.999`; systemd
recorded a client-requested `SIGINT` at `20:39:01` and client-requested
`SIGTERM` at `20:39:06`. No OOM kill occurred, swap use was zero, and the
observed peak was 14.5 GiB. The v9 evidence, work, and control roots were
externally deleted after the operator stop. A post-stop search found zero surviving alternate-schedule bundles,
no bundle marker, and no terminal all-gates summary.

The v9 baseline/reference test hashes retained below are independently
observed and pushed facts only; they are not surviving final all-nine
artifacts. A fresh rerun requires an explicit uninterrupted root-agreed window
and must not evade an active root operator. Deployment/preload were not
performed, and no verified tag was created.

## Current regression authority

| Suite | Passed | Failed | Errors | Skipped/deselected | Elapsed | Peak RSS | Standing |
|---|---:|---:|---:|---:|---:|---:|---|
| Complete fully provisioned repository regression after sparse-context repair and package reseal | 660 | 0 | 0 | 0 | 118.03 s pytest; 1m58.43 wall | 671,340 KiB | PASS |
| Targeted empty-aware/naive-clock repair tests | 3 | 0 | 0 | 0 | Included before complete suite | — | PASS |
| Corrected package/isolation regressions after stale config-pin repair | 2 | 0 | 0 | 0 | Included before complete suite | — | PASS |

The initial complete invocation after the engine repair retained one packaging
failure (659 pass / 1 fail) because a systemd launcher still pinned the old
runtime-configuration digest. The pin was repaired, both directly affected
tests passed, and the unchanged complete suite then passed 660/660. That
intermediate 659/1 result remains a non-pass.

Current authenticated identities are:

- engine aggregate:
  `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947`;
- engine manifest:
  `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210`;
- runtime configuration:
  `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41`;
- deployment aggregate:
  `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949`;
- deployment manifest:
  `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391`.

## Focused August 19 acceptance

The fresh post-repair run used the authorized 2026-08-19 09:15-12:05 IST
fixture and completed incremental A, independently clean chronological B, the
original schedule, and all eight alternate schedules.

| Gate | Passed | Failed | Result |
|---|---:|---:|---|
| Canonical component rows | 21/21 | 0 | PASS |
| Append-only ledger rows | 8/8 | 0 | PASS |
| Causality invariant groups | 9/9 | 0 | PASS |
| Required schedules | 9/9 | 0 | PASS |
| Fresh/final schedule-bundle storage rows | 16/16 | 0 | PASS |
| Checkpoint accounting | 72/72 | 0 | PASS |
| Truncation/replacement recovery | 2/2 | 0 | PASS |
| Source identities | 8/8 | 0 | PASS |

Every stream/batch, canonical, identity/content, tolerance, future-join,
timestamp-backdating, duplicate-ID, analytical-refusal, prohibited-open,
unmeasured-open, and source-mutation counter was zero. The measured audit has
2,508 rows, including 2,499 runtime rows representing 1,190,240 opens.

Focused equivalence summary SHA-256:
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
Schedule-contract SHA-256:
`5314d28c1e6aaa2d4a38cf91d2a90148bca800b1162cfc0d869db14c492cfde7`.

The focused harness completed in 3,839.101 seconds (1:04:00 wall), with
parent/child peak RSS of 1,730,828/891,172 KiB, a 2,965,729,280-byte cgroup
peak, and zero swap.

## Observed v9 full-six baseline evidence

V9 was pinned to a fresh clean checkout of `e1d67c5`, fresh state/output roots,
the authoritative raw root, and both verified frozen reference packages. Its
roots no longer survive, so the facts in this section are retained
pre-deletion observations and not a current terminal authority.

### Projection and source preflight

- 141/141 authoritative source rows rehashed unchanged;
- 139 byte-exact projection files and 746,890 selected complete records;
- six evaluation sessions and eight causal sessions;
- malformed selected records: 0;
- projection-time source mutations: 0;
- August 17 policy:
  `PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`.

Projection manifest/provenance/source-comparison SHA-256 values are:

- `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426`;
- `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0`;
- `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56`.

The all-nine contract file/embedded SHA-256 values are
`9579ec8a4dc5d3b06e3f0caf6005903a83a12804711aff3f8b01d05ce5663020`
and
`af10b6130ef38ca42c79be8aad0ebef3df4bbb9494ac974321cd315ae94583d0`.

### Observed A/B and comparison seals

Canonical incremental A was observed sealed with:

- seal:
  `fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7`;
- snapshot:
  `c03d1e3ef195a70df83221897bf7d1e73a63790b46629825ffc3ef3731c5ce87`;
- 26-file state manifest:
  `5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173`;
- state tree:
  `f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6`.

Independent clean chronological B was observed sealed with seal/snapshot SHA-256
`99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568`
and
`285256f5438eaebd86916aabcee7413aa668e1d8d57a1c4fab281f87dffe2526`.
A and B have the same append-only ledger aggregate:
`4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65`.

| Sealed baseline gate | Passed | Failed | Result |
|---|---:|---:|---|
| Canonical components | 21/21 | 0 | PASS |
| Append-only ledgers | 8/8 | 0 | PASS |
| Causality invariant groups | 9/9 | 0 | PASS |
| R6C2R row-level comparisons | 30/30 | 0 | PASS |
| R6D GUI row-level comparisons | 180/180 | 0 unexplained | PASS |

Every A-only, B-only, field, identity/content, unexplained, future-join,
tolerance, backdating, duplicate, refusal, and GUI clock/display/path difference
in these sealed matrices is zero. Matrix SHA-256 values are:

- canonical components:
  `fd5fad066510b5fe01f5914f55aa3fa2b7fbac9b27af9a9caa4da76b658cf388`;
- analytical ledgers:
  `e68f5f098b6157160b2a27e51c4bc709a6bc0fc25aa71e7fcb39617c8cb77e48`;
- causality:
  `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2`;
- R6C2R comparison:
  `0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8`;
- R6D GUI comparison:
  `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467`.

The frozen packages reverified 74/74 R6C2R files and 40/40 R6D files. Package
verification SHA-256 is
`ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.
The baseline reproduces the frozen counts, including 255 inventory rows, 65
episodes (41 GREEN / 24 RED), 14 retriggers, 14,201 lifecycle transitions,
164,668 dense resolution observations, 65 responses, 69,225 dense
participation rows, 32,068 participation transitions, 65 summaries, 65
compatibility snapshots, and 60,659 cross-layer transitions. The permitted
live degradation extension is independently distinguished from these frozen
counts.

## Full-six gates blocked

The observed baseline seals above do not constitute terminal all-nine
acceptance. The deleted v9 roots supplied no surviving marker-last alternate
bundle or terminal summary, so the following are **BLOCKED** and must not be
inferred from the historical `81b0836` run:

| Required full-six gate | Current standing |
|---|---|
| One complete JSONL record per increment | BLOCKED; no surviving bundle |
| Deterministic variable chunks | BLOCKED; no surviving bundle |
| Chunk boundaries inside JSONL lines | BLOCKED; no surviving bundle |
| Empty/repeated polls | BLOCKED; no surviving bundle |
| Multiple checkpoint restarts | BLOCKED; no surviving bundle |
| Restart at analytical transition boundaries | BLOCKED; no surviving bundle |
| Hourly file rotation | BLOCKED; no surviving bundle |
| Large chronological chunks | BLOCKED; no surviving bundle |
| Final 16/16 bundle-storage matrix | BLOCKED; no terminal summary |
| Final 936/936 checkpoint matrix | BLOCKED; no terminal summary |
| Final 2/2 recovery matrix | BLOCKED; no terminal summary |
| Final measured file-open audit | BLOCKED; no terminal summary |
| Final authoritative/projection post-source comparison | BLOCKED; no terminal summary |
| Full-six terminal equivalence summary | BLOCKED; no terminal summary/exit 0 |
| Real copied-state preload validation | BLOCKED; accepted state root deleted |

Consequently no current-engine claim is made for 9/9 full-six schedules,
936/936 checkpoints, a terminal full-six open count, a terminal post-source
count, a full-six summary hash, preload success, or total full-six
elapsed/peak/output measurements.

## Adversarial and regression standing

The complete 660-test regression and focused all-nine run cover strict
mixed-format timestamps, exact-second/fractional timestamps, naive/future
clock refusal, partial-line deferral/retry, malformed-record refusal,
truncation/replacement refusal, rotation, replay/exactly-once IDs, callback
failure before acknowledgement, durable restart behavior, out-of-order
visibility, stale Index/Futures suspension, missing CE/PE isolation, fixed-layer
degradation, current-session exclusion, August 17 rejection, toggle
persistence, separate Index/Futures paths, price/basis alignment, browser
projection-only analytics, sanitized payloads, and harness tamper defenses.

Where the acceptance requirement specifically calls for a full-six alternate
schedule or full-six terminal aggregate, the current regression/focused result
does not substitute for a fresh terminal artifact.

## Historical and rejected evidence

- The terminal `81b0836` full-six run and its 658-test regression predate the
  sparse-context engine repair. Their counts and timings remain historical but
  are not current acceptance evidence.
- Full-six v2 sealed post-repair A/B/reference comparisons but was externally
  interrupted before an alternate schedule bundle sealed; its evidence tree
  was later deleted. It is rejected for final acceptance.
- Recovery attempts v3-v6 did not produce an eligible terminal result and were
  externally stopped or deleted. No partial bundle is promoted.
- Direct v7 rebuilt its projection but was externally interrupted by signal 2
  before A sealed; its partial output is rejected.
- Persistent v8 failed closed before Python because the referenced projection
  manifest had been deleted; it supplies no analytical evidence.
- Earlier focused runs with incomplete child-open tracing, incorrect GUI
  comparison surfaces, or incomplete transition-boundary coverage remain
  rejected and are not relabelled.

## Blocked boundary

The current engine's complete regression and focused all-nine acceptance pass;
fresh full-six projection/A/B/reference facts were observed before deletion.
Terminal full-six alternate schedules, final open/source/storage/checkpoint/
recovery aggregation, and preload validation remain blocked. Isolated live
deployment, deployed browser checks, health/readiness checks, and
public-interface reachability were not performed.
