# R6E1R Callback Wiring Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED PRODUCTION PATH VERIFIED; FINAL SIX-SESSION EVIDENCE PENDING**

## Production path

The implemented path is:

`raw JSONL -> strict normalization -> canonical symbol registry -> durable observation stage -> registered analytical callback -> explicit refresh/finalize -> causal synchronization -> inventory -> divergence -> dependency -> lifecycle/resolution -> participation/views -> cross-layer transitions -> GUI projection -> append-only ledgers`

The ingestor registers the orchestrator as its callback. Polling owns ingestion and callback delivery; callers do not manually pass returned observations into analytics.

## Durability contract

- Complete JSONL lines are checkpointed; partial final lines remain deferred.
- Normalized observations are staged durably before a source checkpoint can make their bytes unreachable.
- Callback acknowledgement occurs only after the callback returns successfully and durable analytical staging has succeeded.
- A callback exception leaves the observation in the durable outbox for replay after restart.
- Deterministic observation and analytical event IDs provide replay deduplication.
- Ambiguous failures after a durable ledger append reconcile the existing identity before retry.
- Raw polls stage observations without rebuilding a dirty multi-gigabyte session. Analytical rebuild occurs only at an explicit refresh, snapshot, finalize, or session boundary.
- Read-only API requests use sealed output and do not trigger analytics.

## Canonical input and clock contract

- The exact Index identity is `NSE:NIFTYBANK-INDEX`.
- Futures are selected by repository-owned session contract discovery; no session contract is hard-coded in the runtime template.
- Receipt, event/exchange, effective, and publication timestamps remain distinct and timezone-aware in `Asia/Kolkata`.
- Synchronized basis uses a backward Index as-of match from 0 through exactly 2,000 ms. A future Index join is invalid.
- Frozen BN-reference inventory uses its separate backward Index as-of tolerance through 5,000 ms. A real 3-4 second fixture proves inventory remains eligible while synchronized basis remains unmatched beyond exactly 2,000 ms.
- Evidence timestamps are not replaced by display or snapshot timestamps.
- Price, volume, OI, previous OI, delta OI, strike, expiry, option type, bid/ask, source stream, file, byte offset, and source row remain in the normalized envelope when present.

## Fixed context and incremental work

The fixed 1D/2D/3D context reader uses predecessor raw bytes, excludes the current evaluation session, caches source identities, and avoids hashing or rebuilding unchanged history on every poll. Finalized session observation buckets are compacted after durable publication while output and deterministic stage identities remain restart-safe.

## Verified targeted evidence

| Evidence | Recorded result | Final standing |
|---|---|---|
| Pre-write, post-fsync, partial multi-session, publication exception, continuation, and runner coverage | Repaired-engine targeted set recorded 216/216 passed | Current targeted evidence; complete repository regression pending |
| Production callback registration | Covered by ingestor/orchestrator integration tests | Implemented |
| API reads do not flush analytics | Covered by live API/state tests | Implemented |
| One-record unresolved Futures candidate | Earlier probe exposed 668 refusals | Repaired; focused v12 exercised all nine schedules with zero analytical refusals |
| Current-source focused callback path | 21/21 components, 8/8 ledgers, 9/9 schedules, 9/9 invariants, 2/2 recovery probes | PASS — focused v12 |
| Fresh six-session production callback path | Every required schedule and canonical artifact | `PENDING_FINAL_EVIDENCE` |
| Current-source complete regression | `PENDING_FINAL_EVIDENCE` | Pending |

The detailed stage ownership and evidence requirements are in [R6E1R_CALLBACK_WIRING_MATRIX.md](R6E1R_CALLBACK_WIRING_MATRIX.md).

The accepted focused run is bound to pushed repair commits `71a868f1339773df06d0932dd72a3c908caa1028` and `02594dc222afeff5135ac0404dd24211d09f425f`, engine manifest SHA-256 `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3`, and engine hash `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`.
