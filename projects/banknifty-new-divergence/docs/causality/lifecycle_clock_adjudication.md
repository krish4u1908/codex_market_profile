# Clock Semantics

## Effective clocks

| Component | Effective causal clock | Reason |
|---|---|---|
| Divergence confirmation | Frozen synchronized confirmation timestamp | Index and Futures basis evidence is required. |
| Favourable/adverse response | Standalone BankNifty Index receipt | The observable is Index movement from confirmation; no Futures field is required. |
| Basis resolution | Latest valid synchronized Index/Futures basis timestamp | Both price components are required and neither may be future joined. |
| Stalled extreme | Wall-clock elapsed between valid synchronized updates, reset on a new qualifying extreme | This is an elapsed-duration condition, not an observation counter. |
| Transition publication | Timestamp at which a newly classified state first differs from the prior published state | Repeated dense observations are not new transitions. |
| Snapshot publication | Requested replay/as-of timestamp | Compatibility view only; it cannot move an effective event clock. |

## Response reconciliation

`response_clock_reconciliation.csv` contains 130 episode/state checks (65 favourable and 65 adverse). R3 emitted 117 of these and every emitted timestamp exactly equals the independent first raw Index receipt crossing the frozen 10-point threshold. Of the remaining checks, eight raw Index crossings occur after R3's lifecycle cutoff and five never cross the threshold. R6B2 emitted 121 response timestamps; every one is later than the independently observable Index receipt because it waits for a Futures-driven basis observation.

A response that occurs after the frozen lifecycle cutoff is not an R3 response transition even if the Index later crosses 10 points. That is an eligibility distinction, not evidence that Futures synchronization is required.
