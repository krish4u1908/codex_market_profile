# Publication clock specification

- `evidence_receipt_timestamp`: receipt of the causal contributing evidence.
- `calculation_timestamp`: causal computation time, equal to or after evidence receipt.
- `control_effective_timestamp`: earliest time the computed winner can be known.
- `winner_change_timestamp`: receipt time that first changes the winner.
- `snapshot_timestamp`: optional observation/export time; it never replaces effective time.
- `freshness_receipt_timestamp`: latest qualifying evidence receipt in the profile.
- `last_contributing_change_timestamp`: latest receipt adding nonzero profile weight.

Intraday winners are never backdated. Fixed controls become available at 09:15 IST only after their completed source sessions have been validated.
