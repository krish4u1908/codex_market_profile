# R6B3 raw participation methodology

R6B3 derives descriptive Futures, CE and PE context only from physical WebSocket and REST JSONL. Frozen R6B2R episode identifiers and timestamps are event anchors, not generated participation inputs.

Windows are elapsed `(T-window,T]` receipt-time windows. Cumulative volume decreases are reset boundaries; duplicates contribute nothing. Unchanged valid OI receipts remain fresh and yield zero delta. Options remain symbol-, strike-, type- and expiry-specific. Volume means cumulative traded-volume change between REST receipts, not tick-ordered intraminute volume.

The native view selects the nearest causal expiry and ATM plus up to three listed strikes on each side, separately for CE and PE, using the latest BankNifty index observation at or before `T`. No future liquidity or outcome is consulted.

Stream and batch start empty and serialize canonical records with sorted keys. R4/R5 files are prohibited until both seals exist.
