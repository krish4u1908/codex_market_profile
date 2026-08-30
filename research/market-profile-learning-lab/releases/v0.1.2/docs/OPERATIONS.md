# Operations

Run this package as `codexuser`. Root is needed only to place the release and,
if desired, to set its ownership. Do not run the learning commands as root.

## 1. Install

```bash
cd /home/codexuser/banknifty-market-profile-lab/releases/banknifty-market-profile-learning-lab-v0.1.2
./install.sh
./.venv/bin/banknifty-market-profile-lab --version
```

The installation is local and starts nothing.

## 2. Install the opt-in Codex candidate profile

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

## 3. Build the immutable learning dataset

Choose a new run directory. The command refuses to overwrite an existing one.

```bash
release=/home/codexuser/banknifty-market-profile-lab/releases/banknifty-market-profile-learning-lab-v0.1.2
learning_run=/home/codexuser/banknifty-market-profile-lab/runs/pilot-2026-08-v1

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

## 4. Create deterministic seed candidates

```bash
"$release/.venv/bin/banknifty-market-profile-lab" seed-candidates \
  --learning-run "$learning_run"
```

These are comparison agents, not learned champions.

## 5. Prove the candidate Codex isolation profile

```bash
"$release/.venv/bin/banknifty-market-profile-lab" profile-check \
  --learning-run "$learning_run" \
  --codex-bin /home/codexuser/.local/bin/codex \
  --profile banknifty-learning
```

The check creates a harmless random sentinel outside the candidate workspace,
asks a temporary Codex run to read it, and passes only when the read is denied.
If a loaded older `sandbox_mode` setting disables permission profiles, this
check must fail; do not bypass it.

## 6. Generate three Codex candidates

```bash
"$release/.venv/bin/banknifty-market-profile-lab" generate-candidates \
  --learning-run "$learning_run" \
  --agent-schema "$release/schemas/agent-spec.schema.json" \
  --codex-bin /home/codexuser/.local/bin/codex \
  --profile banknifty-learning \
  --count 3
```

Each invocation is ephemeral and receives a training-only aggregate summary.
It cannot read the run root, raw sessions, labels, validation data, or holdout
data. Structured output is constrained by the agent-specification JSON schema.

The schema is checked locally for the strict Structured Outputs object/type
requirements before Codex is called. If a role is interrupted, rerunning the
same command preserves the failed workspace and uses the next numbered attempt;
successfully checkpointed roles are reused rather than regenerated.

## 7. Score development splits

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

## 8. Open the holdout once, only after review

When the validation report explicitly says `ELIGIBLE_FOR_HOLDOUT_REVIEW` and
the candidate skills have been manually inspected:

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

Opening writes `holdout/OPENED.json` with the complete candidate inventory.
New or changed candidates are rejected afterward.

## Expected deliverables

```text
learning-run/
  cases/                    causal prefix cases
  labels/                   separate retrospective outcomes
  candidates/               candidate SKILL.md and numeric specifications
  candidate_workspaces/     training-only Codex inputs
  forecasts/                locked deterministic forecasts
  scores/                   train, validation and optional holdout scorecards
  reports/evaluation_report.md
  metadata/input_manifest.json
  metadata/session_audit.json
  holdout/SEALED.json
```

No file from this directory is automatically copied to v1.0.20 or installed as
a production skill.
