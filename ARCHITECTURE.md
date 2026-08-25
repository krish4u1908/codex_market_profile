# Architecture

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
