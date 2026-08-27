# R6E1R Callback-Wiring Matrix

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

| Stage | Repository-owned entry point | Required input/output contract | Draft evidence | Local/historical evidence; final Hostinger gate |
|---|---|---|---|---|
| File discovery | `IncrementalJSONLIngestor.discover` | Bounded cached discovery; detects session/hour rotation | Unit coverage recorded | PASS — focused v12 all-nine plus 216/216 targeted; full six pending |
| Complete-line ingestion | `IncrementalJSONLIngestor.poll` / `_read_file` | Commit complete JSONL only; defer tail; preserve byte/row coordinates | Targeted ingestion coverage recorded | PASS — focused v12 all-nine plus 216/216 targeted; full six pending |
| Symbol classification | `SymbolRegistry` | Exact `NSE:NIFTYBANK-INDEX`; repository-selected Futures; CE/PE grammar | Unit coverage recorded | PASS — focused v12 plus targeted fixtures; full six pending |
| Lossless normalization | `_normalize_record` / `TypedObservation` | Preserve clocks, price/volume/OI lineage, strike/expiry/type, quotes, raw coordinates | Field-preservation fixtures recorded | PASS — focused v12 plus targeted fixtures; full six pending |
| Durable raw staging | Authenticated SQLite outbox plus normalized event ledger | Full schema, column/payload/content binding; unbound legacy rows fail closed; neither a JSON mirror nor surviving append-only evidence can bootstrap missing/empty SQLite authority; every trusted source must retain monotonic row/offset/identity coverage | Exception/restart/tamper/forged-or-missing-mirror/partial-source/rollback tests recorded | PASS — current ingestion 127/127; Hostinger focused/full six pending |
| Futures selection barrier | Candidate outbox and receipt watermark | Hold equal/later publication until canonical depth selection | Repair and restart fixture present | PASS — focused v12 zero refusals plus targeted restart fixtures; full six pending |
| Registered callback | `register_callback(orchestrator)` | Production poll invokes batch callback; no manual double processing | Integration coverage recorded | PASS — focused production callback path; full six pending |
| Durable analytical stage | `LiveAnalyticalOrchestrator.process_observations` | Retained generic append intent, reconcile before seen-ID, acknowledge only after accepted staging; unstable terminal-group rows remain provisional until causally immutable | Failure-injection coverage recorded | PASS — current orchestrator 114/114; Hostinger full six pending |
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
| Append-only publication | `_publish`, `_append_once`, `_publish_availability` | Immutable event projection; deterministic IDs with same-content validation; bounded exact-prefix recovery | Post-review failure-injection tests recorded | PASS — targeted ambiguity/content/corruption tests; fresh focused/full-six pending |
| Explicit refresh/finalize | `refresh_dirty`, `finalize_session`, runner interval | No rebuild on raw/API poll; bounded analytical refresh; five measured intermediate refreshes in large schedule | State/API and schedule-predicate tests recorded | PASS — targeted periodic evolution fixtures; fresh focused/full-six pending |
| State/restart | Orchestrator state plus checkpoint/ledger stores | Strict canonical sessions; exact output/context/finalization coherence; persisted rows content-match durable stage | Restart/retention/tamper tests recorded | PASS — current local functional gate; Hostinger full six pending |

Final acceptance requires every callback invocation key in each applicable focused fixture and exact A/B artifact equality; a non-qualifying divergence in the small sample does not waive unit exercise of the detector, dependency, lifecycle, participation, cross-layer, or GUI path.

Historical focused-v12 identity: engine manifest SHA-256 `7c13b44c...`, engine hash `980b6af2...`, focused summary SHA-256 `19b6c15f...`. It predates the current repair and is not acceptance evidence. Current engine manifest SHA-256 is `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7`; current engine hash is `362474858eda75b18180ad2fce48e50e1d4acdd1b04a0db405eaae199e70b7a7`.

Fresh six-session sealed callback matrix: `PENDING_FINAL_EVIDENCE`.
