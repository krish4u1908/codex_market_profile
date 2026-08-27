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
import resource
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO, Iterator

import pandas as pd

from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.shadow.api import _chart as sanitized_chart_projection
from banknifty_profiler.runtime.configuration import canonical_configuration_sha256
from banknifty_profiler.runtime.timestamps import parse_timestamp
from banknifty_profiler.divergence.detector import causal_basis
from banknifty_profiler.context import availability as context_availability
from banknifty_profiler.cross_layer import state as cross_layer_state
from banknifty_profiler.gui import adapter as gui_adapter
from banknifty_profiler.gui.adapter import build_payload as build_gui_payload
from banknifty_profiler.inventory import engine as inventory_engine
from banknifty_profiler.raw_io import reader as raw_reader
from banknifty_profiler.raw_io.reader import load_market


SESSIONS = (
    "2026-08-11",
    "2026-08-12",
    "2026-08-13",
    "2026-08-18",
    "2026-08-19",
    "2026-08-20",
)

AUTHORIZED_FOCUSED_FIXTURE_ROOT: Path | None = None
AUTHORIZED_FOCUSED_MANIFEST_SHA256 = (
    "31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382"
)

EXPECTED_COUNTS = {
    "inventory": 255,
    "divergence_episodes": 65,
    "dependency_groups": 65,
    "green": 41,
    "red": 24,
    "retriggers": 14,
    "lifecycle_transitions": 14_201,
    "dense_resolution_observations": 164_668,
    "response_observations": 65,
    "participation_dense": 69_225,
    "participation_transitions": 32_068,
    "participation_summaries": 65,
    "compatibility_snapshots": 65,
    "cross_layer_transitions": 60_659,
}

STATE_TREE_MANIFEST_SCHEMA = "R6E1R_INCREMENTAL_A_STATE_TREE_MANIFEST_V1"
STATE_TREE_SIDECAR_SUFFIXES = (
    "-journal", "-wal", "-shm", ".journal", ".wal",
)

REFERENCE_PACKAGE_CONTRACTS = {
    "R6C2R_REFERENCE_C": {
        "manifest_sha256": "48a549d55def0f88d05fd527423ae14e37881c8be272e2d8e4d4163a1886dca5",
        "file_count": 74,
        "status": "R6C2R_FULL_STACK_EQUIVALENCE_VERIFIED",
        "tag": "r6c2r-full-stack-equivalence-verified",
    },
    "R6D_GUI": {
        "manifest_sha256": "dcd8314b2c55c569e546b4543b8464b422076a20c623c0ec6fb41277d09616f2",
        "file_count": 40,
        "status": "R6D_OFFLINE_GUI_VERIFIED",
        "tag": "r6d-offline-gui-verified",
    },
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
    # Sessions without the complete fixed-horizon predecessor chain still
    # publish a causal Intraday layer.  The clean batch reference deliberately
    # omits those sessions from canonical_inventory.csv, so the raw-only
    # fallback is compared explicitly instead of being hidden in (or added to)
    # the frozen 255-row canonical inventory count.
    "intraday_inventory": "intraday_inventory",
    "partial_fixed_inventory": "partial_fixed_inventory",
    "intraday_cross_layer_transitions": "intraday_cross_layer_transitions",
    "partial_fixed_cross_layer_transitions": "partial_fixed_cross_layer_transitions",
}

MATERIAL_LEDGER_NAMES = (
    "divergence_confirmations",
    "dependency_retriggers",
    "lifecycle_transitions",
    "inventory_winner_transitions",
    "participation_transitions",
    "cross_layer_transitions",
    "availability_transitions",
    "stale_recovery_transitions",
)
SEMANTIC_CALCULATION_TIMESTAMP_SURFACES = frozenset(
    {"participation_transitions"}
)
# Clean-B independently reconstructs the immutable publication contract. These
# closure annotations remain part of the latest analytical snapshot, but are
# not facts known by the divergence-confirmation or lifecycle-entry event.
BATCH_LEDGER_SNAPSHOT_ONLY_FIELDS = {
    "divergence_confirmations": frozenset({"episode_end_timestamp"}),
    "lifecycle_transitions": frozenset({"state_exit_timestamp"}),
}
LEDGER_ENVELOPE_FIELDS = RUN_VOLATILE_FIELDS | frozenset(
    {"engine_hash", "configuration_hash"}
)

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
    # A raw projection uses blank physical lines to retain repository-native
    # source-row coordinates.  Scheduling counts only complete JSON records;
    # checkpoint accounting continues to count every physical line.
    json_records: int | None = None


@dataclass(frozen=True)
class Schedule:
    name: str
    line_groups: tuple[int, ...]
    split_inside_lines: bool = False
    split_events: int = 0
    empty_polls: int = 0
    empty_poll_events: int = 0
    restart_every: int = 0
    restart_events: int = 0
    restart_on_analytical_transition: bool = False
    original_byte_chunks: bool = False
    analytical_flush_events_per_session: int = 0


def _runtime_library_roots() -> tuple[Path, ...]:
    return tuple(
        path.resolve()
        for path in {
            Path(sys.prefix),
            Path(sys.base_prefix),
            Path(sys.executable).resolve().parent.parent,
            Path("/usr"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc"),
            Path("/proc"),
            Path("/sys"),
            Path("/dev"),
        }
        if path.exists()
    )


def _classify_observed_open(
    requested: Path,
    resolved: Path,
    *,
    data_roots: tuple[Path, ...],
    state_roots: tuple[Path, ...],
    config_paths: tuple[Path, ...],
    repository: Path,
    runtime_roots: tuple[Path, ...],
) -> tuple[str, str]:
    if any(
        requested.is_relative_to(root) or resolved.is_relative_to(root)
        for root in data_roots
    ):
        return "PERMITTED_OBSERVED_RAW_OPEN", "RUNTIME_RAW_OR_CONTEXT_READ"
    if any(
        requested.is_relative_to(root) or resolved.is_relative_to(root)
        for root in state_roots
    ):
        return (
            "PERMITTED_OBSERVED_STATE_OPEN",
            "RUNTIME_CHECKPOINT_LEDGER_OR_GENERATED_STATE_READ",
        )
    if requested.is_relative_to(repository) or resolved.is_relative_to(repository):
        return (
            "PERMITTED_OBSERVED_CODE_CONFIG_PACKAGE_OPEN",
            "RUNTIME_CODE_CONFIG_OR_MANIFEST_READ",
        )
    if requested in config_paths or resolved in config_paths:
        return "PERMITTED_OBSERVED_EXPLICIT_CONFIG_OPEN", "RUNTIME_EXPLICIT_CONFIGURATION_READ"
    if any(
        requested.is_relative_to(root) or resolved.is_relative_to(root)
        for root in runtime_roots
    ):
        return "PERMITTED_OBSERVED_RUNTIME_LIBRARY_OPEN", "RUNTIME_LIBRARY_OR_SYSTEM_READ"
    return (
        "PROHIBITED_OBSERVED_UNCLASSIFIED_EXTERNAL_OPEN",
        "UNAUTHORIZED_OR_UNCLASSIFIED_EXTERNAL_INPUT",
    )


class RuntimeOpenRecorder:
    """Capture actual in-process read opens with a scoped Python audit hook."""

    def __init__(self) -> None:
        self.scope: str | None = None
        self.counts: Counter[tuple[str, str, str]] = Counter()
        self._normalized_paths: dict[tuple[str, str], tuple[str, str]] = {}
        sys.addaudithook(self._audit)

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event != "open" or self.scope is None or not args:
            return
        raw_path = args[0]
        if not isinstance(raw_path, (str, bytes, os.PathLike)):
            return
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else None
        readable = isinstance(mode, str) and mode.startswith("r")
        if mode is None and isinstance(flags, int):
            mutating = flags & (os.O_CREAT | os.O_TRUNC | os.O_EXCL)
            readable = not mutating and flags & os.O_ACCMODE != os.O_WRONLY
        if not readable:
            return
        try:
            decoded = os.fsdecode(raw_path)
            raw = Path(decoded)
            cwd = "" if raw.is_absolute() else os.getcwd()
            cache_key = (cwd, decoded)
            normalized = self._normalized_paths.get(cache_key)
            if normalized is None:
                requested = raw if raw.is_absolute() else Path(cwd) / raw
                requested = requested.absolute()
                resolved = requested.resolve(strict=False)
                normalized = (str(requested), str(resolved))
                self._normalized_paths[cache_key] = normalized
        except (OSError, TypeError, ValueError):
            return
        self.counts[(self.scope, *normalized)] += 1

    @contextmanager
    def recording(self, scope: str) -> Iterator[None]:
        if self.scope is not None:
            raise RuntimeError("runtime open recorder scopes must not overlap")
        self.scope = scope
        try:
            yield
        finally:
            self.scope = None

    def observed_count(self, scope: str, path: Path) -> int:
        requested = str(path.absolute())
        return sum(
            count
            for (label, opened, _), count in self.counts.items()
            if label == scope and opened == requested
        )

    def audit_rows(
        self,
        *,
        scope: str,
        permitted_data_roots: Iterable[Path],
        permitted_state_roots: Iterable[Path],
        permitted_config_paths: Iterable[Path] = (),
        repository: Path,
    ) -> list[dict[str, Any]]:
        data_roots = tuple(path.resolve() for path in permitted_data_roots)
        state_roots = tuple(path.resolve() for path in permitted_state_roots)
        config_paths = tuple(path.resolve() for path in permitted_config_paths)
        repo = repository.resolve()
        runtime_roots = _runtime_library_roots()
        rows = []
        for (label, requested, resolved_text), count in sorted(self.counts.items()):
            if label != scope:
                continue
            resolved = Path(resolved_text)
            requested_path = Path(requested)
            classification, purpose = _classify_observed_open(
                requested_path,
                resolved,
                data_roots=data_roots,
                state_roots=state_roots,
                config_paths=config_paths,
                repository=repo,
                runtime_roots=runtime_roots,
            )
            rows.append(
                {
                    "run": scope,
                    "path": requested,
                    "resolved_path": resolved_text,
                    "purpose": purpose,
                    "classification": classification,
                    "evidence_source": "PYTHON_SYS_AUDIT_HOOK_OPEN",
                    "observed_open_count": count,
                }
            )
        return rows


def required_schedule_open_coverage(
    recorder: RuntimeOpenRecorder,
    *,
    scope: str,
    sources: Iterable[SourceFile],
    context_sources: Iterable[SourceFile],
    staging_root: Path,
) -> list[dict[str, Any]]:
    expected: list[tuple[str, Path]] = []
    for source in sources:
        expected.extend(
            (
                ("HARNESS_BYTE_EXACT_SOURCE_READ", source.source),
                ("INGESTOR_STAGED_LIVE_SOURCE_READ", staging_root / source.relative),
            )
        )
    expected.extend(
        ("FIXED_CONTEXT_STAGED_SOURCE_READ", staging_root / source.relative)
        for source in context_sources
    )
    rows = []
    for purpose, path in expected:
        count = recorder.observed_count(scope, path)
        rows.append(
            {
                "run": scope,
                "path": str(path.absolute()),
                "purpose": purpose,
                "classification": (
                    "PERMITTED_OBSERVED_REQUIRED_SOURCE_OPEN"
                    if count
                    else "UNMEASURED_REQUIRED_SOURCE_OPEN"
                ),
                "evidence_source": "PYTHON_SYS_AUDIT_HOOK_OPEN",
                "observed_open_count": count,
                "required_source_open": True,
                "status": "PASS" if count else "FAIL",
            }
        )
    return rows


SCHEDULES = {
    "original_source_chunks": Schedule(
        "original_source_chunks", (512,), original_byte_chunks=True
    ),
    "one_record_per_increment": Schedule("one_record_per_increment", (1,)),
    "deterministic_variable_chunks": Schedule(
        "deterministic_variable_chunks", (1, 7, 3, 11, 2, 17, 5, 13)
    ),
    "boundaries_inside_jsonl_lines": Schedule(
        "boundaries_inside_jsonl_lines", (8192,),
        split_inside_lines=True, split_events=17,
    ),
    "empty_repeated_polls": Schedule(
        "empty_repeated_polls", (8192,), empty_polls=2, empty_poll_events=17
    ),
    "multiple_checkpoint_restarts": Schedule(
        "multiple_checkpoint_restarts", (8192,), restart_events=7
    ),
    "analytical_boundary_restarts": Schedule(
        "analytical_boundary_restarts", (512,), restart_on_analytical_transition=True
    ),
    "hourly_file_rotation": Schedule("hourly_file_rotation", (257,)),
    "large_chronological_chunks": Schedule(
        "large_chronological_chunks", (8192,),
        analytical_flush_events_per_session=2,
    ),
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
    "large_chronological_chunks",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_reference_package_manifest(
    root: Path,
    *,
    reference_name: str,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify a frozen reference package against a pinned manifest identity."""
    expected = dict(contract or REFERENCE_PACKAGE_CONTRACTS[reference_name])
    package_root = root.resolve()
    manifest_path = package_root / "package_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"{reference_name} package manifest missing: {manifest_path}")
    manifest_sha256 = _sha256_file(manifest_path)
    if manifest_sha256 != expected.get("manifest_sha256"):
        raise ValueError(f"{reference_name} package manifest identity mismatch")
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files")
    expected_count = int(expected["file_count"])
    if (
        not isinstance(files, list)
        or manifest.get("file_count") != expected_count
        or len(files) != expected_count
        or manifest.get("status") != expected.get("status")
        or manifest.get("tag") != expected.get("tag")
        or manifest.get("tag_target") != manifest.get("commit")
    ):
        raise ValueError(f"{reference_name} package manifest contract mismatch")

    seen: set[str] = set()
    for row in files:
        if not isinstance(row, Mapping):
            raise ValueError(f"{reference_name} package manifest row is not an object")
        relative = Path(str(row.get("path", "")))
        target = (package_root / relative).resolve()
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or str(relative) in seen
            or not target.is_relative_to(package_root)
            or not target.is_file()
            or target.stat().st_size != int(row.get("size", -1))
            or _sha256_file(target) != row.get("sha256")
        ):
            raise ValueError(
                f"{reference_name} package file identity mismatch: {relative}"
            )
        seen.add(str(relative))
    return {
        "reference": reference_name,
        "status": "PASS",
        "manifest_sha256": manifest_sha256,
        "verified_files": len(files),
        "tag": manifest["tag"],
        "tag_target": manifest["tag_target"],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _safe_state_relative_path(value: str) -> bool:
    relative = Path(value)
    return bool(
        value
        and "\\" not in value
        and not relative.is_absolute()
        and value == relative.as_posix()
        and all(part not in {"", ".", ".."} for part in relative.parts)
    )


def write_state_tree_manifest(
    state_root: Path, manifest_path: Path,
) -> dict[str, Any]:
    """Seal the exact incremental-A state tree outside the mutable state root."""
    root = state_root.resolve(strict=True)
    destination = manifest_path.resolve(strict=False)
    if destination.is_relative_to(root):
        raise ValueError("state-tree manifest must be outside state")
    root_stat = state_root.lstat()
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("state-tree root is not a plain directory")

    files: list[dict[str, Any]] = []
    for current, directory_names, file_names in os.walk(
        state_root, topdown=True, followlinks=False,
    ):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current)
        for name in directory_names:
            child_stat = (current_path / name).lstat()
            if stat.S_ISLNK(child_stat.st_mode) or not stat.S_ISDIR(child_stat.st_mode):
                raise ValueError("state-tree directory is not plain")
        for name in file_names:
            child = current_path / name
            child_stat = child.lstat()
            relative = child.relative_to(state_root).as_posix()
            if (
                stat.S_ISLNK(child_stat.st_mode)
                or not stat.S_ISREG(child_stat.st_mode)
                or name.lower().endswith(STATE_TREE_SIDECAR_SUFFIXES)
                or not _safe_state_relative_path(relative)
            ):
                raise ValueError("state-tree file is unsafe")
            files.append({
                "path": relative,
                "size": child_stat.st_size,
                "sha256": _sha256_file(child),
            })
    files.sort(key=lambda row: row["path"])
    aggregate = hashlib.sha256()
    for row in files:
        aggregate.update(
            f'{row["path"]}\0{row["sha256"]}\0{row["size"]}\n'.encode()
        )
    manifest = {
        "schema": STATE_TREE_MANIFEST_SCHEMA,
        "classification": (
            "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
        ),
        "file_count": len(files),
        "state_tree_sha256": aggregate.hexdigest(),
        "files": files,
    }
    manifest_path.write_bytes(_json_bytes(manifest))
    return {
        "state_manifest_sha256": _sha256_file(manifest_path),
        "state_tree_sha256": manifest["state_tree_sha256"],
        "state_file_count": manifest["file_count"],
    }


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


class _SealedChartProjectionState:
    """Minimal state marker forcing the API to use only sealed inputs."""

    orchestrator = object()


_SEALED_CHART_STATE = _SealedChartProjectionState()


def _gui_projection(payload: Any) -> dict[str, Any]:
    """Project GUI-visible rows plus operational clocks/display metadata."""
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
    projected = {key: _as_rows(payload.get(key, [])) for key in row_keys}
    availability = _availability_projection(payload.get("availability", []))
    payload_date = payload.get("date")
    if payload_date:
        for row in availability:
            if not row.get("evaluation_date"):
                row["evaluation_date"] = str(payload_date)
    projected["availability"] = availability
    raw_availability = payload.get("availability", {})
    detail = raw_availability if isinstance(raw_availability, Mapping) else {}
    date = str(payload.get("date") or payload.get("session") or "")
    # Exercise the repository's actual sanitized /api/chart projection.  The
    # analytical GUI payload intentionally does not carry public display/as-of
    # fields; inventing defaults here would let an absent API field compare as
    # if it had been published.  Historical A/B uses the sealed availability
    # object as the API derivation input and compares its causal contract.
    chart = sanitized_chart_projection(
        _SEALED_CHART_STATE,
        {"session_date": date, "availability": detail},
        payload,
        detail,
        operational=False,
    )
    chart_availability = chart.get("availability", {})
    if not isinstance(chart_availability, Mapping):
        chart_availability = {}
    reference = str(chart_availability.get("reference_timestamp") or "")
    evidence = str(chart_availability.get("evidence_cutoff_timestamp") or "")
    as_of = str(chart.get("as_of") or "")
    try:
        as_of_not_before_evidence = bool(
            as_of
            and evidence
            and parse_timestamp(as_of, field_name="public chart as-of")
            >= parse_timestamp(evidence, field_name="public chart evidence cutoff")
        )
    except (TypeError, ValueError):
        as_of_not_before_evidence = False
    states = {
        key: chart_availability.get(key)
        for key in (
            "index_state",
            "futures_state",
            "futures_oi_state",
            "ce_state",
            "pe_state",
        )
        if key in chart_availability
    }
    projected["public_contract_metadata"] = [
        {
            "schema": str(payload.get("schema") or ""),
            "classification": str(payload.get("classification") or ""),
            "date": date,
        }
    ]
    projected["classification_metadata"] = [
        {
            "classification": str(payload.get("classification") or ""),
            "date": date,
        }
    ]
    projected["display_metadata"] = [
        {
            "date": str(chart.get("session_date") or date),
            "session_date": str(chart.get("session_date") or ""),
            "as_of_present": bool(as_of),
            "as_of_matches_availability_calculation": (
                as_of == str(chart_availability.get("calculation_timestamp") or "")
            ),
            "as_of_not_before_evidence": as_of_not_before_evidence,
            "as_of_clock_contract": "SANITIZED_CHART_CALCULATION_CLOCK",
            "reference_timestamp": reference,
            "evidence_cutoff_timestamp": evidence,
            "display_state": str(chart.get("display_state") or ""),
            "overall_state": str(chart_availability.get("overall_state") or ""),
            "stale_warning": bool(chart.get("stale_warning")),
            "warning_reason": str(chart.get("warning_reason") or ""),
        }
    ]
    projected["availability_instruments"] = [
        {
            "date": date,
            **states,
            "receipt_ages_seconds": chart.get("receipt_ages_seconds", {}),
        }
    ]
    counts = payload.get("counts", {})
    if isinstance(counts, Mapping):
        aliases = {
            "resolution_dense": "resolution_mechanisms",
            "cross_layer": "cross_layer_transitions",
        }
        normalized_counts = {
            aliases.get(str(key), str(key)): value for key, value in counts.items()
        }
        projected["counts"] = [normalized_counts]
    else:
        projected["counts"] = []
    return projected


def _availability_reason_class(state: object, reason: object, horizon: object) -> object:
    """Compare the same published state across live and sealed-batch wording.

    R6C2 describes predecessor cardinality (``REQUIRES_2...``), while the live
    projection describes the resulting condition (``INSUFFICIENT...``).  The
    state and horizon retain the exact distinction; only those repository-owned
    synonymous reason labels are mapped to a shared audit class.
    """
    state_text = str(state or "")
    reason_text = str(reason or "")
    horizon_text = str(horizon or "")
    if state_text in {"MISSING_PRIOR_SESSION", "INSUFFICIENT_PRIOR_SESSIONS"}:
        return "INSUFFICIENT_PRIOR_SESSIONS"
    if state_text == "AVAILABLE" and horizon_text == "ID" and reason_text in {
        "FRESH_SYNCHRONIZED_MARKET",
        "RAW_CONTINUITY_VERIFIED",
    }:
        return "CAUSAL_INTRADAY_AVAILABLE"
    if state_text == "AVAILABLE" and horizon_text in {"1D", "2D", "3D"} and reason_text in {
        "CACHED_RAW_PRIOR_CONTEXT",
        "RAW_ACCEPTED_SOURCE_CHAIN",
    }:
        return "CAUSAL_FIXED_PROFILE_AVAILABLE"
    return reason


def _availability_state_class(state: object) -> object:
    if str(state or "") in {"MISSING_PRIOR_SESSION", "INSUFFICIENT_PRIOR_SESSIONS"}:
        return "MISSING_PRIOR_SESSION"
    return state


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
                        "availability_state": _availability_state_class(detail.get("state")),
                        "availability_reason": _availability_reason_class(
                            detail.get("state"), detail.get("reason"), horizon
                        ),
                    }
                )
        elif row.get("horizon"):
            state = row.get("availability_state") or row.get("state")
            output.append(
                {
                    **common,
                    "horizon": row.get("horizon"),
                    "availability_state": _availability_state_class(state),
                    "availability_reason": _availability_reason_class(
                        state,
                        row.get("availability_reason") or row.get("reason"),
                        row.get("horizon"),
                    ),
                }
            )
    return output


def _historical_reference_availability_projection(
    snapshot: Mapping[str, Any],
    *,
    mode: str,
) -> list[dict[str, Any]]:
    """Project the frozen R6C2 historical-eligibility availability surface.

    Live R6E availability is an as-of operational contract: a historical
    session can correctly finish ``STALE_DATA`` after its last synchronized
    quote while retaining a usable chart.  R6C2's ``layer_availability.csv``
    is a different, session-level audit surface recording whether each layer
    was materially produced from the accepted raw chain.  Reference C must be
    compared against that historical surface, while primary A/B equivalence
    continues to compare the independently rebuilt operational contract.

    Canonical batch/reference snapshots already carry the flat R6C2 table.
    Incremental A derives the same compatibility view solely from its sealed
    material publications (inventory, synchronized basis and participation),
    never from B or Reference C.
    """
    if mode not in {"incremental", "canonical"}:
        raise ValueError(f"unknown reference availability mode: {mode!r}")
    raw_rows = _as_rows(snapshot.get("availability", []))
    flat_schema = [
        bool(row.get("horizon"))
        and ("availability_state" in row or "state" in row)
        and not isinstance(row.get("layers"), Mapping)
        for row in raw_rows
    ]
    nested_schema = [
        not row.get("horizon") and isinstance(row.get("layers"), Mapping)
        for row in raw_rows
    ]
    if mode == "canonical":
        if not raw_rows or not all(flat_schema):
            raise ValueError(
                "canonical reference availability must be a nonempty uniform flat table"
            )
        return _availability_projection(raw_rows)
    if not raw_rows or not all(nested_schema):
        raise ValueError(
            "incremental reference availability must be a nonempty uniform nested table"
        )

    inventory = [
        *_as_rows(snapshot.get("inventory", [])),
        *_as_rows(snapshot.get("partial_fixed_inventory", [])),
        *_as_rows(snapshot.get("intraday_inventory", [])),
    ]
    basis = _as_rows(snapshot.get("basis", []))
    participation = [
        *_as_rows(snapshot.get("participation_dense", [])),
        *_as_rows(snapshot.get("participation_transitions", [])),
        *_as_rows(snapshot.get("participation_summaries", [])),
    ]
    sessions = sorted(
        {
            date
            for rows in (raw_rows, inventory, basis, participation)
            for row in rows
            if (date := _evaluation_date(row))
        }
    )
    horizons = context_availability.HORIZONS
    output: list[dict[str, Any]] = []
    for session in sessions:
        material_horizons = {
            str(row.get("horizon"))
            for row in inventory
            if _evaluation_date(row) == session
        }
        synchronized_market = any(
            _evaluation_date(row) == session
            and str(row.get("validity_status")) == "VALID"
            for row in basis
        )
        if not synchronized_market:
            # A sealed GUI price row is itself a calculation-free projection
            # of a valid synchronized basis row and is acceptable corroboration
            # for compact unit/reference fixtures.
            payloads = snapshot.get("gui_payload", {})
            payload = payloads.get(session, {}) if isinstance(payloads, Mapping) else {}
            synchronized_market = bool(
                _as_rows(payload.get("price", []))
                if isinstance(payload, Mapping)
                else []
            )
        participation_available = any(
            _evaluation_date(row) == session for row in participation
        )
        layers: dict[str, context_availability.LayerAvailability] = {}
        for horizon in horizons:
            present = (
                horizon in material_horizons
                and (horizon != "ID" or synchronized_market)
            )
            if horizon == "ID":
                state = "AVAILABLE" if present else "STALE_DATA"
                reason = (
                    "RAW_CONTINUITY_VERIFIED"
                    if present
                    else "SYNCHRONIZED_MARKET_OR_INTRADAY_MATERIAL_MISSING"
                )
            else:
                state = "AVAILABLE" if present else "MISSING_PRIOR_SESSION"
                reason = (
                    "RAW_ACCEPTED_SOURCE_CHAIN"
                    if present
                    else f"REQUIRES_{horizon[0]}_PRIOR_ACCEPTED_SESSION(S)"
                )
            layers[horizon] = context_availability.LayerAvailability(
                horizon, state, reason
            )
        classified = context_availability.classify_context(
            layers,
            divergence_inputs_available=synchronized_market,
            participation_inputs_available=participation_available,
        )
        for horizon in horizons:
            layer = layers[horizon]
            output.append(
                {
                    "evaluation_date": session,
                    "horizon": horizon,
                    "availability_state": layer.state,
                    "availability_reason": layer.reason,
                    **classified,
                }
            )
    return _availability_projection(output)


def component_rows(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Project the public orchestrator snapshot into the frozen count contract."""
    result = {}
    for component, key in COMPONENT_KEYS.items():
        value = snapshot.get(key, [])
        if component == "availability_states":
            # Clean B retains the canonical inventory engine's raw eligibility
            # table for audit, but partial-context availability is rebuilt
            # independently from the exact chronological market/OI bytes after
            # the Intraday fallback is added.  Compare that operational public
            # contract, never the pre-fallback eligibility table.
            details = snapshot.get("availability_detail")
            if isinstance(details, Mapping) and details:
                value = [
                    {"session_date": str(session), **dict(detail)}
                    for session, detail in sorted(details.items())
                    if isinstance(detail, Mapping)
                ]
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


def reference_component_rows(
    snapshot: Mapping[str, Any],
    *,
    availability_mode: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return like-for-like historical surfaces for post-seal references."""
    result = component_rows(snapshot)
    if availability_mode is not None:
        result["availability_states"] = (
            _historical_reference_availability_projection(
                snapshot, mode=availability_mode
            )
        )
    return result


def analytical_ledger_rows(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    ledgers = snapshot.get("analytical_ledgers", {})
    if not isinstance(ledgers, Mapping):
        return {}
    return {
        name: [
            {
                key: value
                for key, value in row.items()
                if key not in (
                    LEDGER_ENVELOPE_FIELDS
                    - (
                        {"calculation_timestamp"}
                        if name in SEMANTIC_CALCULATION_TIMESTAMP_SURFACES
                        else set()
                    )
                )
            }
            for row in _as_rows(ledgers.get(name, []))
        ]
        for name in MATERIAL_LEDGER_NAMES
    }


def named_rows_semantic_hash(
    rows_by_surface: Mapping[str, Any],
) -> str:
    """Hash named analytical rows with their field-specific clock contract."""
    projected = {
        str(surface): canonicalize(
            rows,
            volatile_fields=_semantic_volatile_fields(str(surface)),
        )
        for surface, rows in sorted(rows_by_surface.items())
    }
    return _sha256_bytes(_json_bytes(projected))


def _ledger_event_hash(prefix: str, *parts: object) -> str:
    """Independent implementation of the frozen deterministic ledger ID contract."""
    body = "|".join(
        json.dumps(
            _jsonable(part), sort_keys=True, separators=(",", ":"), default=str
        )
        for part in parts
    )
    return prefix + "-" + hashlib.sha256(body.encode()).hexdigest()[:24].upper()


def _batch_availability_states(value: Mapping[str, Any]) -> dict[str, str]:
    result = {
        f"HORIZON_{horizon}": str(item.get("state", ""))
        for horizon, item in value.get("layers", {}).items()
    }
    for key in (
        "divergence_state",
        "participation_state",
        "index_state",
        "futures_state",
        "futures_oi_state",
        "ce_state",
        "pe_state",
        "overall_state",
    ):
        if key in value:
            result[key.upper()] = str(value[key])
    return result


def _batch_material_ledger_projection(
    ledger_name: str, row: Mapping[str, Any]
) -> dict[str, Any]:
    """Independently project a clean snapshot row into an immutable event."""
    value = dict(row)
    for field in BATCH_LEDGER_SNAPSHOT_ONLY_FIELDS.get(
        ledger_name, frozenset()
    ):
        value.pop(field, None)
    return value


def build_batch_analytical_ledgers(snapshot: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Derive expected append-only publications from independent clean-B rows."""
    expected: dict[str, list[dict[str, Any]]] = {
        name: [] for name in MATERIAL_LEDGER_NAMES
    }
    expected["divergence_confirmations"] = [
        {
            **_batch_material_ledger_projection(
                "divergence_confirmations", row
            ),
            "event_id": str(row["episode_id"]),
        }
        for row in _as_rows(snapshot.get("episodes", []))
    ]
    expected["dependency_retriggers"] = [
        {
            **row,
            "event_id": _ledger_event_hash(
                "ANALYTICAL",
                "dependency_retriggers",
                f"dependency:{row['episode_id']}",
            ),
        }
        for row in _as_rows(snapshot.get("dependencies", []))
    ]
    expected["lifecycle_transitions"] = [
        {
            **_batch_material_ledger_projection("lifecycle_transitions", row),
            "event_id": str(row["record_id"]),
        }
        for row in _as_rows(snapshot.get("lifecycle", []))
    ]
    inventory = [
        *_as_rows(snapshot.get("inventory", [])),
        *_as_rows(snapshot.get("partial_fixed_inventory", [])),
        *_as_rows(snapshot.get("intraday_inventory", [])),
    ]
    for row in inventory:
        inner = _ledger_event_hash(
            "INVENTORY",
            row.get("evaluation_date"),
            row.get("horizon"),
            row.get("family"),
            row.get("control_effective_timestamp"),
            float(row["control_value"]),
        )
        expected["inventory_winner_transitions"].append(
            {
                **row,
                "event_id": _ledger_event_hash(
                    "ANALYTICAL", "inventory_winner_transitions", inner
                ),
            }
        )
    expected["participation_transitions"] = [
        {**row, "event_id": str(row["transition_id"])}
        for row in _as_rows(snapshot.get("participation_transitions", []))
    ]
    cross = [
        *_as_rows(snapshot.get("cross_layer_transitions", [])),
        *_as_rows(snapshot.get("partial_fixed_cross_layer_transitions", [])),
        *_as_rows(snapshot.get("intraday_cross_layer_transitions", [])),
    ]
    expected["cross_layer_transitions"] = [
        {**row, "event_id": str(row["transition_id"])} for row in cross
    ]
    details = snapshot.get("availability_detail", {})
    if not isinstance(details, Mapping):
        raise ValueError("clean-B availability detail is missing")
    for session, detail in details.items():
        effective = str(
            detail.get("evidence_cutoff_timestamp")
            or detail.get("reference_timestamp")
            or detail.get("calculation_timestamp")
            or ""
        )
        for component, state in _batch_availability_states(detail).items():
            event = {
                "session_date": str(session),
                "component": component,
                "previous_state": "NOT_YET_AVAILABLE",
                "new_state": state,
                "effective_timestamp": effective,
                "reason": "SESSION_AVAILABILITY_SEAL",
            }
            identity = _ledger_event_hash(
                "AVAILABILITY",
                "SESSION_AVAILABILITY_SEAL",
                session,
                component,
                effective,
                state,
            )
            expected["availability_transitions"].append(
                {
                    **event,
                    "event_id": _ledger_event_hash(
                        "ANALYTICAL", "availability_transitions", identity
                    ),
                }
            )
            if "STALE" in state:
                stale_identity = _ledger_event_hash(
                    "STALE",
                    "SESSION_AVAILABILITY_SEAL",
                    session,
                    component,
                    effective,
                    state,
                )
                expected["stale_recovery_transitions"].append(
                    {
                        **event,
                        "event_id": _ledger_event_hash(
                            "ANALYTICAL",
                            "stale_recovery_transitions",
                            stale_identity,
                        ),
                    }
                )
    return _jsonable(expected)


def compare_analytical_ledgers(
    a_snapshot: Mapping[str, Any], b_snapshot: Mapping[str, Any]
) -> list[dict[str, Any]]:
    a_ledgers = analytical_ledger_rows(a_snapshot)
    b_ledgers = analytical_ledger_rows(b_snapshot)
    rows = []
    for name in MATERIAL_LEDGER_NAMES:
        left_rows = a_ledgers[name]
        right_rows = b_ledgers[name]
        volatile_fields = _semantic_volatile_fields(name)
        left = _row_counter(left_rows, volatile_fields=volatile_fields)
        right = _row_counter(right_rows, volatile_fields=volatile_fields)
        a_only = sum((left - right).values())
        b_only = sum((right - left).values())
        fields = _field_mismatches(
            left_rows, right_rows, volatile_fields=volatile_fields
        )
        remainder = a_only + b_only + fields
        rows.append(
            {
                "ledger": name,
                "incremental_a_count": len(left_rows),
                "batch_b_expected_count": len(right_rows),
                "matched_rows": sum((left & right).values()),
                "a_only": a_only,
                "b_only": b_only,
                "field_mismatches": fields,
                "identity_content_differences": remainder,
                "status": "PASS" if remainder == 0 else "FAIL",
            }
        )
    return rows


def bounded_analytical_ledger_differences(
    canonical_snapshot: Mapping[str, Any],
    schedule_snapshot: Mapping[str, Any],
    *,
    identity_limit: int = 5,
) -> dict[str, Any]:
    """Return a compact, row-content-free ledger failure diagnostic.

    Schedule snapshots can be several gigabytes and are normally removed after
    sealing.  Retain only counts, canonical hashes, deterministic analytical
    identities, and hashes of differing canonical rows so a failed schedule is
    diagnosable without publishing raw observations or dense analytical rows.
    """
    if identity_limit <= 0:
        raise ValueError("identity_limit must be positive")
    canonical_ledgers = analytical_ledger_rows(canonical_snapshot)
    schedule_ledgers = analytical_ledger_rows(schedule_snapshot)
    summaries: list[dict[str, Any]] = []
    total_differences = 0

    def canonical_rows(name: str, rows: Iterable[Mapping[str, Any]]) -> list[str]:
        volatile_fields = _semantic_volatile_fields(name)
        return sorted(
            json.dumps(
                canonicalize(dict(row), volatile_fields=volatile_fields),
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in rows
        )

    def digest(rows: Iterable[str]) -> str:
        payload = "".join(f"{row}\n" for row in rows).encode()
        return hashlib.sha256(payload).hexdigest()

    def bounded_rows(counter: Counter[str]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for content, occurrences in sorted(counter.items()):
            row = json.loads(content)
            event_id = str(row.get("event_id", ""))
            result.append(
                {
                    "event_id": event_id or "IDENTITY_NOT_AVAILABLE",
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "occurrences": int(occurrences),
                }
            )
            if len(result) >= identity_limit:
                break
        return result

    for name in MATERIAL_LEDGER_NAMES:
        canonical = canonical_rows(name, canonical_ledgers[name])
        schedule = canonical_rows(name, schedule_ledgers[name])
        canonical_counter = Counter(canonical)
        schedule_counter = Counter(schedule)
        canonical_only = canonical_counter - schedule_counter
        schedule_only = schedule_counter - canonical_counter
        differences = sum(canonical_only.values()) + sum(schedule_only.values())
        if not differences:
            continue
        total_differences += differences
        summaries.append(
            {
                "ledger": name,
                "canonical_count": len(canonical),
                "schedule_count": len(schedule),
                "canonical_sha256": digest(canonical),
                "schedule_sha256": digest(schedule),
                "canonical_only_count": sum(canonical_only.values()),
                "schedule_only_count": sum(schedule_only.values()),
                "canonical_only": bounded_rows(canonical_only),
                "schedule_only": bounded_rows(schedule_only),
                "identity_limit": identity_limit,
                "truncated": (
                    len(canonical_only) > identity_limit
                    or len(schedule_only) > identity_limit
                ),
            }
        )
    return {
        "schema": "R6E1R_BOUNDED_LEDGER_DIFFERENCE_V1",
        "difference_count": total_differences,
        "differing_ledger_count": len(summaries),
        "ledgers": summaries,
    }


def retain_bounded_ledger_differences(
    run_root: Path,
    canonical_snapshot: Mapping[str, Any],
    schedule_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist bounded diagnostics before an unretained snapshot is removed."""
    summary = bounded_analytical_ledger_differences(
        canonical_snapshot, schedule_snapshot
    )
    if summary["difference_count"]:
        (run_root / "ledger_difference_summary.json").write_bytes(
            _json_bytes(summary)
        )
    return summary


def _semantic_volatile_fields(surface: str) -> frozenset[str]:
    """Retain evidence clocks that are semantic only on their owning surface."""
    if surface in SEMANTIC_CALCULATION_TIMESTAMP_SURFACES:
        return RUN_VOLATILE_FIELDS - {"calculation_timestamp"}
    return RUN_VOLATILE_FIELDS


def _row_counter(
    rows: Iterable[Mapping[str, Any]],
    *,
    volatile_fields: frozenset[str] = RUN_VOLATILE_FIELDS,
) -> Counter[str]:
    return Counter(
        json.dumps(
            canonicalize(dict(row), volatile_fields=volatile_fields),
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in rows
    )


def _identity(
    row: Mapping[str, Any],
    *,
    volatile_fields: frozenset[str] = RUN_VOLATILE_FIELDS,
) -> tuple[tuple[str, str], ...]:
    selected = tuple(
        (
            field,
            json.dumps(
                canonicalize(
                    row[field], volatile_fields=volatile_fields
                ),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for field in IDENTITY_FIELDS
        if field in row and row[field] not in (None, "")
    )
    return selected or ((
        "__row__",
        json.dumps(
            canonicalize(dict(row), volatile_fields=volatile_fields),
            sort_keys=True,
        ),
    ),)


def _field_mismatches(
    a_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
    *,
    volatile_fields: frozenset[str] = RUN_VOLATILE_FIELDS,
) -> int:
    a_by_id: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    b_by_id: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] = {}
    for row in a_rows:
        a_by_id.setdefault(
            _identity(row, volatile_fields=volatile_fields), []
        ).append(canonicalize(row, volatile_fields=volatile_fields))
    for row in b_rows:
        b_by_id.setdefault(
            _identity(row, volatile_fields=volatile_fields), []
        ).append(canonicalize(row, volatile_fields=volatile_fields))
    differences = 0
    for identity in a_by_id.keys() & b_by_id.keys():
        left = sorted(a_by_id[identity], key=lambda row: json.dumps(row, sort_keys=True))
        right = sorted(b_by_id[identity], key=lambda row: json.dumps(row, sort_keys=True))
        for a_row, b_row in zip(left, right, strict=False):
            differences += sum(
                canonicalize(
                    a_row.get(field), volatile_fields=volatile_fields
                )
                != canonicalize(
                    b_row.get(field), volatile_fields=volatile_fields
                )
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
        volatile_fields = _semantic_volatile_fields(name)
        left = _row_counter(a_rows, volatile_fields=volatile_fields)
        right = _row_counter(b_rows, volatile_fields=volatile_fields)
        a_only = sum((left - right).values())
        b_only = sum((right - left).values())
        matched = sum((left & right).values())
        fields = _field_mismatches(
            a_rows, b_rows, volatile_fields=volatile_fields
        )
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
    synchronization_tolerance_violations = 0
    backdating = 0
    nat_timestamps = 0
    for row in _walk_mappings(core):
        row_future_join = False
        row_tolerance_violation = False
        if row.get("future_join") is True or str(row.get("future_join", "")).lower() == "true":
            row_future_join = True
        for key, value in row.items():
            if "join_age" in key:
                try:
                    row_future_join |= float(value) < 0
                except (TypeError, ValueError):
                    pass
            if "timestamp" in key.lower() and str(value) == "NaT":
                nat_timestamps += 1
        index_receipt = _timestamp_value(row.get("index_receipt_timestamp"))
        futures_receipt = _timestamp_value(row.get("futures_receipt_timestamp"))
        if index_receipt is not None and futures_receipt is not None:
            receipt_delta_ms = (futures_receipt - index_receipt) / 1_000_000
            row_future_join |= receipt_delta_ms < 0
            if str(row.get("validity_status", "VALID")) == "VALID":
                row_tolerance_violation |= not 0 <= receipt_delta_ms <= 2_000
        if str(row.get("validity_status", "VALID")) == "VALID":
            for field in ("synchronization_age_ms", "absolute_receipt_difference_ms"):
                if row.get(field) in (None, ""):
                    continue
                try:
                    row_tolerance_violation |= not 0 <= float(row[field]) <= 2_000
                except (TypeError, ValueError):
                    row_tolerance_violation = True
        future_joins += int(row_future_join)
        synchronization_tolerance_violations += int(row_tolerance_violation)
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
        "response_observations": "episode_id",
        "participation_dense": "record_id",
        "participation_transitions": "transition_id",
        "participation_summaries": "episode_id",
        "compatibility_snapshots": "episode_id",
        "cross_layer_transitions": "transition_id",
    }
    for component, field in identity_specs.items():
        values = [str(row[field]) for row in components.get(component, []) if row.get(field)]
        duplicate_ids += len(values) - len(set(values))
    for rows in analytical_ledger_rows(snapshot).values():
        values = [str(row["event_id"]) for row in rows if row.get("event_id")]
        duplicate_ids += len(values) - len(set(values))
    raw_ledgers = snapshot.get("analytical_ledgers", {})
    analytical_refusals = (
        len(_as_rows(raw_ledgers.get("refusals_data_quality", [])))
        if isinstance(raw_ledgers, Mapping)
        else 0
    )
    gui_clock_contract_violations = 0
    gui_display_contract_violations = 0
    gui_path_clock_violations = 0
    gui = snapshot.get("gui_payload", {})
    if isinstance(gui, Mapping):
        for payload in gui.values():
            projected = _gui_projection(payload)
            for metadata in projected.get("display_metadata", []):
                evidence = _timestamp_value(metadata.get("evidence_cutoff_timestamp"))
                reference = _timestamp_value(metadata.get("reference_timestamp"))
                if evidence is not None and (
                    not metadata.get("as_of_present")
                    or not metadata.get("as_of_matches_availability_calculation")
                    or not metadata.get("as_of_not_before_evidence")
                    or reference is None
                    or reference < evidence
                ):
                    gui_clock_contract_violations += 1
                stale = metadata.get("stale_warning") is True
                display = str(metadata.get("display_state", ""))
                warning = str(metadata.get("warning_reason", ""))
                if (
                    stale
                    and (
                        display != "LAST_VALID_CHART_WITH_STALE_WARNING"
                        or warning != "STALE_DATA"
                    )
                ) or (
                    not stale
                    and (
                        display != "CURRENT_OR_REPLAY_PROJECTION" or warning
                    )
                ):
                    gui_display_contract_violations += 1
            for row in projected.get("price", []):
                index_receipt = _timestamp_value(row.get("it"))
                futures_receipt = _timestamp_value(row.get("ft"))
                if index_receipt is None or futures_receipt is None:
                    continue
                delta_ms = (futures_receipt - index_receipt) / 1_000_000
                if not 0 <= delta_ms <= 2_000:
                    gui_path_clock_violations += 1
    return {
        "future_joins": int(future_joins),
        "synchronization_tolerance_violations": synchronization_tolerance_violations,
        "timestamp_backdating": backdating,
        "duplicate_analytical_ids": duplicate_ids,
        "valid_timestamps_becoming_nat": nat_timestamps,
        "analytical_refusals": analytical_refusals,
        "gui_clock_contract_violations": gui_clock_contract_violations,
        "gui_display_contract_violations": gui_display_contract_violations,
        "gui_path_clock_violations": gui_path_clock_violations,
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


def _required_source_dates(data_root: Path, sessions: Iterable[str]) -> list[str]:
    requested = tuple(sorted(set(sessions)))
    if not requested:
        raise ValueError("at least one evaluation session is required")
    available = sorted(
        {path.name for path in (data_root / "raw").iterdir() if path.is_dir()}
        & {path.name for path in (data_root / "oi").iterdir() if path.is_dir()}
    )
    missing = [session for session in requested if session not in available]
    if missing:
        raise ValueError(f"required physical sessions missing: {missing}")
    # This is the frozen R6C0I discovery boundary.  It provides the accepted
    # predecessor chain for the first inventory evaluation date while keeping
    # 2026-08-17 present so its canonical rejection is exercised.
    discovery_start = "2026-08-10" if set(requested).issubset(set(SESSIONS)) else requested[0]
    return [
        date
        for date in available
        if discovery_start <= date <= requested[-1]
    ]


def _safe_fixture_path(root: Path, relative_text: object) -> Path:
    relative = Path(str(relative_text))
    target = (root / relative).resolve()
    if (
        not relative.parts
        or relative.is_absolute()
        or ".." in relative.parts
        or not target.is_relative_to(root.resolve())
    ):
        raise ValueError("authorized focused fixture contains an unsafe path")
    return target


def _validate_focused_fixture_manifest(
    root: Path, *, expected_manifest_sha256: str
) -> None:
    """Cryptographically validate the authorized source-hour projection."""
    fixture_root = root.parent
    manifest_path = fixture_root / "manifest.json"
    checksum_path = fixture_root / "manifest.sha256"
    if (
        not manifest_path.is_file()
        or not checksum_path.is_file()
        or _sha256_file(manifest_path) != expected_manifest_sha256
        or checksum_path.read_text(encoding="ascii")
        != f"{expected_manifest_sha256}  manifest.json\n"
    ):
        raise ValueError("authorized focused fixture manifest identity mismatch")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("schema") != "R6E1R_FOCUSED_SAMPLE_V2"
        or
        manifest.get("fixture") != "r6e1r0_aug19_0915_1205"
        or manifest.get("collector_root") != "collector"
        or manifest.get("session_date") != "2026-08-19"
        or manifest.get("complete_json_lines_only") is not True
        or manifest.get("complete_json_records_only") is not True
        or manifest.get("selected_records_byte_exact") is not True
        or manifest.get("incomplete_final_lines_excluded") is not True
        or manifest.get("source_mutations") != 0
        or manifest.get("canonical_symbols", {}).get("index") != "NSE:NIFTYBANK-INDEX"
        or manifest.get("contract_selection", {}).get("authority")
        != "banknifty_profiler.raw_io.reader.load_oi+select_contracts"
        or manifest.get("window", {}).get("timezone") != "Asia/Kolkata"
        or manifest.get("window", {}).get("start_inclusive")
        != "2026-08-19T09:15:00+05:30"
        or manifest.get("window", {}).get("end_exclusive")
        != "2026-08-19T12:05:00+05:30"
    ):
        raise ValueError("authorized focused fixture contract mismatch")

    source_rows = manifest.get("source_files")
    collector_rows = manifest.get("collector_files")
    identities = manifest.get("selected_records")
    if (
        not isinstance(source_rows, list)
        or not isinstance(collector_rows, list)
        or not isinstance(identities, list)
        or len(source_rows) != 8
        or len(collector_rows) != 8
        or manifest.get("collector_file_count") != 8
        or len(identities) != manifest.get("selected_outer_records")
    ):
        raise ValueError("authorized focused fixture inventory mismatch")

    source_paths: dict[str, Path] = {}
    for source in source_rows:
        path = Path(str(source.get("path", ""))).resolve()
        relative = str(source.get("relative_path", ""))
        stat = path.stat() if path.is_file() else None
        if (
            stat is None
            or path.is_symlink()
            or relative in source_paths
            or stat.st_dev != int(source.get("device", -1))
            or stat.st_ino != int(source.get("inode", -1))
            or stat.st_size != int(source.get("bytes_before", -1))
            or stat.st_size != int(source.get("bytes_after", -2))
            or stat.st_mtime_ns != int(source.get("mtime_ns_before", -1))
            or stat.st_mtime_ns != int(source.get("mtime_ns_after", -2))
            or source.get("unchanged") is not True
            or not (
                source.get("sha256_before")
                == source.get("sha256_during_extraction")
                == source.get("sha256_after")
                == source.get("sha256")
                == _sha256_file(path)
            )
        ):
            raise ValueError(f"authorized focused fixture source identity mismatch: {path}")
        source_paths[relative] = path

    collector_paths: dict[str, Path] = {}
    expected_collector_files: set[str] = set()
    for row in collector_rows:
        relative = str(row.get("relative_path", ""))
        path = _safe_fixture_path(root, relative)
        if (
            relative in collector_paths
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != int(row.get("bytes", -1))
            or _sha256_file(path) != row.get("sha256")
            or row.get("ends_with_newline") is not True
        ):
            raise ValueError(
                f"authorized focused fixture collector identity mismatch: {relative}"
            )
        collector_paths[relative] = path
        expected_collector_files.add(relative)
    observed_collector_files = {
        str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
    }
    if observed_collector_files != expected_collector_files or any(
        path.is_symlink() for path in root.rglob("*")
    ):
        raise ValueError("authorized focused fixture file set mismatch")

    archive_paths: dict[str, Path] = {}
    for stream in ("raw", "oi"):
        archive = manifest.get("compatibility_archives", {}).get(stream, {})
        path = _safe_fixture_path(fixture_root, archive.get("relative_path", ""))
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != int(archive.get("bytes", -1))
            or archive.get("sha256")
            != manifest.get("extracted_sha256", {}).get(stream)
            or _sha256_file(path) != archive.get("sha256")
            or archive.get("ends_with_newline") is not True
        ):
            raise ValueError(
                f"authorized focused fixture compatibility identity mismatch: {stream}"
            )
        archive_paths[stream] = path

    identity_file = manifest.get("selected_record_identity_file", {})
    identity_path = _safe_fixture_path(
        fixture_root, identity_file.get("relative_path", "")
    )
    if (
        not identity_path.is_file()
        or identity_path.is_symlink()
        or int(identity_file.get("rows", -1)) != len(identities)
        or _sha256_file(identity_path) != identity_file.get("sha256")
        or sum(1 for _ in identity_path.open("rb")) != len(identities)
    ):
        raise ValueError("authorized focused fixture identity ledger mismatch")

    source_handles = {name: path.open("rb") for name, path in source_paths.items()}
    collector_handles = {
        name: path.open("rb") for name, path in collector_paths.items()
    }
    archive_handles = {name: path.open("rb") for name, path in archive_paths.items()}
    try:
        for identity in identities:
            relative = str(identity.get("source_relative_path", ""))
            projection_relative = str(identity.get("projection_relative_path", ""))
            stream = str(identity.get("source_stream", ""))
            if (
                relative not in source_handles
                or projection_relative != relative
                or projection_relative not in collector_handles
                or stream not in archive_handles
                or Path(str(identity.get("source_path", ""))).resolve()
                != source_paths[relative]
            ):
                raise ValueError("authorized focused fixture record path mismatch")
            source_handle = source_handles[relative]
            source_handle.seek(int(identity["source_byte_offset"]))
            value = source_handle.read(int(identity["source_byte_length"]))
            if (
                not value.endswith(b"\n")
                or _sha256_bytes(value) != identity["record_sha256"]
            ):
                raise ValueError("authorized focused fixture source record identity mismatch")
            collector_handle = collector_handles[projection_relative]
            collector_handle.seek(int(identity["projection_byte_offset"]))
            if collector_handle.read(len(value)) != value:
                raise ValueError(
                    "authorized focused fixture projection record identity mismatch"
                )
            archive_handle = archive_handles[stream]
            archive_handle.seek(int(identity["output_byte_offset"]))
            if archive_handle.read(len(value)) != value:
                raise ValueError(
                    "authorized focused fixture compatibility record identity mismatch"
                )
    finally:
        for handle in (
            *source_handles.values(),
            *collector_handles.values(),
            *archive_handles.values(),
        ):
            handle.close()


def _validate_authorized_focused_fixture(root: Path) -> None:
    """Validate the one explicitly authorized research-hosted raw fixture."""
    if AUTHORIZED_FOCUSED_FIXTURE_ROOT is None:
        raise ValueError("research-derived analytical input root is prohibited")
    expected_root = AUTHORIZED_FOCUSED_FIXTURE_ROOT.resolve()
    if root != expected_root:
        raise ValueError("research-derived analytical input root is prohibited")
    _validate_focused_fixture_manifest(
        root, expected_manifest_sha256=AUTHORIZED_FOCUSED_MANIFEST_SHA256
    )


def _projection_classes(
    record: Mapping[str, Any], stream: str, selected_futures: str
) -> Counter[str]:
    classes: Counter[str] = Counter()
    if stream == "raw":
        symbol = (record.get("message") or {}).get("symbol")
        if symbol == "NSE:NIFTYBANK-INDEX":
            classes["index"] = 1
        elif symbol == selected_futures:
            classes["futures"] = 1
        return classes
    source = record.get("source")
    if source == "future_depth":
        payload = ((record.get("response") or {}).get("d") or {}).get(selected_futures)
        if isinstance(payload, Mapping) and payload.get("oi") not in (None, ""):
            classes["futures_oi"] = 1
        return classes
    if source != "option_chain":
        return classes
    chain = (((record.get("response") or {}).get("data") or {}).get("optionsChain") or [])
    for item in chain:
        symbol = str(item.get("symbol", ""))
        parsed_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else ""
        option_type = str(item.get("option_type") or parsed_type).upper()
        if symbol.startswith("NSE:BANKNIFTY") and symbol.endswith("CE") and option_type == "CE":
            classes["ce"] += 1
        elif symbol.startswith("NSE:BANKNIFTY") and symbol.endswith("PE") and option_type == "PE":
            classes["pe"] += 1
    # A complete option-chain outer record is retained as a unit.  Keeping
    # only one side would change canonical moneyness/participation context.
    return classes if classes["ce"] and classes["pe"] else Counter()


def build_raw_projection(
    *, data_root: Path, projection_root: Path, sessions: tuple[str, ...]
) -> dict[str, Any]:
    """Build a bounded-memory, byte-exact canonical raw-record projection.

    Selected JSON records are copied byte-for-byte.  Excluded physical rows are
    represented by blank JSONL lines before the next selected record, which
    preserves every selected record's repository-native ``source_row`` without
    making schedules poll irrelevant symbols.  Trailing excluded rows are not
    materialized because they cannot affect a selected source coordinate.
    """
    begun = time.monotonic()
    source_root = data_root.resolve()
    if not source_root.is_dir() or "research" in source_root.parts:
        raise ValueError("authoritative projection input must be a physical non-research root")
    if not all((source_root / stream).is_dir() for stream in ("raw", "oi")):
        raise ValueError("authoritative projection input is missing raw/oi")
    target = projection_root.resolve()
    if target.exists():
        raise ValueError("raw projection root must not exist")
    collector = target / "collector"
    collector.mkdir(parents=True)
    dates = _required_source_dates(source_root, sessions)
    contracts: dict[str, str] = {}
    contract_details: dict[str, dict[str, Any]] = {}
    for session in dates:
        source_oi = raw_reader.load_oi(source_root / "oi", session)
        futures, futures_expiry, option_expiry = raw_reader.select_contracts(source_oi, session)
        if not futures:
            raise ValueError(f"repository contract discovery failed for {session}")
        contracts[session] = futures
        contract_details[session] = {
            "futures_symbol": futures,
            "futures_expiry": str(futures_expiry or ""),
            "option_expiry": str(option_expiry or ""),
            "selection_authority": "banknifty_profiler.raw_io.reader.select_contracts",
        }

    source_paths = [
        path
        for stream, pattern in (("raw", "events_*.jsonl"), ("oi", "oi_*.jsonl"))
        for session in dates
        for path in sorted((source_root / stream / session).glob(pattern))
    ]
    if not source_paths:
        raise ValueError("raw projection found no physical JSONL sources")
    provenance_path = target / "raw_projection_provenance.jsonl"
    source_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    selected_outer_records = 0
    malformed_candidates = 0
    receipt_path_session_mismatches = 0
    with provenance_path.open("wb") as provenance:
        for source_path in source_paths:
            relative = source_path.relative_to(source_root)
            stream, session = relative.parts[:2]
            selected_futures = contracts[session]
            before = source_path.stat()
            source_digest = hashlib.sha256()
            output_digest = hashlib.sha256()
            output_handle: BinaryIO | None = None
            destination = collector / relative
            source_row = 0
            source_offset = 0
            selected_count = 0
            pending_blank_rows = 0
            projected_bytes = 0
            projected_physical_rows = 0
            incomplete_tail_bytes = 0
            try:
                with source_path.open("rb") as source_handle:
                    for line in source_handle:
                        current_offset = source_offset
                        source_offset += len(line)
                        source_digest.update(line)
                        if not line.endswith(b"\n"):
                            incomplete_tail_bytes += len(line)
                            continue
                        source_row += 1
                        marker = (
                            b"NIFTYBANK-INDEX" in line
                            or selected_futures.encode() in line
                            or stream == "oi"
                        )
                        classes: Counter[str] = Counter()
                        record: Mapping[str, Any] | None = None
                        if marker:
                            try:
                                record = json.loads(line)
                                classes = _projection_classes(record, stream, selected_futures)
                            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                                malformed_candidates += 1
                        if not classes:
                            pending_blank_rows += 1
                            continue
                        receipt = record.get("received_at") if record is not None else None
                        parsed_receipt = parse_timestamp(
                            receipt, field_name="raw projection receipt timestamp"
                        )
                        if parsed_receipt.date().isoformat() != session:
                            # Preserve late collector snapshots byte-for-byte.
                            # Their path session remains canonical batch lineage;
                            # the live path retains the actual receipt clock and
                            # must never rewrite or backdate it.
                            receipt_path_session_mismatches += 1
                        if output_handle is None:
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            output_handle = destination.open("wb")
                        blanks = b"\n" * pending_blank_rows
                        if blanks:
                            output_handle.write(blanks)
                            output_digest.update(blanks)
                        projected_bytes += len(blanks)
                        projected_physical_rows += pending_blank_rows
                        output_byte_offset = projected_bytes
                        output_handle.write(line)
                        output_digest.update(line)
                        projected_bytes += len(line)
                        projected_physical_rows += 1
                        pending_blank_rows = 0
                        selected_count += 1
                        selected_outer_records += 1
                        class_counts.update(classes)
                        identity = {
                            "source_path": str(source_path),
                            "source_relative_path": str(relative),
                            "source_stream": stream,
                            "source_row": source_row,
                            "source_byte_offset": current_offset,
                            "source_byte_length": len(line),
                            "record_sha256": _sha256_bytes(line),
                            "receipt_timestamp": parsed_receipt.isoformat(),
                            "selected_futures_symbol": selected_futures,
                            "instrument_counts": dict(sorted(classes.items())),
                            "projection_relative_path": str(relative),
                            "projection_row": projected_physical_rows,
                            "projection_byte_offset": output_byte_offset,
                        }
                        provenance.write(_json_bytes(identity))
            finally:
                if output_handle is not None:
                    output_handle.flush()
                    os.fsync(output_handle.fileno())
                    output_handle.close()
            after_read = source_path.stat()
            source_rows.append(
                {
                    "path": str(source_path),
                    "relative_path": str(relative),
                    "bytes_before": before.st_size,
                    "mtime_ns_before": before.st_mtime_ns,
                    "sha256_before": source_digest.hexdigest(),
                    "bytes_after_read": after_read.st_size,
                    "mtime_ns_after_read": after_read.st_mtime_ns,
                    "complete_physical_rows": source_row,
                    "incomplete_final_bytes_excluded": incomplete_tail_bytes,
                    "selected_json_records": selected_count,
                    "unchanged_during_read": (
                        before.st_size == after_read.st_size
                        and before.st_mtime_ns == after_read.st_mtime_ns
                    ),
                }
            )
            if selected_count:
                output_rows.append(
                    {
                        "relative_path": str(relative),
                        "bytes": projected_bytes,
                        "physical_rows": projected_physical_rows,
                        "selected_json_records": selected_count,
                        "sha256": output_digest.hexdigest(),
                        "ends_with_newline": True,
                    }
                )
        provenance.flush()
        os.fsync(provenance.fileno())

    source_mutations = 0
    for row in source_rows:
        source_path = Path(row["path"])
        after = source_path.stat()
        row["bytes_after"] = after.st_size
        row["mtime_ns_after"] = after.st_mtime_ns
        row["sha256_after"] = _sha256_file(source_path)
        row["unchanged_after_projection"] = (
            row["bytes_before"] == row["bytes_after"]
            and row["mtime_ns_before"] == row["mtime_ns_after"]
            and row["sha256_before"] == row["sha256_after"]
            and row["unchanged_during_read"]
        )
        source_mutations += int(not row["unchanged_after_projection"])
    if source_mutations:
        raise ValueError(f"authoritative sources changed during raw projection: {source_mutations}")
    if malformed_candidates:
        raise ValueError(
            "raw projection refused malformed candidate JSON records: "
            f"{malformed_candidates}"
        )

    manifest = {
        "schema": "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1",
        "classification": "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL",
        "authoritative_source_root": str(source_root),
        "collector_root": str(collector),
        "evaluation_sessions": list(sessions),
        "causal_source_sessions": dates,
        "august_17_policy": "PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED",
        "contract_selection": contract_details,
        "complete_json_records_only": True,
        "selected_records_byte_exact": True,
        "excluded_rows_represented_as_blank_jsonl_for_source_row_preservation": True,
        "selected_outer_records": selected_outer_records,
        "instrument_counts": dict(sorted(class_counts.items())),
        "malformed_candidate_records": malformed_candidates,
        "receipt_path_session_mismatches": receipt_path_session_mismatches,
        "source_mutations": source_mutations,
        "source_files": source_rows,
        "projection_files": output_rows,
        "provenance_path": str(provenance_path),
        "provenance_sha256": _sha256_file(provenance_path),
        "elapsed_seconds": time.monotonic() - begun,
        "peak_rss_kib_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    manifest_path = target / "projection_manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    manifest["manifest_path"] = str(manifest_path)
    manifest["manifest_sha256"] = _sha256_file(manifest_path)
    return manifest


def validate_existing_raw_projection(
    *, manifest_path: Path, data_root: Path, sessions: tuple[str, ...]
) -> dict[str, Any]:
    """Fully validate a prior raw projection before allowing A/B reuse."""
    path = manifest_path.resolve()
    if not path.is_file():
        raise ValueError(f"raw projection manifest missing: {path}")
    manifest = json.loads(path.read_text())
    authoritative = data_root.resolve()
    collector = Path(str(manifest.get("collector_root", ""))).resolve()
    provenance = Path(str(manifest.get("provenance_path", ""))).resolve()
    if (
        manifest.get("schema") != "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1"
        or manifest.get("complete_json_records_only") is not True
        or manifest.get("selected_records_byte_exact") is not True
        or manifest.get("malformed_candidate_records") != 0
        or manifest.get("source_mutations") != 0
        or tuple(manifest.get("evaluation_sessions", ())) != sessions
        or Path(str(manifest.get("authoritative_source_root", ""))).resolve()
        != authoritative
        or manifest.get("august_17_policy")
        != "PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED"
    ):
        raise ValueError("existing raw projection manifest contract mismatch")
    if (
        not authoritative.is_dir()
        or "research" in authoritative.parts
        or not collector.is_dir()
        or "research" in collector.parts
    ):
        raise ValueError("existing projection roots are not permitted physical roots")
    if not provenance.is_file() or _sha256_file(provenance) != manifest.get(
        "provenance_sha256"
    ):
        raise ValueError("existing raw projection provenance identity mismatch")
    provenance_rows, provenance_newline = _count_lines(provenance)
    if (
        not provenance_newline
        or provenance_rows != int(manifest.get("selected_outer_records", -1))
    ):
        raise ValueError("existing raw projection provenance row-count mismatch")

    source_rows = list(manifest.get("source_files", []))
    if not source_rows or not manifest.get("projection_files"):
        raise ValueError("existing raw projection inventory is empty")
    for source in source_rows:
        source_path = Path(str(source.get("path", ""))).resolve()
        expected_path = (
            authoritative / str(source.get("relative_path", ""))
        ).resolve()
        if (
            not source_path.is_file()
            or not source_path.is_relative_to(authoritative)
            or source_path != expected_path
            or source.get("unchanged_after_projection") is not True
            or source.get("sha256_after") != source.get("sha256_before")
        ):
            raise ValueError(f"projection authoritative source refused: {source_path}")
        stat = source_path.stat()
        if (
            stat.st_size != int(source.get("bytes_before", -1))
            or stat.st_mtime_ns != int(source.get("mtime_ns_before", -1))
            or _sha256_file(source_path) != source.get("sha256_before")
        ):
            raise ValueError(f"projection authoritative source changed: {source_path}")
    selected_records = 0
    for projected in manifest.get("projection_files", []):
        relative = Path(str(projected.get("relative_path", "")))
        projection_path = (collector / relative).resolve()
        if (
            not relative.parts
            or relative.parts[0] not in {"raw", "oi"}
            or ".." in relative.parts
            or relative.is_absolute()
            or not projection_path.is_file()
            or not projection_path.is_relative_to(collector)
            or projection_path.stat().st_size != int(projected.get("bytes", -1))
            or _sha256_file(projection_path) != projected.get("sha256")
        ):
            raise ValueError(f"existing raw projection file changed: {projection_path}")
        selected_records += int(projected.get("selected_json_records", 0))
    if selected_records != int(manifest.get("selected_outer_records", -1)):
        raise ValueError("existing raw projection selected-record count mismatch")

    contracts = manifest.get("contract_selection", {})
    causal_sessions = tuple(manifest.get("causal_source_sessions", ()))
    if sessions == SESSIONS and "2026-08-17" not in causal_sessions:
        raise ValueError("existing raw projection lost required August 17 rejection input")
    for session in causal_sessions:
        oi = raw_reader.load_oi(authoritative / "oi", str(session))
        futures, futures_expiry, option_expiry = raw_reader.select_contracts(
            oi, str(session)
        )
        recorded = contracts.get(str(session), {})
        if (
            futures != recorded.get("futures_symbol")
            or str(futures_expiry or "") != str(recorded.get("futures_expiry", ""))
            or str(option_expiry or "") != str(recorded.get("option_expiry", ""))
        ):
            raise ValueError(
                f"existing projection dynamic contract selection changed: {session}"
            )
    manifest["manifest_path"] = str(path)
    manifest["manifest_sha256"] = _sha256_file(path)
    manifest["reuse_validation"] = {
        "status": "PASS",
        "authoritative_source_hashes_verified": len(source_rows),
        "projection_file_hashes_verified": len(manifest.get("projection_files", [])),
        "provenance_verified": True,
        "provenance_rows_verified": provenance_rows,
        "dynamic_contract_sessions_verified": len(causal_sessions),
    }
    return manifest


def discover_sources(
    data_root: Path,
    sessions: Iterable[str],
    *,
    include_predecessors: bool = True,
) -> list[SourceFile]:
    """Discover physical JSONL only; derived/reference input roots are refused."""
    root = data_root.resolve()
    if not root.is_dir():
        raise ValueError(f"physical data root missing: {root}")
    if "research" in root.parts:
        _validate_authorized_focused_fixture(root)
    missing_streams = [stream for stream in ("raw", "oi") if not (root / stream).is_dir()]
    if missing_streams:
        raise ValueError(f"physical stream roots missing: {missing_streams}")
    requested = tuple(sorted(set(sessions)))
    dates = (
        _required_source_dates(root, requested)
        if include_predecessors
        else list(requested)
    )
    if not include_predecessors:
        missing = [
            session
            for session in dates
            if not (root / "raw" / session).is_dir()
            or not (root / "oi" / session).is_dir()
        ]
        if missing:
            raise ValueError(f"required physical sessions missing: {missing}")
    projection_details: dict[str, Mapping[str, Any]] = {}
    projection_manifest = root.parent / "projection_manifest.json"
    if projection_manifest.is_file():
        projected = json.loads(projection_manifest.read_text())
        if (
            projected.get("schema") != "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1"
            or Path(projected.get("collector_root", "")).resolve() != root
            or projected.get("source_mutations") != 0
        ):
            raise ValueError("raw projection manifest contract mismatch")
        projection_details = {
            str(row["relative_path"]): row
            for row in projected.get("projection_files", [])
        }
    found: list[SourceFile] = []
    for stream, prefix in (("raw", "events_*.jsonl"), ("oi", "oi_*.jsonl")):
        for date in dates:
            for path in sorted((root / stream / date).glob(prefix)):
                rows, newline = _count_lines(path)
                json_records = None
                detail = projection_details.get(str(path.relative_to(root)))
                if detail is not None:
                    if (
                        path.stat().st_size != int(detail["bytes"])
                        or rows != int(detail["physical_rows"])
                        or newline is not True
                        or _sha256_file(path) != detail["sha256"]
                    ):
                        raise ValueError(f"raw projection file identity mismatch: {path}")
                    json_records = int(detail["selected_json_records"])
                found.append(
                    SourceFile(
                        path.resolve(), path.relative_to(root), path.stat().st_size,
                        rows, newline, json_records,
                    )
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


def _next_json_record_chunk(handle: BinaryIO, physical_row: int) -> tuple[bytes, int]:
    """Return blank-row prefix plus one complete nonblank JSONL record."""
    prefix = bytearray()
    while True:
        line = handle.readline()
        if not line:
            return b"", physical_row
        physical_row += 1
        if line.strip():
            prefix.extend(line)
            return bytes(prefix), physical_row
        prefix.extend(line)


def merged_source_lines(sources: list[SourceFile]) -> Iterator[tuple[SourceFile, bytes]]:
    """Bounded-memory chronological merge retaining projected source bytes.

    A projection's blank line prefix preserves original physical source rows;
    it travels with the next actual JSON record and therefore does not count as
    an additional schedule increment.
    """
    handles: list[BinaryIO] = []
    heap: list[tuple[tuple[int, str, int], int, int, bytes]] = []
    try:
        for index, source in enumerate(sources):
            handle = source.source.open("rb")
            handles.append(handle)
            line, row = _next_json_record_chunk(handle, 0)
            if line:
                heapq.heappush(heap, (_receipt_key(line, source, row), index, row, line))
        while heap:
            _, index, row, line = heapq.heappop(heap)
            source = sources[index]
            yield source, line
            next_line, next_row = _next_json_record_chunk(handles[index], row)
            if next_line:
                heapq.heappush(
                    heap,
                    (_receipt_key(next_line, source, next_row), index, next_row, next_line),
                )
    finally:
        for handle in handles:
            handle.close()


def source_chunk_order(sources: Iterable[SourceFile]) -> list[SourceFile]:
    """Order physical source files by their first complete JSON receipt."""
    keyed = []
    for source in sources:
        with source.source.open("rb") as handle:
            line, row = _next_json_record_chunk(handle, 0)
        key = _receipt_key(line, source, row) if line else (-(1 << 63), str(source.relative), row)
        keyed.append((key, source))
    return [source for _, source in sorted(keyed, key=lambda item: item[0])]


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
        # Exercise the production callback/acknowledgement path.  Manually
        # processing rows after ``poll`` leaves them in the caller-owned
        # inflight state and can acknowledge them on close without proving
        # that the registered analytical callback completed successfully.
        self.ingestor.register_callback(self.orchestrator)

    def poll(self, source_paths: Iterable[Path] | None = None) -> int:
        assert self.ingestor is not None and self.orchestrator is not None
        observations = self.ingestor.poll(source_paths=source_paths)
        return len(observations)

    def restart(self) -> None:
        self.close()
        self.open()

    def snapshot(self, sessions: Iterable[str]) -> dict[str, Any]:
        assert self.ingestor is not None and self.orchestrator is not None
        sessions = tuple(map(str, sessions))
        source_integrity = self.ingestor.verify_committed_sources(sessions)
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
        combined["committed_source_integrity"] = source_integrity
        return combined

    @property
    def checkpoints(self) -> Mapping[str, Any]:
        assert self.ingestor is not None
        return self.ingestor.checkpoints

    @property
    def quarantined_sources(self) -> Mapping[str, Any]:
        assert self.ingestor is not None
        return self.ingestor._quarantined_sources

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


def _claim_schedule_roots(staging_root: Path, state_root: Path) -> None:
    """Exclusively claim fresh roots before a schedule can expose bytes.

    A schedule is an independent equivalence run.  Reusing either root can
    mix a prior checkpoint with newly staged bytes; concurrent writers can
    also replace a growing source underneath the production ingestor.  The
    preflight keeps an already-existing peer root untouched, while the target
    ``mkdir`` calls provide the race-safe ownership decision.
    """
    roots = (("staging", staging_root), ("state", state_root))
    for kind, root in roots:
        if os.path.lexists(root):
            raise ValueError(f"schedule {kind} root must not exist: {root}")
    for kind, root in roots:
        try:
            root.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ValueError(
                f"schedule {kind} root was claimed concurrently: {root}"
            ) from error


def _expose_read_only_context_sources(
    sources: Iterable[SourceFile], staging_root: Path
) -> int:
    """Expose predecessor bytes to fixed-context readers, never to callbacks."""
    count = 0
    for source in sources:
        destination = staging_root / source.relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"context source destination already exists: {destination}")
        destination.symlink_to(source.source)
        count += 1
    return count


def _drain(context: _RunContext, sources: list[SourceFile], staging_root: Path) -> None:
    """Poll until checkpoints catch all currently complete staged bytes."""
    previous: tuple[tuple[str, int], ...] | None = None
    for _ in range(100_000):
        context.poll(
            [
                staging_root / source.relative
                for source in sources
                if (staging_root / source.relative).is_file()
            ]
        )
        current = tuple(
            sorted((key, int(value.get("offset", 0))) for key, value in context.checkpoints.items())
        )
        quarantined = []
        for source in sources:
            relative = str(source.relative)
            quarantine = context.quarantined_sources.get(relative)
            if quarantine is None:
                continue
            reason = (
                str(quarantine.get("reason", "UNKNOWN"))
                if isinstance(quarantine, Mapping)
                else "UNKNOWN"
            )
            quarantined.append((relative, reason))
        if quarantined:
            detail = ", ".join(
                f"{relative}={reason}"
                for relative, reason in sorted(quarantined)
            )
            raise RuntimeError(
                f"checkpoint drain blocked by quarantined source: {detail}"
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
    prefix_size = len(line) - len(line.lstrip(b"\n"))
    prefix, record = line[:prefix_size], line[prefix_size:]
    if len(record) < 3:
        return (line,)
    first = max(1, len(record) // 3)
    second = max(first + 1, (2 * len(record)) // 3)
    return prefix + record[:first], record[first:second], record[second:]


def _fraction_thresholds(total: int, count: int) -> tuple[int, ...]:
    """Return bounded deterministic record ordinals spanning the full stream."""
    if total <= 0 or count <= 0:
        return ()
    if count == 1:
        return (max(1, (total + 1) // 2),)
    return tuple(
        sorted(
            {
                1 + ((total - 1) * index) // (count - 1)
                for index in range(count)
            }
        )
    )


def _per_session_refresh_thresholds(
    sources: Iterable[SourceFile], count: int,
) -> tuple[dict[str, int | str], ...]:
    """Plan distinct interior refreshes for every evaluation session.

    Global stream fractions can put one refresh in each of several sessions
    and never recompute a dirty session.  The live contract is session-local,
    so use two causal interior cutpoints per session.  Their global positions
    are bound later while consuming the actual receipt-ordered merge;
    source-coordinate sessions cannot be assumed contiguous under adversarial
    timestamps.  Context/predecessor sources are not passed to this function.
    """
    records_by_session: Counter[str] = Counter()
    for source in sources:
        if len(source.relative.parts) < 2:
            raise ValueError(
                f"analytical refresh source lacks session coordinate: {source.relative}"
            )
        records_by_session[str(source.relative.parts[1])] += int(
            source.json_records
            if source.json_records is not None
            else source.complete_rows
        )
    plan: list[dict[str, int | str]] = []
    for session, total in sorted(records_by_session.items()):
        local_thresholds = tuple(
            sorted(
                {
                    (total * index) // (count + 1)
                    for index in range(1, count + 1)
                    if 0 < (total * index) // (count + 1) < total
                }
            )
        ) if count > 0 else ()
        for generation, local_ordinal in enumerate(local_thresholds, start=1):
            plan.append(
                {
                    "session_date": session,
                    "session_generation": generation,
                    "session_record_ordinal": local_ordinal,
                    "session_record_count": total,
                }
            )
    return tuple(plan)


def _bind_analytical_refresh_target(
    targets: Mapping[tuple[str, int], Mapping[str, Any]],
    seen_by_session: Counter[str],
    *,
    source_session: str,
    global_record_ordinal: int,
) -> dict[str, Any] | None:
    """Bind one local cutpoint to its measured receipt-merge position."""
    seen_by_session[source_session] += 1
    local_ordinal = int(seen_by_session[source_session])
    target = targets.get((source_session, local_ordinal))
    if target is None:
        return None
    return {
        **dict(target),
        "global_record_ordinal": int(global_record_ordinal),
    }


def _analytical_refresh_closure_coverage(
    refresh_views: Iterable[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure closure evolution between two periodic callback generations."""
    session_snapshots = snapshot.get("session_snapshots", {})
    if not isinstance(session_snapshots, Mapping):
        session_snapshots = {}
    views_by_session: dict[str, list[tuple[pd.Timestamp, Mapping[str, Any]]]] = {}
    for view in refresh_views:
        session = str(view.get("session_date", ""))
        cutoff_value = view.get("evidence_cutoff_timestamp")
        if not session or cutoff_value in (None, ""):
            continue
        cutoff = parse_timestamp(
            cutoff_value,
            field_name="analytical refresh causal evidence cutoff",
        )
        views_by_session.setdefault(session, []).append((cutoff, view))

    episode_opportunities: set[str] = set()
    episode_observed: set[str] = set()
    episode_finalization_only: set[str] = set()
    lifecycle_opportunities: set[str] = set()
    lifecycle_observed: set[str] = set()
    lifecycle_finalization_only: set[str] = set()

    for session, views in views_by_session.items():
        final = session_snapshots.get(session, {})
        if not isinstance(final, Mapping):
            continue
        for row in _as_rows(final.get("episodes", [])):
            identity = str(row.get("episode_id", ""))
            confirmation_value = row.get("confirmation_timestamp")
            final_end_value = row.get("episode_end_timestamp")
            if (
                not identity
                or confirmation_value in (None, "")
                or final_end_value in (None, "")
            ):
                continue
            confirmation = parse_timestamp(
                confirmation_value,
                field_name="final episode confirmation clock",
            )
            final_end = parse_timestamp(
                final_end_value,
                field_name="final episode closure clock",
            )
            final_end_text = str(final_end_value)
            for index, (early_cutoff, early_view) in enumerate(views):
                early = early_view.get("episodes", {})
                if not isinstance(early, Mapping) or identity not in early:
                    continue
                early_end_text = str(early.get(identity) or "")
                if (
                    early_end_text == final_end_text
                    or not (confirmation <= early_cutoff < final_end)
                ):
                    continue
                later_candidates = [
                    (later_cutoff, later_view)
                    for later_cutoff, later_view in views[index + 1 :]
                    if later_cutoff >= final_end
                ]
                if not later_candidates:
                    episode_finalization_only.add(identity)
                    continue
                episode_opportunities.add(identity)
                if any(
                    isinstance(later_view.get("episodes", {}), Mapping)
                    and str(
                        later_view.get("episodes", {}).get(identity) or ""
                    )
                    == final_end_text
                    for _, later_view in later_candidates
                ):
                    episode_observed.add(identity)
                break

        for row in _as_rows(final.get("lifecycle", [])):
            identity = str(row.get("record_id", ""))
            entry_value = row.get("state_entry_timestamp")
            final_exit_value = row.get("state_exit_timestamp")
            if (
                not identity
                or entry_value in (None, "")
                or final_exit_value in (None, "")
            ):
                continue
            entry = parse_timestamp(
                entry_value,
                field_name="final lifecycle entry clock",
            )
            final_exit = parse_timestamp(
                final_exit_value,
                field_name="final lifecycle exit clock",
            )
            final_exit_text = str(final_exit_value)
            for index, (early_cutoff, early_view) in enumerate(views):
                early = early_view.get("lifecycle", {})
                if not isinstance(early, Mapping) or identity not in early:
                    continue
                early_exit_text = str(early.get(identity) or "")
                if (
                    early_exit_text == final_exit_text
                    or not (entry <= early_cutoff < final_exit)
                ):
                    continue
                later_candidates = [
                    (later_cutoff, later_view)
                    for later_cutoff, later_view in views[index + 1 :]
                    if later_cutoff >= final_exit
                ]
                if not later_candidates:
                    lifecycle_finalization_only.add(identity)
                    continue
                lifecycle_opportunities.add(identity)
                if any(
                    isinstance(later_view.get("lifecycle", {}), Mapping)
                    and str(
                        later_view.get("lifecycle", {}).get(identity) or ""
                    )
                    == final_exit_text
                    for _, later_view in later_candidates
                ):
                    lifecycle_observed.add(identity)
                break

    return {
        "analytical_refresh_episode_boundary_opportunity_count": len(
            episode_opportunities
        ),
        "analytical_refresh_episode_boundary_observed_count": len(
            episode_observed
        ),
        "analytical_refresh_episode_boundary_opportunity_ids": sorted(
            episode_opportunities
        ),
        "analytical_refresh_episode_boundary_observed_ids": sorted(
            episode_observed
        ),
        "analytical_refresh_episode_boundary_missing_ids": sorted(
            episode_opportunities - episode_observed
        ),
        "analytical_refresh_episode_boundary_finalization_only_ids": sorted(
            episode_finalization_only
        ),
        "analytical_refresh_episode_boundary_status": (
            "EXERCISED"
            if episode_opportunities
            else "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
        ),
        "analytical_refresh_lifecycle_boundary_opportunity_count": len(
            lifecycle_opportunities
        ),
        "analytical_refresh_lifecycle_boundary_observed_count": len(
            lifecycle_observed
        ),
        "analytical_refresh_lifecycle_boundary_opportunity_ids": sorted(
            lifecycle_opportunities
        ),
        "analytical_refresh_lifecycle_boundary_observed_ids": sorted(
            lifecycle_observed
        ),
        "analytical_refresh_lifecycle_boundary_missing_ids": sorted(
            lifecycle_opportunities - lifecycle_observed
        ),
        "analytical_refresh_lifecycle_boundary_finalization_only_ids": sorted(
            lifecycle_finalization_only
        ),
        "analytical_refresh_lifecycle_boundary_status": (
            "EXERCISED"
            if lifecycle_opportunities
            else "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
        ),
    }


class _AnalyticalBoundaryCrash(RuntimeError):
    """Harness-only simulated crash after a durable analytical append."""


def analytical_transition_boundary_probe(
    context: _RunContext, sessions: Iterable[str]
) -> dict[str, Any]:
    """Restart after the first fsynced append in every material ledger type.

    Each retry removes the already measured ledger from the failure-injection
    set.  The repository therefore progresses in its real publication order,
    crashes after one durable append for every ledger that receives material
    output, recreates the complete ingestor/orchestrator process state, and
    reconciles every deterministic identity before continuing.  Empty ledger
    types are reported but cannot manufacture a transition boundary.
    """
    sessions = tuple(sessions)
    assert context.orchestrator is not None and context.ingestor is not None
    excluded = {
        "raw_file_checkpoints",
        "normalized_raw_events",
        "refusals_data_quality",
        "analytical_observation_stage",
    }
    material_names = [
        name for name in context.orchestrator.ledgers if name not in excluded
    ]
    if not material_names:
        raise RuntimeError("analytical transition-boundary probe has no ledgers")

    events: list[dict[str, Any]] = []
    measured_ledgers: set[str] = set()
    while True:
        assert context.orchestrator is not None
        ledgers = {
            name: context.orchestrator.ledgers[name]
            for name in material_names
        }
        pending = [name for name in material_names if name not in measured_ledgers]
        originals = {name: ledgers[name].append for name in pending}
        observed: dict[str, Any] = {}

        def wrapper(name: str):
            original = originals[name]

            def append_then_crash(row: dict[str, Any]) -> None:
                original(row)
                if observed:
                    return
                observed.update(
                    {
                        "ledger": name,
                        "event_id": str(row.get("event_id", "")),
                        "path": str(ledgers[name].path),
                        "bytes_after_durable_append": (
                            ledgers[name].path.stat().st_size
                        ),
                    }
                )
                raise _AnalyticalBoundaryCrash(
                    f"simulated crash after durable {name} transition"
                )

            return append_then_crash

        for name in pending:
            ledgers[name].append = wrapper(name)  # type: ignore[method-assign]
        caught = False
        try:
            context.orchestrator.flush(sessions)
        except _AnalyticalBoundaryCrash:
            caught = True
        finally:
            for name in pending:
                ledgers[name].append = originals[name]  # type: ignore[method-assign]

        if not caught:
            break
        if not observed.get("event_id"):
            raise RuntimeError("analytical transition-boundary crash lost its identity")
        ledger_name = str(observed["ledger"])
        durable_count = sum(
            str(row.get("event_id", "")) == observed["event_id"]
            for row in ledgers[ledger_name].rows()
        )
        if durable_count != 1:
            raise RuntimeError(
                "analytical transition was not durable exactly once before restart"
            )
        observed["durable_occurrences_before_restart"] = durable_count
        measured_ledgers.add(ledger_name)
        context.restart()
        assert context.orchestrator is not None
        restarted_ledger = context.orchestrator.ledgers[ledger_name]
        restarted_count = sum(
            str(row.get("event_id", "")) == observed["event_id"]
            for row in restarted_ledger.rows()
        )
        if restarted_count != 1:
            raise RuntimeError(
                "durable analytical transition was not recovered exactly once"
            )
        observed["durable_occurrences_after_restart"] = restarted_count
        events.append(observed)

    assert context.orchestrator is not None
    nonempty_ledgers = sorted(
        name
        for name in material_names
        if context.orchestrator.ledgers[name].rows()
    )
    missing = sorted(set(nonempty_ledgers) - measured_ledgers)
    if missing:
        raise RuntimeError(
            "material analytical ledgers escaped restart injection: "
            + ",".join(missing)
        )
    if not events:
        raise RuntimeError("analytical transition-boundary crash was not measured")
    return {
        "measured": True,
        "events": events,
        "restart_count": len(events),
        "material_ledger_types": material_names,
        "material_ledgers_with_rows": nonempty_ledgers,
        "crash_covered_ledgers": sorted(measured_ledgers),
        "empty_material_ledgers": sorted(set(material_names) - set(nonempty_ledgers)),
        "durable_occurrences_before_restart": (
            1
            if all(event["durable_occurrences_before_restart"] == 1 for event in events)
            else 0
        ),
        "durable_occurrences_after_restart": (
            1
            if all(event["durable_occurrences_after_restart"] == 1 for event in events)
            else 0
        ),
    }


def run_schedule(
    *,
    schedule: Schedule,
    sources: list[SourceFile],
    staging_root: Path,
    state_root: Path,
    config_path: Path,
    sessions: tuple[str, ...],
    context_sources: Iterable[SourceFile] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Execute one schedule exclusively through the production live path."""
    begun = time.monotonic()
    _claim_schedule_roots(staging_root, state_root)
    (staging_root / "raw").mkdir()
    (staging_root / "oi").mkdir()
    context_source_count = _expose_read_only_context_sources(
        context_sources, staging_root
    )
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
    checkpoint_restart_count = 0
    analytical_boundary_restart_count = 0
    poll_count = 0
    split_line_boundary_count = 0
    explicit_empty_poll_count = 0
    analytical_refresh_flush_count = 0
    analytical_refresh_nonempty_count = 0
    analytical_refresh_repeat_session_count = 0
    analytical_refresh_episode_end_update_count = 0
    analytical_refresh_lifecycle_exit_update_count = 0
    analytical_refresh_timestamp_backdating = 0
    analytical_refresh_duplicate_ids = 0
    analytical_refresh_future_joins = 0
    analytical_refresh_tolerance_violations = 0
    analytical_refresh_trace: list[dict[str, Any]] = []
    analytical_refresh_closure_views: list[dict[str, Any]] = []
    analytical_refresh_recomputed_target_sessions: set[str] = set()
    original_source_chunk_count = 0
    original_source_files_staged_before_first_poll = 0
    record_increment_count = 0
    record_group_sizes_exercised: set[int] = set()
    record_group_sequence = hashlib.sha256()
    maximum_record_group_bytes = 0
    post_poll_hourly_path_introductions = 0
    polled_live_paths: set[Path] = set()
    causal_backlog_paths: set[Path] = set()
    causal_backlog_path_repolls = 0
    maximum_causal_backlog_paths = 0
    original_checkpoint_chunk_counts: Counter[str] = Counter()
    original_checkpoint_delta_bytes: Counter[str] = Counter()
    original_checkpoint_delta_oversize_count = 0
    exposed_source_paths: set[Path] = set()
    analytical_boundary_probe: dict[str, Any] = {"measured": False}
    total_records = sum(
        source.json_records if source.json_records is not None else source.complete_rows
        for source in sources
    )
    split_thresholds = set(_fraction_thresholds(total_records, schedule.split_events))
    empty_thresholds = list(
        _fraction_thresholds(total_records, schedule.empty_poll_events)
    )
    restart_thresholds = list(_fraction_thresholds(total_records, schedule.restart_events))
    local_analytical_refresh_plan = list(
        _per_session_refresh_thresholds(
            sources, schedule.analytical_flush_events_per_session
        )
    )
    if schedule.analytical_flush_events_per_session:
        planned_sessions = {
            str(row["session_date"])
            for row in local_analytical_refresh_plan
        }
        if planned_sessions != set(sessions):
            raise ValueError(
                "analytical refresh plan does not cover every evaluation "
                f"session: planned={sorted(planned_sessions)!r} "
                f"expected={sorted(sessions)!r}"
            )
    analytical_refresh_targets = {
        (str(row["session_date"]), int(row["session_record_ordinal"])): row
        for row in local_analytical_refresh_plan
    }
    analytical_refresh_plan: list[dict[str, Any]] = []
    analytical_flush_thresholds: list[int] = []
    merged_records_by_session: Counter[str] = Counter()
    merged_record_ordinal = 0
    next_empty_threshold = 0
    next_restart_threshold = 0
    next_analytical_flush_threshold = 0

    def poll_for_schedule(source_paths: Iterable[Path] | None = None) -> int:
        nonlocal poll_count
        count = context.poll(source_paths)
        poll_count += 1
        return count

    def poll_visible_causal_prefix(changed_paths: Iterable[Path]) -> int:
        """Poll new bytes plus visible peers still behind their checkpoints.

        Production discovery polls every visible stream. Schedule fixtures
        pass explicit paths so a one-record increment does not accidentally
        become a broad filesystem rescan, but they must retain any peer whose
        staged bytes could not advance because an unresolved candidate or
        selection-replay barrier held its primary checkpoint. Omitting that
        peer lets a newly changed OI path advance the watermark ahead of the
        earlier raw backlog and manufactures out-of-order refusals that the
        real discovery poll would not produce.
        """
        nonlocal causal_backlog_paths, causal_backlog_path_repolls
        nonlocal maximum_causal_backlog_paths
        changed = set(changed_paths)
        repolled = causal_backlog_paths - changed
        candidates = changed | causal_backlog_paths
        causal_backlog_path_repolls += len(repolled)
        result = poll_for_schedule(candidates)
        remaining: set[Path] = set()
        for path in candidates:
            if not path.is_file():
                continue
            relative = str(path.relative_to(staging_root))
            offset = int(context.checkpoints.get(relative, {}).get("offset", 0))
            if offset < path.stat().st_size:
                remaining.add(path)
        causal_backlog_paths = remaining
        maximum_causal_backlog_paths = max(
            maximum_causal_backlog_paths, len(remaining)
        )
        return result

    def periodic_analytical_flush(plan: Mapping[str, Any]) -> None:
        """Exercise the production refresh/finalize path during ingestion."""
        nonlocal analytical_refresh_flush_count
        nonlocal analytical_refresh_nonempty_count
        nonlocal analytical_refresh_repeat_session_count
        nonlocal analytical_refresh_episode_end_update_count
        nonlocal analytical_refresh_lifecycle_exit_update_count
        nonlocal analytical_refresh_timestamp_backdating
        nonlocal analytical_refresh_duplicate_ids
        nonlocal analytical_refresh_future_joins
        nonlocal analytical_refresh_tolerance_violations
        assert context.orchestrator is not None
        orchestrator = context.orchestrator
        target_session = str(plan["session_date"])
        target_was_dirty = target_session in set(
            getattr(orchestrator, "_dirty_sessions", set())
        )
        accepted_observation_count = len(
            getattr(orchestrator, "_sessions", {}).get(target_session, {})
        )
        # Retain only the two mutable closure annotations under test.  Copying
        # complete snapshots here would transiently duplicate dense resolution
        # and participation tables during the full six-session schedule.
        def closure_annotations() -> dict[str, dict[str, dict[str, Any]]]:
            result: dict[str, dict[str, dict[str, Any]]] = {}
            for session, output in orchestrator._outputs.items():
                result[session] = {
                    "episodes": {
                        str(row.get("episode_id")): row.get(
                            "episode_end_timestamp"
                        )
                        for row in _as_rows(output.get("episodes", []))
                        if row.get("episode_id")
                    },
                    "lifecycle": {
                        str(row.get("record_id")): row.get(
                            "state_exit_timestamp"
                        )
                        for row in _as_rows(output.get("lifecycle", []))
                        if row.get("record_id")
                    },
                }
            return result

        before_annotations = closure_annotations()
        repeated_sessions = set(before_annotations) & set(
            getattr(orchestrator, "_dirty_sessions", set())
        )
        pending_sessions = orchestrator.pending_session_dates()
        refreshed_nonempty = False

        def measure_published_counters() -> None:
            """Capture every intermediate publication without copying rows."""
            nonlocal analytical_refresh_timestamp_backdating
            nonlocal analytical_refresh_duplicate_ids
            nonlocal analytical_refresh_future_joins
            nonlocal analytical_refresh_tolerance_violations
            for published_session in orchestrator.sealed_session_dates():
                audit = orchestrator.sealed_audit_measurements(
                    published_session
                )
                analytical_refresh_timestamp_backdating = max(
                    analytical_refresh_timestamp_backdating,
                    int(audit["timestamp_backdating"]),
                )
                analytical_refresh_duplicate_ids = max(
                    analytical_refresh_duplicate_ids,
                    int(audit["duplicate_analytical_ids"]),
                )
            causality = orchestrator.causality_metrics()
            analytical_refresh_future_joins = max(
                analytical_refresh_future_joins,
                int(causality["future_joins"]),
            )
            analytical_refresh_tolerance_violations = max(
                analytical_refresh_tolerance_violations,
                int(causality["synchronization_tolerance_violations"]),
            )

        if pending_sessions:
            newest = max(pending_sessions)
            for prior_session in (
                session for session in pending_sessions if session < newest
            ):
                refreshed_nonempty = bool(
                    orchestrator.finalize_session(prior_session)
                ) or refreshed_nonempty
                measure_published_counters()
        flushed = orchestrator.flush()
        refreshed_nonempty = bool(flushed) or refreshed_nonempty
        measure_published_counters()
        after_annotations = closure_annotations()
        analytical_refresh_flush_count += 1
        analytical_refresh_nonempty_count += int(refreshed_nonempty)
        analytical_refresh_repeat_session_count += len(repeated_sessions)
        if target_session in repeated_sessions:
            analytical_refresh_recomputed_target_sessions.add(target_session)

        for session in set(before_annotations) & set(after_annotations):
            prior_episodes = before_annotations[session]["episodes"]
            for identity, episode_end in after_annotations[session][
                "episodes"
            ].items():
                if identity in prior_episodes and (
                    prior_episodes[identity] != episode_end
                ):
                    analytical_refresh_episode_end_update_count += 1
            prior_lifecycle = before_annotations[session]["lifecycle"]
            for identity, state_exit in after_annotations[session][
                "lifecycle"
            ].items():
                if identity in prior_lifecycle and (
                    prior_lifecycle[identity] != state_exit
                ):
                    analytical_refresh_lifecycle_exit_update_count += 1

        output = getattr(orchestrator, "_outputs", {}).get(target_session, {})
        availability = (
            output.get("availability", {})
            if isinstance(output, Mapping)
            else {}
        )
        evidence_cutoff = str(
            availability.get("evidence_cutoff_timestamp")
            or availability.get("reference_timestamp")
            or ""
        )
        valid_basis_cutoffs = [
            str(row.get("basis_timestamp", ""))
            for row in _as_rows(
                output.get("basis", {})
                if isinstance(output, Mapping)
                else []
            )
            if row.get("validity_status") == "VALID"
            and row.get("basis_timestamp")
        ]
        valid_basis_cutoff = max(
            valid_basis_cutoffs,
            key=lambda value: parse_timestamp(
                value,
                field_name="periodic valid synchronized basis cutoff",
            ),
            default="",
        )
        analytical_refresh_trace.append(
            {
                **dict(plan),
                "exposed_record_ordinal": exposed_records,
                "poll_generation": poll_count,
                "target_was_dirty": target_was_dirty,
                "flush_returned_target": target_session in flushed,
                "accepted_observation_count": accepted_observation_count,
                "evidence_cutoff_timestamp": evidence_cutoff,
                "valid_basis_cutoff_timestamp": valid_basis_cutoff,
            }
        )
        analytical_refresh_closure_views.append(
            {
                "session_date": target_session,
                "evidence_cutoff_timestamp": evidence_cutoff,
                "episodes": dict(
                    after_annotations.get(target_session, {}).get(
                        "episodes", {}
                    )
                ),
                "lifecycle": dict(
                    after_annotations.get(target_session, {}).get(
                        "lifecycle", {}
                    )
                ),
            }
        )

    try:
        groups = schedule.line_groups
        group_index = 0
        pending: list[tuple[SourceFile, bytes]] = []
        pending_bytes = 0
        assert context.ingestor is not None
        maximum_exposure_bytes = context.ingestor.read_limit

        def flush_pending() -> None:
            nonlocal exposed_records, restart_count, checkpoint_restart_count
            nonlocal group_index, pending_bytes, split_line_boundary_count
            nonlocal explicit_empty_poll_count, next_empty_threshold
            nonlocal next_restart_threshold
            nonlocal next_analytical_flush_threshold
            nonlocal record_increment_count
            nonlocal maximum_record_group_bytes
            nonlocal post_poll_hourly_path_introductions
            if not pending:
                return
            record_increment_count += 1
            record_group_sizes_exercised.add(len(pending))
            record_group_sequence.update(f"{len(pending)},".encode())
            maximum_record_group_bytes = max(maximum_record_group_bytes, pending_bytes)
            changed_paths: set[Path] = set()
            for pending_source, pending_line in pending:
                destination = staging_root / pending_source.relative
                exposed_source_paths.add(pending_source.relative)
                changed_paths.add(destination)
                record_ordinal = exposed_records + 1
                if schedule.split_inside_lines and (
                    not split_thresholds or record_ordinal in split_thresholds
                ):
                    for part in _line_parts(pending_line):
                        _append(destination, part)
                        # Every complete record earlier in this chronological
                        # group is already visible on its own source path.  A
                        # partial-line probe must poll that complete causal
                        # prefix too; polling only the fragmented destination
                        # would invent a future observation ahead of unpolled
                        # peer files and turn a chunk test into an ordering
                        # mutation.
                        poll_visible_causal_prefix(changed_paths)
                    split_line_boundary_count += 1
                else:
                    _append(destination, pending_line)
                exposed_records += 1
            # This final poll is also required when only a deterministic subset
            # was split: records appended after the last split remain pending.
            for destination in changed_paths - polled_live_paths:
                relative = destination.relative_to(staging_root)
                stream_session = relative.parts[:2]
                if any(
                    prior.relative_to(staging_root).parts[:2] == stream_session
                    for prior in polled_live_paths
                ):
                    post_poll_hourly_path_introductions += 1
            poll_visible_causal_prefix(changed_paths)
            polled_live_paths.update(changed_paths)
            while (
                next_analytical_flush_threshold
                < len(analytical_flush_thresholds)
                and exposed_records
                >= analytical_flush_thresholds[next_analytical_flush_threshold]
            ):
                periodic_analytical_flush(
                    analytical_refresh_plan[next_analytical_flush_threshold]
                )
                next_analytical_flush_threshold += 1
            if (
                schedule.restart_every
                and exposed_records // schedule.restart_every > checkpoint_restart_count
            ):
                context.restart()
                restart_count += 1
                checkpoint_restart_count += 1
            while (
                next_restart_threshold < len(restart_thresholds)
                and exposed_records >= restart_thresholds[next_restart_threshold]
            ):
                context.restart()
                restart_count += 1
                checkpoint_restart_count += 1
                next_restart_threshold += 1
            pending.clear()
            if schedule.empty_poll_events:
                while (
                    next_empty_threshold < len(empty_thresholds)
                    and exposed_records >= empty_thresholds[next_empty_threshold]
                ):
                    for _ in range(schedule.empty_polls):
                        poll_for_schedule(())
                        explicit_empty_poll_count += 1
                    next_empty_threshold += 1
            else:
                for _ in range(schedule.empty_polls):
                    poll_for_schedule(())
                    explicit_empty_poll_count += 1
            group_index += 1
            pending_bytes = 0

        if schedule.original_byte_chunks:
            # Make every complete evaluation file visible before the first
            # production poll.  The collector writes raw and OI peers
            # concurrently; exposing and polling one complete hourly file at a
            # time would invent an ordering in which (for example) raw_10 can
            # publish through the hour before oi_10 exists.  Once staged, the
            # production ingestor reads every file in its native ``read_limit``
            # chunks and its incomplete-stream watermarks merge the streams.
            # Predecessor symlinks remain fixed-context-only because every poll
            # below receives the explicit evaluation-file allowlist.
            for source in source_chunk_order(sources):
                destination = staging_root / source.relative
                exposed_source_paths.add(source.relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.source.open("rb") as handle, destination.open("xb") as staged:
                    while True:
                        block = handle.read(maximum_exposure_bytes)
                        if not block:
                            break
                        staged.write(block)
                    staged.flush()
                    os.fsync(staged.fileno())
                exposed_records += (
                    source.json_records
                    if source.json_records is not None
                    else source.complete_rows
                )
            live_destinations = tuple(
                staging_root / source.relative for source in sources
            )
            original_source_files_staged_before_first_poll = len(live_destinations)
            previous_offsets: tuple[tuple[str, int], ...] | None = None
            for _ in range(100_000):
                before = {
                    str(source.relative): int(
                        context.checkpoints.get(str(source.relative), {}).get("offset", 0)
                    )
                    for source in sources
                }
                poll_for_schedule(live_destinations)
                after = tuple(
                    sorted(
                        (
                            str(source.relative),
                            int(
                                context.checkpoints.get(
                                    str(source.relative), {}
                                ).get("offset", 0)
                            ),
                        )
                        for source in sources
                    )
                )
                after_by_relative = dict(after)
                original_source_chunk_count += sum(
                    offset > before[relative] for relative, offset in after
                )
                for relative, offset in after:
                    delta = offset - before[relative]
                    if delta <= 0:
                        continue
                    original_checkpoint_chunk_counts[relative] += 1
                    original_checkpoint_delta_bytes[relative] += delta
                    if delta > maximum_exposure_bytes:
                        original_checkpoint_delta_oversize_count += 1
                if all(
                    after_by_relative[str(source.relative)] == source.size
                    for source in sources
                ):
                    break
                if after == previous_offsets:
                    raise RuntimeError(
                        "original source chunks made no checkpoint progress"
                    )
                previous_offsets = after
            else:
                raise RuntimeError("original source chunk drain iteration limit exceeded")
        else:
            for source, line in merged_source_lines(sources):
                merged_record_ordinal += 1
                refresh_target = _bind_analytical_refresh_target(
                    analytical_refresh_targets,
                    merged_records_by_session,
                    source_session=str(source.relative.parts[1]),
                    global_record_ordinal=merged_record_ordinal,
                )
                if refresh_target is not None:
                    analytical_refresh_plan.append(refresh_target)
                    analytical_flush_thresholds.append(
                        int(refresh_target["global_record_ordinal"])
                    )
                target = groups[group_index % len(groups)]
                stream_session = source.relative.parts[:2]
                earlier_same_stream_file = any(
                    item.relative.parts[:2] == stream_session
                    and item.relative != source.relative
                    for item, _ in pending
                ) or any(
                    relative.parts[:2] == stream_session
                    and relative != source.relative
                    for relative in exposed_source_paths
                )
                if pending and (
                    len(pending) >= target
                    or (
                        target >= 512
                        and pending_bytes + len(line) > maximum_exposure_bytes
                    )
                    or (
                        schedule.name == "hourly_file_rotation"
                        and source.relative
                        not in {item.relative for item, _ in pending}
                        and earlier_same_stream_file
                    )
                ):
                    flush_pending()
                pending.append((source, line))
                pending_bytes += len(line)
                pending_ordinal = exposed_records + len(pending)
                exact_refresh_boundary = (
                    next_analytical_flush_threshold
                    < len(analytical_flush_thresholds)
                    and pending_ordinal
                    == analytical_flush_thresholds[
                        next_analytical_flush_threshold
                    ]
                )
                if (
                    exact_refresh_boundary
                    or len(pending) >= groups[group_index % len(groups)]
                ):
                    flush_pending()
            if len(analytical_refresh_plan) != len(
                local_analytical_refresh_plan
            ):
                raise RuntimeError(
                    "not every per-session analytical refresh cutpoint was "
                    "bound to the receipt-ordered merge"
                )
            flush_pending()
        _drain(context, sources, staging_root)
        causal_checkpoint_remainders_after_drain = sum(
            int(context.checkpoints.get(str(relative), {}).get("offset", 0))
            < (staging_root / relative).stat().st_size
            for relative in exposed_source_paths
            if (staging_root / relative).is_file()
        )
        if schedule.restart_on_analytical_transition:
            analytical_boundary_probe = analytical_transition_boundary_probe(
                context, sessions
            )
            measured_restarts = int(analytical_boundary_probe["restart_count"])
            restart_count += measured_restarts
            analytical_boundary_restart_count += measured_restarts
        snapshot = context.snapshot(sessions)
        assert context.orchestrator is not None
        dirty_sessions = sorted(
            set(getattr(context.orchestrator, "_dirty_sessions", set()))
        )
        staged_sessions = sorted(
            set(getattr(context.orchestrator, "_sessions", {}))
        )
        unexpected_staged_sessions = sorted(set(staged_sessions) - set(sessions))
        if dirty_sessions or unexpected_staged_sessions:
            raise RuntimeError(
                "non-evaluation analytical stage survived seal: "
                f"dirty={dirty_sessions} unexpected={unexpected_staged_sessions}"
            )
        if schedule.restart_on_analytical_transition:
            assert context.orchestrator is not None
            exactly_once = True
            for event in analytical_boundary_probe["events"]:
                ledger = context.orchestrator.ledgers[str(event["ledger"])]
                occurrences = sum(
                    str(row.get("event_id", "")) == event["event_id"]
                    for row in ledger.rows()
                )
                event["occurrences_after_retry_and_seal"] = occurrences
                event["exactly_once_after_seal"] = occurrences == 1
                exactly_once = exactly_once and occurrences == 1
            analytical_boundary_probe["occurrences_after_retry_and_seal"] = (
                1 if exactly_once else 0
            )
            analytical_boundary_probe["exactly_once_after_seal"] = exactly_once
            if not exactly_once:
                raise RuntimeError(
                    "analytical transition duplicated after restart/seal retry"
                )
        accounting = checkpoint_accounting(sources, staging_root, context.checkpoints)
        raw_ledgers = snapshot.get("analytical_ledgers", {})
        analytical_refusals = (
            len(_as_rows(raw_ledgers.get("refusals_data_quality", [])))
            if isinstance(raw_ledgers, Mapping)
            else 0
        )
        closure_coverage = _analytical_refresh_closure_coverage(
            analytical_refresh_closure_views, snapshot
        )
        prior_refresh_by_session: dict[str, dict[str, Any]] = {}
        observed_poll_generations: set[int] = set()
        for trace in analytical_refresh_trace:
            session = str(trace["session_date"])
            prior = prior_refresh_by_session.get(session)
            poll_generation = int(trace["poll_generation"])
            trace["exact_threshold_discharge"] = int(
                trace["exposed_record_ordinal"]
            ) == int(trace["global_record_ordinal"])
            trace["distinct_poll_generation"] = (
                poll_generation not in observed_poll_generations
            )
            observed_poll_generations.add(poll_generation)
            accepted = int(trace["accepted_observation_count"])
            trace["accepted_observation_count_advanced"] = (
                accepted > int(prior["accepted_observation_count"])
                if prior is not None
                else accepted > 0
            )
            evidence_cutoff = trace.get("evidence_cutoff_timestamp")
            basis_cutoff = trace.get("valid_basis_cutoff_timestamp")
            prior_evidence_cutoff = (
                prior.get("evidence_cutoff_timestamp")
                if prior is not None
                else None
            )
            prior_basis_cutoff = (
                prior.get("valid_basis_cutoff_timestamp")
                if prior is not None
                else None
            )
            trace["causal_evidence_cutoff_advanced"] = (
                False
                if evidence_cutoff in (None, "")
                else True
                if prior is None
                else False
                if prior_evidence_cutoff in (None, "")
                else parse_timestamp(
                    evidence_cutoff,
                    field_name="periodic analytical evidence cutoff",
                )
                > parse_timestamp(
                    prior_evidence_cutoff,
                    field_name="prior periodic analytical evidence cutoff",
                )
            )
            trace["valid_basis_cutoff_advanced"] = (
                False
                if basis_cutoff in (None, "")
                else True
                if prior is None
                else False
                if prior_basis_cutoff in (None, "")
                else parse_timestamp(
                    basis_cutoff,
                    field_name="periodic synchronized basis cutoff",
                )
                > parse_timestamp(
                    prior_basis_cutoff,
                    field_name="prior periodic synchronized basis cutoff",
                )
            )
            prior_refresh_by_session[session] = trace
        metrics = {
            "schedule": schedule.name,
            "source_files": len(sources),
            "read_only_context_source_files": context_source_count,
            "dirty_sessions_after_seal": dirty_sessions,
            "staged_sessions": staged_sessions,
            "unexpected_staged_sessions": unexpected_staged_sessions,
            "source_bytes": sum(source.size for source in sources),
            "source_complete_rows": sum(source.complete_rows for source in sources),
            "source_json_records": sum(
                source.json_records if source.json_records is not None else source.complete_rows
                for source in sources
            ),
            "exposed_records": exposed_records,
            "poll_calls_by_harness": poll_count,
            "restart_count": restart_count,
            "checkpoint_restart_count": checkpoint_restart_count,
            "analytical_boundary_restart_count": analytical_boundary_restart_count,
            "analytical_boundary_probe": analytical_boundary_probe,
            "split_line_boundary_count": split_line_boundary_count,
            "explicit_empty_poll_count": explicit_empty_poll_count,
            "analytical_refresh_flush_count": analytical_refresh_flush_count,
            "analytical_refresh_nonempty_count": (
                analytical_refresh_nonempty_count
            ),
            "analytical_refresh_repeat_session_count": (
                analytical_refresh_repeat_session_count
            ),
            "analytical_refresh_episode_end_update_count": (
                analytical_refresh_episode_end_update_count
            ),
            "analytical_refresh_lifecycle_exit_update_count": (
                analytical_refresh_lifecycle_exit_update_count
            ),
            "analytical_refresh_timestamp_backdating": (
                analytical_refresh_timestamp_backdating
            ),
            "analytical_refresh_duplicate_analytical_ids": (
                analytical_refresh_duplicate_ids
            ),
            "analytical_refresh_future_joins": (
                analytical_refresh_future_joins
            ),
            "analytical_refresh_synchronization_tolerance_violations": (
                analytical_refresh_tolerance_violations
            ),
            "analytical_refresh_events_per_session": (
                schedule.analytical_flush_events_per_session
            ),
            "analytical_refresh_evaluation_session_count": len(sessions),
            "analytical_refresh_evaluation_sessions": list(sessions),
            "analytical_refresh_expected_count": len(
                local_analytical_refresh_plan
            ),
            "analytical_refresh_plan": analytical_refresh_plan,
            "analytical_refresh_trace": analytical_refresh_trace,
            "analytical_refresh_recomputed_target_sessions": sorted(
                analytical_refresh_recomputed_target_sessions
            ),
            **closure_coverage,
            "original_source_chunk_count": original_source_chunk_count,
            "original_source_files_staged_before_first_poll": (
                original_source_files_staged_before_first_poll
            ),
            "record_increment_count": record_increment_count,
            "record_group_sizes_exercised": sorted(record_group_sizes_exercised),
            "record_group_sequence_sha256": record_group_sequence.hexdigest(),
            "maximum_record_group_bytes": maximum_record_group_bytes,
            "maximum_exposure_bytes": maximum_exposure_bytes,
            "causal_backlog_path_repolls": causal_backlog_path_repolls,
            "maximum_causal_backlog_paths": maximum_causal_backlog_paths,
            "causal_checkpoint_remainders_after_drain": (
                causal_checkpoint_remainders_after_drain
            ),
            "hourly_rotation_boundary_count": post_poll_hourly_path_introductions,
            "expected_hourly_rotation_boundaries": sum(
                max(
                    0,
                    len(
                        {
                            source.relative
                            for source in sources
                            if source.relative.parts[:2] == (stream, session)
                        }
                    )
                    - 1,
                )
                for stream in ("raw", "oi")
                for session in sessions
            ),
            "source_sizes_by_relative": {
                str(source.relative): source.size for source in sources
            },
            "original_checkpoint_chunk_counts": dict(
                sorted(original_checkpoint_chunk_counts.items())
            ),
            "original_checkpoint_delta_bytes": dict(
                sorted(original_checkpoint_delta_bytes.items())
            ),
            "original_checkpoint_delta_oversize_count": (
                original_checkpoint_delta_oversize_count
            ),
            "checkpoint_failures": sum(row["status"] != "PASS" for row in accounting),
            "analytical_refusals": analytical_refusals,
            "committed_source_integrity": dict(
                snapshot.get("committed_source_integrity", {})
            ),
            "semantic_hash": named_rows_semantic_hash(
                component_rows(snapshot)
            ),
            "elapsed_seconds": time.monotonic() - begun,
            "peak_rss_kib_process": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
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


def _run_repository_command(
    command: list[str], repository: Path, *, trace_path: Path | None = None
) -> dict[str, Any]:
    environment = os.environ.copy()
    source_path = str(repository / "src")
    environment["PYTHONPATH"] = source_path + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    executed = command
    if trace_path is not None:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        executed = [
            "strace",
            "-ff",
            "-qq",
            "-s",
            "4096",
            "-yy",
            "-e",
            "trace=open,openat,openat2",
            "-e",
            "status=successful",
            "-o",
            str(trace_path),
            "--",
            *command,
        ]
    completed = subprocess.run(
        executed,
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
        "open_trace": str(trace_path) if trace_path is not None else "",
        "open_trace_files": [
            str(path) for path in _strace_files(trace_path)
        ] if trace_path is not None else [],
        "open_trace_sha256": semantic_hash(
            [_sha256_file(path) for path in _strace_files(trace_path)]
        ) if trace_path is not None and _strace_files(trace_path) else "",
    }


_STRACE_OPEN = re.compile(
    r'^(?:\d+\s+)?(?:open|openat|openat2)\(([^\"]*)'
    r'\"((?:\\.|[^\"])*)\",\s*([^)]*)\)\s+=\s+(-?\d+)'
    r'(?:<([^>]*)>)?'
)


def _strace_files(prefix: Path) -> tuple[Path, ...]:
    files = tuple(sorted(prefix.parent.glob(prefix.name + ".*")))
    if not files and prefix.is_file():
        files = (prefix,)
    return files


def _parse_strace_read_opens(trace_path: Path, cwd: Path) -> Counter[tuple[str, str]]:
    """Parse successful non-creating read opens from one child trace."""
    result: Counter[tuple[str, str]] = Counter()
    with trace_path.open(errors="replace") as handle:
        for line in handle:
            match = _STRACE_OPEN.match(line)
            if match is None:
                if line.strip():
                    raise ValueError(f"unparsed successful child open: {line[:300]!r}")
                continue
            if int(match.group(4)) < 0:
                continue
            flags = match.group(3)
            if "O_WRONLY" in flags or any(
                flag in flags for flag in ("O_CREAT", "O_TRUNC", "O_EXCL")
            ):
                continue
            if "O_RDONLY" not in flags and "O_RDWR" not in flags:
                continue
            try:
                decoded = json.loads('"' + match.group(2) + '"')
                raw = Path(decoded)
                dirfd = re.search(r'<([^>]*)>', match.group(1))
                base = Path(dirfd.group(1)) if dirfd is not None else cwd
                requested = raw if raw.is_absolute() else base / raw
                requested = requested.absolute()
                returned = match.group(5)
                resolved = (
                    Path(returned)
                    if returned and Path(returned).is_absolute()
                    else requested.resolve(strict=False)
                )
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                continue
            result[(str(requested), str(resolved))] += 1
    return result


def child_open_audit_rows(
    *,
    traces: Mapping[str, Path],
    data_root: Path,
    generated_root: Path,
    repository: Path,
    config_paths: Iterable[Path],
) -> list[dict[str, Any]]:
    """Classify actual clean-B child reads and require complete raw coverage."""
    raw_root = data_root.resolve()
    state_root = generated_root.resolve()
    repo = repository.resolve()
    configs = tuple(path.resolve() for path in config_paths)
    runtime_roots = _runtime_library_roots()
    observed_by_component: dict[str, Counter[tuple[str, str]]] = {}
    rows: list[dict[str, Any]] = []
    for component, trace_path in traces.items():
        trace_files = _strace_files(trace_path)
        if not trace_files:
            raise ValueError(f"clean-B child open trace missing: {component}")
        observed: Counter[tuple[str, str]] = Counter()
        for path in trace_files:
            observed.update(_parse_strace_read_opens(path, repo))
        observed_by_component[component] = observed
        for (requested_text, resolved_text), count in sorted(observed.items()):
            requested = Path(requested_text)
            resolved = Path(resolved_text)
            classification, purpose = _classify_observed_open(
                requested,
                resolved,
                data_roots=(raw_root,),
                state_roots=(state_root,),
                config_paths=configs,
                repository=repo,
                runtime_roots=runtime_roots,
            )
            rows.append(
                {
                    "run": "batch_b",
                    "component": component,
                    "path": requested_text,
                    "resolved_path": resolved_text,
                    "purpose": purpose,
                    "classification": classification,
                    "evidence_source": "LINUX_STRACE_SUCCESSFUL_READ_OPEN",
                    "observed_open_count": count,
                }
            )

    union = Counter()
    for observed in observed_by_component.values():
        union.update(observed)
    for source in sorted(
        [*(raw_root / "raw").glob("*/*.jsonl"), *(raw_root / "oi").glob("*/*.jsonl")]
    ):
        requested = str(source.absolute())
        resolved = str(source.resolve())
        count = sum(
            value
            for (opened, target), value in union.items()
            if opened == requested or target == resolved
        )
        rows.append(
            {
                "run": "batch_b",
                "component": "all_clean_batch_children",
                "path": requested,
                "resolved_path": resolved,
                "purpose": "REQUIRED_AUTHORITATIVE_SOURCE_CHILD_READ",
                "classification": "PERMITTED_OBSERVED_REQUIRED_SOURCE_OPEN"
                if count
                else "UNMEASURED_REQUIRED_SOURCE_OPEN",
                "evidence_source": "LINUX_STRACE_SUCCESSFUL_READ_OPEN",
                "observed_open_count": count,
                "required_source_open": True,
                "status": "PASS" if count else "FAIL",
            }
        )
    for component, observed in observed_by_component.items():
        raw_reads = sum(
            count
            for (requested, resolved), count in observed.items()
            if Path(requested).is_relative_to(raw_root)
            or Path(resolved).is_relative_to(raw_root)
        )
        generated_reads = sum(
            count
            for (requested, resolved), count in observed.items()
            if Path(requested).is_relative_to(state_root)
            or Path(resolved).is_relative_to(state_root)
        )
        passed = raw_reads > 0 if component in {"inventory", "stack"} else generated_reads > 0
        rows.append(
            {
                "run": "batch_b",
                "component": component,
                "path": str(traces[component]),
                "purpose": "REQUIRED_CHILD_RAW_READ"
                if component in {"inventory", "stack"}
                else "REQUIRED_LAYERS_GENERATED_STATE_READ",
                "classification": "PERMITTED_OBSERVED_CHILD_COMPONENT_COVERAGE"
                if passed
                else "UNMEASURED_CHILD_COMPONENT_INPUT",
                "evidence_source": "LINUX_STRACE_SUCCESSFUL_READ_OPEN",
                "observed_open_count": raw_reads
                if component in {"inventory", "stack"}
                else generated_reads,
                "status": "PASS" if passed else "FAIL",
            }
        )
    return rows


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


def _evaluation_date(row: Mapping[str, Any]) -> str:
    value = row.get("evaluation_date") or row.get("session_date") or row.get("date")
    if value:
        return str(value)
    episode = str(row.get("episode_id", ""))
    return episode[5:15] if len(episode) >= 15 else ""


def build_intraday_inventory_fallback(
    *,
    data_root: Path,
    stack_config_path: Path,
    inventory_config_path: Path,
    sessions: tuple[str, ...],
    canonical_inventory: Iterable[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    tuple[str, ...],
]:
    """Independently calculate degradation rows omitted by batch gating.

    The canonical batch inventory intentionally publishes an evaluation only
    after the complete fixed predecessor chain exists.  Live degradation has a
    stronger availability contract: current-session Intraday remains usable.
    This fallback reopens the *same raw bytes* with the canonical raw reader and
    inventory primitives.  ID rows and any causally available partial 1D/2D
    context are exposed as separate comparison components, never added to the
    frozen canonical-inventory count.
    """
    stack_config = json.loads(stack_config_path.read_text())
    inventory_config = json.loads(inventory_config_path.read_text())
    canonical_dates = {
        _evaluation_date(row) for row in canonical_inventory if _evaluation_date(row)
    }
    fallback_sessions = tuple(session for session in sessions if session not in canonical_dates)
    intraday_output: list[dict[str, Any]] = []
    partial_fixed_output: list[dict[str, Any]] = []
    intraday_cross: list[dict[str, Any]] = []
    partial_fixed_cross: list[dict[str, Any]] = []
    index_symbol = str(stack_config["index_symbol"])
    tolerance = float(inventory_config.get("join_tolerance_seconds", 5))
    bin_points = float(inventory_config["bin_points"])
    for session in fallback_sessions:
        oi = raw_reader.load_oi(data_root / "oi", session)
        futures, futures_expiry, option_expiry = raw_reader.select_contracts(oi, session)
        if not futures:
            raise ValueError(f"Intraday fallback could not select futures for {session}")
        market = raw_reader.load_market(
            data_root / "raw", session, {index_symbol, futures}
        )
        current_frames: dict[str, Any] = {
            "BN_REF_FUT_VOLUME_VPOC": inventory_engine.price_events(
                market, session, futures, index_symbol, tolerance
            )
        }
        joined = inventory_engine.oi_events(
            oi,
            market,
            session,
            futures,
            option_expiry,
            index_symbol,
            tolerance,
        )
        for family in inventory_engine.FAMILIES[1:]:
            current_frames[family] = joined[joined.family == family].copy()

        partial_rows: list[dict[str, Any]] = []
        common = sorted(
            {path.name for path in (data_root / "raw").iterdir() if path.is_dir()}
            & {path.name for path in (data_root / "oi").iterdir() if path.is_dir()}
        )
        prior = [value for value in common if value < session]
        if prior:
            discovery_config = {
                "index_symbol": index_symbol,
                "futures_symbol": futures,
                "discovery_start": prior[0],
                "discovery_end": prior[-1],
                "maximum_missing_oi_minutes": int(
                    inventory_config.get("maximum_missing_oi_minutes", 0)
                ),
            }
            eligibility, _ = inventory_engine.discover_sessions(
                data_root, discovery_config
            )
            accepted = [
                row["date"]
                for row in eligibility
                if row["status"] == "ACCEPTED"
                and row["date"] < session
                and row["date"] != "2026-08-17"
            ]
            chain = accepted[-3:]
            prior_frames: dict[str, dict[str, Any]] = {}
            for source_session in chain:
                source_oi = raw_reader.load_oi(data_root / "oi", source_session)
                source_futures, _, source_option_expiry = raw_reader.select_contracts(
                    source_oi, source_session
                )
                source_market = raw_reader.load_market(
                    data_root / "raw",
                    source_session,
                    {index_symbol, source_futures},
                )
                prior_frames[source_session] = {
                    "price": inventory_engine.price_events(
                        source_market,
                        source_session,
                        source_futures,
                        index_symbol,
                        float(inventory_config.get("join_tolerance_seconds", 5)),
                    ),
                    "oi": inventory_engine.oi_events(
                        source_oi,
                        source_market,
                        source_session,
                        source_futures,
                        source_option_expiry,
                        index_symbol,
                        float(inventory_config.get("join_tolerance_seconds", 5)),
                    ),
                }
            for horizon, count in (("1D", 1), ("2D", 2), ("3D", 3)):
                source_chain = chain[-count:]
                if len(source_chain) < count:
                    continue
                for family in inventory_engine.FAMILIES:
                    parts = [
                        prior_frames[value]["price"]
                        if family == "BN_REF_FUT_VOLUME_VPOC"
                        else prior_frames[value]["oi"][
                            prior_frames[value]["oi"].family == family
                        ]
                        for value in source_chain
                    ]
                    sample = pd.concat(parts, ignore_index=True)
                    profile = inventory_engine.profile(sample, bin_points)
                    if profile is None:
                        continue
                    expiry = (
                        futures_expiry
                        if family.startswith(("BN_", "FUT_"))
                        else option_expiry
                    )
                    partial_rows.append(
                        inventory_engine.record(
                            session,
                            horizon,
                            family,
                            profile["control_value"],
                            "|".join(source_chain),
                            f"{session}T09:15:00+05:30",
                            inventory_engine.iso(sample.receipt_timestamp.max()),
                            futures,
                            expiry,
                            profile["count"],
                            profile["winning_bin_weight"],
                            profile["runner_up_bin"],
                            profile["runner_up_weight"],
                            profile["tie_break_reason"],
                        )
                    )

        intraday_rows: list[dict[str, Any]] = []
        for family in inventory_engine.FAMILIES:
            expiry = (
                futures_expiry
                if family.startswith(("BN_", "FUT_"))
                else option_expiry
            )
            intraday_rows.extend(
                inventory_engine.transitions(
                    current_frames[family], family, session, futures, expiry, bin_points
                )
            )
        # Build together so ordinal-backed transition identities match the
        # live per-session publication, then split only for explicit matrices.
        session_cross = cross_layer_state.build_material_transitions(
            [*partial_rows, *intraday_rows], [], [], [], []
        )
        partial_fixed_output.extend(partial_rows)
        intraday_output.extend(intraday_rows)
        partial_fixed_cross.extend(
            row for row in session_cross if str(row.get("horizon")) != "ID"
        )
        intraday_cross.extend(
            row for row in session_cross if str(row.get("horizon")) == "ID"
        )
    return (
        _jsonable(intraday_output),
        _jsonable(partial_fixed_output),
        _jsonable(intraday_cross),
        _jsonable(partial_fixed_cross),
        fallback_sessions,
    )


def build_clean_batch_availability_detail(
    *,
    snapshot: Mapping[str, Any],
    data_root: Path,
    stack_config_path: Path,
    shadow_config_path: Path,
    sessions: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Independently derive final availability from clean chronological raw bytes."""
    stack = json.loads(stack_config_path.read_text())
    shadow = json.loads(shadow_config_path.read_text())
    limits = shadow.get("freshness_seconds", {})
    if not isinstance(limits, Mapping):
        raise ValueError("shadow freshness_seconds must be a component mapping")
    inventory = [
        *_as_rows(snapshot.get("inventory", [])),
        *_as_rows(snapshot.get("partial_fixed_inventory", [])),
        *_as_rows(snapshot.get("intraday_inventory", [])),
    ]
    result: dict[str, dict[str, Any]] = {}
    for session in sessions:
        oi = raw_reader.load_oi(data_root / "oi", session)
        futures, _, _ = raw_reader.select_contracts(oi, session)
        if not futures:
            raise ValueError(f"clean-B availability could not select futures for {session}")
        market = raw_reader.load_market(
            data_root / "raw",
            session,
            {str(stack["index_symbol"]), futures},
        )
        latest: dict[str, Any] = {}
        accepted_receipts: list[Any] = []
        for kind, symbol in (
            ("INDEX", str(stack["index_symbol"])),
            ("FUTURES", futures),
        ):
            accepted = market[
                (market.symbol == symbol) & market.receipt_timestamp.notna()
            ]
            accepted_receipts.extend(accepted.receipt_timestamp.tolist())
            values = accepted[accepted.last_price.notna()]
            if not values.empty:
                latest[kind] = values.receipt_timestamp.max()
        for kind, instrument_class in (
            ("FUTURES_OI", "future"),
            ("CE", "call"),
            ("PE", "put"),
        ):
            accepted = oi[
                (oi.instrument_class == instrument_class)
                & oi.oi_receipt_timestamp.notna()
            ]
            if kind == "FUTURES_OI":
                accepted = accepted[accepted.symbol == futures]
            accepted_receipts.extend(accepted.oi_receipt_timestamp.tolist())
            values = accepted[accepted.oi_close.notna()]
            if not values.empty:
                latest[kind] = values.oi_receipt_timestamp.max()
        # Production evidence_cutoff is the latest accepted known receipt,
        # including a terminal row whose analytical value is null.  Freshness
        # clocks remain latest *valid-valued* receipts.  Collapsing those two
        # clocks would incorrectly keep an older price/OI fresh.
        reference = max(accepted_receipts, default=None)

        def fresh(kind: str) -> bool:
            if reference is None or kind not in latest:
                return False
            seconds = float(limits.get(kind.lower(), 180))
            age = (reference - latest[kind]).total_seconds()
            return 0 <= age <= seconds

        market_available = fresh("INDEX") and fresh("FUTURES")
        layers: dict[str, context_availability.LayerAvailability] = {}
        for horizon in ("1D", "2D", "3D"):
            present = any(
                _evaluation_date(row) == session
                and str(row.get("horizon")) == horizon
                for row in inventory
            )
            layers[horizon] = context_availability.LayerAvailability(
                horizon,
                "AVAILABLE" if present else "MISSING_PRIOR_SESSION",
                "CACHED_RAW_PRIOR_CONTEXT" if present else "INSUFFICIENT_PRIOR_SESSIONS",
            )
        intraday_present = any(
            _evaluation_date(row) == session and str(row.get("horizon")) == "ID"
            for row in inventory
        )
        layers["ID"] = context_availability.LayerAvailability(
            "ID",
            "AVAILABLE"
            if market_available and intraday_present
            else "STALE_DATA"
            if any(kind in latest for kind in ("INDEX", "FUTURES"))
            else "NOT_YET_AVAILABLE",
            "FRESH_SYNCHRONIZED_MARKET"
            if market_available and intraday_present
            else "MARKET_INPUT_STALE_OR_MISSING",
        )
        participation_available = any(
            fresh(kind) for kind in ("FUTURES_OI", "CE", "PE")
        )
        classified = context_availability.classify_context(
            layers,
            divergence_inputs_available=market_available,
            participation_inputs_available=participation_available,
        )
        if not market_available and any(
            kind in latest for kind in ("INDEX", "FUTURES")
        ):
            classified["divergence_state"] = "STALE_DATA"
        result[session] = _jsonable(
            {
                **classified,
                "layers": {
                    horizon: {"state": layer.state, "reason": layer.reason}
                    for horizon, layer in layers.items()
                },
                "index_state": "AVAILABLE" if fresh("INDEX") else "STALE_OR_MISSING",
                "futures_state": "AVAILABLE"
                if fresh("FUTURES")
                else "STALE_OR_MISSING",
                "futures_oi_state": "AVAILABLE"
                if fresh("FUTURES_OI")
                else "STALE_OR_MISSING",
                "ce_state": "AVAILABLE" if fresh("CE") else "STALE_OR_MISSING",
                "pe_state": "AVAILABLE" if fresh("PE") else "STALE_OR_MISSING",
                "evidence_cutoff_timestamp": reference.isoformat()
                if reference is not None
                else "",
                # B uses its evidence clock as the deterministic calculation
                # reference; calculation/publication wall clocks are excluded
                # from analytical comparison.
                "calculation_timestamp": reference.isoformat()
                if reference is not None
                else "",
                "reference_timestamp": reference.isoformat()
                if reference is not None
                else "",
                "receipt_ages_seconds": {
                    kind: (reference - instant).total_seconds()
                    for kind, instant in latest.items()
                }
                if reference is not None
                else {},
            }
        )
    return result


def rebuild_clean_gui_payload(snapshot: dict[str, Any], sessions: tuple[str, ...]) -> None:
    """Project clean-B rows through the same calculation-free live GUI shape."""
    all_inventory = [
        *_as_rows(snapshot.get("inventory", [])),
        *_as_rows(snapshot.get("partial_fixed_inventory", [])),
        *_as_rows(snapshot.get("intraday_inventory", [])),
    ]
    all_cross = [
        *_as_rows(snapshot.get("cross_layer_transitions", [])),
        *_as_rows(snapshot.get("partial_fixed_cross_layer_transitions", [])),
        *_as_rows(snapshot.get("intraday_cross_layer_transitions", [])),
    ]
    gui = snapshot.setdefault("gui_payload", {})
    for session in sessions:
        payload = dict(gui.get(session, {}))
        detail = snapshot.get("availability_detail", {}).get(session, {})
        if not detail:
            raise ValueError(f"clean-B GUI availability detail missing for {session}")
        payload["schema"] = "R6E_LIVE_SESSION_PAYLOAD_V1"
        payload["classification"] = (
            "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
        )
        payload["date"] = session
        payload["session"] = session
        payload["availability"] = detail
        basis = [
            row
            for row in _as_rows(snapshot.get("basis", []))
            if _evaluation_date(row) == session
            and row.get("validity_status") == "VALID"
        ]
        payload["price"] = gui_adapter._pack(
            [
                {
                    "t": row.get("basis_timestamp", ""),
                    "i": row.get("index_price", ""),
                    "f": row.get("futures_price", ""),
                    "b": row.get("basis_value", ""),
                    "it": row.get("index_receipt_timestamp", ""),
                    "ft": row.get("futures_receipt_timestamp", ""),
                    "a": row.get("absolute_receipt_difference_ms", ""),
                }
                for row in basis
            ]
        )
        payload["inventory"] = gui_adapter._pack(
            [row for row in all_inventory if _evaluation_date(row) == session]
        )
        mechanism_fields = (
            "episode_id",
            "timestamp",
            "availability_timestamp",
            "resolution_mechanism_native",
            "resolution_mechanism_compatibility",
            "signed_basis_convergence",
            "index_contribution",
            "futures_contribution",
            "new_extreme_flag",
            "stalled_extreme_duration_seconds",
        )
        mechanism: list[dict[str, Any]] = []
        prior_mechanism: dict[str, object] = {}
        for row in _as_rows(snapshot.get("resolution", [])):
            if _evaluation_date(row) != session:
                continue
            episode = str(row.get("episode_id", ""))
            value = row.get("resolution_mechanism_native")
            if prior_mechanism.get(episode) == value:
                continue
            prior_mechanism[episode] = value
            mechanism.append(gui_adapter._project(row, mechanism_fields))
        payload["resolution_mechanisms"] = gui_adapter._pack(mechanism)
        for payload_key, snapshot_key in (
            ("participation_dense", "participation_dense"),
            ("participation_transitions", "participation_transitions"),
            ("participation_summaries", "participation_summaries"),
            ("compatibility_snapshots", "compatibility_snapshots"),
        ):
            payload[payload_key] = gui_adapter._pack(
                [
                    row
                    for row in _as_rows(snapshot.get(snapshot_key, []))
                    if _evaluation_date(row) == session
                ]
            )
        payload["cross_layer_transitions"] = gui_adapter._pack(
            [row for row in all_cross if _evaluation_date(row) == session]
        )
        payload["counts"] = {
            key: len(value.get("rows", []))
            for key, value in payload.items()
            if isinstance(value, Mapping) and "rows" in value
        }
        gui[session] = payload


def project_incremental_fallback(
    snapshot: Mapping[str, Any], fallback_sessions: Iterable[str]
) -> dict[str, Any]:
    """Separate A's independently comparable partial-context publication."""
    sessions = set(fallback_sessions)
    projected = dict(snapshot)
    inventory = _as_rows(snapshot.get("inventory", []))
    projected["intraday_inventory"] = [
        row
        for row in inventory
        if _evaluation_date(row) in sessions and str(row.get("horizon")) == "ID"
    ]
    projected["partial_fixed_inventory"] = [
        row
        for row in inventory
        if _evaluation_date(row) in sessions and str(row.get("horizon")) != "ID"
    ]
    projected["inventory"] = [
        row
        for row in inventory
        if _evaluation_date(row) not in sessions
    ]
    cross = _as_rows(snapshot.get("cross_layer_transitions", []))
    projected["intraday_cross_layer_transitions"] = [
        row
        for row in cross
        if _evaluation_date(row) in sessions
        and str(row.get("component")) == "INVENTORY"
        and str(row.get("horizon")) == "ID"
    ]
    projected["partial_fixed_cross_layer_transitions"] = [
        row
        for row in cross
        if _evaluation_date(row) in sessions
        and str(row.get("component")) == "INVENTORY"
        and str(row.get("horizon")) != "ID"
    ]
    projected["cross_layer_transitions"] = [
        row
        for row in cross
        if not (
            _evaluation_date(row) in sessions
            and str(row.get("component")) == "INVENTORY"
        )
    ]
    return projected


def run_clean_canonical_batch(
    *,
    data_root: Path,
    batch_root: Path,
    stack_config_path: Path,
    inventory_config_path: Path,
    sessions: tuple[str, ...],
    shadow_config_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Run B through repository batch processors, never the live checkpoint path."""
    begun = time.monotonic()
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
        ("inventory", [
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
        ]),
        ("stack", [
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
        ]),
        ("layers", [
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
        ]),
    ]
    trace_root = batch_root / "child_open_traces"
    traces = {
        component: trace_root / f"{component}.strace"
        for component, _ in commands
    }
    command_audit = [
        {
            "component": component,
            **_run_repository_command(
                command, repository, trace_path=traces[component]
            ),
        }
        for component, command in commands
    ]
    (batch_root / "canonical_batch_commands.json").write_bytes(_json_bytes(command_audit))
    snapshot = load_canonical_batch_snapshot(
        layout_root=layout,
        data_root=data_root.resolve(),
        stack_config_path=stack_config_path.resolve(),
        sessions=sessions,
    )
    (
        intraday,
        partial_fixed,
        intraday_cross,
        partial_fixed_cross,
        fallback_sessions,
    ) = build_intraday_inventory_fallback(
        data_root=data_root.resolve(),
        stack_config_path=stack_config_path.resolve(),
        inventory_config_path=inventory_config_path.resolve(),
        sessions=sessions,
        canonical_inventory=_as_rows(snapshot.get("inventory", [])),
    )
    snapshot["intraday_inventory"] = intraday
    snapshot["partial_fixed_inventory"] = partial_fixed
    snapshot["intraday_cross_layer_transitions"] = intraday_cross
    snapshot["partial_fixed_cross_layer_transitions"] = partial_fixed_cross
    snapshot["intraday_fallback_sessions"] = list(fallback_sessions)
    snapshot["availability_detail"] = build_clean_batch_availability_detail(
        snapshot=snapshot,
        data_root=data_root.resolve(),
        stack_config_path=stack_config_path.resolve(),
        shadow_config_path=(
            shadow_config_path.resolve()
            if shadow_config_path is not None
            else repository / "configs/r6e_shadow.json"
        ),
        sessions=sessions,
    )
    rebuild_clean_gui_payload(snapshot, sessions)
    snapshot["analytical_ledgers"] = build_batch_analytical_ledgers(snapshot)
    open_rows = child_open_audit_rows(
        traces=traces,
        data_root=data_root.resolve(),
        generated_root=layout,
        repository=repository,
        config_paths=(stack_config_path, inventory_config_path),
    )
    metrics = {
        "schedule": "independent_clean_canonical_batch",
        "processor_count": len(commands),
        "command_returncodes": [row["returncode"] for row in command_audit],
        "intraday_fallback_sessions": list(fallback_sessions),
        "intraday_fallback_rows": len(intraday),
        "partial_fixed_fallback_rows": len(partial_fixed),
        "intraday_fallback_cross_layer_rows": len(intraday_cross),
        "partial_fixed_fallback_cross_layer_rows": len(partial_fixed_cross),
        "elapsed_seconds": time.monotonic() - begun,
        "peak_rss_kib_child_processes": resource.getrusage(
            resource.RUSAGE_CHILDREN
        ).ru_maxrss,
        "semantic_hash": named_rows_semantic_hash(component_rows(snapshot)),
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
    "response_observations",
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
        "responses": selected(native / "raw_response_observations.csv"),
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
    component_names = tuple(components)
    compare_availability = "availability_states" in component_names
    targets = {
        "incremental_a": reference_component_rows(
            a_snapshot,
            availability_mode="incremental" if compare_availability else None,
        ),
        "batch_b": reference_component_rows(
            b_snapshot,
            availability_mode="canonical" if compare_availability else None,
        ),
    }
    reference = reference_component_rows(
        reference_snapshot,
        availability_mode="canonical" if compare_availability else None,
    )
    rows = []
    for component in component_names:
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


def compare_gui_visual_authority(
    *,
    a_snapshot: Mapping[str, Any],
    b_snapshot: Mapping[str, Any],
    reference_snapshot: Mapping[str, Any],
    reference_name: str,
) -> list[dict[str, Any]]:
    """Compare live GUI rows to R6D, allowing only required live supersets.

    R6D intentionally compressed price/resolution/cross-layer history and was
    created before partial-context live degradation.  Every R6D-visible row
    must remain present with every R6D-published field exact.  Additional live
    rows are permitted only for those four documented projections; all other
    GUI components remain exact multisets.
    """
    live_supersets = {
        "price",
        "inventory",
        "resolution_mechanisms",
        "cross_layer_transitions",
        "display_metadata",
        "availability_instruments",
    }
    target_snapshots = {
        "incremental_a": a_snapshot,
        "batch_b": b_snapshot,
    }
    targets = {
        name: snapshot.get("gui_payload", {})
        for name, snapshot in target_snapshots.items()
    }
    historical_availability: dict[str, dict[str, list[dict[str, Any]]]] = {}
    reference_payloads = reference_snapshot.get("gui_payload", {})
    if not isinstance(reference_payloads, Mapping):
        raise ValueError("R6D visual authority payload is not session keyed")
    rows: list[dict[str, Any]] = []
    for session, raw_reference in sorted(reference_payloads.items()):
        reference = _gui_projection(raw_reference)
        for target_name, payloads in targets.items():
            if not isinstance(payloads, Mapping) or session not in payloads:
                rows.append(
                    {
                        "reference": reference_name,
                        "session": session,
                        "component": "GUI_SESSION",
                        "target": target_name,
                        "reference_count": 1,
                        "target_count": 0,
                        "matched_rows": 0,
                        "target_only": 0,
                        "reference_only": 1,
                        "permitted_live_extension_rows": 0,
                        "unexplained_remainder": 1,
                        "status": "FAIL",
                    }
                )
                continue
            target = _gui_projection(payloads[session])
            for component in sorted(reference.keys() | target.keys()):
                if component == "public_contract_metadata":
                    # R6D's legacy schema identifier is packaging authority,
                    # while the complete A/B gate above requires the R6E live
                    # public schema and classification to match exactly.
                    continue
                if component == "counts":
                    # R6D compressed several live supersets, so its aggregate
                    # values cannot be compared as row subsets.  The complete
                    # A/B GUI projection gate still compares every normalized
                    # count exactly; the individual R6D-visible artifacts are
                    # checked above instead.
                    continue
                reference_rows = reference.get(component, [])
                target_rows = target.get(component, [])
                if component == "availability" and reference_rows:
                    # The frozen R6D payload records the same historical
                    # material-eligibility surface as R6C2. A/B GUI payloads
                    # deliberately expose the newer operational as-of surface,
                    # which can finish STALE_DATA after the last quote. Derive
                    # the like-for-like R6D compatibility rows from each sealed
                    # target independently; never compare the operational rows
                    # to a different reference contract or use B to project A.
                    if target_name not in historical_availability:
                        mode = (
                            "incremental"
                            if target_name == "incremental_a"
                            else "canonical"
                        )
                        by_session: dict[str, list[dict[str, Any]]] = {}
                        for row in _historical_reference_availability_projection(
                            target_snapshots[target_name], mode=mode
                        ):
                            by_session.setdefault(_evaluation_date(row), []).append(row)
                        historical_availability[target_name] = by_session
                    target_rows = historical_availability[target_name].get(
                        str(session), []
                    )
                if component == "display_metadata":
                    # R6D predates sanitized operational chart metadata.  Its
                    # visual authority here is the displayed session identity;
                    # exact as-of/display/stale clocks are gated A/B through
                    # the production /api/chart projection above.
                    fields = {"date", "session_date"}
                elif component == "availability_instruments":
                    # R6D's packed layer table has no instrument receipt-age
                    # contract.  Preserve the session mapping only; A/B exact
                    # comparison owns the new instrument states and ages.
                    fields = {"date"}
                else:
                    fields = {
                        field
                        for row in reference_rows
                        for field, value in row.items()
                        if value not in (None, "", {}, [])
                    }
                if fields:
                    left = _reference_counter(target_rows, fields)
                    right = _reference_counter(reference_rows, fields)
                else:
                    left = Counter({"__TARGET_ROW__": len(target_rows)}) if target_rows else Counter()
                    right = Counter()
                target_only = sum((left - right).values())
                reference_only = sum((right - left).values())
                permitted = target_only if component in live_supersets else 0
                remainder = reference_only + (0 if component in live_supersets else target_only)
                rows.append(
                    {
                        "reference": reference_name,
                        "session": session,
                        "component": component,
                        "target": target_name,
                        "canonical_fields": "|".join(sorted(fields)),
                        "target_count": len(target_rows),
                        "reference_count": len(reference_rows),
                        "matched_rows": sum((left & right).values()),
                        "target_only": target_only,
                        "reference_only": reference_only,
                        "permitted_live_extension_rows": permitted,
                        "unexplained_remainder": remainder,
                        "status": "PASS" if remainder == 0 else "FAIL",
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
        "analytical_semantic_sha256": named_rows_semantic_hash(
            component_rows(snapshot)
        ),
        "analytical_ledgers_sha256": named_rows_semantic_hash(
            analytical_ledger_rows(snapshot)
        ),
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


def expected_record_group_sequence(
    total_records: int, groups: tuple[int, ...]
) -> tuple[int, str]:
    digest = hashlib.sha256()
    remaining = total_records
    count = 0
    while remaining > 0:
        size = min(groups[count % len(groups)], remaining)
        digest.update(f"{size},".encode())
        remaining -= size
        count += 1
    return count, digest.hexdigest()


def schedule_exercise_failures(
    name: str, seal: Mapping[str, Any]
) -> list[str]:
    """Return truthful failures when a named adversarial schedule was inert."""
    failures: list[str] = []
    if name not in SCHEDULES:
        return failures
    source_records = int(seal.get("source_json_records", 0) or 0)
    exposed_records = int(seal.get("exposed_records", 0) or 0)
    poll_calls = int(seal.get("poll_calls_by_harness", 0) or 0)
    if source_records <= 0:
        failures.append("NO_SOURCE_RECORDS")
    if exposed_records != source_records:
        failures.append("NOT_ALL_SOURCE_RECORDS_EXPOSED")
    if poll_calls <= 0:
        failures.append("NO_PRODUCTION_POLLS")
    if int(seal.get("causal_checkpoint_remainders_after_drain", 0) or 0) != 0:
        failures.append("CAUSAL_CHECKPOINT_REMAINDER_AFTER_DRAIN")

    if name == "original_source_chunks":
        counts = {
            str(key): int(value)
            for key, value in dict(
                seal.get("original_checkpoint_chunk_counts", {})
            ).items()
        }
        delta_bytes = {
            str(key): int(value)
            for key, value in dict(
                seal.get("original_checkpoint_delta_bytes", {})
            ).items()
        }
        source_sizes = {
            str(key): int(value)
            for key, value in dict(seal.get("source_sizes_by_relative", {})).items()
        }
        read_limit = int(seal.get("maximum_exposure_bytes", 0) or 0)
        exact_chunks = (
            source_sizes
            and delta_bytes == source_sizes
            and set(counts) == set(source_sizes)
            and int(seal.get("original_source_chunk_count", 0) or 0)
            == sum(counts.values())
            and int(seal.get("original_checkpoint_delta_oversize_count", 0) or 0)
            == 0
            and read_limit > 0
            and all(
                counts[path] >= (size + read_limit - 1) // read_limit
                for path, size in source_sizes.items()
            )
        )
        if not exact_chunks:
            failures.append("NATIVE_CHECKPOINT_CHUNK_ACCOUNTING_NOT_EXACT")
        if int(
            seal.get("original_source_files_staged_before_first_poll", 0) or 0
        ) != int(seal.get("source_files", 0) or 0):
            failures.append("ALL_SOURCE_FILES_NOT_STAGED_BEFORE_FIRST_POLL")
    elif name == "one_record_per_increment":
        sizes = {int(value) for value in seal.get("record_group_sizes_exercised", [])}
        if sizes != {1} or int(seal.get("record_increment_count", 0) or 0) != source_records:
            failures.append("ONE_RECORD_INCREMENT_NOT_EXERCISED_FOR_FULL_STREAM")
    elif name == "deterministic_variable_chunks":
        expected_count, expected_hash = expected_record_group_sequence(
            source_records, SCHEDULES[name].line_groups
        )
        if (
            int(seal.get("record_increment_count", 0) or 0) != expected_count
            or str(seal.get("record_group_sequence_sha256", "")) != expected_hash
        ):
            failures.append("EXACT_DETERMINISTIC_VARIABLE_SEQUENCE_NOT_EXERCISED")
    elif name == "boundaries_inside_jsonl_lines":
        expected = len(
            _fraction_thresholds(source_records, SCHEDULES[name].split_events)
        )
        if int(seal.get("split_line_boundary_count", 0) or 0) != expected:
            failures.append("CONFIGURED_INSIDE_LINE_BOUNDARIES_NOT_MEASURED")
    elif name == "empty_repeated_polls":
        configured = SCHEDULES[name]
        expected = len(
            _fraction_thresholds(source_records, configured.empty_poll_events)
        ) * configured.empty_polls
        if int(seal.get("explicit_empty_poll_count", 0) or 0) != expected:
            failures.append("CONFIGURED_REPEATED_EMPTY_POLLS_NOT_MEASURED")
    elif name == "multiple_checkpoint_restarts":
        expected = len(
            _fraction_thresholds(source_records, SCHEDULES[name].restart_events)
        )
        if int(seal.get("checkpoint_restart_count", 0) or 0) != expected:
            failures.append("CONFIGURED_CHECKPOINT_RESTARTS_NOT_MEASURED")
    elif name == "analytical_boundary_restarts":
        probe = seal.get("analytical_boundary_probe", {})
        if not isinstance(probe, Mapping) or not probe.get("measured"):
            failures.append("ANALYTICAL_BOUNDARY_NOT_MEASURED")
        elif not (
            int(probe.get("restart_count", 0) or 0) > 0
            and probe.get("crash_covered_ledgers")
            == probe.get("material_ledgers_with_rows")
            and int(probe.get("durable_occurrences_before_restart", 0) or 0) == 1
            and int(probe.get("durable_occurrences_after_restart", 0) or 0) == 1
            and int(probe.get("occurrences_after_retry_and_seal", 0) or 0) == 1
            and probe.get("exactly_once_after_seal") is True
            and all(
                isinstance(event, Mapping)
                and int(event.get("durable_occurrences_before_restart", 0) or 0) == 1
                and int(event.get("durable_occurrences_after_restart", 0) or 0) == 1
                and int(event.get("occurrences_after_retry_and_seal", 0) or 0) == 1
                and event.get("exactly_once_after_seal") is True
                for event in probe.get("events", [])
            )
        ):
            failures.append("ANALYTICAL_BOUNDARY_NOT_EXACTLY_ONCE")
    elif name == "hourly_file_rotation":
        expected = int(seal.get("expected_hourly_rotation_boundaries", 0) or 0)
        observed = int(seal.get("hourly_rotation_boundary_count", 0) or 0)
        if expected <= 0 or observed != expected:
            failures.append("ALL_POST_POLL_HOURLY_PATH_INTRODUCTIONS_NOT_MEASURED")
    elif name == "large_chronological_chunks":
        sizes = [int(value) for value in seal.get("record_group_sizes_exercised", [])]
        target_records = min(SCHEDULES[name].line_groups[0], source_records)
        byte_limit = int(seal.get("maximum_exposure_bytes", 0) or 0)
        maximum_bytes = int(seal.get("maximum_record_group_bytes", 0) or 0)
        record_target_reached = bool(sizes) and max(sizes) >= target_records
        # A complete JSONL record can approach the configured 1 MiB line
        # buffer, so a bounded group may have to stop one record below the
        # 4 MiB poll limit.  Filling at least 75% of that production limit is a
        # measured multi-megabyte chronological increment, not a token >1-row
        # exercise.
        byte_target_reached = byte_limit > 0 and maximum_bytes >= int(byte_limit * 0.75)
        if source_records > 1 and not (record_target_reached or byte_target_reached):
            failures.append("LARGE_CHRONOLOGICAL_TARGET_NOT_MEASURED")
        configured_refreshes = int(
            SCHEDULES[name].analytical_flush_events_per_session
        )
        evaluation_sessions = int(
            seal.get("analytical_refresh_evaluation_session_count", 0) or 0
        )
        evaluation_session_names = [
            str(value)
            for value in seal.get(
                "analytical_refresh_evaluation_sessions", []
            )
        ]
        expected_refreshes = configured_refreshes * evaluation_sessions
        if (
            evaluation_sessions <= 0
            or len(evaluation_session_names) != evaluation_sessions
            or len(set(evaluation_session_names)) != evaluation_sessions
            or int(
            seal.get("analytical_refresh_events_per_session", 0) or 0
            ) != configured_refreshes
            or int(
            seal.get("analytical_refresh_expected_count", 0) or 0
            ) != expected_refreshes
        ):
            failures.append("PER_SESSION_ANALYTICAL_REFRESH_PLAN_NOT_EXACT")
        if int(seal.get("analytical_refresh_flush_count", 0) or 0) != expected_refreshes:
            failures.append("PERIODIC_ANALYTICAL_REFRESH_COUNT_NOT_EXACT")
        if int(
            seal.get("analytical_refresh_nonempty_count", 0) or 0
        ) != expected_refreshes:
            failures.append("PERIODIC_ANALYTICAL_REFRESH_TARGET_NOT_COMPUTED")
        recomputed_targets = {
            str(value)
            for value in seal.get(
                "analytical_refresh_recomputed_target_sessions", []
            )
        }
        if configured_refreshes > 1 and recomputed_targets != set(
            evaluation_session_names
        ):
            failures.append("PERIODIC_ANALYTICAL_RECOMPUTATION_NOT_EXERCISED")
        trace = [
            row
            for row in seal.get("analytical_refresh_trace", [])
            if isinstance(row, Mapping)
        ]
        plan = [
            row
            for row in seal.get("analytical_refresh_plan", [])
            if isinstance(row, Mapping)
        ]
        if len(trace) != expected_refreshes or len(plan) != expected_refreshes:
            failures.append("PERIODIC_ANALYTICAL_REFRESH_TRACE_NOT_EXACT")
        trace_counts = Counter(str(row.get("session_date", "")) for row in trace)
        if (
            set(trace_counts) != set(evaluation_session_names)
            or any(value != configured_refreshes for value in trace_counts.values())
        ):
            failures.append("PER_SESSION_ANALYTICAL_REFRESH_COUNT_NOT_EXACT")
        plan_by_session: dict[str, list[Mapping[str, Any]]] = {}
        for row in plan:
            plan_by_session.setdefault(str(row.get("session_date", "")), []).append(
                row
            )
        plan_structure_exact = set(plan_by_session) == set(
            evaluation_session_names
        )
        session_record_total = 0
        for session in evaluation_session_names:
            rows = sorted(
                plan_by_session.get(session, []),
                key=lambda row: int(row.get("session_generation", 0) or 0),
            )
            counts = {
                int(row.get("session_record_count", 0) or 0) for row in rows
            }
            total = next(iter(counts)) if len(counts) == 1 else 0
            expected_locals = [
                (total * generation) // (configured_refreshes + 1)
                for generation in range(1, configured_refreshes + 1)
            ] if total > 0 else []
            plan_structure_exact = plan_structure_exact and (
                [
                    int(row.get("session_generation", 0) or 0)
                    for row in rows
                ]
                == list(range(1, configured_refreshes + 1))
                and [
                    int(row.get("session_record_ordinal", 0) or 0)
                    for row in rows
                ]
                == expected_locals
                and len(set(expected_locals)) == configured_refreshes
            )
            session_record_total += total
        global_ordinals = [
            int(row.get("global_record_ordinal", 0) or 0) for row in plan
        ]
        plan_structure_exact = plan_structure_exact and (
            session_record_total == source_records
            and global_ordinals == sorted(global_ordinals)
            and len(set(global_ordinals)) == expected_refreshes
            and all(0 < value <= source_records for value in global_ordinals)
        )
        if not plan_structure_exact:
            failures.append("PER_SESSION_ANALYTICAL_REFRESH_PLAN_STRUCTURE_INVALID")
        trace_contract_fields = (
            "exact_threshold_discharge",
            "distinct_poll_generation",
            "target_was_dirty",
            "flush_returned_target",
            "accepted_observation_count_advanced",
            "causal_evidence_cutoff_advanced",
            "valid_basis_cutoff_advanced",
        )
        if any(
            not all(row.get(field) is True for field in trace_contract_fields)
            for row in trace
        ):
            failures.append("PERIODIC_ANALYTICAL_REFRESH_CAUSAL_TRACE_FAILED")
        plan_keys = (
            "session_date",
            "session_generation",
            "session_record_ordinal",
            "session_record_count",
            "global_record_ordinal",
        )
        if [
            tuple(row.get(key) for key in plan_keys) for row in trace
        ] != [
            tuple(row.get(key) for key in plan_keys) for row in plan
        ]:
            failures.append("PERIODIC_ANALYTICAL_REFRESH_PLAN_TRACE_MISMATCH")
        if seal.get(
            "analytical_refresh_episode_boundary_missing_ids", []
        ):
            failures.append("PERIODIC_EPISODE_BOUNDARY_UPDATE_MISSING")
        if seal.get(
            "analytical_refresh_lifecycle_boundary_missing_ids", []
        ):
            failures.append("PERIODIC_LIFECYCLE_BOUNDARY_UPDATE_MISSING")
        for family in ("episode", "lifecycle"):
            opportunities = list(seal.get(
                f"analytical_refresh_{family}_boundary_opportunity_ids", []
            ))
            observed = list(seal.get(
                f"analytical_refresh_{family}_boundary_observed_ids", []
            ))
            missing = list(seal.get(
                f"analytical_refresh_{family}_boundary_missing_ids", []
            ))
            if (
                set(observed) - set(opportunities)
                or set(missing) != set(opportunities) - set(observed)
            ):
                failures.append(
                    f"PERIODIC_{family.upper()}_BOUNDARY_SET_INCONSISTENT"
                )
            if int(seal.get(
                f"analytical_refresh_{family}_boundary_opportunity_count", -1
            )) != len(opportunities) or int(seal.get(
                f"analytical_refresh_{family}_boundary_observed_count", -1
            )) != len(observed):
                failures.append(
                    f"PERIODIC_{family.upper()}_BOUNDARY_COUNT_INCONSISTENT"
                )
            status = str(
                seal.get(
                    f"analytical_refresh_{family}_boundary_status", ""
                )
            )
            expected_status = (
                "EXERCISED"
                if opportunities
                else "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
            )
            if status != expected_status:
                failures.append(
                    f"PERIODIC_{family.upper()}_BOUNDARY_STATUS_INCONSISTENT"
                )
        if int(
            seal.get("analytical_refresh_timestamp_backdating", 0) or 0
        ) != 0:
            failures.append("PERIODIC_TIMESTAMP_BACKDATING_DETECTED")
        if int(
            seal.get("analytical_refresh_duplicate_analytical_ids", 0) or 0
        ) != 0:
            failures.append("PERIODIC_DUPLICATE_ANALYTICAL_ID_DETECTED")
        if int(seal.get("analytical_refresh_future_joins", 0) or 0) != 0:
            failures.append("PERIODIC_FUTURE_JOIN_DETECTED")
        if int(
            seal.get(
                "analytical_refresh_synchronization_tolerance_violations", 0
            ) or 0
        ) != 0:
            failures.append("PERIODIC_SYNCHRONIZATION_TOLERANCE_VIOLATION")
    return failures


def scheduling_comparison(
    canonical_seal: Mapping[str, Any], variants: Iterable[tuple[str, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    canonical_hash = str(canonical_seal["analytical_semantic_sha256"])
    canonical_ledger_hash = str(canonical_seal.get("analytical_ledgers_sha256", ""))
    rows = []
    for name, seal in variants:
        state_equal = seal.get("analytical_semantic_sha256") == canonical_hash
        ledgers_equal = seal.get("analytical_ledgers_sha256", "") == canonical_ledger_hash
        canonical_refusals = int(canonical_seal.get("analytical_refusals", 0))
        schedule_refusals = int(seal.get("analytical_refusals", 0))
        refusals_clear = canonical_refusals == schedule_refusals == 0
        exercise_failures = schedule_exercise_failures(name, seal)
        rows.append({
            "schedule": name,
            "canonical_a_hash": canonical_hash,
            "schedule_hash": seal.get("analytical_semantic_sha256", ""),
            "canonical_a_ledger_hash": canonical_ledger_hash,
            "schedule_ledger_hash": seal.get("analytical_ledgers_sha256", ""),
            "canonical_a_analytical_refusals": canonical_refusals,
            "schedule_analytical_refusals": schedule_refusals,
            "schedule_exercise_failures": "|".join(exercise_failures),
            "differences": (
                int(not state_equal)
                + int(not ledgers_equal)
                + int(not refusals_clear)
                + len(exercise_failures)
            ),
            "status": "PASS"
            if state_equal and ledgers_equal and refusals_clear and not exercise_failures
            else "FAIL",
            "reason": "IDENTICAL_SESSION_FINALIZED_ANALYTICAL_STATE"
            if state_equal and ledgers_equal and refusals_clear and not exercise_failures
            else "SCHEDULE_NOT_EXERCISED"
            if exercise_failures
            else "SCHEDULE_DEPENDENT_ANALYTICAL_STATE",
        })
    return rows


def estimate_schedule_work(
    schedule: Schedule, sources: Iterable[SourceFile], maximum_polls: int
) -> dict[str, Any]:
    """Conservative work estimate used only to decide feasible execution mode."""
    sources = list(sources)
    records = sum(
        source.json_records if source.json_records is not None else source.complete_rows
        for source in sources
    )
    groups = schedule.line_groups or (1,)
    average_group = sum(groups) / len(groups)
    data_polls = int((records + average_group - 1) // average_group)
    if schedule.split_inside_lines:
        split_count = len(_fraction_thresholds(records, schedule.split_events))
        data_polls += 3 * split_count
    empty_polls = (
        len(_fraction_thresholds(records, schedule.empty_poll_events))
        if schedule.empty_poll_events
        else int((records + average_group - 1) // average_group)
    ) * schedule.empty_polls
    estimated_polls = data_polls + empty_polls
    minimum_fsyncs = records + data_polls
    return {
        "schedule": schedule.name,
        "source_records": records,
        "source_physical_rows": sum(source.complete_rows for source in sources),
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


def frozen_count_gate_satisfied(
    sessions: Iterable[str], *, disabled: bool
) -> bool:
    """A six-session verification can never pass with frozen counts disabled."""
    return tuple(sessions) != SESSIONS or not disabled


def _new_output_root(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.exists():
        raise ValueError("output root must not exist")
    resolved.mkdir(parents=True)
    return resolved


def runtime_open_audit_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Gate only observed reader/audit-hook opens, never declarations."""
    materialized = list(rows)
    a_b_runtime = [
        row
        for row in materialized
        if str(row.get("run", "")) in {"incremental_a", "batch_b"}
        or str(row.get("run", "")).startswith("schedule:")
    ]
    trusted = {
        "PYTHON_SYS_AUDIT_HOOK_OPEN",
        "LINUX_STRACE_SUCCESSFUL_READ_OPEN",
    }
    unmeasured = [
        row
        for row in a_b_runtime
        if not str(row.get("classification", "")).strip()
        or str(row.get("evidence_source", "")) not in trusted
        or int(row.get("observed_open_count") or 0) <= 0
        or str(row.get("status", "PASS")) == "FAIL"
        or "UNMEASURED" in str(row.get("classification", "")).upper()
    ]
    prohibited = [
        row
        for row in a_b_runtime
        if "PROHIBITED" in str(row.get("classification", "")).upper()
        or "DERIVED_ANALYTICAL_INPUT" in str(row.get("classification", "")).upper()
    ]
    observed_scopes = {str(row.get("run", "")) for row in a_b_runtime}
    return {
        "measured": {"incremental_a", "batch_b"}.issubset(observed_scopes)
        and not unmeasured,
        "audited_rows": len(materialized),
        "a_b_runtime_rows": len(a_b_runtime),
        "unmeasured_rows": len(unmeasured),
        "prohibited_rows": len(prohibited),
    }


def post_run_source_hash_rows(
    *,
    analytical_sources: Iterable[SourceFile],
    analytical_hashes_before: Mapping[str, str],
    projection_manifest: Mapping[str, Any] | None,
    focused_fixture_source: Path | None,
) -> list[dict[str, Any]]:
    """Re-hash raw authorities only after every A/B/schedule consumer closes."""
    rows: list[dict[str, Any]] = []
    if projection_manifest is not None:
        for source in projection_manifest.get("source_files", []):
            path = Path(str(source["path"]))
            stat = path.stat()
            digest = _sha256_file(path)
            unchanged = (
                digest == source.get("sha256_before")
                and stat.st_size == int(source.get("bytes_before", -1))
                and stat.st_mtime_ns == int(source.get("mtime_ns_before", -1))
            )
            rows.append(
                {
                    "source_kind": "AUTHORITATIVE_RAW_SOURCE",
                    "path": str(path),
                    "relative_path": source.get("relative_path", ""),
                    "sha256_before": source.get("sha256_before", ""),
                    "sha256_after_all_runs": digest,
                    "bytes_before": source.get("bytes_before", ""),
                    "bytes_after_all_runs": stat.st_size,
                    "mtime_ns_before": source.get("mtime_ns_before", ""),
                    "mtime_ns_after_all_runs": stat.st_mtime_ns,
                    "unchanged_after_all_runs": unchanged,
                    "status": "PASS" if unchanged else "FAIL",
                }
            )
        collector = Path(str(projection_manifest["collector_root"]))
        for source in projection_manifest.get("projection_files", []):
            path = collector / str(source["relative_path"])
            stat = path.stat()
            digest = _sha256_file(path)
            unchanged = digest == source.get("sha256") and stat.st_size == int(
                source.get("bytes", -1)
            )
            rows.append(
                {
                    "source_kind": "BYTE_EXACT_RAW_PROJECTION",
                    "path": str(path),
                    "relative_path": source.get("relative_path", ""),
                    "sha256_before": source.get("sha256", ""),
                    "sha256_after_all_runs": digest,
                    "bytes_before": source.get("bytes", ""),
                    "bytes_after_all_runs": stat.st_size,
                    "mtime_ns_before": "",
                    "mtime_ns_after_all_runs": stat.st_mtime_ns,
                    "unchanged_after_all_runs": unchanged,
                    "status": "PASS" if unchanged else "FAIL",
                }
            )
        return rows
    if focused_fixture_source is not None:
        _validate_authorized_focused_fixture(focused_fixture_source.resolve())
        manifest = json.loads((focused_fixture_source.parent / "manifest.json").read_text())
        for source in manifest.get("source_files", []):
            path = Path(str(source["path"]))
            stat = path.stat()
            digest = _sha256_file(path)
            unchanged = (
                digest == source.get("sha256")
                and stat.st_size == int(source.get("size", -1))
                and stat.st_mtime_ns == int(source.get("mtime_ns_before", -1))
            )
            rows.append(
                {
                    "source_kind": "AUTHORIZED_FOCUSED_AUTHORITATIVE_SOURCE",
                    "path": str(path),
                    "relative_path": source.get("relative_path", ""),
                    "sha256_before": source.get("sha256", ""),
                    "sha256_after_all_runs": digest,
                    "bytes_before": source.get("size", ""),
                    "bytes_after_all_runs": stat.st_size,
                    "mtime_ns_before": source.get("mtime_ns_before", ""),
                    "mtime_ns_after_all_runs": stat.st_mtime_ns,
                    "unchanged_after_all_runs": unchanged,
                    "status": "PASS" if unchanged else "FAIL",
                }
            )
        return rows
    for source in analytical_sources:
        path = source.source
        digest = _sha256_file(path)
        before = analytical_hashes_before[str(path)]
        unchanged = digest == before and path.stat().st_size == source.size
        rows.append(
            {
                "source_kind": "DIRECT_PHYSICAL_RAW_SOURCE",
                "path": str(path),
                "relative_path": str(source.relative),
                "sha256_before": before,
                "sha256_after_all_runs": digest,
                "bytes_before": source.size,
                "bytes_after_all_runs": path.stat().st_size,
                "mtime_ns_before": "",
                "mtime_ns_after_all_runs": path.stat().st_mtime_ns,
                "unchanged_after_all_runs": unchanged,
                "status": "PASS" if unchanged else "FAIL",
            }
        )
    return rows


def main() -> int:
    global AUTHORIZED_FOCUSED_FIXTURE_ROOT
    harness_begun = time.monotonic()
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
    )
    parser.add_argument(
        "--r6d-reference-root",
        type=Path,
    )
    parser.add_argument(
        "--authorized-focused-fixture-root",
        type=Path,
        help="exact manifest-pinned research fixture root, when explicitly used",
    )
    parser.add_argument("--skip-references", action="store_true")
    parser.add_argument("--sessions", default=",".join(SESSIONS))
    parser.add_argument(
        "--schedules",
        default=",".join(REQUIRED_SCHEDULES),
    )
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument(
        "--build-raw-projection",
        action="store_true",
        help="build one byte-exact raw-record projection from --data-root for both A and B",
    )
    parser.add_argument(
        "--projection-root",
        type=Path,
        help="new non-research temporary root for --build-raw-projection",
    )
    parser.add_argument(
        "--use-existing-projection-manifest",
        type=Path,
        help=(
            "reuse a prior projection only after full manifest, provenance, "
            "projection-file, authoritative-source and dynamic-contract validation"
        ),
    )
    parser.add_argument(
        "--retain-staging",
        action="store_true",
        help="retain per-schedule staged raw copies (large; off by default)",
    )
    parser.add_argument(
        "--retain-variant-snapshots",
        action="store_true",
        help="retain large noncanonical schedule snapshots (off by default)",
    )
    parser.add_argument("--no-expected-count-gate", action="store_true")
    parser.add_argument(
        "--schedule-profile", choices=("required", "feasible"), default="required"
    )
    parser.add_argument("--maximum-feasible-polls", type=int, default=50_000)
    args = parser.parse_args()

    AUTHORIZED_FOCUSED_FIXTURE_ROOT = (
        args.authorized_focused_fixture_root.resolve()
        if args.authorized_focused_fixture_root is not None
        else None
    )

    if args.maximum_feasible_polls <= 0:
        parser.error("--maximum-feasible-polls must be positive")

    sessions = _parse_sessions(args.sessions)
    if not args.skip_references and (
        args.r6c2_reference_root is None or args.r6d_reference_root is None
    ):
        parser.error(
            "--r6c2-reference-root and --r6d-reference-root are required "
            "unless --skip-references is used"
        )
    missing_configs = [
        str(path)
        for path in (args.config, args.stack_config, args.inventory_config)
        if not path.is_file()
    ]
    if missing_configs:
        raise SystemExit(f"configuration missing: {missing_configs}")
    try:
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

    try:
        projection_manifest: dict[str, Any] | None = None
        analytical_data_root = args.data_root.resolve()
        focused_fixture_source: Path | None = None
        if args.build_raw_projection and args.use_existing_projection_manifest is not None:
            raise ValueError(
                "--build-raw-projection and --use-existing-projection-manifest are exclusive"
            )
        if args.build_raw_projection:
            projection_root = (
                args.projection_root.resolve()
                if args.projection_root is not None
                else work / "raw_projection"
            )
            if "research" in projection_root.parts:
                raise ValueError("raw projection root must not be under research")
            projection_manifest = build_raw_projection(
                data_root=args.data_root,
                projection_root=projection_root,
                sessions=sessions,
            )
            analytical_data_root = Path(projection_manifest["collector_root"])
            shutil.copy2(
                projection_manifest["manifest_path"],
                output / "raw_projection_manifest.json",
            )
            shutil.copy2(
                projection_manifest["provenance_path"],
                output / "raw_projection_provenance.jsonl",
            )
            _write_csv(
                output / "source_hash_comparison.csv",
                projection_manifest["source_files"],
            )
        elif args.use_existing_projection_manifest is not None:
            if args.projection_root is not None:
                raise ValueError(
                    "--projection-root cannot be used with --use-existing-projection-manifest"
                )
            projection_manifest = validate_existing_raw_projection(
                manifest_path=args.use_existing_projection_manifest,
                data_root=args.data_root,
                sessions=sessions,
            )
            analytical_data_root = Path(projection_manifest["collector_root"])
            shutil.copy2(
                projection_manifest["manifest_path"],
                output / "raw_projection_manifest.json",
            )
            shutil.copy2(
                projection_manifest["provenance_path"],
                output / "raw_projection_provenance.jsonl",
            )
            (output / "raw_projection_reuse_validation.json").write_bytes(
                _json_bytes(projection_manifest["reuse_validation"])
            )
            _write_csv(
                output / "source_hash_comparison.csv",
                projection_manifest["source_files"],
            )
        elif args.projection_root is not None:
            raise ValueError("--projection-root requires --build-raw-projection")
        elif (
            AUTHORIZED_FOCUSED_FIXTURE_ROOT is not None
            and analytical_data_root == AUTHORIZED_FOCUSED_FIXTURE_ROOT.resolve()
        ):
            # The canonical batch inventory engine correctly refuses every
            # research-root input.  Validate the sole authorized fixture in
            # place, then give A and B the same exact-byte temporary copy under
            # the non-research work root.
            _validate_authorized_focused_fixture(analytical_data_root)
            focused_fixture_source = analytical_data_root
            focused_manifest = json.loads(
                (focused_fixture_source.parent / "manifest.json").read_text()
            )
            analytical_data_root = work / "focused_fixture_collector"
            shutil.copytree(focused_fixture_source, analytical_data_root)
            # ``discover_sources`` must distinguish actual JSON records from
            # the blank physical rows that retain authoritative source-row
            # coordinates.  Materialize a local, non-authoritative scheduling
            # contract from the already pinned and fully validated fixture
            # manifest.  A and B still consume only the copied collector bytes.
            (work / "projection_manifest.json").write_bytes(
                _json_bytes(
                    {
                        "schema": "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1",
                        "collector_root": str(analytical_data_root.resolve()),
                        "source_mutations": 0,
                        "projection_files": focused_manifest["collector_files"],
                    }
                )
            )

        focused_equivalence = (
            focused_fixture_source is not None and sessions == ("2026-08-19",)
        )

        all_sources = discover_sources(
            analytical_data_root, sessions, include_predecessors=True
        )
        sources = discover_sources(
            analytical_data_root, sessions, include_predecessors=False
        )
        live_relatives = {source.relative for source in sources}
        context_sources = [
            source for source in all_sources if source.relative not in live_relatives
        ]
        analytical_hashes_before = {
            str(source.source): _sha256_file(source.source) for source in all_sources
        }
        audit = [
            {
                "run": "A_AND_B_SOURCE",
                "path": str(source.source),
                "relative_path": str(source.relative),
                "purpose": "BYTE_EXACT_RAW_PROJECTION_A_B_INPUT"
                if projection_manifest is not None
                else "VALIDATED_FOCUSED_FIXTURE_EXACT_COPY_A_B_INPUT"
                if focused_fixture_source is not None
                else "PHYSICAL_RAW_A_B_INPUT",
                "classification": "PERMITTED",
                "sha256": analytical_hashes_before[str(source.source)],
                "bytes": source.size,
                "live_callback_input": source.relative in live_relatives,
                "fixed_context_input": source.relative not in live_relatives,
            }
            for source in all_sources
        ]
        if projection_manifest is not None:
            audit.extend(
                {
                    "path": row["path"],
                    "relative_path": row["relative_path"],
                    "purpose": "AUTHORITATIVE_RAW_PROJECTION_SOURCE",
                    "classification": "PERMITTED_BYTE_EXACT_RAW_SOURCE",
                    "sha256": row["sha256_before"],
                    "bytes": row["bytes_before"],
                    "source_unchanged": row["unchanged_after_projection"],
                }
                for row in projection_manifest["source_files"]
            )
        elif focused_fixture_source is not None:
            audit.append(
                {
                    "path": str(focused_fixture_source),
                    "purpose": "MANIFEST_VALIDATED_FOCUSED_FIXTURE_SOURCE",
                    "classification": "PERMITTED_EXACT_COPY_SOURCE",
                    "sha256": AUTHORIZED_FOCUSED_MANIFEST_SHA256,
                    "bytes": sum(source.size for source in sources),
                    "source_unchanged": True,
                }
            )
        all_accounting: list[dict[str, Any]] = []
        open_recorder = RuntimeOpenRecorder()
        a_staging = work / "a_collector"
        a_state = output / "runs/incremental_a/state"
        with open_recorder.recording("incremental_a"):
            a_snapshot, accounting, a_metrics = run_schedule(
                schedule=SCHEDULES["original_source_chunks"],
                sources=sources,
                staging_root=a_staging,
                state_root=a_state,
                config_path=args.config,
                sessions=sessions,
                context_sources=context_sources,
            )
        all_accounting.extend({"run": "incremental_a", **row} for row in accounting)
        audit.extend(
            open_recorder.audit_rows(
                scope="incremental_a",
                permitted_data_roots=(analytical_data_root, a_staging),
                permitted_state_roots=(a_state,),
                permitted_config_paths=(args.config,),
                repository=repository,
            )
        )
        audit.extend(
            required_schedule_open_coverage(
                open_recorder,
                scope="incremental_a",
                sources=sources,
                context_sources=context_sources,
                staging_root=a_staging,
            )
        )
        a_seal = seal_run(output / "runs/incremental_a", a_snapshot, a_metrics)
        state_manifest_seal = write_state_tree_manifest(
            a_state, output / "incremental_a_state_manifest.json",
        )
        a_seal.update(state_manifest_seal)
        (output / "runs/incremental_a/seal.json").write_bytes(
            _json_bytes(a_seal)
        )
        if not args.retain_staging:
            shutil.rmtree(work / "a_collector")

        b_state = output / "runs/batch_b"
        with open_recorder.recording("batch_b"):
            b_snapshot, b_metrics, batch_open_rows = run_clean_canonical_batch(
                data_root=analytical_data_root,
                batch_root=b_state,
                stack_config_path=args.stack_config,
                inventory_config_path=args.inventory_config,
                shadow_config_path=args.config,
                sessions=sessions,
            )
        b_seal = seal_run(output / "runs/batch_b", b_snapshot, b_metrics)
        audit.extend(batch_open_rows)
        audit.extend(
            open_recorder.audit_rows(
                scope="batch_b",
                permitted_data_roots=(analytical_data_root,),
                permitted_state_roots=(b_state,),
                permitted_config_paths=(
                    args.stack_config,
                    args.inventory_config,
                    args.config,
                ),
                repository=repository,
            )
        )

        # Deliberately reopen only sealed A/B snapshots for comparison.
        sealed_a = _load_sealed_snapshot(output / "runs/incremental_a")
        sealed_b = _load_sealed_snapshot(output / "runs/batch_b")
        comparison_a = project_incremental_fallback(
            sealed_a, sealed_b.get("intraday_fallback_sessions", [])
        )
        comparison = compare_snapshots(
            comparison_a,
            sealed_b,
            expected=None if args.no_expected_count_gate else EXPECTED_COUNTS,
        )
        _write_csv(output / "component_equivalence.csv", comparison)
        ledger_comparison = compare_analytical_ledgers(sealed_a, sealed_b)
        _write_csv(
            output / "analytical_ledger_identity_equivalence.csv",
            ledger_comparison,
        )
        invariant_rows = compare_invariants(sealed_a, sealed_b)
        _write_csv(output / "causality_invariants.csv", invariant_rows)

        reference_rows: list[dict[str, Any]] = []
        gui_reference_rows: list[dict[str, Any]] = []
        reference_manifest_audits: list[dict[str, Any]] = []
        if not args.skip_references:
            # This is intentionally below both seal writes and seal validation.
            # References cannot influence either A or B generation.
            reference_manifest_audits = [
                verify_reference_package_manifest(
                    args.r6c2_reference_root,
                    reference_name="R6C2R_REFERENCE_C",
                ),
                verify_reference_package_manifest(
                    args.r6d_reference_root,
                    reference_name="R6D_GUI",
                ),
            ]
            (output / "reference_package_manifest_verification.json").write_bytes(
                _json_bytes(reference_manifest_audits)
            )
            reference_c = load_r6c2_reference_snapshot(args.r6c2_reference_root, sessions)
            reference_rows = compare_reference_snapshot(
                a_snapshot=comparison_a,
                b_snapshot=sealed_b,
                reference_snapshot=reference_c,
                reference_name="R6C2R_REFERENCE_C",
            )
            _write_csv(output / "reference_c_component_equivalence.csv", reference_rows)
            reference_d = load_r6d_reference_snapshot(args.r6d_reference_root, sessions)
            gui_reference_rows = compare_gui_visual_authority(
                a_snapshot=comparison_a,
                b_snapshot=sealed_b,
                reference_snapshot=reference_d,
                reference_name="R6D_GUI",
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
            variant_scope = f"schedule:{name}"
            variant_staging = work / f"schedule_{name}/collector"
            variant_state = output / f"runs/schedules/{name}/state"
            with open_recorder.recording(variant_scope):
                variant_snapshot, accounting, metrics = run_schedule(
                    schedule=SCHEDULES[name],
                    sources=sources,
                    staging_root=variant_staging,
                    state_root=variant_state,
                    config_path=args.config,
                    sessions=sessions,
                    context_sources=context_sources,
                )
            all_accounting.extend({"run": name, **row} for row in accounting)
            audit.extend(
                open_recorder.audit_rows(
                    scope=variant_scope,
                    permitted_data_roots=(analytical_data_root, variant_staging),
                    permitted_state_roots=(variant_state,),
                    permitted_config_paths=(args.config,),
                    repository=repository,
                )
            )
            audit.extend(
                required_schedule_open_coverage(
                    open_recorder,
                    scope=variant_scope,
                    sources=sources,
                    context_sources=context_sources,
                    staging_root=variant_staging,
                )
            )
            variant_run_root = output / f"runs/schedules/{name}"
            variant_seal = seal_run(variant_run_root, variant_snapshot, metrics)
            if (
                variant_seal.get("analytical_ledgers_sha256")
                != a_seal.get("analytical_ledgers_sha256")
            ):
                ledger_difference_summary = retain_bounded_ledger_differences(
                    variant_run_root, sealed_a, variant_snapshot
                )
            else:
                ledger_difference_summary = {
                    "schema": "R6E1R_BOUNDED_LEDGER_DIFFERENCE_V1",
                    "difference_count": 0,
                    "differing_ledger_count": 0,
                    "ledgers": [],
                }
            variant_seal["bounded_ledger_difference_count"] = int(
                ledger_difference_summary["difference_count"]
            )
            variant_seal["bounded_ledger_difference_summary_retained"] = bool(
                ledger_difference_summary["difference_count"]
            )
            variant_seal["snapshot_retained"] = bool(
                args.retain_staging or args.retain_variant_snapshots
            )
            if not variant_seal["snapshot_retained"]:
                (variant_run_root / "snapshot.json").unlink()
                variant_seal["snapshot_removed_after_seal"] = True
            (variant_run_root / "seal.json").write_bytes(_json_bytes(variant_seal))
            variant_seals.append((name, variant_seal))
            del variant_snapshot
            if not args.retain_staging:
                shutil.rmtree(work / f"schedule_{name}/collector")
                shutil.rmtree(output / f"runs/schedules/{name}/state")
        schedule_rows = scheduling_comparison(a_seal, variant_seals)
        schedule_rows.extend(skipped_schedule_rows)
        schedule_rows.extend(
            {
                "schedule": name,
                "canonical_a_hash": a_seal["analytical_semantic_sha256"],
                "schedule_hash": "NOT_RUN",
                "canonical_a_ledger_hash": a_seal["analytical_ledgers_sha256"],
                "schedule_ledger_hash": "NOT_RUN",
                "differences": 0 if focused_equivalence else "NOT_MEASURED",
                "status": "PASS" if focused_equivalence else "NOT_RUN_REQUIRED",
                "reason": (
                    "FULL_SIX_SESSION_SCHEDULE_GATE_NOT_APPLICABLE_TO_FOCUSED_A_B"
                    if focused_equivalence
                    else "REQUIRED_SCHEDULE_OMITTED;EQUIVALENCE_SEMANTICS_NOT_SATISFIED"
                ),
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
        post_hash_rows = post_run_source_hash_rows(
            analytical_sources=all_sources,
            analytical_hashes_before=analytical_hashes_before,
            projection_manifest=projection_manifest,
            focused_fixture_source=focused_fixture_source,
        )
        _write_csv(output / "source_hash_post_run.csv", post_hash_rows)
        open_audit = runtime_open_audit_summary(audit)
        _write_csv(output / "file_open_audit.csv", audit)

        summary = {
            "incremental_a_seal": a_seal,
            "incremental_a_state_manifest_sha256": a_seal[
                "state_manifest_sha256"
            ],
            "incremental_a_state_tree_sha256": a_seal["state_tree_sha256"],
            "incremental_a_state_file_count": a_seal["state_file_count"],
            "incremental_a_committed_source_integrity": a_seal[
                "committed_source_integrity"
            ],
            "batch_b_seal": b_seal,
            "component_failures": sum(row["status"] != "PASS" for row in comparison),
            "analytical_ledger_failures": sum(
                row["status"] != "PASS" for row in ledger_comparison
            ),
            "causality_failures": sum(row["status"] != "PASS" for row in invariant_rows),
            "reference_failures": sum(
                row["status"] != "PASS" for row in reference_rows + gui_reference_rows
            ),
            "references_skipped": args.skip_references,
            "reference_package_manifests": reference_manifest_audits,
            "reference_manifests_verified": (
                len(reference_manifest_audits) == 2
                and all(row["status"] == "PASS" for row in reference_manifest_audits)
            ),
            "focused_equivalence": focused_equivalence,
            "frozen_count_contract_applicable": sessions == SESSIONS,
            "frozen_count_gate_enforced": not args.no_expected_count_gate,
            "frozen_count_gate_satisfied": frozen_count_gate_satisfied(
                sessions, disabled=args.no_expected_count_gate
            ),
            "schedule_failures": sum(row["status"] != "PASS" for row in schedule_rows),
            "checkpoint_failures": sum(row["status"] != "PASS" for row in all_accounting),
            "checkpoint_recovery_failures": sum(
                row["status"] != "PASS" for row in recovery_rows
            ),
            "file_open_audit_measured": open_audit["measured"],
            "file_open_audit_rows": open_audit["audited_rows"],
            "file_open_audit_unmeasured_rows": open_audit["unmeasured_rows"],
            "prohibited_a_b_opens": open_audit["prohibited_rows"],
            "post_run_source_mutations": sum(
                row["status"] != "PASS" for row in post_hash_rows
            ),
            "raw_projection": {
                "used": projection_manifest is not None,
                "reused_existing": (
                    projection_manifest is not None
                    and args.use_existing_projection_manifest is not None
                ),
                "manifest_sha256": projection_manifest.get("manifest_sha256", "")
                if projection_manifest is not None
                else "",
                "source_mutations": projection_manifest.get("source_mutations", 0)
                if projection_manifest is not None
                else 0,
                "malformed_candidate_records": projection_manifest.get(
                    "malformed_candidate_records", 0
                )
                if projection_manifest is not None
                else 0,
                "selected_outer_records": projection_manifest.get("selected_outer_records", 0)
                if projection_manifest is not None
                else 0,
                "reuse_validation": projection_manifest.get("reuse_validation", {})
                if projection_manifest is not None
                else {},
            },
            "sessions": sessions,
            "elapsed_seconds": time.monotonic() - harness_begun,
            "peak_rss_kib_parent_process": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
            "peak_rss_kib_child_processes": resource.getrusage(
                resource.RUSAGE_CHILDREN
            ).ru_maxrss,
        }
        summary["status"] = (
            "PASS"
            if not summary["component_failures"]
            and not summary["analytical_ledger_failures"]
            and not summary["causality_failures"]
            and not summary["reference_failures"]
            and (focused_equivalence or not summary["references_skipped"])
            and (focused_equivalence or summary["reference_manifests_verified"])
            and summary["frozen_count_gate_satisfied"]
            and not summary["schedule_failures"]
            and not summary["checkpoint_failures"]
            and not summary["checkpoint_recovery_failures"]
            and summary["file_open_audit_measured"]
            and not summary["file_open_audit_unmeasured_rows"]
            and not summary["prohibited_a_b_opens"]
            and not summary["post_run_source_mutations"]
            and not summary["raw_projection"]["malformed_candidate_records"]
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
