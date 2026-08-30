"""Deterministic forecasts, baselines, evaluation, and holdout gating."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path
import random
import shutil
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


def import_frozen_candidates(
    run_root: Path,
    *,
    source_run: Path,
    candidate_ids: Sequence[str],
) -> list[dict[str, object]]:
    """Copy exact, already-bound candidates into a new sealed evaluation run."""
    if (run_root / "holdout" / "OPENED.json").exists():
        raise RuntimeError("candidate import is forbidden after holdout opening")
    requested = list(dict.fromkeys(str(value) for value in candidate_ids))
    if not requested:
        raise ValueError("at least one candidate id is required")
    source = {str(row["candidate_id"]): row for row in candidate_inventory(source_run)}
    missing = sorted(set(requested) - set(source))
    if missing:
        raise ValueError(f"source run lacks candidates: {missing}")
    imported = []
    for candidate_id in requested:
        source_path = Path(str(source[candidate_id]["path"]))
        destination = run_root / "candidates" / candidate_id
        if destination.exists():
            existing = next(
                (row for row in candidate_inventory(run_root) if row["candidate_id"] == candidate_id),
                None,
            )
            if existing is None or existing["agent_spec_sha256"] != source[candidate_id]["agent_spec_sha256"]:
                raise FileExistsError(f"candidate collision: {destination}")
        else:
            shutil.copytree(source_path, destination)
        imported.append({
            "candidate_id": candidate_id,
            "agent_spec_sha256": source[candidate_id]["agent_spec_sha256"],
            "skill_sha256": source[candidate_id]["skill_sha256"],
            "origin": source[candidate_id]["origin"],
        })
    source_manifest = load_json(source_run / "metadata" / "input_manifest.json")
    atomic_json(run_root / "metadata" / "frozen_candidate_import.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_FROZEN_CANDIDATE_IMPORT_V1",
        "source_input_manifest_sha256": (
            source_manifest.get("manifest_sha256")
            if isinstance(source_manifest, Mapping) else None
        ),
        "candidates": imported,
        "candidate_inventory_sha256": sha256_text(canonical_json(imported)),
        "rule": "IMPORTED_CANDIDATES_ARE_BYTE_IDENTICAL_AND_MUST_NOT_BE_REGENERATED",
    })
    return imported


def _holdout_gate(
    run_root: Path, *, open_holdout: bool
) -> list[dict[str, object]]:
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
    selection_path = run_root / "scores" / "validation_selection.json"
    if opened.is_file():
        marker = load_json(opened)
        if not isinstance(marker, Mapping) or marker.get("candidate_inventory_sha256") != inventory_hash:
            raise RuntimeError("candidate inventory changed after holdout opening")
        if not selection_path.is_file() or marker.get("validation_selection_sha256") != sha256_file(selection_path):
            raise RuntimeError("validation selection changed after holdout opening")
        selected = marker.get("selected_specialists")
        if not isinstance(selected, list) or not selected:
            raise RuntimeError("holdout marker lacks selected specialists")
        return [dict(row) for row in selected if isinstance(row, Mapping)]
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
    selection = load_json(selection_path)
    if not isinstance(selection, Mapping) or selection.get("schema") != "BANKNIFTY_MARKET_PROFILE_VALIDATION_SELECTION_V2":
        raise RuntimeError("V0.1.3 validation selection is unavailable")
    selected = selection.get("eligible_specialists")
    if not isinstance(selected, list) or not selected:
        raise RuntimeError("no horizon specialist is eligible for holdout review")
    selected_rows = [dict(row) for row in selected if isinstance(row, Mapping)]
    if len(selected_rows) != len(selected):
        raise RuntimeError("eligible specialist inventory is invalid")
    atomic_json(opened, {
        "schema": "BANKNIFTY_MARKET_PROFILE_HOLDOUT_OPEN_V1",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "candidate_inventory": inventory,
        "candidate_inventory_sha256": inventory_hash,
        "cases_sha256": seal["cases_sha256"],
        "labels_sha256": seal["labels_sha256"],
        "validation_selection_sha256": sha256_file(selection_path),
        "selected_specialists": selected_rows,
        "state": "OPENED_ONCE_CANDIDATES_FROZEN",
    })
    return selected_rows


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


def _level_test(
    levels: Sequence[float],
    outcome: Mapping[str, object],
    *,
    side: str,
    tolerance: float,
    reaction_points: float,
    breach_points: float,
) -> dict[str, object]:
    path_value = outcome.get("ordered_future_path")
    if not levels or not isinstance(path_value, list):
        return {"status": "UNTESTED", "level": None, "touch_timestamp": None}
    path: list[tuple[str, float]] = []
    for row in path_value:
        if not isinstance(row, Mapping):
            continue
        price = finite(row.get("p"))
        if price is not None:
            path.append((str(row.get("t")), price))
    first: tuple[int, int, float] | None = None
    for rank, level in enumerate(levels):
        for position, (_, price) in enumerate(path):
            touched = price <= level + tolerance if side == "support" else price >= level - tolerance
            if touched:
                candidate = (position, rank, level)
                if first is None or candidate[:2] < first[:2]:
                    first = candidate
                break
    if first is None:
        return {"status": "UNTESTED", "level": None, "touch_timestamp": None}
    position, _, level = first
    touch_timestamp = path[position][0]
    for timestamp, price in path[position:]:
        if side == "support":
            reaction = price >= level + reaction_points
            breach = price <= level - breach_points
        else:
            reaction = price <= level - reaction_points
            breach = price >= level + breach_points
        if reaction and breach:
            return {
                "status": "AMBIGUOUS_SAME_RECEIPT",
                "level": level,
                "touch_timestamp": touch_timestamp,
                "resolved_timestamp": timestamp,
            }
        if reaction:
            return {
                "status": "REACTION_BEFORE_BREACH",
                "level": level,
                "touch_timestamp": touch_timestamp,
                "resolved_timestamp": timestamp,
            }
        if breach:
            return {
                "status": "BREACH_BEFORE_REACTION",
                "level": level,
                "touch_timestamp": touch_timestamp,
                "resolved_timestamp": timestamp,
            }
    return {
        "status": "TOUCHED_UNRESOLVED",
        "level": level,
        "touch_timestamp": touch_timestamp,
        "resolved_timestamp": None,
    }


def _calibration_bins(rows: Sequence[tuple[float, bool]]) -> list[dict[str, object]]:
    buckets: defaultdict[int, list[tuple[float, bool]]] = defaultdict(list)
    for confidence, correct in rows:
        buckets[min(9, max(0, int(confidence * 10)))].append((confidence, correct))
    return [
        {
            "lower": bucket / 10.0,
            "upper": (bucket + 1) / 10.0,
            "count": len(values),
            "mean_confidence": sum(value for value, _ in values) / len(values),
            "accuracy": sum(correct for _, correct in values) / len(values),
        }
        for bucket, values in sorted(buckets.items())
    ]


def _metrics(
    forecasts: Sequence[Mapping[str, object]],
    labels_by_case: Mapping[str, Mapping[str, object]],
    *,
    horizon: int,
    level_tolerance: float,
    reaction_points: float,
    breach_points: float,
) -> dict[str, object]:
    paired = []
    for forecast in forecasts:
        label = labels_by_case.get(str(forecast["case_id"]))
        outcome = None if label is None else label.get("outcomes", {}).get(str(horizon))
        if isinstance(label, Mapping) and isinstance(outcome, Mapping) and outcome.get("available") is True:
            paired.append((forecast, outcome, str(label.get("session"))))
    confusion: defaultdict[str, Counter[str]] = defaultdict(Counter)
    class_support: Counter[str] = Counter()
    correct = 0
    brier_total = 0.0
    support_hits = 0
    support_opportunities = 0
    resistance_hits = 0
    resistance_opportunities = 0
    directional_predictions = 0
    calibration: list[tuple[float, bool]] = []
    level_status: Counter[str] = Counter()
    support_status: Counter[str] = Counter()
    resistance_status: Counter[str] = Counter()
    for forecast, outcome, _ in paired:
        actual, predicted = str(outcome["direction"]), str(forecast["bias"])
        confusion[actual][predicted] += 1
        class_support[actual] += 1
        correct += actual == predicted
        directional_predictions += predicted in {"UP", "DOWN"}
        confidence = float(forecast["confidence"])
        calibration.append((confidence, actual == predicted))
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
        for side, levels, counter in (
            ("support", supports, support_status),
            ("resistance", resistances, resistance_status),
        ):
            status = str(_level_test(
                levels,
                outcome,
                side=side,
                tolerance=level_tolerance,
                reaction_points=reaction_points,
                breach_points=breach_points,
            )["status"])
            counter[status] += 1
            level_status[status] += 1
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
    tested = sum(
        level_status[status]
        for status in (
            "REACTION_BEFORE_BREACH",
            "BREACH_BEFORE_REACTION",
            "TOUCHED_UNRESOLVED",
            "AMBIGUOUS_SAME_RECEIPT",
        )
    )
    reactions = level_status["REACTION_BEFORE_BREACH"]
    breaches = level_status["BREACH_BEFORE_REACTION"]
    composite = 0.65 * balanced + 0.20 * (1.0 - brier) + 0.15 * level_rate
    return {
        "cases": count,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "brier_score": brier,
        "directional_coverage": directional_predictions / count if count else 0.0,
        "neutral_prediction_rate": 1.0 - directional_predictions / count if count else 0.0,
        "class_support": {klass: class_support[klass] for klass in CLASSES},
        "present_actual_classes": sum(class_support[klass] > 0 for klass in CLASSES),
        "support_extreme_hit_rate": support_rate,
        "support_opportunities": support_opportunities,
        "resistance_extreme_hit_rate": resistance_rate,
        "resistance_opportunities": resistance_opportunities,
        "level_extreme_hit_rate": level_rate,
        "level_reaction_tested": tested,
        "level_reaction_rate": reactions / tested if tested else 0.0,
        "level_breach_rate": breaches / tested if tested else 0.0,
        "level_reaction_status": dict(sorted(level_status.items())),
        "support_reaction_status": dict(sorted(support_status.items())),
        "resistance_reaction_status": dict(sorted(resistance_status.items())),
        "calibration_bins": _calibration_bins(calibration),
        "composite_score": composite,
        "confusion": {
            actual: {predicted: confusion[actual][predicted] for predicted in CLASSES}
            for actual in CLASSES
        },
    }


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _session_diagnostics(
    forecasts: Sequence[Mapping[str, object]],
    labels_by_case: Mapping[str, Mapping[str, object]],
    *,
    horizon: int,
    level_tolerance: float,
    reaction_points: float,
    breach_points: float,
    bootstrap_replicates: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    by_session: defaultdict[str, list[Mapping[str, object]]] = defaultdict(list)
    for forecast in forecasts:
        label = labels_by_case.get(str(forecast["case_id"]))
        if isinstance(label, Mapping):
            by_session[str(label.get("session"))].append(forecast)
    sessions = sorted(by_session)

    def score(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
        return _metrics(
            rows,
            labels_by_case,
            horizon=horizon,
            level_tolerance=level_tolerance,
            reaction_points=reaction_points,
            breach_points=breach_points,
        )

    per_session = []
    for session in sessions:
        metrics = score(by_session[session])
        per_session.append({
            "session": session,
            "cases": metrics["cases"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "brier_score": metrics["brier_score"],
            "directional_coverage": metrics["directional_coverage"],
            "level_reaction_tested": metrics["level_reaction_tested"],
            "level_reaction_rate": metrics["level_reaction_rate"],
            "composite_score": metrics["composite_score"],
        })
    leave_one_out = []
    if len(sessions) > 1:
        for omitted in sessions:
            rows = [
                row for session in sessions if session != omitted
                for row in by_session[session]
            ]
            metrics = score(rows)
            leave_one_out.append({
                "omitted_session": omitted,
                "balanced_accuracy": metrics["balanced_accuracy"],
                "brier_score": metrics["brier_score"],
                "level_reaction_rate": metrics["level_reaction_rate"],
                "composite_score": metrics["composite_score"],
            })
    samples: defaultdict[str, list[float]] = defaultdict(list)
    if sessions and bootstrap_replicates > 0:
        generator = random.Random(bootstrap_seed)
        for _ in range(bootstrap_replicates):
            selected = [generator.choice(sessions) for _ in sessions]
            rows = [row for session in selected for row in by_session[session]]
            metrics = score(rows)
            for key in (
                "balanced_accuracy", "brier_score", "level_reaction_rate", "composite_score"
            ):
                samples[key].append(float(metrics[key]))
    intervals = {
        key: {
            "lower_2_5": _percentile(values, 0.025),
            "median": _percentile(values, 0.5),
            "upper_97_5": _percentile(values, 0.975),
        }
        for key, values in sorted(samples.items())
    }
    return {
        "effective_sample_unit": "SESSION_DATE",
        "sessions": per_session,
        "leave_one_session_out": leave_one_out,
        "session_bootstrap": {
            "replicates": bootstrap_replicates,
            "seed": bootstrap_seed,
            "intervals": intervals,
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
    selected_specialists: list[dict[str, object]] = []
    if split == "holdout":
        selected_specialists = _holdout_gate(run_root, open_holdout=open_holdout)
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
    gate = config["evaluation_v013"]
    level_tolerance = float(config["level_touch_tolerance_points"])
    reaction_points = float(config["level_reaction_points"])
    breach_points = float(config["level_breach_points"])
    bootstrap_replicates = int(gate["session_bootstrap_replicates"])
    base_bootstrap_seed = int(gate["session_bootstrap_seed"])
    selected_by_candidate: defaultdict[str, set[int]] = defaultdict(set)
    for row in selected_specialists:
        selected_by_candidate[str(row["candidate_id"])].add(int(row["horizon_minutes"]))
    all_scores: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_horizons = (
            sorted(selected_by_candidate.get(str(candidate["candidate_id"]), set()))
            if split == "holdout" else horizons
        )
        if not candidate_horizons:
            continue
        candidate_forecasts = []
        for case in cases:
            for horizon in candidate_horizons:
                candidate_forecasts.append(
                    forecast_case(case, candidate["spec"], str(candidate["candidate_id"]), horizon)
                )
        atomic_jsonl(
            run_root / "forecasts" / f"{split}-{candidate['candidate_id']}.jsonl",
            candidate_forecasts,
        )
        for horizon in candidate_horizons:
            horizon_forecasts = [
                row for row in candidate_forecasts if row["horizon_minutes"] == horizon
            ]
            metrics = _metrics(
                horizon_forecasts,
                labels_by_case,
                horizon=horizon,
                level_tolerance=level_tolerance,
                reaction_points=reaction_points,
                breach_points=breach_points,
            )
            diagnostics = _session_diagnostics(
                horizon_forecasts,
                labels_by_case,
                horizon=horizon,
                level_tolerance=level_tolerance,
                reaction_points=reaction_points,
                breach_points=breach_points,
                bootstrap_replicates=bootstrap_replicates,
                bootstrap_seed=base_bootstrap_seed + int(sha256_text(
                    f"{split}|{candidate['candidate_id']}|{horizon}"
                )[:8], 16),
            )
            all_scores.append({
                "candidate_id": candidate["candidate_id"],
                "origin": candidate["origin"],
                "split": split,
                "horizon_minutes": horizon,
                **metrics,
                "session_diagnostics": diagnostics,
            })
    baseline_horizons = (
        sorted({int(row["horizon_minutes"]) for row in selected_specialists})
        if split == "holdout" else horizons
    )
    for baseline in (
        "baseline-no-edge",
        "baseline-momentum-5m",
        "baseline-option-flow-balance",
    ):
        forecasts = [
            _baseline_forecast(case, baseline, horizon)
            for case in cases for horizon in baseline_horizons
        ]
        atomic_jsonl(run_root / "forecasts" / f"{split}-{baseline}.jsonl", forecasts)
        for horizon in baseline_horizons:
            horizon_forecasts = [row for row in forecasts if row["horizon_minutes"] == horizon]
            metrics = _metrics(
                horizon_forecasts,
                labels_by_case,
                horizon=horizon,
                level_tolerance=level_tolerance,
                reaction_points=reaction_points,
                breach_points=breach_points,
            )
            diagnostics = _session_diagnostics(
                horizon_forecasts,
                labels_by_case,
                horizon=horizon,
                level_tolerance=level_tolerance,
                reaction_points=reaction_points,
                breach_points=breach_points,
                bootstrap_replicates=bootstrap_replicates,
                bootstrap_seed=base_bootstrap_seed + int(sha256_text(
                    f"{split}|{baseline}|{horizon}"
                )[:8], 16),
            )
            all_scores.append({
                "candidate_id": baseline,
                "origin": "DETERMINISTIC_BASELINE",
                "split": split,
                "horizon_minutes": horizon,
                **metrics,
                "session_diagnostics": diagnostics,
            })
    result = {
        "schema": "BANKNIFTY_MARKET_PROFILE_SCORECARD_V2",
        "classification": config["classification"],
        "split": split,
        "session_count": len(config["splits"][split]),
        "episode_count": len(cases),
        "scores": all_scores,
        "metric_boundary": {
            "effective_sample_unit": "SESSION_DATE",
            "level_metric": "PREDICTED_LEVEL_WITHIN_TOLERANCE_OF_FUTURE_PATH_EXTREME",
            "level_metric_is_not": "PROOF_OF_SUPPORT_OR_RESISTANCE_CAUSATION",
            "reaction_metric": "TOUCH_THEN_REACTION_BEFORE_BREACH_USING_ORDERED_FUTURE_RECEIPTS",
            "composite": "0.65*balanced_accuracy + 0.20*(1-brier) + 0.15*level_extreme_hit_rate",
            "selection_unit": "HORIZON_SPECIALIST_WITH_SESSION_STABILITY",
        },
    }
    atomic_json(run_root / "scores" / f"{split}.json", result)
    if split == "validation":
        _select_validation_candidate(run_root, result, config)
    return result


def _select_validation_candidate(
    run_root: Path,
    scorecard: Mapping[str, object],
    config: Mapping[str, object],
) -> None:
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
    gate = config["evaluation_v013"]
    allowlist = gate.get("horizon_candidate_allowlist", {})
    horizon_selection = []
    eligible_specialists = []
    for horizon in (5, 15, 30):
        horizon_rows = [
            row for row in rows
            if isinstance(row, Mapping) and int(row["horizon_minutes"]) == horizon
        ]
        horizon_baselines = [
            row for row in horizon_rows if row["origin"] == "DETERMINISTIC_BASELINE"
        ]
        horizon_candidates = [
            row for row in horizon_rows if row["origin"] != "DETERMINISTIC_BASELINE"
        ]
        if str(horizon) in allowlist:
            permitted = {str(value) for value in allowlist[str(horizon)]}
            horizon_candidates = [
                row for row in horizon_candidates if str(row["candidate_id"]) in permitted
            ]
        best_horizon_baseline = max(
            horizon_baselines, key=lambda row: float(row["composite_score"])
        )
        if not horizon_candidates:
            horizon_selection.append({
                "horizon_minutes": horizon,
                "eligible": False,
                "candidate_id": None,
                "baseline_id": best_horizon_baseline["candidate_id"],
                "reasons": ["NO_PREDECLARED_CANDIDATE"],
            })
            continue
        best_horizon_candidate = max(
            horizon_candidates, key=lambda row: float(row["composite_score"])
        )
        candidate_sessions = {
            str(row["session"]): row
            for row in best_horizon_candidate["session_diagnostics"]["sessions"]
        }
        baseline_sessions = {
            str(row["session"]): row
            for row in best_horizon_baseline["session_diagnostics"]["sessions"]
        }
        shared_sessions = sorted(set(candidate_sessions) & set(baseline_sessions))
        session_wins = sum(
            float(candidate_sessions[session]["composite_score"])
            > float(baseline_sessions[session]["composite_score"])
            for session in shared_sessions
        )
        session_win_fraction = session_wins / len(shared_sessions) if shared_sessions else 0.0
        candidate_loo = {
            str(row["omitted_session"]): row
            for row in best_horizon_candidate["session_diagnostics"]["leave_one_session_out"]
        }
        baseline_loo = {
            str(row["omitted_session"]): row
            for row in best_horizon_baseline["session_diagnostics"]["leave_one_session_out"]
        }
        shared_loo = sorted(set(candidate_loo) & set(baseline_loo))
        loo_passes = 0
        for omitted in shared_loo:
            candidate_row, baseline_row = candidate_loo[omitted], baseline_loo[omitted]
            loo_passes += (
                float(candidate_row["balanced_accuracy"])
                - float(baseline_row["balanced_accuracy"])
                >= float(gate["minimum_balanced_accuracy_margin"])
                and float(candidate_row["composite_score"])
                - float(baseline_row["composite_score"])
                >= float(gate["minimum_composite_margin"])
                and float(candidate_row["brier_score"])
                - float(baseline_row["brier_score"])
                <= float(gate["maximum_brier_worsening"])
            )
        loo_pass_fraction = loo_passes / len(shared_loo) if shared_loo else 0.0
        margins = {
            "balanced_accuracy": (
                float(best_horizon_candidate["balanced_accuracy"])
                - float(best_horizon_baseline["balanced_accuracy"])
            ),
            "brier_worsening": (
                float(best_horizon_candidate["brier_score"])
                - float(best_horizon_baseline["brier_score"])
            ),
            "composite": (
                float(best_horizon_candidate["composite_score"])
                - float(best_horizon_baseline["composite_score"])
            ),
            "level_reaction_rate": (
                float(best_horizon_candidate["level_reaction_rate"])
                - float(best_horizon_baseline["level_reaction_rate"])
            ),
        }
        checks = {
            "balanced_accuracy_margin": (
                margins["balanced_accuracy"]
                >= float(gate["minimum_balanced_accuracy_margin"])
            ),
            "composite_margin": (
                margins["composite"] >= float(gate["minimum_composite_margin"])
            ),
            "brier_not_worse": (
                margins["brier_worsening"] <= float(gate["maximum_brier_worsening"])
            ),
            "session_win_fraction": (
                session_win_fraction >= float(gate["minimum_session_win_fraction"])
            ),
            "leave_one_session_out": (
                loo_pass_fraction >= float(gate["minimum_loo_pass_fraction"])
            ),
            "directional_coverage": (
                float(best_horizon_candidate["directional_coverage"])
                >= float(gate["minimum_directional_coverage"])
            ),
            "actual_class_support": (
                int(best_horizon_candidate["present_actual_classes"])
                >= int(gate["minimum_present_actual_classes"])
            ),
            "level_reaction_tests": (
                int(best_horizon_candidate["level_reaction_tested"])
                >= int(gate["minimum_level_reaction_tests"])
            ),
            "level_reaction_rate_margin": (
                margins["level_reaction_rate"]
                >= float(gate["minimum_level_reaction_rate_margin"])
            ),
        }
        eligible = all(checks.values())
        row = {
            "horizon_minutes": horizon,
            "candidate_id": best_horizon_candidate["candidate_id"],
            "candidate_origin": best_horizon_candidate["origin"],
            "baseline_id": best_horizon_baseline["candidate_id"],
            "eligible": eligible,
            "margins": margins,
            "session_wins": session_wins,
            "session_count": len(shared_sessions),
            "session_win_fraction": session_win_fraction,
            "loo_passes": loo_passes,
            "loo_count": len(shared_loo),
            "loo_pass_fraction": loo_pass_fraction,
            "checks": checks,
            "reasons": sorted(key for key, value in checks.items() if not value) or ["OK"],
        }
        horizon_selection.append(row)
        if eligible:
            eligible_specialists.append({
                "candidate_id": best_horizon_candidate["candidate_id"],
                "horizon_minutes": horizon,
                "baseline_id": best_horizon_baseline["candidate_id"],
            })
    contract = {
        key: gate[key]
        for key in sorted(gate)
    }
    atomic_json(run_root / "scores" / "validation_selection.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_VALIDATION_SELECTION_V2",
        "aggregates": aggregates,
        "best_baseline": best_baseline,
        "best_candidate": best_candidate,
        "candidate_passes_relative_gate": passes,
        "legacy_aggregate_decision": (
            "ELIGIBLE_FOR_HOLDOUT_REVIEW" if passes
            else "NO_CANDIDATE_EDGE_ON_VALIDATION"
        ),
        "evaluation_contract": contract,
        "evaluation_contract_sha256": sha256_text(canonical_json(contract)),
        "horizon_selection": horizon_selection,
        "eligible_specialists": eligible_specialists,
        "decision": (
            "HORIZON_SPECIALIST_ELIGIBLE_FOR_HOLDOUT_REVIEW"
            if eligible_specialists else "NO_HORIZON_SPECIALIST_EDGE_ON_VALIDATION"
        ),
        "automatic_production_promotion": False,
    })
