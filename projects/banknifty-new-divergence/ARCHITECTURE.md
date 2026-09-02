# Architecture

## New Divergence V1

The new path is an additive boundary under
`src/banknifty_profiler/new_divergence`. `ReplayAdapter` and `LiveAdapter`
normalize into the same `MarketEvent` contract. `CausalDivergenceEngine` owns
backward synchronization, frozen basis classification, and episode lifecycle.
`TransitionLedger` seals every publication in an append-only hash chain.

Outcome measurement imports engine outputs, but the engine does not import the
outcome module. Browser assets project completed runs and perform no inference.
The full contract is in `docs/NEW_DIVERGENCE_CONTRACT.md`.

`new_divergence.nightly_context` is a separate completed-session boundary. It
reads the collector tree without writing to it, stores immutable per-session
profile revisions and composable weighted bins in SQLite, and atomically
publishes versioned 1D/2D/3D JSON bundles. It cannot mutate the intraday engine
configuration or select divergence thresholds.

`new_divergence.cash_samples` is another isolated completed-file boundary. It
derives exactly two 09:45+ parameters from the collector's one-minute cash
rows, publishes them atomically into `RUN_ROOT/YYYY-MM-DD`, and never imports
or invokes `CausalDivergenceEngine`. A sample-only date may later be promoted
by replay in the same directory; the two hashed files are preserved while the
verified engine bundle is atomically exposed.

## Recovered R6D baseline

The package is deliberately layered:

1. `raw_io` parses receipt-timed external collector records.
2. `synchronization` owns causal backward matching; no future join is permitted.
3. `inventory` maintains canonical `CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN` controls.
4. `divergence` detects frozen synchronized Index/Futures basis episodes.
5. `lifecycle` applies standalone Index response clocks and synchronized-basis resolution clocks.
6. `participation` contains verified descriptive participation primitives; it is not a trade gate.

Runtime and API implementations are intentionally absent because no verified production implementation was authorized. Dense observations, transition ledger, episode summaries, and replay snapshots are distinct publication views.

R6C0 makes the analytical runtime repository-native. Raw market data enters
only through an explicit caller-provided data root and output persistence only
through an explicit output root. Divergence and inventory-context modules are
pure over caller-supplied records and contain no historical research path.

Canonical Price VPOC: `BN_REF_FUT_VOLUME_VPOC` (user label: **BN-REF FUT VOL-VPOC**). Legacy Futures-coordinate VPOC is diagnostic-only and disabled by default.
# R6C0I raw inventory boundary

`banknifty_profiler.raw_io.reader` owns repository-native raw parsing, expiry classification, backward causal joins, and moneyness. `banknifty_profiler.inventory.engine` owns continuity-based session discovery, chronological source chains, BN-reference Futures-volume VPOC, signed Futures/CE/PE OI-VPOCs, deterministic tie-breaking, fixed publication clocks, and causal intraday winner transitions. Runtime roots and configuration are mandatory CLI inputs.
# R6C0T portable participation runtime

The production participation processor now owns the complete raw causal path: synchronization, divergence, dependency grouping, lifecycle, typed in-run episode anchors, strike-level participation, and four canonical views. Data/output/config roots are explicit CLI arguments. Historical reconciliation utilities live under `tools/historical_audit/` and are not imported by production runtime.
