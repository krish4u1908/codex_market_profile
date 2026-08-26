# R6E1R0 Callback-Wiring Report

Status: `R6E1R0_CALLBACK_WIRING_VERIFIED_ON_HOSTINGER_SAMPLE`

The production path is `poll → normalization → causal synchronization → inventory → divergence → dependency → lifecycle/resolution → participation → four views → cross-layer transitions → GUI projection`.

Repairs were limited to adapters and scheduling:

- Depth-only raw rows with neither price nor volume remain in the audit ledger but are excluded from analytical frames, matching the canonical raw loader.
- Participation stops at each episode's canonical lifecycle end instead of the latest poll cutoff.
- Poll-sized observations are staged once per session, retaining append-only recovery without one fsync per row.
- Equivalence comparison removes only run-local raw/OI path prefixes; stream, date, filename and row remain compared.

No frozen formula, threshold or semantic changed. Synchronization remains exactly 2,000 ms. No deployment or prospective activation occurred.

Classification: LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL
