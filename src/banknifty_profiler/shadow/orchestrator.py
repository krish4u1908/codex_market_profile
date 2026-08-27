"""Incremental, repository-owned wiring for the verified analytical stack.

The frozen analytical modules remain the only authority for calculations.  This
module adapts typed live observations into their canonical input frames, keeps a
bounded per-session cache, and publishes only previously unseen material rows.
It deliberately contains no trading, signalling, or threshold logic.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, MutableMapping
from zoneinfo import ZoneInfo

import pandas as pd

from banknifty_profiler.context import availability as context_availability
from banknifty_profiler.cross_layer import state as cross_layer_state
from banknifty_profiler.divergence import dependency as divergence_dependency
from banknifty_profiler.divergence import detector as divergence_detector
from banknifty_profiler.gui import adapter as gui_adapter
from banknifty_profiler.inventory import engine as inventory_engine
from banknifty_profiler.lifecycle import raw_engine as lifecycle_engine
from banknifty_profiler.participation import raw_engine as participation_engine
from banknifty_profiler.participation import views as participation_views
from banknifty_profiler.raw_io import reader as raw_reader
from banknifty_profiler.runtime.timestamps import parse_timestamp, parse_timestamp_series
from banknifty_profiler.shadow.ledger import (
    AppendOnlyLedger,
    LedgerBoundary,
    atomic_json,
)
from banknifty_profiler.shadow.symbols import SymbolRegistry, _FUTURES, _OPTION


INDEX_SYMBOL = "NSE:NIFTYBANK-INDEX"
IST = ZoneInfo("Asia/Kolkata")
KNOWN_CLASSES = frozenset({"INDEX", "FUTURES", "FUTURES_OI", "CE", "PE"})
CLASS_ORDER = {"INDEX": 0, "FUTURES": 1, "FUTURES_OI": 2, "CE": 3, "PE": 4}
LEDGER_NAMES = (
    "divergence_confirmations",
    "dependency_retriggers",
    "lifecycle_transitions",
    "inventory_winner_transitions",
    "participation_transitions",
    "cross_layer_transitions",
    "availability_transitions",
    "stale_recovery_transitions",
    "refusals_data_quality",
)
# These fields describe the latest interval view, not the immutable event that
# caused publication. A live recomputation legitimately extends an active
# divergence episode and closes a prior lifecycle state after its successor
# arrives. Publishing either closure annotation in an append-only event row
# would make the row schedule-dependent under the production periodic flush.
MATERIAL_LEDGER_SNAPSHOT_ONLY_FIELDS = {
    "divergence_confirmations": frozenset({"episode_end_timestamp"}),
    "lifecycle_transitions": frozenset({"state_exit_timestamp"}),
}
# ``calculation_timestamp`` is a causal field in the canonical participation
# transition view. For the other ledgers it is injected by ``_append_once`` as
# publication metadata and therefore cannot participate in idempotency.
CALCULATION_TIMESTAMP_IS_SEMANTIC = frozenset({"participation_transitions"})
LEDGER_RUNTIME_ENVELOPE_FIELDS = frozenset({
    "publication_timestamp", "raw_run_id",
})
OBSERVATION_FIELDS = (
    "observation_id", "event_id", "session_date", "instrument_class",
    "canonical_symbol", "source_symbol", "receipt_timestamp",
    "event_timestamp", "exchange_timestamp", "price", "cumulative_volume",
    "open_interest",
    "previous_open_interest", "open_interest_change", "strike", "option_type",
    "oi", "previous_oi", "delta_oi", "expiry", "expiry_date",
    "underlying_price", "forward_price", "source_file",
    "source_byte_offset", "source_row_number", "raw_record_id",
    "availability_status", "freshness_status", "out_of_order",
    "canonical_payload", "effective_timestamp", "publication_timestamp",
    "source_receipt_identifiers", "engine_hash", "configuration_hash",
    "raw_run_id", "status", "reason", "classification_reason",
    "source_stream", "source_row", "bid_price", "ask_price",
)

# Durable producer ledgers are recovery authorities, not loosely typed audit
# logs.  A syntactically valid JSON object with only an ``event_id`` must never
# enter an identity index and mask the canonical row that should own that ID.
# Keep these requirements adjacent to the producer so schema changes cannot be
# made accidentally by the generic JSONL transport.
_MATERIAL_LEDGER_SCHEMAS = {
    "divergence_confirmations": {
        "identities": ("event_id", "episode_id"),
        "strings": ("colour",),
        "numbers": (
            "index_at_confirmation", "futures_at_confirmation",
            "basis_at_confirmation",
        ),
        "dates": ("evaluation_date",),
        "timestamps": (
            "candidate_start_timestamp", "confirmation_timestamp",
            "index_receipt_timestamp",
            "futures_receipt_timestamp", "calculation_timestamp",
            "publication_timestamp",
        ),
    },
    "dependency_retriggers": {
        "identities": (
            "event_id", "episode_id", "dependency_group_id",
            "root_episode_id",
        ),
        "strings": ("classification", "reason_code"),
        "fields": ("previous_episode_id", "gap_seconds"),
        "timestamps": ("calculation_timestamp", "publication_timestamp"),
        "integers": ("member_number",),
        "booleans": (
            "favourable_response_before_retrigger",
            "adverse_response_before_retrigger",
            "opposite_episode_before_retrigger",
            "previous_hypothesis_resolved", "retrigger_flag",
        ),
        "optional_numbers": ("gap_seconds",),
    },
    "lifecycle_transitions": {
        "identities": (
            "event_id", "record_id", "episode_id", "dependency_group_id",
        ),
        "strings": ("state", "previous_state", "reason_code", "colour"),
        "dates": ("evaluation_date",),
        "timestamps": (
            "state_entry_timestamp", "causal_input_cutoff",
            "calculation_timestamp", "publication_timestamp",
        ),
    },
    "inventory_winner_transitions": {
        "identities": ("event_id",),
        "strings": (
            "horizon", "family", "sign", "source_sessions", "contract",
            "tie_break_reason", "methodology_version",
            "raw_input_hashes", "authority_basis", "canonical_control_name",
            "user_facing_label", "canonical_revision",
        ),
        "fields": (
            "expiry", "snapshot_timestamp", "runner_up_bin",
            "runner_up_weight",
        ),
        "present": ("control_value",),
        "numbers": (
            "eligible_observation_count", "excluded_observation_count",
            "winning_bin_weight",
        ),
        "dates": ("evaluation_date",),
        "timestamps": (
            "winner_change_timestamp", "freshness_receipt_timestamp",
            "last_contributing_change_timestamp",
            "control_effective_timestamp", "calculation_timestamp",
            "publication_timestamp",
        ),
    },
    "participation_transitions": {
        "identities": ("event_id", "transition_id", "episode_id"),
        "strings": (
            "component", "previous_state", "new_state", "reason_code",
            "dependency_group_id", "constituent_effective_timestamps",
            "raw_source_references",
        ),
        "timestamps": (
            "effective_timestamp", "evidence_receipt_timestamp",
            "calculation_timestamp", "publication_timestamp",
        ),
    },
    "cross_layer_transitions": {
        "identities": (
            "event_id", "transition_id", "source_record_id",
        ),
        "strings": (
            "component", "state_key", "previous_state", "new_state",
            "reason_code", "constituent_effective_timestamps",
        ),
        "fields": ("episode_id", "horizon", "family"),
        "dates": ("evaluation_date",),
        "timestamps": (
            "effective_timestamp", "calculation_timestamp",
            "publication_timestamp",
        ),
    },
    "availability_transitions": {
        "identities": ("event_id",),
        "strings": (
            "component", "previous_state", "new_state", "reason",
        ),
        "dates": ("session_date",),
        "timestamps": (
            "effective_timestamp", "calculation_timestamp",
            "publication_timestamp",
        ),
    },
    "stale_recovery_transitions": {
        "identities": ("event_id",),
        "strings": (
            "component", "previous_state", "new_state", "reason",
        ),
        "dates": ("session_date",),
        "timestamps": (
            "effective_timestamp", "calculation_timestamp",
            "publication_timestamp",
        ),
    },
}
_DURABLE_PROVENANCE_FIELDS = (
    "engine_hash", "configuration_hash", "raw_run_id",
)


def _required_nonempty_string(
    row: Mapping[str, object], field: str, context: str,
) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} has invalid {field}")
    return value


def _required_string(
    row: Mapping[str, object], field: str, context: str,
) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{context} has invalid {field}")
    return value


def _required_canonical_date(
    row: Mapping[str, object], field: str, context: str,
) -> str:
    value = _required_nonempty_string(row, field, context)
    try:
        canonical = date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{context} has invalid {field}") from error
    if canonical != value:
        raise ValueError(f"{context} has noncanonical {field}")
    return value


def _required_aware_timestamp(
    row: Mapping[str, object], field: str, context: str,
) -> str:
    value = _required_nonempty_string(row, field, context)
    try:
        parse_timestamp(value, field_name=f"{context} {field}")
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{context} has invalid timezone-aware {field}"
        ) from error
    return value


def _canonical_state_session(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a canonical session date")
    try:
        canonical = date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(
            f"{context} is invalid: {value!r}"
        ) from error
    if canonical != value:
        raise ValueError(f"{context} is noncanonical: {value!r}")
    return value


def _validate_refusal_ledger_row(
    row: Mapping[str, object], *, context: str,
) -> None:
    _required_nonempty_string(row, "event_id", context)
    # An invalid session value can itself be the evidence being refused, so it
    # must be a string but need not be a canonical date.
    _required_string(row, "session_date", context)
    _required_aware_timestamp(row, "effective_timestamp", context)
    _required_aware_timestamp(row, "publication_timestamp", context)
    if row.get("effective_timestamp_provenance") not in {
        "EVIDENCE", "WALL_CLOCK_FALLBACK",
    }:
        raise ValueError(
            f"{context} has invalid effective_timestamp_provenance"
        )
    identifiers = row.get("source_receipt_identifiers")
    if not isinstance(identifiers, Mapping):
        raise ValueError(f"{context} has invalid source_receipt_identifiers")
    if "file" not in identifiers or not isinstance(
        identifiers.get("file"), str
    ):
        raise ValueError(
            f"{context} has invalid source_receipt_identifiers.file"
        )
    for field in ("byte_offset", "source_row"):
        value = identifiers.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"{context} has invalid source_receipt_identifiers.{field}"
            )
    _required_nonempty_string(row, "reason", context)
    _required_string(row, "detail", context)
    if row.get("status") != "REFUSED":
        raise ValueError(f"{context} has invalid status")
    for field in _DURABLE_PROVENANCE_FIELDS:
        _required_nonempty_string(row, field, context)


def _validate_material_ledger_row(
    ledger_name: str, row: object, *, ordinal: int | None = None,
) -> Mapping[str, object]:
    location = f" row {ordinal}" if ordinal is not None else " row"
    context = f"append-only {ledger_name}{location}"
    if not isinstance(row, Mapping):
        raise ValueError(f"{context} is not an object")
    if ledger_name == "refusals_data_quality":
        _validate_refusal_ledger_row(row, context=context)
        return row
    schema = _MATERIAL_LEDGER_SCHEMAS.get(ledger_name)
    if schema is None:
        raise ValueError(f"unknown durable producer ledger: {ledger_name}")
    for field in schema.get("identities", ()):
        _required_nonempty_string(row, field, context)
    for field in schema.get("fields", ()):
        if field not in row:
            raise ValueError(f"{context} is missing {field}")
    for field in schema.get("strings", ()):
        _required_nonempty_string(row, field, context)
    for field in schema.get("present", ()):
        if field not in row or row[field] is None or isinstance(row[field], bool):
            raise ValueError(f"{context} has invalid {field}")
    for field in schema.get("numbers", ()):
        value = row.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"{context} has invalid {field}")
    for field in schema.get("optional_numbers", ()):
        value = row.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"{context} has invalid {field}")
    for field in schema.get("dates", ()):
        _required_canonical_date(row, field, context)
    for field in schema.get("timestamps", ()):
        _required_aware_timestamp(row, field, context)
    for field in schema.get("optional_timestamps", ()):
        if row.get(field) not in (None, ""):
            _required_aware_timestamp(row, field, context)
    for field in schema.get("integers", ()):
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{context} has invalid {field}")
    for field in schema.get("booleans", ()):
        if not isinstance(row.get(field), bool):
            raise ValueError(f"{context} has invalid {field}")
    for field in _DURABLE_PROVENANCE_FIELDS:
        _required_nonempty_string(row, field, context)
    return row


def _validate_staged_observation_row(
    row: object, *, session: str, ordinal: int | None = None,
) -> Mapping[str, object]:
    location = f" row {ordinal}" if ordinal is not None else " row"
    context = f"analytical observation stage {session}{location}"
    if not isinstance(row, Mapping):
        raise ValueError(f"{context} is not an object")
    missing = [field for field in OBSERVATION_FIELDS if field not in row]
    if missing:
        raise ValueError(
            f"{context} is missing required fields: {','.join(missing)}"
        )
    observation_id = _required_nonempty_string(
        row, "observation_id", context
    )
    if row.get("event_id") != observation_id:
        raise ValueError(f"{context} has mismatched event_id")
    if row.get("session_date") != session:
        raise ValueError(f"{context} has mismatched session_date")
    _required_canonical_date(row, "session_date", context)
    instrument = _required_nonempty_string(
        row, "instrument_class", context
    )
    if instrument not in KNOWN_CLASSES:
        raise ValueError(f"{context} has invalid instrument_class")
    _required_nonempty_string(row, "canonical_symbol", context)
    _required_nonempty_string(row, "source_symbol", context)
    receipt = parse_timestamp(
        _required_aware_timestamp(row, "receipt_timestamp", context)
    )
    for field in ("event_timestamp", "exchange_timestamp"):
        if row.get(field) not in (None, ""):
            _required_aware_timestamp(row, field, context)
    effective = parse_timestamp(
        _required_aware_timestamp(row, "effective_timestamp", context)
    )
    if effective != receipt:
        raise ValueError(f"{context} has mismatched effective_timestamp")
    _required_aware_timestamp(row, "publication_timestamp", context)
    _required_nonempty_string(row, "source_file", context)
    if row.get("source_stream") not in {"raw", "oi"}:
        raise ValueError(f"{context} has invalid source_stream")
    for field in ("source_byte_offset", "source_row_number"):
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{context} has invalid {field}")
    _required_nonempty_string(row, "raw_record_id", context)
    if row.get("source_row") != row.get("source_row_number"):
        raise ValueError(f"{context} has mismatched source_row")
    _required_nonempty_string(row, "availability_status", context)
    _required_nonempty_string(row, "freshness_status", context)
    if not isinstance(row.get("out_of_order"), bool):
        raise ValueError(f"{context} has invalid out_of_order")
    if not isinstance(row.get("canonical_payload"), Mapping):
        raise ValueError(f"{context} has invalid canonical_payload")
    identifiers = row.get("source_receipt_identifiers")
    if not isinstance(identifiers, Mapping):
        raise ValueError(f"{context} has invalid source_receipt_identifiers")
    expected_identifiers = {
        "file": row["source_file"],
        "byte_offset": row["source_byte_offset"],
        "source_row": row["source_row_number"],
        "raw_record_id": row["raw_record_id"],
        "source_stream": row["source_stream"],
    }
    if any(identifiers.get(key) != value for key, value in expected_identifiers.items()):
        raise ValueError(
            f"{context} has mismatched source_receipt_identifiers"
        )
    item_number = identifiers.get("item_number")
    if (
        isinstance(item_number, bool)
        or not isinstance(item_number, int)
        or item_number < 0
    ):
        raise ValueError(f"{context} has invalid source item_number")
    for field in _DURABLE_PROVENANCE_FIELDS:
        _required_nonempty_string(row, field, context)
    if row.get("status") != "OBSERVED":
        raise ValueError(f"{context} has invalid status")
    _required_nonempty_string(row, "reason", context)
    _required_nonempty_string(row, "classification_reason", context)
    for field in (
        "price", "cumulative_volume", "open_interest",
        "previous_open_interest", "open_interest_change", "oi",
        "previous_oi", "delta_oi", "strike", "underlying_price",
        "forward_price", "bid_price", "ask_price",
    ):
        value = row.get(field)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError(f"{context} has invalid {field}")
    for canonical, alias in (
        ("open_interest", "oi"),
        ("previous_open_interest", "previous_oi"),
        ("open_interest_change", "delta_oi"),
    ):
        if row.get(canonical) != row.get(alias):
            raise ValueError(
                f"{context} has mismatched {canonical}/{alias}"
            )
    for field in ("option_type", "expiry", "expiry_date"):
        if row.get(field) is not None and not isinstance(row.get(field), str):
            raise ValueError(f"{context} has invalid {field}")
    if row.get("expiry") != row.get("expiry_date"):
        raise ValueError(f"{context} has mismatched expiry/expiry_date")
    if row.get("expiry"):
        _required_canonical_date(row, "expiry", context)
    if row["source_symbol"] != row["canonical_symbol"]:
        raise ValueError(f"{context} has mismatched canonical/source symbol")
    source_parts = Path(str(row["source_file"])).parts
    if (
        len(source_parts) != 3
        or source_parts[0] != row["source_stream"]
        or source_parts[1] != session
    ):
        raise ValueError(f"{context} has invalid source file identity")
    canonical_symbol = str(row["canonical_symbol"])
    if instrument == "INDEX":
        if canonical_symbol != INDEX_SYMBOL or row["source_stream"] != "raw":
            raise ValueError(f"{context} has invalid Index identity")
    elif instrument == "FUTURES":
        futures_match = _FUTURES.fullmatch(canonical_symbol)
        if (
            futures_match is None
            or row["source_stream"] != "raw"
            or (
                row.get("expiry")
                and not SymbolRegistry._expiry_matches(
                    futures_match, str(row["expiry"])
                )
            )
        ):
            raise ValueError(f"{context} has invalid Futures identity")
    elif instrument == "FUTURES_OI":
        futures_match = _FUTURES.fullmatch(canonical_symbol)
        if (
            futures_match is None
            or row["source_stream"] != "oi"
            or not row.get("expiry")
            or not SymbolRegistry._expiry_matches(
                futures_match, str(row["expiry"])
            )
        ):
            raise ValueError(f"{context} has invalid Futures OI identity")
    else:
        option_match = _OPTION.fullmatch(canonical_symbol)
        option_strike = (
            float(option_match.group("strike"))
            if option_match is not None else None
        )
        if (
            option_match is None
            or row["source_stream"] != "oi"
            or row.get("option_type") != instrument
            or row.get("strike") != option_strike
            or not row.get("expiry")
            or not SymbolRegistry._expiry_matches(
                option_match, str(row["expiry"])
            )
        ):
            raise ValueError(f"{context} has invalid option identity")
    return row


def _jsonable(value):
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    return value


def _material_ledger_projection(
    ledger_name: str, row: Mapping[str, object]
) -> dict:
    """Return the immutable event represented by a mutable live snapshot row."""
    value = _jsonable(dict(row))
    for field in MATERIAL_LEDGER_SNAPSHOT_ONLY_FIELDS.get(
        ledger_name, frozenset()
    ):
        value.pop(field, None)
    return value


def _material_ledger_content(
    ledger_name: str, row: Mapping[str, object]
) -> str:
    """Fixed-size digest used to validate a deterministic event identity."""
    value = _material_ledger_projection(ledger_name, row)
    for field in LEDGER_RUNTIME_ENVELOPE_FIELDS:
        value.pop(field, None)
    if ledger_name not in CALCULATION_TIMESTAMP_IS_SEMANTIC:
        value.pop("calculation_timestamp", None)
    if ledger_name == "refusals_data_quality":
        provenance = value.pop("effective_timestamp_provenance", None)
        if provenance == "WALL_CLOCK_FALLBACK":
            # A row with an invalid evidence timestamp necessarily falls back
            # to its wall-clock publication instant.  That instant may change
            # after an ambiguous durable append, while the refusal identity,
            # reason, detail and source coordinates remain immutable.  Valid
            # evidence timestamps remain part of the content digest.
            value.pop("effective_timestamp", None)
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _staged_observation_content(row: Mapping[str, object]) -> str:
    """Return a fixed-size digest for one durable callback-stage row."""
    encoded = json.dumps(
        _jsonable(dict(row)),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _staged_observation_encoded_size(row: Mapping[str, object]) -> int:
    """Return the exact canonical JSONL byte size used by AppendOnlyLedger."""
    return len((
        json.dumps(
            _jsonable(dict(row)), sort_keys=True, separators=(",", ":"),
            default=str,
        ) + "\n"
    ).encode())


def _compact_gui_resolution_payload(
    output: Mapping[str, object],
) -> dict[str, object] | None:
    """Compact a persisted pre-repair GUI resolution pack at load time."""
    raw_gui = output.get("gui_payload")
    if not isinstance(raw_gui, Mapping) or not raw_gui:
        return None
    raw_pack = raw_gui.get("resolution_mechanisms")
    if not isinstance(raw_pack, Mapping):
        if not output.get("resolution"):
            return None
        raise ValueError("persisted GUI resolution projection is missing")
    fields = raw_pack.get("fields")
    rows = raw_pack.get("rows")
    if (
        not isinstance(fields, list)
        or not all(isinstance(field, str) for field in fields)
        or not isinstance(rows, list)
    ):
        raise ValueError("persisted GUI resolution projection is invalid")
    try:
        episode_index = fields.index("episode_id")
        mechanism_index = fields.index("resolution_mechanism_native")
    except ValueError as error:
        if rows:
            raise ValueError(
                "persisted GUI resolution projection lacks material keys"
            ) from error
        episode_index = mechanism_index = 0
    compacted: list[list[object]] = []
    prior: dict[str, object] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != len(fields):
            raise ValueError("persisted GUI resolution row is invalid")
        values = list(row)
        episode = str(values[episode_index])
        mechanism = values[mechanism_index]
        if prior.get(episode) == mechanism:
            continue
        prior[episode] = mechanism
        compacted.append(values)
    gui = _jsonable(dict(raw_gui))
    gui["resolution_mechanisms"] = {
        "fields": list(fields), "rows": compacted,
    }
    counts = gui.get("counts")
    if not isinstance(counts, dict):
        counts = {}
        gui["counts"] = counts
    counts["resolution_mechanisms"] = len(compacted)
    gui.pop("projection_hash", None)
    gui["projection_hash"] = hashlib.sha256(
        json.dumps(
            gui, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    return gui


_PUBLIC_AUDIT_IDENTITIES = {
    "episodes": "episode_id",
    "dependencies": "episode_id",
    "lifecycle": "record_id",
    "participation_dense": "record_id",
    "participation_transitions": "transition_id",
    "participation_summaries": "episode_id",
    "compatibility_snapshots": "episode_id",
    "cross_layer_transitions": "transition_id",
}
_PUBLIC_AUDIT_EVIDENCE_CLOCKS = (
    "effective_timestamp", "confirmation_timestamp",
    "state_entry_timestamp", "observation_timestamp",
    "receipt_timestamp", "evidence_receipt_timestamp",
    "availability_timestamp", "control_effective_timestamp",
    "index_receipt_timestamp", "futures_receipt_timestamp",
)


def _sealed_snapshot_audit_counters(
    snapshot: Mapping[str, object],
) -> dict[str, int]:
    """Measure one output generation once, before it becomes API-visible."""
    availability = snapshot.get("availability", {})
    calculation = None
    if isinstance(availability, Mapping):
        value = availability.get("calculation_timestamp")
        if value not in (None, ""):
            try:
                calculation = parse_timestamp(
                    value, field_name="sealed public audit calculation clock"
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "invalid sealed public audit calculation clock"
                ) from error
    duplicate_ids = 0
    timestamp_backdating = 0
    measured_rows = 0
    for artifact, identity_field in _PUBLIC_AUDIT_IDENTITIES.items():
        rows = snapshot.get(artifact, [])
        if not isinstance(rows, list):
            raise ValueError(
                f"sealed public audit artifact is not a list: {artifact}"
            )
        identities: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"sealed public audit row is not an object: {artifact}"
                )
            measured_rows += 1
            identity = row.get(identity_field)
            if identity:
                identities.append(str(identity))
            if calculation is None:
                continue
            for field in _PUBLIC_AUDIT_EVIDENCE_CLOCKS:
                evidence = row.get(field)
                if evidence in (None, ""):
                    continue
                try:
                    parsed = parse_timestamp(
                        evidence, field_name=f"sealed public audit {field}"
                    )
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"invalid sealed public audit clock: {field}"
                    ) from error
                if parsed > calculation:
                    timestamp_backdating += 1
                    break
        duplicate_ids += len(identities) - len(set(identities))
    return {
        "timestamp_backdating": timestamp_backdating,
        "duplicate_analytical_ids": duplicate_ids,
        "measured_snapshot_rows": measured_rows,
    }


def _sealed_causality_counters(
    snapshot: Mapping[str, object], *, tolerance_ms: int,
) -> dict[str, int]:
    """Measure synchronized-basis causality once for a sealed generation."""
    rows = snapshot.get("basis", [])
    if not isinstance(rows, list):
        raise ValueError("sealed causality basis is not a list")
    valid_pairs = 0
    future_joins = 0
    tolerance_violations = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("sealed causality basis row is not an object")
        if row.get("validity_status") != "VALID":
            continue
        index_receipt = parse_timestamp(
            row.get("index_receipt_timestamp"),
            field_name="sealed basis Index receipt",
        )
        futures_receipt = parse_timestamp(
            row.get("futures_receipt_timestamp"),
            field_name="sealed basis Futures receipt",
        )
        delta_ms = (futures_receipt - index_receipt).total_seconds() * 1000
        valid_pairs += 1
        future_joins += int(delta_ms < 0)
        tolerance_violations += int(not 0 <= delta_ms <= tolerance_ms)
    return {
        "valid_basis_pairs": valid_pairs,
        "future_joins": future_joins,
        "synchronization_tolerance_violations": tolerance_violations,
    }


def _hash(prefix: str, *parts: object) -> str:
    body = "|".join(json.dumps(_jsonable(part), sort_keys=True, separators=(",", ":"), default=str) for part in parts)
    return prefix + "-" + hashlib.sha256(body.encode()).hexdigest()[:24].upper()


def _as_mapping(observation: object) -> dict:
    if isinstance(observation, Mapping):
        return dict(observation)
    if is_dataclass(observation):
        return asdict(observation)
    if hasattr(observation, "to_dict"):
        return dict(observation.to_dict())
    raise TypeError("live observation must be a typed Mapping or dataclass")


def _number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _truth(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _expiry(value):
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return pd.Timestamp(value).date()
    text = str(value).strip()
    try:
        if text.replace(".", "", 1).isdigit() and float(text) > 10_000_000:
            return pd.to_datetime(float(text), unit="s", utc=True).tz_convert("Asia/Kolkata").date()
        parsed = pd.to_datetime(text, dayfirst="/" in text, errors="raise")
        return parsed.date()
    except (TypeError, ValueError, OverflowError):
        return None


def _write_csv(path: Path, rows: Iterable[Mapping[str, object]], fallback_fields: Iterable[str]) -> None:
    values = [_jsonable(dict(row)) for row in rows]
    fields = list(dict.fromkeys(key for row in values for key in row)) or list(fallback_fields)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _source_stream(row: Mapping[str, object]) -> str:
    """Return the physical collector stream, never an inferred instrument."""
    explicit = str(row.get("source_stream", "")).lower()
    if explicit in {"raw", "oi"}:
        return explicit
    parts = str(row.get("source_file", "")).replace("\\", "/").split("/")
    if "raw" in parts:
        return "raw"
    if "oi" in parts:
        return "oi"
    return "unknown"


class LiveAnalyticalOrchestrator:
    """Route committed typed observations through the canonical processors.

    ``contract`` is the validated R6E shadow contract.  ``ledgers`` may be the
    ingestor's ledger mapping; missing analytical ledgers are created below its
    state root.  Public methods intentionally accept both one-observation
    callbacks and poll-sized batches.
    """

    def __init__(self, contract: Mapping[str, object], ledgers: MutableMapping[str, object] | None = None):
        self.c = dict(contract)
        self.config = dict(self.c.get("config", {}))
        self.state_root = Path(self.c["state_root"])
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_root / "live_analytical_orchestrator.json"
        self.stage_root = self.state_root / "analytical_observation_stage"
        self.stage_root.mkdir(parents=True, exist_ok=True)
        self.max_sessions = int(self.config.get("max_live_sessions", 8))
        self.ledgers: MutableMapping[str, object] = ledgers if ledgers is not None else {}
        for name in LEDGER_NAMES:
            self.ledgers.setdefault(name, AppendOnlyLedger(self.state_root / "ledgers" / f"{name}.jsonl"))
        self._ledger_content = {
            name: self._existing_events(name) for name in LEDGER_NAMES
        }
        # Preserve the membership-shaped compatibility view without retaining
        # a second full identity set. Values are fixed-size content digests.
        self._ledger_seen = self._ledger_content
        # The refusal ledger has two live producers: this orchestrator and the
        # raw ingestor.  ShadowState binds the ingestor's all-history identity
        # set here once at startup, after both producers have independently
        # validated the same physical ledger.  Thereafter either producer
        # updates one shared O(1) audit authority.
        self._quality_identity_index: set[str] | None = None
        self._sessions: dict[str, dict[str, dict]] = {}
        # Identities in the fsynced observation-stage ledgers.  This cache is
        # populated once at startup and updated only after an acknowledged
        # ledger append (or an exceptional append has been reconciled from
        # disk).  It keeps the normal callback path O(1) without weakening the
        # callback-before-ACK durability boundary.
        self._stage_seen: dict[str, dict[str, str]] = {}
        self._stage_ledgers: dict[str, AppendOnlyLedger] = {}
        self._poisoned_stage_sessions: set[str] = set()
        self._outputs: dict[str, dict] = {}
        # API threads read this separately published, immutable overlay rather
        # than traversing the writer-owned mutable observation buckets.
        self._operational_views: Mapping[
            str, tuple[Mapping[str, object], bool]
        ] = (
            MappingProxyType({})
        )
        self._published_causality_metrics: Mapping[str, int] = MappingProxyType({
            "valid_basis_pairs": 0,
            "future_joins": 0,
            "synchronization_tolerance_violations": 0,
        })
        self._operational_generation: tuple[
            Mapping[str, tuple[Mapping[str, object], bool]],
            Mapping[str, int],
        ] = (self._operational_views, self._published_causality_metrics)
        self._cross_layer_contexts: dict[str, dict[str, object]] = {}
        self._pending_cross_layer_contexts: dict[str, dict[str, object]] = {}
        # A trailing, not-yet-confirmed divergence candidate can later move
        # the frozen lifecycle boundary of the current terminal dependency
        # group back to its candidate-start clock.  Keep this evidence only
        # for the compute -> publish transaction: live outputs remain fully
        # provisional, while append-only ledgers admit only stable groups.
        self._pending_unstable_dependency_groups: dict[str, str] = {}
        self._last_order_key: dict[str, tuple] = {}
        self._dirty_sessions: set[str] = set()
        self._finalized_sessions: set[str] = set()
        self._fixed_cache_info: dict[str, dict] = {}
        self._fixed_profiles_memory: dict[tuple[str, str], tuple[str, dict]] = {}
        self._raw_hash_memory: dict[str, tuple[int, int, str]] = {}
        self.raw_hash_cache_path = self.state_root / "fixed_raw_source_hashes.json"
        self._raw_hash_cache = self._load_raw_hash_cache()
        self._raw_hash_cache_dirty = False
        self._eligibility_memory: dict[tuple[str, str], dict] = {}
        self.callback_invocations = Counter()
        self._load()
        self._load_staged_observations()
        self._publish_operational_views()

    def bind_quality_identity_index(self, identities: set[str]) -> None:
        """Bind the shared exactly-once authority for the refusal ledger.

        The one-time union accommodates a refusal published between producer
        construction and state assembly.  The physical row count proves that
        the union represents every row exactly once before it becomes the
        shared live index.
        """
        if not isinstance(identities, set) or any(
            not isinstance(identity, str) for identity in identities
        ):
            raise TypeError("quality identity index must be a set of strings")
        identities.update(self._ledger_content["refusals_data_quality"])
        ledger = self.ledgers["refusals_data_quality"]
        audit_snapshot = getattr(ledger, "audit_snapshot", None)
        if callable(audit_snapshot):
            audit = audit_snapshot()
            row_count = audit.get("row_count") if isinstance(audit, Mapping) else None
        else:
            rows = ledger.rows() if hasattr(ledger, "rows") else []
            row_count = len(rows) if isinstance(rows, list) else None
        if (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count != len(identities)
        ):
            raise ValueError(
                "shared refusal identity index does not match physical ledger"
            )
        self._quality_identity_index = identities

    def trusted_quality_identity_count(self) -> int:
        """Return the constant-time producer-validated refusal identity count."""
        if self._quality_identity_index is not None:
            return len(self._quality_identity_index)
        return len(self._ledger_content["refusals_data_quality"])

    def __call__(self, observation: object):
        return self.on_observation(observation)

    def on_observation(self, observation: object) -> dict:
        """Durably stage one callback row in O(1); ``flush`` runs analytics.

        The ingestor invokes callbacks once per row and has no end-of-poll
        callback.  Eagerly rerunning batch primitives here would be quadratic.
        The live runner therefore calls :meth:`process` with the whole poll, or
        callback users call :meth:`flush` once after the poll.
        """
        self._stage([observation])
        row = _as_mapping(observation)
        session = str(row.get("session_date", ""))
        return (
            self.snapshot(session, flush_dirty=False)
            if session else self.snapshot(flush_dirty=False)
        )

    def process_observations(self, observations: Iterable[object]) -> dict[str, dict]:
        return self.process(observations)

    def process(self, observations: Iterable[object]) -> dict[str, dict]:
        """Durably stage a complete poll without rebuilding the live session."""
        self._stage(observations)
        # Analytical work is intentionally coalesced until an explicit flush,
        # snapshot, or session-finalization boundary.  This keeps one-record
        # checkpoint schedules linear instead of rebuilding the full session
        # after every poll.  The fsynced stage is sufficient for safe ACK and
        # is recovered as dirty after a crash.
        return {}

    def stage_observations(self, observations: Iterable[object]) -> set[str]:
        """Durably stage a batch for callers that intentionally coalesce flushes."""
        return self._stage(observations)

    def _stage(self, observations: Iterable[object]) -> set[str]:
        """Validate, order, and durably stage rows without analytical work."""
        prepared = []
        for observation in observations:
            try:
                row = self._prepare(observation)
            except (TypeError, ValueError) as error:
                raw = _as_mapping(observation)
                self._quality(raw, "ORCHESTRATOR_OBSERVATION_REFUSED", str(error))
                continue
            prepared.append(row)
        prepared.sort(key=self._order_key)
        # A recovery marker poisons the complete session immediately.  Check
        # before identity short-circuits so a same-process callback retry can
        # never acknowledge work past an unrelated durable stage tail.
        changed: set[str] = set()
        for session in {str(row["session_date"]) for row in prepared}:
            self._assert_stage_not_quarantined(session)
            self._recover_stage_append_intent(session)
            if self._recover_retained_stage_append(session):
                changed.add(session)
            self._assert_stage_not_quarantined(session)
        staged: dict[str, list[dict]] = {}
        staged_content: dict[str, dict[str, str]] = {}
        # Do not advance the live high-water marks while merely validating a
        # batch.  They become authoritative only as each per-session append is
        # durably accepted below.
        provisional_order = dict(self._last_order_key)
        for row in prepared:
            session = row["session_date"]
            if row["instrument_class"] not in KNOWN_CLASSES:
                self._quality(row, "UNKNOWN_SYMBOL", row.get("source_symbol", ""))
                continue
            try:
                _validate_staged_observation_row(
                    row, session=str(row["session_date"])
                )
            except (TypeError, ValueError) as error:
                self._quality(
                    row, "ORCHESTRATOR_OBSERVATION_REFUSED", str(error)
                )
                continue
            identity = row["observation_id"]
            content = _staged_observation_content(row)
            # A checkpoint rewind or callback retry is idempotent only when
            # its complete normalized content remains identical.
            prior_content = self._stage_seen.get(session, {}).get(identity)
            if prior_content is None:
                prior_row = self._sessions.get(session, {}).get(identity)
                if prior_row is not None:
                    prior_content = _staged_observation_content(prior_row)
            if prior_content is not None:
                if prior_content != content:
                    raise ValueError(
                        "analytical observation identity reused with different "
                        f"content: {session}:{identity}"
                    )
                continue
            pending_content = staged_content.setdefault(session, {})
            if identity in pending_content:
                if pending_content[identity] != content:
                    raise ValueError(
                        "analytical observation identity repeated in one batch "
                        f"with different content: {session}:{identity}"
                    )
                continue
            if session in self._finalized_sessions:
                self._quality(row, "FINALIZED_SESSION_RECEIPT", session)
                continue
            later_outputs = [date_key for date_key in self._outputs if date_key > session]
            if later_outputs:
                self._quality(
                    row,
                    "OUT_OF_ORDER_SESSION_RECEIPT",
                    f"published_successor={min(later_outputs)}",
                )
                continue
            key = self._order_key(row)
            prior = provisional_order.get(session)
            if _truth(row.get("out_of_order")) or (prior is not None and key < prior):
                self._quality(row, "OUT_OF_ORDER_ANALYTICAL_RECEIPT", f"previous={prior!r} current={key!r}")
                continue
            staged.setdefault(session, []).append(row)
            pending_content[identity] = content
            provisional_order[session] = key if prior is None or key >= prior else prior
        for session, values in staged.items():
            ledger = self._stage_ledger(session)
            boundary = ledger.append_boundary()
            try:
                receipt = ledger.append_many_retained(values)
                if receipt is None:
                    raise ValueError(
                        "analytical observation stage append produced no receipt"
                    )
            except Exception:
                # The append contract may fail either before writing or after
                # a complete prefix became durable. Reconcile only the exact
                # attempted tail; unrelated/concurrent or partial bytes fail
                # closed and can never become callback-visible.
                try:
                    receipt = ledger.reconcile_retained_append(
                        boundary, values, identity_field="observation_id"
                    )
                    committed = receipt.committed_identities
                except Exception as recovery_error:
                    self._quarantine_stage_recovery(
                        session, boundary, recovery_error
                    )
                    raise ValueError(
                        "analytical observation stage ambiguity quarantined "
                        f"for {session}"
                    ) from recovery_error
                recovered = values[:len(committed)]
                if tuple(
                    str(row["observation_id"]) for row in recovered
                ) != committed:
                    raise ValueError(
                        "analytical observation recovery prefix mismatch"
                    )
                self._accept_durable_stage_rows(session, recovered)
                ledger.acknowledge_retained_append(
                    receipt, accepted_identities=committed,
                )
                self._evict_sessions()
                raise
            accepted = self._accept_durable_stage_rows(session, values)
            ledger.acknowledge_retained_append(
                receipt,
                accepted_identities=tuple(
                    str(row["observation_id"]) for row in values
                ),
            )
            if accepted:
                changed.add(session)
        if changed:
            self._evict_sessions()
        return changed

    def _stage_ledger(self, session: str) -> AppendOnlyLedger:
        self._assert_stage_not_quarantined(session)
        if self._stage_append_intent_path(session).is_file():
            raise ValueError(
                f"analytical observation stage has unresolved append intent "
                f"for {session}"
            )
        return self._raw_stage_ledger(session)

    def _raw_stage_ledger(self, session: str) -> AppendOnlyLedger:
        """Return the cached ledger while a recovery intent is being resolved."""
        ledger = self._stage_ledgers.get(session)
        if ledger is None:
            ledger = AppendOnlyLedger(self.stage_root / f"{session}.jsonl")
            self._stage_ledgers[session] = ledger
        return ledger

    def _assert_stage_not_quarantined(self, session: str) -> None:
        if (
            session in self._poisoned_stage_sessions
            or self._stage_recovery_failure_path(session).is_file()
        ):
            raise ValueError(
                f"analytical observation stage is quarantined for {session}"
            )

    def _recover_retained_stage_append(self, session: str) -> bool:
        """Accept and ACK a generic stage intent before replay deduplication."""
        ledger = self._raw_stage_ledger(session)
        if not ledger.has_retained_append():
            return False
        rows, receipt = self._read_unique_staged_rows(session)
        if receipt is None:
            raise ValueError(
                f"analytical observation stage lost retained receipt for {session}"
            )
        self._authenticate_persisted_session_rows(session, rows)
        accepted = self._accept_durable_stage_rows(session, rows)
        ledger.acknowledge_retained_append(
            receipt, accepted_identities=receipt.committed_identities,
        )
        return accepted

    def _stage_recovery_failure_path(self, session: str) -> Path:
        return self.stage_root / f"{session}.recovery_failed.json"

    def _stage_append_intent_path(self, session: str) -> Path:
        return self.stage_root / f"{session}.append_intent.json"

    def _write_stage_append_intent(
        self,
        session: str,
        boundary: LedgerBoundary,
        values: Iterable[Mapping[str, object]],
    ) -> None:
        """Durably declare the only tail allowed after a captured boundary."""
        rows = list(values)
        path = self._stage_append_intent_path(session)
        if path.exists():
            raise ValueError(
                f"analytical observation stage has unresolved append intent "
                f"for {session}"
            )
        expected = [
            {
                "observation_id": str(row["observation_id"]),
                "content_sha256": _staged_observation_content(row),
            }
            for row in rows
        ]
        expected_encoded_bytes = sum(
            _staged_observation_encoded_size(row) for row in rows
        )
        atomic_json(path, {
            "version": "R6E1R_ANALYTICAL_STAGE_APPEND_INTENT_V1",
            "session_date": session,
            "boundary": {
                field: getattr(boundary, field)
                for field in (
                    "existed", "device", "inode", "size", "mtime_ns",
                    "ctime_ns", "content_chain_sha256",
                )
            },
            "expected": expected,
            "expected_encoded_bytes": expected_encoded_bytes,
            "created_at": datetime.now(IST).isoformat(),
        })

    def _clear_stage_append_intent(self, session: str) -> None:
        """Durably remove an intent after its exact prefix is accepted."""
        path = self._stage_append_intent_path(session)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        descriptor = os.open(self.stage_root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _recover_stage_append_intent(self, session: str) -> None:
        """Reconcile a crash-left intent or quarantine any unrelated tail."""
        path = self._stage_append_intent_path(session)
        if not path.is_file():
            return
        boundary: LedgerBoundary | None = None
        try:
            raw = json.loads(path.read_text())
            if (
                not isinstance(raw, Mapping)
                or raw.get("version")
                != "R6E1R_ANALYTICAL_STAGE_APPEND_INTENT_V1"
                or raw.get("session_date") != session
            ):
                raise ValueError("invalid analytical stage append intent envelope")
            boundary_value = raw.get("boundary")
            expected_value = raw.get("expected")
            expected_encoded_bytes = raw.get("expected_encoded_bytes")
            if not isinstance(boundary_value, Mapping) or not isinstance(
                expected_value, list
            ):
                raise ValueError("invalid analytical stage append intent content")
            if (
                isinstance(expected_encoded_bytes, bool)
                or not isinstance(expected_encoded_bytes, int)
                or expected_encoded_bytes < 0
            ):
                raise ValueError(
                    "invalid analytical stage append intent byte bound"
                )
            boundary = LedgerBoundary(**{
                field: boundary_value.get(field)
                for field in (
                    "existed", "device", "inode", "size", "mtime_ns",
                    "ctime_ns", "content_chain_sha256",
                )
            })
            if (
                not isinstance(boundary.existed, bool)
                or isinstance(boundary.size, bool)
                or not isinstance(boundary.size, int)
                or boundary.size < 0
                or not isinstance(boundary.content_chain_sha256, str)
                or len(boundary.content_chain_sha256) != 64
            ):
                raise ValueError("invalid analytical stage append intent boundary")
            expected: list[tuple[str, str]] = []
            for item in expected_value:
                if not isinstance(item, Mapping):
                    raise ValueError("invalid analytical stage append intent row")
                identity = item.get("observation_id")
                content = item.get("content_sha256")
                if (
                    not isinstance(identity, str) or not identity
                    or not isinstance(content, str) or len(content) != 64
                ):
                    raise ValueError("invalid analytical stage append intent row")
                expected.append((identity, content))
            if len({identity for identity, _content in expected}) != len(expected):
                raise ValueError("duplicate analytical stage append intent identity")

            observed_rows: list[dict] = []
            ledger = self._raw_stage_ledger(session)
            try:
                physical_size = ledger.path.stat().st_size
            except FileNotFoundError:
                physical_size = 0
            if physical_size > boundary.size + expected_encoded_bytes:
                raise ValueError(
                    "analytical stage tail exceeds declared append byte bound"
                )

            def consume(row: Mapping[str, object]) -> None:
                if len(observed_rows) >= len(expected):
                    raise ValueError(
                        "analytical stage tail exceeds declared append row bound"
                    )
                observed_rows.append(dict(row))

            ledger.scan_from(boundary, consume)
            observed = [
                (
                    str(row.get("observation_id", "")),
                    _staged_observation_content(row),
                )
                for row in observed_rows
            ]
            if observed != expected[:len(observed)]:
                raise ValueError(
                    "analytical stage tail is not the declared append prefix"
                )
        except Exception as recovery_error:
            self._quarantine_stage_recovery(
                session, boundary, recovery_error
            )
            raise ValueError(
                f"analytical observation stage is quarantined for {session}"
            ) from recovery_error
        self._accept_durable_stage_rows(session, observed_rows)
        self._clear_stage_append_intent(session)

    def _quarantine_stage_recovery(
        self, session: str, boundary: object, error: Exception,
    ) -> None:
        """Persist a fail-closed marker for an unexpected physical stage tail."""
        # Poison memory before attempting persistence. Even if the state
        # filesystem refuses the marker write, this process can never retry or
        # acknowledge a callback past the unexpected durable tail.
        self._poisoned_stage_sessions.add(session)
        atomic_json(self._stage_recovery_failure_path(session), {
            "version": "R6E1R_ANALYTICAL_STAGE_QUARANTINE_V1",
            "session_date": session,
            "boundary": {
                field: getattr(boundary, field, None)
                for field in ("existed", "device", "inode", "size")
            },
            "reason": type(error).__name__,
            "detail": str(error),
            "detected_at": datetime.now(IST).isoformat(),
        })

    def _read_unique_staged_rows(self, session: str):
        """Read one durable stage and reject duplicate/corrupt identities."""
        self._assert_stage_not_quarantined(session)
        self._recover_stage_append_intent(session)
        self._assert_stage_not_quarantined(session)
        try:
            rows, receipt = self._stage_ledger(
                session
            ).rows_with_retained_append()
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"analytical observation stage corrupt for {session}: {error}"
            ) from error
        identities: set[str] = set()
        for ordinal, row in enumerate(rows, start=1):
            _validate_staged_observation_row(
                row, session=session, ordinal=ordinal
            )
            identity = str(row["observation_id"])
            if identity in identities:
                raise ValueError(
                    f"duplicate analytical observation stage identity for "
                    f"{session}: {identity}"
                )
            identities.add(identity)
        return rows, receipt

    def _accept_durable_stage_rows(
        self, session: str, rows: Iterable[Mapping[str, object]]
    ) -> bool:
        """Make already-fsynced stage rows visible to analytical memory."""
        values = [dict(row) for row in rows]
        if not values:
            return False
        seen = self._stage_seen.setdefault(session, {})
        pending: dict[str, str] = {}
        for ordinal, row in enumerate(values, start=1):
            _validate_staged_observation_row(
                row, session=session, ordinal=ordinal
            )
            identity = str(row["observation_id"])
            content = _staged_observation_content(row)
            prior = seen.get(identity, pending.get(identity))
            if prior is not None:
                if prior != content:
                    raise ValueError(
                        "analytical observation identity reused with different "
                        f"durable content: {session}:{identity}"
                    )
                continue
            pending[identity] = content
        seen.update(pending)
        bucket = self._sessions.setdefault(session, {})
        added = False
        last_order_key = self._last_order_key.get(session)
        ordered = sorted(
            ((self._order_key(row), row) for row in values),
            key=lambda item: item[0],
        )
        for order_key, row in ordered:
            identity = str(row["observation_id"])
            if identity not in bucket:
                bucket[identity] = row
                if last_order_key is None or order_key > last_order_key:
                    last_order_key = order_key
                added = True
        if last_order_key is not None:
            self._last_order_key[session] = last_order_key
        if added:
            self._dirty_sessions.add(session)
        return added

    def flush(self, session_dates: Iterable[str] | None = None) -> dict[str, dict]:
        """Run canonical batch primitives once for each dirty live session."""
        requested = set(session_dates) if session_dates is not None else set(self._dirty_sessions)
        targets = requested & set(self._dirty_sessions)
        if not targets:
            return {}
        earliest_target = min(targets)
        unresolved_predecessors = {
            session
            for session in self._sessions
            if session < earliest_target
            and session not in self._finalized_sessions
            and session not in targets
        }
        if unresolved_predecessors:
            raise ValueError(
                "cannot publish a later analytical session before finalizing "
                f"predecessor(s): {sorted(unresolved_predecessors)!r}"
            )
        previous = self._outputs
        computed = self._compute_sessions(targets)
        computed_contexts = self._pending_cross_layer_contexts
        self._publish(
            {session: computed[session] for session in sorted(targets)}, previous
        )
        remaining_dirty = set(self._dirty_sessions) - targets
        self._persist_values(
            sessions=self._sessions,
            outputs=computed,
            contexts=computed_contexts,
            dirty_sessions=remaining_dirty,
            finalized_sessions=self._finalized_sessions,
        )
        self._outputs = computed
        self._cross_layer_contexts = computed_contexts
        self._dirty_sessions = remaining_dirty
        self._publish_operational_views()
        return {session: self.snapshot(session) for session in sorted(targets)}

    def pending_session_dates(self) -> tuple[str, ...]:
        """Return recovered/live mutable sessions that still require sealing."""
        pending = (
            set(self._sessions)
            | set(self._dirty_sessions)
        ) - set(self._finalized_sessions)
        return tuple(sorted(pending))

    def finalize_session(self, session_date: str) -> dict:
        """Flush and close one session against subsequent late callbacks."""
        self.flush([session_date])
        sealed = self.snapshot(session_date, flush_dirty=False)
        # A regular refresh can intentionally defer the current terminal
        # dependency group while an unconfirmed candidate is still capable of
        # moving its frozen group-end boundary backwards.  Finalization is the
        # authority that no more session evidence can arrive, so publish the
        # complete canonical snapshot even when the session was already clean.
        # Append-once content validation makes a crash/retry at any row exact.
        self._publish(
            {session_date: sealed}, self._outputs, publish_deferred=True
        )
        # Availability is a session-seal declaration, not a record of when an
        # arbitrary periodic flush happened.  Publishing only after the final
        # snapshot is computed gives incremental and one-shot execution the
        # same immutable evidence clock and component states.  A failed append
        # remains replayable because finalization state is persisted below.
        self._publish_availability(
            session_date,
            sealed.get("availability", {}),
            {},
            reason="SESSION_AVAILABILITY_SEAL",
        )
        finalized = set(self._finalized_sessions)
        finalized.add(session_date)
        sessions = dict(self._sessions)
        sessions.pop(session_date, None)
        dirty = set(self._dirty_sessions)
        dirty.discard(session_date)
        outputs = self._retained_outputs(self._outputs, sessions, dirty)
        # The sealed output and append-only stage are the durable authorities
        # after finalization.  Raw normalized observations no longer need to
        # remain in the JSON state blob or process memory, and finalized-stage
        # recovery explicitly refuses to reload them on restart.
        self._persist_values(
            sessions=sessions,
            outputs=outputs,
            contexts=self._cross_layer_contexts,
            dirty_sessions=dirty,
            finalized_sessions=finalized,
        )
        self._sessions = sessions
        self._outputs = outputs
        self._finalized_sessions = finalized
        self._dirty_sessions = dirty
        self._last_order_key.pop(session_date, None)
        self._stage_seen.pop(session_date, None)
        self._stage_ledgers.pop(session_date, None)
        self._publish_operational_views()
        return self.snapshot(session_date)

    def sealed_read_view(
        self, session_date: str | None = None,
    ) -> Mapping[str, object]:
        """Return one already-published output without copying or flushing it.

        Published outputs are copy-on-write: analytical publication and the
        staleness refresh both build a replacement output mapping and swap
        ``self._outputs`` only after it is complete.  Capturing that mapping
        reference therefore gives a request thread a stable sealed generation
        even if another thread publishes the next generation concurrently.
        The proxy prevents API consumers from replacing top-level fields; API
        projection remains responsible for allowlisting every nested value.
        """
        outputs = self._outputs
        if not outputs:
            return MappingProxyType(self._empty_snapshot(session_date or ""))
        selected = session_date or max(outputs)
        value = outputs.get(selected)
        if value is None:
            value = self._empty_snapshot(selected)
        return MappingProxyType(value)

    def sealed_session_dates(self) -> tuple[str, ...]:
        """List published session keys from one copy-on-write generation."""
        outputs = self._outputs
        return tuple(sorted(outputs))

    def _publish_operational_views(self) -> None:
        """Atomically expose sealed outputs and their live-session membership."""
        outputs = self._outputs
        active = frozenset(self._sessions)
        views = MappingProxyType({
            session: (
                output if isinstance(output, Mapping) else {},
                session in active,
            )
            for session, output in outputs.items()
        })
        totals = {
            "valid_basis_pairs": 0,
            "future_joins": 0,
            "synchronization_tolerance_violations": 0,
        }
        for output, _active in views.values():
            counters = output.get("public_causality_counters", {})
            if not isinstance(counters, Mapping):
                raise ValueError("sealed public causality counters are invalid")
            for field in totals:
                value = counters.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(
                        f"invalid sealed public causality counter: {field}"
                    )
                totals[field] += value
        causality = MappingProxyType(totals)
        # The composite tuple is the API authority and is replaced by one
        # atomic reference assignment. Compatibility attributes remain for
        # older internal callers but cannot tear the production API read.
        self._operational_generation = (views, causality)
        self._published_causality_metrics = causality
        self._operational_views = views

    def sealed_audit_measurements(
        self, session_date: str | None = None,
    ) -> dict[str, int]:
        """Return counters computed before the sealed output was published."""
        view = self.sealed_read_view(session_date)
        counters = view.get("public_audit_counters")
        if not isinstance(counters, Mapping):
            raise ValueError("sealed output has no public audit counters")
        fields = (
            "timestamp_backdating", "duplicate_analytical_ids",
            "measured_snapshot_rows",
        )
        result: dict[str, int] = {}
        for field in fields:
            value = counters.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid sealed public audit counter: {field}")
            result[field] = value
        return result

    def snapshot(
        self,
        session_date: str | None = None,
        *,
        flush_dirty: bool = True,
    ) -> dict:
        if flush_dirty:
            if session_date is None:
                self.flush()
            elif session_date in self._dirty_sessions:
                self.flush([session_date])
        if not self._outputs:
            return self._empty_snapshot(session_date or "")
        selected = session_date or max(self._outputs)
        value = self._outputs.get(selected)
        return json.loads(json.dumps(value if value is not None else self._empty_snapshot(selected), default=str))

    def snapshot_all(self, *, flush_dirty: bool = True) -> dict[str, dict]:
        if flush_dirty:
            self.flush()
        sessions = sorted(set(self._outputs) | set(self._sessions))
        return {
            session: self.snapshot(session, flush_dirty=False)
            for session in sessions
        }

    def operational_availability(self, at: object | None = None) -> dict:
        """Project current-session freshness against a timezone-aware wall clock."""
        _output, availability, _causality = (
            self.sealed_operational_generation(at)
        )
        return dict(availability)

    def sealed_operational_generation(
        self, at: object | None = None,
    ) -> tuple[
        Mapping[str, object], Mapping[str, object], Mapping[str, int]
    ]:
        """Return output, freshness and runtime causality from one generation."""
        views, causality = self._operational_generation
        if not views:
            empty = self._empty_snapshot("")
            return (
                MappingProxyType(empty),
                MappingProxyType(empty["availability"]),
                causality,
            )
        session = max(views)
        output, active = views[session]
        availability = self._operational_availability_from_view(
            output, active=active, at=at,
        )
        return (
            MappingProxyType(output),
            MappingProxyType(availability),
            causality,
        )

    def sealed_operational_read_view(
        self, at: object | None = None,
    ) -> tuple[Mapping[str, object], Mapping[str, object]]:
        """Return one sealed output and wall-clock overlay from one generation.

        The analytical writer replaces ``_operational_views`` atomically.  API
        readers capture that mapping once, so the chart and its operational
        availability can never straddle two publications.
        """
        output, availability, _causality = self.sealed_operational_generation(at)
        return output, availability

    def _operational_availability_from_view(
        self,
        output: Mapping[str, object],
        *,
        active: bool,
        at: object | None = None,
    ) -> dict:
        """Build a current freshness overlay from one captured sealed output."""
        value = output.get("availability", {})
        current = value if isinstance(value, Mapping) else {}
        reference = parse_timestamp(
            at if at is not None else datetime.now(IST),
            field_name="operational availability clock",
        )
        # This method is used only for live/latest operational projection.
        # Explicit historical replay reads the sealed snapshot directly, so a
        # historical latest output must still age against the current wall
        # clock instead of making the live readiness endpoint appear fresh.
        if not active:
            # A verified preload may contain a sealed GUI/output without its
            # mutable observation cache.  Such historical-only evidence can
            # keep the last chart visible, but it can never establish current
            # live readiness.
            stale = json.loads(json.dumps(current, default=str))
            layers = stale.setdefault("layers", {})
            intraday = layers.setdefault("ID", {})
            intraday.update({
                "state": "STALE_DATA",
                "reason": "HISTORICAL_SEALED_OUTPUT_ONLY",
            })
            stale.update({
                "overall_state": "STALE_PARTIAL",
                "market_display_enabled": True,
                "divergence_state": "STALE_DATA",
                "index_state": "STALE_OR_MISSING",
                "futures_state": "STALE_OR_MISSING",
                "reference_timestamp": reference.isoformat(),
                "calculation_timestamp": reference.isoformat(),
            })
            cutoff = stale.get("evidence_cutoff_timestamp")
            if cutoff:
                try:
                    age = max(
                        0.0,
                        (reference - parse_timestamp(cutoff)).total_seconds(),
                    )
                    stale["receipt_ages_seconds"] = {
                        "INDEX": age, "FUTURES": age,
                    }
                except ValueError:
                    stale["receipt_ages_seconds"] = {}
            return stale
        latest: dict[str, pd.Timestamp] = {}
        base_reference = None
        for field in (
            "reference_timestamp", "calculation_timestamp",
            "evidence_cutoff_timestamp",
        ):
            value = current.get(field) if isinstance(current, Mapping) else None
            if value in (None, ""):
                continue
            try:
                base_reference = parse_timestamp(
                    value, field_name="sealed availability reference clock"
                )
                break
            except (TypeError, ValueError):
                continue
        ages = current.get("receipt_ages_seconds", {})
        if base_reference is not None and isinstance(ages, Mapping):
            for kind, age in ages.items():
                try:
                    seconds = float(age)
                except (TypeError, ValueError, OverflowError):
                    continue
                latest[str(kind)] = base_reference - timedelta(seconds=seconds)
        layers = current.get("layers", {})
        inventory = [
            {"horizon": horizon}
            for horizon in ("1D", "2D", "3D")
            if isinstance(layers, Mapping)
            and isinstance(layers.get(horizon), Mapping)
            and layers[horizon].get("state") == "AVAILABLE"
        ]
        evidence_cutoff = None
        if isinstance(current, Mapping) and current.get("evidence_cutoff_timestamp"):
            evidence_cutoff = parse_timestamp(
                current["evidence_cutoff_timestamp"],
                field_name="sealed availability evidence cutoff",
            )
        return self._availability_from_latest(
            latest,
            inventory,
            evidence_cutoff=evidence_cutoff,
            reference=reference,
            calculation=reference,
        )

    def refresh_staleness(self, at: object | None = None) -> bool:
        """Persist a material live freshness transition on an empty poll."""
        if not self._outputs:
            return False
        session = max(self._outputs)
        reference = parse_timestamp(
            at if at is not None else datetime.now(IST),
            field_name="staleness refresh clock",
        )
        if session != reference.date().isoformat() or session not in self._sessions:
            return False
        old_result = self._outputs[session]
        availability = self._availability(
            session,
            list(self._sessions[session].values()),
            list(old_result.get("inventory", [])),
            reference_time=reference,
        )
        if self._availability_states(availability) == self._availability_states(
            old_result.get("availability", {})
        ):
            return False
        result = dict(old_result)
        result["availability"] = availability
        invocation_counts = self.callback_invocations.copy()
        result["gui_payload"] = self._gui_payload(result)
        self.callback_invocations = invocation_counts
        result["public_audit_counters"] = _sealed_snapshot_audit_counters(result)
        result["public_causality_counters"] = _sealed_causality_counters(
            result,
            tolerance_ms=int(self.config.get("synchronization_tolerance_ms", 2000)),
        )
        self._publish_availability(
            session, availability, old_result.get("availability", {})
        )
        outputs = dict(self._outputs)
        outputs[session] = _jsonable(result)
        self._persist_values(
            sessions=self._sessions,
            outputs=outputs,
            contexts=self._cross_layer_contexts,
            dirty_sessions=self._dirty_sessions,
            finalized_sessions=self._finalized_sessions,
        )
        self._outputs = outputs
        self._publish_operational_views()
        return True

    def causality_metrics(self) -> dict[str, int]:
        """Return the constant-size counters published with analytical outputs."""
        _views, causality = self._operational_generation
        return dict(causality)

    def _prepare(self, observation: object) -> dict:
        raw = _as_mapping(observation)
        source_identifiers = raw.get("source_receipt_identifiers")
        source_identifiers = source_identifiers if isinstance(source_identifiers, Mapping) else {}
        row = {field: raw.get(field) for field in OBSERVATION_FIELDS}
        row["observation_id"] = str(raw.get("observation_id") or raw.get("event_id") or raw.get("raw_record_id") or "")
        if not row["observation_id"]:
            row["observation_id"] = _hash("OBS", raw.get("source_file"), raw.get("source_byte_offset"), raw.get("source_row_number"))
        supplied_event_id = raw.get("event_id")
        if supplied_event_id not in (None, "", row["observation_id"]):
            raise ValueError("live analytical event_id mismatches observation_id")
        row["event_id"] = row["observation_id"]
        instrument = str(raw.get("instrument_class") or raw.get("reason") or "UNKNOWN_SYMBOL").upper()
        aliases = {"CALL": "CE", "PUT": "PE", "FUTURE": "FUTURES_OI", "OPTION_OI": "UNKNOWN_SYMBOL", "IGNORED": "UNKNOWN_SYMBOL"}
        row["instrument_class"] = aliases.get(instrument, instrument)
        receipt = raw.get("receipt_timestamp") or raw.get("effective_timestamp")
        parsed = parse_timestamp(receipt, field_name="live analytical receipt timestamp")
        row["receipt_timestamp"] = parsed.isoformat()
        event_timestamp = raw.get("event_timestamp") or raw.get("exchange_timestamp")
        exchange = raw.get("exchange_timestamp") or event_timestamp
        row["event_timestamp"] = parse_timestamp(
            event_timestamp, field_name="event timestamp"
        ).isoformat() if event_timestamp else None
        row["exchange_timestamp"] = parse_timestamp(
            exchange, field_name="exchange event timestamp"
        ).isoformat() if exchange else None
        session_date = str(
            raw.get("session_date") or parsed.date().isoformat()
        )
        try:
            canonical_session_date = date.fromisoformat(session_date).isoformat()
        except ValueError as error:
            raise ValueError(
                f"unsafe analytical session date: {session_date!r}"
            ) from error
        if canonical_session_date != session_date:
            raise ValueError(
                f"unsafe analytical session date: {session_date!r}"
            )
        row["session_date"] = canonical_session_date
        row["canonical_symbol"] = str(raw.get("canonical_symbol") or raw.get("source_symbol") or raw.get("symbol") or "")
        row["source_symbol"] = str(raw.get("source_symbol") or raw.get("symbol") or row["canonical_symbol"])
        row["price"] = _number(raw.get("price", raw.get("last_price")))
        row["cumulative_volume"] = _number(raw.get("cumulative_volume", raw.get("volume")))
        row["open_interest"] = _number(raw.get("open_interest", raw.get("oi")))
        row["previous_open_interest"] = _number(raw.get("previous_open_interest"))
        row["open_interest_change"] = _number(raw.get("open_interest_change", raw.get("delta_oi")))
        row["oi"] = row["open_interest"]
        row["previous_oi"] = row["previous_open_interest"]
        row["delta_oi"] = row["open_interest_change"]
        row["strike"] = _number(raw.get("strike"))
        row["option_type"] = str(raw.get("option_type") or (row["instrument_class"] if row["instrument_class"] in {"CE", "PE"} else "FUT" if row["instrument_class"] == "FUTURES_OI" else ""))
        row["expiry"] = _jsonable(raw.get("expiry") or raw.get("expiry_date"))
        row["expiry_date"] = row["expiry"]
        row["source_file"] = str(raw.get("source_file") or source_identifiers.get("file", ""))
        row["source_stream"] = str(
            raw.get("source_stream")
            or source_identifiers.get("source_stream")
            or row["source_file"].split("/", 1)[0]
        ).lower()
        if row["source_stream"] not in {"raw", "oi"}:
            raise ValueError(f"unsafe physical source stream: {row['source_stream']!r}")
        byte_offset = raw.get(
            "source_byte_offset", source_identifiers.get("byte_offset", 0)
        )
        source_row = raw.get(
            "source_row_number",
            raw.get("source_row", source_identifiers.get("source_row", 0)),
        )
        for name, value in (
            ("source_byte_offset", byte_offset),
            ("source_row_number", source_row),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid live analytical {name}")
        row["source_byte_offset"] = byte_offset
        row["source_row_number"] = source_row
        row["source_row"] = source_row
        row["raw_record_id"] = str(raw.get("raw_record_id") or raw.get("event_id") or row["observation_id"])
        row["availability_status"] = str(raw.get("availability_status") or raw.get("status") or "AVAILABLE")
        row["freshness_status"] = str(raw.get("freshness_status") or "FRESH")
        row["out_of_order"] = _truth(raw.get("out_of_order"))
        row["bid_price"] = _number(raw.get("bid_price"))
        row["ask_price"] = _number(raw.get("ask_price"))
        canonical_payload = raw.get("canonical_payload", {})
        if not isinstance(canonical_payload, Mapping):
            raise ValueError("live analytical canonical_payload must be an object")
        row["canonical_payload"] = _jsonable(dict(canonical_payload))
        row["effective_timestamp"] = parse_timestamp(
            raw.get("effective_timestamp") or row["receipt_timestamp"],
            field_name="live analytical effective timestamp",
        ).isoformat()
        row["publication_timestamp"] = parse_timestamp(
            raw.get("publication_timestamp") or row["receipt_timestamp"],
            field_name="live analytical publication timestamp",
        ).isoformat()
        item_number = source_identifiers.get("item_number", 0)
        if (
            isinstance(item_number, bool)
            or not isinstance(item_number, int)
            or item_number < 0
        ):
            raise ValueError("invalid live analytical source item_number")
        row["source_receipt_identifiers"] = {
            **_jsonable(dict(source_identifiers)),
            "file": row["source_file"],
            "byte_offset": row["source_byte_offset"],
            "source_row": row["source_row_number"],
            "raw_record_id": row["raw_record_id"],
            "item_number": item_number,
            "source_stream": row["source_stream"],
        }
        row["engine_hash"] = str(
            raw.get("engine_hash") or self.c.get("engine_hash", "")
        )
        row["configuration_hash"] = str(
            raw.get("configuration_hash")
            or self.c.get("configuration_hash", "")
        )
        row["raw_run_id"] = str(
            raw.get("raw_run_id") or self.c.get("raw_run_id", "")
        )
        row["status"] = str(raw.get("status") or "OBSERVED")
        row["reason"] = str(raw.get("reason") or row["instrument_class"])
        row["classification_reason"] = str(
            raw.get("classification_reason") or "CALLBACK_NORMALIZED"
        )
        if row["instrument_class"] == "INDEX" and row["canonical_symbol"] != INDEX_SYMBOL:
            raise ValueError(f"unsafe Index identity: {row['canonical_symbol']!r}")
        return _jsonable(row)

    @staticmethod
    def _order_key(row: Mapping[str, object]) -> tuple:
        return (
            parse_timestamp(row["receipt_timestamp"], field_name="live ordering receipt timestamp").value,
            CLASS_ORDER.get(str(row.get("instrument_class")), 99),
            str(row.get("canonical_symbol", "")), str(row.get("source_file", "")),
            int(row.get("source_byte_offset") or 0), int(row.get("source_row_number") or 0),
            str(row.get("observation_id", "")),
        )

    def _compute_sessions(self, targets: set[str]) -> dict[str, dict]:
        """Recompute only dirty sessions, retaining finalized prior outputs."""
        self.callback_invocations = Counter()
        self._pending_unstable_dependency_groups = {}
        results: dict[str, dict] = dict(self._outputs)
        contexts = {
            session: cross_layer_state.normalize_material_context(value)
            for session, value in self._cross_layer_contexts.items()
        }
        for session in sorted(targets):
            rows = sorted(self._sessions[session].values(), key=self._order_key)
            market = self._market_frame(rows)
            oi = self._oi_frame(rows)
            futures = self._futures_symbol(rows)
            inventory = self._inventory(session, market, oi, futures)
            basis, frame, candidates = self._divergence(session, market, futures)
            prior_episode_count = sum(len(value.get("episodes", [])) for date_key, value in results.items() if date_key < session)
            candidates.sort(key=lambda row: parse_timestamp(row["confirmation_timestamp"], field_name="divergence confirmation"))
            for ordinal, episode in enumerate(candidates, prior_episode_count + 1):
                episode["episode_id"] = f"BDR1-{episode['evaluation_date']}-{episode['colour']}-{ordinal:03d}"
            series = {session: frame} if frame is not None and not frame.empty else {}
            self.callback_invocations["dependency"] += 1
            dependencies = divergence_dependency.group_episodes(candidates, series)
            # The frozen dependency function numbers groups globally.  Its
            # classifications are session-local; offset only the identity to
            # retain the exact chronological global numbering without opening
            # or recomputing finalized sessions.
            prior_group_count = len({row["dependency_group_id"] for date_key, value in results.items() if date_key < session for row in value.get("dependencies", [])})
            group_map = {}
            for row in dependencies:
                local = row["dependency_group_id"]
                if local not in group_map:
                    group_map[local] = f"HYP-{session}-{prior_group_count + len(group_map) + 1:03d}-{local.rsplit('-', 1)[-1]}"
                row["dependency_group_id"] = group_map[local]
            if (
                dependencies
                and self._trailing_unconfirmed_candidate_start(frame)
            ):
                self._pending_unstable_dependency_groups[session] = str(
                    dependencies[-1]["dependency_group_id"]
                )
            self.callback_invocations["lifecycle"] += 1
            lifecycle, resolution, responses = lifecycle_engine.build_lifecycle(candidates, dependencies, series, {session: self._index_frame(market)})

            causal_cutoff = max(parse_timestamp(row["receipt_timestamp"]) for row in rows)
            episodes = candidates
            deps = dependencies
            # The frozen batch lifecycle closes unresolved hypotheses at the
            # session boundary.  In live mode that row is not publishable until
            # its effective clock has actually arrived.
            life = []
            for source in lifecycle:
                if parse_timestamp(source["state_entry_timestamp"], field_name="lifecycle effective timestamp") > causal_cutoff:
                    continue
                row = dict(source)
                if row.get("state_exit_timestamp") and parse_timestamp(row["state_exit_timestamp"], field_name="lifecycle exit timestamp") > causal_cutoff:
                    row["state_exit_timestamp"] = ""
                life.append(row)
            dense_resolution = [row for row in resolution if parse_timestamp(row["availability_timestamp"], field_name="resolution availability timestamp") <= causal_cutoff]
            response_rows = responses
            participation = self._participation(session, rows, episodes, deps, life)
            self.callback_invocations["cross_layer"] += 1
            prior_context = self._cross_layer_context_before(session, contexts)
            canonical_inventory = self._uses_canonical_inventory_context(
                session, inventory
            )
            builder_context = dict(prior_context)
            if not canonical_inventory:
                # Clean batch publishes incomplete fixed-chain inventory as an
                # explicit per-session degradation fallback.  Its ordinal and
                # prior-state contract is intentionally session-local, while
                # every non-inventory component remains globally chronological.
                builder_context["inventory_source_count"] = 0
                builder_context["inventory_previous"] = {}
            cross, advanced_context = cross_layer_state.build_material_transitions(
                inventory,
                episodes,
                life,
                dense_resolution,
                participation["transitions"],
                initial_context=builder_context,
                return_context=True,
            )
            if not canonical_inventory:
                advanced_context["inventory_source_count"] = prior_context[
                    "inventory_source_count"
                ]
                advanced_context["inventory_previous"] = prior_context[
                    "inventory_previous"
                ]
            contexts[session] = cross_layer_state.normalize_material_context(
                advanced_context
            )
            availability = self._availability(session, rows, inventory)
            result = {
                "session_date": session,
                "basis": basis,
                "inventory": inventory,
                "episodes": episodes,
                "dependencies": deps,
                "lifecycle": life,
                "resolution": dense_resolution,
                "responses": response_rows,
                "participation_dense": participation["dense"],
                "participation_transitions": participation["transitions"],
                "participation_summaries": participation["summaries"],
                "compatibility_snapshots": participation["compatibility"],
                "participation_view_seal": participation["seal"],
                "cross_layer_transitions": cross,
                "availability": availability,
                "fixed_inventory_cache": self._fixed_cache_info.get(session, {}),
            }
            result["gui_payload"] = self._gui_payload(result)
            result["callback_invocations"] = {key: 1 for key in self.callback_invocations}
            result["counts"] = {
                "observations": len(rows), "basis": len(basis),
                "inventory": len(inventory), "episodes": len(episodes),
                "dependencies": len(deps), "lifecycle": len(life),
                "resolution": len(dense_resolution), "participation_dense": len(participation["dense"]),
                "participation_transitions": len(participation["transitions"]),
                "participation_summaries": len(participation["summaries"]),
                "compatibility_snapshots": len(participation["compatibility"]),
                "cross_layer_transitions": len(cross),
            }
            result["public_audit_counters"] = _sealed_snapshot_audit_counters(
                result
            )
            result["public_causality_counters"] = _sealed_causality_counters(
                result,
                tolerance_ms=int(
                    self.config.get("synchronization_tolerance_ms", 2000)
                ),
            )
            results[session] = _jsonable(result)
        self._pending_cross_layer_contexts = contexts
        return results

    @staticmethod
    def _cross_layer_context_before(
        session: str, contexts: Mapping[str, Mapping[str, object]]
    ) -> dict[str, object]:
        preceding_dates = [date_key for date_key in contexts if date_key < session]
        if not preceding_dates:
            return cross_layer_state.empty_material_context()
        latest = max(preceding_dates)
        return cross_layer_state.normalize_material_context(contexts[latest])

    def _uses_canonical_inventory_context(
        self, session: str, inventory: Iterable[Mapping[str, object]]
    ) -> bool:
        cache = self._fixed_cache_info.get(session, {})
        chain = cache.get("source_chain", [])
        if isinstance(chain, list) and len(chain) >= 3:
            return True
        return any(str(row.get("horizon")) == "3D" for row in inventory)

    def _market_frame(self, rows: list[dict]) -> pd.DataFrame:
        values = []
        for row in rows:
            if _source_stream(row) != "raw" or row["instrument_class"] not in {"INDEX", "FUTURES"}:
                continue
            if row.get("price") is None and row.get("cumulative_volume") is None:
                continue
            values.append({
                "session_date": row["session_date"], "symbol": row["canonical_symbol"],
                "event_timestamp": row.get("exchange_timestamp"), "receipt_timestamp": row["receipt_timestamp"],
                "availability_timestamp": row["receipt_timestamp"], "last_price": row.get("price"),
                "cumulative_volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""),
                "source_row": row.get("source_row_number", 0),
            })
        columns = ["session_date", "symbol", "event_timestamp", "receipt_timestamp", "availability_timestamp", "last_price", "cumulative_volume", "source_file", "source_row"]
        frame = pd.DataFrame(values, columns=columns)
        if not frame.empty:
            frame["receipt_timestamp"] = parse_timestamp_series(frame.receipt_timestamp, field_name="market receipt timestamp")
            frame["availability_timestamp"] = frame.receipt_timestamp.copy()
            frame["event_timestamp"] = parse_timestamp_series(frame.event_timestamp, field_name="market event timestamp", allow_missing=True)
            frame["last_price"] = pd.to_numeric(frame.last_price, errors="coerce")
            frame["cumulative_volume"] = pd.to_numeric(frame.cumulative_volume, errors="coerce")
            frame = frame.sort_values(["receipt_timestamp", "symbol", "source_file", "source_row"]).reset_index(drop=True)
        return frame

    def _oi_frame(self, rows: list[dict]) -> pd.DataFrame:
        values = []
        class_name = {"FUTURES_OI": "future", "CE": "call", "PE": "put"}
        for row in rows:
            if _source_stream(row) != "oi" or row["instrument_class"] not in class_name:
                continue
            values.append({
                "session_date": row["session_date"], "symbol": row["canonical_symbol"],
                "instrument_class": class_name[row["instrument_class"]], "expiry_date": _expiry(row.get("expiry")),
                "strike": row.get("strike"), "oi_observation_timestamp": row.get("exchange_timestamp"),
                "oi_receipt_timestamp": row["receipt_timestamp"], "availability_timestamp": row["receipt_timestamp"],
                "oi_close": row.get("open_interest"), "previous_oi": row.get("previous_open_interest"),
                "delta_oi": row.get("open_interest_change"), "instrument_price": row.get("price"),
                "cumulative_volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""),
                "source_row": row.get("source_row_number", 0),
            })
        columns = ["session_date", "symbol", "instrument_class", "expiry_date", "strike", "oi_observation_timestamp", "oi_receipt_timestamp", "availability_timestamp", "oi_close", "previous_oi", "delta_oi", "instrument_price", "cumulative_volume", "source_file", "source_row"]
        frame = pd.DataFrame(values, columns=columns)
        if frame.empty:
            return frame
        frame["oi_receipt_timestamp"] = parse_timestamp_series(frame.oi_receipt_timestamp, field_name="OI receipt timestamp")
        frame["availability_timestamp"] = frame.oi_receipt_timestamp.copy()
        frame["oi_observation_timestamp"] = parse_timestamp_series(frame.oi_observation_timestamp, field_name="OI observation timestamp", allow_missing=True)
        for field in ("strike", "oi_close", "previous_oi", "delta_oi", "instrument_price", "cumulative_volume"):
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
        frame = frame.sort_values(["symbol", "availability_timestamp", "source_file", "source_row"]).reset_index(drop=True)
        grouped = frame.groupby("symbol", observed=True)
        # REST ``prev_oi``/``oich`` describe exchange prior-day fields.  The
        # canonical inventory reader deliberately derives poll-to-poll OI from
        # the current session instead, while the typed envelope retains the raw
        # fields for audit.
        frame["previous_oi"] = grouped.oi_close.shift()
        frame["delta_oi"] = frame.oi_close - frame.previous_oi
        frame["valid_receipt"] = frame.oi_close.notna() & frame.availability_timestamp.notna()
        frame["oi_changed"] = frame.delta_oi.ne(0) & frame.delta_oi.notna()
        frame["duplicate_record"] = frame.duplicated(["symbol", "availability_timestamp", "oi_close", "instrument_price"], keep="first")
        frame.loc[grouped.cumcount().eq(0) | ~frame.valid_receipt | frame.delta_oi.eq(0), "delta_oi"] = float("nan")
        return frame

    @staticmethod
    def _futures_symbol(rows: list[dict]) -> str:
        symbols = [row["canonical_symbol"] for row in rows if row["instrument_class"] in {"FUTURES", "FUTURES_OI"} and str(row.get("canonical_symbol", "")).endswith("FUT")]
        return Counter(symbols).most_common(1)[0][0] if symbols else ""

    def _inventory(self, session: str, market: pd.DataFrame, oi: pd.DataFrame, futures: str) -> list[dict]:
        self.callback_invocations["inventory"] += 1
        rows = [dict(row) for row in self.c.get("fixed_inventory_rows", self.config.get("fixed_inventory_rows", [])) if str(row.get("evaluation_date")) == session]
        future_expiries = sorted(value for value in oi.loc[(oi.instrument_class == "future") & oi.expiry_date.notna(), "expiry_date"].unique()) if not oi.empty else []
        option_expiries = sorted(value for value in oi.loc[oi.instrument_class.isin(["call", "put"]) & oi.expiry_date.notna(), "expiry_date"].unique()) if not oi.empty else []
        if not rows:
            rows.extend(self._fixed_inventory_rows(session, futures, future_expiries[0] if future_expiries else None, option_expiries[0] if option_expiries else None))
        # Inventory's frozen causal as-of join is independently configured at
        # five seconds.  The exact 2,000-ms clock remains exclusive to the
        # synchronized basis/divergence path below.
        tolerance = float(self.config.get("inventory_join_tolerance_seconds", 5))
        bin_points = float(self.config.get("inventory_bin_points", 25))
        frames: dict[str, pd.DataFrame] = {}
        if futures and not market.empty and {INDEX_SYMBOL, futures}.issubset(set(market.symbol)):
            price = inventory_engine.price_events(market, session, futures, INDEX_SYMBOL, tolerance)
            frames["BN_REF_FUT_VOLUME_VPOC"] = price
        if futures and not oi.empty and not market.empty and INDEX_SYMBOL in set(market.symbol):
            option_expiries = sorted(value for value in oi.loc[oi.instrument_class.isin(["call", "put"]), "expiry_date"].dropna().unique())
            option_expiry = option_expiries[0] if option_expiries else None
            joined = inventory_engine.oi_events(oi, market, session, futures, option_expiry, INDEX_SYMBOL, tolerance)
            for family in inventory_engine.FAMILIES[1:]:
                frames[family] = joined[joined.family == family].copy()
        for family in inventory_engine.FAMILIES:
            frame = frames.get(family)
            if frame is None or frame.empty:
                continue
            expiry = (future_expiries[0] if future_expiries else None) if family.startswith(("BN_", "FUT_")) else (option_expiries[0] if option_expiries else None)
            rows.extend(inventory_engine.transitions(frame, family, session, futures, expiry, bin_points))
        keyed = {}
        for row in rows:
            key = (row.get("horizon"), row.get("family"), row.get("control_effective_timestamp"), row.get("control_value"))
            keyed[key] = _jsonable(row)
        return [keyed[key] for key in sorted(keyed, key=lambda item: tuple(str(value) for value in item))]

    def _fixed_inventory_rows(self, session: str, futures: str, futures_expiry, option_expiry) -> list[dict]:
        """Build/cache prior-session profiles with canonical inventory functions."""
        data_value = self.c.get("data_root")
        if not data_value or not futures:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "RAW_ROOT_OR_SELECTED_FUTURES_MISSING"}
            return []
        data_root = Path(data_value)
        raw_root = data_root / "raw"
        oi_root = data_root / "oi"
        if not raw_root.is_dir() or not oi_root.is_dir() or "research" in data_root.resolve().parts:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "PERMITTED_RAW_ROOT_MISSING"}
            return []
        memory_key = (session, futures)
        if memory_key in self._fixed_profiles_memory:
            key, cached = self._fixed_profiles_memory[memory_key]
            return self._materialize_fixed_inventory(session, futures, futures_expiry, option_expiry, key, cached, True)
        common = sorted({path.name for path in raw_root.iterdir() if path.is_dir()} & {path.name for path in oi_root.iterdir() if path.is_dir()})
        prior = [value for value in common if value < session]
        if not prior:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "NO_PRIOR_RAW_SESSIONS"}
            return []
        canonical_config = {
            "index_symbol": INDEX_SYMBOL,
            "futures_symbol": futures,
            "discovery_start": prior[0],
            "discovery_end": prior[-1],
            "maximum_missing_oi_minutes": int(self.config.get("inventory_maximum_missing_oi_minutes", 0)),
            "join_tolerance_seconds": float(self.config.get("inventory_join_tolerance_seconds", 5)),
            "bin_points": float(self.config.get("inventory_bin_points", 25)),
        }
        paths = []
        for source_session in prior:
            paths.extend(sorted((raw_root / source_session).glob("events_*.jsonl")))
            paths.extend(sorted((oi_root / source_session).glob("oi_*.jsonl")))
        raw_hashes = {str(path.relative_to(data_root)): self._raw_sha(path) for path in paths}
        self._persist_raw_hash_cache()
        key = _hash("FIXED", self.c.get("engine_hash", ""), self.c.get("configuration_hash", ""), canonical_config, raw_hashes)
        cache_root = self.state_root / "fixed_inventory_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_path = cache_root / f"{key}.json"
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text())
            if cached.get("cache_key") != key:
                raise ValueError("fixed inventory cache key mismatch")
            cache_hit = True
        else:
            missing = [value for value in prior if (futures, value) not in self._eligibility_memory]
            if missing:
                discovery_config = {**canonical_config, "discovery_start": missing[0], "discovery_end": missing[-1]}
                discovered, _ = inventory_engine.discover_sessions(data_root, discovery_config)
                for row in discovered:
                    self._eligibility_memory[(futures, row["date"])] = row
            eligibility = [self._eligibility_memory[(futures, value)] for value in prior if (futures, value) in self._eligibility_memory]
            accepted = [row["date"] for row in eligibility if row["status"] == "ACCEPTED"]
            # R6C0I froze 2026-08-17 as rejected; live startup must not silently
            # rehabilitate it through a partial or changed discovery boundary.
            accepted = [value for value in accepted if value < session and value != "2026-08-17"]
            chain = accepted[-3:]
            profiles = []
            frames = {}
            contracts = {}
            for source_session in chain:
                source_oi = raw_reader.load_oi(oi_root, source_session)
                source_futures, source_futures_expiry, source_option_expiry = raw_reader.select_contracts(source_oi, source_session)
                source_market = raw_reader.load_market(raw_root, source_session, {INDEX_SYMBOL, source_futures})
                contracts[source_session] = (source_futures, source_futures_expiry, source_option_expiry)
                frames[source_session] = {
                    "price": inventory_engine.price_events(source_market, source_session, source_futures, INDEX_SYMBOL, canonical_config["join_tolerance_seconds"]),
                    "oi": inventory_engine.oi_events(source_oi, source_market, source_session, source_futures, source_option_expiry, INDEX_SYMBOL, canonical_config["join_tolerance_seconds"]),
                }
            for horizon, count in (("1D", 1), ("2D", 2), ("3D", 3)):
                sources = chain[-count:]
                if len(sources) < count:
                    continue
                for family in inventory_engine.FAMILIES:
                    parts = [frames[value]["price"] if family == "BN_REF_FUT_VOLUME_VPOC" else frames[value]["oi"][frames[value]["oi"].family == family] for value in sources]
                    sample = pd.concat(parts, ignore_index=True)
                    result = inventory_engine.profile(sample, canonical_config["bin_points"])
                    if result is None:
                        continue
                    profiles.append({
                        "horizon": horizon, "family": family, "source_sessions": "|".join(sources),
                        "freshness_receipt_timestamp": inventory_engine.iso(sample.receipt_timestamp.max()),
                        **_jsonable(result),
                    })
            august = next((row for row in eligibility if row.get("date") == "2026-08-17"), None)
            cached = {
                "cache_key": key, "profiles": profiles, "source_chain": chain,
                "eligibility": eligibility, "raw_input_hashes": raw_hashes,
                "august_17_status": "PRESERVED_REJECTION" if "2026-08-17" not in accepted else "ERROR_ACCEPTED",
                "august_17_reason": august.get("reason", "EXPLICIT_FROZEN_REJECTION") if august else "EXPLICIT_FROZEN_REJECTION",
            }
            cached = _jsonable(cached)
            atomic_json(cache_path, cached)
            cache_hit = False
        self._fixed_profiles_memory[memory_key] = (key, cached)
        return self._materialize_fixed_inventory(session, futures, futures_expiry, option_expiry, key, cached, cache_hit)

    def _materialize_fixed_inventory(self, session: str, futures: str, futures_expiry, option_expiry, key: str, cached: Mapping[str, object], cache_hit: bool) -> list[dict]:
        self._fixed_cache_info[session] = {
            "status": "AVAILABLE" if cached.get("profiles") else "INSUFFICIENT_PRIOR_SESSIONS",
            "cache_key": key, "cache_hit": cache_hit, "source_chain": cached.get("source_chain", []),
            "current_session_excluded": session not in cached.get("source_chain", []),
            "august_17_status": cached.get("august_17_status", ""),
            "raw_input_file_count": len(cached.get("raw_input_hashes", {})),
        }
        rows = []
        for profile in cached.get("profiles", []):
            family = profile["family"]
            expiry = futures_expiry if family.startswith(("BN_", "FUT_")) else option_expiry
            if expiry is None:
                continue
            rows.append(inventory_engine.record(
                session, profile["horizon"], family, profile["control_value"], profile["source_sessions"],
                f"{session}T09:15:00+05:30", profile["freshness_receipt_timestamp"], futures, expiry,
                profile["count"], profile["winning_bin_weight"], profile["runner_up_bin"],
                profile["runner_up_weight"], profile["tie_break_reason"],
            ))
        return rows

    def _raw_sha(self, path: Path) -> str:
        """Hash each immutable prior raw file once per stable stat signature."""
        stat = path.stat()
        data_root = Path(self.c.get("data_root", path.parent)).resolve()
        try:
            key = str(path.resolve().relative_to(data_root))
        except ValueError:
            key = str(path.resolve())
        cached = self._raw_hash_memory.get(key)
        signature = (stat.st_size, stat.st_mtime_ns)
        if cached is not None and cached[:2] == signature:
            return cached[2]
        durable = self._raw_hash_cache.get(key)
        if durable is not None and (
            int(durable.get("size", -1)), int(durable.get("mtime_ns", -1))
        ) == signature:
            digest = str(durable["sha256"])
            self._raw_hash_memory[key] = (*signature, digest)
            return digest
        digest = inventory_engine.sha(path)
        self._raw_hash_memory[key] = (*signature, digest)
        self._raw_hash_cache[key] = {
            "size": signature[0], "mtime_ns": signature[1], "sha256": digest,
        }
        self._raw_hash_cache_dirty = True
        return digest

    def _load_raw_hash_cache(self) -> dict[str, dict]:
        if not self.raw_hash_cache_path.is_file():
            return {}
        try:
            value = json.loads(self.raw_hash_cache_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixed raw source hash cache corrupt: {error}") from error
        if value.get("version") != "R6E1R_FIXED_RAW_HASH_CACHE_V1" or not isinstance(
            value.get("files"), dict
        ):
            raise ValueError("fixed raw source hash cache version mismatch")
        return value["files"]

    def _persist_raw_hash_cache(self) -> None:
        if not self._raw_hash_cache_dirty:
            return
        atomic_json(self.raw_hash_cache_path, {
            "version": "R6E1R_FIXED_RAW_HASH_CACHE_V1",
            "files": self._raw_hash_cache,
        })
        self._raw_hash_cache_dirty = False

    def _divergence(self, session: str, market: pd.DataFrame, futures: str):
        self.callback_invocations["synchronization"] += 1
        if not futures or market.empty or not {INDEX_SYMBOL, futures}.issubset(set(market.symbol)):
            return [], None, []
        basis = divergence_detector.causal_basis(market, session, INDEX_SYMBOL, futures, int(self.config.get("synchronization_tolerance_ms", 2000)))
        if not basis:
            return [], None, []
        self.callback_invocations["divergence_detector"] += 1
        frame = divergence_detector.derive(basis)
        candidates = []
        for row in divergence_detector.episodes(frame):
            if row.get("episode_type") not in {"GREEN_CONFIRMED", "RED_CONFIRMED"}:
                continue
            confirmation = parse_timestamp(row["confirmation_timestamp"], field_name="divergence confirmation")
            point = frame[frame.t == confirmation]
            if point.empty:
                continue
            current = point.iloc[-1]
            candidates.append({
                "evaluation_date": session,
                "colour": "GREEN" if row["episode_type"] == "GREEN_CONFIRMED" else "RED",
                "candidate_start_timestamp": row["start_timestamp"],
                "confirmation_timestamp": row["confirmation_timestamp"],
                "episode_end_timestamp": row["end_timestamp"],
                "index_at_confirmation": _jsonable(current["index"]),
                "futures_at_confirmation": _jsonable(current["futures"]),
                "basis_at_confirmation": _jsonable(current["basis"]),
                "index_receipt_timestamp": str(current["index_receipt_timestamp"]),
                "futures_receipt_timestamp": str(current["futures_receipt_timestamp"]),
            })
        return _jsonable(basis), frame, candidates

    @staticmethod
    def _trailing_unconfirmed_candidate_start(
        frame: pd.DataFrame | None,
    ) -> str:
        """Return the causal start of a trailing unresolved candidate run.

        The frozen detector confirms only after its persistence rule.  Until
        then a later confirmation can assign the already-observed candidate
        start as the next dependency-group boundary, invalidating terminal
        lifecycle-derived rows after that clock.  The derived detector frame
        is the authority for this provisional condition; no wall clock or
        display clock participates.
        """
        if frame is None or frame.empty:
            return ""
        tail = frame.iloc[-1]
        candidate = str(tail.get("candidate_state", ""))
        if candidate not in {"GREEN_CANDIDATE", "RED_CANDIDATE"}:
            return ""
        if str(tail.get("divergence_state", "")) in {
            "GREEN_CONFIRMED", "RED_CONFIRMED",
        }:
            return ""
        start = len(frame) - 1
        while start > 0:
            current = frame.iloc[start]
            prior = frame.iloc[start - 1]
            if str(prior.get("candidate_state", "")) != candidate:
                break
            current_time = parse_timestamp(
                current["t"], field_name="candidate stability current clock"
            )
            prior_time = parse_timestamp(
                prior["t"], field_name="candidate stability prior clock"
            )
            if (
                current_time - prior_time
            ).total_seconds() > divergence_detector.MERGE_GAP:
                break
            start -= 1
        return parse_timestamp(
            frame.iloc[start]["t"],
            field_name="candidate stability start clock",
        ).isoformat()

    @staticmethod
    def _index_frame(market: pd.DataFrame) -> pd.DataFrame:
        if market.empty:
            return pd.DataFrame(columns=["t", "index"])
        values = market[(market.symbol == INDEX_SYMBOL) & market.receipt_timestamp.notna() & market.last_price.notna()].sort_values(["receipt_timestamp", "source_file", "source_row"])
        return values[["receipt_timestamp", "last_price"]].rename(columns={"receipt_timestamp": "t", "last_price": "index"})

    def _participation(
        self,
        session: str,
        rows: list[dict],
        episodes: list[dict],
        dependencies: list[dict],
        lifecycle: list[dict],
    ) -> dict:
        self.callback_invocations["participation"] += 1
        store = self._participation_store(rows)
        config = {
            "windows_minutes": list(self.config.get("participation_windows_minutes", [1, 3, 5])),
            "volume_spike_percentile": float(self.config.get("participation_volume_spike_percentile", .9)),
            "oi_spike_percentile": float(self.config.get("participation_oi_spike_percentile", .9)),
            "freshness_seconds": float(self.config.get("freshness_seconds", {}).get("futures_oi", 180)) if isinstance(self.config.get("freshness_seconds"), Mapping) else float(self.config.get("freshness_seconds", 180)),
            "strike_step": int(self.config.get("participation_strike_step", 100)),
            "near_strikes_each_side": int(self.config.get("participation_near_strikes_each_side", 3)),
        }
        futures_rows: list[dict] = []
        option_rows: list[dict] = []
        cutoff = max((parse_timestamp(row["receipt_timestamp"]).to_pydatetime() for row in rows), default=None)
        lifecycle_ends: dict[str, datetime] = {}
        for row in lifecycle:
            episode_id = str(row.get("episode_id", ""))
            if not episode_id:
                continue
            instant = parse_timestamp(
                row["state_entry_timestamp"], field_name="participation lifecycle end"
            ).to_pydatetime()
            lifecycle_ends[episode_id] = max(
                lifecycle_ends.get(episode_id, instant), instant
            )
        for episode in episodes:
            confirmation = parse_timestamp(episode["confirmation_timestamp"]).to_pydatetime()
            end = lifecycle_ends.get(str(episode["episode_id"]), confirmation)
            if cutoff is not None:
                end = min(end, cutoff)
            anchor = {**episode, "confirmation": confirmation, "end": end}
            times = [confirmation]
            times.extend(sorted({
                item["receipt"]
                for values in store.oi.values()
                for item in values
                if confirmation < item["receipt"] <= end
            }))
            for at in times:
                futures, options = participation_engine.participation_at(store, anchor, at, config)
                futures_rows.append(futures)
                option_rows.extend(options)
        return self._build_participation_views(session, futures_rows, option_rows, episodes, dependencies)

    @staticmethod
    def _participation_store(rows: list[dict]) -> participation_engine.RawStore:
        """Mirror ``RawStore.load_raw`` physical-stream lineage exactly."""
        store = participation_engine.RawStore()
        for row in rows:
            receipt = parse_timestamp(row["receipt_timestamp"], field_name="participation receipt").to_pydatetime()
            common = {"receipt": receipt, "price": row.get("price"), "volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""), "source_row": row.get("source_row_number", 0)}
            if (
                _source_stream(row) == "raw"
                and row["instrument_class"] in KNOWN_CLASSES
                and (row.get("price") is not None or row.get("cumulative_volume") is not None)
            ):
                store.market.setdefault(row["canonical_symbol"], []).append(common)
            elif _source_stream(row) == "oi" and row["instrument_class"] in {"FUTURES_OI", "CE", "PE"}:
                expiry = str(row.get("expiry") or "")
                if row["instrument_class"] in {"CE", "PE"} and expiry:
                    parsed_expiry = _expiry(expiry)
                    if parsed_expiry is not None:
                        expiry = parsed_expiry.strftime("%d-%m-%Y")
                store.oi.setdefault(row["canonical_symbol"], []).append({**common, "oi": row.get("open_interest"), "strike": row.get("strike"), "option_type": row.get("option_type"), "expiry": expiry})
        store.finalize()
        return store

    def _build_participation_views(self, session: str, futures: list[dict], options: list[dict], episodes: list[dict], dependencies: list[dict]) -> dict:
        self.callback_invocations["participation_views"] += 1
        dependency = {row["episode_id"]: row for row in dependencies}
        anchors = [{**episode, "dependency_group_id": dependency.get(episode["episode_id"], {}).get("dependency_group_id", "")} for episode in episodes]
        with tempfile.TemporaryDirectory(prefix="r6e-live-views-", dir=self.state_root) as name:
            root = Path(name)
            native = root / "native"
            output = root / "views"
            native.mkdir()
            futures_path = native / "futures_participation.csv"
            options_path = native / "option_participation.csv"
            breadth_path = native / "option_strike_breadth.csv"
            anchor_path = native / "episode_anchors.csv"
            _write_csv(futures_path, futures, ("record_id", "episode_id", "evaluation_date", "observation_timestamp", "receipt_timestamp"))
            _write_csv(options_path, options, ("record_id", "episode_id", "evaluation_date", "observation_timestamp", "receipt_timestamp", "option_type"))
            _write_csv(breadth_path, participation_views.breadth(options), ("episode_id", "observation_timestamp", "selected_strike_count", "supportive_count", "contradictory_count", "mixed", "broad_agreement", "ce_pe_agreement"))
            _write_csv(anchor_path, anchors, ("episode_id", "evaluation_date", "colour", "confirmation_timestamp", "dependency_group_id"))
            seal = participation_views.build(native, anchor_path, breadth_path, output, "stream")
            dense = _read_csv(output / "dense_participation_view.csv")
            transitions = _read_csv(output / "transition_participation_ledger.csv")
            summaries = _read_csv(output / "episode_participation_summary.csv")
            compatibility = _read_csv(output / "legacy_compatibility_snapshot.csv")
        return {"dense": dense, "transitions": transitions, "summaries": summaries, "compatibility": compatibility, "seal": seal}

    def _availability(
        self,
        session: str,
        rows: list[dict],
        inventory: list[dict],
        *,
        reference_time: object | None = None,
    ) -> dict:
        evidence_cutoff = max(
            (parse_timestamp(row["receipt_timestamp"]) for row in rows), default=None
        )
        reference = (
            parse_timestamp(reference_time, field_name="availability reference clock")
            if reference_time is not None
            else evidence_cutoff
        )
        calculation = reference if reference_time is not None else datetime.now(IST)
        latest = {}
        for row in rows:
            kind = row["instrument_class"]
            stream = _source_stream(row)
            valid = (
                stream == "raw" and kind in {"INDEX", "FUTURES"}
                and row.get("price") is not None
            ) or (
                stream == "oi" and kind in {"FUTURES_OI", "CE", "PE"}
                and row.get("open_interest") is not None
            )
            if not valid:
                continue
            instant = parse_timestamp(row["receipt_timestamp"])
            if kind not in latest or instant > latest[kind]:
                latest[kind] = instant
        return self._availability_from_latest(
            latest,
            inventory,
            evidence_cutoff=evidence_cutoff,
            reference=reference,
            calculation=calculation,
        )

    def _availability_from_latest(
        self,
        latest: Mapping[str, object],
        inventory: Iterable[Mapping[str, object]],
        *,
        evidence_cutoff: object | None,
        reference: object | None,
        calculation: object,
    ) -> dict:
        """Classify availability from one immutable latest-receipt view."""
        limits = self.config.get("freshness_seconds", {}) if isinstance(self.config.get("freshness_seconds"), Mapping) else {}
        def fresh(kind: str, seconds: float) -> bool:
            return reference is not None and kind in latest and 0 <= (reference - latest[kind]).total_seconds() <= seconds
        market = fresh("INDEX", float(limits.get("index", 10))) and fresh("FUTURES", float(limits.get("futures", 10)))
        layers = {}
        for horizon in ("1D", "2D", "3D"):
            present = any(row.get("horizon") == horizon for row in inventory)
            layers[horizon] = context_availability.LayerAvailability(horizon, "AVAILABLE" if present else "MISSING_PRIOR_SESSION", "CACHED_RAW_PRIOR_CONTEXT" if present else "INSUFFICIENT_PRIOR_SESSIONS")
        id_state = "AVAILABLE" if market else "STALE_DATA" if any(kind in latest for kind in ("INDEX", "FUTURES")) else "NOT_YET_AVAILABLE"
        layers["ID"] = context_availability.LayerAvailability("ID", id_state, "FRESH_SYNCHRONIZED_MARKET" if market else "MARKET_INPUT_STALE_OR_MISSING")
        participation_available = fresh("FUTURES_OI", float(limits.get("futures_oi", 180))) or fresh("CE", float(limits.get("ce", 180))) or fresh("PE", float(limits.get("pe", 180)))
        classified = context_availability.classify_context(layers, divergence_inputs_available=market, participation_inputs_available=participation_available)
        # Required market inputs that have arrived but are stale/invalid are a
        # distinct operational state, not a generic missing-input suspension.
        # This exact label is consumed by the live GUI/readiness projection.
        if not market and any(kind in latest for kind in ("INDEX", "FUTURES")):
            classified["divergence_state"] = "STALE_DATA"
        return {
            **classified,
            "layers": {horizon: {"state": layer.state, "reason": layer.reason} for horizon, layer in layers.items()},
            "index_state": "AVAILABLE" if fresh("INDEX", float(limits.get("index", 10))) else "STALE_OR_MISSING",
            "futures_state": "AVAILABLE" if fresh("FUTURES", float(limits.get("futures", 10))) else "STALE_OR_MISSING",
            "futures_oi_state": "AVAILABLE" if fresh("FUTURES_OI", float(limits.get("futures_oi", 180))) else "STALE_OR_MISSING",
            "ce_state": "AVAILABLE" if fresh("CE", float(limits.get("ce", 180))) else "STALE_OR_MISSING",
            "pe_state": "AVAILABLE" if fresh("PE", float(limits.get("pe", 180))) else "STALE_OR_MISSING",
            "evidence_cutoff_timestamp": evidence_cutoff.isoformat() if evidence_cutoff is not None else "",
            "calculation_timestamp": calculation.isoformat(),
            "reference_timestamp": reference.isoformat() if reference is not None else "",
            "receipt_ages_seconds": {
                kind: (reference - instant).total_seconds()
                for kind, instant in latest.items()
            } if reference is not None else {},
        }

    def _gui_payload(self, result: Mapping[str, object]) -> dict:
        self.callback_invocations["gui_projection"] += 1
        basis = [row for row in result["basis"] if row.get("validity_status") == "VALID"]
        price = [{"t": row.get("basis_timestamp", ""), "i": row.get("index_price", ""), "f": row.get("futures_price", ""), "b": row.get("basis_value", ""), "it": row.get("index_receipt_timestamp", ""), "ft": row.get("futures_receipt_timestamp", ""), "a": row.get("absolute_receipt_difference_ms", "")} for row in basis]
        mechanism = []
        prior_mechanism: dict[str, object] = {}
        mechanism_fields = (
            "episode_id", "timestamp", "availability_timestamp",
            "resolution_mechanism_native", "resolution_mechanism_compatibility",
            "signed_basis_convergence", "index_contribution",
            "futures_contribution", "new_extreme_flag",
            "stalled_extreme_duration_seconds",
        )
        for row in result["resolution"]:
            episode = str(row.get("episode_id", ""))
            value = row.get("resolution_mechanism_native")
            if prior_mechanism.get(episode) == value:
                continue
            prior_mechanism[episode] = value
            mechanism.append(gui_adapter._project(row, mechanism_fields))
        payload = {
            "schema": "R6E_LIVE_SESSION_PAYLOAD_V1",
            "classification": self.config.get("classification", "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"),
            "date": result["session_date"],
            "availability": result["availability"],
            "price": gui_adapter._pack(price),
            "inventory": gui_adapter._pack(result["inventory"]),
            "episodes": gui_adapter._pack(result["episodes"]),
            "dependencies": gui_adapter._pack(result["dependencies"]),
            "lifecycle": gui_adapter._pack(result["lifecycle"]),
            "resolution_mechanisms": gui_adapter._pack(mechanism),
            "participation_dense": gui_adapter._pack(result["participation_dense"]),
            "participation_transitions": gui_adapter._pack(result["participation_transitions"]),
            "participation_summaries": gui_adapter._pack(result["participation_summaries"]),
            "compatibility_snapshots": gui_adapter._pack(result["compatibility_snapshots"]),
            "cross_layer_transitions": gui_adapter._pack(result["cross_layer_transitions"]),
        }
        payload["counts"] = {key: len(value.get("rows", [])) for key, value in payload.items() if isinstance(value, dict) and "rows" in value}
        payload["projection_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return payload

    def _publish(
        self,
        outputs: Mapping[str, dict],
        previous: Mapping[str, dict],
        *,
        publish_deferred: bool = False,
    ) -> None:
        for session, result in outputs.items():
            cutoff = result["availability"].get("calculation_timestamp", "")
            deferred_group = (
                ""
                if publish_deferred
                else self._pending_unstable_dependency_groups.get(session, "")
            )
            episode_groups = {
                str(row["episode_id"]): str(row["dependency_group_id"])
                for row in result["dependencies"]
            }
            provisional_lifecycle_ids: set[str] = set()
            provisional_episode_ids: set[str] = set()
            if not publish_deferred:
                for row in result["lifecycle"]:
                    if (
                        row.get("state") == "EXPIRED_OR_UNRESOLVED"
                        and row.get("reason_code")
                        == "LIFECYCLE_END_WITHOUT_FAVOURABLE_RESPONSE"
                    ):
                        provisional_lifecycle_ids.add(str(row["record_id"]))
                        provisional_episode_ids.add(str(row["episode_id"]))
            # Participation is bounded by the latest lifecycle state entry.
            # A live prefix can therefore contain observations admitted only
            # by a provisional terminal expiration.  A later standalone Index
            # response can remove that expiration and shrink the participation
            # window.  Hold every transition for the affected episode until
            # either the provisional condition clears or the session seals.
            provisional_participation_ids = {
                str(row["transition_id"])
                for row in result["participation_transitions"]
                if str(row.get("episode_id", "")) in provisional_episode_ids
            }
            provisional_cross_layer_sources = (
                provisional_lifecycle_ids | provisional_participation_ids
            )

            def deferred_episode(row: Mapping[str, object]) -> bool:
                if not deferred_group:
                    return False
                group = str(row.get("dependency_group_id", ""))
                if not group:
                    group = episode_groups.get(str(row.get("episode_id", "")), "")
                return group == deferred_group

            for row in result["episodes"]:
                self._append_once("divergence_confirmations", row, row["episode_id"], cutoff)
            for row in result["dependencies"]:
                self._append_once("dependency_retriggers", row, f"dependency:{row['episode_id']}", cutoff)
            for row in result["lifecycle"]:
                if (
                    deferred_episode(row)
                    or str(row["record_id"]) in provisional_lifecycle_ids
                ):
                    continue
                self._append_once("lifecycle_transitions", row, str(row["record_id"]), cutoff)
            for row in result["inventory"]:
                identity = _hash("INVENTORY", row.get("evaluation_date"), row.get("horizon"), row.get("family"), row.get("control_effective_timestamp"), row.get("control_value"))
                self._append_once("inventory_winner_transitions", row, identity, cutoff)
            for row in result["participation_transitions"]:
                if (
                    deferred_episode(row)
                    or str(row["transition_id"])
                    in provisional_participation_ids
                ):
                    continue
                self._append_once("participation_transitions", row, str(row["transition_id"]), cutoff)
            for row in result["cross_layer_transitions"]:
                if (
                    row.get("episode_id") and deferred_episode(row)
                ) or str(row.get("source_record_id", "")) in (
                    provisional_cross_layer_sources
                ):
                    continue
                self._append_once("cross_layer_transitions", row, str(row["transition_id"]), cutoff)

    def _publish_availability(
        self,
        session: str,
        current: Mapping[str, object],
        old: Mapping[str, object],
        *,
        reason: str = "MATERIAL_AVAILABILITY_CHANGE",
    ) -> None:
        calculation = str(current.get("calculation_timestamp", ""))
        prior_states = self._availability_states(old)
        for component, state in self._availability_states(current).items():
            prior = prior_states.get(component, "NOT_YET_AVAILABLE")
            if prior == state:
                continue
            if reason == "SESSION_AVAILABILITY_SEAL":
                # Preserve the frozen seal contract: all component declarations
                # share the final causal evidence cutoff.  Periodic live
                # freshness events use the distinct evidence-clock path below.
                effective = str(
                    current.get("evidence_cutoff_timestamp")
                    or current.get("reference_timestamp")
                    or calculation
                )
                evidence_identity = ""
            else:
                # A refresh can append these rows and then crash before the
                # copy-on-write output is persisted.  The retry wall clock is
                # therefore not an event identity.  Derive both the event
                # clock and identity from the latest source receipts plus the
                # frozen freshness thresholds so a later retry publishes the
                # same immutable event.
                effective, evidence_identity = (
                    self._availability_transition_evidence(
                        session, current, component, state
                    )
                )
            event = {
                "session_date": session,
                "component": component,
                "previous_state": prior,
                "new_state": state,
                "effective_timestamp": effective,
                "reason": reason,
            }
            if evidence_identity:
                event["evidence_identity"] = evidence_identity
                identity = _hash(
                    "AVAILABILITY", reason, session, component, prior, state,
                    evidence_identity,
                )
            else:
                # Do not alter verified SESSION_AVAILABILITY_SEAL identities.
                identity = _hash(
                    "AVAILABILITY", reason, session, component, effective, state
                )
            self._append_once(
                "availability_transitions", event, identity, calculation
            )
            if "STALE" in prior or "STALE" in state:
                stale_identity = (
                    _hash(
                        "STALE", reason, session, component, prior, state,
                        evidence_identity,
                    )
                    if evidence_identity
                    else _hash(
                        "STALE", reason, session, component, effective, state
                    )
                )
                self._append_once(
                    "stale_recovery_transitions",
                    event,
                    stale_identity,
                    calculation,
                )

    def _availability_transition_evidence(
        self,
        session: str,
        current: Mapping[str, object],
        component: str,
        state: str,
    ) -> tuple[str, str]:
        """Return a deterministic evidence clock and freshness identity.

        ``reference_timestamp`` is intentionally excluded from the identity:
        it is merely the poll clock that noticed a transition.  Exact source
        receipts are recovered from the live normalized bucket, and an
        unavailable state is timed at the configured freshness boundary.
        """
        limits = (
            self.config.get("freshness_seconds", {})
            if isinstance(self.config.get("freshness_seconds"), Mapping)
            else {}
        )
        seconds = {
            "INDEX": float(limits.get("index", 10)),
            "FUTURES": float(limits.get("futures", 10)),
            "FUTURES_OI": float(limits.get("futures_oi", 180)),
            "CE": float(limits.get("ce", 180)),
            "PE": float(limits.get("pe", 180)),
        }
        latest: dict[str, object] = {}
        for row in self._sessions.get(session, {}).values():
            kind = str(row.get("instrument_class", ""))
            stream = _source_stream(row)
            valid = (
                stream == "raw"
                and kind in {"INDEX", "FUTURES"}
                and row.get("price") is not None
            ) or (
                stream == "oi"
                and kind in {"FUTURES_OI", "CE", "PE"}
                and row.get("open_interest") is not None
            )
            if not valid:
                continue
            instant = parse_timestamp(
                row.get("receipt_timestamp"),
                field_name="availability transition source receipt",
            )
            if kind not in latest or instant > latest[kind]:
                latest[kind] = instant

        dependencies: tuple[str, ...]
        if component in {"HORIZON_ID", "DIVERGENCE_STATE", "OVERALL_STATE"}:
            dependencies = ("INDEX", "FUTURES")
        elif component == "PARTICIPATION_STATE":
            dependencies = ("FUTURES_OI", "CE", "PE")
        elif component == "INDEX_STATE":
            dependencies = ("INDEX",)
        elif component == "FUTURES_STATE":
            dependencies = ("FUTURES",)
        elif component == "FUTURES_OI_STATE":
            dependencies = ("FUTURES_OI",)
        elif component == "CE_STATE":
            dependencies = ("CE",)
        elif component == "PE_STATE":
            dependencies = ("PE",)
        else:
            dependencies = ()

        descriptor = [
            {
                "instrument_class": kind,
                "receipt_timestamp": (
                    latest[kind].isoformat() if kind in latest else "MISSING"
                ),
                "freshness_seconds": seconds[kind],
            }
            for kind in dependencies
        ]
        evidence_identity = _hash(
            "AVAILABILITY_EVIDENCE", component, descriptor
        )

        fallback = str(
            current.get("evidence_cutoff_timestamp")
            or current.get("calculation_timestamp")
            or current.get("reference_timestamp")
        )
        if not dependencies or not any(kind in latest for kind in dependencies):
            return fallback, evidence_identity

        available = state in {
            "AVAILABLE", "LIVE_FULL_CONTEXT", "LIVE_PARTIAL_CONTEXT",
            "LIVE_INTRADAY_ONLY",
        }
        if available:
            candidates = [latest[kind] for kind in dependencies if kind in latest]
            if component == "PARTICIPATION_STATE":
                reference_value = current.get("reference_timestamp")
                reference = (
                    parse_timestamp(
                        reference_value,
                        field_name="availability transition reference clock",
                    )
                    if reference_value not in (None, "")
                    else None
                )
                if reference is not None:
                    fresh_candidates = [
                        latest[kind]
                        for kind in dependencies
                        if kind in latest
                        and 0 <= (reference - latest[kind]).total_seconds()
                        <= seconds[kind]
                    ]
                    if fresh_candidates:
                        candidates = fresh_candidates
            effective = max(candidates)
        else:
            expirations = [
                latest[kind] + timedelta(seconds=seconds[kind])
                for kind in dependencies
                if kind in latest
            ]
            effective = (
                max(expirations)
                if component == "PARTICIPATION_STATE"
                else min(expirations)
            )
        return effective.isoformat(), evidence_identity

    @staticmethod
    def _availability_states(value: Mapping[str, object]) -> dict[str, str]:
        if not value:
            return {}
        result = {f"HORIZON_{key}": str(item.get("state", "")) for key, item in value.get("layers", {}).items()}
        for key in ("divergence_state", "participation_state", "index_state", "futures_state", "futures_oi_state", "ce_state", "pe_state", "overall_state"):
            if key in value:
                result[key.upper()] = str(value[key])
        return result

    def _append_once(self, ledger_name: str, row: Mapping[str, object], identity: str, calculation_timestamp: str) -> None:
        event_id = identity if identity.startswith(("BDR1-", "R6", "XL-")) else _hash("ANALYTICAL", ledger_name, identity)
        value = _material_ledger_projection(ledger_name, row)
        supplied_event_id = value.get("event_id")
        if supplied_event_id not in (None, "", event_id):
            raise ValueError(
                f"{ledger_name} supplied event identity conflicts with "
                f"deterministic identity {event_id}"
            )
        value["event_id"] = event_id
        value.setdefault("calculation_timestamp", calculation_timestamp)
        value["publication_timestamp"] = datetime.now(IST).isoformat()
        value.setdefault("engine_hash", self.c.get("engine_hash", ""))
        value.setdefault("configuration_hash", self.c.get("configuration_hash", ""))
        value.setdefault("raw_run_id", self.c.get("raw_run_id", ""))
        _validate_material_ledger_row(ledger_name, value)
        content = _material_ledger_content(ledger_name, value)
        prior_content = self._ledger_content[ledger_name].get(event_id)
        if prior_content is not None:
            if prior_content != content:
                raise ValueError(
                    f"append-only {ledger_name} identity reused with "
                    f"different immutable content: {event_id}"
                )
            return
        ledger = self.ledgers[ledger_name]
        boundary = ledger.append_boundary()
        try:
            ledger.append(value)
        except Exception:
            # An append wrapper can report an error after the underlying
            # fsynced write completed. Reconcile only the attempted bounded
            # tail before propagating the error so a dirty-session retry cannot
            # publish a duplicate or accept different same-ID content.
            committed = ledger.reconcile_appended_prefix(
                boundary, [value], identity_field="event_id"
            )
            if event_id in committed:
                self._ledger_content[ledger_name][event_id] = content
            raise
        self._ledger_content[ledger_name][event_id] = content

    def _quality(self, row: Mapping[str, object], reason: str, detail: str) -> None:
        identity = _hash("QUALITY", row.get("observation_id") or row.get("event_id") or row.get("raw_record_id"), reason)
        event_id = _hash("ANALYTICAL", "refusals_data_quality", identity)
        receipt = row.get("receipt_timestamp") or row.get("effective_timestamp") or ""
        try:
            effective = parse_timestamp(receipt).isoformat()
            effective_provenance = "EVIDENCE"
        except ValueError:
            effective = datetime.now(IST).isoformat()
            effective_provenance = "WALL_CLOCK_FALLBACK"
        publication = datetime.now(IST).isoformat()
        value = {
            "event_id": event_id, "session_date": str(row.get("session_date", "")),
            "effective_timestamp": effective, "publication_timestamp": publication,
            "effective_timestamp_provenance": effective_provenance,
            "source_receipt_identifiers": {"file": row.get("source_file", ""), "byte_offset": row.get("source_byte_offset", 0), "source_row": row.get("source_row_number", 0)},
            "engine_hash": self.c.get("engine_hash", ""), "configuration_hash": self.c.get("configuration_hash", ""),
            "raw_run_id": self.c.get("raw_run_id", ""), "status": "REFUSED", "reason": reason, "detail": detail,
        }
        _validate_material_ledger_row("refusals_data_quality", value)
        content = _material_ledger_content("refusals_data_quality", value)
        prior_content = self._ledger_content["refusals_data_quality"].get(
            event_id
        )
        if prior_content is not None:
            if prior_content != content:
                raise ValueError(
                    "append-only refusals_data_quality identity reused with "
                    f"different immutable content: {event_id}"
                )
            return
        if (
            self._quality_identity_index is not None
            and event_id in self._quality_identity_index
        ):
            raise ValueError(
                "shared refusal identity exists without immutable content: "
                f"{event_id}"
            )
        ledger = self.ledgers["refusals_data_quality"]
        boundary = ledger.append_boundary()
        try:
            ledger.append(value)
        except Exception:
            committed = ledger.reconcile_appended_prefix(
                boundary, [value], identity_field="event_id"
            )
            if event_id in committed:
                self._ledger_content["refusals_data_quality"][event_id] = (
                    content
                )
                if self._quality_identity_index is not None:
                    self._quality_identity_index.add(event_id)
            raise
        self._ledger_content["refusals_data_quality"][event_id] = content
        if self._quality_identity_index is not None:
            self._quality_identity_index.add(event_id)

    def _existing_events(self, ledger_name: str) -> dict[str, str]:
        result: dict[str, str] = {}
        ledger = self.ledgers[ledger_name]
        rows = ledger.rows() if hasattr(ledger, "rows") else []
        for ordinal, row in enumerate(rows, start=1):
            _validate_material_ledger_row(
                ledger_name, row, ordinal=ordinal
            )
            identity = row.get("event_id") or row.get("transition_id") or row.get("record_id") or row.get("episode_id")
            if not identity:
                raise ValueError(
                    f"append-only {ledger_name} row is missing an event identity"
                )
            event_id = str(identity)
            if event_id in result:
                raise ValueError(
                    f"duplicate physical event identity in {ledger_name}: "
                    f"{event_id}"
                )
            result[event_id] = _material_ledger_content(ledger_name, row)
        return result

    def _existing_ids(self, ledger_name: str) -> set[str]:
        """Compatibility helper for callers that require only identities."""
        return set(self._existing_events(ledger_name))

    def _evict_sessions(self) -> None:
        # Dirty sessions cannot be discarded before an explicit analytical
        # seal.  Retain them in addition to the bounded newest live buckets.
        newest_live = set(sorted(self._sessions)[-self.max_sessions:])
        keep_live = newest_live | set(self._dirty_sessions)
        for session in sorted(set(self._sessions) - keep_live):
            self._sessions.pop(session, None)
            self._last_order_key.pop(session, None)
            self._stage_ledgers.pop(session, None)
        # Verified replay outputs are independently protected from rolling live
        # retention.  Other sealed outputs retain only the newest live window.
        self._outputs = self._retained_outputs(
            self._outputs, self._sessions, self._dirty_sessions
        )
        self._publish_operational_views()

    def _retained_outputs(
        self,
        outputs: Mapping[str, dict],
        sessions: Mapping[str, object],
        dirty_sessions: Iterable[str],
    ) -> dict[str, dict]:
        verified_replays = set(gui_adapter.SESSIONS)
        newest_outputs = set(sorted(outputs)[-self.max_sessions:])
        keep = (
            verified_replays
            | newest_outputs
            | set(sessions)
            | set(dirty_sessions)
        )
        return {
            session: value for session, value in outputs.items() if session in keep
        }

    def _persist(self) -> None:
        self._persist_values(
            sessions=self._sessions,
            outputs=self._outputs,
            contexts=self._cross_layer_contexts,
            dirty_sessions=self._dirty_sessions,
            finalized_sessions=self._finalized_sessions,
        )

    def _persist_values(
        self,
        *,
        sessions: Mapping[str, Mapping[str, Mapping[str, object]]],
        outputs: Mapping[str, dict],
        contexts: Mapping[str, Mapping[str, object]],
        dirty_sessions: Iterable[str],
        finalized_sessions: Iterable[str],
    ) -> None:
        atomic_json(self.state_path, {
            "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
            "sessions": {
                session: list(bucket.values()) for session, bucket in sessions.items()
            },
            "outputs": outputs,
            "cross_layer_contexts": contexts,
            "dirty_sessions": sorted(dirty_sessions),
            "finalized_sessions": sorted(finalized_sessions),
        })

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"analytical orchestrator state corrupt: {error}") from error
        if not isinstance(state, Mapping):
            raise ValueError("analytical orchestrator state must be an object")
        if state.get("version") != "R6E1R_LIVE_ANALYTICAL_STATE_V1":
            raise ValueError("analytical orchestrator state version mismatch")
        raw_sessions = state.get("sessions", {})
        if not isinstance(raw_sessions, Mapping):
            raise ValueError("analytical sessions must be a mapping")
        for session, rows in raw_sessions.items():
            if not isinstance(session, str) or not session:
                raise ValueError("analytical session key must be a string")
            try:
                canonical_session = date.fromisoformat(session).isoformat()
            except ValueError as error:
                raise ValueError(
                    f"persisted analytical session key is invalid: {session!r}"
                ) from error
            if canonical_session != session:
                raise ValueError(
                    f"persisted analytical session key is noncanonical: {session!r}"
                )
            if not isinstance(rows, list):
                raise ValueError(
                    f"analytical session rows must be a list for {session}"
                )
            bucket: dict[str, dict] = {}
            for ordinal, row in enumerate(rows, start=1):
                if not isinstance(row, Mapping):
                    raise ValueError(
                        "persisted analytical session row is not an object: "
                        f"{session}:{ordinal}"
                    )
                identity = row.get("observation_id")
                if not isinstance(identity, str) or not identity:
                    raise ValueError(
                        "persisted analytical session row is missing identity: "
                        f"{session}:{ordinal}"
                    )
                if row.get("session_date") != session:
                    raise ValueError(
                        "persisted analytical session row has mismatched "
                        f"session: {session}:{identity}"
                    )
                if identity in bucket:
                    raise ValueError(
                        "duplicate persisted analytical observation identity: "
                        f"{session}:{identity}"
                    )
                bucket[identity] = dict(row)
            self._sessions[session] = bucket
            if rows:
                self._last_order_key[session] = max(self._order_key(row) for row in rows)
        raw_outputs = state.get("outputs", {})
        if not isinstance(raw_outputs, Mapping):
            raise ValueError("analytical outputs must be a mapping")
        self._outputs = {}
        for raw_session, raw_output in raw_outputs.items():
            session = _canonical_state_session(
                raw_session, "analytical output key"
            )
            if not isinstance(raw_output, Mapping):
                raise ValueError(
                    f"analytical output is not an object for {session}"
                )
            output = dict(raw_output)
            if output.get("session_date") != session:
                raise ValueError(
                    "analytical output has mismatched session_date for "
                    f"{session}"
                )
            self._outputs[session] = output
            compacted_gui = _compact_gui_resolution_payload(output)
            if compacted_gui is not None:
                output["gui_payload"] = compacted_gui
            expected_audit = _sealed_snapshot_audit_counters(output)
            persisted_audit = output.get("public_audit_counters")
            if persisted_audit is not None and persisted_audit != expected_audit:
                raise ValueError(
                    f"sealed public audit counters mismatch for {session}"
                )
            output["public_audit_counters"] = expected_audit
            expected_causality = _sealed_causality_counters(
                output,
                tolerance_ms=int(
                    self.config.get("synchronization_tolerance_ms", 2000)
                ),
            )
            persisted_causality = output.get("public_causality_counters")
            if (
                persisted_causality is not None
                and persisted_causality != expected_causality
            ):
                raise ValueError(
                    f"sealed public causality counters mismatch for {session}"
                )
            output["public_causality_counters"] = expected_causality

        def state_session_set(field: str) -> set[str]:
            raw_values = state.get(field, [])
            if not isinstance(raw_values, list):
                raise ValueError(f"analytical {field} must be a list")
            values: set[str] = set()
            for ordinal, raw_value in enumerate(raw_values, start=1):
                value = _canonical_state_session(
                    raw_value, f"analytical {field} item {ordinal}"
                )
                if value in values:
                    raise ValueError(
                        f"analytical {field} contains duplicate {value}"
                    )
                values.add(value)
            return values

        self._dirty_sessions = state_session_set("dirty_sessions")
        self._finalized_sessions = state_session_set("finalized_sessions")
        if not self._dirty_sessions.issubset(self._sessions):
            raise ValueError(
                "analytical dirty_sessions are missing mutable session rows"
            )
        if self._dirty_sessions & self._finalized_sessions:
            raise ValueError(
                "analytical dirty_sessions overlap finalized_sessions"
            )
        if self._finalized_sessions & set(self._sessions):
            raise ValueError(
                "analytical finalized_sessions retain mutable session rows"
            )
        output_authority = set(self._sessions) | self._finalized_sessions
        if not set(self._outputs).issubset(output_authority):
            raise ValueError(
                "analytical outputs lack mutable or finalized session authority"
            )
        raw_contexts = state.get("cross_layer_contexts", {})
        if not isinstance(raw_contexts, Mapping):
            raise ValueError("analytical cross-layer contexts must be a mapping")
        self._cross_layer_contexts = {}
        for raw_session, value in raw_contexts.items():
            session = _canonical_state_session(
                raw_session, "analytical cross-layer context key"
            )
            if not isinstance(value, Mapping):
                raise ValueError(
                    "analytical cross-layer context is not an object for "
                    f"{session}"
                )
            self._cross_layer_contexts[session] = (
                cross_layer_state.normalize_material_context(value)
            )
        if self._outputs and not self._cross_layer_contexts:
            missing_prefix = self._finalized_sessions - set(self._outputs)
            if missing_prefix:
                raise ValueError(
                    "legacy analytical state lacks cross-layer context and "
                    "has evicted finalized prefix output; clean rebuild required: "
                    f"{sorted(missing_prefix)!r}"
                )
            self._cross_layer_contexts = self._rebuild_cross_layer_contexts()
        expected_context_sessions = (
            set(self._outputs) | self._finalized_sessions
        )
        if set(self._cross_layer_contexts) != expected_context_sessions:
            missing = sorted(
                expected_context_sessions - set(self._cross_layer_contexts)
            )
            orphaned = sorted(
                set(self._cross_layer_contexts) - expected_context_sessions
            )
            raise ValueError(
                "analytical cross-layer context authority mismatch: "
                f"missing={missing!r} orphaned={orphaned!r}"
            )

    def _rebuild_cross_layer_contexts(self) -> dict[str, dict[str, object]]:
        """Migrate an older state once without reopening raw source history."""
        context = cross_layer_state.empty_material_context()
        rebuilt: dict[str, dict[str, object]] = {}
        for session in sorted(self._outputs):
            output = self._outputs[session]
            context["episode_source_count"] = int(
                context["episode_source_count"]
            ) + len(output.get("episodes", []))
            resolution = list(output.get("resolution", []))
            context["resolution_source_count"] = int(
                context["resolution_source_count"]
            ) + len(resolution)
            resolution_previous = dict(context["resolution_previous"])
            for row in resolution:
                resolution_previous[str(row["episode_id"])] = str(
                    row["resolution_mechanism_native"]
                )
            context["resolution_previous"] = resolution_previous
            inventory = list(output.get("inventory", []))
            if self._uses_canonical_inventory_context(session, inventory):
                context["inventory_source_count"] = int(
                    context["inventory_source_count"]
                ) + len(inventory)
                inventory_previous = dict(context["inventory_previous"])
                for row in sorted(
                    inventory,
                    key=lambda item: (
                        parse_timestamp(item["control_effective_timestamp"]).value,
                        str(item["horizon"]),
                        str(item["family"]),
                    ),
                ):
                    key = f'{row["horizon"]}:{row["family"]}'
                    inventory_previous[key] = f'AVAILABLE:{row["control_value"]}'
                context["inventory_previous"] = inventory_previous
            context = cross_layer_state.normalize_material_context(context)
            rebuilt[session] = context
        return rebuilt

    def _load_staged_observations(self) -> None:
        """Recover callback rows durably appended after the last state seal."""
        intent_sessions = {
            path.name.removesuffix(".append_intent.json")
            for path in self.stage_root.glob(
                "????-??-??.append_intent.json"
            )
        }
        # An unresolved intent is an integrity boundary, not rolling live
        # history. Inspect every one even when its session predates retention.
        for session in sorted(intent_sessions):
            self._assert_stage_not_quarantined(session)
            self._recover_stage_append_intent(session)
            self._assert_stage_not_quarantined(session)
        stage_sessions = sorted(
            path.stem
            for path in self.stage_root.glob("????-??-??.jsonl")
        )
        # Every mutable row copied into the replaceable JSON state must remain
        # authenticated by its append-only callback stage.  Persisted sessions
        # may legitimately extend beyond the rolling stage window while dirty,
        # so inspect all of them in addition to the newest retained stages.
        load_sessions = set(stage_sessions[-self.max_sessions:]) | set(
            self._sessions
        )
        for session in sorted(load_sessions):
            # A finalized output plus the durable finalized marker is enough
            # to refuse any later replay without rehydrating every normalized
            # observation or identity from its append-only stage.
            if session in self._finalized_sessions and session not in self._sessions:
                continue
            rows, receipt = self._read_unique_staged_rows(session)
            self._authenticate_persisted_session_rows(session, rows)
            self._accept_durable_stage_rows(session, rows)
            if receipt is not None:
                self._raw_stage_ledger(
                    session
                ).acknowledge_retained_append(
                    receipt,
                    accepted_identities=receipt.committed_identities,
                )
        self._evict_sessions()

    def _authenticate_persisted_session_rows(
        self, session: str, staged_rows: Iterable[Mapping[str, object]],
    ) -> None:
        """Require replaceable live state to match its durable stage exactly.

        A stage may contain additional rows when a crash occurred after its
        fsync but before the next state replacement.  Those rows are recovered
        normally.  The inverse is never valid: every identity already present
        in mutable state must exist in the stage with byte-canonical content.
        """
        persisted = self._sessions.get(session)
        if persisted is None:
            return
        durable: dict[str, str] = {}
        for row in staged_rows:
            identity = str(row.get("observation_id", ""))
            if row.get("session_date") != session:
                raise ValueError(
                    "durable analytical stage row has mismatched session: "
                    f"{session}:{identity or '<missing>'}"
                )
            # _read_unique_staged_rows rejects duplicates before this helper;
            # retain the guard so direct internal use cannot weaken the check.
            if identity in durable:
                raise ValueError(
                    "duplicate analytical observation stage identity for "
                    f"{session}: {identity}"
                )
            durable[identity] = _staged_observation_content(row)
        for identity, row in persisted.items():
            durable_content = durable.get(identity)
            if durable_content is None:
                raise ValueError(
                    "persisted analytical observation is missing from durable "
                    f"stage: {session}:{identity}"
                )
            if durable_content != _staged_observation_content(row):
                raise ValueError(
                    "persisted analytical observation content mismatch with "
                    f"durable stage: {session}:{identity}"
                )

    @staticmethod
    def _empty_snapshot(session: str) -> dict:
        empty = {name: [] for name in ("basis", "inventory", "episodes", "dependencies", "lifecycle", "resolution", "responses", "participation_dense", "participation_transitions", "participation_summaries", "compatibility_snapshots", "cross_layer_transitions")}
        return {"session_date": session, **empty, "availability": {"overall_state": "NO_VALID_MARKET_DATA"}, "gui_payload": {}, "callback_invocations": {}, "counts": {"observations": 0, **{key: 0 for key in empty}}, "public_audit_counters": {"timestamp_backdating": 0, "duplicate_analytical_ids": 0, "measured_snapshot_rows": 0}, "public_causality_counters": {"valid_basis_pairs": 0, "future_joins": 0, "synchronization_tolerance_violations": 0}}


__all__ = ["LiveAnalyticalOrchestrator"]
