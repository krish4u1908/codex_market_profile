# Operations

Run this package as `codexuser`. Root is needed only to place the release and,
if desired, to set its ownership. Do not run the learning commands as root.

## 1. Install

```bash
cd /home/codexuser/banknifty-market-profile-lab/releases/banknifty-market-profile-learning-lab-v0.1.3
./install.sh
./.venv/bin/banknifty-market-profile-lab --version
```

The installation is local and starts nothing.

## 2. Optional: retain the opt-in Codex profile

```bash
./install_codex_profile.sh
```

This creates only:

```text
/home/codexuser/.codex/banknifty-learning.config.toml
```

It does not change the default profile and is active only when a command uses
`--profile banknifty-learning`. If the file already exists, installation stops
without overwriting it.

V0.1.3 evaluation does not call Codex and does not require this profile. The
installer is retained only for release compatibility; do not regenerate
candidates for the V0.1.3 evaluation run.

## 3. Build the immutable learning dataset

Choose a new run directory. The command refuses to overwrite an existing one.

```bash
release=/home/codexuser/banknifty-market-profile-lab/releases/banknifty-market-profile-learning-lab-v0.1.3
source_run=/home/codexuser/banknifty-market-profile-lab/runs/pilot-2026-08-v1
learning_run=/home/codexuser/banknifty-market-profile-lab/runs/pilot-2026-08-v2-evaluation

"$release/.venv/bin/banknifty-market-profile-lab" build \
  --run-root /home/bankadmin/divergence/sessions \
  --gui-root /home/bankadmin/divergence/new-divergence-gui-v1.0.19 \
  --config "$release/config/learning_run.json" \
  --output-root "$learning_run"
```

The build independently verifies every v1.0.19 artifact hash used, reconstructs
the intraday inventory, and refuses the session if its reconstruction differs
from the published browser rows.

The v1.0.19 contract permits legacy runs without a retained `futures_market`
artifact. Such a run remains eligible for its available CE, PE and Futures-OI
families. BN-reference Futures-volume evidence stays unavailable for that run
and is explicitly recorded in `metadata/session_audit.json`.

The new V0.1.3 run retains ordered future receipts only inside sealed label
files. It does not modify the V0.1.2 run or its holdout seal.

## 4. Import the two predeclared frozen candidates

```bash
"$release/.venv/bin/banknifty-market-profile-lab" import-candidates \
  --learning-run "$learning_run" \
  --source-run "$source_run" \
  --candidate-id conservative-flow-confirmation-v1-966e83ba1736 \
  --candidate-id empirical-minimal-abstaining-v1-13051026b24b
```

The command copies the existing candidate directories byte-for-byte and writes
`metadata/frozen_candidate_import.json`. It fails if either candidate hash is
missing or if the destination contains a different candidate. Do not run
`seed-candidates` or `generate-candidates` for this evaluation run.

## 5. Score development splits

```bash
"$release/.venv/bin/banknifty-market-profile-lab" evaluate \
  --learning-run "$learning_run" \
  --split train

"$release/.venv/bin/banknifty-market-profile-lab" evaluate \
  --learning-run "$learning_run" \
  --split validation

"$release/.venv/bin/banknifty-market-profile-lab" report \
  --learning-run "$learning_run"

"$release/.venv/bin/banknifty-market-profile-lab" verify \
  --learning-run "$learning_run"
```

Stop here and review `reports/evaluation_report.md`. Do not open the holdout
merely to obtain a better-looking result.

The validation report contains separate 5m/15m/30m gates, per-session scores,
leave-one-session-out stability, session bootstrap intervals, confusion/class
support, calibration, and reaction-before-breach results. The 5-minute
allowlist is intentionally empty.

## 6. Open the holdout once, only after review

Only when the validation report explicitly says
`HORIZON_SPECIALIST_ELIGIBLE_FOR_HOLDOUT_REVIEW`:

```bash
"$release/.venv/bin/banknifty-market-profile-lab" evaluate \
  --learning-run "$learning_run" \
  --split holdout \
  --open-holdout

"$release/.venv/bin/banknifty-market-profile-lab" report \
  --learning-run "$learning_run"

"$release/.venv/bin/banknifty-market-profile-lab" verify \
  --learning-run "$learning_run"
```

Opening writes `holdout/OPENED.json` with the complete candidate inventory,
validation-selection hash, selected candidate/horizon list, and sealed case
and label hashes. Only eligible specialists and same-horizon baselines are
scored. New candidates or a changed selection are rejected afterward.

## Expected deliverables

```text
learning-run/
  cases/                    causal prefix cases
  labels/                   separate retrospective outcomes
  candidates/               candidate SKILL.md and numeric specifications
  metadata/frozen_candidate_import.json
  forecasts/                locked deterministic forecasts
  scores/                   train, validation and optional holdout scorecards
  reports/evaluation_report.md
  metadata/input_manifest.json
  metadata/session_audit.json
  holdout/SEALED.json
```

No file from this directory is automatically copied to v1.0.20 or installed as
a production skill.
