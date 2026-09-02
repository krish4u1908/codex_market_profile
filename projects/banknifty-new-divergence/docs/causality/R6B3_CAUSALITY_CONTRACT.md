# R6B3 causality contract

- Every source timestamp is timezone-aware.
- An observation may use only receipts at or before its observation clock.
- REST receipt time is authoritative; no exchange event time is invented.
- Missing and stale states remain explicit.
- Post-confirmation evidence retains its actual first receipt and timing cohort.
- Reference comparison begins only after native stream and batch seals.
- Participation is descriptive context and never a confirmation gate, direction, entry, outcome, or P&L field.
