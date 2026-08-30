# Methodology

## Experimental unit

The causal event is a migration of an inventory control from one BankNifty
Index price bin to another. Changes from several families with the same receipt
time become one episode. The first observation for each family establishes its
baseline and is not a shift.

The effective independent sample unit is a full session date. Hundreds of
intraday episodes do not turn eighteen dates into hundreds of independent
market regimes.

## Inventory reconstruction

The lab reconstructs the v1.0.19 profiles from verified artifacts:

- option and Futures OI deltas are mapped to a fresh backward-joined BankNifty
  Index receipt;
- positive and negative OI use separate absolute-weight profiles;
- accepted incremental Futures volume uses the BankNifty Index coordinate;
- controls use 25-point bins and the v1.0.19 weighted-mean/lower-bin tie-break;
- Futures volume uses a contiguous 70% value area around VPOC.

The reconstructed intraday rows must be exactly equivalent to the published
v1.0.19 browser rows for timestamp, family, VPOC, VAL and VAH. A mismatch stops
the build.

`futures_market` is optional in the v1.0.19 run contract for legacy sessions.
When it is absent, the lab supplies no Futures-volume contribution for that
session. It still verifies the remaining published inventory exactly and
marks the volume family unavailable instead of imputing or reverse-engineering
missing raw evidence.

For a target date, 1D/2D/3D profiles combine contributions from only the
strictly preceding one, two or three eligible completed sessions. Future dates
cannot enter a prefix.

## Prefix and labels

A case contains only information at or before its `causal_cutoff`: current
price and basis, recent returns, latest fresh Futures OI, latest selected CE/PE
flow, current profile controls, frozen prior profiles, shift provenance and
candidate interaction levels.

Outcomes are stored in different files, cryptographically bound to the complete
case JSON, and never copied into candidate Codex workspaces. Direction is:

- `UP` when the endpoint change is at least +25 points;
- `DOWN` when it is at most -25 points;
- `ROTATION` otherwise.

The report also retains 15/25/40-point sensitivity labels. Horizons are 5, 15
and 30 minutes. Cases without a sufficiently close future receipt are marked
unavailable instead of imputed.

## Candidate learning

Codex receives training-only aggregate statistics. It emits a constrained
numeric specification containing feature weights, abstention threshold, level
ranking weights and confidence bounds. The lab converts that specification to
a candidate skill. The candidate cannot change code, define a new outcome, or
see raw validation/holdout outcomes.

Forecasts are produced deterministically from the frozen specification. This
separates natural-language agent creation from scoring and makes every result
reproducible.

## Metrics

Primary metrics are three-class balanced accuracy and Brier score. Directional
coverage records how often an agent avoids `ROTATION`. The level-extreme metric
records whether one of the ranked support/resistance levels lies within the
configured tolerance of the subsequent path low/high.

The level metric is diagnostic. A future extreme near a level is not proof the
level caused a reversal and does not establish trade executability.

The fixed experimental composite is:

```text
0.65 × balanced accuracy
+ 0.20 × (1 − Brier score)
+ 0.15 × level-extreme hit rate
```

A candidate passes the relative validation gate only when both its mean
balanced accuracy and mean composite exceed the best deterministic baseline.
That gate permits holdout review; it does not permit production promotion.

## Promotion boundary

The internal holdout can be opened once for a frozen candidate inventory.
Regardless of the result, at least several new prospective completed sessions
are required before considering a centralized live/replay commentary service.
No result from this pilot is a buy/sell instruction or profitability claim.
