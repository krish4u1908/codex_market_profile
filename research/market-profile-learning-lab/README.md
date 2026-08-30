# Market Profile Agent Learning Lab

This directory preserves the isolated BankNifty market-profile agent-learning
work and the decisions needed to reuse the same causal framework for NIFTY.

The lab converts verified replay sessions into causal inventory-shift episodes,
keeps future outcomes separate, asks Codex to propose constrained numeric agent
specifications from training-only summaries, and evaluates those frozen agents
against deterministic baselines.

It does **not** retrain Codex model weights. It does **not** authorize a trading
signal. Generated language is an explanation layer over deterministic,
versioned inputs and forecasts.

## Repository contents

- `releases/v0.1.2/` — verified source release used for the August 2026 pilot.
- `docs/CONCEPT_AND_SYSTEM_DESIGN.md` — centralized shift-analysis and GUI design.
- `docs/DECISION_LOG.md` — decisions carried forward from the design discussion.
- `docs/NIFTY_REUSE_PLAN.md` — instrument-adapter boundary for NIFTY.
- `docs/NEXT_EVALUATION_V0.1.3.md` — evaluation-hardening plan before holdout use.
- `evidence/pilot-2026-08-v1/` — small, non-market-data pilot summaries.
- `manifests/` — release lineage and publication boundary.

## Frozen pilot conclusion

The August 2026 pilot completed successfully, generated three Codex candidate
agents, and left the holdout sealed. The aggregate selection decision was:

`NO_CANDIDATE_EDGE_ON_VALIDATION`

Two horizon-specific observations remain research hypotheses:

- the empirical minimal/abstaining candidate was strongest at 30 minutes;
- the conservative flow-confirmation candidate was strongest at 15 minutes.

Neither may be promoted from this result. Validation contains four independent
session dates, so the episode count must not be treated as the independent
sample size.

## Data boundary

This tree contains source, schemas, tests, methodology, decision records,
hashes, and compact aggregate evidence only. It excludes raw market records,
browser payloads, learning-run workspaces, candidate workspaces, logs,
credentials, tokens, virtual environments, and archive binaries.

The source archive is represented by its SHA-256 in
`manifests/UPSTREAM_ARCHIVE.sha256`; the unpacked release is the reviewable
package stored in Git.

## Promotion boundary

The holdout remains sealed until a horizon-specific evaluation contract is
predeclared and frozen. Even a holdout pass would permit only prospective
shadow commentary, not automatic production promotion.
