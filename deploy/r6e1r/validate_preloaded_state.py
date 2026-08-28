#!/usr/bin/env python3
"""Fail-closed validation for an R6E1R state preload.

The validator intentionally depends only on the Python standard library so it
can run before either service is installed.  Its stdout is a small, sanitized
JSON result: no state paths, source-file names, database values, or record
payloads are emitted.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from typing import Any, NoReturn, Sequence


SCHEMA = "R6E1R_PRELOADED_STATE_VALIDATION_V1"
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
ORCHESTRATOR_STATE_VERSION = "R6E1R_LIVE_ANALYTICAL_STATE_V1"
CROSS_LAYER_CONTEXT_VERSION = "R6E1R_CROSS_LAYER_CONTEXT_V1"
STATE_TREE_MANIFEST_SCHEMA = "R6E1R_INCREMENTAL_A_STATE_TREE_MANIFEST_V1"
EXPECTED_SESSION_COUNT = 6
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
INTEGRITY_BLOCK_BYTES = 65_536
REQUIRED_STATE_FILES = (
    "checkpoints.json",
    "dedup.sqlite3",
    "live_analytical_orchestrator.json",
)
SQLITE_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm", ".journal", ".wal")
REQUIRED_IDENTITY_LEDGERS = (
    "availability_transitions.jsonl",
    "cross_layer_transitions.jsonl",
    "dependency_retriggers.jsonl",
    "divergence_confirmations.jsonl",
    "inventory_winner_transitions.jsonl",
    "lifecycle_transitions.jsonl",
    "normalized_raw_events.jsonl",
    "participation_transitions.jsonl",
    "raw_file_checkpoints.jsonl",
)
ZERO_EQUIVALENCE_GATES = (
    "component_failures",
    "analytical_ledger_failures",
    "causality_failures",
    "reference_failures",
    "schedule_failures",
    "checkpoint_failures",
    "checkpoint_recovery_failures",
    "file_open_audit_unmeasured_rows",
    "prohibited_a_b_opens",
    "post_run_source_mutations",
)
REUSE_VALIDATION_KEYS = frozenset({
    "status",
    "authoritative_source_hashes_verified",
    "projection_file_hashes_verified",
    "provenance_verified",
    "provenance_rows_verified",
    "dynamic_contract_sessions_verified",
})
AUGUST_17_POLICY = "PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED"
FROZEN_OUTPUT_COUNTS = {
    "inventory": 255,
    "episodes": 65,
    "green": 41,
    "red": 24,
    "retriggers": 14,
    "lifecycle": 14_201,
    "resolution": 164_668,
    "responses": 65,
    "participation_dense": 69_225,
    "participation_transitions": 32_068,
    "participation_summaries": 65,
    "compatibility_snapshots": 65,
    "cross_layer_transitions": 60_659,
}
FALLBACK_METRIC_FIELDS = (
    "intraday_fallback_rows",
    "partial_fixed_fallback_rows",
    "intraday_fallback_cross_layer_rows",
    "partial_fixed_fallback_cross_layer_rows",
)
FALLBACK_HORIZONS = frozenset({"ID", "1D", "2D", "3D"})
OUTPUT_LIST_FIELDS = (
    "basis", "inventory", "episodes", "dependencies", "lifecycle",
    "resolution", "responses", "participation_dense",
    "participation_transitions", "participation_summaries",
    "compatibility_snapshots", "cross_layer_transitions",
)
OUTPUT_COUNT_FIELDS = tuple(
    field for field in OUTPUT_LIST_FIELDS if field != "responses"
)
REQUIRED_CALLBACKS = {
    "synchronization", "inventory", "divergence_detector", "dependency",
    "lifecycle", "participation", "participation_views", "cross_layer",
    "gui_projection",
}


class ValidationError(Exception):
    """An expected, sanitized preflight refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def refuse(code: str) -> NoReturn:
    raise ValidationError(code)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_hash(value: str, code: str) -> str:
    if not HASH_PATTERN.fullmatch(value):
        refuse(code)
    return value


def require_plain_file(path: Path, code: str) -> None:
    try:
        value = path.lstat()
    except OSError:
        refuse(code)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        refuse(code)


def load_json_object(path: Path, code: str) -> dict[str, Any]:
    require_plain_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        refuse(code)
    if not isinstance(value, dict):
        refuse(code)
    return value


def validate_state_tree(state_root: Path) -> int:
    """Reject links, special files, and uncheckpointed SQLite sidecars."""
    try:
        root_stat = state_root.lstat()
    except OSError:
        refuse("STATE_ROOT_UNREADABLE")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        refuse("STATE_ROOT_NOT_PLAIN_DIRECTORY")

    file_count = 0
    for current, directory_names, file_names in os.walk(
        state_root, topdown=True, followlinks=False,
    ):
        current_path = Path(current)
        for name in directory_names:
            child = current_path / name
            try:
                child_stat = child.lstat()
            except OSError:
                refuse("STATE_TREE_UNREADABLE")
            if stat.S_ISLNK(child_stat.st_mode):
                refuse("STATE_TREE_SYMLINK")
            if not stat.S_ISDIR(child_stat.st_mode):
                refuse("STATE_TREE_NONREGULAR")
        for name in file_names:
            child = current_path / name
            try:
                child_stat = child.lstat()
            except OSError:
                refuse("STATE_TREE_UNREADABLE")
            if stat.S_ISLNK(child_stat.st_mode):
                refuse("STATE_TREE_SYMLINK")
            if not stat.S_ISREG(child_stat.st_mode):
                refuse("STATE_TREE_NONREGULAR")
            if name.lower().endswith(SQLITE_SIDECAR_SUFFIXES):
                refuse("SQLITE_SIDECAR_PRESENT")
            file_count += 1
    return file_count


def _safe_manifest_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        refuse("STATE_MANIFEST_INVALID")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        refuse("STATE_MANIFEST_INVALID")
    return value


def validate_bound_state_tree(
    state_root: Path,
    state_manifest_path: Path,
    expected_seal: dict[str, Any],
    observed_file_count: int,
) -> tuple[str, str, int]:
    """Match every staged state byte to the PASS-bound harness manifest."""
    require_plain_file(state_manifest_path, "STATE_MANIFEST_INVALID")
    manifest_sha256 = sha256_file(state_manifest_path)
    if manifest_sha256 != expected_seal["state_manifest_sha256"]:
        refuse("STATE_MANIFEST_SEAL_MISMATCH")
    manifest = load_json_object(state_manifest_path, "STATE_MANIFEST_INVALID")
    files = manifest.get("files")
    if (
        manifest.get("schema") != STATE_TREE_MANIFEST_SCHEMA
        or manifest.get("classification") != CLASSIFICATION
        or type(manifest.get("file_count")) is not int
        or manifest.get("file_count") != expected_seal["state_file_count"]
        or manifest.get("state_tree_sha256")
        != expected_seal["state_tree_sha256"]
        or not isinstance(files, list)
        or len(files) != manifest.get("file_count")
    ):
        refuse("STATE_MANIFEST_CONTRACT_MISMATCH")
    if observed_file_count != manifest["file_count"]:
        refuse("STATE_MANIFEST_FILE_SET_MISMATCH")

    expected_files: dict[str, tuple[int, str]] = {}
    aggregate = hashlib.sha256()
    paths: list[str] = []
    for row in files:
        if not isinstance(row, dict):
            refuse("STATE_MANIFEST_INVALID")
        relative = _safe_manifest_relative_path(row.get("path"))
        size = row.get("size")
        digest = row.get("sha256")
        if (
            relative in expected_files
            or type(size) is not int
            or size < 0
            or not isinstance(digest, str)
            or HASH_PATTERN.fullmatch(digest) is None
        ):
            refuse("STATE_MANIFEST_INVALID")
        paths.append(relative)
        expected_files[relative] = (size, digest)
        aggregate.update(f"{relative}\0{digest}\0{size}\n".encode())
    if paths != sorted(paths):
        refuse("STATE_MANIFEST_INVALID")
    tree_sha256 = aggregate.hexdigest()
    if tree_sha256 != manifest.get("state_tree_sha256"):
        refuse("STATE_MANIFEST_TREE_HASH_MISMATCH")

    observed_files: dict[str, Path] = {}
    try:
        for current, _, file_names in os.walk(
            state_root, topdown=True, followlinks=False,
        ):
            current_path = Path(current)
            for name in file_names:
                child = current_path / name
                relative = _safe_manifest_relative_path(
                    child.relative_to(state_root).as_posix()
                )
                observed_files[relative] = child
    except (OSError, ValueError):
        refuse("STATE_TREE_UNREADABLE")
    if set(observed_files) != set(expected_files):
        refuse("STATE_MANIFEST_FILE_SET_MISMATCH")
    for relative, child in observed_files.items():
        expected_size, expected_digest = expected_files[relative]
        try:
            actual_size = child.stat().st_size
        except OSError:
            refuse("STATE_TREE_UNREADABLE")
        if actual_size != expected_size:
            refuse("STATE_MANIFEST_FILE_SIZE_MISMATCH")
        try:
            actual_digest = sha256_file(child)
        except OSError:
            refuse("STATE_TREE_UNREADABLE")
        if actual_digest != expected_digest:
            refuse("STATE_MANIFEST_FILE_HASH_MISMATCH")
    return manifest_sha256, tree_sha256, len(observed_files)


def validate_sessions(
    orchestrator: dict[str, Any], expected_sessions: Sequence[str],
) -> None:
    expected = set(expected_sessions)
    if len(expected_sessions) != EXPECTED_SESSION_COUNT or len(expected) != EXPECTED_SESSION_COUNT:
        refuse("EXPECTED_SESSIONS_NOT_EXACTLY_SIX")
    if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in expected):
        refuse("EXPECTED_SESSION_INVALID")
    if orchestrator.get("version") != ORCHESTRATOR_STATE_VERSION:
        refuse("ORCHESTRATOR_STATE_VERSION_MISMATCH")

    outputs = orchestrator.get("outputs")
    finalized = orchestrator.get("finalized_sessions")
    contexts = orchestrator.get("cross_layer_contexts")
    if not isinstance(outputs, dict) or set(outputs) != expected:
        refuse("OUTPUT_SESSION_SET_MISMATCH")
    if (
        not isinstance(finalized, list)
        or len(finalized) != EXPECTED_SESSION_COUNT
        or set(finalized) != expected
    ):
        refuse("FINALIZED_SESSION_SET_MISMATCH")
    if orchestrator.get("dirty_sessions") != []:
        refuse("DIRTY_SESSIONS_PRESENT")
    if orchestrator.get("sessions") != {}:
        refuse("MUTABLE_SESSIONS_PRESENT")
    if not isinstance(contexts, dict) or set(contexts) != expected:
        refuse("CROSS_LAYER_CONTEXT_SESSION_SET_MISMATCH")

    prior_counts = {
        "inventory_source_count": 0,
        "episode_source_count": 0,
        "resolution_source_count": 0,
    }
    for session_date, output in outputs.items():
        if not isinstance(output, dict) or output.get("session_date") != session_date:
            refuse("OUTPUT_SESSION_IDENTITY_MISMATCH")
    for session_date in sorted(expected_sessions):
        context = contexts.get(session_date)
        if (
            not isinstance(context, dict)
            or context.get("version") != CROSS_LAYER_CONTEXT_VERSION
        ):
            refuse("CROSS_LAYER_CONTEXT_SHAPE_INVALID")
        for field, prior in prior_counts.items():
            value = context.get(field)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < prior
            ):
                refuse("CROSS_LAYER_CONTEXT_COUNT_INVALID")
            prior_counts[field] = value
        for field in ("inventory_previous", "resolution_previous"):
            states = context.get(field)
            if (
                not isinstance(states, dict)
                or any(
                    not isinstance(key, str) or not isinstance(value, str)
                    for key, value in states.items()
                )
            ):
                refuse("CROSS_LAYER_CONTEXT_SHAPE_INVALID")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_analytical_outputs(
    orchestrator: dict[str, Any],
    expected_sessions: Sequence[str],
    fallback_contract: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Recount the bound six-session payload instead of trusting metadata."""
    outputs = orchestrator.get("outputs")
    if not isinstance(outputs, dict):
        refuse("ANALYTICAL_OUTPUT_SHAPE_INVALID")
    aggregate = {key: 0 for key in FROZEN_OUTPUT_COUNTS}
    fallback = (
        {
            "sessions": [],
            **{field: 0 for field in FALLBACK_METRIC_FIELDS},
        }
        if fallback_contract is None
        else fallback_contract
    )
    if (
        not isinstance(fallback, dict)
        or set(fallback) != {"sessions", *FALLBACK_METRIC_FIELDS}
        or not isinstance(fallback.get("sessions"), list)
        or any(
            type(fallback.get(field)) is not int or fallback[field] < 0
            for field in FALLBACK_METRIC_FIELDS
        )
    ):
        refuse("FALLBACK_ANALYTICAL_CONTRACT_INVALID")
    fallback_sessions = set(fallback["sessions"])
    if (
        len(fallback_sessions) != len(fallback["sessions"])
        or fallback["sessions"] != sorted(fallback["sessions"])
        or not fallback_sessions.issubset(set(expected_sessions))
    ):
        refuse("FALLBACK_ANALYTICAL_CONTRACT_INVALID")
    observed_fallback = {field: 0 for field in FALLBACK_METRIC_FIELDS}
    valid_basis_total = 0
    basis_total = 0
    for session_date in expected_sessions:
        output = outputs.get(session_date)
        if not isinstance(output, dict):
            refuse("ANALYTICAL_OUTPUT_SHAPE_INVALID")
        rows_by_field: dict[str, list[dict[str, Any]]] = {}
        for field in OUTPUT_LIST_FIELDS:
            value = output.get(field)
            if (
                not isinstance(value, list)
                or any(not isinstance(row, dict) for row in value)
            ):
                refuse("ANALYTICAL_OUTPUT_SHAPE_INVALID")
            rows_by_field[field] = value

        valid_basis = [
            row
            for row in rows_by_field["basis"]
            if row.get("validity_status") == "VALID"
            and _is_number(row.get("index_price"))
            and _is_number(row.get("futures_price"))
            and _is_number(row.get("basis_value"))
            and isinstance(row.get("basis_timestamp"), str)
            and bool(row.get("basis_timestamp"))
            and isinstance(row.get("index_receipt_timestamp"), str)
            and bool(row.get("index_receipt_timestamp"))
            and isinstance(row.get("futures_receipt_timestamp"), str)
            and bool(row.get("futures_receipt_timestamp"))
        ]
        if len(valid_basis) < 2:
            refuse("ANALYTICAL_BASIS_MULTIPOINT_REQUIRED")
        if len({row["basis_timestamp"] for row in valid_basis}) < 2:
            refuse("ANALYTICAL_BASIS_MULTIPOINT_REQUIRED")
        basis_total += len(rows_by_field["basis"])
        valid_basis_total += len(valid_basis)

        availability = output.get("availability")
        gui_payload = output.get("gui_payload")
        callbacks = output.get("callback_invocations")
        cached_counts = output.get("counts")
        if (
            not isinstance(availability, dict)
            or not isinstance(availability.get("layers"), dict)
            or not isinstance(availability.get("overall_state"), str)
            or type(availability.get("market_display_enabled")) is not bool
            or not isinstance(gui_payload, dict)
            or gui_payload.get("schema") != "R6E_LIVE_SESSION_PAYLOAD_V1"
            or gui_payload.get("classification") != CLASSIFICATION
            or gui_payload.get("date") != session_date
            or not isinstance(gui_payload.get("price"), dict)
            or not isinstance(gui_payload["price"].get("fields"), list)
            or not isinstance(gui_payload["price"].get("rows"), list)
            or len(gui_payload["price"]["rows"]) < 2
            or not isinstance(callbacks, dict)
            or not REQUIRED_CALLBACKS.issubset(callbacks)
            or any(
                type(callbacks.get(name)) is not int or callbacks[name] <= 0
                for name in REQUIRED_CALLBACKS
            )
            or not isinstance(output.get("participation_view_seal"), dict)
            or not isinstance(output.get("fixed_inventory_cache"), dict)
            or not isinstance(cached_counts, dict)
            or type(cached_counts.get("observations")) is not int
            or cached_counts["observations"] <= 0
        ):
            refuse("ANALYTICAL_OUTPUT_SHAPE_INVALID")
        if any(
            type(cached_counts.get(field)) is not int
            or cached_counts[field] != len(rows_by_field[field])
            for field in OUTPUT_COUNT_FIELDS
        ):
            refuse("ANALYTICAL_OUTPUT_CACHED_COUNT_MISMATCH")

        for field in (
            "episodes", "lifecycle", "resolution", "responses",
            "participation_dense", "participation_transitions",
            "participation_summaries", "compatibility_snapshots",
        ):
            aggregate[field] += len(rows_by_field[field])
        for row in rows_by_field["inventory"]:
            if session_date not in fallback_sessions:
                aggregate["inventory"] += 1
                continue
            horizon = str(row.get("horizon", ""))
            if (
                row.get("evaluation_date") != session_date
                or horizon not in FALLBACK_HORIZONS
            ):
                refuse("FALLBACK_ANALYTICAL_OUTPUT_SHAPE_INVALID")
            field = (
                "intraday_fallback_rows"
                if horizon == "ID"
                else "partial_fixed_fallback_rows"
            )
            observed_fallback[field] += 1
        for row in rows_by_field["cross_layer_transitions"]:
            if (
                session_date not in fallback_sessions
                or row.get("component") != "INVENTORY"
            ):
                aggregate["cross_layer_transitions"] += 1
                continue
            horizon = str(row.get("horizon", ""))
            if (
                row.get("evaluation_date") != session_date
                or horizon not in FALLBACK_HORIZONS
            ):
                refuse("FALLBACK_ANALYTICAL_OUTPUT_SHAPE_INVALID")
            field = (
                "intraday_fallback_cross_layer_rows"
                if horizon == "ID"
                else "partial_fixed_fallback_cross_layer_rows"
            )
            observed_fallback[field] += 1
        for episode in rows_by_field["episodes"]:
            colour = str(
                episode.get("colour", episode.get("episode_type", ""))
            ).upper()
            aggregate["green"] += int(colour.startswith("GREEN"))
            aggregate["red"] += int(colour.startswith("RED"))
        aggregate["retriggers"] += sum(
            row.get("retrigger_flag") is True
            or str(row.get("retrigger_flag", "")).lower() == "true"
            or row.get("classification") == "DEPENDENT_RETRIGGER"
            for row in rows_by_field["dependencies"]
        )
    if aggregate != FROZEN_OUTPUT_COUNTS:
        refuse("FROZEN_ANALYTICAL_OUTPUT_COUNT_MISMATCH")
    if any(
        observed_fallback[field] != fallback[field]
        for field in FALLBACK_METRIC_FIELDS
    ):
        refuse("FALLBACK_ANALYTICAL_OUTPUT_COUNT_MISMATCH")
    return {
        **aggregate,
        "intraday_fallback_inventory": observed_fallback[
            "intraday_fallback_rows"
        ],
        "partial_fixed_fallback_inventory": observed_fallback[
            "partial_fixed_fallback_rows"
        ],
        "intraday_fallback_cross_layer": observed_fallback[
            "intraday_fallback_cross_layer_rows"
        ],
        "partial_fixed_fallback_cross_layer": observed_fallback[
            "partial_fixed_fallback_cross_layer_rows"
        ],
        "live_inventory_total": (
            aggregate["inventory"]
            + observed_fallback["intraday_fallback_rows"]
            + observed_fallback["partial_fixed_fallback_rows"]
        ),
        "live_cross_layer_total": (
            aggregate["cross_layer_transitions"]
            + observed_fallback["intraday_fallback_cross_layer_rows"]
            + observed_fallback["partial_fixed_fallback_cross_layer_rows"]
        ),
        "basis": basis_total,
        "valid_basis": valid_basis_total,
    }


def validate_fallback_contract(
    batch_seal: dict[str, Any], expected_sessions: Sequence[str],
) -> dict[str, Any]:
    """Bind live degradation rows to the independently rebuilt batch seal."""
    sessions = batch_seal.get("intraday_fallback_sessions")
    if (
        not isinstance(sessions, list)
        or any(not isinstance(value, str) for value in sessions)
        or sessions != sorted(sessions)
        or len(sessions) != len(set(sessions))
        or not set(sessions).issubset(set(expected_sessions))
        or any(
            type(batch_seal.get(field)) is not int
            or batch_seal[field] < 0
            for field in FALLBACK_METRIC_FIELDS
        )
        or batch_seal.get("intraday_fallback_rows")
        != batch_seal.get("intraday_fallback_cross_layer_rows")
        or batch_seal.get("partial_fixed_fallback_rows")
        != batch_seal.get("partial_fixed_fallback_cross_layer_rows")
        or (
            bool(sessions)
            != bool(
                batch_seal.get("intraday_fallback_rows")
                or batch_seal.get("partial_fixed_fallback_rows")
            )
        )
    ):
        refuse("FALLBACK_SEAL_CONTRACT_INVALID")
    return {
        "sessions": list(sessions),
        **{field: batch_seal[field] for field in FALLBACK_METRIC_FIELDS},
    }


def validate_ledger_identities(
    state_root: Path,
    expected_engine_hash: str,
    expected_configuration_hash: str,
) -> tuple[int, int]:
    """Stream every durable ledger and bind it to the deployed identities."""
    ledger_root = state_root / "ledgers"
    try:
        root_stat = ledger_root.lstat()
    except OSError:
        refuse("STATE_LEDGER_DIRECTORY_MISSING")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        refuse("STATE_LEDGER_DIRECTORY_INVALID")
    try:
        paths = sorted(ledger_root.glob("*.jsonl"))
    except OSError:
        refuse("STATE_LEDGER_DIRECTORY_UNREADABLE")
    names = {path.name for path in paths}
    if not set(REQUIRED_IDENTITY_LEDGERS).issubset(names):
        refuse("REQUIRED_IDENTITY_LEDGER_MISSING")

    required = set(REQUIRED_IDENTITY_LEDGERS)
    total_rows = 0
    nonempty_ledgers = 0
    for path in paths:
        require_plain_file(path, "STATE_LEDGER_UNREADABLE")
        row_count = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        refuse("STATE_LEDGER_BLANK_ROW")
                    try:
                        row = json.loads(line)
                    except (UnicodeError, json.JSONDecodeError):
                        refuse("STATE_LEDGER_INVALID_JSON")
                    if not isinstance(row, dict):
                        refuse("STATE_LEDGER_INVALID_ROW")
                    if row.get("engine_hash") != expected_engine_hash:
                        refuse("STATE_ENGINE_IDENTITY_MISMATCH")
                    if row.get("configuration_hash") != expected_configuration_hash:
                        refuse("STATE_CONFIGURATION_IDENTITY_MISMATCH")
                    row_count += 1
        except OSError:
            refuse("STATE_LEDGER_UNREADABLE")
        if path.name in required and row_count == 0:
            refuse("REQUIRED_IDENTITY_LEDGER_EMPTY")
        if row_count:
            nonempty_ledgers += 1
            total_rows += row_count
    return nonempty_ledgers, total_rows


def _exact_zero(value: Any) -> bool:
    return type(value) is int and value == 0


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _safe_raw_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    relative = Path(value)
    return (
        not relative.is_absolute()
        and value == relative.as_posix()
        and bool(relative.parts)
        and relative.parts[0] in {"raw", "oi"}
        and all(part not in {"", ".", ".."} for part in relative.parts)
    )


def validate_raw_projection_reuse_evidence(
    raw_projection: dict[str, Any],
    projection: dict[str, Any],
) -> None:
    """Bind projection reuse claims to the exact supplied manifest."""
    source_files = projection.get("source_files")
    projection_files = projection.get("projection_files")
    causal_sessions = projection.get("causal_source_sessions")
    selected_outer_records = projection.get("selected_outer_records")
    contracts = projection.get("contract_selection")
    evaluation_sessions = projection.get("evaluation_sessions")
    reused_existing = raw_projection.get("reused_existing")
    if (
        not isinstance(source_files, list)
        or not source_files
        or not isinstance(projection_files, list)
        or not projection_files
        or not isinstance(causal_sessions, list)
        or not causal_sessions
        or not isinstance(evaluation_sessions, list)
        or type(selected_outer_records) is not int
        or selected_outer_records <= 0
        or raw_projection.get("selected_outer_records") != selected_outer_records
        or not isinstance(contracts, dict)
        or type(reused_existing) is not bool
        or not isinstance(projection.get("provenance_sha256"), str)
        or HASH_PATTERN.fullmatch(projection["provenance_sha256"]) is None
    ):
        refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")

    if (
        any(not _valid_iso_date(session) for session in causal_sessions)
        or len(set(causal_sessions)) != len(causal_sessions)
        or causal_sessions != sorted(causal_sessions)
        or any(session not in causal_sessions for session in evaluation_sessions)
        or set(contracts) != set(causal_sessions)
    ):
        refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
    for contract in contracts.values():
        if (
            not isinstance(contract, dict)
            or set(contract) != {
                "futures_expiry",
                "futures_symbol",
                "option_expiry",
                "selection_authority",
            }
            or not isinstance(contract.get("futures_symbol"), str)
            or not contract["futures_symbol"].startswith("NSE:BANKNIFTY")
            or not contract["futures_symbol"].endswith("FUT")
            or any(character.isspace() for character in contract["futures_symbol"])
            or not _valid_iso_date(contract.get("futures_expiry"))
            or not _valid_iso_date(contract.get("option_expiry"))
            or contract.get("selection_authority")
            != "banknifty_profiler.raw_io.reader.select_contracts"
        ):
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")

    source_counts: dict[str, int] = {}
    for row in source_files:
        if not isinstance(row, dict):
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
        relative = row.get("relative_path")
        selected = row.get("selected_json_records")
        if (
            not _safe_raw_relative_path(relative)
            or relative in source_counts
            or type(selected) is not int
            or selected < 0
        ):
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
        source_counts[relative] = selected

    projection_counts: dict[str, int] = {}
    for row in projection_files:
        if not isinstance(row, dict):
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
        relative = row.get("relative_path")
        selected = row.get("selected_json_records")
        byte_count = row.get("bytes")
        physical_rows = row.get("physical_rows")
        digest = row.get("sha256")
        if (
            not _safe_raw_relative_path(relative)
            or relative in projection_counts
            or type(selected) is not int
            or selected <= 0
            or type(byte_count) is not int
            or byte_count <= 0
            or type(physical_rows) is not int
            or physical_rows < selected
            or row.get("ends_with_newline") is not True
            or not isinstance(digest, str)
            or HASH_PATTERN.fullmatch(digest) is None
        ):
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
        projection_counts[relative] = selected

    expected_projection_paths = {
        relative for relative, selected in source_counts.items() if selected > 0
    }
    if (
        sum(source_counts.values()) != selected_outer_records
        or sum(projection_counts.values()) != selected_outer_records
        or set(projection_counts) != expected_projection_paths
        or any(
            projection_counts[relative] != source_counts[relative]
            for relative in projection_counts
        )
    ):
        refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")

    reuse_validation = raw_projection.get("reuse_validation")
    if reused_existing is False:
        if reuse_validation != {}:
            refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
        return

    if (
        not isinstance(reuse_validation, dict)
        or frozenset(reuse_validation) != REUSE_VALIDATION_KEYS
        or reuse_validation.get("status") != "PASS"
        or reuse_validation.get("provenance_verified") is not True
    ):
        refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")
    expected_counts = {
        "authoritative_source_hashes_verified": len(source_files),
        "projection_file_hashes_verified": len(projection_files),
        "provenance_rows_verified": selected_outer_records,
        "dynamic_contract_sessions_verified": len(causal_sessions),
    }
    if any(
        type(reuse_validation.get(field)) is not int
        or reuse_validation.get(field) != expected
        for field, expected in expected_counts.items()
    ):
        refuse("RAW_PROJECTION_REUSE_VALIDATION_FAILED")


def require_expected_authoritative_source_root(value: str) -> str:
    """Require one explicit, normalized absolute source-root identity."""
    if not isinstance(value, str) or not value or "\\" in value:
        refuse("EXPECTED_AUTHORITATIVE_SOURCE_ROOT_INVALID")
    root = Path(value)
    if (
        not root.is_absolute()
        or root.anchor != "/"
        or root == Path(root.anchor)
        or value != root.as_posix()
        or any(part in {"", ".", ".."} for part in root.parts[1:])
    ):
        refuse("EXPECTED_AUTHORITATIVE_SOURCE_ROOT_INVALID")
    return value


def validate_equivalence_evidence(
    summary_path: Path,
    projection_path: Path,
    expected_sessions: Sequence[str],
    expected_authoritative_source_root: str,
) -> tuple[str, str, int, dict[str, Any], dict[str, Any]]:
    """Require the fresh, full six-session PASS and its August 17 policy."""
    expected_source_root = require_expected_authoritative_source_root(
        expected_authoritative_source_root,
    )
    summary = load_json_object(summary_path, "EQUIVALENCE_SUMMARY_INVALID")
    expected = list(expected_sessions)
    if (
        summary.get("status") != "PASS"
        or summary.get("sessions") != expected
        or summary.get("focused_equivalence") is not False
        or summary.get("frozen_count_contract_applicable") is not True
        or summary.get("frozen_count_gate_enforced") is not True
        or summary.get("frozen_count_gate_satisfied") is not True
        or summary.get("references_skipped") is not False
        or summary.get("reference_manifests_verified") is not True
        or summary.get("file_open_audit_measured") is not True
        or type(summary.get("file_open_audit_rows")) is not int
        or summary.get("file_open_audit_rows", 0) <= 0
        or any(not _exact_zero(summary.get(field)) for field in ZERO_EQUIVALENCE_GATES)
    ):
        refuse("EQUIVALENCE_ACCEPTANCE_GATE_FAILED")
    reference_manifests = summary.get("reference_package_manifests")
    if (
        not isinstance(reference_manifests, list)
        or len(reference_manifests) != 2
        or any(
            not isinstance(row, dict) or row.get("status") != "PASS"
            for row in reference_manifests
        )
    ):
        refuse("REFERENCE_MANIFEST_GATE_FAILED")

    incremental = summary.get("incremental_a_seal")
    batch = summary.get("batch_b_seal")
    if (
        not isinstance(incremental, dict)
        or incremental.get("sealed") is not True
        or incremental.get("dirty_sessions_after_seal") != []
        or incremental.get("staged_sessions") != []
        or incremental.get("unexpected_staged_sessions") != []
        or not _exact_zero(incremental.get("analytical_refusals"))
        or not _exact_zero(incremental.get("checkpoint_failures"))
        or not isinstance(batch, dict)
        or batch.get("sealed") is not True
        or not isinstance(batch.get("command_returncodes"), list)
        or not batch["command_returncodes"]
        or any(not _exact_zero(code) for code in batch["command_returncodes"])
    ):
        refuse("EQUIVALENCE_SEAL_GATE_FAILED")
    fallback_contract = validate_fallback_contract(batch, expected_sessions)
    state_seal = {
        "state_manifest_sha256": incremental.get("state_manifest_sha256"),
        "state_tree_sha256": incremental.get("state_tree_sha256"),
        "state_file_count": incremental.get("state_file_count"),
    }
    if (
        not isinstance(state_seal["state_manifest_sha256"], str)
        or HASH_PATTERN.fullmatch(state_seal["state_manifest_sha256"]) is None
        or not isinstance(state_seal["state_tree_sha256"], str)
        or HASH_PATTERN.fullmatch(state_seal["state_tree_sha256"]) is None
        or type(state_seal["state_file_count"]) is not int
        or state_seal["state_file_count"] <= 0
        or summary.get("incremental_a_state_manifest_sha256")
        != state_seal["state_manifest_sha256"]
        or summary.get("incremental_a_state_tree_sha256")
        != state_seal["state_tree_sha256"]
        or summary.get("incremental_a_state_file_count")
        != state_seal["state_file_count"]
    ):
        refuse("INCREMENTAL_STATE_SEAL_GATE_FAILED")
    source_integrity = incremental.get("committed_source_integrity")
    if (
        not isinstance(source_integrity, dict)
        or type(source_integrity.get("source_files")) is not int
        or source_integrity.get("source_files", 0) <= 0
        or type(source_integrity.get("prefix_blocks")) is not int
        or source_integrity.get("prefix_blocks", 0) <= 0
        or summary.get("incremental_a_committed_source_integrity")
        != source_integrity
    ):
        refuse("COMMITTED_SOURCE_INTEGRITY_SEAL_FAILED")

    raw_projection = summary.get("raw_projection")
    if (
        not isinstance(raw_projection, dict)
        or raw_projection.get("used") is not True
        or type(raw_projection.get("reused_existing")) is not bool
        or not _exact_zero(raw_projection.get("source_mutations"))
        or not _exact_zero(raw_projection.get("malformed_candidate_records"))
        or type(raw_projection.get("selected_outer_records")) is not int
        or raw_projection.get("selected_outer_records", 0) <= 0
    ):
        refuse("RAW_PROJECTION_SUMMARY_GATE_FAILED")
    require_plain_file(
        projection_path, "RAW_PROJECTION_MANIFEST_INVALID",
    )
    projection_sha = sha256_file(projection_path)
    if raw_projection.get("manifest_sha256") != projection_sha:
        refuse("RAW_PROJECTION_MANIFEST_HASH_MISMATCH")

    projection = load_json_object(
        projection_path, "RAW_PROJECTION_MANIFEST_INVALID",
    )
    causal_sessions = projection.get("causal_source_sessions")
    if (
        projection.get("schema") != "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1"
        or projection.get("classification") != CLASSIFICATION
        or projection.get("authoritative_source_root") != expected_source_root
        or projection.get("evaluation_sessions") != expected
        or not isinstance(causal_sessions, list)
        or "2026-08-17" not in causal_sessions
        or "2026-08-17" in expected
        or projection.get("august_17_policy") != AUGUST_17_POLICY
        or projection.get("complete_json_records_only") is not True
        or projection.get("selected_records_byte_exact") is not True
        or not _exact_zero(projection.get("source_mutations"))
        or not _exact_zero(projection.get("malformed_candidate_records"))
    ):
        refuse("RAW_PROJECTION_POLICY_GATE_FAILED")
    contracts = projection.get("contract_selection")
    august_contract = (
        contracts.get("2026-08-17") if isinstance(contracts, dict) else None
    )
    if (
        not isinstance(august_contract, dict)
        or not str(august_contract.get("futures_symbol", ""))
        or august_contract.get("selection_authority")
        != "banknifty_profiler.raw_io.reader.select_contracts"
    ):
        refuse("AUGUST_17_REJECTION_POLICY_UNVERIFIED")
    source_files = projection.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        refuse("RAW_PROJECTION_SOURCE_EVIDENCE_MISSING")
    validate_raw_projection_reuse_evidence(raw_projection, projection)
    for row in source_files:
        if (
            not isinstance(row, dict)
            or row.get("unchanged_after_projection") is not True
            or not HASH_PATTERN.fullmatch(str(row.get("sha256_before", "")))
            or row.get("sha256_after") != row.get("sha256_before")
        ):
            refuse("RAW_PROJECTION_SOURCE_MUTATION_EVIDENCE_FAILED")
    return (
        sha256_file(summary_path), projection_sha, len(source_files), state_seal,
        fallback_contract,
    )


def open_read_only_database(path: Path) -> sqlite3.Connection:
    require_plain_file(path, "DATABASE_UNREADABLE")
    try:
        uri = path.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
        return sqlite3.connect(uri, uri=True)
    except (OSError, sqlite3.Error, ValueError):
        refuse("DATABASE_OPEN_FAILED")


def table_names(connection: sqlite3.Connection) -> set[str]:
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    except sqlite3.Error:
        refuse("DATABASE_SCHEMA_UNREADABLE")


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {
            str(row[1])
            for row in connection.execute(f"pragma table_info({table})")
        }
    except sqlite3.Error:
        refuse("DATABASE_SCHEMA_UNREADABLE")


def validate_database(
    connection: sqlite3.Connection,
) -> tuple[int, int, int, int, int]:
    try:
        result = [str(row[0]) for row in connection.execute("pragma quick_check")]
    except sqlite3.Error:
        refuse("DATABASE_QUICK_CHECK_FAILED")
    if result != ["ok"]:
        refuse("DATABASE_QUICK_CHECK_FAILED")

    required_tables = {
        "file_checkpoint", "observation_outbox", "futures_candidate_outbox",
        "futures_selection_probe", "quarantined_source", "file_prefix_block",
        "file_integrity_scrub",
    }
    if not required_tables.issubset(table_names(connection)):
        refuse("DATABASE_REQUIRED_TABLE_MISSING")
    required_columns = {
        "futures_selection_probe": {
            "source_file", "session_date", "start_offset", "probe_offset",
            "identity", "prefix_fingerprint", "mtime_ns_at_probe",
            "replay_target", "bytes_consumed", "inspected_offset",
            "inspected_fingerprint", "size_at_probe", "authority_fingerprint",
        },
        "file_prefix_block": {
            "source_file", "block_index", "byte_count", "digest",
        },
        "file_integrity_scrub": {
            "source_file", "next_block", "updated_at",
        },
    }
    if any(
        not columns.issubset(table_columns(connection, table))
        for table, columns in required_columns.items()
    ):
        refuse("DATABASE_REQUIRED_COLUMN_MISSING")
    try:
        observation_count = int(
            connection.execute("select count(*) from observation_outbox").fetchone()[0]
        )
        candidate_count = int(
            connection.execute("select count(*) from futures_candidate_outbox").fetchone()[0]
        )
        checkpoint_count = int(
            connection.execute("select count(*) from file_checkpoint").fetchone()[0]
        )
        selection_probe_count = int(
            connection.execute("select count(*) from futures_selection_probe").fetchone()[0]
        )
        quarantined_source_count = int(
            connection.execute("select count(*) from quarantined_source").fetchone()[0]
        )
    except (sqlite3.Error, TypeError, ValueError):
        refuse("DATABASE_REQUIRED_TABLE_UNREADABLE")
    if observation_count:
        refuse("OBSERVATION_OUTBOX_NOT_EMPTY")
    if candidate_count:
        refuse("FUTURES_CANDIDATE_OUTBOX_NOT_EMPTY")
    if selection_probe_count:
        refuse("FUTURES_SELECTION_PROBE_NOT_EMPTY")
    if quarantined_source_count:
        refuse("QUARANTINED_SOURCE_NOT_EMPTY")
    return (
        checkpoint_count,
        observation_count,
        candidate_count,
        selection_probe_count,
        quarantined_source_count,
    )


def validate_integrity_inventory(
    connection: sqlite3.Connection,
    checkpoints: dict[str, tuple[Any, ...]],
) -> tuple[int, int]:
    """Validate durable prefix coverage without opening collector source data."""
    try:
        block_rows = connection.execute(
            "select source_file,block_index,byte_count,digest "
            "from file_prefix_block order by source_file,block_index"
        ).fetchall()
        scrub_rows = connection.execute(
            "select source_file,next_block,updated_at "
            "from file_integrity_scrub order by source_file"
        ).fetchall()
    except sqlite3.Error:
        refuse("DATABASE_REQUIRED_TABLE_UNREADABLE")

    by_source: dict[str, list[tuple[Any, Any, Any]]] = {}
    for source_file, block_index, byte_count, digest in block_rows:
        if not isinstance(source_file, str) or source_file not in checkpoints:
            refuse("PREFIX_BLOCK_ORPHAN_SOURCE")
        by_source.setdefault(source_file, []).append(
            (block_index, byte_count, digest)
        )

    block_counts: dict[str, int] = {}
    for source_file, checkpoint in checkpoints.items():
        committed_offset = checkpoint[0]
        if type(committed_offset) is not int or committed_offset < 0:
            refuse("PREFIX_BLOCK_INVENTORY_INVALID")
        expected_count = (
            (committed_offset + INTEGRITY_BLOCK_BYTES - 1)
            // INTEGRITY_BLOCK_BYTES
        )
        block_counts[source_file] = expected_count
        rows = by_source.get(source_file, [])
        if len(rows) != expected_count:
            refuse("PREFIX_BLOCK_INVENTORY_INVALID")
        for expected_index, (block_index, byte_count, digest) in enumerate(rows):
            expected_bytes = min(
                INTEGRITY_BLOCK_BYTES,
                committed_offset - expected_index * INTEGRITY_BLOCK_BYTES,
            )
            if (
                type(block_index) is not int
                or block_index != expected_index
                or type(byte_count) is not int
                or byte_count != expected_bytes
                or not isinstance(digest, str)
                or HASH_PATTERN.fullmatch(digest) is None
            ):
                refuse("PREFIX_BLOCK_INVENTORY_INVALID")

    for source_file, next_block, updated_at in scrub_rows:
        if not isinstance(source_file, str) or source_file not in checkpoints:
            refuse("INTEGRITY_SCRUB_ORPHAN_SOURCE")
        block_count = block_counts[source_file]
        if (
            type(next_block) is not int
            or not 0 <= next_block < block_count
            or not isinstance(updated_at, str)
            or not updated_at
        ):
            refuse("INTEGRITY_SCRUB_BOUNDS_INVALID")
    return len(block_rows), len(scrub_rows)


def canonical_json_checkpoints(value: dict[str, Any]) -> dict[str, tuple[Any, ...]]:
    canonical: dict[str, tuple[Any, ...]] = {}
    required = {
        "offset", "row", "identity", "size_at_commit", "updated_at",
        "prefix_fingerprint", "mtime_ns_at_commit",
    }
    for source_file, checkpoint in value.items():
        if not isinstance(source_file, str) or not isinstance(checkpoint, dict):
            refuse("CHECKPOINT_JSON_INVALID")
        if not required.issubset(checkpoint):
            refuse("CHECKPOINT_JSON_INVALID")
        try:
            canonical[source_file] = (
                int(checkpoint["offset"]),
                int(checkpoint["row"]),
                str(checkpoint["identity"]),
                int(checkpoint["size_at_commit"]),
                str(checkpoint["updated_at"]),
                str(checkpoint["prefix_fingerprint"]),
                int(checkpoint["mtime_ns_at_commit"]),
            )
        except (TypeError, ValueError):
            refuse("CHECKPOINT_JSON_INVALID")
    return canonical


def canonical_sqlite_checkpoints(
    connection: sqlite3.Connection,
) -> dict[str, tuple[Any, ...]]:
    try:
        rows = connection.execute(
            "select source_file,offset,row_number,identity,size_at_commit,"
            "updated_at,prefix_fingerprint,mtime_ns_at_commit "
            "from file_checkpoint"
        ).fetchall()
    except sqlite3.Error:
        refuse("CHECKPOINT_DATABASE_INVALID")
    try:
        return {
            str(row[0]): (
                int(row[1]), int(row[2]), str(row[3]), int(row[4]),
                str(row[5]), str(row[6]), int(row[7]),
            )
            for row in rows
        }
    except (TypeError, ValueError):
        refuse("CHECKPOINT_DATABASE_INVALID")


def validate_hashes(
    engine_manifest: Path,
    expected_engine_manifest_sha256: str,
    expected_engine_hash: str,
    runtime_config: Path,
    expected_runtime_config_sha256: str,
    expected_configuration_hash: str,
) -> tuple[str, str, str, str]:
    expected_engine = require_hash(
        expected_engine_manifest_sha256, "EXPECTED_ENGINE_HASH_INVALID",
    )
    expected_config = require_hash(
        expected_runtime_config_sha256, "EXPECTED_CONFIG_HASH_INVALID",
    )
    expected_engine_identity = require_hash(
        expected_engine_hash, "EXPECTED_ENGINE_IDENTITY_INVALID",
    )
    expected_configuration_identity = require_hash(
        expected_configuration_hash, "EXPECTED_CONFIGURATION_IDENTITY_INVALID",
    )
    require_plain_file(engine_manifest, "ENGINE_MANIFEST_UNREADABLE")
    require_plain_file(runtime_config, "RUNTIME_CONFIG_UNREADABLE")
    actual_engine = sha256_file(engine_manifest)
    actual_config = sha256_file(runtime_config)
    if actual_engine != expected_engine:
        refuse("ENGINE_MANIFEST_HASH_MISMATCH")
    if actual_config != expected_config:
        refuse("RUNTIME_CONFIG_HASH_MISMATCH")

    manifest = load_json_object(engine_manifest, "ENGINE_MANIFEST_INVALID")
    config = load_json_object(runtime_config, "RUNTIME_CONFIG_INVALID")
    if config.get("engine_source_manifest_sha256") != expected_engine:
        refuse("CONFIG_ENGINE_HASH_MISMATCH")
    actual_engine_identity = manifest.get("engine_hash")
    if actual_engine_identity != expected_engine_identity:
        refuse("ENGINE_IDENTITY_MISMATCH")
    canonical_config = (
        json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    actual_configuration_identity = hashlib.sha256(canonical_config).hexdigest()
    if actual_configuration_identity != expected_configuration_identity:
        refuse("CONFIGURATION_IDENTITY_MISMATCH")
    return (
        actual_engine,
        actual_config,
        str(actual_engine_identity),
        actual_configuration_identity,
    )


def validate(args: argparse.Namespace) -> dict[str, Any]:
    state_root = Path(args.state_root)
    state_file_count = validate_state_tree(state_root)
    for relative in REQUIRED_STATE_FILES:
        require_plain_file(state_root / relative, "REQUIRED_STATE_FILE_MISSING")

    engine_sha, config_sha, engine_identity, configuration_identity = validate_hashes(
        Path(args.engine_manifest),
        args.expected_engine_manifest_sha256,
        args.expected_engine_hash,
        Path(args.runtime_config),
        args.expected_runtime_config_sha256,
        args.expected_configuration_hash,
    )
    (
        equivalence_sha,
        projection_sha,
        source_evidence_count,
        state_seal,
        fallback_contract,
    ) = (
        validate_equivalence_evidence(
            Path(args.equivalence_summary),
            Path(args.raw_projection_manifest),
            args.expected_session,
            args.expected_authoritative_source_root,
        )
    )
    state_manifest_sha, state_tree_sha, bound_state_file_count = (
        validate_bound_state_tree(
            state_root,
            Path(args.state_manifest),
            state_seal,
            state_file_count,
        )
    )
    orchestrator = load_json_object(
        state_root / "live_analytical_orchestrator.json",
        "ORCHESTRATOR_STATE_INVALID",
    )
    validate_sessions(orchestrator, args.expected_session)
    identity_ledger_count, identity_ledger_row_count = validate_ledger_identities(
        state_root, engine_identity, configuration_identity,
    )
    checkpoints = load_json_object(
        state_root / "checkpoints.json", "CHECKPOINT_JSON_INVALID",
    )

    connection = open_read_only_database(state_root / "dedup.sqlite3")
    try:
        (
            checkpoint_count,
            observation_count,
            candidate_count,
            selection_probe_count,
            quarantined_source_count,
        ) = validate_database(connection)
        canonical_checkpoints = canonical_json_checkpoints(checkpoints)
        if canonical_checkpoints != canonical_sqlite_checkpoints(connection):
            refuse("CHECKPOINT_JSON_SQLITE_MISMATCH")
        file_prefix_block_count, file_integrity_scrub_count = (
            validate_integrity_inventory(connection, canonical_checkpoints)
        )
    finally:
        connection.close()
    analytical_output_counts = validate_analytical_outputs(
        orchestrator, args.expected_session, fallback_contract,
    )

    return {
        "schema": SCHEMA,
        "ok": True,
        "session_count": EXPECTED_SESSION_COUNT,
        "output_count": EXPECTED_SESSION_COUNT,
        "finalized_session_count": EXPECTED_SESSION_COUNT,
        "dirty_session_count": 0,
        "mutable_session_count": 0,
        "checkpoint_count": checkpoint_count,
        "observation_outbox_count": observation_count,
        "futures_candidate_outbox_count": candidate_count,
        "futures_selection_probe_count": selection_probe_count,
        "quarantined_source_count": quarantined_source_count,
        "file_prefix_block_count": file_prefix_block_count,
        "file_integrity_scrub_count": file_integrity_scrub_count,
        "sqlite_quick_check": "ok",
        "state_file_count": bound_state_file_count,
        "state_manifest_sha256": state_manifest_sha,
        "state_tree_sha256": state_tree_sha,
        "analytical_output_counts": analytical_output_counts,
        "engine_manifest_sha256": engine_sha,
        "runtime_config_sha256": config_sha,
        "engine_hash": engine_identity,
        "configuration_hash": configuration_identity,
        "identity_ledger_count": identity_ledger_count,
        "identity_ledger_row_count": identity_ledger_row_count,
        "equivalence_summary_sha256": equivalence_sha,
        "raw_projection_manifest_sha256": projection_sha,
        "raw_source_evidence_count": source_evidence_count,
        "august_17_policy": AUGUST_17_POLICY,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Validate a staged, finalized six-session R6E1R state preload.",
    )
    value.add_argument("--state-root", required=True)
    value.add_argument(
        "--expected-session", action="append", required=True,
        help="Expected finalized session date; supply exactly six times.",
    )
    value.add_argument("--engine-manifest", required=True)
    value.add_argument("--expected-engine-manifest-sha256", required=True)
    value.add_argument("--expected-engine-hash", required=True)
    value.add_argument("--runtime-config", required=True)
    value.add_argument("--expected-runtime-config-sha256", required=True)
    value.add_argument("--expected-configuration-hash", required=True)
    value.add_argument("--equivalence-summary", required=True)
    value.add_argument("--raw-projection-manifest", required=True)
    value.add_argument("--expected-authoritative-source-root", required=True)
    value.add_argument("--state-manifest", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = validate(parser().parse_args(argv))
    except ValidationError as error:
        result = {"schema": SCHEMA, "ok": False, "error_code": error.code}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    except Exception:
        result = {"schema": SCHEMA, "ok": False, "error_code": "UNEXPECTED_VALIDATION_ERROR"}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
