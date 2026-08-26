"""Sanitized, read-only HTTP projection for the R6E live shadow.

The live analytical state contains raw lineage needed for audit and restart.
None of that lineage belongs in a browser response. This module therefore
uses explicit field allowlists for every public artifact and never serializes
an analytical snapshot, ledger row, exception, or configuration wholesale.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from inspect import signature
from urllib.parse import parse_qs, urlparse

from banknifty_profiler.gui.adapter import PRODUCT_CLASSIFICATION, SESSIONS
from banknifty_profiler.runtime.timestamps import parse_timestamp


STATIC_ROOT = Path(__file__).resolve().parents[1] / "gui" / "static"
STATIC_ROUTES = {
    "/": ("live_page.template", "text/html; charset=utf-8"),
    "/live": ("live_page.template", "text/html; charset=utf-8"),
    "/assets/live.js": ("live.js", "text/javascript; charset=utf-8"),
    "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
}

PRICE_FIELDS = ("t", "i", "f", "b", "it", "ft", "a")
INVENTORY_FIELDS = (
    "evaluation_date", "horizon", "family", "sign", "control_value",
    "control_effective_timestamp", "winner_change_timestamp",
    "snapshot_timestamp", "freshness_receipt_timestamp",
    "last_contributing_change_timestamp", "contract", "expiry",
    "eligible_observation_count", "excluded_observation_count",
    "tie_break_reason", "authority_basis", "canonical_control_name",
    "user_facing_label", "canonical_revision",
)
EPISODE_FIELDS = (
    "episode_id", "evaluation_date", "colour", "candidate_start_timestamp",
    "confirmation_timestamp", "episode_end_timestamp",
    "index_at_confirmation", "futures_at_confirmation",
    "basis_at_confirmation", "index_receipt_timestamp",
    "futures_receipt_timestamp",
)
DEPENDENCY_FIELDS = (
    "episode_id", "dependency_group_id", "classification", "retrigger_flag",
    "previous_episode_id", "reason_code",
)
LIFECYCLE_FIELDS = (
    "record_id", "episode_id", "dependency_group_id", "evaluation_date",
    "colour", "previous_state", "state", "state_entry_timestamp",
    "state_exit_timestamp", "reason_code", "causal_input_cutoff",
)
RESOLUTION_FIELDS = (
    "episode_id", "timestamp", "availability_timestamp",
    "resolution_mechanism_native", "resolution_mechanism_compatibility",
    "signed_basis_convergence", "index_contribution", "futures_contribution",
    "new_extreme_flag", "stalled_extreme_duration_seconds",
)
PARTICIPATION_FIELDS = (
    "view_record_kind", "colour", "episode_id", "evaluation_date",
    "observation_timestamp", "receipt_timestamp", "receipt_age_seconds",
    "record_id", "stale", "symbol", "expiry", "option_type", "strike",
    "moneyness", "price", "premium", "oi", "delta_oi_1m", "delta_oi_3m",
    "delta_oi_5m", "price_change_1m", "price_change_3m", "price_change_5m",
    "premium_change_1m", "premium_change_3m", "premium_change_5m",
    "incremental_volume_5m", "volume_percentile", "volume_robust_z",
    "volume_spike", "volume_status", "inventory_state",
    "semantic_classification", "timing_cohort", "selection_reason",
)
PARTICIPATION_TRANSITION_FIELDS = (
    "transition_id", "episode_id", "dependency_group_id", "component",
    "previous_state", "new_state", "effective_timestamp",
    "evidence_receipt_timestamp", "calculation_timestamp", "reason_code",
)
SUMMARY_FIELDS = (
    "episode_id", "dependency_group_id", "evaluation_date", "colour",
    "confirmation_timestamp", "latest_observation_timestamp",
    "futures_state", "ce_state", "pe_state", "overall_participation_state",
)
CROSS_LAYER_FIELDS = (
    "transition_id", "evaluation_date", "effective_timestamp", "component",
    "state_key", "previous_state", "new_state", "reason_code", "episode_id",
    "horizon", "family",
)

ARTIFACT_SPECS = {
    "inventory": ("inventory", INVENTORY_FIELDS),
    "episodes": ("episodes", EPISODE_FIELDS),
    "dependencies": ("dependencies", DEPENDENCY_FIELDS),
    "lifecycle": ("lifecycle", LIFECYCLE_FIELDS),
    "resolution_mechanisms": ("resolution", RESOLUTION_FIELDS),
    "participation_dense": ("participation_dense", PARTICIPATION_FIELDS),
    "participation_transitions": (
        "participation_transitions", PARTICIPATION_TRANSITION_FIELDS,
    ),
    "participation_summaries": ("participation_summaries", SUMMARY_FIELDS),
    "cross_layer_transitions": ("cross_layer_transitions", CROSS_LAYER_FIELDS),
}


def _primitive(value: object) -> object:
    """Return a JSON primitive without invoking an object's custom encoder."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _primitive(item())
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _project(row: Mapping[str, object], fields: Sequence[str]) -> dict[str, object]:
    return {field: _primitive(row.get(field)) for field in fields if field in row}


def _unpack(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if not isinstance(value, Mapping):
        return []
    fields = value.get("fields", [])
    rows = value.get("rows", [])
    if not isinstance(fields, list) or not isinstance(rows, list):
        return []
    names = [str(field) for field in fields]
    result = []
    for values in rows:
        if isinstance(values, Mapping):
            result.append(dict(values))
        elif isinstance(values, list):
            result.append(dict(zip(names, values)))
    return result


def _pack(rows: Iterable[Mapping[str, object]], fields: Sequence[str]) -> dict[str, object]:
    projected = [_project(row, fields) for row in rows]
    return {
        "fields": list(fields),
        "rows": [[row.get(field) for field in fields] for row in projected],
    }


def _read_snapshot(callable_: object, session_date: str | None = None) -> object:
    """Read a sealed snapshot while explicitly suppressing dirty-session work."""
    if not callable(callable_):
        return {}
    parameters = signature(callable_).parameters
    kwargs = {"flush_dirty": False} if "flush_dirty" in parameters else {}
    return callable_(session_date, **kwargs) if session_date else callable_(**kwargs)


def _snapshot(state: object, session_date: str | None = None) -> Mapping[str, object]:
    orchestrator = getattr(state, "orchestrator", None)
    snapshot = getattr(orchestrator, "snapshot", None)
    if callable(snapshot):
        value = _read_snapshot(snapshot, session_date)
    elif session_date:
        value = {}
    else:
        value = state.analytical_snapshot()
    return value if isinstance(value, Mapping) else {}


def _gui(snapshot: Mapping[str, object]) -> Mapping[str, object]:
    value = snapshot.get("gui_payload", {})
    return value if isinstance(value, Mapping) else {}


def _artifact_rows(
    snapshot: Mapping[str, object], gui: Mapping[str, object], name: str,
) -> list[dict[str, object]]:
    snapshot_name, _ = ARTIFACT_SPECS[name]
    direct = snapshot.get(snapshot_name)
    if isinstance(direct, list):
        return [dict(row) for row in direct if isinstance(row, Mapping)]
    return _unpack(gui.get(name, {}))


def _classification(state: object) -> str:
    try:
        value = state.ingestor.c.get("config", {}).get("classification")
    except (AttributeError, TypeError):
        value = None
    return value if value == PRODUCT_CLASSIFICATION else PRODUCT_CLASSIFICATION


def _safe_availability(value: object) -> dict[str, object]:
    """Normalize old and live availability shapes without leaking extras."""
    if not isinstance(value, Mapping):
        return {
            "overall_state": "NO_VALID_MARKET_DATA",
            "market_display_enabled": False,
            "layers": {
                horizon: {"state": "NOT_YET_AVAILABLE", "reason": "NO_RECORD"}
                for horizon in ("3D", "2D", "1D", "ID")
            },
        }
    safe: dict[str, object] = {}
    scalar_fields = (
        "overall_state", "market_display_enabled", "divergence_state",
        "participation_state", "available_horizons", "unavailable_horizons",
        "index_state", "futures_state", "futures_oi_state", "ce_state",
        "pe_state", "calculation_timestamp", "reference_timestamp",
        "evidence_cutoff_timestamp",
    )
    for field in scalar_fields:
        if field in value:
            safe[field] = _primitive(value[field])
    layers: dict[str, dict[str, object]] = {}
    source_layers = value.get("layers", {})
    if isinstance(source_layers, Mapping):
        for horizon in ("3D", "2D", "1D", "ID"):
            item = source_layers.get(horizon, {})
            if isinstance(item, Mapping):
                layers[horizon] = {
                    "state": _primitive(item.get("state")) or "NOT_YET_AVAILABLE",
                    "reason": _primitive(item.get("reason")) or "NO_RECORD",
                }
    legacy = {"3D": "3D", "2D": "2D", "1D": "1D", "ID": "Intraday"}
    for horizon, field in legacy.items():
        if horizon not in layers:
            layers[horizon] = {
                "state": _primitive(value.get(field)) or "NOT_YET_AVAILABLE",
                "reason": "RUNTIME_INPUT_STATE",
            }
    component_legacy = {
        "divergence_state": "Divergence",
        "futures_oi_state": "FuturesParticipation",
        "ce_state": "CEParticipation",
        "pe_state": "PEParticipation",
    }
    for output, field in component_legacy.items():
        if output not in safe and field in value:
            safe[output] = _primitive(value[field])
    safe["layers"] = layers
    safe.setdefault("overall_state", "NO_VALID_MARKET_DATA")
    safe.setdefault(
        "market_display_enabled", safe["overall_state"] != "NO_VALID_MARKET_DATA",
    )
    receipt_ages = value.get("receipt_ages_seconds", {})
    if isinstance(receipt_ages, Mapping):
        safe["receipt_ages_seconds"] = {
            key: _primitive(receipt_ages.get(key))
            for key in ("INDEX", "FUTURES", "FUTURES_OI", "CE", "PE")
            if key in receipt_ages
        }
    return safe


def _availability_for(
    state: object, snapshot: Mapping[str, object], gui: Mapping[str, object],
    *, operational: bool = False,
) -> dict[str, object]:
    if operational:
        try:
            current = state.availability()
        except (AttributeError, TypeError, ValueError):
            current = {}
        if current:
            return _safe_availability(current)
    value = snapshot.get("availability") or gui.get("availability")
    if value:
        return _safe_availability(value)
    # Legacy test/pre-orchestrator states have no sealed analytical snapshot.
    # A live orchestrator must be read only through snapshot(flush_dirty=False).
    if getattr(state, "orchestrator", None) is None:
        return _safe_availability(state.availability())
    return _safe_availability({})


def _ages(state: object) -> dict[str, object]:
    try:
        values = state.ages()
    except (AttributeError, TypeError, ValueError):
        values = {}
    if not isinstance(values, Mapping):
        return {}
    allowed = ("INDEX", "FUTURES", "FUTURES_OI", "CE", "PE", "OPTION_OI")
    return {key: _primitive(values.get(key)) for key in allowed if key in values}


def _latest_receipts(state: object) -> dict[str, object]:
    try:
        values = state.ingestor.latest
    except AttributeError:
        values = {}
    if not isinstance(values, Mapping):
        return {}
    allowed = ("INDEX", "FUTURES", "FUTURES_OI", "CE", "PE", "OPTION_OI")
    return {key: _primitive(values.get(key)) for key in allowed if key in values}


def _counts(value: object) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    result = {}
    for key, item in value.items():
        primitive = _primitive(item)
        if isinstance(primitive, (int, float)) and not isinstance(primitive, bool):
            result[str(key)] = primitive
    return result


def _timestamp(value: object):
    if value in (None, ""):
        return None
    try:
        return parse_timestamp(value, field_name="public audit clock")
    except (TypeError, ValueError):
        return None


def _audit_measurements(
    state: object, snapshot: Mapping[str, object],
) -> dict[str, object]:
    """Measure public audit counters from current/persisted runtime artifacts."""
    orchestrator = getattr(state, "orchestrator", None)
    causality_method = getattr(orchestrator, "causality_metrics", None)
    try:
        causality = causality_method() if callable(causality_method) else {}
    except (TypeError, ValueError, OSError):
        causality = {}
    causality = causality if isinstance(causality, Mapping) else {}

    ingestor = getattr(state, "ingestor", None)
    ledgers = getattr(ingestor, "ledgers", {})
    ledgers = ledgers if isinstance(ledgers, Mapping) else {}
    duplicate_ids = 0
    timestamp_backdating = 0
    measured_ledger_rows = 0
    identity_fields = ("event_id", "transition_id", "record_id", "episode_id")
    evidence_fields = (
        "effective_timestamp", "confirmation_timestamp",
        "state_entry_timestamp", "observation_timestamp",
        "receipt_timestamp", "evidence_receipt_timestamp",
        "availability_timestamp", "control_effective_timestamp",
        "index_receipt_timestamp", "futures_receipt_timestamp",
    )
    for ledger in ledgers.values():
        try:
            rows = ledger.rows() if hasattr(ledger, "rows") else []
        except (OSError, ValueError, json.JSONDecodeError):
            rows = []
        identities = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            measured_ledger_rows += 1
            identity = next(
                (str(row[field]) for field in identity_fields if row.get(field)),
                "",
            )
            if identity:
                identities.append(identity)
            publication = _timestamp(row.get("publication_timestamp"))
            if publication is not None and any(
                evidence is not None and evidence > publication
                for evidence in (_timestamp(row.get(field)) for field in evidence_fields)
            ):
                timestamp_backdating += 1
        duplicate_ids += len(identities) - len(set(identities))

    calculation = _timestamp(
        (snapshot.get("availability") or {}).get("calculation_timestamp")
        if isinstance(snapshot.get("availability"), Mapping) else None
    )
    snapshot_identities = {
        "episodes": "episode_id", "dependencies": "episode_id",
        "lifecycle": "record_id", "participation_dense": "record_id",
        "participation_transitions": "transition_id",
        "participation_summaries": "episode_id",
        "compatibility_snapshots": "episode_id",
        "cross_layer_transitions": "transition_id",
    }
    measured_snapshot_rows = 0
    for artifact, identity_field in snapshot_identities.items():
        rows = snapshot.get(artifact, [])
        if not isinstance(rows, list):
            continue
        identities = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            measured_snapshot_rows += 1
            if row.get(identity_field):
                identities.append(str(row[identity_field]))
            if calculation is not None and any(
                evidence is not None and evidence > calculation
                for evidence in (_timestamp(row.get(field)) for field in evidence_fields)
            ):
                timestamp_backdating += 1
        duplicate_ids += len(identities) - len(set(identities))

    contract = getattr(ingestor, "c", {})
    contract = contract if isinstance(contract, Mapping) else {}
    open_audit = contract.get("runtime_source_open_audit", {})
    prohibited_opens = (
        _primitive(open_audit.get("prohibited_open_count"))
        if isinstance(open_audit, Mapping) else None
    )
    return {
        "future_joins": _primitive(causality.get("future_joins")),
        "synchronization_tolerance_violations": _primitive(
            causality.get("synchronization_tolerance_violations")
        ),
        "timestamp_backdating": timestamp_backdating,
        "duplicate_analytical_ids": duplicate_ids,
        "prohibited_runtime_opens": prohibited_opens,
        "manifest_verified": bool(contract.get("engine_source_verified", False)),
        "measured_ledger_rows": measured_ledger_rows,
        "measured_snapshot_rows": measured_snapshot_rows,
    }


def _readiness(state: object) -> dict[str, object]:
    orchestrator = getattr(state, "orchestrator", None)
    snapshot = _snapshot(state)
    availability = _availability_for(
        state, snapshot, _gui(snapshot), operational=True,
    )
    try:
        source = state.readiness()
    except (AttributeError, TypeError, ValueError):
        source = {}
    if (not isinstance(source, Mapping) or not source) and orchestrator is not None:
        ingestor = getattr(state, "ingestor", None)
        checkpoint_health = getattr(ingestor, "checkpoint_health", None)
        checkpoint = checkpoint_health() if callable(checkpoint_health) else {"valid": True}
        causality_metrics = getattr(orchestrator, "causality_metrics", None)
        causality = causality_metrics() if callable(causality_metrics) else {}
        config = getattr(ingestor, "c", {}) if ingestor is not None else {}
        reasons = []
        if getattr(state, "last_error", ""):
            reasons.append(str(state.last_error).split(":", 1)[0])
        if not checkpoint.get("valid", False):
            reasons.append("CHECKPOINT_INTEGRITY_FAILED")
        if causality.get("future_joins"):
            reasons.append("FUTURE_JOIN_DETECTED")
        if causality.get("synchronization_tolerance_violations"):
            reasons.append("SYNCHRONIZATION_TOLERANCE_VIOLATION")
        source_verified = bool(config.get("engine_source_verified", False))
        if not source_verified:
            reasons.append("ENGINE_SOURCE_IDENTITY_UNVERIFIED")
        source = {
            "ready": not reasons, "reasons": reasons,
            "engine_hash": config.get("engine_hash", ""),
            "configuration_hash": config.get("configuration_hash", ""),
            "checkpoint_valid": bool(checkpoint.get("valid", False)),
            "future_joins": int(causality.get("future_joins", 0)),
            "synchronization_tolerance_violations": int(
                causality.get("synchronization_tolerance_violations", 0)
            ),
            "manifest_verified": source_verified,
        }
    source = source if isinstance(source, Mapping) else {}
    reasons = []
    for reason in source.get("reasons", []):
        if not isinstance(reason, str):
            continue
        token = reason.split(":", 1)[0]
        reasons.append(token if token.replace("_", "").isalnum() else "RUNTIME_ERROR")

    index_state = availability.get("index_state")
    futures_state = availability.get("futures_state")
    receipts = _latest_receipts(state)
    id_layer = availability.get("layers", {}).get("ID", {})
    market_seen = bool(
        receipts.get("INDEX")
        or receipts.get("FUTURES")
        or (isinstance(id_layer, Mapping) and id_layer.get("state") == "STALE_DATA")
    )
    if index_state not in (None, "AVAILABLE") or futures_state not in (None, "AVAILABLE"):
        reasons.append("STALE_DATA" if market_seen else "REQUIRED_MARKET_INPUTS_UNAVAILABLE")
    if availability.get("overall_state") == "NO_VALID_MARKET_DATA":
        reasons.append("REQUIRED_MARKET_INPUTS_UNAVAILABLE")
    reasons = list(dict.fromkeys(reasons))
    ready = bool(source.get("ready", not reasons)) and not reasons
    result = {
        "ready": ready,
        "reasons": reasons,
        "availability_state": availability.get("overall_state"),
    }
    for field in (
        "engine_hash", "configuration_hash", "checkpoint_valid",
        "future_joins", "synchronization_tolerance_violations",
        "manifest_verified",
    ):
        source_field = (
            "runtime_source_identity_verified"
            if field == "manifest_verified" and field not in source
            else field
        )
        if source_field in source:
            result[field] = _primitive(source[source_field])
    return result


def _limit(query: Mapping[str, list[str]], default: int, maximum: int) -> int:
    try:
        return max(1, min(maximum, int(query.get("limit", [str(default)])[0])))
    except (TypeError, ValueError, IndexError):
        return default


def _tail_response(
    rows: list[dict[str, object]], fields: Sequence[str], limit: int, session: str,
) -> dict[str, object]:
    selected = rows[-limit:]
    return {
        "session_date": session,
        "rows": [_project(row, fields) for row in selected],
        "count": len(rows),
        "returned_count": len(selected),
        "truncated": len(rows) > len(selected),
    }


def _session(snapshot: Mapping[str, object], gui: Mapping[str, object]) -> str:
    return str(snapshot.get("session_date") or gui.get("date") or "")


def _material_resolution(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Retain canonical mechanism changes, never dense repeated display rows."""
    result = []
    previous: dict[str, object] = {}
    for row in rows:
        episode = str(row.get("episode_id", ""))
        mechanism = row.get("resolution_mechanism_native")
        if previous.get(episode) == mechanism:
            continue
        previous[episode] = mechanism
        result.append(dict(row))
    return result


def _chart(
    state: object,
    snapshot: Mapping[str, object],
    gui: Mapping[str, object],
    *,
    operational: bool,
) -> dict[str, object]:
    price = _unpack(gui.get("price", {}))
    inventory = _artifact_rows(snapshot, gui, "inventory")
    episodes = _artifact_rows(snapshot, gui, "episodes")
    dependencies = _artifact_rows(snapshot, gui, "dependencies")
    lifecycle = _artifact_rows(snapshot, gui, "lifecycle")
    resolution = _material_resolution(_artifact_rows(snapshot, gui, "resolution_mechanisms"))
    availability = _availability_for(
        state, snapshot, gui, operational=operational,
    )
    date = _session(snapshot, gui)
    stale_warning = operational and (
        availability.get("divergence_state") == "STALE_DATA"
        or availability.get("index_state") not in (None, "AVAILABLE")
        or availability.get("futures_state") not in (None, "AVAILABLE")
    )
    receipt_ages = availability.get("receipt_ages_seconds")
    if not isinstance(receipt_ages, Mapping) or not receipt_ages:
        receipt_ages = _ages(state) if operational else {}
    return {
        "schema": "R6E1R_SANITIZED_CHART_V1",
        "classification": _classification(state),
        "session_date": date,
        "session": {
            "start": f"{date}T09:15:00+05:30" if date else "",
            "end": f"{date}T15:30:00+05:30" if date else "",
        },
        "as_of": availability.get("calculation_timestamp") or "",
        "availability": availability,
        "stale_warning": bool(stale_warning),
        "warning_reason": "STALE_DATA" if stale_warning else "",
        "display_state": (
            "LAST_VALID_CHART_WITH_STALE_WARNING"
            if stale_warning else "CURRENT_OR_REPLAY_PROJECTION"
        ),
        "receipt_ages_seconds": dict(receipt_ages),
        "latest_receipts": _latest_receipts(state),
        "price": _pack(price, PRICE_FIELDS),
        "inventory": _pack(inventory, INVENTORY_FIELDS),
        "episodes": _pack(episodes, EPISODE_FIELDS),
        "dependencies": _pack(dependencies, DEPENDENCY_FIELDS),
        "lifecycle": _pack(lifecycle, LIFECYCLE_FIELDS),
        "resolution_mechanisms": _pack(resolution, RESOLUTION_FIELDS),
        "counts": {
            "price": len(price), "inventory": len(inventory),
            "episodes": len(episodes), "dependencies": len(dependencies),
            "lifecycle": len(lifecycle),
            "resolution_mechanisms": len(resolution),
        },
        "projection_hash": _primitive(gui.get("projection_hash")) or "",
    }


def _selected_session(query: Mapping[str, list[str]]) -> tuple[str | None, bool]:
    values = query.get("date")
    if not values or not values[0] or values[0] == "latest":
        return None, False
    value = values[0]
    return (value, False) if value in SESSIONS else (None, True)


def _available_replays(state: object) -> list[str]:
    orchestrator = getattr(state, "orchestrator", None)
    outputs = getattr(orchestrator, "_outputs", None)
    if not isinstance(outputs, Mapping):
        outputs = getattr(orchestrator, "outputs", None)
    if isinstance(outputs, Mapping):
        return [
            date for date in SESSIONS
            if isinstance(outputs.get(date), Mapping)
            and str(outputs[date].get("session_date", "")) == date
        ]
    snapshot_all = getattr(orchestrator, "snapshot_all", None)
    if not callable(snapshot_all):
        return []
    try:
        parameters = signature(snapshot_all).parameters
        values = snapshot_all(**({"flush_dirty": False} if "flush_dirty" in parameters else {}))
    except (TypeError, ValueError, OSError):
        return []
    return [
        date for date in SESSIONS
        if isinstance(values, Mapping)
        and isinstance(values.get(date), Mapping)
        and str(values[date].get("session_date", "")) == date
        and bool(values[date].get("gui_payload"))
    ]


def _response_for(state: object, path: str, query: Mapping[str, list[str]]) -> tuple[dict[str, object], int]:
    if path == "/api/health":
        started = getattr(state, "started", None)
        return {
            "alive": True,
            "classification": _classification(state),
            "started_at": started.isoformat() if hasattr(started, "isoformat") else "",
        }, 200
    if path == "/api/readiness":
        value = _readiness(state)
        return value, 200 if value["ready"] else 503

    selected, invalid_session = _selected_session(query)
    if invalid_session:
        return {"error": "UNVERIFIED_SESSION"}, 400
    if selected and selected not in _available_replays(state):
        return {
            "error": "REPLAY_SESSION_UNAVAILABLE",
            "session_date": selected,
        }, 404
    snapshot = _snapshot(state, selected)
    gui = _gui(snapshot)
    session = _session(snapshot, gui)
    operational = selected is None
    availability = _availability_for(
        state, snapshot, gui, operational=operational,
    )

    if path == "/api/status":
        analytical_counts = _counts(snapshot.get("counts", {}))
        metrics = _counts(getattr(state.ingestor, "metrics", {}))
        return {
            "classification": _classification(state),
            "operational_diagnostic_only": True,
            "prospective_session_eligible": False,
            "session_date": session,
            "availability": availability,
            "receipt_ages_seconds": _ages(state),
            "latest_receipts": _latest_receipts(state),
            "metrics": metrics,
            "analytical_counts": analytical_counts,
        }, 200
    if path == "/api/session":
        return {
            "schema": "R6E1R_SANITIZED_SESSION_V1",
            "classification": _classification(state),
            "session_date": session,
            "mode": "HISTORICAL_REPLAY" if selected else "LIVE_LATEST",
            "verified_replay_sessions": list(SESSIONS),
            "available_replay_sessions": _available_replays(state),
            "as_of": availability.get("calculation_timestamp") or "",
            "availability": availability,
            "counts": _counts(snapshot.get("counts", {})),
            "projection_hash": _primitive(gui.get("projection_hash")) or "",
            "read_only_endpoints": [
                "/api/health", "/api/readiness", "/api/status", "/api/session",
                "/api/chart", "/api/inventory", "/api/divergence",
                "/api/lifecycle", "/api/participation", "/api/transitions",
                "/api/availability", "/api/audit",
            ],
        }, 200
    if path == "/api/chart":
        return _chart(
            state, snapshot, gui, operational=operational,
        ), 200
    if path == "/api/availability":
        return {
            "session_date": session,
            "classification": _classification(state),
            "receipt_ages_seconds": _ages(state),
            **availability,
        }, 200
    if path == "/api/inventory":
        rows = _artifact_rows(snapshot, gui, "inventory")
        return _tail_response(rows, INVENTORY_FIELDS, _limit(query, 1000, 5000), session), 200
    if path == "/api/divergence":
        rows = _artifact_rows(snapshot, gui, "episodes")
        dependencies = _artifact_rows(snapshot, gui, "dependencies")
        response = _tail_response(rows, EPISODE_FIELDS, _limit(query, 1000, 5000), session)
        response["dependencies"] = [_project(row, DEPENDENCY_FIELDS) for row in dependencies[-5000:]]
        response["dependency_count"] = len(dependencies)
        return response, 200
    if path == "/api/lifecycle":
        rows = _artifact_rows(snapshot, gui, "lifecycle")
        return _tail_response(rows, LIFECYCLE_FIELDS, _limit(query, 1000, 5000), session), 200
    if path == "/api/participation":
        dense = _artifact_rows(snapshot, gui, "participation_dense")
        transitions = _artifact_rows(snapshot, gui, "participation_transitions")
        summaries = _artifact_rows(snapshot, gui, "participation_summaries")
        limit = _limit(query, 500, 5000)
        return {
            "session_date": session,
            "rows": [_project(row, PARTICIPATION_FIELDS) for row in dense[-limit:]],
            "count": len(dense), "returned_count": min(limit, len(dense)),
            "truncated": len(dense) > limit,
            "transitions": [
                _project(row, PARTICIPATION_TRANSITION_FIELDS)
                for row in transitions[-limit:]
            ],
            "transition_count": len(transitions),
            "summaries": [_project(row, SUMMARY_FIELDS) for row in summaries[-limit:]],
            "summary_count": len(summaries),
        }, 200
    if path == "/api/transitions":
        cross = _artifact_rows(snapshot, gui, "cross_layer_transitions")
        participation = _artifact_rows(snapshot, gui, "participation_transitions")
        limit = _limit(query, 1000, 5000)
        return {
            "session_date": session,
            "rows": [_project(row, CROSS_LAYER_FIELDS) for row in cross[-limit:]],
            "count": len(cross), "returned_count": min(limit, len(cross)),
            "truncated": len(cross) > limit,
            "participation_rows": [
                _project(row, PARTICIPATION_TRANSITION_FIELDS)
                for row in participation[-limit:]
            ],
            "participation_count": len(participation),
        }, 200
    if path == "/api/audit":
        ledgers = getattr(state.ingestor, "ledgers", {})
        refusal_ledger = ledgers.get("refusals_data_quality") if isinstance(ledgers, Mapping) else None
        rows = refusal_ledger.rows() if hasattr(refusal_ledger, "rows") else []
        limit = _limit(query, 100, 500)
        allowed = (
            "event_id", "session_date", "effective_timestamp",
            "publication_timestamp", "status", "reason",
        )
        measurements = _audit_measurements(state, snapshot)
        return {
            "session_date": session,
            "classification": _classification(state),
            "refusals": [_project(row, allowed) for row in rows[-limit:]],
            "refusal_count": len(rows),
            **measurements,
            "measurement_source": "PERSISTED_AND_CURRENT_RUNTIME_ARTIFACTS",
            "lineage_redacted": True,
            "filesystem_identifiers_redacted": True,
        }, 200
    return {"error": "NOT_FOUND"}, 404


def handler_for(state: object) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "R6EReadOnly"
        sys_version = ""

        def _security_headers(self, content_type: str) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )

        def _send_bytes(self, data: bytes, status: int, content_type: str) -> None:
            self.send_response(status)
            self._security_headers(content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not getattr(self, "_head_only", False):
                self.wfile.write(data)

        def _send_json(self, value: object, status: int = 200) -> None:
            data = json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            self._send_bytes(data, status, "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
            parsed = urlparse(self.path)
            if parsed.path in STATIC_ROUTES:
                name, content_type = STATIC_ROUTES[parsed.path]
                try:
                    data = (STATIC_ROOT / name).read_bytes()
                except OSError:
                    return self._send_json({"error": "STATIC_ASSET_UNAVAILABLE"}, 503)
                return self._send_bytes(data, 200, content_type)
            if not parsed.path.startswith("/api/"):
                return self._send_json({"error": "NOT_FOUND"}, 404)
            try:
                value, status = _response_for(
                    state, parsed.path, parse_qs(parsed.query, keep_blank_values=False),
                )
            except Exception:  # public responses must never contain exception detail
                return self._send_json({"error": "INTERNAL_STATE_UNAVAILABLE"}, 500)
            return self._send_json(value, status)

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler contract
            self._head_only = True
            self.do_GET()

        def _method_not_allowed(self) -> None:
            self._send_json({"error": "READ_ONLY_API"}, 405)

        do_POST = _method_not_allowed
        do_PUT = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed

        def log_message(self, *_: object) -> None:
            pass

    return Handler


def create_server(state: object, bind: str, port: int) -> ThreadingHTTPServer:
    if bind != "127.0.0.1":
        raise ValueError("public bind prohibited")
    return ThreadingHTTPServer((bind, port), handler_for(state))


__all__ = ["create_server", "handler_for"]
