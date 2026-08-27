# R6E1R Performance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

## Current-source local measurements

| Workload | Result | Elapsed | Peak RSS | Standing |
|---|---|---:|---:|---|
| Ingestion suite | 127 passed | 7.51 s | Not recorded | Current local functional evidence |
| Orchestrator suite | 111 passed | 19.98 s | Not recorded | Current local functional evidence |
| Equivalence harness | 32 passed, 3 ptrace/strace failures | 6.64 s | Not recorded | Host rerun required |
| Deployment package, gateway security, and runner | 130 passed, 2 user-systemd-bus failures | 42.79 s | Not recorded | Host rerun required |
| Pre-final-repair selected functional baseline | 416 passed; 5 host-only tests deliberately deselected | 76.92 s | Not recorded | Historical local baseline only |
| Stabilized full non-browser collection | 545 passed, 20 skipped, 13 failed, 16 errors | 79.30 s | Not recorded | All 29 failures/errors and 20 skips require host facilities or sealed references; Hostinger rerun required |

These timings describe test execution, not raw-data equivalence throughput. No current-source full six-session elapsed time, peak parent/child RSS, output size, or filesystem-usage measurement has yet been accepted.

## Required final measurements

| Workload | Elapsed | Peak parent RSS | Peak child RSS | Output/filesystem size | Standing |
|---|---:|---:|---:|---:|---|
| Focused August 19 all-nine schedules using current seals | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Pending |
| Auxiliary uploaded August 20 diagnostic, pre-fix seal | Large chunks: 700.086 s; original chunks: 478.448 s | Large schedule: 1,132,316 KiB; original schedule: 1,198,476 KiB | Not separately recorded | Combined retained output/log footprint about 1.4 GiB | Failed ledger identity by +12 lifecycle/+24 cross-layer rows; exposed and drove the terminal-group publication repair; not acceptance |
| Auxiliary uploaded August 20 sample using current seals | `PENDING_HOSTINGER_RERUN` | `PENDING_HOSTINGER_RERUN` | `PENDING_HOSTINGER_RERUN` | `PENDING_HOSTINGER_RERUN` | Auxiliary proof of the repair only; cannot replace canonical acceptance |
| Six-session original chunks | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Pending |
| Six-session one-record schedule | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Pending |
| Complete six-session all-nine schedule set | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Pending |
| Largest sanitized public chart response | `PENDING_HOSTINGER_EVIDENCE` | — | — | Must remain below the 8 MiB per-response gateway cap | Pending |

Each accepted host run must record its exact command, source and seal hashes, `/usr/bin/time -v` output, child-process resource measurement, output-tree size, and clean input/output roots. A killed run, an older-seal run, or a comparator-invalid run remains diagnostic only.

## Historical measurements

The following measurements predate the current sealed runtime/package. They explain prior design work but are not current performance acceptance evidence:

| Historical run | Outcome | Elapsed | Peak RSS | Notes |
|---|---|---:|---:|---|
| Inherited focused incremental baseline | Interrupted after defect confirmation | 8m56.43s | 343,064 KiB | Rebuilt the full dirty session per poll; output reached 2,862,368 KiB before interruption |
| Focused A/B v2 | Repair required | 3m11.34s | 1,063,876 KiB | Core analytics matched; legacy batch omitted Intraday fallback rows |
| Focused A/B v4 | Rehearsal only | 3m49.54s | 1,113,236 KiB | Running process contained a pre-edit GUI comparator |
| Focused A/B v8 | Diagnostic only | 3m58.44s | Parent 1,121,076 KiB; child 696,360 KiB | Later audit rejected this comparator as final evidence |
| Authoritative sample-source rehash | Passed | 1.08s | 3,712 KiB | Eight source identities remained unchanged |
| Source-hour-preserving sample build/integrity check | Passed | 9.91s | 434,972 KiB | Eight hourly collector paths; manifest `31077f42...`; 46,550/46,550 identities |
| Frozen reference-manifest verification | Passed | 0.96s | 18,668 KiB | R6C2R 74/74 and R6D 40/40 package files |
| Correctly provisioned prior complete regression | Passed | 62.29s | 663,256 KiB | 289 passed, zero failed, zero skipped at that checkpoint |
| Accepted focused all-nine v12 | Passed | 22m09.73s | Parent 1,586,204 KiB; child 803,968 KiB | 21/21 components, 8/8 ledgers, 9/9 schedules, all invariant/open/source gates zero |
| Full-six v6 before interruption | Rejected diagnostic | 1h22m19s | 12,992,404 KiB | Baselines/references exact; one-record harness visibility defect produced 1,796 refusal rows, so no value is promoted |
| Causal-backlog targeted gate | Passed | 14.60s wall | 137,536 KiB | 116/116 ingestion, orchestrator, and equivalence-harness tests |

The historical focused v12 accepted-output size was 465,846,934 bytes and its retained work root was 33,365,301 bytes. Its summary, state-manifest, and state-tree hashes belong only to that historical run and must not be presented as current-seal evidence.

## Scaling design and pending conclusion

The implementation reads raw files in bounded chunks, caches discovery and source identities, source-hash caches fixed context, excludes the evaluation session from fixed context, compacts finalized raw buckets after durable publication, retains protected replay outputs independently of the rolling live window, and tail-limits browser responses. These are design properties, not a measured guarantee.

The committed but uninstalled backend unit uses `MemoryHigh=8G` and `MemoryMax=10G`. Hostinger must compare those limits with current-seal focused and six-session peaks before installation.

`20-30 session extension assessment: PENDING_HOSTINGER_PERFORMANCE_EVIDENCE`
