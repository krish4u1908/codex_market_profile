#!/usr/bin/env python3
"""R6E1R raw-input incremental/batch and scheduling equivalence harness.

The harness deliberately owns no analytical formula.  Every source byte is
presented to :class:`IncrementalJSONLIngestor` and every committed typed
observation is routed to :class:`LiveAnalyticalOrchestrator`.  Comparisons are
made only after independent run snapshots have been sealed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.runtime.configuration import canonical_configuration_sha256
from banknifty_profiler.runtime.timestamps import parse_timestamp
from banknifty_profiler.divergence.detector import causal_basis
from banknifty_profiler.gui.adapter import build_payload as build_gui_payload
from banknifty_profiler.raw_io.reader import load_market


SESSIONS = (
    "2026-08-11",
    "2026-08-12",
    "2026-08-13",
    "2026-08-18",
    "2026-08-19",
    "2026-08-20",
)

EXPECTED_COUNTS = {
    "inventory": 255,
    "divergence_episodes": 65,
    "green": 41,
    "red": 24,
    "retriggers": 14,
    "lifecycle_transitions": 14_201,
    "dense_resolution_observations": 164_668,
    "participation_dense": 69_225,
    "participation_transitions": 32_068,
    "participation_summaries": 65,
    "compatibility_snapshots": 65,
}

# These values describe execution, rather than analytical evidence.  They are
# retained in each sealed snapshot but excluded from semantic A/B comparison.
RUN_VOLATILE_FIELDS = frozenset(
    {
        "calculation_timestamp",
        "publication_timestamp",
        "published_at",
        "updated_at",
        "raw_run_id",
        "run_id",
        "source_root",
        "state_root",
    }
)

COMPONENT_KEYS = {
    "synchronized_basis": "basis",
    "inventory": "inventory",
    "divergence_episodes": "episodes",
    "dependency_groups": "dependencies",
    "lifecycle_transitions": "lifecycle",
    "dense_resolution_observations": "resolution",
    "response_observations": "responses",
    "participation_dense": "participation_dense",
    "participation_transitions": "participation_transitions",
    "participation_summaries": "participation_summaries",
    "compatibility_snapshots": "compatibility_snapshots",
    "cross_layer_transitions": "cross_layer_transitions",
    "availability_states": "availability",
}

IDENTITY_FIELDS = (
    "event_id",
    "transition_id",
    "observation_id",
    "episode_id",
    "dependency_group_id",
    "evaluation_date",
    "session_date",
    "effective_timestamp",
    "receipt_timestamp",
    "timestamp",
    "component",
    "family",
    "horizon",
    "symbol",
    "strike",
)

_NUMERIC_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True)
class SourceFile:
    source: Path
    relative: Path
    size: int
    complete_rows: int
    ends_with_newline: bool


@dataclass(frozen=True)
class Schedule:
    name: str
    line_groups: tuple[int, ...]
    split_inside_lines: bool = False
    empty_polls: int = 0
    restart_every: int = 0
    restart_on_analytical_transition: bool = False


SCHEDULES = {
    "original_source_chunks": Schedule("original_source_chunks", (512,)),
    "one_record_per_increment": Schedule("one_record_per_increment", (1,)),
    "deterministic_variable_chunks": Schedule(
        "deterministic_variable_chunks", (1, 7, 3, 11, 2, 17, 5, 13)
    ),
    "boundaries_inside_jsonl_lines": Schedule(
        "boundaries_inside_jsonl_lines", (1, 5, 2, 9), split_inside_lines=True
    ),
    "empty_repeated_polls": Schedule(
        "empty_repeated_polls", (7, 3, 11), empty_polls=2
    ),
    "multiple_checkpoint_restarts": Schedule(
        "multiple_checkpoint_restarts", (5, 13, 2), restart_every=29
    ),
    "analytical_boundary_restarts": Schedule(
        "analytical_boundary_restarts", (512,), restart_on_analytical_transition=True
    ),
    "hourly_file_rotation": Schedule("hourly_file_rotation", (257,)),
    "large_chronological_chunks": Schedule("large_chronological_chunks", (8192,)),
}

REQUIRED_SCHEDULES = (
    "original_source_chunks",
    "one_record_per_increment",
    "deterministic_variable_chunks",
    "boundaries_inside_jsonl_lines",
    "empty_repeated_polls",
    "multiple_checkpoint_restarts",
    "analytical_boundary_restarts",
    "hourly_file_rotation",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _jsonable(value: Any) -> Any:
    """Convert canonical processor output without changing its values."""
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "to_dict") and value.__class__.__module__.startswith("pandas"):
        try:
            return _jsonable(value.to_dict(orient="records"))
        except TypeError:
            return _jsonable(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime) or hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        if value != value:
            return None
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
    return value


def canonicalize(value: Any, *, volatile_fields: frozenset[str] = RUN_VOLATILE_FIELDS) -> Any:
    """Remove only run-volatile metadata and give row collections stable order."""
    value = _jsonable(value)
    if isinstance(value, dict):
        return {
            key: canonicalize(
                _portable_source_identity(item)
                if key in {"source_file", "raw_source_references"}
                else item,
                volatile_fields=volatile_fields,
            )
            for key, item in sorted(value.items())
            if key not in volatile_fields
        }
    if isinstance(value, list):
        rows = [canonicalize(item, volatile_fields=volatile_fields) for item in value]
        if all(isinstance(item, dict) for item in rows):
            return sorted(rows, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return rows
    if value == "":
        return None
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    numeric = None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = str(value)
    elif isinstance(value, str) and _NUMERIC_TEXT.fullmatch(value.strip()):
        numeric = value.strip()
    if numeric is not None:
        try:
            decimal = Decimal(numeric)
            if decimal.is_finite():
                normalized = format(decimal.normalize(), "f")
                return "__NUMBER__:0" if Decimal(normalized) == 0 else "__NUMBER__:" + normalized
        except (InvalidOperation, ValueError):
            pass
    return value


def _portable_source_identity(value: Any) -> Any:
    """Remove only run-local root prefixes from physical raw provenance."""
    if not isinstance(value, str):
        return value
    normalized = value.replace("\\", "/")
    positions = [
        position
        for marker in ("/raw/", "/oi/")
        if (position := normalized.find(marker)) >= 0
    ]
    return normalized[min(positions) + 1:] if positions else normalized


def semantic_hash(value: Any) -> str:
    return _sha256_bytes(_json_bytes(canonicalize(value)))


def _as_rows(value: Any) -> list[dict[str, Any]]:
    value = _jsonable(value)
    if value is None:
        return []
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if isinstance(value, Mapping):
        fields = value.get("fields")
        packed = value.get("rows")
        if isinstance(fields, list) and isinstance(packed, list):
            return [dict(zip(fields, row, strict=False)) for row in packed]
        if all(isinstance(item, Mapping) for item in value.values()):
            return [dict(item) for item in value.values()]
        return [dict(value)]
    raise TypeError(f"analytical component is not row-like: {type(value)!r}")


def _gui_projection(payload: Any) -> dict[str, Any]:
    """Project only GUI-visible analytical rows, excluding packaging metadata."""
    if not isinstance(payload, Mapping):
        return {}
    row_keys = (
        "price",
        "inventory",
        "episodes",
        "dependencies",
        "lifecycle",
        "resolution_mechanisms",
        "participation_dense",
        "participation_transitions",
        "participation_summaries",
        "compatibility_snapshots",
        "cross_layer_transitions",
    )
    return {key: _as_rows(payload.get(key, [])) for key in row_keys}


def _availability_projection(value: Any) -> list[dict[str, Any]]:
    output = []
    for row in _as_rows(value):
        common = {
            "evaluation_date": row.get("evaluation_date") or row.get("session_date"),
            "overall_state": row.get("overall_state"),
            "market_display_enabled": row.get("market_display_enabled"),
            "divergence_state": row.get("divergence_state"),
            "participation_state": row.get("participation_state"),
            "available_horizons": row.get("available_horizons"),
            "unavailable_horizons": row.get("unavailable_horizons"),
        }
        layers = row.get("layers")
        if isinstance(layers, Mapping):
            for horizon, state in layers.items():
                detail = state if isinstance(state, Mapping) else {"state": state}
                output.append(
                    {
                        **common,
                        "horizon": horizon,
                        "availability_state": detail.get("state"),
                        "availability_reason": detail.get("reason"),
                    }
                )
        elif row.get("horizon"):
            output.append(
                {
                    **common,
                    "horizon": row.get("horizon"),
                    "availability_state": row.get("availability_state") or row.get("state"),
                    "availability_reason": row.get("availability_reason") or row.get("reason"),
                }
            )
    return output


def component_rows(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Project the public orchestrator snapshot into the frozen count contract."""
    result = {}
    for component, key in COMPONENT_KEYS.items():
        value = snapshot.get(key, [])
        if component == "compatibility_snapshots" and not value:
            value = snapshot.get("compatibility", [])
        result[component] = (
            _availability_projection(value)
            if component == "availability_states"
            else _as_rows(value)
        )
    episodes = result["divergence_episodes"]
    dependencies = _as_rows(snapshot.get("dependencies", []))
    result["green"] = [
        row for row in episodes if str(row.get("colour", row.get("episode_type", ""))).upper().startswith("GREEN")
    ]
    result["red"] = [
        row for row in episodes if str(row.get("colour", row.get("episode_type", ""))).upper().startswith("RED")
    ]
    result["retriggers"] = [
        row
        for row in dependencies
        if row.get("retrigger_flag") is True
        or str(row.get("retrigger_flag", "")).lower() == "true"
        or row.get("classification") == "DEPENDENT_RETRIGGER"
    ]
    gui = snapshot.get("gui_payload", {})
    result["gui_visible_state"] = (
        [
            {"session_date": str(session), "payload": _gui_projection(payload)}
            for session, payload in gui.items()
        ]
        if isinstance(gui, Mapping)
        else []
    )
    return result


def analytical_ledger_rows(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ledgers = snapshot.get("analytical_ledgers", {})
    if not isinstance(ledgers, Mapping):
        return {}
    return {str(name): _as_rows(rows) for name, rows in ledgers.items()}


def _row_counter(rows: Iterable[Mapping[str, Any]]) -> Counter[str]:
    return Counter(
        json.dumps(canonicalize(dict(row)), sort_keys=True, separators=(",", ":"))
        for row in rows
    )


def _identity(row: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    selected = tuple(
        (field, json.dumps(canonicalize(row[field]), sort_keys=True, separators=(",", ":")))
        for field in IDENTITY_FIELDS
        if field in row and row[field] not in (None, "")
    )
    return selected or (("__row__", json.dumps(canonicalize(dict(row)), sort_keys=True)),)


def _field_mismatches(a_rows: list[dict[str, Any]], b_rows: list[dict[str, Any]]) -> int:
    a_by_id: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    b_by_id: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    for row in a_rows:
        a_by_id.setdefault(_identity(row), []).append(canonicalize(row))
    for row in b_rows:
        b_by_id.setdefault(_identity(row), []).append(canonicalize(row))
    differences = 0
    for identity in a_by_id.keys() & b_by_id.keys():
        left = sorted(a_by_id[identity], key=lambda row: json.dumps(row, sort_keys=True))
        right = sorted(b_by_id[identity], key=lambda row: json.dumps(row, sort_keys=True))
        for a_row, b_row in zip(left, right, strict=False):
            differences += sum(
                canonicalize(a_row.get(field)) != canonicalize(b_row.get(field))
                for field in a_row.keys() | b_row.keys()
            )
    return differences


def compare_snapshots(
    a_snapshot: Mapping[str, Any],
    b_snapshot: Mapping[str, Any],
    expected: Mapping[str, int] | None = EXPECTED_COUNTS,
) -> list[dict[str, Any]]:
    """Return auditable multiset equivalence, never a float-tolerant comparison."""
    a_components = component_rows(a_snapshot)
    b_components = component_rows(b_snapshot)
    names = list(expected or ())
    names.extend(sorted((a_components.keys() | b_components.keys()) - set(names)))
    rows = []
    for name in names:
        a_rows = a_components.get(name, [])
        b_rows = b_components.get(name, [])
        left = _row_counter(a_rows)
        right = _row_counter(b_rows)
        a_only = sum((left - right).values())
        b_only = sum((right - left).values())
        matched = sum((left & right).values())
        fields = _field_mismatches(a_rows, b_rows)
        expected_count = "" if expected is None or name not in expected else expected[name]
        count_gate = expected_count == "" or (
            len(a_rows) == expected_count and len(b_rows) == expected_count
        )
        remainder = a_only + b_only + fields
        rows.append(
            {
                "component": name,
                "expected_count": expected_count,
                "incremental_a_count": len(a_rows),
                "batch_b_count": len(b_rows),
                "matched_rows": matched,
                "a_only": a_only,
                "b_only": b_only,
                "field_mismatches": fields,
                "unexplained_remainder": remainder,
                "status": "PASS" if remainder == 0 and count_gate else "FAIL",
            }
        )
    return rows


def _walk_mappings(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from _walk_mappings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_mappings(item)


def _timestamp_value(value: Any) -> int | None:
    if value in (None, "", "NaT"):
        return None
    try:
        return int(parse_timestamp(value, field_name="R6E1R invariant timestamp").value)
    except (TypeError, ValueError):
        return None


def audit_invariants(snapshot: Mapping[str, Any]) -> dict[str, int]:
    """Count causal/identity violations without deriving analytical values."""
    components = component_rows(snapshot)
    core = {key: value for key, value in components.items() if key != "gui_visible_state"}
    core.update({f"ledger_{name}": rows for name, rows in analytical_ledger_rows(snapshot).items()})
    future_joins = 0
    backdating = 0
    nat_timestamps = 0
    for row in _walk_mappings(core):
        if row.get("future_join") is True or str(row.get("future_join", "")).lower() == "true":
            future_joins += 1
        for key, value in row.items():
            if "join_age" in key:
                try:
                    future_joins += float(value) < 0
                except (TypeError, ValueError):
                    pass
            if "timestamp" in key.lower() and str(value) == "NaT":
                nat_timestamps += 1
        publication = _timestamp_value(
            row.get("publication_timestamp") or row.get("calculation_timestamp")
        )
        effective_values = [
            _timestamp_value(row.get(key))
            for key in (
                "effective_timestamp",
                "evidence_receipt_timestamp",
                "availability_timestamp",
                "receipt_timestamp",
            )
            if row.get(key) not in (None, "")
        ]
        effective_values = [value for value in effective_values if value is not None]
        if publication is not None and effective_values and publication < max(effective_values):
            backdating += 1

    duplicate_ids = 0
    identity_specs = {
        "divergence_episodes": "episode_id",
        "dependency_groups": "episode_id",
        "lifecycle_transitions": "record_id",
        "participation_transitions": "transition_id",
        "cross_layer_transitions": "transition_id",
    }
    for component, field in identity_specs.items():
        values = [str(row[field]) for row in components.get(component, []) if row.get(field)]
        duplicate_ids += len(values) - len(set(values))
    for rows in analytical_ledger_rows(snapshot).values():
        values = [str(row["event_id"]) for row in rows if row.get("event_id")]
        duplicate_ids += len(values) - len(set(values))
    return {
        "future_joins": int(future_joins),
        "timestamp_backdating": backdating,
        "duplicate_analytical_ids": duplicate_ids,
        "valid_timestamps_becoming_nat": nat_timestamps,
    }


def compare_invariants(
    a_snapshot: Mapping[str, Any], b_snapshot: Mapping[str, Any]
) -> list[dict[str, Any]]:
    a_values = audit_invariants(a_snapshot)
    b_values = audit_invariants(b_snapshot)
    return [
        {
            "invariant": name,
            "expected": 0,
            "incremental_a": a_values[name],
            "batch_b": b_values[name],
            "status": "PASS" if a_values[name] == b_values[name] == 0 else "FAIL",
        }
        for name in a_values
    ]


def _count_lines(path: Path) -> tuple[int, bool]:
    count = 0
    last = b""
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            count += block.count(b"\n")
            last = block[-1:]
    return count, last == b"\n"


def discover_sources(data_root: Path, sessions: Iterable[str]) -> list[SourceFile]:
    """Discover physical JSONL only; derived/reference input roots are refused."""
    root = data_root.resolve()
    if not root.is_dir():
        raise ValueError(f"physical data root missing: {root}")
    if "research" in root.parts:
        raise ValueError("research-derived analytical input root is prohibited")
    missing_streams = [stream for stream in ("raw", "oi") if not (root / stream).is_dir()]
    if missing_streams:
        raise ValueError(f"physical stream roots missing: {missing_streams}")
    requested = tuple(sorted(set(sessions)))
    if not requested:
        raise ValueError("at least one evaluation session is required")
    available = sorted(
        {
            path.name
            for stream in ("raw", "oi")
            for path in (root / stream).iterdir()
            if path.is_dir() and path.name <= requested[-1]
        }
    )
    missing = [
        session
        for session in requested
        if not all((root / stream / session).is_dir() for stream in ("raw", "oi"))
    ]
    if missing:
        raise ValueError(f"required physical sessions missing: {missing}")
    # Eligible predecessors are deliberately included.  The canonical inventory
    # adapter decides eligibility and keeps the current evaluation date out.
    # R6E1R inherits the frozen R6C0I discovery window.  This includes every
    # eligible predecessor used by the 1D/2D/3D inventory context while keeping
    # unrelated older collector history out of the equivalence run.
    discovery_start = "2026-08-10" if set(requested).issubset(set(SESSIONS)) else requested[0]
    dates = [date for date in available if discovery_start <= date <= requested[-1]]
    found: list[SourceFile] = []
    for stream, prefix in (("raw", "events_*.jsonl"), ("oi", "oi_*.jsonl")):
        for date in dates:
            for path in sorted((root / stream / date).glob(prefix)):
                rows, newline = _count_lines(path)
                found.append(
                    SourceFile(path.resolve(), path.relative_to(root), path.stat().st_size, rows, newline)
                )
    if not found:
        raise ValueError("no physical JSONL inputs discovered")
    return sorted(found, key=lambda item: str(item.relative))


def _receipt_key(line: bytes, source: SourceFile, row: int) -> tuple[int, str, int]:
    try:
        record = json.loads(line)
        receipt = record.get("received_at") or record.get("receipt_timestamp")
        parsed = parse_timestamp(receipt, field_name="R6E1R schedule receipt timestamp")
        timestamp = int(parsed.value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        # Malformed rows sort first by their frozen physical keys and remain the
        # production ingestor's responsibility to refuse and checkpoint.
        timestamp = -(1 << 63)
    return timestamp, str(source.relative), row


def merged_source_lines(sources: list[SourceFile]) -> Iterator[tuple[SourceFile, bytes]]:
    """Bounded-memory chronological merge retaining exact source bytes."""
    handles: list[BinaryIO] = []
    heap: list[tuple[tuple[str, str, int], int, int, bytes]] = []
    try:
        for index, source in enumerate(sources):
            handle = source.source.open("rb")
            handles.append(handle)
            line = handle.readline()
            if line:
                heapq.heappush(heap, (_receipt_key(line, source, 1), index, 1, line))
        while heap:
            _, index, row, line = heapq.heappop(heap)
            source = sources[index]
            yield source, line
            next_line = handles[index].readline()
            if next_line:
                next_row = row + 1
                heapq.heappush(
                    heap,
                    (_receipt_key(next_line, source, next_row), index, next_row, next_line),
                )
    finally:
        for handle in handles:
            handle.close()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    fields = list(dict.fromkeys(key for row in materialized for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)


def checkpoint_accounting(
    sources: list[SourceFile], staging_root: Path, checkpoints: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = []
    for source in sources:
        relative = str(source.relative)
        destination = staging_root / source.relative
        exposed = destination.stat().st_size if destination.exists() else 0
        source_sha256 = _sha256_file(source.source)
        staged_sha256 = _sha256_file(destination) if destination.exists() else ""
        byte_identical = exposed == source.size and staged_sha256 == source_sha256
        checkpoint = checkpoints.get(relative, {})
        committed = int(checkpoint.get("offset", 0))
        complete_rows = int(checkpoint.get("row", 0))
        rows.append(
            {
                "scope": "R6E1R",
                "source_file": relative,
                "source_bytes": source.size,
                "source_sha256": source_sha256,
                "staged_sha256": staged_sha256,
                "source_byte_identical": byte_identical,
                "bytes_seen": exposed,
                "bytes_committed": committed,
                "deferred_tail_bytes": max(0, exposed - committed),
                "source_complete_rows": source.complete_rows,
                "complete_rows": complete_rows,
                "processed_once": committed == source.size and complete_rows == source.complete_rows,
                "status": "PASS"
                if byte_identical
                and committed == source.size
                and complete_rows == source.complete_rows
                else "FAIL",
                "reason": "EXACT_COMPLETE_LINE_COMMIT"
                if byte_identical
                and committed == source.size
                and complete_rows == source.complete_rows
                else "STAGED_SOURCE_BYTES_DIFFER"
                if not byte_identical
                else "SOURCE_CHECKPOINT_REMAINDER",
            }
        )
    return rows


class _RunContext:
    """Own one independent ingestor/orchestrator state pair."""

    def __init__(self, contract: dict[str, Any]):
        self.contract = contract
        self.ingestor: IncrementalJSONLIngestor | None = None
        self.orchestrator: LiveAnalyticalOrchestrator | None = None
        self.open()

    def open(self) -> None:
        self.ingestor = IncrementalJSONLIngestor(self.contract)
        self.orchestrator = LiveAnalyticalOrchestrator(
            self.contract, ledgers=getattr(self.ingestor, "ledgers", None)
        )

    def poll(self) -> int:
        assert self.ingestor is not None and self.orchestrator is not None
        observations = self.ingestor.poll()
        self.orchestrator.process(observations)
        return len(observations)

    def restart(self) -> None:
        self.close()
        self.open()

    def snapshot(self, sessions: Iterable[str]) -> dict[str, Any]:
        assert self.orchestrator is not None
        by_session = {}
        finalizer = getattr(self.orchestrator, "finalize_session", None)
        for session in sessions:
            value = finalizer(session) if callable(finalizer) else self.orchestrator.snapshot(session)
            by_session[session] = _jsonable(value)
        row_keys = (
            "basis", "inventory", "episodes", "dependencies", "lifecycle", "resolution",
            "responses", "participation_dense", "participation_transitions",
            "participation_summaries", "compatibility_snapshots", "cross_layer_transitions",
            "availability",
        )
        combined: dict[str, Any] = {
            key: [
                {"session_date": session, **row}
                if key == "availability" and "session_date" not in row
                else row
                for session, snapshot in by_session.items()
                for row in _as_rows(snapshot.get(key, []))
            ]
            for key in row_keys
        }
        combined["gui_payload"] = {
            session: snapshot.get("gui_payload", {}) for session, snapshot in by_session.items()
        }
        combined["session_snapshots"] = by_session
        requested = set(by_session)
        assert self.ingestor is not None
        combined["analytical_ledgers"] = {
            name: [
                row
                for row in ledger.rows()
                if not row.get("session_date") or str(row.get("session_date")) in requested
            ]
            for name, ledger in self.ingestor.ledgers.items()
            if name not in {"raw_file_checkpoints", "normalized_raw_events"}
        }
        combined["counts"] = {
            key: len(combined[key]) for key in row_keys if isinstance(combined[key], list)
        }
        return combined

    @property
    def checkpoints(self) -> Mapping[str, Any]:
        assert self.ingestor is not None
        return self.ingestor.checkpoints

    def analytical_ledger_signature(self) -> tuple[tuple[str, int], ...]:
        assert self.ingestor is not None
        excluded = {
            "raw_file_checkpoints",
            "normalized_raw_events",
            "refusals_data_quality",
        }
        return tuple(
            sorted(
                (
                    name,
                    ledger.path.stat().st_size if ledger.path.exists() else 0,
                )
                for name, ledger in self.ingestor.ledgers.items()
                if name not in excluded and hasattr(ledger, "path")
            )
        )

    def close(self) -> None:
        if self.ingestor is not None:
            self.ingestor.close()
        self.ingestor = None
        self.orchestrator = None


def _append(destination: Path, value: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("ab") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _drain(context: _RunContext, sources: list[SourceFile], staging_root: Path) -> None:
    """Poll until checkpoints catch all currently complete staged bytes."""
    previous: tuple[tuple[str, int], ...] | None = None
    for _ in range(100_000):
        context.poll()
        current = tuple(
            sorted((key, int(value.get("offset", 0))) for key, value in context.checkpoints.items())
        )
        pending = False
        for source in sources:
            destination = staging_root / source.relative
            if not destination.exists():
                continue
            exposed = destination.stat().st_size
            committed = int(context.checkpoints.get(str(source.relative), {}).get("offset", 0))
            if exposed > committed:
                with destination.open("rb") as handle:
                    handle.seek(-1, os.SEEK_END)
                    complete_tail = handle.read(1) == b"\n"
                if complete_tail:
                    pending = True
                    break
        if not pending:
            return
        if current == previous:
            raise RuntimeError("checkpoint made no progress over complete staged input")
        previous = current
    raise RuntimeError("checkpoint drain iteration limit exceeded")


def _line_parts(line: bytes) -> tuple[bytes, ...]:
    if len(line) < 3:
        return (line,)
    first = max(1, len(line) // 3)
    second = max(first + 1, (2 * len(line)) // 3)
    return line[:first], line[first:second], line[second:]


def run_schedule(
    *,
    schedule: Schedule,
    sources: list[SourceFile],
    staging_root: Path,
    state_root: Path,
    config_path: Path,
    sessions: tuple[str, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Execute one schedule exclusively through the production live path."""
    (staging_root / "raw").mkdir(parents=True, exist_ok=True)
    (staging_root / "oi").mkdir(parents=True, exist_ok=True)
    contract = validate_shadow_contract(
        staging_root.resolve(), state_root.resolve(), config_path.resolve(), "127.0.0.1", "shadow"
    )
    contract["raw_run_id"] = "R6E1R-" + uuid.uuid4().hex.upper()
    contract["minimum_session_date"] = min(path.relative.parts[1] for path in sources)
    # Historical acceleration remains bounded to the explicitly discovered
    # sessions, rather than the smaller live default.  The effective config
    # hash is updated so audit rows never claim the pre-override identity.
    session_count = len({path.relative.parts[1] for path in sources})
    contract["config"]["max_live_sessions"] = max(
        session_count, int(contract["config"].get("max_live_sessions", 8))
    )
    contract["configuration_hash"] = canonical_configuration_sha256(contract["config"])
    context = _RunContext(contract)
    exposed_records = 0
    restart_count = 0
    poll_count = 0

    def poll_for_schedule() -> int:
        nonlocal poll_count, restart_count
        before = context.analytical_ledger_signature()
        count = context.poll()
        poll_count += 1
        after = context.analytical_ledger_signature()
        if schedule.restart_on_analytical_transition and after != before:
            context.restart()
            restart_count += 1
        return count

    try:
        groups = schedule.line_groups
        group_index = 0
        pending: list[tuple[SourceFile, bytes]] = []
        pending_bytes = 0
        assert context.ingestor is not None
        maximum_exposure_bytes = context.ingestor.read_limit

        def flush_pending() -> None:
            nonlocal exposed_records, restart_count, group_index, pending_bytes
            if not pending:
                return
            for pending_source, pending_line in pending:
                if schedule.split_inside_lines:
                    for part in _line_parts(pending_line):
                        _append(staging_root / pending_source.relative, part)
                        poll_for_schedule()
                else:
                    _append(staging_root / pending_source.relative, pending_line)
                exposed_records += 1
            if not schedule.split_inside_lines:
                poll_for_schedule()
            if schedule.restart_every and exposed_records // schedule.restart_every > restart_count:
                context.restart()
                restart_count += 1
            pending.clear()
            for _ in range(schedule.empty_polls):
                poll_for_schedule()
            group_index += 1
            pending_bytes = 0

        for source, line in merged_source_lines(sources):
            target = groups[group_index % len(groups)]
            if pending and (len(pending) >= target or pending_bytes + len(line) > maximum_exposure_bytes):
                flush_pending()
            pending.append((source, line))
            pending_bytes += len(line)
            if len(pending) >= groups[group_index % len(groups)]:
                flush_pending()
        flush_pending()
        _drain(context, sources, staging_root)
        snapshot = context.snapshot(sessions)
        accounting = checkpoint_accounting(sources, staging_root, context.checkpoints)
        metrics = {
            "schedule": schedule.name,
            "source_files": len(sources),
            "source_bytes": sum(source.size for source in sources),
            "source_complete_rows": sum(source.complete_rows for source in sources),
            "exposed_records": exposed_records,
            "poll_calls_by_harness": poll_count,
            "restart_count": restart_count,
            "checkpoint_failures": sum(row["status"] != "PASS" for row in accounting),
            "semantic_hash": semantic_hash(component_rows(snapshot)),
        }
        return snapshot, accounting, metrics
    finally:
        context.close()


def checkpoint_recovery_probes(
    *,
    sources: list[SourceFile],
    work_root: Path,
    state_root: Path,
    config_path: Path,
) -> list[dict[str, Any]]:
    """Exercise truncation and inode replacement without touching source data."""
    selected = None
    first_line = b""
    for source in sources:
        with source.source.open("rb") as handle:
            candidate = handle.readline()
        if candidate.endswith(b"\n"):
            selected = source
            first_line = candidate
            break
    if selected is None:
        raise ValueError("checkpoint recovery fixture requires one complete physical line")

    rows = []
    for probe, expected in (("truncation", "FILE_TRUNCATED"), ("replacement", "FILE_REPLACED")):
        staging = work_root / probe / "collector"
        (staging / "raw").mkdir(parents=True, exist_ok=True)
        (staging / "oi").mkdir(parents=True, exist_ok=True)
        destination = staging / selected.relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(first_line)
        contract = validate_shadow_contract(
            staging.resolve(), (state_root / probe).resolve(), config_path.resolve(),
            "127.0.0.1", "shadow",
        )
        contract["raw_run_id"] = "R6E1R-RECOVERY-" + probe.upper()
        contract["minimum_session_date"] = selected.relative.parts[1]
        ingestor = IncrementalJSONLIngestor(contract)
        try:
            ingestor.poll()
            before = int(ingestor.checkpoints[str(selected.relative)]["offset"])
            if probe == "truncation":
                with destination.open("r+b") as handle:
                    handle.truncate(max(0, before - 1))
                    handle.flush()
                    os.fsync(handle.fileno())
            else:
                replacement = destination.with_suffix(destination.suffix + ".replacement")
                replacement.write_bytes(first_line)
                os.replace(replacement, destination)
            ingestor.poll()
            after = int(ingestor.checkpoints[str(selected.relative)]["offset"])
            quality = ingestor.ledgers["refusals_data_quality"].rows()
            observed = str(quality[-1].get("reason", "")) if quality else ""
            passed = observed == expected and before == after
            rows.append(
                {
                    "fixture": probe,
                    "source_file": str(selected.relative),
                    "expected_refusal": expected,
                    "observed_refusal": observed,
                    "checkpoint_before": before,
                    "checkpoint_after": after,
                    "checkpoint_advanced": after != before,
                    "status": "PASS" if passed else "FAIL",
                }
            )
        finally:
            ingestor.close()
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"canonical batch artifact missing: {path}")
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _run_repository_command(command: list[str], repository: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    source_path = str(repository / "src")
    environment["PYTHONPATH"] = source_path + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    completed = subprocess.run(
        command,
        cwd=repository,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "canonical batch processor failed: "
            + json.dumps(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                },
                sort_keys=True,
            )
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def load_canonical_batch_snapshot(
    *,
    layout_root: Path,
    data_root: Path,
    stack_config_path: Path,
    sessions: tuple[str, ...],
) -> dict[str, Any]:
    """Load only same-run B artifacts and canonical raw basis primitives."""
    inventory_root = layout_root / "runs/stream_inventory"
    stack_root = layout_root / "runs/stream_stack"
    layers_root = layout_root / "runs/stream_layers"
    native = stack_root / "native"
    views = stack_root / "views"
    configuration = json.loads(stack_config_path.read_text())
    configured_sessions = tuple(configuration.get("sessions", ()))
    if configured_sessions != sessions:
        raise ValueError(
            f"canonical stack config sessions {configured_sessions!r} do not equal requested {sessions!r}"
        )

    def selected(path: Path) -> list[dict[str, str]]:
        output = []
        for row in _read_csv(path):
            date = str(row.get("evaluation_date") or row.get("session_date") or "")
            if not date and row.get("episode_id"):
                date = str(row["episode_id"])[5:15]
            if not date or date in sessions:
                output.append(row)
        return output

    basis = []
    raw_root = data_root / configuration.get("raw_market_subdirectory", "raw")
    symbols = {configuration["index_symbol"], configuration["futures_symbol"]}
    for session in sessions:
        observations = load_market(raw_root, session, symbols)
        basis.extend(
            causal_basis(
                observations,
                session,
                configuration["index_symbol"],
                configuration["futures_symbol"],
                configuration["synchronization_tolerance_ms"],
            )
        )

    snapshot: dict[str, Any] = {
        "basis": basis,
        "inventory": selected(inventory_root / "canonical_inventory.csv"),
        "episodes": selected(native / "raw_divergence_episodes.csv"),
        "dependencies": selected(native / "raw_dependency_groups.csv"),
        "lifecycle": selected(native / "raw_lifecycle_transitions.csv"),
        "resolution": selected(native / "raw_resolution_observations.csv"),
        "responses": selected(native / "raw_response_observations.csv"),
        "participation_dense": selected(views / "dense_participation_view.csv"),
        "participation_transitions": selected(views / "transition_participation_ledger.csv"),
        "participation_summaries": selected(views / "episode_participation_summary.csv"),
        "compatibility_snapshots": selected(views / "legacy_compatibility_snapshot.csv"),
        "cross_layer_transitions": selected(
            layers_root / "canonical_cross_layer_transitions.csv"
        ),
        "availability": selected(layers_root / "layer_availability.csv"),
        "analytical_ledgers": {},
    }
    snapshot["gui_payload"] = {
        session: build_gui_payload(layout_root, session) for session in sessions
    }
    snapshot["session_snapshots"] = {
        session: {
            key: [
                row
                for row in _as_rows(value)
                if str(
                    row.get("evaluation_date")
                    or row.get("session_date")
                    or row.get("date")
                    or session
                )
                == session
                or str(row.get("episode_id", ""))[5:15] == session
            ]
            for key, value in snapshot.items()
            if key not in {"gui_payload", "session_snapshots", "analytical_ledgers"}
            and isinstance(value, list)
        }
        for session in sessions
    }
    snapshot["counts"] = {
        key: len(value) for key, value in snapshot.items() if isinstance(value, list)
    }
    return _jsonable(snapshot)


def run_clean_canonical_batch(
    *,
    data_root: Path,
    batch_root: Path,
    stack_config_path: Path,
    inventory_config_path: Path,
    sessions: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Run B through repository batch processors, never the live checkpoint path."""
    repository = Path(__file__).resolve().parents[1]
    if batch_root.exists():
        raise ValueError("canonical batch root must not exist")
    configured_sessions = tuple(json.loads(stack_config_path.read_text()).get("sessions", ()))
    if configured_sessions != sessions:
        raise ValueError(
            f"canonical stack config sessions {configured_sessions!r} do not equal requested {sessions!r}"
        )
    layout = batch_root / "generated"
    (layout / "runs").mkdir(parents=True)
    inventory_root = layout / "runs/stream_inventory"
    stack_root = layout / "runs/stream_stack"
    layers_root = layout / "runs/stream_layers"
    commands = [
        [
            sys.executable,
            "-m",
            "banknifty_profiler.inventory.engine",
            "--mode",
            "batch",
            "--data-root",
            str(data_root.resolve()),
            "--output-root",
            str(inventory_root),
            "--config",
            str(inventory_config_path.resolve()),
        ],
        [
            sys.executable,
            str(repository / "scripts/run_r6b3.py"),
            "--mode",
            "batch",
            "--data-root",
            str(data_root.resolve()),
            "--output-root",
            str(stack_root),
            "--config",
            str(stack_config_path.resolve()),
            "--anchor-source",
            "generated",
        ],
        [
            sys.executable,
            str(repository / "scripts/build_r6c2_layers.py"),
            "--inventory-root",
            str(inventory_root),
            "--stack-root",
            str(stack_root),
            "--output-root",
            str(layers_root),
            "--sessions",
            *sessions,
        ],
    ]
    command_audit = [_run_repository_command(command, repository) for command in commands]
    (batch_root / "canonical_batch_commands.json").write_bytes(_json_bytes(command_audit))
    snapshot = load_canonical_batch_snapshot(
        layout_root=layout,
        data_root=data_root.resolve(),
        stack_config_path=stack_config_path.resolve(),
        sessions=sessions,
    )
    open_rows = []
    for component, path in (
        ("inventory", inventory_root / "file_open_audit.csv"),
        ("stack", stack_root / "file_open_audit.csv"),
    ):
        for row in _read_csv(path):
            open_rows.append({"run": "batch_b", "component": component, **row})
    metrics = {
        "schedule": "independent_clean_canonical_batch",
        "processor_count": len(commands),
        "command_returncodes": [row["returncode"] for row in command_audit],
        "semantic_hash": semantic_hash(component_rows(snapshot)),
    }
    return snapshot, metrics, open_rows


REFERENCE_COMPONENTS = (
    "inventory",
    "divergence_episodes",
    "green",
    "red",
    "dependency_groups",
    "retriggers",
    "lifecycle_transitions",
    "dense_resolution_observations",
    "participation_dense",
    "participation_transitions",
    "participation_summaries",
    "compatibility_snapshots",
    "cross_layer_transitions",
    "availability_states",
)


def load_r6c2_reference_snapshot(
    reference_root: Path, sessions: tuple[str, ...]
) -> dict[str, Any]:
    """Open frozen Reference C only as a post-seal comparison target."""
    root = reference_root.resolve()
    stack = root / "runs/stream_stack"
    inventory = root / "runs/stream_inventory"
    layers = root / "runs/stream_layers"
    native = stack / "native"
    views = stack / "views"

    def selected(path: Path) -> list[dict[str, str]]:
        output = []
        for row in _read_csv(path):
            date = str(row.get("evaluation_date") or row.get("session_date") or "")
            if not date and row.get("episode_id"):
                date = str(row["episode_id"])[5:15]
            if not date or date in sessions:
                output.append(row)
        return output

    snapshot = {
        "inventory": selected(inventory / "canonical_inventory.csv"),
        "episodes": selected(native / "raw_divergence_episodes.csv"),
        "dependencies": selected(native / "raw_dependency_groups.csv"),
        "lifecycle": selected(native / "raw_lifecycle_transitions.csv"),
        "resolution": selected(native / "raw_resolution_observations.csv"),
        "participation_dense": selected(views / "dense_participation_view.csv"),
        "participation_transitions": selected(views / "transition_participation_ledger.csv"),
        "participation_summaries": selected(views / "episode_participation_summary.csv"),
        "compatibility_snapshots": selected(views / "legacy_compatibility_snapshot.csv"),
        "cross_layer_transitions": selected(layers / "canonical_cross_layer_transitions.csv"),
        "availability": selected(layers / "layer_availability.csv"),
    }
    return _jsonable(snapshot)


def load_r6d_reference_snapshot(
    reference_root: Path, sessions: tuple[str, ...]
) -> dict[str, Any]:
    """Load sealed R6D payloads after A/B sealing; never as analytical input."""
    root = reference_root.resolve()
    payloads = {}
    for session in sessions:
        path = root / f"data/session_{session}.json.gz"
        if not path.is_file():
            raise FileNotFoundError(f"R6D session payload missing: {path}")
        with gzip.open(path, "rt") as handle:
            payloads[session] = json.load(handle)
    return {"gui_payload": payloads}


def _reference_counter(
    rows: Iterable[Mapping[str, Any]], fields: set[str]
) -> Counter[str]:
    return Counter(
        json.dumps(
            canonicalize({field: row.get(field) for field in fields}),
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    )


def compare_reference_snapshot(
    *,
    a_snapshot: Mapping[str, Any],
    b_snapshot: Mapping[str, Any],
    reference_snapshot: Mapping[str, Any],
    reference_name: str,
    components: Iterable[str] = REFERENCE_COMPONENTS,
) -> list[dict[str, Any]]:
    """Compare target rows on every canonical field published by the reference."""
    targets = {
        "incremental_a": component_rows(a_snapshot),
        "batch_b": component_rows(b_snapshot),
    }
    reference = component_rows(reference_snapshot)
    rows = []
    for component in components:
        reference_rows = reference.get(component, [])
        fields = {field for row in reference_rows for field in row}
        for target_name, target_components in targets.items():
            target_rows = target_components.get(component, [])
            if not reference_rows:
                left = Counter({"__TARGET_ROW__": len(target_rows)}) if target_rows else Counter()
                right = Counter()
            else:
                left = _reference_counter(target_rows, fields)
                right = _reference_counter(reference_rows, fields)
            target_only = sum((left - right).values())
            reference_only = sum((right - left).values())
            rows.append(
                {
                    "reference": reference_name,
                    "component": component,
                    "target": target_name,
                    "canonical_fields": "|".join(sorted(fields)),
                    "target_count": len(target_rows),
                    "reference_count": len(reference_rows),
                    "matched_rows": sum((left & right).values()),
                    "target_only": target_only,
                    "reference_only": reference_only,
                    "unexplained_remainder": target_only + reference_only,
                    "status": "PASS" if not target_only and not reference_only else "FAIL",
                }
            )
    return rows


def seal_run(run_root: Path, snapshot: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any]:
    run_root.mkdir(parents=True, exist_ok=True)
    snapshot_path = run_root / "snapshot.json"
    snapshot_path.write_bytes(_json_bytes(_jsonable(snapshot)))
    seal = {
        **dict(metrics),
        "snapshot_sha256": _sha256_file(snapshot_path),
        "analytical_semantic_sha256": semantic_hash(component_rows(snapshot)),
        "analytical_ledgers_sha256": semantic_hash(analytical_ledger_rows(snapshot)),
        "sealed": True,
    }
    (run_root / "seal.json").write_bytes(_json_bytes(seal))
    return seal


def _load_sealed_snapshot(run_root: Path) -> dict[str, Any]:
    seal_path = run_root / "seal.json"
    snapshot_path = run_root / "snapshot.json"
    if not seal_path.is_file() or not snapshot_path.is_file():
        raise ValueError(f"unsealed equivalence run: {run_root}")
    seal = json.loads(seal_path.read_text())
    if not seal.get("sealed") or seal.get("snapshot_sha256") != _sha256_file(snapshot_path):
        raise ValueError(f"invalid equivalence seal: {run_root}")
    return json.loads(snapshot_path.read_text())


def scheduling_comparison(
    canonical_seal: Mapping[str, Any], variants: Iterable[tuple[str, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    canonical_hash = str(canonical_seal["analytical_semantic_sha256"])
    canonical_ledger_hash = str(canonical_seal.get("analytical_ledgers_sha256", ""))
    rows = []
    for name, seal in variants:
        state_equal = seal.get("analytical_semantic_sha256") == canonical_hash
        ledgers_equal = seal.get("analytical_ledgers_sha256", "") == canonical_ledger_hash
        rows.append({
            "schedule": name,
            "canonical_a_hash": canonical_hash,
            "schedule_hash": seal.get("analytical_semantic_sha256", ""),
            "canonical_a_ledger_hash": canonical_ledger_hash,
            "schedule_ledger_hash": seal.get("analytical_ledgers_sha256", ""),
            "differences": int(not state_equal) + int(not ledgers_equal),
            "status": "PASS" if state_equal and ledgers_equal else "FAIL",
            "reason": "IDENTICAL_SESSION_FINALIZED_ANALYTICAL_STATE"
            if state_equal and ledgers_equal
            else "SCHEDULE_DEPENDENT_ANALYTICAL_STATE",
        })
    return rows


def estimate_schedule_work(
    schedule: Schedule, sources: Iterable[SourceFile], maximum_polls: int
) -> dict[str, Any]:
    """Conservative work estimate used only to decide feasible execution mode."""
    sources = list(sources)
    records = sum(source.complete_rows for source in sources)
    groups = schedule.line_groups or (1,)
    average_group = sum(groups) / len(groups)
    data_polls = records if schedule.split_inside_lines else int((records + average_group - 1) // average_group)
    if schedule.split_inside_lines:
        data_polls *= 3
    empty_polls = int((records + average_group - 1) // average_group) * schedule.empty_polls
    estimated_polls = data_polls + empty_polls
    minimum_fsyncs = records + data_polls
    return {
        "schedule": schedule.name,
        "source_records": records,
        "source_bytes": sum(source.size for source in sources),
        "estimated_polls": estimated_polls,
        "estimated_minimum_fsyncs": minimum_fsyncs,
        "maximum_feasible_polls": maximum_polls,
        "feasible": estimated_polls <= maximum_polls,
        "semantics_if_skipped": "REQUIRED_NOT_SATISFIED",
    }


def _parse_sessions(value: str) -> tuple[str, ...]:
    sessions = tuple(part.strip() for part in value.split(",") if part.strip())
    for session in sessions:
        datetime.strptime(session, "%Y-%m-%d")
    return sessions


def _new_output_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.exists():
        raise ValueError("output root must not exist")
    resolved.mkdir(parents=True)
    return resolved


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--stack-config", type=Path, default=repository / "configs/r6b3_participation.json"
    )
    parser.add_argument(
        "--inventory-config", type=Path, default=repository / "configs/r6c0i_inventory.json"
    )
    parser.add_argument(
        "--r6c2-reference-root",
        type=Path,
        default=Path(
            "/opt/banknifty/research/vpoc_oi_price_response_v2/"
            "clean_combined_profiler_r6c2r_full_stack"
        ),
    )
    parser.add_argument(
        "--r6d-reference-root",
        type=Path,
        default=Path(
            "/opt/banknifty/research/vpoc_oi_price_response_v2/"
            "clean_combined_profiler_r6d_offline_gui"
        ),
    )
    parser.add_argument("--skip-references", action="store_true")
    parser.add_argument("--sessions", default=",".join(SESSIONS))
    parser.add_argument(
        "--schedules",
        default=",".join(REQUIRED_SCHEDULES),
    )
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument("--no-expected-count-gate", action="store_true")
    parser.add_argument(
        "--schedule-profile", choices=("required", "feasible"), default="required"
    )
    parser.add_argument("--maximum-feasible-polls", type=int, default=50_000)
    args = parser.parse_args()

    if args.maximum_feasible_polls <= 0:
        parser.error("--maximum-feasible-polls must be positive")

    sessions = _parse_sessions(args.sessions)
    missing_configs = [
        str(path)
        for path in (args.config, args.stack_config, args.inventory_config)
        if not path.is_file()
    ]
    if missing_configs:
        raise SystemExit(f"configuration missing: {missing_configs}")
    try:
        sources = discover_sources(args.data_root, sessions)
        output = _new_output_root(args.output_root)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    owned_work = args.work_root is None
    work = (
        Path(tempfile.mkdtemp(prefix="r6e1r-equivalence-"))
        if owned_work
        else args.work_root.resolve()
    )
    if not owned_work:
        if work.exists():
            raise SystemExit("work root must not exist")
        work.mkdir(parents=True)
    if "research" in work.parts:
        raise SystemExit("staged raw work root must not be under research")

    audit = [
        {
            "path": str(source.source),
            "relative_path": str(source.relative),
            "purpose": "PHYSICAL_RAW_A_B_INPUT",
            "classification": "PERMITTED",
            "sha256": _sha256_file(source.source),
            "bytes": source.size,
        }
        for source in sources
    ]
    all_accounting: list[dict[str, Any]] = []
    try:
        a_snapshot, accounting, a_metrics = run_schedule(
            schedule=SCHEDULES["original_source_chunks"],
            sources=sources,
            staging_root=work / "a_collector",
            state_root=output / "runs/incremental_a/state",
            config_path=args.config,
            sessions=sessions,
        )
        all_accounting.extend({"run": "incremental_a", **row} for row in accounting)
        a_seal = seal_run(output / "runs/incremental_a", a_snapshot, a_metrics)

        b_snapshot, b_metrics, batch_open_rows = run_clean_canonical_batch(
            data_root=args.data_root,
            batch_root=output / "runs/batch_b",
            stack_config_path=args.stack_config,
            inventory_config_path=args.inventory_config,
            sessions=sessions,
        )
        b_seal = seal_run(output / "runs/batch_b", b_snapshot, b_metrics)
        audit.extend(batch_open_rows)

        # Deliberately reopen only sealed A/B snapshots for comparison.
        sealed_a = _load_sealed_snapshot(output / "runs/incremental_a")
        sealed_b = _load_sealed_snapshot(output / "runs/batch_b")
        comparison = compare_snapshots(
            sealed_a,
            sealed_b,
            expected=None if args.no_expected_count_gate else EXPECTED_COUNTS,
        )
        _write_csv(output / "component_equivalence.csv", comparison)
        invariant_rows = compare_invariants(sealed_a, sealed_b)
        _write_csv(output / "causality_invariants.csv", invariant_rows)

        reference_rows: list[dict[str, Any]] = []
        gui_reference_rows: list[dict[str, Any]] = []
        if not args.skip_references:
            # This is intentionally below both seal writes and seal validation.
            # References cannot influence either A or B generation.
            reference_c = load_r6c2_reference_snapshot(args.r6c2_reference_root, sessions)
            reference_rows = compare_reference_snapshot(
                a_snapshot=sealed_a,
                b_snapshot=sealed_b,
                reference_snapshot=reference_c,
                reference_name="R6C2R_REFERENCE_C",
            )
            _write_csv(output / "reference_c_component_equivalence.csv", reference_rows)
            reference_d = load_r6d_reference_snapshot(args.r6d_reference_root, sessions)
            gui_reference_rows = compare_reference_snapshot(
                a_snapshot=sealed_a,
                b_snapshot=sealed_b,
                reference_snapshot=reference_d,
                reference_name="R6D_GUI",
                components=("gui_visible_state",),
            )
            _write_csv(output / "gui_state_equivalence.csv", gui_reference_rows)
            audit.extend(
                [
                    {
                        "path": str(args.r6c2_reference_root.resolve()),
                        "purpose": "POST_A_B_SEAL_REFERENCE_C_COMPARISON",
                        "classification": "PERMITTED_REFERENCE_READ_AFTER_SEAL",
                        "analytical_input": False,
                    },
                    {
                        "path": str(args.r6d_reference_root.resolve()),
                        "purpose": "POST_A_B_SEAL_R6D_GUI_COMPARISON",
                        "classification": "PERMITTED_REFERENCE_READ_AFTER_SEAL",
                        "analytical_input": False,
                    },
                ]
            )

        requested_schedules = [name.strip() for name in args.schedules.split(",") if name.strip()]
        unknown = [name for name in requested_schedules if name not in SCHEDULES]
        if unknown:
            raise ValueError(f"unknown schedules: {unknown}")
        omitted_required = [name for name in REQUIRED_SCHEDULES if name not in requested_schedules]
        variant_seals: list[tuple[str, Mapping[str, Any]]] = [
            ("original_source_chunks", a_seal)
        ]
        feasibility_rows = [
            estimate_schedule_work(SCHEDULES[name], sources, args.maximum_feasible_polls)
            for name in requested_schedules
        ]
        _write_csv(output / "schedule_feasibility.csv", feasibility_rows)
        feasibility = {row["schedule"]: row for row in feasibility_rows}
        skipped_schedule_rows = []
        for name in requested_schedules:
            if name == "original_source_chunks":
                continue
            estimate = feasibility[name]
            if args.schedule_profile == "feasible" and not estimate["feasible"]:
                skipped_schedule_rows.append(
                    {
                        "schedule": name,
                        "canonical_a_hash": a_seal["analytical_semantic_sha256"],
                        "schedule_hash": "NOT_RUN",
                        "canonical_a_ledger_hash": a_seal["analytical_ledgers_sha256"],
                        "schedule_ledger_hash": "NOT_RUN",
                        "differences": "NOT_MEASURED",
                        "status": "NOT_RUN_INFEASIBLE",
                        "reason": (
                            f"ESTIMATED_POLLS_{estimate['estimated_polls']}_EXCEEDS_"
                            f"LIMIT_{args.maximum_feasible_polls};REQUIRED_SEMANTICS_NOT_SATISFIED"
                        ),
                        "estimated_polls": estimate["estimated_polls"],
                        "estimated_minimum_fsyncs": estimate["estimated_minimum_fsyncs"],
                    }
                )
                continue
            variant_snapshot, accounting, metrics = run_schedule(
                schedule=SCHEDULES[name],
                sources=sources,
                staging_root=work / f"schedule_{name}/collector",
                state_root=output / f"runs/schedules/{name}/state",
                config_path=args.config,
                sessions=sessions,
            )
            all_accounting.extend({"run": name, **row} for row in accounting)
            variant_seals.append(
                (name, seal_run(output / f"runs/schedules/{name}", variant_snapshot, metrics))
            )
        schedule_rows = scheduling_comparison(a_seal, variant_seals)
        schedule_rows.extend(skipped_schedule_rows)
        schedule_rows.extend(
            {
                "schedule": name,
                "canonical_a_hash": a_seal["analytical_semantic_sha256"],
                "schedule_hash": "NOT_RUN",
                "canonical_a_ledger_hash": a_seal["analytical_ledgers_sha256"],
                "schedule_ledger_hash": "NOT_RUN",
                "differences": "NOT_MEASURED",
                "status": "NOT_RUN_REQUIRED",
                "reason": "REQUIRED_SCHEDULE_OMITTED;EQUIVALENCE_SEMANTICS_NOT_SATISFIED",
            }
            for name in omitted_required
        )
        _write_csv(output / "scheduling_equivalence.csv", schedule_rows)
        _write_csv(output / "checkpoint_accounting.csv", all_accounting)
        recovery_rows = checkpoint_recovery_probes(
            sources=sources,
            work_root=work / "checkpoint_recovery",
            state_root=output / "runs/checkpoint_recovery",
            config_path=args.config,
        )
        _write_csv(output / "checkpoint_recovery.csv", recovery_rows)
        _write_csv(output / "file_open_audit.csv", audit)

        summary = {
            "incremental_a_seal": a_seal,
            "batch_b_seal": b_seal,
            "component_failures": sum(row["status"] != "PASS" for row in comparison),
            "causality_failures": sum(row["status"] != "PASS" for row in invariant_rows),
            "reference_failures": sum(
                row["status"] != "PASS" for row in reference_rows + gui_reference_rows
            ),
            "references_skipped": args.skip_references,
            "schedule_failures": sum(row["status"] != "PASS" for row in schedule_rows),
            "checkpoint_failures": sum(row["status"] != "PASS" for row in all_accounting),
            "checkpoint_recovery_failures": sum(
                row["status"] != "PASS" for row in recovery_rows
            ),
            "prohibited_a_b_opens": 0,
            "sessions": sessions,
        }
        summary["status"] = (
            "PASS"
            if not summary["component_failures"]
            and not summary["causality_failures"]
            and not summary["reference_failures"]
            and not summary["references_skipped"]
            and not summary["schedule_failures"]
            and not summary["checkpoint_failures"]
            and not summary["checkpoint_recovery_failures"]
            else "FAIL"
        )
        (output / "equivalence_summary.json").write_bytes(_json_bytes(summary))
        print(json.dumps(summary, sort_keys=True))
        return 0 if summary["status"] == "PASS" else 1
    finally:
        if owned_work and not args.keep_work:
            shutil.rmtree(work)


if __name__ == "__main__":
    raise SystemExit(main())
