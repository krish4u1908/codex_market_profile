# Resolution Precedence Specification

At every valid synchronized basis timestamp, R6B2R calculates Index movement, Futures movement, basis change, Index contribution, Futures contribution, and signed convergence. It then applies assignments sequentially:

1. `UNRESOLVED`
2. `BASIS_EXPANSION_CONTINUING`
3. `BOTH_CONVERGING_CONSTRUCTIVELY` or `BOTH_CONVERGING_ADVERSELY`
4. `INDEX_CATCH_UP` or `INDEX_CATCH_DOWN`
5. `FUTURES_REVERSED_TO_INDEX`
6. `BASIS_EXTREME_STALLED`

Later masks override earlier masks. The native mechanism is stored separately from the compatibility-normalized label. No early-return or generic remained-extreme substitution participates in native classification.
