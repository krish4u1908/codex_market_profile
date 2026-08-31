# Resolution-Mechanism Audit

The algebra is identical on common timestamps:

- GREEN: Index contribution = Index movement; Futures contribution = negative Futures movement.
- RED: Index contribution = negative Index movement; Futures contribution = Futures movement.
- Signed convergence equals the sum of those contributions and equals negative signed basis change, within the frozen `1e-8` identity tolerance.

The classification precedence in `basis_divergence_state_revision_1/build_study.py:519-530` is sequential assignment: unresolved, expansion, both constructive/adverse, Index catch, Futures reversal, then stalled. Later masks override earlier masks.

R6B2 instead called the reusable `decompose_basis` with stalled duration fixed to zero and accepted its earlier-return precedence. The resulting 49,545 differences split exactly into:

- Missing stalled clock: 8,779 Futures reversal, 3,405 Index catch-down, 7,210 Index catch-up, and 2,831 unresolved rows that R3 classifies stalled.
- Precedence difference: 2,250 both-adverse, 10,187 Futures reversal, 1,676 Index catch-down, and 13,207 Index catch-up rows that R6B2 reduces to remained-extreme.

`resolution_manual_reconciliation.csv` provides 104 independently inspectable rows: at least ten across every material root-cause/mechanism group, matched controls for both colours on every session, and labelled August 19 cases A/B/C/D. Each row includes component timestamps, prices, movements, contributions, receipts, and adjudication. `resolution_root_cause_groups.csv` proves the unexplained remainder is zero.

The normalized views intentionally differ:

- `dense_observation_comparison.csv`: all 164,668 common valid timestamps.
- `transition_view_comparison.csv`: state-change rows only.
- `episode_summary_comparison.csv`: one row per 65 episodes.
- `snapshot_compatibility_comparison.csv`: R3-compatible snapshot view.

These views must not be treated as interchangeable sample populations.
