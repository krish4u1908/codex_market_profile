# R6B2R Clock Contract

- **Divergence confirmation:** frozen synchronized confirmation timestamp.
- **Index response:** first qualifying standalone raw Index receipt strictly after confirmation. No Futures delay or rounding.
- **Basis resolution:** Futures-driven synchronized basis rows with backward Index as-of matching, age from 0 through 2,000 ms, `VALID` status, and timestamp within the episode cutoff.
- **Stalled extreme:** timezone-aware wall-clock seconds from confirmation/latest colour-consistent basis extreme. Equal two-decimal basis prices reset the extreme clock. Invalid observations do not pause elapsed time.
- **Terminal lifecycle:** frozen lifecycle/opposite-confirmation cutoff. A response may exist after cutoff without becoming an eligible transition; its existence still prevents an erroneous expired classification under the frozen R3 rule.
- **Snapshot:** replay compatibility only; never an effective-event clock.
