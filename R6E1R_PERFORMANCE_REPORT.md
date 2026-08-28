# R6E1R Performance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR REGRESSION/FOCUSED/PROJECTION/A/B MEASURED; TERMINAL
FULL-SIX AND PRELOAD PERFORMANCE PENDING**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

## Accepted current measurements

| Workload | Result | Elapsed | Peak parent/process RSS | Peak child RSS | Other resource evidence |
|---|---|---:|---:|---:|---|
| Complete repository regression after sparse-context repair/package reseal | 660 passed; 0 failed/errors/skipped/deselected | 118.03 s pytest; 1m58.43 wall | 671,340 KiB | — | Exit 0 |
| Focused August 19 all-nine acceptance | PASS | 3,839.101 s harness; 1:04:00 wall | 1,730,828 KiB | 891,172 KiB | 2,965,729,280-byte cgroup peak; swap 0 |
| Persistent v9 raw projection | PASS | 117.675 s | 189,924 KiB | — | 141 sources; 139 files; 746,890 records |
| Persistent v9 canonical incremental A, original source chunks | PASS / immutable seal | 5,893.937 s | 6,481,416 KiB | — | 26 files; 4,141,835,394-byte state |
| Persistent v9 independent clean chronological B | PASS / immutable seal | 741.789 s | — | 7,153,156 KiB | Child command exits 0/0/0 |

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

## Persistent v9 resource envelope

The persistent verifier runs as an isolated user service with:

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
memory-event accounting is accepted until the service exits 0.

## Full-six schedule measurements still pending

Canonical A is the measured original-source-chunk baseline. All alternate
schedule measurements must come from persistent v9's marker-last bundles;
historical timings from `81b0836` cannot be copied into current acceptance.

| Schedule | Exercise count | Elapsed | Peak RSS | Atomic bundle identity | Standing |
|---|---:|---:|---:|---|---|
| Original source chunks | 543,329 selected outer records; 396,713,521 selected bytes | 5,893.937 s | 6,481,416 KiB | A seal `fa62ace6...` | PASS |
| One record per increment | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Deterministic variable chunks | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Boundaries inside JSONL lines | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Empty/repeated polls | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Multiple checkpoint restarts | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Analytical transition restarts | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Hourly file rotation | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |
| Large chronological chunks | PENDING | PENDING | PENDING | PENDING | Await terminal v9 bundle |

The following aggregate measurements are also pending terminal v9 publication:

- all-nine harness elapsed time and wall time;
- final parent/child/process and cgroup peak memory;
- final CPU and swap/memory-event accounting;
- final output file count and byte size;
- final file-open audit row/open totals;
- final post-run source comparison time;
- final full-six summary/run-log/timing SHA-256 values.

## State-preload measurement boundary

The sealed A state contains 26 files and 4,141,835,394 bytes. This is an
immutable analytical-state measurement only. The state may not be copied into
the runtime package or used for cold-start performance claims until persistent
v9 reaches terminal acceptance and the real copied-state validator passes.

Cold preload validation time, cold service-start time, recovery restart time,
endpoint latency, gateway payload size, deployed browser memory, and externally
served response latency remain **PENDING**.

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
equivalence rebuild fits the live service envelope. Even before the eight
alternate v9 schedules complete, clean B has peaked at 7,153,156 KiB and the
original-source incremental A at 6,481,416 KiB. Longer historical validation
should remain an offline bounded job with a separately measured resource
envelope. This assessment must be revisited after terminal v9 and deployment
measurements are available.

## Historical and excluded measurements

- The pre-repair `81b0836` terminal full-six run took 49,456.697 harness
  seconds / 13:46:33 wall, peaked at 19,259,224 KiB process RSS and
  25,770,590,208 bytes at cgroup scope, and produced about 16.60 GB. Those
  values are historical only and do not establish post-repair performance.
- Its per-schedule timings and bundle hashes likewise remain historical and
  must not fill the pending v9 table.
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
