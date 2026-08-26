# R6E1R Callback-Wiring Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED V12 VERIFIED; FINAL SIX-SESSION SEALED-RUN EVIDENCE PENDING**

| Stage | Repository-owned entry point | Required input/output contract | Draft evidence | Final evidence |
|---|---|---|---|---|
| File discovery | `IncrementalJSONLIngestor.discover` | Bounded cached discovery; detects session/hour rotation | Unit coverage recorded | PASS — focused v12 all-nine plus 216/216 targeted; full six pending |
| Complete-line ingestion | `IncrementalJSONLIngestor.poll` / `_read_file` | Commit complete JSONL only; defer tail; preserve byte/row coordinates | Targeted ingestion coverage recorded | PASS — focused v12 all-nine plus 216/216 targeted; full six pending |
| Symbol classification | `SymbolRegistry` | Exact `NSE:NIFTYBANK-INDEX`; repository-selected Futures; CE/PE grammar | Unit coverage recorded | PASS — focused v12 plus targeted fixtures; full six pending |
| Lossless normalization | `_normalize_record` / `TypedObservation` | Preserve clocks, price/volume/OI lineage, strike/expiry/type, quotes, raw coordinates | Field-preservation fixtures recorded | PASS — focused v12 plus targeted fixtures; full six pending |
| Durable raw staging | SQLite outbox plus normalized event ledger | Stage before checkpoint makes bytes unreachable | Exception/restart tests recorded | PASS — focused v12 recovery probes plus targeted failure injection; full six pending |
| Futures selection barrier | Candidate outbox and receipt watermark | Hold equal/later publication until canonical depth selection | Repair and restart fixture present | PASS — focused v12 zero refusals plus targeted restart fixtures; full six pending |
| Registered callback | `register_callback(orchestrator)` | Production poll invokes batch callback; no manual double processing | Integration coverage recorded | PASS — focused production callback path; full six pending |
| Durable analytical stage | `LiveAnalyticalOrchestrator.process_observations` | Durable append before acknowledgement; retry-safe per session | Failure-injection coverage recorded | PASS — seven nonempty material-ledger boundaries exactly once; full six pending |
| Fixed context | Orchestrator fixed-context loader/cache | Raw predecessor chain; current session excluded; source-hash cached | Targeted context tests recorded | PASS — targeted and focused evidence; full predecessor-chain gate pending |
| Causal synchronization | `_divergence` / canonical `causal_basis` | Backward Index as-of, inclusive 0-2,000 ms, no future join | Unit/reference coverage recorded | PASS — focused v12 zero future/tolerance violations; full six pending |
| Inventory | `_inventory` | BN-reference Price and OI VPOC; frozen backward as-of through 5,000 ms; fixed plus Intraday | Focused fallback comparison recorded | PASS — focused Intraday equality and real 3-4s inventory fixture; frozen-count full six pending |
| Divergence detector | `_divergence` | Frozen detector and confirmation clock; exact 0-2,000 ms synchronized basis | Unit/reference coverage recorded | PASS — focused exact A/B plus targeted fixtures; full six pending |
| Dependency grouping | `_compute_session` dependency stage | Groups/retriggers without threshold changes | Reference comparison exists | PASS — focused exact A/B; full frozen counts pending |
| Lifecycle/resolution | `_compute_session` lifecycle stage | Frozen precedence and evidence clocks | Reference comparison exists | PASS — focused exact A/B; full frozen counts pending |
| Participation | `_participation` | Futures/CE/PE constituent clocks and frozen strike/window rules | Unit/reference coverage recorded | PASS — focused exact A/B plus targeted fixtures; full six pending |
| Four views | `_build_participation_views` | Dense, transitions, summaries, compatibility | Reference comparison exists | PASS — focused exact A/B; full frozen counts pending |
| Cross-layer state | Cross-layer material transition builder | Deterministic canonical transitions with restart-safe continuation context | Focused Intraday fallback matched diagnostically | PASS — focused exact A/B and transactional continuation tests; full 60,659-row gate pending |
| Availability | `_availability` / `operational_availability` | Per-layer degradation; live wall-clock staleness; replay-safe sealed state | Operational/API tests recorded | PASS — focused operational equality; reference comparator 29/29; full six pending |
| GUI projection | `_gui` | Calculation-free public payload with classification | Browser/API tests recorded | PASS — focused GUI equality and 135/135 parity suite; deployed live pending |
| Append-only publication | `_publish`, `_append_once`, `_publish_availability` | Deterministic exactly-once IDs; reconcile ambiguous durable append | Ledger-generic failure tests recorded | PASS — 8/8 focused ledgers and seven nonempty crash boundaries; full six pending |
| Explicit refresh/finalize | `refresh_dirty`, `finalize_session`, runner interval | No rebuild on raw/API poll; bounded analytical refresh | State/API tests recorded | PASS — focused and targeted runner evidence; full six pending |
| State/restart | Orchestrator state plus checkpoint/ledger stores | Restore dirty stage, outputs, identities, replay set | Restart/retention tests recorded | PASS — focused 2/2 recovery plus targeted persistence failures; full six pending |

Final acceptance requires every callback invocation key in each applicable focused fixture and exact A/B artifact equality; a non-qualifying divergence in the small sample does not waive unit exercise of the detector, dependency, lifecycle, participation, cross-layer, or GUI path.

Accepted focused identity: engine manifest SHA-256 `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3`, engine hash `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`, focused summary SHA-256 `19b6c15f426b925fa6ec018d65477f4364242d65cfaaa5425423098d3861de15`.

Fresh six-session sealed callback matrix: `PENDING_FINAL_EVIDENCE`.
