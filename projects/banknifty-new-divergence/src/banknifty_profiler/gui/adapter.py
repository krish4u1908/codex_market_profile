"""Prepare compact, calculation-free R6D browser payloads.

The adapter projects sealed canonical records.  It does not infer market
states, move timestamps, or recalculate analytical values.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SESSIONS = (
    "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-18", "2026-08-19", "2026-08-20",
)
PRODUCT_CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _project(row: dict[str, str], fields: Iterable[str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in fields}


def _unique(rows: Iterable[dict[str, object]], fields: tuple[str, ...]) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    result = []
    for row in rows:
        key = tuple(row.get(field) for field in fields)
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def _pack(rows: list[dict[str, object]]) -> dict[str, object]:
    """Column contract plus arrays; lossless and substantially smaller JSON."""
    fields = list(dict.fromkeys(key for row in rows for key in row))
    return {"fields": fields, "rows": [[row.get(field, "") for field in fields] for row in rows]}


def source_contract(root: Path) -> dict[str, object]:
    files = {
        "inventory": root / "runs/stream_inventory/canonical_inventory.csv",
        "availability": root / "runs/stream_layers/layer_availability.csv",
        "cross_layer": root / "runs/stream_layers/canonical_cross_layer_transitions.csv",
        "episodes": root / "runs/stream_stack/native/raw_divergence_episodes.csv",
        "dependencies": root / "runs/stream_stack/native/raw_dependency_groups.csv",
        "lifecycle": root / "runs/stream_stack/native/raw_lifecycle_transitions.csv",
        "resolution": root / "runs/stream_stack/native/raw_resolution_observations.csv",
        "participation_dense": root / "runs/stream_stack/views/dense_participation_view.csv",
        "participation_transitions": root / "runs/stream_stack/views/transition_participation_ledger.csv",
        "participation_summary": root / "runs/stream_stack/views/episode_participation_summary.csv",
        "compatibility": root / "runs/stream_stack/views/legacy_compatibility_snapshot.csv",
    }
    missing = [str(path) for path in files.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"sealed R6C2R inputs missing: {missing}")
    return {
        "version": "R6D_GUI_INPUT_SCHEMA_V1",
        "source_root": str(root),
        "files": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in files.items()
        },
    }


def build_payload(root: Path, date: str) -> dict[str, object]:
    if date not in SESSIONS:
        raise ValueError(f"unverified session: {date}")
    contract = source_contract(root)
    paths = {name: Path(info["path"]) for name, info in contract["files"].items()}
    episodes = [row for row in _read(paths["episodes"]) if row["evaluation_date"] == date]
    episode_ids = {row["episode_id"] for row in episodes}
    dependencies = [row for row in _read(paths["dependencies"]) if row["episode_id"] in episode_ids]
    lifecycle = [row for row in _read(paths["lifecycle"]) if row["evaluation_date"] == date]
    resolution = [row for row in _read(paths["resolution"]) if row["evaluation_date"] == date]
    inventory = [row for row in _read(paths["inventory"]) if row["evaluation_date"] == date]
    availability = [row for row in _read(paths["availability"]) if row["evaluation_date"] == date]
    for row in availability:
        if row["availability_state"] == "MISSING_PRIOR_SESSION":
            row["availability_state"] = "INSUFFICIENT_PRIOR_SESSIONS"
    cross = [row for row in _read(paths["cross_layer"]) if row["evaluation_date"] == date]
    dense = [row for row in _read(paths["participation_dense"]) if row["evaluation_date"] == date]
    transitions = [row for row in _read(paths["participation_transitions"]) if row["episode_id"] in episode_ids]
    summaries = [row for row in _read(paths["participation_summary"]) if row["evaluation_date"] == date]
    compatibility = [row for row in _read(paths["compatibility"]) if row["episode_id"] in episode_ids]

    # Price records are projections of synchronized dense resolution rows.
    # Separate receipt clocks are retained; no row-number pairing occurs.
    price = _unique(({
        "t": row["timestamp"], "i": row["current_index"], "f": row["current_futures"],
        "b": row["current_basis"], "it": row["index_receipt_timestamp"],
        "ft": row["futures_receipt_timestamp"], "a": row["synchronization_age_ms"],
    } for row in resolution), ("t", "i", "f", "it", "ft"))
    price.sort(key=lambda row: (str(row["t"]), str(row["ft"]), str(row["it"])))

    # Dense mechanism values are compressed to material changes for display;
    # exact canonical timestamps and values remain unchanged.
    mechanism = []
    previous: dict[str, str] = {}
    for row in resolution:
        key = row["episode_id"]
        value = row["resolution_mechanism_native"]
        if previous.get(key) != value:
            mechanism.append(_project(row, (
                "episode_id", "timestamp", "availability_timestamp",
                "resolution_mechanism_native", "resolution_mechanism_compatibility",
                "signed_basis_convergence", "index_contribution", "futures_contribution",
                "new_extreme_flag", "stalled_extreme_duration_seconds",
            )))
            previous[key] = value

    payload = {
        "schema": "R6D_SESSION_PAYLOAD_V1",
        "classification": PRODUCT_CLASSIFICATION,
        "date": date,
        "session": {"start": f"{date}T09:15:00+05:30", "end": f"{date}T15:30:00+05:30"},
        "source_contract_hash": hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest(),
        "availability": availability,
        "price": _pack(price),
        "inventory": _pack(inventory),
        "episodes": _pack(episodes),
        "dependencies": _pack(dependencies),
        "lifecycle": _pack(lifecycle),
        "resolution_mechanisms": _pack(mechanism),
        "participation_dense": _pack([_project(row, (
            "view_record_kind", "colour", "episode_id", "evaluation_date", "observation_timestamp",
            "receipt_timestamp", "receipt_age_seconds", "symbol", "expiry", "option_type", "strike",
            "moneyness", "price", "premium", "oi", "delta_oi_1m", "delta_oi_3m", "delta_oi_5m",
            "price_change_1m", "price_change_3m", "price_change_5m", "premium_change_1m",
            "premium_change_3m", "premium_change_5m", "incremental_volume_5m", "volume_percentile",
            "volume_robust_z", "volume_spike", "volume_status", "stale", "inventory_state",
            "semantic_classification", "timing_cohort", "selection_reason",
        )) for row in dense]),
        "participation_transitions": _pack([_project(row, (
            "transition_id", "episode_id", "dependency_group_id", "component", "previous_state",
            "new_state", "effective_timestamp", "evidence_receipt_timestamp", "calculation_timestamp",
            "reason_code",
        )) for row in transitions]),
        "participation_summaries": _pack(summaries),
        "compatibility_snapshots": _pack(compatibility),
        "cross_layer_transitions": _pack([_project(row, (
            "transition_id", "effective_timestamp", "component", "previous_state", "new_state",
            "reason_code", "episode_id", "horizon", "family",
        )) for row in cross if row["component"] == "INVENTORY"]),
        "counts": {
            "episodes": len(episodes), "lifecycle": len(lifecycle), "resolution_dense": len(resolution),
            "participation_dense": len(dense), "participation_transitions": len(transitions),
            "inventory": len(inventory), "cross_layer": len(cross),
        },
    }
    return payload


def write_payload(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as handle:
            handle.write(compact)
