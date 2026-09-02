# R6C2 full-stack contract

R6C2 adds only two publication layers to the frozen raw engines:

1. A deterministic transition-only cross-layer ledger that retains causal constituent clocks and rejects backdating.
2. Independent 1D, 2D, 3D and Intraday availability, with explicit partial-context degradation.

The layers do not modify inventory, divergence, dependency, lifecycle,
resolution, participation, persistence, synchronization or threshold semantics.
They contain no outcome, P&L, order or trading fields.
