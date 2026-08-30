"""Deterministic forecasts, baselines, evaluation, and holdout gating."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Mapping, Sequence

from .candidates import validate_agent_spec
from .io_utils import (
    atomic_json,
    atomic_jsonl,
    canonical_json,
    finite,
    iter_jsonl,
    load_json,
    sha256_file,
    sha256_text,
)


CLASSES = ("UP", "DOWN", "ROTATION")


def _candidate_directories(run_root: Path) -> list[Path]:
    return sorted(
        path for path in (run_root / "candidates").iterdir()
        if path.is_dir()
        and (path / "references" / "agent-spec.json").is_file()
        and (path / "candidate_manifest.json").is_file()
    )


def candidate_inventory(run_root: Path) -> list[dict[str, object]]:
    result = []
    for path in _candidate_directories(run_root):
        manifest = load_json(path / "candidate_manifest.json")
        if not isinstance(manifest, Mapping):
            raise ValueError(f"{path}: candidate manifest is invalid")
        spec_path = path / "references" / "agent-spec.json"
        spec = validate_agent_spec(load_json(spec_path))
        actual = sha256_text(canonical_json(spec))
        if actual != manifest.get("agent_spec_sha256"):
            raise ValueError(f"{path}: candidate spec hash mismatch")
        bound_files = {
            "skill_sha256": path / "SKILL.md",
            "forecast_schema_sha256": path / "references" / "forecast.schema.json",
            "market_profile_semantics_sha256": (
                path / "references" / "market-profile-semantics.md"
            ),
        }
        for key, bound_path in bound_files.items():
            if not bound_path.is_file() or sha256_file(bound_path) != manifest.get(key):
                raise ValueError(f"{path}: candidate file binding failed for {key}")
        result.append({
            "candidate_id": str(manifest["candidate_id"]),
            "agent_spec_sha256": actual,
            "skill_sha256": str(manifest["skill_sha256"]),
            "origin": str(manifest.get("origin", "UNKNOWN")),
            "path": str(path),
            "spec": spec,
        })
    return result


def _holdout_gate(run_root: Path, *, open_holdout: bool) -> None:
    opened = run_root / "holdout" / "OPENED.json"
    inventory = [
        {
            "candidate_id": row["candidate_id"],
            "agent_spec_sha256": row["agent_spec_sha256"],
            "skill_sha256": row["skill_sha256"],
        }
        for row in candidate_inventory(run_root)
    ]
    inventory_hash = sha256_text(canonical_json(inventory))
    if opened.is_file():
        marker = load_json(opened)
        if not isinstance(marker, Mapping) or marker.get("candidate_inventory_sha256") != inventory_hash:
            raise RuntimeError("candidate inventory changed after holdout opening")
        return
    if not open_holdout:
        raise RuntimeError(
            "holdout remains sealed; repeat with --open-holdout only after validation review"
        )
    seal = load_json(run_root / "holdout" / "SEALED.json")
    if not isinstance(seal, Mapping):
        raise ValueError("holdout seal is invalid")
    if sha256_file(run_root / "cases" / "holdout.jsonl") != seal.get("cases_sha256"):
        raise RuntimeError("holdout cases changed after sealing")
    if sha256_file(run_root / "labels" / "holdout.jsonl") != seal.get("labels_sha256"):
        raise RuntimeError("holdout labels changed after sealing")
    atomic_json(opened, {
        "schema": "BANKNIFTY_MARKET_PROFILE_HOLDOUT_OPEN_V1",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "candidate_inventory": inventory,
        "candidate_inventory_sha256": inventory_hash,
        "cases_sha256": seal["cases_sha256"],
        "labels_sha256": seal["labels_sha256"],
        "state": "OPENED_ONCE_CANDIDATES_FROZEN",
    })


def _level_weights(spec: Mapping[str, object]) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    families = {
        str(row["family"]): float(row["weight"])
        for row in spec["level_family_weights"]
    }
    scopes = {str(key): float(value) for key, value in spec["level_scope_weights"].items()}
    kinds = {str(key): float(value) for key, value in spec["level_kind_weights"].items()}
    return families, scopes, kinds


def _rank_levels(
    case: Mapping[str, object], spec: Mapping[str, object]
) -> tuple[list[float], list[float]]:
    current = finite(case.get("market_context", {}).get("index_price"))
    if current is None:
        return [], []
    families, scopes, kinds = _level_weights(spec)
    rows = []
    for candidate in case.get("level_candidates", []):
        if not isinstance(candidate, Mapping):
            continue
        level = finite(candidate.get("level"))
        sources = candidate.get("sources")
        if level is None or not isinstance(sources, list):
            continue
        source_scores = []
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            source_scores.append(
                families.get(str(source.get("family")), 0.0)
                + scopes.get(str(source.get("scope")), 0.0)
                + kinds.get(str(source.get("kind")), 0.0)
            )
        base = max(source_scores, default=0.0)
        confluence = max(1, int(candidate.get("confluence", len(source_scores) or 1)))
        score = (
            base
            + float(spec["confluence_bonus"]) * (confluence - 1)
            - float(spec["distance_penalty"]) * abs(level - current) / 25.0
        )
        rows.append((level, score))
    maximum = 2
    supports = [
        level for level, _ in sorted(
            ((level, score) for level, score in rows if level <= current),
            key=lambda row: (-row[1], current - row[0], -row[0]),
        )[:maximum]
    ]
    resistances = [
        level for level, _ in sorted(
            ((level, score) for level, score in rows if level >= current),
            key=lambda row: (-row[1], row[0] - current, row[0]),
        )[:maximum]
    ]
    return supports, resistances


def _what_changed(case: Mapping[str, object]) -> str:
    pieces = []
    for row in case.get("shift_components", []):
        if not isinstance(row, Mapping):
            continue
        old, new = finite(row.get("previous_control")), finite(row.get("new_control"))
        if old is None or new is None:
            continue
        arrow = "higher" if new > old else "lower"
        pieces.append(f"{row.get('family')} {old:g}→{new:g} ({arrow})")
    return "; ".join(pieces) if pieces else "No validated control migration"


def forecast_case(
    case: Mapping[str, object],
    spec: Mapping[str, object],
    candidate_id: str,
    horizon: int,
) -> dict[str, object]:
    features = case.get("features")
    if not isinstance(features, Mapping):
        raise ValueError("case lacks normalized features")
    score = float(spec["direction_bias"]) + float(spec["horizon_bias"][str(horizon)])
    for row in spec["direction_weights"]:
        score += float(row["weight"]) * float(features.get(str(row["feature"]), 0.0))
    raw = case.get("features_raw", {})
    ages = [
        finite(raw.get(name))
        for name in ("option_flow_age_seconds", "futures_oi_age_seconds")
    ] if isinstance(raw, Mapping) else []
    present_ages = [max(0.0, value) for value in ages if value is not None]
    if present_ages:
        oldest = max(present_ages)
        freshness_factor = 1.0 if oldest <= 120.0 else max(0.1, 120.0 / oldest)
        score *= freshness_factor
    threshold = float(spec["neutral_score_threshold"])
    bias = "UP" if score > threshold else "DOWN" if score < -threshold else "ROTATION"
    confidence = min(
        float(spec["confidence_ceiling"]),
        max(
            float(spec["confidence_floor"]),
            float(spec["confidence_floor"])
            + float(spec["confidence_scale"]) * max(0.0, abs(score) - threshold),
        ),
    )
    supports, resistances = _rank_levels(case, spec)
    invalidation = (
        supports[0] if bias == "UP" and supports
        else resistances[0] if bias == "DOWN" and resistances
        else None
    )
    return {
        "schema": "BANKNIFTY_MARKET_PROFILE_FORECAST_V1",
        "case_id": str(case["case_id"]),
        "candidate_id": candidate_id,
        "candidate_spec_sha256": sha256_text(canonical_json(spec)),
        "horizon_minutes": horizon,
        "causal_cutoff": case["causal_cutoff"],
        "what_changed": _what_changed(case),
        "bias": bias,
        "direction_score": score,
        "support": supports,
        "resistance": resistances,
        "invalidation": invalidation,
        "confidence": confidence,
        "classification": "POSSIBLE_OUTCOME_RESEARCH_ONLY",
    }


def _baseline_forecast(
    case: Mapping[str, object], name: str, horizon: int
) -> dict[str, object]:
    raw = case.get("features_raw", {})
    if name == "baseline-no-edge":
        bias, score = "ROTATION", 0.0
    elif name == "baseline-momentum-5m":
        change = finite(raw.get("price_return_5m")) or 0.0
        bias = "UP" if change >= 25 else "DOWN" if change <= -25 else "ROTATION"
        score = change / 25.0
    elif name == "baseline-option-flow-balance":
        balance = finite(raw.get("pe_minus_ce_delta")) or 0.0
        bias = "UP" if balance > 0 else "DOWN" if balance < 0 else "ROTATION"
        score = 1.0 if balance > 0 else -1.0 if balance < 0 else 0.0
    else:
        raise ValueError(f"unknown baseline: {name}")
    current = finite(case.get("market_context", {}).get("index_price"))
    levels = sorted(float(row["level"]) for row in case.get("level_candidates", []))
    supports = [] if current is None else sorted((level for level in levels if level <= current), reverse=True)[:2]
    resistances = [] if current is None else sorted(level for level in levels if level >= current)[:2]
    return {
        "schema": "BANKNIFTY_MARKET_PROFILE_FORECAST_V1",
        "case_id": str(case["case_id"]),
        "candidate_id": name,
        "candidate_spec_sha256": None,
        "horizon_minutes": horizon,
        "causal_cutoff": case["causal_cutoff"],
        "what_changed": _what_changed(case),
        "bias": bias,
        "direction_score": score,
        "support": supports,
        "resistance": resistances,
        "invalidation": None,
        "confidence": 0.5,
        "classification": "POSSIBLE_OUTCOME_RESEARCH_ONLY",
    }


def _metrics(
    forecasts: Sequence[Mapping[str, object]],
    labels_by_case: Mapping[str, Mapping[str, object]],
    *,
    horizon: int,
    level_tolerance: float,
) -> dict[str, object]:
    paired = []
    for forecast in forecasts:
        label = labels_by_case.get(str(forecast["case_id"]))
        outcome = None if label is None else label.get("outcomes", {}).get(str(horizon))
        if isinstance(outcome, Mapping) and outcome.get("available") is True:
            paired.append((forecast, outcome))
    confusion: defaultdict[str, Counter[str]] = defaultdict(Counter)
    correct = 0
    brier_total = 0.0
    support_hits = 0
    support_opportunities = 0
    resistance_hits = 0
    resistance_opportunities = 0
    directional_predictions = 0
    for forecast, outcome in paired:
        actual, predicted = str(outcome["direction"]), str(forecast["bias"])
        confusion[actual][predicted] += 1
        correct += actual == predicted
        directional_predictions += predicted in {"UP", "DOWN"}
        confidence = float(forecast["confidence"])
        probabilities = {klass: (1.0 - confidence) / 2.0 for klass in CLASSES}
        probabilities[predicted] = confidence
        brier_total += sum(
            (probabilities[klass] - (1.0 if klass == actual else 0.0)) ** 2
            for klass in CLASSES
        ) / len(CLASSES)
        supports = [float(value) for value in forecast.get("support", [])]
        resistances = [float(value) for value in forecast.get("resistance", [])]
        if supports:
            support_opportunities += 1
            low = float(outcome["low_price"])
            support_hits += min(abs(level - low) for level in supports) <= level_tolerance
        if resistances:
            resistance_opportunities += 1
            high = float(outcome["high_price"])
            resistance_hits += min(abs(level - high) for level in resistances) <= level_tolerance
    recalls = []
    for klass in CLASSES:
        total = sum(confusion[klass].values())
        if total:
            recalls.append(confusion[klass][klass] / total)
    count = len(paired)
    balanced = sum(recalls) / len(recalls) if recalls else 0.0
    accuracy = correct / count if count else 0.0
    brier = brier_total / count if count else 1.0
    support_rate = support_hits / support_opportunities if support_opportunities else 0.0
    resistance_rate = resistance_hits / resistance_opportunities if resistance_opportunities else 0.0
    level_rate = (
        (support_hits + resistance_hits) / (support_opportunities + resistance_opportunities)
        if support_opportunities + resistance_opportunities else 0.0
    )
    composite = 0.65 * balanced + 0.20 * (1.0 - brier) + 0.15 * level_rate
    return {
        "cases": count,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "brier_score": brier,
        "directional_coverage": directional_predictions / count if count else 0.0,
        "support_extreme_hit_rate": support_rate,
        "support_opportunities": support_opportunities,
        "resistance_extreme_hit_rate": resistance_rate,
        "resistance_opportunities": resistance_opportunities,
        "level_extreme_hit_rate": level_rate,
        "composite_score": composite,
        "confusion": {
            actual: {predicted: confusion[actual][predicted] for predicted in CLASSES}
            for actual in CLASSES
        },
    }


def evaluate_split(
    run_root: Path,
    *,
    split: str,
    open_holdout: bool = False,
) -> dict[str, object]:
    if split not in {"train", "validation", "holdout"}:
        raise ValueError("split must be train, validation, or holdout")
    if split == "holdout":
        _holdout_gate(run_root, open_holdout=open_holdout)
    config = load_json(run_root / "metadata" / "learning_config.json")
    if not isinstance(config, Mapping):
        raise ValueError("learning configuration is invalid")
    cases = list(iter_jsonl(run_root / "cases" / f"{split}.jsonl"))
    labels = list(iter_jsonl(run_root / "labels" / f"{split}.jsonl"))
    labels_by_case = {str(row["case_id"]): row for row in labels}
    for case in cases:
        label = labels_by_case.get(str(case["case_id"]))
        if label is None or label.get("case_sha256") != sha256_text(canonical_json(case)):
            raise RuntimeError(f"case/label binding failed for {case.get('case_id')}")
    candidates = candidate_inventory(run_root)
    if not candidates:
        raise RuntimeError("no candidates are available")
    horizons = [int(value) for value in config["horizons_minutes"]]
    all_scores: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_forecasts = []
        for case in cases:
            for horizon in horizons:
                candidate_forecasts.append(
                    forecast_case(case, candidate["spec"], str(candidate["candidate_id"]), horizon)
                )
        atomic_jsonl(
            run_root / "forecasts" / f"{split}-{candidate['candidate_id']}.jsonl",
            candidate_forecasts,
        )
        for horizon in horizons:
            metrics = _metrics(
                [row for row in candidate_forecasts if row["horizon_minutes"] == horizon],
                labels_by_case,
                horizon=horizon,
                level_tolerance=float(config["level_touch_tolerance_points"]),
            )
            all_scores.append({
                "candidate_id": candidate["candidate_id"],
                "origin": candidate["origin"],
                "split": split,
                "horizon_minutes": horizon,
                **metrics,
            })
    for baseline in (
        "baseline-no-edge",
        "baseline-momentum-5m",
        "baseline-option-flow-balance",
    ):
        forecasts = [
            _baseline_forecast(case, baseline, horizon)
            for case in cases for horizon in horizons
        ]
        atomic_jsonl(run_root / "forecasts" / f"{split}-{baseline}.jsonl", forecasts)
        for horizon in horizons:
            metrics = _metrics(
                [row for row in forecasts if row["horizon_minutes"] == horizon],
                labels_by_case,
                horizon=horizon,
                level_tolerance=float(config["level_touch_tolerance_points"]),
            )
            all_scores.append({
                "candidate_id": baseline,
                "origin": "DETERMINISTIC_BASELINE",
                "split": split,
                "horizon_minutes": horizon,
                **metrics,
            })
    result = {
        "schema": "BANKNIFTY_MARKET_PROFILE_SCORECARD_V1",
        "classification": config["classification"],
        "split": split,
        "session_count": len(config["splits"][split]),
        "episode_count": len(cases),
        "scores": all_scores,
        "metric_boundary": {
            "effective_sample_unit": "SESSION_DATE",
            "level_metric": "PREDICTED_LEVEL_WITHIN_TOLERANCE_OF_FUTURE_PATH_EXTREME",
            "level_metric_is_not": "PROOF_OF_SUPPORT_OR_RESISTANCE_CAUSATION",
            "composite": "0.65*balanced_accuracy + 0.20*(1-brier) + 0.15*level_extreme_hit_rate",
        },
    }
    atomic_json(run_root / "scores" / f"{split}.json", result)
    if split == "validation":
        _select_validation_candidate(run_root, result)
    return result


def _select_validation_candidate(run_root: Path, scorecard: Mapping[str, object]) -> None:
    rows = scorecard.get("scores", [])
    by_candidate: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, Mapping):
            by_candidate[str(row["candidate_id"])].append(row)
    aggregates = []
    for candidate_id, values in sorted(by_candidate.items()):
        aggregates.append({
            "candidate_id": candidate_id,
            "origin": values[0]["origin"],
            "mean_balanced_accuracy": sum(float(row["balanced_accuracy"]) for row in values) / len(values),
            "mean_brier_score": sum(float(row["brier_score"]) for row in values) / len(values),
            "mean_level_extreme_hit_rate": sum(float(row["level_extreme_hit_rate"]) for row in values) / len(values),
            "mean_composite_score": sum(float(row["composite_score"]) for row in values) / len(values),
        })
    baselines = [row for row in aggregates if row["origin"] == "DETERMINISTIC_BASELINE"]
    candidates = [row for row in aggregates if row["origin"] != "DETERMINISTIC_BASELINE"]
    best_baseline = max(baselines, key=lambda row: row["mean_composite_score"])
    best_candidate = max(candidates, key=lambda row: row["mean_composite_score"])
    passes = (
        best_candidate["mean_composite_score"] > best_baseline["mean_composite_score"]
        and best_candidate["mean_balanced_accuracy"] > best_baseline["mean_balanced_accuracy"]
    )
    atomic_json(run_root / "scores" / "validation_selection.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_VALIDATION_SELECTION_V1",
        "aggregates": aggregates,
        "best_baseline": best_baseline,
        "best_candidate": best_candidate,
        "candidate_passes_relative_gate": passes,
        "decision": "ELIGIBLE_FOR_HOLDOUT_REVIEW" if passes else "NO_CANDIDATE_EDGE_ON_VALIDATION",
        "automatic_production_promotion": False,
    })
