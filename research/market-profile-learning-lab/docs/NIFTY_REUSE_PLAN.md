# NIFTY Reuse Plan

## Reuse principle

Reuse the causal contracts and evaluation machinery; do not copy BankNifty
candidate weights or fixed point thresholds into NIFTY.

The current V0.1.2 release remains a frozen BankNifty implementation. A future
portable release should introduce an instrument adapter around a generic core.

## Generic core

The shared core owns:

- receipt-time parsing and backward causal synchronization;
- CE/PE/Futures-OI and index-reference Futures-volume contributions;
- positive/negative inventory families and control migrations;
- intraday and strictly prior 1D/2D/3D profile construction;
- episode consolidation, prefix snapshots, label separation, and hashes;
- candidate specification, deterministic forecasting, scoring, reporting,
  holdout sealing, and promotion gates;
- centralized commentary storage and GUI response schema.

## Instrument adapter

Each instrument supplies a versioned configuration or adapter for:

- `instrument_id` and exchange symbol classification;
- Index, Futures, CE, and PE symbol resolution;
- expiry-calendar and rollover resolution;
- strike interval, ATM rounding, and selected moneyness range;
- session calendar, market timezone, warm-up, and observation cadence;
- profile bin width, join freshness, merge window, and level tolerances;
- direction labels and horizons, preferably normalized before choosing points;
- optional constituent/cash-basket availability;
- data-quality requirements and missing-feature policy.

No adapter may hard-code individual session dates or require future knowledge
of an expiry.

## Separate BankNifty and NIFTY experiments

BankNifty and NIFTY must have different:

- dataset manifests and source hashes;
- train, validation, holdout, and prospective dates;
- candidate inventories and fitted parameters;
- calibration reports and promotion decisions;
- commentary cache namespaces.

A BankNifty result is prior design evidence for NIFTY, not a NIFTY score.

## NIFTY-specific evaluation sequence

1. Build a NIFTY adapter and synthetic contract tests.
2. Reconstruct NIFTY replay inventory and prove exact equivalence.
3. Audit missing inputs explicitly; an unavailable constituent basket remains
   unavailable rather than being imputed.
4. Freeze independent NIFTY session splits before candidate generation.
5. Generate candidates from NIFTY training summaries only.
6. Compare per horizon with NIFTY-specific deterministic baselines.
7. Open the NIFTY holdout once only after a frozen validation selection.
8. Run prospective NIFTY shadow commentary before any integration.

## Portability acceptance criteria

- A generic-case JSON can represent both instruments without renamed semantic
  fields or BankNifty-only constants.
- Identical raw event sequences produce identical generic state transitions
  after instrument normalization.
- Missing optional features produce an explicit availability flag.
- Replay and live NIFTY paths produce identical stored commentary identities
  for the same prefix.
- Cross-instrument tests prove that one instrument cannot read the other's
  labels, candidates, holdout, or commentary cache.
