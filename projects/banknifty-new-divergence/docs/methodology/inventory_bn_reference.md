# Inventory V2 BN-reference methodology

For each selected Futures contract, observations are restricted to 09:15:00–15:29:59.999999 IST. The first valid same-session cumulative-volume counter is a baseline. Positive increments are retained; unchanged counters add zero and negative resets are rejected. Each increment at receipt time T is backward joined to the latest finite BankNifty Index price at or before T, within the frozen 5-second tolerance. Missing or stale joins are excluded without a Futures-price fallback.

The Index reference price is rounded deterministically to a 25-point bin. Volume is summed by bin. Ties resolve nearest the volume-weighted mean, then nearest the prior causal VPOC, then to the lower bin. Fixed 1D/2D/3D profiles aggregate event-level bin contributions from the specified prior sessions; daily winners are never averaged. Intraday profiles publish only when the winning bin changes.

For the replay context, the canonical BankNifty-reference Futures-volume
profile also publishes a contiguous 70% value area. Starting at aggregate
VPOC, the algorithm adds the heavier immediately adjacent 25-point bin; exact
upper/lower weight ties add both. Expansion continues until cumulative included
weight reaches at least 70% of total profile weight. The interval endpoints are
VAL and VAH. They are volume-profile descriptors only and are never inferred
for signed OI families.

Signed Futures, CE and PE OI-VPOC semantics remain separate and unchanged. Options use one compatible expiry with preserved type and moneyness. August 17 remains excluded.
