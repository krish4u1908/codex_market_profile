# R6E1R Callback Wiring Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT REGRESSION 636/636 — FOCUSED-V3/FULL-SIX-V2 RUNNING — EQUIVALENCE PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

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
- Ambiguous failures after a durable ledger append reconcile only the exact,
  complete attempted suffix before retry; replacement, truncation, partial or
  concurrent tails fail closed.
- Divergence-confirmation and lifecycle-entry ledgers contain immutable event
  fields. Episode-end and state-exit annotations remain in the latest snapshot
  but cannot make an earlier append-only event schedule-dependent.
- A repeated deterministic identity is accepted only when its immutable content
  is identical. Duplicate physical identities fail at startup.
- Normalized, refusal, checkpoint, material, staged-observation, and SQLite
  outbox authorities validate complete schemas before an identity enters a
  deduplication index. Same-ID changed content, column/payload mismatch,
  noncanonical sessions, and unbound legacy outboxes fail closed.
- Every source represented by trusted checkpoint or normalized-ledger evidence
  must retain a SQLite checkpoint that covers its row and byte frontier without
  changing identity. Total deletion, partial multi-source deletion, and
  same-source rollback fail closed; a replaceable JSON mirror is never trusted
  to create that authority.
- Generic append intents retain the exact declared batch through fsync and are
  acknowledged only after caller state accepts the committed identities. An
  interrupted same-process acknowledgement reconciles before seen-ID handling.
- Refusal identities are shared across ingestion and analytics, and persisted
  analytical sessions/outputs/cross-layer contexts are authenticated for exact
  key, session, stage, and finalization coherence on restart.
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

## Recorded targeted and historical evidence

| Evidence | Recorded result | Final standing |
|---|---|---|
| Pre-write, post-fsync, partial multi-session, publication exception, continuation, checkpoint-authority, unstable-terminal-group, and runner coverage | Ingestion 127/127; orchestrator 111/111; included in current 636/636 | CURRENT REGRESSION PASS; fresh A/B pending |
| Production callback registration | Covered by ingestor/orchestrator integration tests | Implemented |
| API reads do not flush analytics | Covered by live API/state tests | Implemented |
| One-record unresolved Futures candidate | Earlier probe exposed 668 refusals | Repaired; focused v12 exercised all nine schedules with zero analytical refusals |
| Historical focused callback path | Earlier v12 passed 21/21 components, 8/8 ledgers, 9/9 schedules, 9/9 invariants, 2/2 recovery probes | Superseded; focused-v3 running from current repair commit |
| Fresh six-session production callback path | Every required schedule and canonical artifact | Full-six-v2 running since 2026-08-27 15:03:13 IST; `PENDING_FINAL_EVIDENCE` |
| Current-source complete regression | 636 passed, 0 failed, 0 skipped in 129.36 s | CURRENT REGRESSION PASS; fresh equivalence and deployment pending |

Focused merged-v2 reached exact analytical components and all eight ledgers but
then exposed one clean-B GUI-comparator defect: clean B emitted 11,486 dense
resolution observations where live A emitted 1,294 material native-mechanism
transitions. Because full-six-v1 shared that comparator, both units were stopped
and rejected without promoting partial results. Commit `c42e703...` repairs only
the independent clean GUI builder, was independently reviewed, and does not
change the callback path, frozen analytical rules, clocks, IDs, dense artifacts,
or ledgers. Fresh focused-v3 and full-six-v2 are running from that pinned commit.

The detailed stage ownership and evidence requirements are in [R6E1R_CALLBACK_WIRING_MATRIX.md](R6E1R_CALLBACK_WIRING_MATRIX.md).

Focused v12 is retained as historical evidence bound to commits
`71a868f1339773df06d0932dd72a3c908caa1028` and
`02594dc222afeff5135ac0404dd24211d09f425f`. Current runtime identity is engine
manifest SHA-256
`715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`
and engine hash
`021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`;
it requires fresh focused-v3 and full-six-v2 runs on the pushed repair commit;
both units are currently running and their results remain pending.
