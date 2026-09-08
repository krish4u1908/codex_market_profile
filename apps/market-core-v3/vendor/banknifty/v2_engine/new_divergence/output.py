"""Atomic run-bundle persistence and dynamic session catalog generation."""

from __future__ import annotations

from collections import Counter
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import uuid
from typing import Callable, Iterable, Mapping

from .clock import iso_utc, session_instant
from .cash_samples import MANIFEST_FILE, SAMPLE_FILE, validate_sample_bundle
from .contracts import EngineConfig, EventKind, MarketEvent
from .engine import CausalDivergenceEngine
from .ledger import canonical_json, verify_ledger
from .provenance import runtime_identity

CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
DAY_OPEN_MAX_DELAY_SECONDS = 60


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def _jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _option_strike_rows(event: MarketEvent) -> list[dict[str, object]]:
    """Flatten one normalized option-chain receipt for its dedicated artifact."""

    if event.kind != EventKind.OPTION_PRESSURE:
        return []
    values = event.values.get("strike_oi")
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError("OPTION_PRESSURE strike_oi must be a list")
    rows = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("OPTION_PRESSURE strike_oi row must be an object")
        option_type = str(item.get("option_type", "")).upper()
        expiry = str(item.get("expiry", "")).strip()
        symbol = str(item.get("symbol", "")).upper().strip()
        try:
            strike = float(item.get("strike"))
            oi = float(item.get("oi"))
        except (TypeError, ValueError) as error:
            raise ValueError("OPTION_PRESSURE strike/OI must be finite") from error
        if option_type not in {"CE", "PE"} or not expiry or not symbol:
            raise ValueError("OPTION_PRESSURE strike row has incomplete identity")
        if not math.isfinite(strike) or not math.isfinite(oi):
            raise ValueError("OPTION_PRESSURE strike/OI must be finite")
        price_value = item.get("price")
        price = None
        if price_value is not None:
            try:
                price = float(price_value)
            except (TypeError, ValueError) as error:
                raise ValueError("OPTION_PRESSURE strike price must be finite") from error
            if not math.isfinite(price):
                raise ValueError("OPTION_PRESSURE strike price must be finite")
        volume_value = item.get("volume")
        volume = None
        if volume_value is not None:
            try:
                volume = float(volume_value)
            except (TypeError, ValueError) as error:
                raise ValueError("OPTION_PRESSURE strike volume must be finite") from error
            if not math.isfinite(volume) or volume < 0:
                raise ValueError("OPTION_PRESSURE strike volume must be finite and non-negative")
        rows.append({
            "t": iso_utc(event.receipt_timestamp),
            "e": expiry,
            "k": option_type,
            "s": strike,
            "oi": oi,
            "p": price,
            "v": volume,
            "symbol": symbol,
            "event_id": event.event_id,
        })
    return rows


def _futures_market_row(event: MarketEvent) -> dict[str, object] | None:
    """Retain the active Futures counter needed by the causal ID volume profile."""

    if event.kind != EventKind.FUTURES_TICK:
        return None
    try:
        price = float(event.values["price"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("FUTURES_TICK price must be finite") from error
    if not math.isfinite(price) or price <= 0:
        raise ValueError("FUTURES_TICK price must be finite and positive")
    volume_value = event.values.get("volume")
    volume = None
    if volume_value is not None:
        try:
            candidate = float(volume_value)
        except (TypeError, ValueError):
            candidate = math.nan
        # Volume is an auxiliary display source. A malformed/missing counter
        # must fail closed for the profile without preventing the basis replay.
        if math.isfinite(candidate) and candidate >= 0:
            volume = candidate
    return {
        "t": iso_utc(event.receipt_timestamp),
        "p": price,
        "v": volume,
        "symbol": event.symbol,
        "event_id": event.event_id,
    }


def _session_reference(engine: CausalDivergenceEngine) -> dict[str, object]:
    """Publish a hashed, fail-closed BankNifty Index day-open reference."""

    assert engine.session is not None
    session_start = session_instant(engine.session, engine.config.session_start)
    opening = engine.index_open_tick
    if opening is None:
        index_open = {
            "status": "MISSING_INDEX_OPEN",
            "selection_rule": "FIRST_VALID_INDEX_TICK_AT_OR_AFTER_SESSION_START",
            "max_delay_seconds": DAY_OPEN_MAX_DELAY_SECONDS,
            "session_start": iso_utc(session_start),
        }
    else:
        delay = (opening.receipt_timestamp - session_start).total_seconds()
        valid = 0 <= delay <= DAY_OPEN_MAX_DELAY_SECONDS
        index_open = {
            "status": "VALID_DAY_OPEN" if valid else "LATE_FIRST_INDEX_TICK",
            "selection_rule": "FIRST_VALID_INDEX_TICK_AT_OR_AFTER_SESSION_START",
            "max_delay_seconds": DAY_OPEN_MAX_DELAY_SECONDS,
            "session_start": iso_utc(session_start),
            "delay_seconds": delay,
            "symbol": opening.symbol,
            "price": float(opening.values["price"]),
            "event_timestamp": iso_utc(opening.event_timestamp),
            "receipt_timestamp": iso_utc(opening.receipt_timestamp),
            "event_id": opening.event_id,
        }
    return {
        "schema": "NEW_DIVERGENCE_SESSION_REFERENCE_V1",
        "session": engine.session.isoformat(),
        "index_open": index_open,
    }


def write_engine_artifacts(
    engine: CausalDivergenceEngine,
    directory: Path,
    *,
    source: Mapping[str, object],
    option_strike_rows: Iterable[Mapping[str, object]] = (),
    futures_market_rows: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    if engine.session is None:
        raise ValueError("cannot write an empty engine run")
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    _jsonl(root / "basis_observations.jsonl", (row.to_dict() for row in engine.observations))
    _jsonl(root / "evidence_snapshots.jsonl", (row.to_dict() for row in engine.evidence_snapshots))
    _jsonl(root / "diagnostics.jsonl", engine.diagnostics)
    materialized_option_strikes = [dict(row) for row in option_strike_rows]
    _jsonl(root / "option_strike_oi.jsonl", materialized_option_strikes)
    materialized_futures_market = [dict(row) for row in futures_market_rows]
    _jsonl(root / "futures_market.jsonl", materialized_futures_market)
    session_reference = _session_reference(engine)
    atomic_json(root / "session_reference.json", session_reference)
    if not (root / "transitions.jsonl").exists():
        atomic_text(root / "transitions.jsonl", "")
    atomic_json(root / "engine_config.json", engine.config.to_dict())
    atomic_json(root / "source_manifest.json", {
        "schema": "NEW_DIVERGENCE_SOURCE_MANIFEST_V1",
        "input": dict(source),
        "runtime": runtime_identity(),
    })
    transitions = list(engine.transitions)
    states = Counter(transition.state.value for transition in transitions)
    ledger_status = verify_ledger(root / "transitions.jsonl")
    files = {
        "basis": "basis_observations.jsonl",
        "evidence": "evidence_snapshots.jsonl",
        "transitions": "transitions.jsonl",
        "diagnostics": "diagnostics.jsonl",
        "option_strike_oi": "option_strike_oi.jsonl",
        "futures_market": "futures_market.jsonl",
        "session_reference": "session_reference.json",
        "config": "engine_config.json",
        "source": "source_manifest.json",
    }
    artifact_hashes = {
        key: sha256_file(root / relative) for key, relative in files.items()
    }
    summary = {
        "schema": "NEW_DIVERGENCE_RUN_V1",
        "classification": CLASSIFICATION,
        "research_only": True,
        "production_weight": engine.config.production_weight,
        "session": engine.session.isoformat(),
        "methodology_version": engine.config.methodology_version,
        "config_sha256": engine.config.sha256,
        "index_symbol": engine.index_symbol,
        "futures_symbol": engine.futures_symbol,
        "basis_observation_count": len(engine.observations),
        "evidence_snapshot_count": len(engine.evidence_snapshots),
        "transition_count": len(transitions),
        "diagnostic_count": len(engine.diagnostics),
        "option_strike_oi_count": len(materialized_option_strikes),
        "futures_market_count": len(materialized_futures_market),
        "session_reference_status": session_reference["index_open"]["status"],
        "transition_states": dict(sorted(states.items())),
        "first_observation": None if not engine.observations else iso_utc(engine.observations[0].timestamp),
        "last_observation": None if not engine.observations else iso_utc(engine.observations[-1].timestamp),
        "ledger": ledger_status,
        "causal_guarantees": [
            "RECEIPT_ORDER_ONLY",
            "BACKWARD_INDEX_JOIN_ONLY",
            "NO_IMPLICIT_REPLAY_FINALIZATION",
            "NO_OUTCOME_INPUT_TO_INFERENCE",
        ],
        "files": files,
        "artifact_sha256": artifact_hashes,
    }
    atomic_json(root / "summary.json", summary)
    return summary


def _line_count(path: Path) -> int:
    with path.open(encoding="utf-8") as handle:
        return sum(bool(line.strip()) for line in handle)


def verify_run(directory: Path) -> dict[str, object]:
    root = Path(directory).resolve()
    reasons: list[str] = []
    try:
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        if str(summary.get("session")) != root.name:
            reasons.append("SESSION_DIRECTORY_MISMATCH")
        files = summary.get("files")
        hashes = summary.get("artifact_sha256")
        if not isinstance(files, dict) or not isinstance(hashes, dict):
            reasons.append("MISSING_ARTIFACT_CONTRACT")
            files = {}
            hashes = {}
        resolved: dict[str, Path] = {}
        for key, relative in files.items():
            if not isinstance(relative, str) or Path(relative).name != relative:
                reasons.append(f"UNSAFE_ARTIFACT_PATH:{key}")
                continue
            path = root / relative
            resolved[str(key)] = path
            if not path.is_file():
                reasons.append(f"MISSING_ARTIFACT:{key}")
            elif hashes.get(key) != sha256_file(path):
                reasons.append(f"ARTIFACT_HASH_MISMATCH:{key}")
        required = {"basis", "evidence", "transitions", "diagnostics", "config", "source"}
        for key in sorted(required - set(resolved)):
            reasons.append(f"MISSING_ARTIFACT_DECLARATION:{key}")
        ledger = verify_ledger(resolved.get("transitions", root / "transitions.jsonl"))
        if not ledger["valid"]:
            reasons.append(f"INVALID_LEDGER:{ledger['reason']}")
        if "basis" in resolved and resolved["basis"].is_file():
            if _line_count(resolved["basis"]) != int(summary.get("basis_observation_count", -1)):
                reasons.append("BASIS_COUNT_MISMATCH")
        if "evidence" in resolved and resolved["evidence"].is_file():
            if _line_count(resolved["evidence"]) != int(summary.get("evidence_snapshot_count", -1)):
                reasons.append("EVIDENCE_COUNT_MISMATCH")
        if "transitions" in resolved and resolved["transitions"].is_file():
            if _line_count(resolved["transitions"]) != int(summary.get("transition_count", -1)):
                reasons.append("TRANSITION_COUNT_MISMATCH")
        if "diagnostics" in resolved and resolved["diagnostics"].is_file():
            if _line_count(resolved["diagnostics"]) != int(summary.get("diagnostic_count", -1)):
                reasons.append("DIAGNOSTIC_COUNT_MISMATCH")
        if "option_strike_oi" in resolved and resolved["option_strike_oi"].is_file():
            if _line_count(resolved["option_strike_oi"]) != int(
                summary.get("option_strike_oi_count", -1)
            ):
                reasons.append("OPTION_STRIKE_OI_COUNT_MISMATCH")
        if "futures_market" in resolved and resolved["futures_market"].is_file():
            if _line_count(resolved["futures_market"]) != int(
                summary.get("futures_market_count", -1)
            ):
                reasons.append("FUTURES_MARKET_COUNT_MISMATCH")
        if "session_reference" in resolved and resolved["session_reference"].is_file():
            reference = json.loads(resolved["session_reference"].read_text(encoding="utf-8"))
            if reference.get("schema") != "NEW_DIVERGENCE_SESSION_REFERENCE_V1":
                reasons.append("SESSION_REFERENCE_SCHEMA_MISMATCH")
            if str(reference.get("session")) != str(summary.get("session")):
                reasons.append("SESSION_REFERENCE_DATE_MISMATCH")
            opening = reference.get("index_open")
            if not isinstance(opening, dict) or opening.get("status") not in {
                "VALID_DAY_OPEN", "LATE_FIRST_INDEX_TICK", "MISSING_INDEX_OPEN"
            }:
                reasons.append("SESSION_REFERENCE_STATUS_INVALID")
        if "config" in resolved and resolved["config"].is_file():
            config_row = json.loads(resolved["config"].read_text(encoding="utf-8"))
            config = EngineConfig.from_mapping(config_row)
            if config.sha256 != summary.get("config_sha256"):
                reasons.append("CONFIG_HASH_MISMATCH")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        reasons.append(f"RUN_VERIFICATION_ERROR:{error}")
        ledger = {"valid": False, "records": 0, "reason": str(error)}
    return {
        "valid": not reasons,
        "reasons": reasons or ["OK"],
        "ledger": ledger,
    }


def publish_run(
    output_root: Path,
    session: date,
    events: Iterable[MarketEvent],
    config: EngineConfig,
    *,
    source: Mapping[str, object] | Callable[[], Mapping[str, object]],
    finalize_at=None,
) -> Path:
    """Build in a staging directory, then atomically expose one session."""

    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    final = root / session.isoformat()
    preserved_sample: tuple[Path, Path] | None = None
    if final.exists():
        if not final.is_dir():
            raise FileExistsError(f"session output already exists: {final}")
        children = {path.name for path in final.iterdir()}
        allowed = {SAMPLE_FILE, MANIFEST_FILE}
        integrity = validate_sample_bundle(final, expected_session=session.isoformat())
        if children != allowed or not integrity["valid"]:
            raise FileExistsError(f"session output already exists: {final}")
        preserved_sample = (final / SAMPLE_FILE, final / MANIFEST_FILE)
    staging_parent = root / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = staging_parent / f"{session.isoformat()}-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        engine = CausalDivergenceEngine(config, ledger_path=staging / "transitions.jsonl")
        option_strikes: list[dict[str, object]] = []
        futures_market: list[dict[str, object]] = []
        for event in events:
            option_strikes.extend(_option_strike_rows(event))
            futures_row = _futures_market_row(event)
            if futures_row is not None:
                futures_market.append(futures_row)
            engine.ingest(event)
        if engine.session is None:
            raise ValueError("no normalized events were available in the requested interval")
        if engine.session != session:
            raise ValueError(f"normalized session {engine.session} differs from requested {session}")
        if finalize_at is not None:
            engine.finalize(finalize_at)
        resolved_source = source() if callable(source) else source
        write_engine_artifacts(
            engine,
            staging,
            source=resolved_source,
            option_strike_rows=option_strikes,
            futures_market_rows=futures_market,
        )
        if preserved_sample is not None:
            for source_path in preserved_sample:
                shutil.copyfile(source_path, staging / source_path.name)
            copied = validate_sample_bundle(staging, expected_session=session.isoformat())
            if not copied["valid"]:
                raise ValueError(f"preserved cash sample failed verification: {copied['reasons']}")
            displaced = staging_parent / f"sample-only-{session.isoformat()}-{uuid.uuid4().hex}"
            os.replace(final, displaced)
            try:
                os.replace(staging, final)
            except Exception:
                os.replace(displaced, final)
                raise
            shutil.rmtree(displaced, ignore_errors=True)
        else:
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    write_session_catalog(root)
    return final


def _summary_rows(root: Path) -> list[dict[str, object]]:
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        try:
            date.fromisoformat(path.name)
        except ValueError:
            continue
        summary_path = path / "summary.json"
        if not summary_path.is_file():
            continue
        try:
            row = json.loads(summary_path.read_text(encoding="utf-8"))
            date.fromisoformat(str(row["session"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: str(row["session"]))


def write_session_catalog(output_root: Path) -> dict[str, object]:
    root = Path(output_root).resolve()
    summaries = _summary_rows(root)
    by_session = {str(row["session"]): row for row in summaries}
    sample_directories = {}
    if root.is_dir():
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            try:
                date.fromisoformat(path.name)
            except ValueError:
                continue
            if (path / MANIFEST_FILE).is_file() or (path / SAMPLE_FILE).is_file():
                sample_directories[path.name] = path
    discovered = sorted(set(by_session) | set(sample_directories))
    required_methodology = EngineConfig().methodology_version
    integrities = {
        session: verify_run(root / session)
        for session in by_session
    }
    sample_integrities = {
        session: validate_sample_bundle(path, expected_session=session)
        for session, path in sample_directories.items()
    }
    eligible = [
        session for session, row in by_session.items()
        if int(row.get("basis_observation_count", 0)) > 0
        and integrities[session]["valid"]
        and row.get("methodology_version") == required_methodology
    ]
    sessions = []
    for current in discovered:
        row = by_session.get(current, {})
        prior = [value for value in eligible if value < current]
        integrity = integrities.get(current, {
            "valid": False,
            "reasons": ["MISSING_VERIFIED_DIVERGENCE_RUN"],
            "ledger": {"valid": False, "records": 0, "reason": "missing run"},
        })
        sample_integrity = sample_integrities.get(current, {
            "valid": False,
            "reasons": ["MISSING_CASH_SAMPLE"],
            "row_count": 0,
            "manifest": {},
        })
        sample_manifest = sample_integrity.get("manifest", {})
        methodology_compatible = (
            row.get("methodology_version") == required_methodology
            if row
            else None
        )
        sessions.append({
            "session": current,
            "eligible": current in eligible,
            "methodology_version": row.get("methodology_version"),
            "methodology_compatible": methodology_compatible,
            "basis_observation_count": row.get("basis_observation_count", 0),
            "transition_count": row.get("transition_count", 0),
            "index_symbol": row.get("index_symbol"),
            "futures_symbol": row.get("futures_symbol"),
            "first_observation": row.get("first_observation"),
            "last_observation": row.get("last_observation"),
            "run_integrity": integrity,
            "cash_sample_available": bool(sample_integrity["valid"]),
            "cash_sample_integrity": {
                "valid": bool(sample_integrity["valid"]),
                "reasons": list(sample_integrity["reasons"]),
            },
            "cash_sample_row_count": int(sample_integrity.get("row_count", 0)),
            "cash_parameters": list(sample_manifest.get("parameters", [])),
            "actual_scope_sessions": {
                "intraday": [current],
                "1-session": prior[-1:],
                "2-session": prior[-2:],
                "3-session": prior[-3:],
            },
            "payload": f"sessions/{current}.json" if current in eligible else None,
        })
    catalog = {
        "schema": "NEW_DIVERGENCE_DYNAMIC_SESSION_CATALOG_V2",
        "classification": CLASSIFICATION,
        "sessions": sessions,
        "eligible_sessions": sorted(eligible),
        "required_methodology": required_methodology,
        "session_count": len(sessions),
        "date_policy": "DIRECT_SESSION_ROOT_DISCOVERED_FROM_VERIFIED_OUTPUTS_AND_CASH_SAMPLES",
        "session_root_contract": "RUN_ROOT/YYYY-MM-DD",
    }
    atomic_json(root / "catalog.json", catalog)
    return catalog
