# Market-profile semantics

The coordinate is the synchronized BankNifty Index price at which a retained
change was observed. It is not the option strike and it is not the option
premium.

Families:

- `CE_POS_OI_VPOC` and `PE_POS_OI_VPOC`: BankNifty price bins carrying the
  greatest accumulated absolute positive option-OI change for the fixed
  selected-expiry contracts.
- `CE_NEG_OI_VPOC` and `PE_NEG_OI_VPOC`: corresponding negative-OI controls.
- `FUT_POS_OI_VPOC` and `FUT_NEG_OI_VPOC`: BankNifty price bins carrying the
  greatest accumulated absolute Futures-OI change.
- `BN_REF_FUT_VOLUME_VPOC`: BankNifty price bin carrying the greatest accepted
  incremental Futures volume; `VAL` and `VAH` are the contiguous configured
  value-area bounds around it.

An upward control migration means the profile's maximum-weight BankNifty price
bin moved higher. It does not by itself mean price must rise. A negative-OI
profile means OI decreased at that BankNifty coordinate; it does not identify
whether a buyer or writer closed a position.

Scopes:

- `ID` uses only observations from 09:45 IST through the causal cutoff.
- `1D`, `2D`, and `3D` are frozen combined profiles constructed only from the
  preceding one, two, or three eligible completed sessions.

The candidate may treat confluence, migration, price response, Futures OI,
option flow, and freshness as evidence. It must abstain when those components
conflict or are unavailable.
