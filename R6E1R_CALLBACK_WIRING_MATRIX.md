# R6E1R Callback-Wiring Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

## Terminal disposition

The v9 verifier did not reach terminal all-nine publication. During the
operator stop, the runtime mask was applied at `20:39:00.999`; systemd then
recorded a client-requested `SIGINT` at `20:39:01` and a client-requested
`SIGTERM` at `20:39:06`. This was not an OOM or swap event: no OOM kill was
recorded, swap use was zero, and the observed peak was 14.5 GiB. The v9
evidence, work, and control roots were externally deleted after the operator
stop. A post-stop
search found zero surviving alternate-schedule bundles, no bundle marker, and
no terminal all-gates summary.

The v9 hashes and counts retained below are independently observed and pushed
baseline/reference observations. They are not surviving, independently
revalidatable final all-nine artifacts and do not support a final six-session
equivalence claim. A fresh full-six run requires an explicit uninterrupted
root-agreed window; it must not evade or work around an active root operator.
Deployment was not performed and the verified tag was not created.

Evidence lineage:

- Branch snapshot at this refresh: `612d3ebb8fad818386f4b2a6a9b6f519ac837ada`.
- Analytical repair under test: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.
- Fresh focused summary SHA-256: `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
- Fresh six-session v9 invocation: `ce9595fd18b344ab8ab2765ae509f8fa`.

| Stage | Repository-owned entry point | Required input/output contract | Current post-repair evidence | Remaining final gate |
|---|---|---|---|---|
| File discovery | `IncrementalJSONLIngestor.discover` | Bounded cached discovery; detects session/hour rotation | Focused hourly rotation 6/6; regression PASS | Full-six rotation proof blocked; no surviving v9 bundle |
| Complete-line ingestion | `IncrementalJSONLIngestor.poll` / `_read_file` | Commit complete JSONL only; defer tail; preserve byte/row coordinates | Focused 9/9 schedules and 72/72 checkpoint rows; regression PASS | Full-six inside-line/poll/restart proof blocked |
| Symbol classification | `SymbolRegistry` | Exact `NSE:NIFTYBANK-INDEX`; repository-selected Futures; CE/PE grammar | Focused PASS; v9 projection selection was observed | Terminal suite blocked; v9 roots deleted |
| Lossless normalization | `_normalize_record` / `TypedObservation` | Preserve clocks, price/volume/OI lineage, strike/expiry/type, quotes, and raw coordinates | Focused field comparison PASS; byte-exact v9 projection was observed | Terminal suite blocked; no surviving bundle |
| Durable raw staging | Authenticated SQLite outbox plus normalized event ledger | Full schema/content binding and monotonic source coverage; missing or rolled-back authority fails closed | Regression 660/660; focused 2/2 recovery probes | Six-session restart/storage proof blocked |
| Futures selection barrier | Candidate outbox and receipt watermark | Hold equal/later publication until canonical depth selection | Focused analytical refusals zero; regression barrier/restart tests PASS | Full-six one-record proof blocked |
| Registered callback | `register_callback(orchestrator)` | Production poll invokes batch callback; no manual double processing | Focused production path PASS; v9 incremental-A execution was observed | Remaining full-six schedules blocked |
| Durable analytical stage | `LiveAnalyticalOrchestrator.process_observations` | Retained append intent; reconcile before seen-ID; acknowledge only after accepted durable staging | Focused 8/8 ledgers and 2/2 recovery; v9 A/B 8/8 was observed | Transition-restart proof blocked |
| Fixed context | Fixed-context loader/cache | Raw predecessor chain; current session excluded; source-hash cached | Observed v9 baseline/reference PASS across six evaluation and eight causal-source sessions; August 17 not forced accepted | Schedule/restart invariance blocked |
| Causal synchronization | `_divergence` / canonical `causal_basis` | Backward Index as-of, inclusive 0-2,000 ms; no future join | Focused 13,781 rows; v9 A=B at 158,746 rows was observed | Terminal matrix blocked |
| Empty-Index matching | `raw_io.reader.backward_join` | An absent Index row yields an unmatched aware clock; naive availability clocks fail closed | Repair `e1d67c5` uses an aware `NaT` series with the availability-clock dtype; two regression fixtures PASS | No frozen-rule change; terminal suite blocked |
| Inventory | `_inventory` | `CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN`; BN-reference Price/OI VPOC; separate backward as-of tolerance through 5,000 ms | Focused 25 Intraday rows; v9 255 canonical plus fallback counts were observed | Terminal matrix blocked |
| Divergence detector | `_divergence` | Frozen detector, thresholds, colours, and confirmation clock | Focused 4 episodes; v9 65 episodes (41 GREEN, 24 RED) were observed | Terminal matrix blocked |
| Dependency grouping | `_compute_session` dependency stage | Groups/retriggers without threshold changes | Focused 4 groups/1 retrigger; v9 65 groups/14 retriggers were observed | Terminal matrix blocked |
| Lifecycle/resolution | `_compute_session` lifecycle stage | Frozen precedence and evidence clocks | Focused 1,299 lifecycle/11,486 dense rows; v9 14,201/164,668 was observed | Transition-restart proof blocked |
| Participation | `_participation` | Futures/CE/PE constituent clocks and frozen strike/window rules | Focused 4,500 dense rows; v9 69,225 dense rows was observed | Terminal schedules blocked |
| Four views | `_build_participation_views` | Dense, transitions, summaries, compatibility | Focused 2,221 transitions and 4 summaries/snapshots; v9 32,068/65/65 was observed | Terminal schedules blocked |
| Cross-layer state | Cross-layer transition builder | Deterministic transitions with restart-safe continuation context | Focused 4,818 canonical plus 25 fallback rows; v9 60,659 canonical plus 139 fallback rows was observed | Transition-restart proof blocked |
| Availability | `_availability` / `operational_availability` | Per-layer degradation; live wall-clock staleness; replay-safe sealed state | Focused 4 states; v9 24 states was observed | Live deployment not performed |
| GUI projection | `_gui` | Calculation-free public payload with classification | Regression PASS; v9/R6D 180/180 was observed | Browser/deployed-live acceptance not performed |
| Append-only publication | `_publish`, `_append_once`, `_publish_availability` | Deterministic IDs; identical-content replay only; bounded exact-prefix recovery | Focused 8/8; v9 8/8 aggregate was observed | Full-six restart proof blocked |
| Explicit refresh/finalize | `refresh_dirty`, `finalize_session`, runner interval | No rebuild on raw/API poll; bounded analytical refresh | Regression/focused PASS; v9 original-chunk baseline seal was observed | Remaining schedules blocked |
| State/restart | Orchestrator state plus checkpoint/ledger stores | Strict session/output/context/finalization coherence; persisted rows content-match durable stage | Focused 2/2 recovery, 16/16 storage rows, and 40/40 artifacts | Full-six restart/preload proof blocked |

## Current accepted evidence

The post-repair regression passed 660/660 with zero failures or skips in
118.03 seconds; peak RSS was 671,340 KiB. The clean focused run against
`e1d67c534bea5c61b0e3d379db7f599de7e1c445` passed 21/21 component rows,
8/8 analytical ledgers, 9/9 causality groups, 9/9 focused schedules, 16/16
storage rows, 72/72 checkpoint rows, 2/2 recovery probes, and 8/8 sources.
Every focused comparison, refusal, future-join, backdating, duplicate-ID,
runtime-open, and source-mutation counter was zero.

The repair is representational and fail-closed. When the Index frame has no
eligible row, `backward_join` now creates `matched_price_timestamp` as an aware
`NaT` series using the timezone-aware availability-clock dtype. It also refuses
a naive availability clock before joining. The frozen backward direction,
0-2,000 ms synchronized-basis window, separate inventory tolerance, future-join
prohibition, detector thresholds, and evidence clocks were not changed.

Before deletion, the fresh v9 original-source-chunk incremental A and
independently clean batch B were observed sealed. Their component matrix passed 21/21, ledger matrix
8/8, and causality matrix 9/9. Both also matched the verified R6C2R analytical
reference 30/30 and the R6D GUI reference 180/180, with no unexplained
remainder. The A and B seal SHA-256 values are
`fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7`
and `99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568`.

This retained baseline/reference observation does **not** close the final
six-session gate. No alternate-schedule marker or terminal v9 acceptance
summary survived the operator stop and root deletion. Deployment and browser
acceptance were not performed, and the verified tag was not created.

## Historical evidence retained as historical

The earlier accepted `81b0836fe50939246ae210bb62780ac4e163e100` run is a
pre-repair historical result and is not current acceptance evidence. Historical
focused merged-v2/full-six-v1 GUI-compaction failures and v6 one-record
visibility/refusal failures remain rejected diagnostics. Their repairs did not
change frozen analytical or timestamp semantics, and none of their counts is
promoted into a current terminal schedule result.
