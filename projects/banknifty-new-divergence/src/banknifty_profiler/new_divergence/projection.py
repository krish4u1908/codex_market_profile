"""Calculation-free browser projection over completed engine run bundles."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
import math
from datetime import date, datetime, time
from pathlib import Path
import shutil
from typing import Iterable, Mapping

from .clock import iso_utc, parse_instant, session_instant
from .cash_samples import MANIFEST_FILE, SAMPLE_FILE, validate_sample_bundle
from .nightly_context import ALGORITHM_VERSION as CONTEXT_ALGORITHM_VERSION
from .nightly_context import CONTEXT_RUNTIME_VERSION
from .nightly_context import CONTEXT_SCHEMA, FAMILIES as CONTEXT_FAMILIES
from .nightly_context import VOLUME_PROFILE_FAMILY
from .output import CLASSIFICATION, atomic_json, sha256_file, verify_run, write_session_catalog
from .provenance import RUNTIME_VERSION


INTRADAY_SCOPE = "ID"
INTRADAY_BIN_POINTS = 25
INTRADAY_VALUE_AREA_FRACTION = 0.70


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number} is not an object")
            rows.append(row)
    return rows


def _pack(rows: Iterable[dict[str, object]], fields: tuple[str, ...]) -> dict[str, object]:
    return {
        "fields": list(fields),
        "rows": [[row.get(field) for field in fields] for row in rows],
    }


def confirmed_zones(transitions: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Project only confirmed episode intervals for chart colouring."""

    terminal_states = {"RESOLVED", "ROTATION", "EXPIRED"}
    open_zones: dict[str, dict[str, object]] = {}
    zones: list[dict[str, object]] = []
    ordered = sorted(transitions, key=lambda row: str(row["published_at"]))
    for row in ordered:
        episode_id = str(row["episode_id"])
        state = str(row["state"])
        if state == "CONFIRMED":
            zone = {
                "episode_id": episode_id,
                "colour": str(row["colour"]),
                "confirmed_at": str(row["published_at"]),
                "ended_at": None,
                "terminal_state": None,
            }
            open_zones[episode_id] = zone
            zones.append(zone)
        elif state in terminal_states and episode_id in open_zones:
            zone = open_zones.pop(episode_id)
            zone["ended_at"] = str(row["published_at"])
            zone["terminal_state"] = state
    return zones


def _zones_from(
    transitions: Iterable[dict[str, object]],
    display_start: datetime,
) -> list[dict[str, object]]:
    """Clip a zone already active at 09:45 instead of silently dropping it."""

    result = []
    for source in confirmed_zones(transitions):
        confirmed_at = parse_instant(source["confirmed_at"], field="zone confirmation time")
        ended_at = (
            None
            if source["ended_at"] is None
            else parse_instant(source["ended_at"], field="zone terminal time")
        )
        if ended_at is not None and ended_at < display_start:
            continue
        row = dict(source)
        if confirmed_at < display_start:
            row["source_confirmed_at"] = row["confirmed_at"]
            row["confirmed_at"] = iso_utc(display_start)
            row["clipped_at_projection_start"] = True
        else:
            row["clipped_at_projection_start"] = False
        result.append(row)
    return result


def futures_oi_rows(
    evidence: Iterable[Mapping[str, object]],
    *,
    max_gap_seconds: float,
) -> list[dict[str, object]]:
    """Project unique Futures OI receipts and gap-safe successive deltas.

    Evidence snapshots repeat the latest still-fresh auxiliary event at every
    basis observation.  The browser needs one row per source receipt, not one
    row per repeated snapshot.  A delta is therefore calculated only between
    successive unique event IDs and is reset after the configured freshness
    gap so a missing interval cannot be presented as one continuous change.
    """

    try:
        gap_limit = float(max_gap_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("max_gap_seconds must be finite and non-negative") from error
    if not math.isfinite(gap_limit) or gap_limit < 0:
        raise ValueError("max_gap_seconds must be finite and non-negative")
    unique: dict[str, dict[str, object]] = {}
    for snapshot in evidence:
        source = snapshot.get("futures_oi")
        if source is None:
            continue
        if not isinstance(source, Mapping):
            raise ValueError("futures_oi evidence must be an object")
        event_id = str(source.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("futures_oi evidence has no event_id")
        receipt = parse_instant(
            source.get("receipt_timestamp"), field="futures_oi receipt_timestamp"
        )
        try:
            oi = float(source.get("oi"))
        except (TypeError, ValueError) as error:
            raise ValueError("futures_oi evidence has no finite oi") from error
        if not math.isfinite(oi):
            raise ValueError("futures_oi evidence has no finite oi")
        price_value = source.get("price")
        price = None
        if price_value is not None:
            try:
                price = float(price_value)
            except (TypeError, ValueError) as error:
                raise ValueError("futures_oi evidence has a non-finite price") from error
            if not math.isfinite(price):
                raise ValueError("futures_oi evidence has a non-finite price")
        row = {
            "t": iso_utc(receipt),
            "oi": oi,
            "d": None,
            "p": price,
            "symbol": str(source.get("symbol", "")),
            "event_id": event_id,
        }
        previous = unique.get(event_id)
        if previous is not None and previous != row:
            raise ValueError(f"futures_oi event {event_id!r} changed between evidence snapshots")
        unique[event_id] = row

    ordered = sorted(
        unique.values(),
        key=lambda row: (parse_instant(row["t"]), str(row["event_id"])),
    )
    previous = None
    for row in ordered:
        if previous is not None:
            gap = (parse_instant(row["t"]) - parse_instant(previous["t"])).total_seconds()
            if 0 <= gap <= gap_limit:
                row["d"] = float(row["oi"]) - float(previous["oi"])
        previous = row
    return ordered


def option_strike_oi_rows(
    source_rows: Iterable[Mapping[str, object]],
    *,
    max_gap_seconds: float,
) -> list[dict[str, object]]:
    """Project per-contract option OI with causal, gap-safe receipt deltas."""

    try:
        gap_limit = float(max_gap_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("max_gap_seconds must be finite and non-negative") from error
    if not math.isfinite(gap_limit) or gap_limit < 0:
        raise ValueError("max_gap_seconds must be finite and non-negative")

    unique: dict[tuple[str, str], dict[str, object]] = {}
    for source in source_rows:
        event_id = str(source.get("event_id", "")).strip()
        symbol = str(source.get("symbol", "")).upper().strip()
        expiry = str(source.get("e", "")).strip()
        option_type = str(source.get("k", "")).upper().strip()
        if not event_id or not symbol or not expiry or option_type not in {"CE", "PE"}:
            raise ValueError("option strike OI row has incomplete identity")
        receipt = parse_instant(source.get("t"), field="option strike OI receipt timestamp")
        try:
            strike = float(source.get("s"))
            oi = float(source.get("oi"))
        except (TypeError, ValueError) as error:
            raise ValueError("option strike OI row has non-finite strike/OI") from error
        if not math.isfinite(strike) or not math.isfinite(oi):
            raise ValueError("option strike OI row has non-finite strike/OI")
        price_value = source.get("p")
        price = None
        if price_value is not None:
            try:
                price = float(price_value)
            except (TypeError, ValueError) as error:
                raise ValueError("option strike OI row has non-finite price") from error
            if not math.isfinite(price):
                raise ValueError("option strike OI row has non-finite price")
        volume_value = source.get("v")
        volume = None
        if volume_value is not None:
            try:
                volume = float(volume_value)
            except (TypeError, ValueError) as error:
                raise ValueError("option strike OI row has non-finite volume") from error
            if not math.isfinite(volume) or volume < 0:
                raise ValueError("option strike OI row has non-finite volume")
        row = {
            "t": iso_utc(receipt),
            "e": expiry,
            "k": option_type,
            "s": strike,
            "oi": oi,
            "d": None,
            "p": price,
            "v": volume,
            "dv": None,
            "vs": "MISSING" if volume is None else "BASELINE",
            "symbol": symbol,
            "event_id": event_id,
        }
        unique_key = (event_id, symbol)
        previous = unique.get(unique_key)
        if previous is not None and previous != row:
            raise ValueError(
                f"option strike OI event {event_id!r}/{symbol!r} changed between rows"
            )
        unique[unique_key] = row

    ordered = sorted(
        unique.values(),
        key=lambda row: (
            parse_instant(row["t"]),
            str(row["event_id"]),
            str(row["k"]),
            float(row["s"]),
            str(row["symbol"]),
        ),
    )
    previous_by_contract: dict[tuple[str, str, float, str], dict[str, object]] = {}
    for row in ordered:
        contract = (str(row["e"]), str(row["k"]), float(row["s"]), str(row["symbol"]))
        previous = previous_by_contract.get(contract)
        if previous is not None:
            gap = (parse_instant(row["t"]) - parse_instant(previous["t"])).total_seconds()
            if 0 <= gap <= gap_limit:
                row["d"] = float(row["oi"]) - float(previous["oi"])
                if row["v"] is None or previous["v"] is None:
                    row["vs"] = "MISSING"
                else:
                    volume_delta = float(row["v"]) - float(previous["v"])
                    if volume_delta < 0:
                        row["vs"] = "RESET"
                    else:
                        row["dv"] = volume_delta
                        row["vs"] = "VALID"
            elif row["v"] is not None:
                row["vs"] = "GAP_RESET"
        previous_by_contract[contract] = row
    return ordered


def futures_volume_rows(
    source_rows: Iterable[Mapping[str, object]],
    observations: Iterable[Mapping[str, object]],
    *,
    analysis_start: datetime,
    max_gap_seconds: float,
) -> list[dict[str, object]]:
    """Project the active Futures cumulative-volume counter after 09:45.

    Each accepted delta is attached to the already-verified synchronized basis
    observation generated by that exact Futures receipt.  The first counter,
    a reset, a missing value, or a material receipt gap is only a baseline.
    """

    try:
        gap_limit = float(max_gap_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("max_gap_seconds must be finite and non-negative") from error
    if not math.isfinite(gap_limit) or gap_limit < 0:
        raise ValueError("max_gap_seconds must be finite and non-negative")

    index_by_receipt: dict[datetime, float] = {}
    for source in observations:
        receipt = parse_instant(source.get("timestamp"), field="basis observation timestamp")
        try:
            index_price = float(source.get("index_price"))
        except (TypeError, ValueError) as error:
            raise ValueError("basis observation has no finite Index price") from error
        if not math.isfinite(index_price):
            raise ValueError("basis observation has no finite Index price")
        previous = index_by_receipt.get(receipt)
        if previous is not None and previous != index_price:
            raise ValueError("one Futures receipt has inconsistent synchronized Index prices")
        index_by_receipt[receipt] = index_price

    unique: dict[str, dict[str, object]] = {}
    for source in source_rows:
        event_id = str(source.get("event_id", "")).strip()
        symbol = str(source.get("symbol", "")).upper().strip()
        if not event_id or not symbol:
            raise ValueError("Futures market row has incomplete identity")
        receipt = parse_instant(source.get("t"), field="Futures market receipt timestamp")
        if receipt < analysis_start:
            continue
        try:
            price = float(source.get("p"))
        except (TypeError, ValueError) as error:
            raise ValueError("Futures market row has no finite price") from error
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Futures market row has no finite positive price")
        raw_volume = source.get("v")
        volume = None
        if raw_volume is not None:
            try:
                volume = float(raw_volume)
            except (TypeError, ValueError) as error:
                raise ValueError("Futures market row has non-finite cumulative volume") from error
            if not math.isfinite(volume) or volume < 0:
                raise ValueError("Futures market row has non-finite cumulative volume")
        row = {
            "t": iso_utc(receipt),
            "p": price,
            "v": volume,
            "dv": None,
            "vs": "MISSING" if volume is None else "BASELINE",
            "i": index_by_receipt.get(receipt),
            "symbol": symbol,
            "event_id": event_id,
        }
        previous = unique.get(event_id)
        if previous is not None and previous != row:
            raise ValueError(f"Futures market event {event_id!r} changed between rows")
        unique[event_id] = row

    ordered = sorted(
        unique.values(), key=lambda row: (parse_instant(row["t"]), str(row["event_id"]))
    )
    previous_by_symbol: dict[str, dict[str, object]] = {}
    for row in ordered:
        previous = previous_by_symbol.get(str(row["symbol"]))
        if previous is not None and row["v"] is not None and previous["v"] is not None:
            gap = (parse_instant(row["t"]) - parse_instant(previous["t"])).total_seconds()
            delta = float(row["v"]) - float(previous["v"])
            if gap > gap_limit:
                row["vs"] = "GAP_RESET"
            elif delta < 0:
                row["vs"] = "RESET"
            elif delta == 0:
                row["vs"] = "UNCHANGED"
            elif row["i"] is None:
                row["vs"] = "NO_SYNCHRONIZED_INDEX"
            else:
                row["dv"] = delta
                row["vs"] = "VALID"
        previous_by_symbol[str(row["symbol"])] = row
    return ordered


def _causal_index_matcher(
    observations: Iterable[Mapping[str, object]], *, max_age_seconds: float
):
    rows = sorted(
        (
            parse_instant(source.get("timestamp"), field="basis observation timestamp"),
            parse_instant(
                source.get("index_receipt_timestamp"), field="Index receipt timestamp"
            ),
            float(source.get("index_price")),
        )
        for source in observations
    )
    receipts = [row[0] for row in rows]

    def match(value: object) -> float | None:
        receipt = parse_instant(value, field="inventory receipt timestamp")
        position = bisect_right(receipts, receipt) - 1
        if position < 0:
            return None
        _, index_receipt, price = rows[position]
        age = (receipt - index_receipt).total_seconds()
        if age < 0 or age > max_age_seconds or not math.isfinite(price):
            return None
        return price

    return match


def _choose_intraday_control(
    bins: Mapping[float, float], weighted_price_sum: float, total_weight: float
) -> tuple[float, str]:
    maximum = max(bins.values())
    candidates = sorted(price for price, weight in bins.items() if weight == maximum)
    reason = "NO_TIE"
    if len(candidates) > 1:
        reason = "TIE_WEIGHTED_MEAN"
        mean = weighted_price_sum / total_weight
        distance = min(abs(price - mean) for price in candidates)
        candidates = [price for price in candidates if abs(price - mean) == distance]
    if len(candidates) > 1:
        reason = "TIE_LOWER_BIN"
    return min(candidates), reason


def _intraday_value_area(
    bins: Mapping[float, float], vpoc: float
) -> tuple[float, float, float]:
    total = sum(float(weight) for weight in bins.values())
    target = total * INTRADAY_VALUE_AREA_FRACTION
    low = high = float(vpoc)
    included = float(bins[vpoc])
    lower_bound, upper_bound = min(bins), max(bins)
    while included < target and (low > lower_bound or high < upper_bound):
        lower = low - INTRADAY_BIN_POINTS if low > lower_bound else None
        upper = high + INTRADAY_BIN_POINTS if high < upper_bound else None
        lower_weight = -1.0 if lower is None else float(bins.get(lower, 0.0))
        upper_weight = -1.0 if upper is None else float(bins.get(upper, 0.0))
        if lower is not None and upper is not None and math.isclose(
            lower_weight, upper_weight, rel_tol=0, abs_tol=1e-12
        ):
            low, high = lower, upper
            included += lower_weight + upper_weight
        elif upper is not None and upper_weight > lower_weight:
            high = upper
            included += upper_weight
        elif lower is not None:
            low = lower
            included += lower_weight
        else:
            break
    return low, high, included / total


def intraday_inventory_rows(
    observations: Iterable[Mapping[str, object]],
    futures_oi: Iterable[Mapping[str, object]],
    option_oi: Iterable[Mapping[str, object]],
    futures_volume: Iterable[Mapping[str, object]],
    strike_selection: Mapping[str, object],
    *,
    session: str,
    max_index_age_seconds: float,
) -> list[dict[str, object]]:
    """Build causal developing controls from 09:45 receipts in event order."""

    observation_rows = list(observations)
    match_index = _causal_index_matcher(
        observation_rows, max_age_seconds=float(max_index_age_seconds)
    )
    contributions: list[tuple[datetime, str, float, float, str]] = []

    for row in futures_oi:
        delta = row.get("d")
        if delta is None or not math.isfinite(float(delta)) or float(delta) == 0:
            continue
        index_price = match_index(row.get("t"))
        if index_price is None:
            continue
        family = "FUT_POS_OI_VPOC" if float(delta) > 0 else "FUT_NEG_OI_VPOC"
        contributions.append((
            parse_instant(row["t"]), family, index_price, abs(float(delta)),
            str(row.get("event_id", "")),
        ))

    selected_symbols = {
        str(contract.get("symbol", "")).upper(): option_type
        for option_type in ("CE", "PE")
        for contract in strike_selection.get(option_type, [])
        if isinstance(contract, Mapping) and contract.get("symbol")
    }
    selected_at = (
        parse_instant(strike_selection["selected_at"], field="strike-selection receipt")
        if strike_selection.get("available") is True
        else None
    )
    for row in option_oi:
        delta = row.get("d")
        symbol = str(row.get("symbol", "")).upper()
        option_type = selected_symbols.get(symbol)
        receipt = parse_instant(row.get("t"), field="option OI receipt timestamp")
        if (
            selected_at is None
            or receipt < selected_at
            or option_type is None
            or delta is None
            or not math.isfinite(float(delta))
            or float(delta) == 0
        ):
            continue
        index_price = match_index(receipt)
        if index_price is None:
            continue
        sign = "POS" if float(delta) > 0 else "NEG"
        contributions.append((
            receipt, f"{option_type}_{sign}_OI_VPOC", index_price, abs(float(delta)),
            f"{row.get('event_id', '')}:{symbol}",
        ))

    for row in futures_volume:
        delta = row.get("dv")
        index_price = row.get("i")
        if (
            row.get("vs") != "VALID"
            or delta is None
            or index_price is None
            or not math.isfinite(float(delta))
            or float(delta) <= 0
            or not math.isfinite(float(index_price))
        ):
            continue
        contributions.append((
            parse_instant(row["t"]), VOLUME_PROFILE_FAMILY,
            float(index_price), float(delta), str(row.get("event_id", "")),
        ))

    bins_by_family: dict[str, defaultdict[float, float]] = {}
    total_by_family: defaultdict[str, float] = defaultdict(float)
    weighted_by_family: defaultdict[str, float] = defaultdict(float)
    count_by_family: defaultdict[str, int] = defaultdict(int)
    last_display_by_family: dict[str, tuple[float, float | None, float | None]] = {}
    result: list[dict[str, object]] = []
    ordered = sorted(contributions, key=lambda row: (row[0], row[1], row[4]))
    position = 0
    while position < len(ordered):
        receipt = ordered[position][0]
        end = position
        changed: set[str] = set()
        while end < len(ordered) and ordered[end][0] == receipt:
            _, family, price, weight, _ = ordered[end]
            price_bin = float(round(price / INTRADAY_BIN_POINTS) * INTRADAY_BIN_POINTS)
            bins = bins_by_family.setdefault(family, defaultdict(float))
            bins[price_bin] += weight
            total_by_family[family] += weight
            weighted_by_family[family] += price * weight
            count_by_family[family] += 1
            changed.add(family)
            end += 1
        for family in sorted(changed):
            bins = bins_by_family[family]
            winner, tie_reason = _choose_intraday_control(
                bins, weighted_by_family[family], total_by_family[family]
            )
            low = high = achieved = None
            if family == VOLUME_PROFILE_FAMILY:
                low, high, achieved = _intraday_value_area(bins, winner)
            display_identity = (winner, low, high)
            if last_display_by_family.get(family) == display_identity:
                continue
            last_display_by_family[family] = display_identity
            result.append({
                "t": iso_utc(receipt),
                "scope": INTRADAY_SCOPE,
                "family": family,
                "status": "AVAILABLE",
                "control_value": winner,
                "value_area_low": low,
                "value_area_high": high,
                "value_area_target_fraction": (
                    INTRADAY_VALUE_AREA_FRACTION
                    if family == VOLUME_PROFILE_FAMILY else None
                ),
                "value_area_achieved_fraction": achieved,
                "total_weight": total_by_family[family],
                "evidence_count": count_by_family[family],
                "source_sessions": [session],
                "tie_break_reason": tie_reason,
            })
        position = end
    return result


STRIKE_REFERENCE_TIME = time(9, 45)


def bn_0945_close_reference(
    observations: Iterable[Mapping[str, object]],
    *,
    session: str,
    index_symbol: str | None,
    max_age_ms: float,
) -> dict[str, object]:
    """Select the last fresh synchronized BN Index receipt at/before 09:45 IST."""

    try:
        tolerance = float(max_age_ms)
    except (TypeError, ValueError) as error:
        raise ValueError("09:45 reference max_age_ms must be finite and non-negative") from error
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("09:45 reference max_age_ms must be finite and non-negative")
    target = session_instant(date.fromisoformat(session), STRIKE_REFERENCE_TIME)
    unique: dict[object, dict[str, object]] = {}
    for source in observations:
        receipt = parse_instant(
            source.get("index_receipt_timestamp"),
            field="synchronized Index receipt timestamp",
        )
        if receipt > target:
            continue
        try:
            price = float(source.get("index_price"))
        except (TypeError, ValueError) as error:
            raise ValueError("synchronized Index reference has a non-finite price") from error
        if not math.isfinite(price):
            raise ValueError("synchronized Index reference has a non-finite price")
        row = {"receipt": receipt, "price": price}
        previous = unique.get(receipt)
        if previous is not None and previous != row:
            raise ValueError("one synchronized Index receipt has inconsistent prices")
        unique[receipt] = row

    base = {
        "rule": "LAST_VALID_SYNCHRONIZED_INDEX_TICK_AT_OR_BEFORE_0945_IST",
        "target": iso_utc(target),
        "max_age_ms": tolerance,
        "symbol": index_symbol,
    }
    if not unique:
        return {**base, "status": "MISSING_0945_BN_CLOSE"}
    selected = max(unique.values(), key=lambda row: row["receipt"])
    age_ms = (target - selected["receipt"]).total_seconds() * 1000
    valid = 0 <= age_ms <= tolerance
    return {
        **base,
        "status": "VALID_0945_BN_CLOSE" if valid else "STALE_0945_BN_CLOSE",
        "age_ms": age_ms,
        "price": selected["price"],
        "receipt_timestamp": iso_utc(selected["receipt"]),
    }


def close_0945_strike_selection(
    strike_rows: Iterable[Mapping[str, object]],
    close_reference: Mapping[str, object],
) -> dict[str, object]:
    """Select and freeze ATM plus three OTM contracts from the 09:45 BN close."""

    unavailable = {
        "available": False,
        "rule": "BANKNIFTY_0945_CLOSE_ATM_PLUS_THREE_OTM_FIXED",
        "reason": "MISSING_OR_STALE_0945_BN_CLOSE",
        "volume_retained": False,
        "CE": [],
        "PE": [],
    }
    if close_reference.get("status") != "VALID_0945_BN_CLOSE":
        return {
            **unavailable,
            "reason": str(close_reference.get("status") or "MISSING_OR_STALE_0945_BN_CLOSE"),
            "reference_close": dict(close_reference),
        }
    try:
        reference_price = float(close_reference.get("price"))
        selection_start = parse_instant(
            close_reference.get("target"), field="09:45 BN-close target"
        )
    except (TypeError, ValueError) as error:
        raise ValueError("09:45 BN-close reference is invalid") from error
    if not math.isfinite(reference_price):
        raise ValueError("09:45 BN-close reference has a non-finite price")

    materialized = [dict(row) for row in strike_rows]
    groups: dict[tuple[object, str, str], list[dict[str, object]]] = {}
    for row in materialized:
        receipt = parse_instant(row.get("t"), field="option strike receipt timestamp")
        if receipt < selection_start:
            continue
        key = (receipt, str(row.get("event_id", "")), str(row.get("e", "")))
        groups.setdefault(key, []).append(row)

    for (receipt, event_id, expiry), rows in sorted(groups.items(), key=lambda item: item[0]):
        by_type: dict[str, dict[float, dict[str, object]]] = {"CE": {}, "PE": {}}
        duplicate = False
        for row in rows:
            option_type = str(row.get("k", ""))
            if option_type not in by_type:
                continue
            strike = float(row["s"])
            if strike in by_type[option_type]:
                duplicate = True
                break
            by_type[option_type][strike] = row
        if duplicate:
            raise ValueError(f"duplicate strike identity in option event {event_id!r}")
        common = sorted(set(by_type["CE"]) & set(by_type["PE"]))
        if not common:
            continue
        atm = min(common, key=lambda strike: (abs(strike - reference_price), strike))
        ce_strikes = [strike for strike in sorted(by_type["CE"]) if strike >= atm][:4]
        pe_strikes = [strike for strike in sorted(by_type["PE"], reverse=True) if strike <= atm][:4]
        if len(ce_strikes) < 4 or len(pe_strikes) < 4:
            continue

        def contracts(option_type: str, strikes: list[float]) -> list[dict[str, object]]:
            return [
                {
                    "slot": index,
                    "option_type": option_type,
                    "strike": strike,
                    "symbol": str(by_type[option_type][strike]["symbol"]),
                }
                for index, strike in enumerate(strikes, 1)
            ]

        ce = contracts("CE", ce_strikes)
        pe = contracts("PE", pe_strikes)
        selected_symbols = {str(row["symbol"]) for row in [*ce, *pe]}
        selected_rows = [
            row for row in materialized
            if str(row.get("e")) == expiry and str(row.get("symbol")) in selected_symbols
        ]
        volume_retained = bool(selected_rows) and all(row.get("v") is not None for row in selected_rows)
        return {
            "available": True,
            "rule": "BANKNIFTY_0945_CLOSE_ATM_PLUS_THREE_OTM_FIXED",
            "tie_break": "LOWER_LISTED_STRIKE",
            "fixed_for_session": True,
            "selected_at": iso_utc(receipt),
            "selection_event_id": event_id,
            "expiry": expiry,
            "reference_close": dict(close_reference),
            "atm": atm,
            "volume_retained": volume_retained,
            "CE": ce,
            "PE": pe,
        }
    return {
        **unavailable,
        "reason": "NO_COMPLETE_ATM_PLUS_THREE_OTM_CHAIN_AFTER_0945_CLOSE",
        "reference_close": dict(close_reference),
    }


def _inventory_unavailable(
    reason: str,
    *,
    enable_oi_vpoc: bool,
    enable_volume_profile: bool,
    details: Iterable[str] = (),
) -> dict[str, object]:
    return {
        "schema": "NEW_DIVERGENCE_BROWSER_INVENTORY_CONTEXT_V1",
        "status": "DISABLED" if not (enable_oi_vpoc or enable_volume_profile) else "UNAVAILABLE",
        "reason": reason,
        "details": list(details),
        "coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
        "frozen_for_session": True,
        "divergence_engine_input": False,
        "feature_flags": {
            "oi_vpoc": {"enabled": enable_oi_vpoc, "available": False},
            "volume_profile": {"enabled": enable_volume_profile, "available": False},
        },
        "snapshot_id": None,
        "cutoff_source_session": None,
        "source_chain": [],
        "bin_points": None,
        "value_area_fraction": None,
        "controls": [],
    }


def _verified_context_bundle(directory: Path) -> tuple[dict[str, object] | None, list[str]]:
    reasons: list[str] = []
    try:
        manifest = json.loads((directory / "sha256_manifest.json").read_text(encoding="utf-8"))
        files = manifest.get("files")
        if not isinstance(files, Mapping):
            raise ValueError("context hash manifest has no files object")
        for name in ("context.json", "source_manifest.json"):
            expected = files.get(name)
            path = directory / name
            if not isinstance(expected, str) or len(expected) != 64:
                reasons.append(f"MISSING_HASH:{name}")
            elif not path.is_file():
                reasons.append(f"MISSING_ARTIFACT:{name}")
            elif sha256_file(path) != expected:
                reasons.append(f"HASH_MISMATCH:{name}")
        if reasons:
            return None, reasons
        context = json.loads((directory / "context.json").read_text(encoding="utf-8"))
        if not isinstance(context, dict):
            raise ValueError("context payload is not an object")
        expected = {
            "schema": CONTEXT_SCHEMA,
            "status": "COMPLETE",
            "algorithm_version": CONTEXT_ALGORITHM_VERSION,
            "runtime_version": CONTEXT_RUNTIME_VERSION,
            "model_parameters_changed": False,
            "coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
            "bin_points": 25,
            "value_area_fraction": 0.70,
        }
        for field, value in expected.items():
            if context.get(field) != value:
                reasons.append(f"CONTEXT_IDENTITY_MISMATCH:{field}")
        if context.get("snapshot_id") != directory.name:
            reasons.append("SNAPSHOT_DIRECTORY_MISMATCH")
        if context.get("cutoff_source_session") != directory.parent.name:
            reasons.append("CUTOFF_DIRECTORY_MISMATCH")
        controls = context.get("controls")
        if not isinstance(controls, list):
            reasons.append("CONTEXT_CONTROLS_INVALID")
        else:
            seen_controls: set[tuple[str, str]] = set()
            for index, control in enumerate(controls):
                if not isinstance(control, Mapping):
                    reasons.append(f"CONTEXT_CONTROL_INVALID:{index}")
                    continue
                scope = str(control.get("scope", ""))
                family = str(control.get("family", ""))
                status = str(control.get("status", ""))
                identity = (scope, family)
                if (
                    scope not in {"1D", "2D", "3D"}
                    or family not in CONTEXT_FAMILIES
                    or status not in {"AVAILABLE", "UNAVAILABLE"}
                    or identity in seen_controls
                ):
                    reasons.append(f"CONTEXT_CONTROL_INVALID:{index}")
                    continue
                seen_controls.add(identity)
                sources = control.get("source_sessions")
                if not isinstance(sources, list) or not all(
                    isinstance(value, str) for value in sources
                ):
                    reasons.append(f"CONTEXT_CONTROL_SOURCES_INVALID:{index}")
                value = control.get("control_value")
                value_is_valid = not (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                )
                if status == "AVAILABLE" and not value_is_valid:
                    reasons.append(f"CONTEXT_CONTROL_VALUE_INVALID:{index}")
                if (
                    family == VOLUME_PROFILE_FAMILY
                    and status == "AVAILABLE"
                    and value_is_valid
                ):
                    low = control.get("value_area_low")
                    high = control.get("value_area_high")
                    if (
                        isinstance(low, bool)
                        or isinstance(high, bool)
                        or not isinstance(low, (int, float))
                        or not isinstance(high, (int, float))
                        or not math.isfinite(float(low))
                        or not math.isfinite(float(high))
                        or float(low) > float(value)
                        or float(value) > float(high)
                    ):
                        reasons.append(f"CONTEXT_VALUE_AREA_INVALID:{index}")
            expected_controls = {
                (scope, family)
                for scope in ("1D", "2D", "3D")
                for family in CONTEXT_FAMILIES
            }
            if seen_controls != expected_controls:
                reasons.append("CONTEXT_CONTROL_SET_INCOMPLETE")
        source_chain = context.get("source_chain")
        if not isinstance(source_chain, list):
            reasons.append("CONTEXT_SOURCE_CHAIN_INVALID")
        else:
            source_dates = []
            for index, row in enumerate(source_chain):
                if not isinstance(row, Mapping) or not isinstance(row.get("session"), str):
                    reasons.append(f"CONTEXT_SOURCE_SESSION_INVALID:{index}")
                    continue
                try:
                    source_dates.append(date.fromisoformat(str(row["session"])))
                except ValueError:
                    reasons.append(f"CONTEXT_SOURCE_SESSION_INVALID:{index}")
            try:
                cutoff = date.fromisoformat(directory.parent.name)
            except ValueError:
                reasons.append("CONTEXT_CUTOFF_INVALID")
            else:
                if (
                    not source_dates
                    or len(source_dates) > 3
                    or source_dates != sorted(set(source_dates))
                    or source_dates[-1] != cutoff
                ):
                    reasons.append("CONTEXT_SOURCE_CHAIN_INVALID")
        return (None if reasons else context), reasons
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        return None, [f"CONTEXT_BUNDLE_ERROR:{type(error).__name__}:{error}"]


def inventory_context_for_session(
    session: str,
    context_state_root: Path | None,
    *,
    enable_oi_vpoc: bool = True,
    enable_volume_profile: bool = True,
) -> dict[str, object]:
    """Select the newest verified context whose source cutoff precedes session."""

    if not (enable_oi_vpoc or enable_volume_profile):
        return _inventory_unavailable(
            "ALL_INVENTORY_FEATURES_DISABLED",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )
    if context_state_root is None:
        return _inventory_unavailable(
            "CONTEXT_STATE_ROOT_NOT_CONFIGURED",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )
    root = Path(context_state_root).resolve()
    daily = root / "daily_context"
    if not daily.is_dir():
        return _inventory_unavailable(
            "CONTEXT_STATE_ROOT_MISSING",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )
    replay_day = date.fromisoformat(session)
    candidates: list[tuple[date, Path]] = []
    for cutoff_directory in daily.iterdir():
        if not cutoff_directory.is_dir():
            continue
        try:
            cutoff = date.fromisoformat(cutoff_directory.name)
        except ValueError:
            continue
        if cutoff >= replay_day:
            continue
        candidates.extend(
            (cutoff, path)
            for path in cutoff_directory.iterdir()
            if path.is_dir()
        )
    if not candidates:
        return _inventory_unavailable(
            "NO_CONTEXT_STRICTLY_BEFORE_REPLAY_SESSION",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )

    newest_cutoff = max(cutoff for cutoff, _ in candidates)
    valid: list[dict[str, object]] = []
    rejected: list[str] = []
    for _, directory in sorted(
        (item for item in candidates if item[0] == newest_cutoff),
        key=lambda item: item[1].name,
    ):
        context, reasons = _verified_context_bundle(directory)
        if context is None:
            rejected.extend(f"{directory.name}:{reason}" for reason in reasons)
        else:
            valid.append(context)
    if not valid:
        return _inventory_unavailable(
            "NEWEST_PRIOR_CONTEXT_FAILED_VERIFICATION",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
            details=rejected,
        )
    selected = max(
        valid,
        key=lambda row: (str(row.get("created_at", "")), str(row.get("snapshot_id", ""))),
    )
    source_chain = selected.get("source_chain", [])
    if any(date.fromisoformat(str(row["session"])) >= replay_day for row in source_chain):
        return _inventory_unavailable(
            "CONTEXT_SOURCE_CHAIN_LEAKS_REPLAY_SESSION",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )

    projected_controls = []
    for source in selected["controls"]:
        if not isinstance(source, Mapping):
            continue
        family = str(source.get("family", ""))
        is_volume = family == VOLUME_PROFILE_FAMILY
        if (is_volume and not enable_volume_profile) or (not is_volume and not enable_oi_vpoc):
            continue
        projected_controls.append(
            {
                "scope": source.get("scope"),
                "family": family,
                "status": source.get("status"),
                "reason": source.get("reason"),
                "control_value": source.get("control_value"),
                "value_area_low": source.get("value_area_low"),
                "value_area_high": source.get("value_area_high"),
                "value_area_target_fraction": source.get("value_area_target_fraction"),
                "value_area_achieved_fraction": source.get("value_area_achieved_fraction"),
                "total_weight": source.get("total_weight"),
                "evidence_count": source.get("evidence_count"),
                "source_sessions": list(source.get("source_sessions", [])),
            }
        )
    oi_available = any(
        row["family"] != VOLUME_PROFILE_FAMILY and row["status"] == "AVAILABLE"
        for row in projected_controls
    )
    volume_available = any(
        row["family"] == VOLUME_PROFILE_FAMILY
        and row["status"] == "AVAILABLE"
        and row["value_area_low"] is not None
        and row["value_area_high"] is not None
        for row in projected_controls
    )
    enabled_available = [
        available
        for enabled, available in (
            (enable_oi_vpoc, oi_available),
            (enable_volume_profile, volume_available),
        )
        if enabled
    ]
    status = "AVAILABLE" if all(enabled_available) else "PARTIAL" if any(enabled_available) else "UNAVAILABLE"
    return {
        "schema": "NEW_DIVERGENCE_BROWSER_INVENTORY_CONTEXT_V1",
        "status": status,
        "reason": "VERIFIED_PRIOR_SESSION_CONTEXT",
        "details": rejected,
        "coordinate": selected.get("coordinate"),
        "frozen_for_session": True,
        "divergence_engine_input": False,
        "feature_flags": {
            "oi_vpoc": {"enabled": enable_oi_vpoc, "available": oi_available},
            "volume_profile": {
                "enabled": enable_volume_profile,
                "available": volume_available,
            },
        },
        "snapshot_id": selected.get("snapshot_id"),
        "cutoff_source_session": selected.get("cutoff_source_session"),
        "source_chain": source_chain,
        "bin_points": selected.get("bin_points"),
        "value_area_fraction": selected.get("value_area_fraction"),
        "controls": projected_controls,
    }


def session_payload(
    run_directory: Path,
    scope_sessions: dict[str, list[str]],
    inventory_context: Mapping[str, object] | None = None,
    *,
    enable_oi_vpoc: bool = True,
    enable_volume_profile: bool = True,
) -> dict[str, object]:
    root = Path(run_directory)
    integrity = verify_run(root)
    if not integrity["valid"]:
        raise ValueError(f"run integrity verification failed: {integrity['reasons']}")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((root / "engine_config.json").read_text(encoding="utf-8"))
    observations = _read_jsonl(root / "basis_observations.jsonl")
    evidence = _read_jsonl(root / "evidence_snapshots.jsonl")
    transitions = _read_jsonl(root / "transitions.jsonl")
    cash_integrity = validate_sample_bundle(root, expected_session=str(summary["session"]))
    cash_retained = bool(cash_integrity["valid"])
    cash_rows = _read_jsonl(root / SAMPLE_FILE) if cash_retained else []
    cash_manifest = cash_integrity.get("manifest", {}) if cash_retained else {}
    if len(evidence) != len(observations):
        raise ValueError("basis/evidence row counts differ")
    strike_relative = summary.get("files", {}).get("option_strike_oi")
    strike_retained = isinstance(strike_relative, str)
    raw_strike_rows = (
        _read_jsonl(root / strike_relative)
        if strike_retained
        else []
    )
    futures_market_relative = summary.get("files", {}).get("futures_market")
    futures_market_retained = isinstance(futures_market_relative, str)
    raw_futures_market = (
        _read_jsonl(root / futures_market_relative)
        if futures_market_retained
        else []
    )
    close_reference = bn_0945_close_reference(
        observations,
        session=str(summary["session"]),
        index_symbol=None if summary.get("index_symbol") is None else str(summary["index_symbol"]),
        max_age_ms=float(config["match_tolerance_ms"]),
    )
    option_analysis_start = parse_instant(
        close_reference["target"], field="09:45 option-analysis start"
    )
    analysis_observations = [
        row for row in observations
        if parse_instant(row["timestamp"], field="basis observation timestamp")
        >= option_analysis_start
    ]
    participation_max_age_seconds = float(config["participation_max_age_seconds"])
    oi_rows = futures_oi_rows(
        evidence,
        max_gap_seconds=participation_max_age_seconds,
    )
    analysis_oi_rows = [
        dict(row) for row in oi_rows
        if parse_instant(row["t"], field="Futures OI receipt timestamp")
        >= option_analysis_start
    ]
    previous_oi_by_symbol: dict[str, tuple[datetime, float]] = {}
    for row in analysis_oi_rows:
        symbol = str(row["symbol"])
        receipt = parse_instant(row["t"], field="Futures OI receipt timestamp")
        current_oi = float(row["oi"])
        previous = previous_oi_by_symbol.get(symbol)
        row["d"] = (
            None if previous is None
            or (receipt - previous[0]).total_seconds() > participation_max_age_seconds
            else current_oi - previous[1]
        )
        previous_oi_by_symbol[symbol] = (receipt, current_oi)
    analysis_delta_by_event = {
        str(row["event_id"]): row["d"] for row in analysis_oi_rows
    }
    for row in oi_rows:
        row["d"] = (
            analysis_delta_by_event.get(str(row["event_id"]))
            if parse_instant(row["t"], field="Futures OI receipt timestamp")
            >= option_analysis_start else None
        )
    validated_strike_rows = option_strike_oi_rows(
        raw_strike_rows,
        max_gap_seconds=participation_max_age_seconds,
    )
    # Option flow and snapshots retain a hard 09:45 boundary. Re-project them
    # so their first receipt is a true baseline and no opening delta leaks.
    strike_rows = option_strike_oi_rows(
        (
            row for row in validated_strike_rows
            if parse_instant(row["t"]) >= option_analysis_start
        ),
        max_gap_seconds=participation_max_age_seconds,
    )
    strike_selection = close_0945_strike_selection(strike_rows, close_reference)
    if strike_selection.get("available") is True:
        selected_at = parse_instant(
            strike_selection["selected_at"], field="09:45 strike-selection receipt timestamp"
        )
        selected_expiry = str(strike_selection["expiry"])
        for row in strike_rows:
            if (
                str(row.get("e")) == selected_expiry
                and parse_instant(row["t"]) == selected_at
            ):
                row["d"] = None
                row["dv"] = None
                row["vs"] = "MISSING" if row.get("v") is None else "BASELINE"
    projected_futures_volume = futures_volume_rows(
        raw_futures_market,
        analysis_observations,
        analysis_start=option_analysis_start,
        max_gap_seconds=float(config["participation_max_age_seconds"]),
    )
    intraday_rows = intraday_inventory_rows(
        analysis_observations,
        analysis_oi_rows if enable_oi_vpoc else (),
        strike_rows if enable_oi_vpoc else (),
        projected_futures_volume if enable_volume_profile else (),
        strike_selection,
        session=str(summary["session"]),
        max_index_age_seconds=5.0,
    )
    intraday_oi_available = any(
        row["family"] != VOLUME_PROFILE_FAMILY for row in intraday_rows
    )
    intraday_volume_available = any(
        row["family"] == VOLUME_PROFILE_FAMILY for row in intraday_rows
    )
    enabled_intraday = [
        available
        for enabled, available in (
            (enable_oi_vpoc, intraday_oi_available),
            (enable_volume_profile, intraday_volume_available),
        )
        if enabled
    ]
    intraday_status = (
        "DISABLED" if not enabled_intraday
        else "AVAILABLE" if all(enabled_intraday)
        else "PARTIAL" if any(enabled_intraday)
        else "UNAVAILABLE"
    )
    price_rows = ({
        "t": row["timestamp"],
        "ist": row["timestamp_ist"],
        "i": row["index_price"],
        "f": row["futures_price"],
        "b": row["basis"],
        "age": row["synchronization_age_ms"],
    } for row in observations)
    projection_start = parse_instant(
        observations[0]["timestamp"], field="first basis observation timestamp"
    )
    return {
        "schema": "NEW_DIVERGENCE_BROWSER_PAYLOAD_V1",
        "classification": CLASSIFICATION,
        "session": summary["session"],
        "summary": summary,
        "config": config,
        "actual_scope_sessions": scope_sessions,
        "inventory_context": dict(inventory_context) if inventory_context is not None else _inventory_unavailable(
            "CONTEXT_STATE_ROOT_NOT_CONFIGURED",
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        ),
        "intraday_inventory": {
            "schema": "NEW_DIVERGENCE_BROWSER_INTRADAY_INVENTORY_V1",
            "status": intraday_status,
            "reason": (
                "CAUSAL_0945_VISIBLE_PREFIX_PROFILE"
                if intraday_rows else
                "FUTURES_MARKET_ARTIFACT_NOT_RETAINED"
                if enable_volume_profile and not futures_market_retained else
                "NO_ELIGIBLE_POST_0945_PROFILE_CHANGE"
            ),
            "scope": INTRADAY_SCOPE,
            "analysis_start": iso_utc(option_analysis_start),
            "coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
            "bin_points": INTRADAY_BIN_POINTS,
            "value_area_fraction": INTRADAY_VALUE_AREA_FRACTION,
            "developing_at_cursor": True,
            "divergence_engine_input": False,
            "futures_market_retained": futures_market_retained,
            "feature_flags": {
                "oi_vpoc": {
                    "enabled": enable_oi_vpoc,
                    "available": intraday_oi_available,
                },
                "volume_profile": {
                    "enabled": enable_volume_profile,
                    "available": intraday_volume_available,
                },
            },
            **_pack(
                intraday_rows,
                (
                    "t", "scope", "family", "status", "control_value",
                    "value_area_low", "value_area_high",
                    "value_area_target_fraction", "value_area_achieved_fraction",
                    "total_weight", "evidence_count", "source_sessions",
                    "tie_break_reason",
                ),
            ),
        },
        "price": _pack(price_rows, ("t", "ist", "i", "f", "b", "age")),
        "futures_oi": _pack(oi_rows, ("t", "oi", "d", "p", "symbol", "event_id")),
        "option_strike_oi": {
            **_pack(
                strike_rows,
                ("t", "e", "k", "s", "oi", "d", "p", "v", "dv", "vs", "symbol", "event_id"),
            ),
            "retained": strike_retained,
            "analysis_start": iso_utc(option_analysis_start),
            "volume_retained": bool(strike_selection.get("volume_retained", False)),
            "strike_selection": strike_selection,
        },
        "cash_participation": {
            **_pack(
                cash_rows,
                (
                    "t",
                    "minute_ist",
                    "cash_breadth",
                    "index_participant_volume",
                    "breadth_coverage_count",
                    "volume_coverage_count",
                    "expected_constituent_count",
                    "status",
                ),
            ),
            "retained": cash_retained,
            "parameters": list(cash_manifest.get("parameters", [])),
            "manifest_file": MANIFEST_FILE if cash_retained else None,
            "integrity": {
                "valid": bool(cash_integrity["valid"]),
                "reasons": list(cash_integrity["reasons"]),
            },
        },
        "states": _pack(({
            "t": row["as_of"],
            "s": row["basis_state"],
            "n": row["supporting_horizons"],
            "p": row["basis_percentile"],
            "z": row["basis_robust_z"],
            "c": row["contradictions"],
        } for row in evidence), ("t", "s", "n", "p", "z", "c")),
        "transitions": transitions,
        "confirmed_zones": _zones_from(transitions, projection_start),
        "projection_window": {
            "start": iso_utc(projection_start),
            "bar_analysis_start": iso_utc(option_analysis_start),
            "rule": "FULL_MARKET_HISTORY_WITH_0945_BAR_BASELINE",
            "engine_run_retained_full_session": True,
        },
        "rendering_policy": {
            "availability_clock": "published_at",
            "timezone": "Asia/Kolkata",
            "future_records_rendered": False,
            "payload_transport": "0945_SESSION_SUFFIX_STATIC",
            "browser_inference_calculation": "NONE",
            "chart_x_axis": "RECEIPT_TIMESTAMP",
            "futures_oi_source": "VERIFIED_EVIDENCE_SNAPSHOTS",
            "futures_oi_delta": "SUCCESSIVE_UNIQUE_RECEIPT_DIFFERENCE_GAP_SAFE",
            "option_strike_oi_source": "VERIFIED_DEDICATED_RECEIPT_ARTIFACT",
            "option_strike_oi_delta": "SUCCESSIVE_CONTRACT_RECEIPT_DIFFERENCE_GAP_SAFE",
            "option_strike_volume_delta": "SUCCESSIVE_CUMULATIVE_VOLUME_DIFFERENCE_GAP_AND_RESET_SAFE",
            "intraday_inventory": "CAUSAL_DEVELOPING_0945_TO_VISIBLE_CURSOR",
            "intraday_futures_volume": "SUCCESSIVE_CUMULATIVE_COUNTER_GAP_AND_RESET_SAFE",
            "intraday_inventory_engine_input": False,
            "option_strike_snapshot": "LATEST_VISIBLE_RECEIPT_ABSOLUTE_OI_WITH_SIGNED_DELTA",
            "option_strike_expiry": "LATEST_VISIBLE_SELECTED_EXPIRY",
            "option_flow_strikes": "BANKNIFTY_0945_CLOSE_ATM_PLUS_THREE_OTM_FIXED",
            "option_analysis_start": "09:45:00_ASIA_KOLKATA_HARD_BOUNDARY",
            "browser_market_history_start": "FIRST_SYNCHRONIZED_SESSION_OBSERVATION",
            "browser_bar_analysis_start": "09:45:00_ASIA_KOLKATA_BASELINE",
            "cash_participation_start": "09:45:00_ASIA_KOLKATA_HARD_BOUNDARY",
            "cash_breadth": "EQUAL_CONSTITUENT_VOTE_VERSUS_FROZEN_0945_REFERENCE",
            "index_participant_volume": "UNWEIGHTED_CONSTITUENT_MINUTE_SHARE_SUM",
            "cash_participation_engine_input": False,
            "inventory_context_engine_input": False,
            "inventory_context_coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
            "inventory_context_selection": "NEWEST_VERIFIED_SOURCE_CUTOFF_STRICTLY_BEFORE_SESSION",
            "aligned_chart_x_domain": "VISIBLE_PRICE_RECEIPT_PREFIX",
            "candidate_transitions_coloured_as_zones": False,
        },
    }


def build_browser(
    run_root: Path,
    output_root: Path,
    *,
    context_state_root: Path | None = None,
    enable_oi_vpoc: bool = True,
    enable_volume_profile: bool = True,
) -> Path:
    runs = Path(run_root).resolve()
    target = Path(output_root).resolve()
    catalog = write_session_catalog(runs)
    target.mkdir(parents=True, exist_ok=True)
    payload_dir = target / "sessions"
    payload_dir.mkdir(exist_ok=True)
    ui_sessions = []
    for entry in catalog["sessions"]:
        session = str(entry["session"])
        if not entry["eligible"]:
            ui_sessions.append({**entry, "payload": None})
            continue
        run_directory = runs / session
        inventory = inventory_context_for_session(
            session,
            context_state_root,
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )
        payload = session_payload(
            run_directory,
            entry["actual_scope_sessions"],
            inventory,
            enable_oi_vpoc=enable_oi_vpoc,
            enable_volume_profile=enable_volume_profile,
        )
        atomic_json(payload_dir / f"{session}.json", payload)
        ui_sessions.append({**entry, "payload": f"sessions/{session}.json"})
    ui_catalog = {**catalog, "sessions": ui_sessions}
    atomic_json(target / "catalog.json", ui_catalog)
    static = Path(__file__).with_name("static_new")
    assets = ("index.html", "replay.html", "app.js", "style.css")
    for name in assets:
        shutil.copyfile(static / name, target / name)
    hashes = {
        name: hashlib.sha256((target / name).read_bytes()).hexdigest()
        for name in (*assets, "catalog.json")
    }
    atomic_json(target / "build_manifest.json", {
        "schema": "NEW_DIVERGENCE_BROWSER_BUILD_V1",
        "classification": CLASSIFICATION,
        "runtime_version": RUNTIME_VERSION,
        "sessions": [entry["session"] for entry in ui_sessions if entry["eligible"]],
        "inventory_features": {
            "oi_vpoc": enable_oi_vpoc,
            "volume_profile": enable_volume_profile,
            "context_state_configured": context_state_root is not None,
        },
        "files_sha256": hashes,
    })
    return target
