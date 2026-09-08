"""Compact, auditable NIFTY weighted-cash and India-VIX context samples.

The production collector remains the source of truth.  This module reads its
completed one-minute cash-constituent and India-VIX rows and publishes the
independent display context used by the NIFTY V2 GUI:

* weight-normalized constituent return from each name's first session open;
* five-minute rolling weighted cash and India VIX, each coloured only by its
  own rolling direction; and
* a separate five-state cash/VIX context ribbon.

These samples do not alter the basis episode engine. The separate corrected
directional scoring layer consumes validated Cash/VIX slopes.
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
SAMPLE_SCHEMA = "NIFTY_CASH_VIX_SAMPLE_V2"
MANIFEST_SCHEMA = "NIFTY_CASH_VIX_MANIFEST_V2"
SAMPLE_GENERATOR_VERSION = "1.0.57"
SAMPLE_FILE = "cash_participation_1m.jsonl"
MANIFEST_FILE = "sample_manifest.json"
PARAMETERS = ("cash_weighted_pct", "vix_close", "cash_vix_context")
PARAMETER_CONTRACT = {
    "cash_weighted_pct": {
        "unit": "PERCENT",
        "weighting": "COLLECTOR_STARTUP_NIFTY_WEIGHTS_NORMALIZED_TO_AVAILABLE_WEIGHT",
        "formula": "SUM(WEIGHT*100*(CLOSE/SESSION_OPEN-1))/SUM(AVAILABLE_WEIGHT)",
        "reference": "FIRST_AVAILABLE_SESSION_LTP_OPEN_PER_CONSTITUENT",
    },
    "vix_close": {
        "unit": "INDIA_VIX_POINTS",
        "source": "INSTRUMENT_CLASS_VIX_OR_SYMBOL_CONTAINS_INDIAVIX",
    },
    "cash_vix_context": {
        "rolling_minutes": 5,
        "cash_level_pct": 0.03,
        "cash_momentum_noise_pct": 0.02,
        "vix_rate_noise_pct": 0.15,
        "engine_input": False,
    },
}
REFERENCE_RULE = "FIRST_AVAILABLE_SESSION_LTP_OPEN_PER_CONSTITUENT"
CONTEXT_START = time(9, 15)
ANALYSIS_START = time(9, 45)
DEFAULT_CASH_CLOSE = time(15, 15)
DEFAULT_FINALIZE_DELAY_SECONDS = 8
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _cash_vix_regime(
    cash_weighted_pct: float | None,
    cash_momentum_5m: float | None,
    vix_rate_5m_pct: float | None,
) -> tuple[str, int]:
    """Return the reference GUI's exact descriptive five-state context."""

    if cash_weighted_pct is None or vix_rate_5m_pct is None:
        return "UNAVAILABLE", 0
    cash_up = cash_weighted_pct >= 0.03
    cash_down = cash_weighted_pct <= -0.03
    cash_not_fading = (cash_momentum_5m or 0.0) >= -0.02
    cash_not_recovering = (cash_momentum_5m or 0.0) <= 0.02
    vix_up = vix_rate_5m_pct >= 0.15
    vix_down = vix_rate_5m_pct <= -0.15
    if cash_up and not vix_up and cash_not_fading:
        return "CASH_UP_VIX_CALM", 2
    if cash_up and vix_up:
        return "CASH_UP_VIX_STRESS", 1
    if cash_down and vix_up and cash_not_recovering:
        return "CASH_DOWN_VIX_RISING", -2
    if cash_down and vix_down:
        return "CASH_DOWN_VIX_RELIEF", -1
    return "MIXED_OR_NEUTRAL", 0


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


def _status(cash_valid: bool, vix_valid: bool) -> str:
    if cash_valid and vix_valid:
        return "VALID"
    if not cash_valid and not vix_valid:
        return "INCOMPLETE_BOTH"
    return "INCOMPLETE_CASH" if not cash_valid else "INCOMPLETE_VIX"


def _read_source_rows(
    path: Path,
) -> tuple[
    dict[tuple[datetime, str], dict[str, object]],
    set[str],
    dict[datetime, dict[str, object]],
]:
    required = {
        "minute",
        "symbol",
        "instrument_class",
        "ltp_open",
        "ltp_close",
        "minute_volume",
        "last_received_time",
    }
    rows: dict[tuple[datetime, str], dict[str, object]] = {}
    cash_symbols: set[str] = set()
    vix_rows: dict[datetime, dict[str, object]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
        for line_number, source in enumerate(reader, 2):
            instrument_class = str(source.get("instrument_class", "")).strip().lower()
            symbol = str(source.get("symbol", "")).upper().strip()
            is_vix = instrument_class == "vix" or "INDIAVIX" in symbol
            if instrument_class != "cash" and not is_vix:
                continue
            if not symbol:
                raise ValueError(f"{path}:{line_number} cash/VIX row has no symbol")
            minute = parse_instant(source.get("minute"), field=f"{path}:{line_number} minute")
            minute = minute.astimezone(IST)
            if minute.second != 0 or minute.microsecond != 0:
                raise ValueError(f"{path}:{line_number} minute is not minute-aligned")
            receipt_value = source.get("last_received_time")
            receipt = None
            if receipt_value not in (None, ""):
                receipt = parse_instant(
                    receipt_value,
                    field=f"{path}:{line_number} last_received_time",
                )
            parsed = {
                "open": _finite(source.get("ltp_open")),
                "close": _finite(source.get("ltp_close")),
                "volume": _finite(source.get("minute_volume"), non_negative=True),
                "receipt": receipt,
            }
            if is_vix:
                prior = vix_rows.get(minute)
                if prior is None or (
                    isinstance(receipt, datetime)
                    and (not isinstance(prior.get("receipt"), datetime) or receipt > prior["receipt"])
                ):
                    vix_rows[minute] = parsed
                continue
            key = (minute, symbol)
            if key in rows:
                raise ValueError(f"{path}:{line_number} duplicates {minute.isoformat()} {symbol}")
            rows[key] = parsed
            cash_symbols.add(symbol)
    return rows, cash_symbols, vix_rows


def build_sample_rows(
    market_1m: Path,
    day: date,
    *,
    metadata: Mapping[str, object] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Derive the GitHub V2 GUI's weighted-cash/VIX view causally."""

    source_rows, observed_symbols, vix_source_rows = _read_source_rows(Path(market_1m))
    foreign_dates = sorted(
        ({minute.date() for minute, _ in source_rows}
         | {minute.date() for minute in vix_source_rows}) - {day}
    )
    if foreign_dates:
        raise ValueError(f"market_1m.csv contains rows outside {day}: {foreign_dates}")
    expected, expected_source = _expected_symbols(metadata, observed_symbols)
    expected_set = set(expected)
    unexpected = sorted(observed_symbols - expected_set)
    metadata_weights = metadata.get("constituent_weights") if metadata is not None else None
    weights: dict[str, float] = {}
    if isinstance(metadata_weights, Mapping):
        for name, value in metadata_weights.items():
            weight = _finite(value, non_negative=True)
            if weight is None or weight <= 0:
                continue
            weights[f"NSE:{str(name).upper()}-EQ"] = weight

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

    context_start = _session_instant(day, CONTEXT_START)
    start = _session_instant(day, ANALYSIS_START)
    end = _session_instant(day, cash_close)
    if end <= start:
        raise ValueError("cash close must be after 09:45 IST")

    session_opens: dict[str, tuple[datetime, float]] = {}
    for (minute, symbol), row in sorted(source_rows.items()):
        opening = row["open"]
        if (
            symbol in expected_set
            and symbol in weights
            and symbol not in session_opens
            and minute >= context_start
            and opening is not None
            and opening > 0
        ):
            session_opens[symbol] = (minute, float(opening))

    result: list[dict[str, object]] = []
    cash_history: list[float | None] = []
    vix_history: list[float | None] = []
    prior_cash_rolling: float | None = None
    prior_vix_rolling: float | None = None
    current = context_start
    while current < end:
        weighted_returns: list[tuple[float, float]] = []
        receipts: list[datetime] = []
        for symbol in expected:
            row = source_rows.get((current, symbol))
            if row is None:
                continue
            close = row["close"]
            receipt = row["receipt"]
            if (
                close is not None
                and close > 0
                and symbol in session_opens
                and session_opens[symbol][0] <= current
                and symbol in weights
            ):
                return_pct = 100.0 * (float(close) / session_opens[symbol][1] - 1.0)
                weighted_returns.append((return_pct, weights[symbol]))
            if isinstance(receipt, datetime):
                receipts.append(receipt)

        available_weight = sum(weight for _, weight in weighted_returns)
        cash_weighted_pct = (
            sum(value * weight for value, weight in weighted_returns) / available_weight
            if available_weight > 0 else None
        )
        vix_row = vix_source_rows.get(current)
        vix_close = None if vix_row is None else vix_row["close"]
        if vix_row is not None and isinstance(vix_row.get("receipt"), datetime):
            receipts.append(vix_row["receipt"])
        cash_history.append(cash_weighted_pct)
        vix_history.append(vix_close)

        cash_values = [value for value in cash_history[-5:] if value is not None]
        vix_values = [value for value in vix_history[-5:] if value is not None]
        cash_rolling = sum(cash_values) / len(cash_values) if cash_values else None
        vix_rolling = sum(vix_values) / len(vix_values) if vix_values else None
        cash_rolling_change = (
            cash_rolling - prior_cash_rolling
            if cash_rolling is not None and prior_cash_rolling is not None else None
        )
        vix_rolling_change = (
            vix_rolling - prior_vix_rolling
            if vix_rolling is not None and prior_vix_rolling is not None else None
        )
        cash_direction = 0 if cash_rolling_change is None else (1 if cash_rolling_change > 0 else -1 if cash_rolling_change < 0 else 0)
        vix_direction = 0 if vix_rolling_change is None else (1 if vix_rolling_change > 0 else -1 if vix_rolling_change < 0 else 0)
        cash_momentum = (
            cash_weighted_pct - cash_history[-6]
            if len(cash_history) > 5
            and cash_weighted_pct is not None
            and cash_history[-6] is not None else None
        )
        vix_rate = (
            100.0 * (float(vix_close) / float(vix_history[-6]) - 1.0)
            if len(vix_history) > 5
            and vix_close is not None
            and vix_history[-6] not in (None, 0) else None
        )
        regime, regime_code = _cash_vix_regime(
            cash_weighted_pct,
            cash_momentum,
            vix_rate,
        )
        prior_cash_rolling = cash_rolling
        prior_vix_rolling = vix_rolling

        safe_publication = current + timedelta(minutes=1, seconds=finalize_delay)
        if receipts:
            safe_publication = max(safe_publication, max(receipts))
        if current >= start:
            result.append({
                "schema": SAMPLE_SCHEMA,
                "session": day.isoformat(),
                "minute_ist": current.isoformat(timespec="seconds"),
                "t": iso_utc(safe_publication),
                "cash_weighted_pct": None if cash_weighted_pct is None else round(cash_weighted_pct, 6),
                "cash_rolling_pct": None if cash_rolling is None else round(cash_rolling, 6),
                "cash_rolling_change": None if cash_rolling_change is None else round(cash_rolling_change, 6),
                "cash_rolling_direction": cash_direction,
                "cash_momentum_5m": None if cash_momentum is None else round(cash_momentum, 6),
                "cash_names": len(weighted_returns),
                "available_weight": round(available_weight, 6),
                "expected_constituent_count": len(expected),
                "vix_close": None if vix_close is None else round(float(vix_close), 6),
                "vix_rolling": None if vix_rolling is None else round(vix_rolling, 6),
                "vix_rolling_change": None if vix_rolling_change is None else round(vix_rolling_change, 6),
                "vix_rolling_direction": vix_direction,
                "vix_rate_5m_pct": None if vix_rate is None else round(vix_rate, 6),
                "cash_vix_regime": regime,
                "cash_vix_code": regime_code,
                "rolling_minutes": 5,
                "status": _status(cash_weighted_pct is not None, vix_close is not None),
            })
        current += timedelta(minutes=1)

    details = {
        "expected_constituents": list(expected),
        "expected_constituent_count": len(expected),
        "expected_constituent_source": expected_source,
        "unexpected_cash_symbols": unexpected,
        "reference_status": (
            "VALID" if len(session_opens) == len(expected) else "INCOMPLETE_SESSION_OPEN"
        ),
        "reference_count": len(session_opens),
        "reference_rule": REFERENCE_RULE,
        "context_start": context_start.isoformat(timespec="seconds"),
        "analysis_start": start.isoformat(timespec="seconds"),
        "analysis_end_exclusive": end.isoformat(timespec="seconds"),
        "collector_finalize_delay_seconds": finalize_delay,
        "rolling_minutes": 5,
        "cash_context_min_pct": 0.03,
        "cash_momentum_noise_pct": 0.02,
        "vix_rate_noise_pct": 0.15,
        "constituent_weights": {symbol: weights[symbol] for symbol in expected if symbol in weights},
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
                derivation.get("context_start"), field="cash/VIX context start"
            ) != _session_instant(session_day, CONTEXT_START):
                reasons.append("CONTEXT_START_MISMATCH")
            if int(derivation.get("rolling_minutes", 0)) != 5:
                reasons.append("ROLLING_WINDOW_MISMATCH")
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
                    cash = row.get("cash_weighted_pct")
                    vix = row.get("vix_close")
                    if cash is not None and _finite(cash) is None:
                        reasons.append(f"WEIGHTED_CASH_INVALID:{line_number}")
                    if vix is not None and (
                        _finite(vix, non_negative=True) is None or float(vix) == 0
                    ):
                        reasons.append(f"VIX_INVALID:{line_number}")
                    for field in (
                        "cash_rolling_pct", "cash_rolling_change", "cash_momentum_5m",
                        "vix_rolling", "vix_rolling_change", "vix_rate_5m_pct",
                    ):
                        if row.get(field) is not None and _finite(row.get(field)) is None:
                            reasons.append(f"ROLLING_VALUE_INVALID:{field}:{line_number}")
                    try:
                        cash_names = int(row.get("cash_names"))
                        row_expected = int(row.get("expected_constituent_count"))
                        cash_direction = int(row.get("cash_rolling_direction"))
                        vix_direction = int(row.get("vix_rolling_direction"))
                        regime_code = int(row.get("cash_vix_code"))
                    except (TypeError, ValueError):
                        reasons.append(f"ROW_COVERAGE_INVALID:{line_number}")
                        continue
                    if (
                        row_expected != expected_count
                        or not 0 <= cash_names <= expected_count
                        or cash_direction not in {-1, 0, 1}
                        or vix_direction not in {-1, 0, 1}
                        or regime_code not in {-2, -1, 0, 1, 2}
                        or int(row.get("rolling_minutes", 0)) != 5
                    ):
                        reasons.append(f"ROW_COVERAGE_INVALID:{line_number}")
                        continue
                    regimes = {
                        -2: "CASH_DOWN_VIX_RISING",
                        -1: "CASH_DOWN_VIX_RELIEF",
                        0: {"MIXED_OR_NEUTRAL", "UNAVAILABLE"},
                        1: "CASH_UP_VIX_STRESS",
                        2: "CASH_UP_VIX_CALM",
                    }
                    expected_regime = regimes[regime_code]
                    actual_regime = row.get("cash_vix_regime")
                    if (
                        (isinstance(expected_regime, set) and actual_regime not in expected_regime)
                        or (not isinstance(expected_regime, set) and actual_regime != expected_regime)
                    ):
                        reasons.append(f"CASH_VIX_REGIME_MISMATCH:{line_number}")
                    if row.get("status") != _status(cash is not None, vix is not None):
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
        "schema": "NIFTY_CASH_SAMPLE_GENERATION_RESULT_V1",
        "generator_version": SAMPLE_GENERATOR_VERSION,
        "data_root": str(data),
        "output_root": str(output),
        "parameters": list(PARAMETERS),
        "results": results,
        "status_counts": dict(sorted(counts.items())),
    }
