"""Human-readable experiment report and integrity verification."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Mapping

from .io_utils import (
    atomic_json,
    atomic_text,
    canonical_json,
    iter_jsonl,
    load_json,
    sha256_file,
    sha256_text,
)
from .scoring import candidate_inventory


def _percent(value: object) -> str:
    return f"{100.0 * float(value):.2f}%"


def _score_table(scorecard: Mapping[str, object]) -> str:
    rows = scorecard.get("scores", [])
    lines = [
        "| Candidate | Horizon | Balanced accuracy | Brier | Level-extreme hit | Reaction/tested | Composite |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(
        (value for value in rows if isinstance(value, Mapping)),
        key=lambda value: (str(value["candidate_id"]), int(value["horizon_minutes"])),
    ):
        lines.append(
            f"| {row['candidate_id']} | {row['horizon_minutes']}m | "
            f"{_percent(row['balanced_accuracy'])} | {float(row['brier_score']):.4f} | "
            f"{_percent(row['level_extreme_hit_rate'])} | "
            f"{_percent(row.get('level_reaction_rate', 0.0))}/"
            f"{int(row.get('level_reaction_tested', 0))} | "
            f"{float(row['composite_score']):.4f} |"
        )
    return "\n".join(lines)


def generate_report(run_root: Path) -> Path:
    manifest_value = load_json(run_root / "metadata" / "input_manifest.json")
    audit_value = load_json(run_root / "metadata" / "session_audit.json")
    config_value = load_json(run_root / "metadata" / "learning_config.json")
    if not all(isinstance(value, Mapping) for value in (manifest_value, audit_value, config_value)):
        raise ValueError("run metadata is invalid")
    manifest, audit, config = manifest_value, audit_value, config_value
    candidates = candidate_inventory(run_root)
    scorecards: dict[str, Mapping[str, object]] = {}
    for split in ("train", "validation", "holdout"):
        path = run_root / "scores" / f"{split}.json"
        if path.is_file():
            value = load_json(path)
            if isinstance(value, Mapping):
                scorecards[split] = value
    selection_path = run_root / "scores" / "validation_selection.json"
    selection = load_json(selection_path) if selection_path.is_file() else None
    holdout_state = "OPENED" if (run_root / "holdout" / "OPENED.json").is_file() else "SEALED"
    total_components = sum(
        int(row.get("control_shift_components", 0))
        for row in audit.get("sessions", [])
        if isinstance(row, Mapping)
    )
    total_episodes = sum(
        int(row.get("episodes", 0))
        for row in audit.get("sessions", [])
        if isinstance(row, Mapping)
    )
    lines = [
        "# BankNifty Market Profile Agent Learning Report",
        "",
        f"Classification: **{config['classification']}**",
        "",
        "## Dataset",
        "",
        f"- Input manifest: `{manifest['manifest_sha256']}`",
        f"- Training sessions: {len(config['splits']['train'])}",
        f"- Validation sessions: {len(config['splits']['validation'])}",
        f"- Holdout sessions: {len(config['splits']['holdout'])}",
        f"- Individual control migrations: {total_components}",
        f"- Consolidated causal episodes: {total_episodes}",
        "- Intraday reconstruction equivalence: PASS for every included session",
        "- Prior context: combined 1D/2D/3D profiles from strictly earlier eligible sessions",
        "",
        "Rows inside one market session are correlated. The effective sample size is the number of session dates, not the episode count.",
        "",
        "## Candidate agents",
        "",
    ]
    if candidates:
        for row in candidates:
            lines.append(
                f"- `{row['candidate_id']}` — {row['origin']} — `{row['agent_spec_sha256']}`"
            )
    else:
        lines.append("- No candidates have been generated.")
    for split in ("train", "validation", "holdout"):
        if split in scorecards:
            lines.extend([
                "",
                f"## {split.title()} scorecard",
                "",
                _score_table(scorecards[split]),
            ])
    lines.extend(["", "## Selection", ""])
    if isinstance(selection, Mapping):
        lines.extend([
            f"- Best candidate: `{selection['best_candidate']['candidate_id']}`",
            f"- Best baseline: `{selection['best_baseline']['candidate_id']}`",
            f"- Relative validation gate: **{'PASS' if selection['candidate_passes_relative_gate'] else 'FAIL'}**",
            f"- Decision: **{selection['decision']}**",
        ])
        horizon_rows = selection.get("horizon_selection", [])
        if isinstance(horizon_rows, list):
            lines.extend([
                "",
                "### Horizon-specialist gate",
                "",
                "| Horizon | Candidate | Baseline | Session wins | LOO passes | Eligible | Reasons |",
                "|---:|---|---|---:|---:|---|---|",
            ])
            for row in horizon_rows:
                if not isinstance(row, Mapping):
                    continue
                lines.append(
                    f"| {row['horizon_minutes']}m | {row.get('candidate_id') or '-'} | "
                    f"{row.get('baseline_id') or '-'} | "
                    f"{row.get('session_wins', 0)}/{row.get('session_count', 0)} | "
                    f"{row.get('loo_passes', 0)}/{row.get('loo_count', 0)} | "
                    f"{'YES' if row.get('eligible') else 'NO'} | "
                    f"{', '.join(map(str, row.get('reasons', [])))} |"
                )
    else:
        lines.append("Validation has not been scored; no candidate can be selected.")
    lines.extend([
        "",
        "## Holdout and promotion state",
        "",
        f"- Holdout: **{holdout_state}**",
        "- Automatic production promotion: **DISABLED**",
        "- v1.0.19 services modified: **NO**",
        "- Production signal claim: **NOT PERMITTED**",
        "",
        "A candidate may be reviewed for a later centralized commentary service only after it beats the deterministic baselines on validation and the once-opened holdout. Even then, prospective sessions are required before production use.",
        "",
        "## Metric boundary",
        "",
        "The legacy level-extreme metric remains in the fixed composite for comparability. V0.1.3 additionally follows ordered future receipts after the first touch and distinguishes reaction-before-breach, breach-before-reaction, unresolved, and untested levels. Neither metric proves trade executability or profitability.",
    ])
    destination = run_root / "reports" / "evaluation_report.md"
    atomic_text(destination, "\n".join(lines) + "\n")
    atomic_json(run_root / "reports" / "report_manifest.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_REPORT_MANIFEST_V2",
        "report": destination.name,
        "report_sha256": sha256_file(destination),
        "holdout_state": holdout_state,
        "candidate_count": len(candidates),
        "available_scorecards": sorted(scorecards),
    })
    return destination


def verify_learning_run(run_root: Path) -> dict[str, object]:
    reasons: list[str] = []
    try:
        manifest = load_json(run_root / "metadata" / "input_manifest.json")
        if not isinstance(manifest, Mapping):
            raise ValueError("input manifest is invalid")
        expected_manifest_hash = manifest.get("manifest_sha256")
        unhashed = dict(manifest)
        unhashed.pop("manifest_sha256", None)
        if sha256_text(canonical_json(unhashed)) != expected_manifest_hash:
            reasons.append("INPUT_MANIFEST_SELF_HASH_MISMATCH")
        for row in manifest.get("files", []):
            if not isinstance(row, Mapping):
                reasons.append("INVALID_INPUT_FILE_ROW")
                continue
            path = Path(str(row.get("path", "")))
            if not path.is_file():
                reasons.append(f"MISSING_INPUT:{path}")
            elif sha256_file(path) != row.get("sha256"):
                reasons.append(f"INPUT_HASH_MISMATCH:{path}")
        for split in ("train", "validation", "holdout"):
            cases = {str(row["case_id"]): row for row in iter_jsonl(run_root / "cases" / f"{split}.jsonl")}
            labels = {str(row["case_id"]): row for row in iter_jsonl(run_root / "labels" / f"{split}.jsonl")}
            if set(cases) != set(labels):
                reasons.append(f"CASE_LABEL_ID_MISMATCH:{split}")
            for case_id in set(cases) & set(labels):
                if sha256_text(canonical_json(cases[case_id])) != labels[case_id].get("case_sha256"):
                    reasons.append(f"CASE_LABEL_HASH_MISMATCH:{split}:{case_id}")
        seal = load_json(run_root / "holdout" / "SEALED.json")
        if not isinstance(seal, Mapping):
            reasons.append("INVALID_HOLDOUT_SEAL")
        else:
            if sha256_file(run_root / "cases" / "holdout.jsonl") != seal.get("cases_sha256"):
                reasons.append("HOLDOUT_CASE_HASH_MISMATCH")
            if sha256_file(run_root / "labels" / "holdout.jsonl") != seal.get("labels_sha256"):
                reasons.append("HOLDOUT_LABEL_HASH_MISMATCH")
        candidate_inventory(run_root)
    except Exception as error:  # verification must return a complete failure record
        reasons.append(f"VERIFICATION_ERROR:{type(error).__name__}:{error}")
    result = {
        "schema": "BANKNIFTY_MARKET_PROFILE_LEARNING_RUN_VERIFICATION_V1",
        "valid": not reasons,
        "reasons": reasons or ["OK"],
    }
    atomic_json(run_root / "metadata" / "verification.json", result)
    return result
