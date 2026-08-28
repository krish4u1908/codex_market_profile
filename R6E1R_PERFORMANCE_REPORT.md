# R6E1R Performance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

## Terminal infrastructure stop

The operator stop applied the v9 runtime mask at `20:39:00.999`; systemd
recorded a client-requested `SIGINT` at `20:39:01` and client-requested
`SIGTERM` at `20:39:06`. No OOM kill occurred, swap use was zero, and the
observed peak was 14.5 GiB. The v9 evidence, work, and control roots were
externally deleted after the operator stop. A post-stop search found zero surviving alternate-schedule bundles,
no bundle marker, and no terminal all-gates summary.

The v9 measurements and hashes below are retained independently observed and
pushed baseline facts, not surviving final all-nine artifacts. The 14.5-GiB
peak is stop-diagnostic evidence, not a terminal all-nine measurement. A fresh
run requires an explicit uninterrupted root-agreed window and must not evade
an active root operator. Deployment/preload were not performed, and no
verified tag was created.

## Accepted current measurements

| Workload | Result | Elapsed | Peak parent/process RSS | Peak child RSS | Other resource evidence |
|---|---|---:|---:|---:|---|
| Complete repository regression after sparse-context repair/package reseal | 660 passed; 0 failed/errors/skipped/deselected | 118.03 s pytest; 1m58.43 wall | 671,340 KiB | — | Exit 0 |
| Focused August 19 all-nine acceptance | PASS | 3,839.101 s harness; 1:04:00 wall | 1,730,828 KiB | 891,172 KiB | 2,965,729,280-byte cgroup peak; swap 0 |
| Persistent v9 raw projection | PASS | 117.675 s | 189,924 KiB | — | 141 sources; 139 files; 746,890 records |
| Persistent v9 canonical incremental A, original source chunks | Observed baseline PASS; root deleted | 5,893.937 s | 6,481,416 KiB | — | 26 files; 4,141,835,394-byte state observed before deletion |
| Persistent v9 independent clean chronological B | Observed baseline PASS; root deleted | 741.789 s | — | 7,153,156 KiB | Child command exits 0/0/0 |
| Interrupted v9 overall process | BLOCKED stop diagnostic | Not terminal | 14.5 GiB observed peak | — | No OOM; swap 0; roots deleted |

Focused equivalence summary SHA-256:
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.

The persistent v9 A/B append-only ledger aggregate is exactly
`4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65`.
A's seal/state-manifest/state-tree SHA-256 values are:

- `fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7`;
- `5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173`;
- `f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6`.

B's seal SHA-256 is
`99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568`.

## V9 configured resource envelope

The stopped verifier was configured as an isolated user service with:

- `MemoryHigh=24G`;
- `MemoryMax=28G`;
- `MemorySwapMax=0`;
- `CPUQuota=600%`;
- address-family restriction to `AF_UNIX`;
- fresh checkout, work, projection, and output roots.

Its unit SHA-256 is
`48a65a204e2d1ad491f3b0eae7eebee7f6afc7254065fc48d75efbad972f352c`
and invocation identity is `ce9595fd18b344ab8ab2765ae509f8fa`.
No terminal cgroup peak, total CPU, total wall time, total output size, or final
memory-event accounting exists because the verifier did not exit cleanly and
its roots were deleted.

## Full-six schedule measurements blocked

Canonical A is a retained measured original-source-chunk baseline observation.
All alternate measurements require fresh marker-last bundles; historical
timings from `81b0836` cannot be copied into current acceptance.

| Schedule | Exercise count | Elapsed | Peak RSS | Atomic bundle identity | Standing |
|---|---:|---:|---:|---|---|
| Original source chunks | 543,329 selected outer records; 396,713,521 selected bytes | 5,893.937 s | 6,481,416 KiB | A seal `fa62ace6...` | Observed baseline PASS; root deleted |
| One record per increment | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Deterministic variable chunks | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Boundaries inside JSONL lines | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Empty/repeated polls | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Multiple checkpoint restarts | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Analytical transition restarts | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Hourly file rotation | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |
| Large chronological chunks | BLOCKED | BLOCKED | BLOCKED | none survived | No surviving v9 bundle |

The following aggregate measurements were not published and are blocked:

- all-nine harness elapsed time and wall time;
- final parent/child/process and cgroup peak memory;
- final CPU and swap/memory-event accounting;
- final output file count and byte size;
- final file-open audit row/open totals;
- final post-run source comparison time;
- final full-six summary/run-log/timing SHA-256 values.

## State-preload measurement boundary

The A state was observed to contain 26 files and 4,141,835,394 bytes before its
root was deleted. This is a retained measurement only, not an available state
for preload. It may not be reconstructed from hashes or used for cold-start
performance claims without a fresh terminal run and copied-state validation.

Cold preload validation time, cold service-start time, recovery restart time,
endpoint latency, gateway payload size, deployed browser memory, and externally
served response latency are **NOT MEASURED — DEPLOYMENT NOT PERFORMED**.

## Preliminary scaling assessment

The implementation is architecturally bounded for live extension: raw
discovery/source identities are cached, checkpoint reads are incremental,
fixed 1D/2D/3D context is source-hash cached and excludes the current session,
finalized raw buckets are compacted after durable publication, and browser
responses are tail-limited rather than shipping dense historical tables.
Runtime configuration retains a bounded rolling output set while protecting
the six replay sessions.

That design supports the provisional conclusion that 20-30 sessions can be
served incrementally without loading all raw data or dense analytics into
browser memory. It does **not** establish that a fresh all-nine 20-30-session
equivalence rebuild fits the live service envelope. In the retained baseline
observations, clean B peaked at 7,153,156 KiB and the
original-source incremental A at 6,481,416 KiB. Longer historical validation
should remain an offline bounded job with a separately measured resource
envelope. This assessment must be revisited after a fresh terminal run and
deployment measurements are available.

## Historical and excluded measurements

- The pre-repair `81b0836` terminal full-six run took 49,456.697 harness
  seconds / 13:46:33 wall, peaked at 19,259,224 KiB process RSS and
  25,770,590,208 bytes at cgroup scope, and produced about 16.60 GB. Those
  values are historical only and do not establish post-repair performance.
- Its per-schedule timings and bundle hashes likewise remain historical and
  must not fill the blocked v9 table.
- Full-six v2 sealed post-repair A/B/reference evidence but was externally
  interrupted during the one-record schedule and later deleted. It has no
  terminal performance standing.
- Direct v7 was externally interrupted by signal 2 after 16:44.56 wall at
  4,982,376 KiB peak RSS and zero swap, before A sealed. That timing is a
  rejected diagnostic, not acceptance evidence.
- Persistent v8 failed closed in preflight before Python because the referenced
  projection had been deleted; it contributes no workload measurement.
- Earlier focused and full-six attempts with incomplete tracing, comparison,
  or transition-boundary coverage remain excluded.

No rejected timing, peak, output size, or superseded preload measurement is
used as current acceptance evidence.
