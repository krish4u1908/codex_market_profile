"""Compact, auditable BankNifty cash-participation sample generation.

The production collector remains the source of truth.  This module reads its
completed one-minute cash-constituent rows and publishes exactly two research
parameters for browser consumption:

* ``cash_breadth``: equal-vote constituent direction versus the frozen 09:45
  IST reference price.
* ``index_participant_volume``: the unweighted sum of constituent shares
  traded in the minute, matching the documented FYERS index-volume semantics.

Neither parameter is an input to the divergence engine.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any
import uuid

from .clock import IST, iso_utc, parse_instant, session_date
SAMPLE_SCHEMA = "BANKNIFTY_CASH_PARTICIPATION_SAMPLE_V1"
MANIFEST_SCHEMA = "BANKNIFTY_CASH_PARTICIPATION_MANIFEST_V1"
SAMPLE_GENERATOR_VERSION = "1.0.11"
SAMPLE_FILE = "cash_participation_1m.jsonl"
MANIFEST_FILE = "sample_manifest.json"
PARAMETERS = ("cash_breadth", "index_participant_volume")
PARAMETER_CONTRACT = {
    "cash_breadth": {
        "unit": "PERCENT_NET_CONSTITUENTS",
        "weighting": "EQUAL_CONSTITUENT_VOTE",
        "formula": "100*(ADVANCING_MINUS_DECLINING)/EXPECTED_CONSTITUENTS",
        "reference": "FROZEN_0945_IST_CONSTITUENT_PRICE",
    },
    "index_participant_volume": {
        "unit": "SHARES",
        "weighting": "UNWEIGHTED_CONSTITUENT_SUM",
        "formula": "SUM(CONSTITUENT_MINUTE_VOLUME)",
        "futures_volume": False,
        "rupee_turnover": False,
    },
}
REFERENCE_RULE = "EXACT_0944_BUCKET_CLOSE_AT_0945_IST"
ANALYSIS_START = time(9, 45)
DEFAULT_CASH_CLOSE = time(15, 15)
DEFAULT_FINALIZE_DELAY_SECONDS = 8
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _atomic_text(path: Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _finite(value: object, *, non_negative: bool = False) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (non_negative and number < 0):
        return None
    return number


def _parse_hhmm(value: object, fallback: time) -> time:
    if not isinstance(value, str):
        return fallback
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return fallback
    return fallback if parsed.tzinfo is not None else parsed


def _session_instant(day: date, wall_time: time) -> datetime:
    return datetime.combine(day, wall_time, tzinfo=IST)


def _metadata_for_session(data_root: Path, day: date) -> dict[str, object] | None:
    candidates: list[tuple[datetime, Path, dict[str, object]]] = []
    metadata_root = data_root / "metadata"
    if not metadata_root.is_dir():
        return None
    for path in sorted(metadata_root.glob("startup_*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(row, dict):
                continue
            started = parse_instant(row.get("started_at"), field="collector startup time")
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if session_date(started) == day:
            candidates.append((started, path, row))
    if not candidates:
        return None
    _, path, row = max(candidates, key=lambda item: item[0])
    return {"path": path, "row": row}


def _expected_symbols(
    metadata: Mapping[str, object] | None,
    observed_cash_symbols: Iterable[str],
) -> tuple[tuple[str, ...], str]:
    weights = metadata.get("constituent_weights") if metadata is not None else None
    if isinstance(weights, Mapping) and weights:
        symbols = tuple(sorted(f"NSE:{str(name).upper()}-EQ" for name in weights))
        return symbols, "COLLECTOR_STARTUP_CONSTITUENT_WEIGHTS"
    symbols = tuple(sorted({str(symbol).upper() for symbol in observed_cash_symbols if symbol}))
    if not symbols:
        raise ValueError("market_1m.csv contains no cash-constituent symbols")
    return symbols, "INFERRED_FROM_OBSERVED_CASH_ROWS"


def _status(breadth_valid: bool, volume_valid: bool) -> str:
    if breadth_valid and volume_valid:
        return "VALID"
    if not breadth_valid and not volume_valid:
        return "INCOMPLETE_BOTH"
    return "INCOMPLETE_BREADTH" if not breadth_valid else "INCOMPLETE_VOLUME"


def _read_source_rows(path: Path) -> tuple[dict[tuple[datetime, str], dict[str, object]], set[str]]:
    required = {
        "minute",
        "symbol",
        "instrument_class",
        "ltp_close",
        "minute_volume",
        "last_received_time",
    }
    rows: dict[tuple[datetime, str], dict[str, object]] = {}
    cash_symbols: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        for line_number, source in enumerate(reader, 2):
            if str(source.get("instrument_class", "")).strip().lower() != "cash":
                continue
            symbol = str(source.get("symbol", "")).upper().strip()
            if not symbol:
                raise ValueError(f"{path}:{line_number} cash row has no symbol")
            minute = parse_instant(source.get("minute"), field=f"{path}:{line_number} minute")
            minute = minute.astimezone(IST)
            if minute.second != 0 or minute.microsecond != 0:
                raise ValueError(f"{path}:{line_number} minute is not minute-aligned")
            key = (minute, symbol)
            if key in rows:
                raise ValueError(f"{path}:{line_number} duplicates {minute.isoformat()} {symbol}")
            receipt_value = source.get("last_received_time")
            receipt = None
            if receipt_value not in (None, ""):
                receipt = parse_instant(
                    receipt_value,
                    field=f"{path}:{line_number} last_received_time",
                )
            rows[key] = {
                "price": _finite(source.get("ltp_close")),
                "volume": _finite(source.get("minute_volume"), non_negative=True),
                "receipt": receipt,
            }
            cash_symbols.add(symbol)
    return rows, cash_symbols


def build_sample_rows(
    market_1m: Path,
    day: date,
    *,
    metadata: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Derive the two compact parameters from one completed collector CSV."""

    source_rows, observed_symbols = _read_source_rows(Path(market_1m))
    foreign_dates = sorted({minute.date() for minute, _ in source_rows if minute.date() != day})
    if foreign_dates:
        raise ValueError(f"market_1m.csv contains rows outside {day}: {foreign_dates}")
    expected, expected_source = _expected_symbols(metadata, observed_symbols)
    expected_set = set(expected)
    unexpected = sorted(observed_symbols - expected_set)

    schedule = metadata.get("market_schedule") if metadata is not None else None
    cash_close = _parse_hhmm(
        schedule.get("cash_continuous_close_exclusive")
        if isinstance(schedule, Mapping)
        else None,
        DEFAULT_CASH_CLOSE,
    )
    finalize_delay_value = metadata.get("finalize_delay") if metadata is not None else None
    try:
        finalize_delay = int(finalize_delay_value)
    except (TypeError, ValueError):
        finalize_delay = DEFAULT_FINALIZE_DELAY_SECONDS
    if finalize_delay < 0 or finalize_delay > 300:
        raise ValueError("collector finalize_delay must be between 0 and 300 seconds")

    start = _session_instant(day, ANALYSIS_START)
    end = _session_instant(day, cash_close)
    if end <= start:
        raise ValueError("cash close must be after 09:45 IST")

    references: dict[str, tuple[datetime, float]] = {}
    reference_minute = start - timedelta(minutes=1)
    for (minute, symbol), row in source_rows.items():
        price = row["price"]
        if (
            symbol not in expected_set
            or minute != reference_minute
            or price is None
            or price <= 0
        ):
            continue
        references[symbol] = (minute, float(price))

    result: list[dict[str, object]] = []
    current = start
    while current < end:
        prices: dict[str, float] = {}
        volumes: dict[str, float] = {}
        receipts: list[datetime] = []
        for symbol in expected:
            row = source_rows.get((current, symbol))
            if row is None:
                continue
            price = row["price"]
            volume = row["volume"]
            receipt = row["receipt"]
            if price is not None and price > 0 and symbol in references:
                prices[symbol] = float(price)
            if volume is not None:
                volumes[symbol] = float(volume)
            if isinstance(receipt, datetime):
                receipts.append(receipt)

        breadth_valid = len(prices) == len(expected)
        volume_valid = len(volumes) == len(expected)
        breadth = None
        if breadth_valid:
            advancing = sum(prices[symbol] > references[symbol][1] for symbol in expected)
            declining = sum(prices[symbol] < references[symbol][1] for symbol in expected)
            breadth = round(100.0 * (advancing - declining) / len(expected), 6)
        participant_volume = None
        if volume_valid:
            summed = sum(volumes.values())
            participant_volume = int(summed) if summed.is_integer() else round(summed, 6)

        safe_publication = current + timedelta(minutes=1, seconds=finalize_delay)
        if receipts:
            safe_publication = max(safe_publication, max(receipts))
        result.append({
            "schema": SAMPLE_SCHEMA,
            "session": day.isoformat(),
            "minute_ist": current.isoformat(timespec="seconds"),
            "t": iso_utc(safe_publication),
            "cash_breadth": breadth,
            "index_participant_volume": participant_volume,
            "breadth_coverage_count": len(prices),
            "volume_coverage_count": len(volumes),
            "expected_constituent_count": len(expected),
            "status": _status(breadth_valid, volume_valid),
        })
        current += timedelta(minutes=1)

    details = {
        "expected_constituents": list(expected),
        "expected_constituent_count": len(expected),
        "expected_constituent_source": expected_source,
        "unexpected_cash_symbols": unexpected,
        "reference_status": (
            "VALID" if len(references) == len(expected) else "INCOMPLETE_0945_REFERENCE"
        ),
        "reference_count": len(references),
        "reference_rule": REFERENCE_RULE,
        "reference_minute": reference_minute.isoformat(timespec="seconds"),
        "analysis_start": start.isoformat(timespec="seconds"),
        "analysis_end_exclusive": end.isoformat(timespec="seconds"),
        "collector_finalize_delay_seconds": finalize_delay,
    }
    return result, details


def _sample_content(rows: Iterable[Mapping[str, object]]) -> str:
    return "".join(_canonical_json(dict(row)) + "\n" for row in rows)


def validate_sample_bundle(directory: Path, *, expected_session: str | None = None) -> dict[str, object]:
    root = Path(directory)
    reasons: list[str] = []
    manifest: dict[str, Any] = {}
    row_count = 0
    try:
        manifest = json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
            reasons.append("MANIFEST_SCHEMA_MISMATCH")
        session = str(manifest.get("session", ""))
        if expected_session is not None and session != expected_session:
            reasons.append("SESSION_MISMATCH")
        session_day = date.fromisoformat(session)
        if manifest.get("generator_version") != SAMPLE_GENERATOR_VERSION:
            reasons.append("GENERATOR_VERSION_MISMATCH")
        if manifest.get("parameters") != list(PARAMETERS):
            reasons.append("PARAMETER_CONTRACT_MISMATCH")
        if manifest.get("parameter_contract") != PARAMETER_CONTRACT:
            reasons.append("PARAMETER_DEFINITION_MISMATCH")
        if manifest.get("divergence_engine_input") is not False:
            reasons.append("DIVERGENCE_BOUNDARY_MISMATCH")
        if manifest.get("production_weight") != 0:
            reasons.append("PRODUCTION_WEIGHT_MISMATCH")
        parse_instant(manifest.get("generated_at"), field="cash sample generation time")
        output = manifest.get("output")
        if not isinstance(output, dict) or output.get("file") != SAMPLE_FILE:
            reasons.append("OUTPUT_CONTRACT_MISMATCH")
            output = {}
        sample_path = root / SAMPLE_FILE
        if not sample_path.is_file():
            reasons.append("MISSING_SAMPLE_FILE")
        elif output.get("sha256") != _sha256_file(sample_path):
            reasons.append("SAMPLE_HASH_MISMATCH")
        elif int(output.get("size_bytes", -1)) != sample_path.stat().st_size:
            reasons.append("SAMPLE_SIZE_MISMATCH")
        if sample_path.is_file():
            previous = None
            previous_minute = None
            derivation = manifest.get("derivation")
            if not isinstance(derivation, Mapping):
                reasons.append("DERIVATION_CONTRACT_MISMATCH")
                derivation = {}
            analysis_start = parse_instant(
                derivation.get("analysis_start"), field="cash sample analysis start"
            )
            analysis_end = parse_instant(
                derivation.get("analysis_end_exclusive"), field="cash sample analysis end"
            )
            required_start = _session_instant(session_day, ANALYSIS_START)
            if analysis_start != required_start:
                reasons.append("ANALYSIS_START_IS_NOT_0945_IST")
            if analysis_end <= analysis_start:
                reasons.append("ANALYSIS_WINDOW_INVALID")
            expected_count = int(derivation.get("expected_constituent_count", 0))
            finalize_delay = int(derivation.get("collector_finalize_delay_seconds", -1))
            if expected_count <= 0:
                reasons.append("EXPECTED_CONSTITUENT_COUNT_INVALID")
            if finalize_delay < 0:
                reasons.append("FINALIZE_DELAY_INVALID")
            if derivation.get("reference_rule") != REFERENCE_RULE:
                reasons.append("REFERENCE_RULE_MISMATCH")
            if parse_instant(
                derivation.get("reference_minute"), field="cash reference minute"
            ) != required_start - timedelta(minutes=1):
                reasons.append("REFERENCE_MINUTE_MISMATCH")
            expected_symbols = derivation.get("expected_constituents")
            if (
                not isinstance(expected_symbols, list)
                or len(expected_symbols) != expected_count
                or len(set(expected_symbols)) != expected_count
            ):
                reasons.append("EXPECTED_CONSTITUENTS_MISMATCH")
            actual_status_counts: dict[str, int] = {}
            with sample_path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    row_count += 1
                    row = json.loads(line)
                    if not isinstance(row, dict) or row.get("schema") != SAMPLE_SCHEMA:
                        reasons.append(f"ROW_SCHEMA_MISMATCH:{line_number}")
                        continue
                    if str(row.get("session")) != session:
                        reasons.append(f"ROW_SESSION_MISMATCH:{line_number}")
                    minute = parse_instant(
                        row.get("minute_ist"), field="cash sample minute timestamp"
                    )
                    if minute < analysis_start or minute >= analysis_end:
                        reasons.append(f"ROW_OUTSIDE_ANALYSIS_WINDOW:{line_number}")
                    if previous_minute is None and minute != analysis_start:
                        reasons.append("FIRST_ROW_IS_NOT_0945_ANALYSIS_START")
                    if previous_minute is not None and minute != previous_minute + timedelta(minutes=1):
                        reasons.append(f"ROW_MINUTE_GAP:{line_number}")
                    previous_minute = minute
                    timestamp = parse_instant(row.get("t"), field="cash sample publication time")
                    safe_time = minute + timedelta(minutes=1, seconds=finalize_delay)
                    if timestamp < safe_time:
                        reasons.append(f"ROW_PUBLISHED_BEFORE_FINALIZATION:{line_number}")
                    if previous is not None and timestamp <= previous:
                        reasons.append(f"ROW_TIME_ORDER_INVALID:{line_number}")
                    previous = timestamp
                    breadth = row.get("cash_breadth")
                    if breadth is not None and (
                        _finite(breadth) is None or not -100 <= float(breadth) <= 100
                    ):
                        reasons.append(f"CASH_BREADTH_INVALID:{line_number}")
                    volume = row.get("index_participant_volume")
                    if volume is not None and _finite(volume, non_negative=True) is None:
                        reasons.append(f"PARTICIPANT_VOLUME_INVALID:{line_number}")
                    try:
                        breadth_coverage = int(row.get("breadth_coverage_count"))
                        volume_coverage = int(row.get("volume_coverage_count"))
                        row_expected = int(row.get("expected_constituent_count"))
                    except (TypeError, ValueError):
                        reasons.append(f"ROW_COVERAGE_INVALID:{line_number}")
                        continue
                    if (
                        row_expected != expected_count
                        or not 0 <= breadth_coverage <= expected_count
                        or not 0 <= volume_coverage <= expected_count
                    ):
                        reasons.append(f"ROW_COVERAGE_INVALID:{line_number}")
                        continue
                    breadth_valid = breadth_coverage == expected_count
                    volume_valid = volume_coverage == expected_count
                    if (breadth is not None) != breadth_valid:
                        reasons.append(f"CASH_BREADTH_COVERAGE_MISMATCH:{line_number}")
                    if (volume is not None) != volume_valid:
                        reasons.append(f"PARTICIPANT_VOLUME_COVERAGE_MISMATCH:{line_number}")
                    if row.get("status") != _status(breadth_valid, volume_valid):
                        reasons.append(f"ROW_STATUS_MISMATCH:{line_number}")
                    status = str(row.get("status"))
                    actual_status_counts[status] = actual_status_counts.get(status, 0) + 1
            if int(output.get("row_count", -1)) != row_count:
                reasons.append("ROW_COUNT_MISMATCH")
            expected_rows = int((analysis_end - analysis_start).total_seconds() // 60)
            if row_count != expected_rows:
                reasons.append("ANALYSIS_WINDOW_ROW_COUNT_MISMATCH")
            if output.get("status_counts") != dict(sorted(actual_status_counts.items())):
                reasons.append("STATUS_COUNTS_MISMATCH")
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        reasons.append(f"SAMPLE_VERIFICATION_ERROR:{error}")
    return {
        "valid": not reasons,
        "reasons": reasons or ["OK"],
        "row_count": row_count,
        "manifest": manifest,
    }


def generate_session_sample(
    data_root: Path,
    output_root: Path,
    day: date,
    *,
    force: bool = False,
) -> dict[str, object]:
    source = Path(data_root).resolve() / "minute" / day.isoformat() / "market_1m.csv"
    if not source.is_file():
        raise FileNotFoundError(source)
    root = Path(output_root).resolve()
    destination = root / day.isoformat()
    if destination.exists() and not destination.is_dir():
        raise FileExistsError(f"session destination is not a directory: {destination}")

    metadata_entry = _metadata_for_session(Path(data_root).resolve(), day)
    metadata_path = None if metadata_entry is None else Path(metadata_entry["path"])
    metadata = None if metadata_entry is None else metadata_entry["row"]
    source_hash = _sha256_file(source)
    metadata_hash = None if metadata_path is None else _sha256_file(metadata_path)

    manifest_path = destination / MANIFEST_FILE
    if not force and manifest_path.is_file():
        try:
            current = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_contract = current.get("source", {})
            unchanged = (
                current.get("generator_version") == SAMPLE_GENERATOR_VERSION
                and current.get("parameters") == list(PARAMETERS)
                and source_contract.get("market_1m_sha256") == source_hash
                and source_contract.get("startup_metadata_sha256") == metadata_hash
                and validate_sample_bundle(destination, expected_session=day.isoformat())["valid"]
            )
            if unchanged:
                return {"session": day.isoformat(), "status": "UNCHANGED", "directory": str(destination)}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass

    rows, details = build_sample_rows(source, day, metadata=metadata)
    if _sha256_file(source) != source_hash:
        raise ValueError(f"collector minute source changed during generation: {source}")
    if metadata_path is not None and _sha256_file(metadata_path) != metadata_hash:
        raise ValueError(f"collector startup metadata changed during generation: {metadata_path}")
    content = _sample_content(rows)
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_text(destination / SAMPLE_FILE, content)
    sample_hash = _sha256_file(destination / SAMPLE_FILE)
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session": day.isoformat(),
        "generator_version": SAMPLE_GENERATOR_VERSION,
        "generated_at": iso_utc(datetime.now(timezone.utc)),
        "parameters": list(PARAMETERS),
        "parameter_contract": PARAMETER_CONTRACT,
        "source": {
            "market_1m": str(source),
            "market_1m_sha256": source_hash,
            "startup_metadata": None if metadata_path is None else str(metadata_path),
            "startup_metadata_sha256": metadata_hash,
        },
        "derivation": details,
        "output": {
            "file": SAMPLE_FILE,
            "sha256": sample_hash,
            "row_count": len(rows),
            "size_bytes": (destination / SAMPLE_FILE).stat().st_size,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "divergence_engine_input": False,
        "production_weight": 0,
    }
    _atomic_json(manifest_path, manifest)
    verification = validate_sample_bundle(destination, expected_session=day.isoformat())
    if not verification["valid"]:
        raise ValueError(f"generated cash sample failed verification: {verification['reasons']}")
    return {
        "session": day.isoformat(),
        "status": "GENERATED",
        "directory": str(destination),
        "row_count": len(rows),
        "size_bytes": (destination / SAMPLE_FILE).stat().st_size,
    }


def discover_minute_sessions(data_root: Path) -> tuple[date, ...]:
    minute_root = Path(data_root).resolve() / "minute"
    if not minute_root.is_dir():
        raise FileNotFoundError(minute_root)
    sessions = []
    for path in sorted(minute_root.iterdir()):
        if path.is_dir() and DATE_RE.match(path.name) and (path / "market_1m.csv").is_file():
            sessions.append(date.fromisoformat(path.name))
    return tuple(sessions)


def generate_samples(
    data_root: Path,
    output_root: Path,
    *,
    sessions: Iterable[date] | None = None,
    stability_seconds: int = 120,
    force: bool = False,
) -> dict[str, object]:
    data = Path(data_root).resolve()
    output = Path(output_root).resolve()
    if output == Path(output.anchor):
        raise ValueError("sample output root must not be the filesystem root")
    if output == data or data in output.parents:
        raise ValueError("sample output root must not be inside the collector data root")
    if stability_seconds < 0:
        raise ValueError("stability_seconds must be non-negative")
    selected = tuple(sessions) if sessions is not None else discover_minute_sessions(data)
    now = datetime.now(timezone.utc).timestamp()
    results = []
    for day in sorted(set(selected)):
        source = data / "minute" / day.isoformat() / "market_1m.csv"
        if not source.is_file():
            results.append({"session": day.isoformat(), "status": "MISSING_SOURCE"})
            continue
        age = now - source.stat().st_mtime
        if age < stability_seconds:
            results.append({
                "session": day.isoformat(),
                "status": "SOURCE_NOT_STABLE",
                "age_seconds": max(0.0, age),
            })
            continue
        results.append(generate_session_sample(data, output, day, force=force))
    counts: dict[str, int] = {}
    for row in results:
        status = str(row["status"])
        counts[status] = counts.get(status, 0) + 1
    return {
        "schema": "BANKNIFTY_CASH_SAMPLE_GENERATION_RESULT_V1",
        "generator_version": SAMPLE_GENERATOR_VERSION,
        "data_root": str(data),
        "output_root": str(output),
        "parameters": list(PARAMETERS),
        "results": results,
        "status_counts": dict(sorted(counts.items())),
    }
