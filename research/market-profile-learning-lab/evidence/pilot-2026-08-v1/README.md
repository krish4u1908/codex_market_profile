# Pilot 2026-08 V1 Evidence

Classification: `RESEARCH_ONLY_NOT_A_TRADING_SIGNAL`

This directory contains compact, non-market-data evidence transcribed from the
verified learning run. The original learning-run directory, cases, labels,
raw session payloads, candidate workspaces, and logs remain external.

## Integrity summary

- Input manifest SHA-256:
  `2dc87193ab168ec1b834ff2aebe4ba8594135325bc4b212b8927c3b340ff6cde`
- Train: 10 sessions, 373 episodes, 373 labels.
- Validation: 4 sessions, 168 episodes, 168 labels.
- Holdout: 4 sessions, 164 episodes, 164 labels.
- Consolidated causal episodes: 705.
- Inventory reconstruction equivalence: PASS for every included session.
- One legacy session lacked retained raw Futures-market volume; no evidence was
  fabricated.
- Holdout state after reporting: SEALED.
- Automatic production promotion: disabled.

## Selection conclusion

- Best deterministic baseline: `baseline-momentum-5m`.
- Best aggregate learned candidate: `empirical-minimal-abstaining-v1`.
- Relative validation gate: FAIL.
- Decision: `NO_CANDIDATE_EDGE_ON_VALIDATION`.

The independent sample size is four validation dates, not 168 episodes.
