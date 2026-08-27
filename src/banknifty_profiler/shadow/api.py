"""Sanitized, read-only HTTP projection for the R6E live shadow.

The live analytical state contains raw lineage needed for audit and restart.
None of that lineage belongs in a browser response. This module therefore
uses explicit field allowlists for every public artifact and never serializes
an analytical snapshot, ledger row, exception, or configuration wholesale.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import math
from pathlib import Path
from inspect import signature
from threading import Lock
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
    sealed_view = getattr(orchestrator, "sealed_read_view", None)
    snapshot = getattr(orchestrator, "snapshot", None)
    if callable(sealed_view):
        value = _read_snapshot(sealed_view, session_date)
    elif callable(snapshot):
        value = _read_snapshot(snapshot, session_date)
    elif session_date:
        value = {}
    else:
        value = state.analytical_snapshot()
    return value if isinstance(value, Mapping) else {}


def _snapshot_and_availability(
    state: object,
    session_date: str | None = None,
    *,
    operational: bool,
) -> tuple[
    Mapping[str, object], dict[str, object], dict[str, int] | None
]:
    """Capture one analytical generation and its matching availability view."""
    orchestrator = getattr(state, "orchestrator", None)
    generation = getattr(orchestrator, "sealed_operational_generation", None)
    if operational and callable(generation):
        value = generation()
        if not isinstance(value, tuple) or len(value) != 3:
            raise ValueError("invalid sealed operational generation")
        snapshot, availability, causality = value
        if not all(
            isinstance(item, Mapping)
            for item in (snapshot, availability, causality)
        ):
            raise ValueError("invalid sealed operational generation")
        return (
            snapshot,
            _safe_availability(availability),
            _validated_causality(causality),
        )
    composite = getattr(orchestrator, "sealed_operational_read_view", None)
    if operational and callable(composite):
        value = composite()
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError("invalid sealed operational read view")
        snapshot, availability = value
        if not isinstance(snapshot, Mapping) or not isinstance(
            availability, Mapping
        ):
            raise ValueError("invalid sealed operational read view")
        return snapshot, _safe_availability(availability), None
    snapshot = _snapshot(state, session_date)
    availability = _availability_for(
        state, snapshot, _gui(snapshot), operational=operational,
    )
    return snapshot, availability, None


def _validated_causality(values: Mapping[str, object]) -> dict[str, int]:
    """Validate one constant-size sealed causality mapping."""
    result: dict[str, int] = {}
    for field_name in (
        "valid_basis_pairs", "future_joins",
        "synchronization_tolerance_violations",
    ):
        value = values.get(field_name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"invalid sealed public causality counter: {field_name}"
            )
        result[field_name] = value
    return result


def _causality_for(
    state: object, snapshot: Mapping[str, object],
) -> dict[str, int]:
    """Read runtime-wide sealed causality with a per-snapshot fallback.

    Readiness and audit are process gates, so they must not hide a violation in
    an older retained session merely because the latest session is clean.  The
    production orchestrator publishes a constant-size aggregate; legacy state
    objects without that method fall back to their selected sealed snapshot.
    """
    orchestrator = getattr(state, "orchestrator", None)
    method = getattr(orchestrator, "causality_metrics", None)
    if callable(method):
        values = method()
    else:
        direct = snapshot.get("public_causality_counters")
        values = direct if isinstance(direct, Mapping) else {}
    values = values if isinstance(values, Mapping) else {}
    return _validated_causality(values)


def _gui(snapshot: Mapping[str, object]) -> Mapping[str, object]:
    value = snapshot.get("gui_payload", {})
    return value if isinstance(value, Mapping) else {}


def _artifact_rows(
    snapshot: Mapping[str, object], gui: Mapping[str, object], name: str,
) -> Sequence[Mapping[str, object]]:
    snapshot_name, _ = ARTIFACT_SPECS[name]
    direct = snapshot.get(snapshot_name)
    if isinstance(direct, list):
        # Canonical sealed outputs contain mapping rows.  Return the published
        # sequence by reference so bounded endpoints project only their tail,
        # instead of first copying every dense row in the session.
        return direct
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
    if value is None:
        return None
    return parse_timestamp(value, field_name="public audit clock")


def _audit_timestamp(value: object, field_name: str):
    """Parse an optional audit clock, refusing malformed/naive evidence."""
    if value in (None, ""):
        return None
    parsed = _timestamp(value)
    if parsed is None:
        raise ValueError(f"invalid public audit clock: {field_name}")
    return parsed


_AUDIT_IDENTITY_FIELDS = (
    "event_id", "transition_id", "record_id", "episode_id",
)
_AUDIT_EVIDENCE_FIELDS = (
    "effective_timestamp", "confirmation_timestamp",
    "state_entry_timestamp", "observation_timestamp",
    "receipt_timestamp", "evidence_receipt_timestamp",
    "availability_timestamp", "control_effective_timestamp",
    "index_receipt_timestamp", "futures_receipt_timestamp",
)
_AUDIT_SNAPSHOT_IDENTITIES = {
    "episodes": "episode_id", "dependencies": "episode_id",
    "lifecycle": "record_id", "participation_dense": "record_id",
    "participation_transitions": "transition_id",
    "participation_summaries": "episode_id",
    "compatibility_snapshots": "episode_id",
    "cross_layer_transitions": "transition_id",
}
_LEGACY_AUDIT_IDENTITY_LIMIT = 5_000


@dataclass
class _LedgerAuditState:
    ledger: object
    boundary: object | None = None
    row_count: int = 0
    timestamp_backdating: int = 0
    duplicate_ids: int = 0
    seen_ids: set[str] = field(default_factory=set)
    refusal_tail: deque[dict[str, object]] = field(
        default_factory=lambda: deque(maxlen=500)
    )
    legacy_complete: bool = False


def _audit_snapshot_generation(
    snapshot: object, ledger_name: str,
) -> tuple[object, ...]:
    """Validate the monotonic token used for a stable ledger double-collect."""
    if not isinstance(snapshot, Mapping):
        raise ValueError(f"public audit snapshot is not an object: {ledger_name}")
    value = snapshot.get("generation")
    if not isinstance(value, (tuple, list)) or len(value) != 7:
        raise ValueError(f"public audit snapshot has no generation: {ledger_name}")
    existed, device, inode, size, mtime_ns, ctime_ns, digest = value
    if not isinstance(existed, bool):
        raise ValueError(f"invalid public audit generation: {ledger_name}")
    for item in (device, inode, mtime_ns, ctime_ns):
        if item is not None and (isinstance(item, bool) or not isinstance(item, int)):
            raise ValueError(f"invalid public audit generation: {ledger_name}")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError(f"invalid public audit generation: {ledger_name}")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"invalid public audit generation: {ledger_name}")
    return tuple(value)


def _trusted_ledger_identity_count(
    state: object, ledger_name: str,
) -> int | None:
    """Return a runtime-validated unique-ID count without allocating a set."""
    ingestor = getattr(state, "ingestor", None)
    if ledger_name == "normalized_raw_events":
        identities = getattr(ingestor, "_normalized_seen", None)
        return len(identities) if isinstance(identities, set) else None
    if ledger_name == "raw_file_checkpoints":
        identities = getattr(ingestor, "_checkpoint_seen", None)
        return len(identities) if isinstance(identities, set) else None
    if ledger_name == "refusals_data_quality":
        orchestrator = getattr(state, "orchestrator", None)
        shared_count = getattr(
            orchestrator, "trusted_quality_identity_count", None
        )
        if callable(shared_count):
            value = shared_count()
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("invalid shared refusal identity count")
            return value
        identities = getattr(ingestor, "_quality_seen", None)
        return len(identities) if isinstance(identities, set) else None
    orchestrator = getattr(state, "orchestrator", None)
    indexes = getattr(orchestrator, "_ledger_content", None)
    if isinstance(indexes, Mapping):
        identities = indexes.get(ledger_name)
        if isinstance(identities, Mapping):
            return len(identities)
    return None


def _fallback_snapshot_audit(
    snapshot: Mapping[str, object],
) -> dict[str, int]:
    """One-generation fallback for legacy orchestrators without sealed counts."""
    availability = snapshot.get("availability", {})
    calculation = _audit_timestamp(
        availability.get("calculation_timestamp")
        if isinstance(availability, Mapping) else None,
        "calculation_timestamp",
    )
    duplicate_ids = 0
    timestamp_backdating = 0
    measured_rows = 0
    for artifact, identity_field in _AUDIT_SNAPSHOT_IDENTITIES.items():
        rows = snapshot.get(artifact, [])
        if not isinstance(rows, list):
            raise ValueError(f"public audit artifact is not a list: {artifact}")
        identities: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"public audit row is not an object: {artifact}")
            measured_rows += 1
            if row.get(identity_field):
                identities.append(str(row[identity_field]))
            if calculation is not None and any(
                evidence is not None and evidence > calculation
                for evidence in (
                    _audit_timestamp(row.get(field), field)
                    for field in _AUDIT_EVIDENCE_FIELDS
                )
            ):
                timestamp_backdating += 1
        duplicate_ids += len(identities) - len(set(identities))
    return {
        "timestamp_backdating": timestamp_backdating,
        "duplicate_analytical_ids": duplicate_ids,
        "measured_snapshot_rows": measured_rows,
    }


class _AuditReadCache:
    """Bounded, thread-safe incremental view of append-only audit evidence."""

    def __init__(self):
        self._lock = Lock()
        self._ledgers: dict[str, _LedgerAuditState] = {}
        self._snapshot_token: tuple[object, ...] | None = None
        self._snapshot_counters: dict[str, int] = {}

    @staticmethod
    def _sealed_snapshot_counters(
        state: object, snapshot: Mapping[str, object],
    ) -> dict[str, int]:
        direct = snapshot.get("public_audit_counters")
        if isinstance(direct, Mapping):
            values = direct
        else:
            orchestrator = getattr(state, "orchestrator", None)
            method = getattr(orchestrator, "sealed_audit_measurements", None)
            if not callable(method):
                return {}
            session = str(snapshot.get("session_date", "")) or None
            values = method(session)
        result: dict[str, int] = {}
        for name in (
            "timestamp_backdating", "duplicate_analytical_ids",
            "measured_snapshot_rows",
        ):
            value = values.get(name) if isinstance(values, Mapping) else None
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid sealed public audit counter: {name}")
            result[name] = value
        return result

    def _advance_ledger(
        self,
        state: object,
        name: str,
        ledger: object,
        preloaded_audit: Mapping[str, object] | None = None,
    ) -> _LedgerAuditState:
        audit_snapshot = getattr(ledger, "audit_snapshot", None)
        if callable(audit_snapshot):
            snapshot = (
                preloaded_audit
                if preloaded_audit is not None
                else audit_snapshot()
            )
            if not isinstance(snapshot, Mapping):
                raise ValueError(f"public audit snapshot is not an object: {name}")
            counters: dict[str, int] = {}
            for field_name in (
                "row_count", "timestamp_backdating", "duplicate_ids",
            ):
                value = snapshot.get(field_name)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(
                        f"invalid public ledger audit counter {field_name}: {name}"
                    )
                counters[field_name] = value
            raw_tail = snapshot.get("tail")
            if not isinstance(raw_tail, list) or len(raw_tail) > 500:
                raise ValueError(f"invalid public ledger audit tail: {name}")
            tail: deque[dict[str, object]] = deque(maxlen=500)
            for row in raw_tail:
                if not isinstance(row, Mapping):
                    raise ValueError(f"public audit tail row is not an object: {name}")
                # Revalidate optional clocks at the API trust boundary. The
                # production ledger has already accounted for backdating.
                _timestamp(row.get("publication_timestamp"))
                for field_name in _AUDIT_EVIDENCE_FIELDS:
                    _timestamp(row.get(field_name))
                if name == "refusals_data_quality":
                    tail.append(dict(row))
            trusted_count = _trusted_ledger_identity_count(state, name)
            if trusted_count is not None:
                if trusted_count != counters["row_count"]:
                    raise ValueError(
                        f"public audit ledger identity count mismatch: {name}"
                    )
                # Production producers admit a row only after consulting their
                # all-history uniqueness index. A disagreement (including the
                # narrow append-before-index-update window) fails closed instead
                # of inventing a duplicate total from two generations.
                counters["duplicate_ids"] = 0
            updated = _LedgerAuditState(
                ledger=ledger,
                row_count=counters["row_count"],
                timestamp_backdating=counters["timestamp_backdating"],
                duplicate_ids=counters["duplicate_ids"],
                refusal_tail=tail,
                legacy_complete=True,
            )
            self._ledgers[name] = updated
            return updated

        prior = self._ledgers.get(name)
        if prior is None or prior.ledger is not ledger:
            prior = _LedgerAuditState(ledger=ledger)
        if prior.legacy_complete:
            return prior

        row_count = prior.row_count
        backdating = prior.timestamp_backdating
        duplicates = prior.duplicate_ids
        pending_ids: set[str] = set()
        refusal_tail = deque(prior.refusal_tail, maxlen=500)
        trusted_count = _trusted_ledger_identity_count(state, name)

        def consume(row: object) -> None:
            nonlocal row_count, backdating, duplicates
            if not isinstance(row, Mapping):
                raise ValueError(f"public audit ledger row is not an object: {name}")
            identity = next(
                (
                    str(row[field]) for field in _AUDIT_IDENTITY_FIELDS
                    if row.get(field)
                ),
                "",
            )
            if not identity:
                raise ValueError(f"public audit ledger row has no identity: {name}")
            if trusted_count is None:
                if identity in prior.seen_ids or identity in pending_ids:
                    duplicates += 1
                elif (
                    len(prior.seen_ids) + len(pending_ids)
                    >= _LEGACY_AUDIT_IDENTITY_LIMIT
                ):
                    raise ValueError(
                        f"legacy public audit identity bound exceeded: {name}"
                    )
                pending_ids.add(identity)
            publication = _audit_timestamp(
                row.get("publication_timestamp"), "publication_timestamp"
            )
            if publication is not None and any(
                evidence is not None and evidence > publication
                for evidence in (
                    _audit_timestamp(row.get(field), field)
                    for field in _AUDIT_EVIDENCE_FIELDS
                )
            ):
                backdating += 1
            row_count += 1
            if name == "refusals_data_quality":
                refusal_tail.append(dict(row))

        scanner = getattr(ledger, "scan_from", None)
        if callable(scanner):
            boundary = scanner(prior.boundary, consume)
            legacy_complete = False
        else:
            rows_method = getattr(ledger, "rows", None)
            rows = rows_method() if callable(rows_method) else []
            if not isinstance(rows, list):
                raise ValueError(f"public audit ledger rows are not a list: {name}")
            for row in rows:
                consume(row)
            boundary = prior.boundary
            legacy_complete = True

        # Production ledgers are identity-validated during runtime startup and
        # on every append.  A count disagreement indicates an external append,
        # an incomplete producer update, or corruption, so the request fails
        # without committing this scan and can be retried safely.
        trusted_after = _trusted_ledger_identity_count(state, name)
        if trusted_after is not None and row_count != trusted_after:
            raise ValueError(f"public audit ledger identity count mismatch: {name}")

        updated = _LedgerAuditState(
            ledger=ledger,
            boundary=boundary,
            row_count=row_count,
            timestamp_backdating=backdating,
            duplicate_ids=duplicates,
            seen_ids=prior.seen_ids,
            refusal_tail=refusal_tail,
            legacy_complete=legacy_complete,
        )
        updated.seen_ids.update(pending_ids)
        self._ledgers[name] = updated
        return updated

    def read(
        self, state: object, snapshot: Mapping[str, object], limit: int,
    ) -> dict[str, object]:
        with self._lock:
            ingestor = getattr(state, "ingestor", None)
            ledgers = getattr(ingestor, "ledgers", {})
            ledgers = ledgers if isinstance(ledgers, Mapping) else {}
            active = set(map(str, ledgers))
            for stale in set(self._ledgers) - active:
                self._ledgers.pop(stale, None)
            items = sorted(ledgers.items(), key=lambda item: str(item[0]))
            production = bool(items) and all(
                callable(getattr(ledger, "audit_snapshot", None))
                for _name, ledger in items
            )
            stable: dict[str, Mapping[str, object]] | None = None
            if production:
                # Two identical ordered collects provide one real overlap point
                # for independently locked monotonic ledger generations. Retry
                # boundedly rather than reporting a vector that never existed.
                for _attempt in range(4):
                    first = {
                        str(name): ledger.audit_snapshot()
                        for name, ledger in items
                    }
                    second = {
                        str(name): ledger.audit_snapshot()
                        for name, ledger in items
                    }
                    if all(
                        _audit_snapshot_generation(first[name], name)
                        == _audit_snapshot_generation(second[name], name)
                        for name in first
                    ):
                        stable = second
                        break
                if stable is None:
                    raise ValueError(
                        "public audit ledgers changed during stable collection"
                    )
            states = [
                self._advance_ledger(
                    state,
                    str(name),
                    ledger,
                    stable.get(str(name)) if stable is not None else None,
                )
                for name, ledger in items
            ]

            sealed = self._sealed_snapshot_counters(state, snapshot)
            if sealed:
                snapshot_counters = sealed
            else:
                gui = snapshot.get("gui_payload", {})
                projection = (
                    gui.get("projection_hash") if isinstance(gui, Mapping) else ""
                )
                token = (
                    str(snapshot.get("session_date", "")), projection,
                    id(snapshot.get("participation_dense")),
                )
                if token != self._snapshot_token:
                    self._snapshot_counters = _fallback_snapshot_audit(snapshot)
                    self._snapshot_token = token
                snapshot_counters = self._snapshot_counters

            refusal = self._ledgers.get("refusals_data_quality")
            refusal_rows = list(refusal.refusal_tail)[-limit:] if refusal else []
            return {
                "refusals": refusal_rows,
                "refusal_count": refusal.row_count if refusal else 0,
                "timestamp_backdating": sum(
                    item.timestamp_backdating for item in states
                ) + snapshot_counters["timestamp_backdating"],
                "duplicate_analytical_ids": sum(
                    item.duplicate_ids for item in states
                ) + snapshot_counters["duplicate_analytical_ids"],
                "measured_ledger_rows": sum(item.row_count for item in states),
                "measured_snapshot_rows": snapshot_counters[
                    "measured_snapshot_rows"
                ],
            }


def _audit_measurements(
    state: object,
    snapshot: Mapping[str, object],
    cached: Mapping[str, object],
    causality: Mapping[str, int] | None = None,
) -> dict[str, object]:
    """Combine sealed/incremental counters with current constant-size gates."""
    causality = (
        _validated_causality(causality)
        if causality is not None
        else _causality_for(state, snapshot)
    )

    ingestor = getattr(state, "ingestor", None)
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
        "timestamp_backdating": cached["timestamp_backdating"],
        "duplicate_analytical_ids": cached["duplicate_analytical_ids"],
        "prohibited_runtime_opens": prohibited_opens,
        "manifest_verified": bool(contract.get("engine_source_verified", False)),
        "measured_ledger_rows": cached["measured_ledger_rows"],
        "measured_snapshot_rows": cached["measured_snapshot_rows"],
    }


def _readiness(state: object) -> dict[str, object]:
    orchestrator = getattr(state, "orchestrator", None)
    snapshot, availability, generation_causality = _snapshot_and_availability(
        state, operational=True,
    )
    causality = (
        generation_causality
        if generation_causality is not None
        else _causality_for(state, snapshot)
    )
    try:
        readiness = state.readiness
        parameters = signature(readiness).parameters
        kwargs = {}
        if "availability" in parameters:
            kwargs["availability"] = availability
        if "causality" in parameters:
            kwargs["causality"] = causality
        source = readiness(**kwargs)
    except (AttributeError, TypeError, ValueError):
        source = {}
    if (not isinstance(source, Mapping) or not source) and orchestrator is not None:
        ingestor = getattr(state, "ingestor", None)
        checkpoint_health = getattr(ingestor, "checkpoint_health", None)
        checkpoint = checkpoint_health() if callable(checkpoint_health) else {"valid": True}
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
    if causality.get("future_joins"):
        reasons.append("FUTURE_JOIN_DETECTED")
    if causality.get("synchronization_tolerance_violations"):
        reasons.append("SYNCHRONIZATION_TOLERANCE_VIOLATION")
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
    rows: Sequence[Mapping[str, object]], fields: Sequence[str], limit: int,
    session: str,
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


def _chart(
    state: object,
    snapshot: Mapping[str, object],
    gui: Mapping[str, object],
    availability: Mapping[str, object],
    *,
    operational: bool,
) -> dict[str, object]:
    price = _unpack(gui.get("price", {}))
    inventory = _artifact_rows(snapshot, gui, "inventory")
    episodes = _artifact_rows(snapshot, gui, "episodes")
    dependencies = _artifact_rows(snapshot, gui, "dependencies")
    lifecycle = _artifact_rows(snapshot, gui, "lifecycle")
    # Production GUI projection seals only material mechanism changes. Reading
    # that packed surface avoids rescanning/copying the dense resolution ledger
    # (164k+ rows in the canonical six-session reference) on every refresh.
    resolution = _unpack(gui.get("resolution_mechanisms", {}))
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
    session_dates = getattr(orchestrator, "sealed_session_dates", None)
    if callable(session_dates):
        try:
            available = set(session_dates())
        except (TypeError, ValueError, OSError):
            return []
        return [date for date in SESSIONS if date in available]
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


def _response_for(
    state: object,
    path: str,
    query: Mapping[str, list[str]],
    audit_cache: _AuditReadCache | None = None,
) -> tuple[dict[str, object], int]:
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
    operational = selected is None
    snapshot, availability, generation_causality = _snapshot_and_availability(
        state, selected, operational=operational,
    )
    gui = _gui(snapshot)
    session = _session(snapshot, gui)

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
            state, snapshot, gui, availability, operational=operational,
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
        limit = _limit(query, 100, 500)
        cache = audit_cache if audit_cache is not None else _AuditReadCache()
        audit = cache.read(state, snapshot, limit)
        allowed = (
            "event_id", "session_date", "effective_timestamp",
            "publication_timestamp", "status", "reason",
        )
        measurements = _audit_measurements(
            state, snapshot, audit, generation_causality,
        )
        return {
            "session_date": session,
            "classification": _classification(state),
            "refusals": [
                _project(row, allowed) for row in audit["refusals"]
                if isinstance(row, Mapping)
            ],
            "refusal_count": audit["refusal_count"],
            **measurements,
            "measurement_source": "PERSISTED_AND_CURRENT_RUNTIME_ARTIFACTS",
            "lineage_redacted": True,
            "filesystem_identifiers_redacted": True,
        }, 200
    return {"error": "NOT_FOUND"}, 404


def handler_for(state: object) -> type[BaseHTTPRequestHandler]:
    audit_cache = _AuditReadCache()
    contract = getattr(getattr(state, "ingestor", None), "c", None)
    inventory = (
        contract.get("engine_source_inventory")
        if isinstance(contract, Mapping)
        else None
    )
    if not isinstance(inventory, list):
        raise ValueError("verified engine source inventory is unavailable")
    inventory_by_path: dict[str, Mapping[str, object]] = {}
    for row in inventory:
        if not isinstance(row, Mapping):
            raise ValueError("verified engine source inventory is invalid")
        relative = row.get("path")
        if not isinstance(relative, str) or relative in inventory_by_path:
            raise ValueError("verified engine source inventory is invalid")
        inventory_by_path[relative] = row
    static_assets: dict[str, tuple[bytes, str]] = {}
    for route, (name, content_type) in STATIC_ROUTES.items():
        try:
            data = (STATIC_ROOT / name).read_bytes()
        except OSError as error:
            raise ValueError("verified static asset is unavailable") from error
        relative = f"src/banknifty_profiler/gui/static/{name}"
        expected = inventory_by_path.get(relative)
        actual = {
            "path": relative,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if expected != actual:
            raise ValueError("verified static asset identity mismatch")
        static_assets[route] = (data, content_type)

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
            if parsed.path in static_assets:
                data, content_type = static_assets[parsed.path]
                return self._send_bytes(data, 200, content_type)
            if not parsed.path.startswith("/api/"):
                return self._send_json({"error": "NOT_FOUND"}, 404)
            try:
                value, status = _response_for(
                    state,
                    parsed.path,
                    parse_qs(parsed.query, keep_blank_values=False),
                    audit_cache,
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
