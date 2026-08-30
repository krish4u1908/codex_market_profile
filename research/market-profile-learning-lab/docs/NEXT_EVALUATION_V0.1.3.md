# V0.1.3 Evaluation-Hardening Plan

V0.1.3 should evaluate the frozen V0.1.2 candidates more rigorously. It should
not generate additional candidates from the same validation result.

## Frozen shortlist

- 5-minute learned specialist: none.
- 15-minute research hypothesis: `conservative-flow-confirmation-v1`.
- 30-minute research hypothesis: `empirical-minimal-abstaining-v1`.

The hashes recorded in the pilot evidence identify the exact candidates.

## Required additions

1. Select and report each horizon independently instead of relying only on an
   equal mean of 5, 15, and 30 minutes.
2. Treat the session date as the independent unit.
3. Add per-session scorecards, session win/loss counts, leave-one-session-out
   stability, and a session-block bootstrap interval.
4. Add class support, confusion matrices, directional coverage, abstention
   rate, and calibration/reliability summaries.
5. Compare every specialist with the strongest baseline at that same horizon.
6. Replace the level-extreme proxy with a directional event sequence:
   publication, approach/touch, reaction before breach, or breach before
   reaction. Thresholds remain frozen configuration values.
7. Score support and resistance separately and report how often a level was
   actually testable within the horizon.
8. Produce a machine-readable selection record explaining every passed or
   failed gate.

## Proposed predeclared gate

A horizon specialist may become holdout-eligible only when:

- balanced accuracy and composite exceed the strongest same-horizon baseline;
- Brier score is not worse;
- improvement is not driven by a single validation session;
- class support and coverage meet declared minima;
- support/resistance reaction metrics beat their declared baseline when level
  prediction is part of the agent;
- all candidate and evaluator hashes are frozen before holdout access.

The exact numeric margins and stability rule must be written before rescoring.

## Holdout rule

The existing holdout remains sealed during V0.1.3 development. If no specialist
passes the predeclared validation gate, stop and gather more prospective
sessions. If one passes, freeze only that specialist and open the holdout once.

A holdout pass permits prospective shadow commentary only. It does not permit
automatic production promotion.
