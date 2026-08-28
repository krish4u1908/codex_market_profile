# R6E1R Callback Wiring Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR REGRESSION AND FOCUSED PATH PASS; FRESH SIX-SESSION V9 BASELINE/REFERENCES PASS; TERMINAL SCHEDULE SUITE AND DEPLOYMENT PENDING**

Evidence lineage:

- Branch snapshot at this refresh: `612d3ebb8fad818386f4b2a6a9b6f519ac837ada`.
- Repair commit exercised by current evidence: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.
- Engine aggregate: `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947`.
- Engine manifest SHA-256: `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210`.
- Runtime-config identity: `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41`.

## Production path

The implemented repository-owned path is:

`raw JSONL -> strict normalization -> canonical symbol registry -> durable observation stage -> registered analytical callback -> explicit refresh/finalize -> causal synchronization -> inventory -> divergence -> dependency -> lifecycle/resolution -> participation/views -> cross-layer transitions -> GUI projection -> append-only ledgers`

The ingestor registers the orchestrator as its callback. Polling owns ingestion
and callback delivery; a caller does not manually double-process returned
observations. `run_r6e_shadow.py` consumes committed observations, flushes
analytical work at the defined boundaries, persists results, and exposes only
sealed current state to read-only API consumers.

## Durability contract

- Complete JSONL lines are checkpointed; a partial final line remains deferred.
- Normalized observations are staged before the source checkpoint can make raw
  bytes unreachable.
- An observation is acknowledged only after callback processing and durable
  analytical staging succeed.
- A callback exception leaves durable replay state for restart.
- Deterministic observation and analytical event IDs provide replay
  deduplication; repeated IDs are accepted only for identical immutable content.
- Ambiguous post-fsync failures reconcile only the exact attempted suffix;
  replacement, truncation, partial, or concurrent tails fail closed.
- Normalized, refusal, checkpoint, material, staged-observation, and SQLite
  authorities validate their complete schemas before deduplication.
- A JSON mirror cannot bootstrap missing or rolled-back SQLite checkpoint
  authority.
- Raw polls stage observations without rebuilding dirty multi-gigabyte history.
  Analytical rebuild occurs only at refresh, snapshot, finalize, or a session
  boundary.
- Read-only API calls consume sealed output and do not trigger analytics.

## Canonical input and clock contract

- The exact Index identity is `NSE:NIFTYBANK-INDEX`.
- Futures and option expiries are discovered through repository-owned contract
  selection; they are not hard-coded by the runtime.
- Receipt, event/exchange, effective, and publication timestamps remain
  distinct, timezone-aware, and normalized to `Asia/Kolkata` without rounding.
- Synchronized basis uses a backward Index as-of match from 0 through exactly
  2,000 ms. Future joins are invalid.
- Frozen BN-reference inventory uses its separate backward Index as-of tolerance
  through 5,000 ms.
- Evidence clocks are never replaced with calculation, snapshot, or display
  timestamps.
- Price, cumulative volume, OI, previous OI, delta OI, strike, expiry, option
  type, bid/ask, source stream, raw file, byte offset, and source row remain in
  the normalized envelope when present.

### Empty-Index aware-clock repair

Commit `e1d67c534bea5c61b0e3d379db7f599de7e1c445` repairs the
no-eligible-Index branch of `raw_io.reader.backward_join`. That branch now
constructs `matched_price_timestamp` as an all-missing Series with the same
timezone-aware dtype as `availability_timestamp`, instead of using a generic
timezone-naive `pd.NaT`. It also refuses a naive availability clock before any
join. The two new regression fixtures prove that an empty Index produces an
unmatched aware clock and that naive input fails closed.

This is a type-safety and refusal repair only. It does not change backward
matching, either tolerance, synchronization ordering, future-join handling,
inventory coordinates, detector persistence, lifecycle precedence, thresholds,
colours, or evidence clocks.

## Fixed context and incremental work

The fixed 1D/2D/3D context reader uses predecessor raw bytes, excludes the
current evaluation session, and caches source identities. Finalized session
observation buckets are compacted after durable publication while canonical
outputs and deterministic stage identities remain restart-safe. This prevents
each raw poll from rescanning multi-gigabyte history and keeps dense artifacts
out of browser memory.

## Current post-repair evidence

| Evidence | Recorded result | Standing |
|---|---|---|
| Complete repository regression | 660 passed, 0 failed, 0 skipped; 118.03 s; peak RSS 671,340 KiB | PASS |
| Clean August 19 focused callback path | 21/21 components, 8/8 ledgers, 9/9 causality groups, 9/9 focused schedules, 16/16 storage rows, 72/72 checkpoints, 2/2 recovery, 8/8 sources | PASS |
| Focused zero gates | Future joins, backdating, duplicate IDs, analytical refusals, prohibited/unmeasured runtime opens, and source mutations all zero | PASS |
| Fresh v9 raw projection | 141 authoritative sources, 139 projection files, 746,890 byte-exact records; malformed candidates and source mutations zero; August 17 present only for canonical rejection | PASS |
| Fresh v9 original-chunk incremental A | 543,329 JSON records from 104 evaluation-source files; clean seal; checkpoint failures/refusals/future joins/backdating/duplicate IDs/remainders all zero | PASS |
| Fresh v9 independent clean batch B | Independent chronological batch over the same selected raw bytes; three child commands returned zero | PASS |
| Fresh v9 A/B components | 21/21 exact component rows | PASS |
| Fresh v9 append-only ledgers | 8/8 exact identity/content rows | PASS |
| Fresh v9 causality | 9/9 invariants | PASS |
| Frozen analytical reference | R6C2R 30/30 rows; manifest 74/74 | PASS |
| Frozen GUI reference | R6D 180/180 rows; exactly 174,080 permitted live-extension rows; manifest 40/40 | PASS |
| Remaining eight six-session schedules and terminal summary | No terminal v9 schedule bundle promoted yet | PENDING |
| Installed services, browser capture, and public-interface verification | Not current post-repair evidence | PENDING |

The focused summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
The focused run exercised 2,508 file-open audit rows, of which 2,499 were
runtime rows representing 1,190,240 opens; prohibited and unmeasured opens were
zero. Its elapsed time was 3,839.101 seconds; parent and child peak RSS were
1,730,828 and 891,172 KiB.

The immutable v9 incremental-A and clean-B seal SHA-256 values are
`fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7`
and `99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568`.
Their common analytical-ledger aggregate is
`4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65`.
The exact artifact and reference counts are recorded in
[R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md](R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md).

## Remaining acceptance boundary

The fresh v9 baseline/reference result is necessary but not sufficient for
terminal R6E1R equivalence. The one-record, deterministic-variable,
inside-JSONL-line, empty/repeated-poll, multiple-checkpoint-restart,
analytical-transition-restart, hourly-rotation, and large-chronological-chunk
schedules must each publish their immutable result, after which the final
schedule, checkpoint, storage, recovery, source, and summary matrices must pass.
Deployment and browser acceptance remain separately pending. No verified tag is
authorized from the baseline/reference slice alone.

## Historical diagnostics retained as historical

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` evidence is
pre-repair historical evidence and is not used as the current acceptance
identity. Earlier focused merged-v2/full-six-v1 clean-GUI compaction failures,
v6 checkpoint-lag visibility/refusal failures, and interrupted v2-v8 attempts
remain rejected diagnostics. Their repairs preserved the frozen analytical and
timestamp contracts; no rejected or pre-repair terminal schedule count is
substituted for fresh v9 evidence.

The detailed stage ownership is in
[R6E1R_CALLBACK_WIRING_MATRIX.md](R6E1R_CALLBACK_WIRING_MATRIX.md).
