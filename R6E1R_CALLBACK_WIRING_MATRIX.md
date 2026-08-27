# R6E1R Callback-Wiring Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT REGRESSION 636/636; FOCUSED-V3/FULL-SIX-V2 RESULTS PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

| Stage | Repository-owned entry point | Required input/output contract | Draft evidence | Targeted/historical evidence; current final gate |
|---|---|---|---|---|
| File discovery | `IncrementalJSONLIngestor.discover` | Bounded cached discovery; detects session/hour rotation | Unit coverage recorded | HISTORICAL/TARGETED — focused v12 plus targeted coverage; current full six pending |
| Complete-line ingestion | `IncrementalJSONLIngestor.poll` / `_read_file` | Commit complete JSONL only; defer tail; preserve byte/row coordinates | Targeted ingestion coverage recorded | HISTORICAL/TARGETED — focused v12 plus targeted coverage; current full six pending |
| Symbol classification | `SymbolRegistry` | Exact `NSE:NIFTYBANK-INDEX`; repository-selected Futures; CE/PE grammar | Unit coverage recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Lossless normalization | `_normalize_record` / `TypedObservation` | Preserve clocks, price/volume/OI lineage, strike/expiry/type, quotes, raw coordinates | Field-preservation fixtures recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Durable raw staging | Authenticated SQLite outbox plus normalized event ledger | Full schema, column/payload/content binding; unbound legacy rows fail closed; neither a JSON mirror nor surviving append-only evidence can bootstrap missing/empty SQLite authority; every trusted source must retain monotonic row/offset/identity coverage | Exception/restart/tamper/forged-or-missing-mirror/partial-source/rollback tests recorded | TARGETED — ingestion 127/127 recorded; current focused/full-six results pending |
| Futures selection barrier | Candidate outbox and receipt watermark | Hold equal/later publication until canonical depth selection | Repair and restart fixture present | HISTORICAL/TARGETED — current focused/full-six results pending |
| Registered callback | `register_callback(orchestrator)` | Production poll invokes batch callback; no manual double processing | Integration coverage recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Durable analytical stage | `LiveAnalyticalOrchestrator.process_observations` | Retained generic append intent, reconcile before seen-ID, acknowledge only after accepted staging; unstable terminal-group rows remain provisional until causally immutable | Failure-injection coverage recorded | TARGETED — orchestrator 111/111 recorded; current focused/full-six results pending |
| Fixed context | Orchestrator fixed-context loader/cache | Raw predecessor chain; current session excluded; source-hash cached | Targeted context tests recorded | HISTORICAL/TARGETED — full predecessor-chain gate pending |
| Causal synchronization | `_divergence` / canonical `causal_basis` | Backward Index as-of, inclusive 0-2,000 ms, no future join | Unit/reference coverage recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Inventory | `_inventory` | BN-reference Price and OI VPOC; frozen backward as-of through 5,000 ms; fixed plus Intraday | Focused fallback comparison recorded | HISTORICAL/TARGETED — frozen-count full-six gate pending |
| Divergence detector | `_divergence` | Frozen detector and confirmation clock; exact 0-2,000 ms synchronized basis | Unit/reference coverage recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Dependency grouping | `_compute_session` dependency stage | Groups/retriggers without threshold changes | Reference comparison exists | HISTORICAL — current frozen-count gate pending |
| Lifecycle/resolution | `_compute_session` lifecycle stage | Frozen precedence and evidence clocks | Reference comparison exists | HISTORICAL — current frozen-count gate pending |
| Participation | `_participation` | Futures/CE/PE constituent clocks and frozen strike/window rules | Unit/reference coverage recorded | HISTORICAL/TARGETED — current focused/full-six results pending |
| Four views | `_build_participation_views` | Dense, transitions, summaries, compatibility | Reference comparison exists | HISTORICAL — current frozen-count gate pending |
| Cross-layer state | Cross-layer material transition builder | Deterministic canonical transitions with restart-safe continuation context | Focused Intraday fallback matched diagnostically | HISTORICAL/TARGETED — current 60,659-row gate pending |
| Availability | `_availability` / `operational_availability` | Per-layer degradation; live wall-clock staleness; replay-safe sealed state | Operational/API tests recorded | HISTORICAL/TARGETED — current full-six result pending |
| GUI projection | `_gui` | Calculation-free public payload with classification | Current complete regression and fixture-browser coverage | CURRENT SUITE/FIXTURE PASS — fresh A/B and deployed-live results pending |
| Append-only publication | `_publish`, `_append_once`, `_publish_availability` | Immutable event projection; deterministic IDs with same-content validation; bounded exact-prefix recovery | Post-review failure-injection tests recorded | TARGETED — current focused/full-six results pending |
| Explicit refresh/finalize | `refresh_dirty`, `finalize_session`, runner interval | No rebuild on raw/API poll; bounded analytical refresh; five measured intermediate refreshes in large schedule | State/API and schedule-predicate tests recorded | TARGETED — current focused/full-six results pending |
| State/restart | Orchestrator state plus checkpoint/ledger stores | Strict canonical sessions; exact output/context/finalization coherence; persisted rows content-match durable stage | Restart/retention/tamper tests recorded | TARGETED — current full-six result pending |

Final acceptance requires every callback invocation key in each applicable focused fixture and exact A/B artifact equality; a non-qualifying divergence in the small sample does not waive unit exercise of the detector, dependency, lifecycle, participation, cross-layer, or GUI path.

The current pushed repair commit passes the complete repository regression
636/636 with zero failures or skips. Focused merged-v2 then exposed a clean-B
GUI-only mismatch: 11,486 dense resolution observations were projected instead
of the live GUI's 1,294 material transitions. Focused merged-v2 and full-six-v1
were stopped and rejected. The `c42e703...` repair changes only the clean
comparator, was independently reviewed, and leaves frozen analytics and clocks
unchanged. Fresh focused-v3 and full-six-v2 have run from the pinned repair
commit since 2026-08-27 15:03:13 IST; their callback matrices remain pending.

Historical focused-v12 identity: engine manifest SHA-256 `7c13b44c...`, engine hash `980b6af2...`, focused summary SHA-256 `19b6c15f...`. It predates the current repair and is not acceptance evidence. Current engine manifest SHA-256 is `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`; current engine hash is `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`.

Current six-session sealed callback matrix: `PENDING_FINAL_EVIDENCE`.
