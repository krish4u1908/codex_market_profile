# BankNifty Market Profile Learning Lab v0.1.3

This is an isolated, finite research workflow that reconstructs CE, PE,
Futures-OI, and BankNifty-reference Futures-volume inventory shifts from
verified New Divergence v1.0.19 replay sessions. It creates causal cases,
separately sealed future labels, candidate numeric agents, candidate Codex
skills, deterministic forecasts, and scored reports.

V0.1.3 is an evaluation-hardening release. It rebuilds a new sealed run with
ordered future receipt paths, imports exact frozen V0.1.2 candidates, scores
each horizon independently, and treats the session date as the effective
sample unit.

It does not retrain Codex model weights. "Learning" means that Codex proposes
versioned, reviewable agent specifications and skills from training-only
statistics; deterministic code evaluates those specifications on later dates.

## Safety boundary

- Reads v1.0.19 completed runs and browser payloads.
- Writes only to a new learning-run directory.
- Starts no service or background process.
- Opens no port.
- Does not modify the collector, v1.0.19, replay `8794`, live `8793`, or the
  loopback worker on `4500`.
- Keeps validation and holdout labels outside all candidate Codex workspaces.
- Requires a Codex permission-profile proof before Codex candidate generation.
- Forbids candidate creation after holdout opening.
- Accepts v1.0.19's declared legacy sessions where the optional raw Futures
  market artifact was not retained; it records volume-profile unavailability
  and never fabricates the missing volume evidence.
- Validates Codex response schemas locally before an API request and resumes an
  interrupted candidate role in a new audit workspace without deleting or
  overwriting the failed attempt.
- Distinguishes level reaction-before-breach from breach-before-reaction using
  ordered future receipts kept only in sealed label files.
- Adds per-session metrics, leave-one-session-out stability, deterministic
  session bootstrap intervals, calibration bins, and horizon-specific gates.
- Refuses holdout opening unless at least one predeclared horizon specialist
  passes every V0.1.3 validation gate.
- Evaluates only the frozen eligible candidate/horizon inventory after the
  holdout is opened once.

See [Operations](docs/OPERATIONS.md) for exact commands and
[Methodology](docs/METHODOLOGY.md) for the causal and scoring contracts.
