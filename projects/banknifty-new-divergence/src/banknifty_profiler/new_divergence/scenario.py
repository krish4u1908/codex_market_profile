"""Deterministic, causal BankNifty inventory scenario classification."""

from __future__ import annotations

from datetime import timedelta
import math
from typing import Mapping
from zoneinfo import ZoneInfo

from .clock import parse_instant
from .short_trap import short_trap_scenario


IST = ZoneInfo("Asia/Kolkata")
PRICE_MOVE = 15.0
BASIS_TOLERANCE = 10.0
LEVEL_MARGIN = 5.0
ACCEPTANCE_SECONDS = 30.0


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _market_rows(bundle: Mapping[str, object]) -> list[dict[str, object]]:
    source = bundle.get("recent_market", [])
    result: list[dict[str, object]] = []
    if not isinstance(source, list):
        return result
    for row in source:
        if not isinstance(row, Mapping):
            continue
        stamp = row.get("t") or row.get("timestamp")
        index = _finite(row.get("i", row.get("index_price")))
        futures = _finite(row.get("f", row.get("futures_price")))
        basis = _finite(row.get("b", row.get("basis")))
        if stamp is None or index is None or futures is None or basis is None:
            continue
        try:
            instant = parse_instant(str(stamp))
        except ValueError:
            continue
        result.append({"t": instant, "i": index, "f": futures, "b": basis})
    return sorted(result, key=lambda row: row["t"])


def _oi_rows(bundle: Mapping[str, object]) -> list[dict[str, object]]:
    source = bundle.get("recent_futures_oi", [])
    result: list[dict[str, object]] = []
    if not isinstance(source, list):
        return result
    for row in source:
        if not isinstance(row, Mapping):
            continue
        stamp = row.get("t") or row.get("receipt_timestamp")
        oi = _finite(row.get("oi"))
        price = _finite(row.get("p", row.get("price")))
        if stamp is None or oi is None or price is None:
            continue
        try:
            instant = parse_instant(str(stamp))
        except ValueError:
            continue
        result.append({"t": instant, "oi": oi, "p": price})
    return sorted(result, key=lambda row: row["t"])


def _window(rows: list[dict[str, object]], minutes: int) -> list[dict[str, object]]:
    if not rows:
        return []
    cutoff = rows[-1]["t"] - timedelta(minutes=minutes)
    selected = [row for row in rows if row["t"] >= cutoff]
    return selected if len(selected) >= 2 else rows[-2:]


def _control(bundle: Mapping[str, object], family: str) -> float | None:
    controls = bundle.get("visible_intraday_inventory", {})
    row = controls.get(family) if isinstance(controls, Mapping) else None
    return _finite(row.get("control_value")) if isinstance(row, Mapping) else None


def _shift(bundle: Mapping[str, object], family: str) -> float | None:
    history = bundle.get("recent_intraday_inventory_shifts", {})
    rows = history.get(family, []) if isinstance(history, Mapping) else []
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    previous, current = rows[-2], rows[-1]
    if not isinstance(previous, Mapping) or not isinstance(current, Mapping):
        return None
    old = _finite(previous.get("control_value"))
    new = _finite(current.get("control_value"))
    return None if old is None or new is None else new - old


def _accepted(
    rows: list[dict[str, object]], level: float | None, *, above: bool,
) -> bool:
    if level is None or len(rows) < 2:
        return False
    predicate = (
        (lambda row: float(row["i"]) >= level + LEVEL_MARGIN)
        if above else
        (lambda row: float(row["i"]) <= level - LEVEL_MARGIN)
    )
    trailing: list[dict[str, object]] = []
    for row in reversed(rows):
        if not predicate(row):
            break
        trailing.append(row)
    return (
        len(trailing) >= 2
        and (trailing[0]["t"] - trailing[-1]["t"]).total_seconds()
        >= ACCEPTANCE_SECONDS
    )


def _result(
    scenario: str,
    direction: str,
    stage: str,
    confidence: str,
    evidence: list[str],
    confirmation: str,
    invalidation: str,
    expected: str,
    metrics: Mapping[str, object],
    rules: list[str],
    missing: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema": "NEW_DIVERGENCE_INVENTORY_SCENARIO_V1",
        "analysis_method": "TRANSPARENT_CAUSAL_SCENARIO_ENGINE",
        "scenario": scenario,
        "direction": direction,
        "stage": stage,
        "confidence": confidence,
        "horizon_minutes": 15,
        "evidence": evidence,
        "confirmation": confirmation,
        "invalidation": invalidation,
        "expected": expected,
        "metrics": dict(metrics),
        "rules": rules,
        "missing_evidence": list(missing or []),
        "experimental": True,
    }


def inventory_scenario(bundle: Mapping[str, object]) -> dict[str, object]:
    """Classify four causal buildup/trap narratives or abstain."""
    market = _market_rows(bundle)
    futures_oi = _oi_rows(bundle)
    missing = []
    if len(market) < 2:
        missing.append("RECENT_SYNCHRONIZED_MARKET_HISTORY")
    if len(futures_oi) < 2:
        missing.append("RECENT_FUTURES_OI_HISTORY")
    if missing:
        return _result(
            "NO_EDGE", "NO_EDGE", "UNAVAILABLE", "LOW", [],
            "Wait for sufficient synchronized market and Futures OI history.",
            "Not applicable while causal history is unavailable.",
            "No directional classification.", {}, ["INSUFFICIENT_CAUSAL_HISTORY"], missing,
        )

    latest_time = market[-1]["t"]
    local_time = latest_time.astimezone(IST).time()
    if not (local_time.hour > 9 or (local_time.hour == 9 and local_time.minute >= 45)) \
            or (local_time.hour > 15 or (local_time.hour == 15 and local_time.minute >= 0)):
        return _result(
            "NO_EDGE", "NO_EDGE", "TIME_FILTERED", "LOW", [],
            "Directional scenarios are evaluated only from 09:45 to 15:00 IST.",
            "Not applicable outside the configured decision window.",
            "Observe only; opening and closing volatility are excluded.", {},
            ["DECISION_WINDOW_0945_1500"],
        )

    causal_short_trap = short_trap_scenario(bundle)
    if causal_short_trap is not None:
        return causal_short_trap

    market5 = _window(market, 5)
    oi5 = _window(futures_oi, 5)
    oi15 = _window(futures_oi, 15)
    index_move = float(market5[-1]["i"]) - float(market5[0]["i"])
    futures_move = float(market5[-1]["f"]) - float(market5[0]["f"])
    basis_move = float(market5[-1]["b"]) - float(market5[0]["b"])
    oi_move = float(oi5[-1]["oi"]) - float(oi5[0]["oi"])
    latest_index = float(market[-1]["i"])
    ce_control = _control(bundle, "CE_POS_OI_VPOC")
    pe_control = _control(bundle, "PE_POS_OI_VPOC")
    ce_shift = _shift(bundle, "CE_POS_OI_VPOC")
    pe_shift = _shift(bundle, "PE_POS_OI_VPOC")
    metrics = {
        "index_change_5m": index_move,
        "futures_change_5m": futures_move,
        "basis_change_5m": basis_move,
        "futures_oi_change_5m": oi_move,
        "index": latest_index,
        "ce_positive_control": ce_control,
        "pe_positive_control": pe_control,
    }

    # A trap requires an observed buildup followed by OI liquidation. The OI
    # peak is the causal phase boundary and must not be the first or last row.
    peak_index = max(range(len(oi15)), key=lambda index: float(oi15[index]["oi"]))
    if 0 < peak_index < len(oi15) - 1:
        first, peak, last = oi15[0], oi15[peak_index], oi15[-1]
        build_oi = float(peak["oi"]) - float(first["oi"])
        unwind_oi = float(last["oi"]) - float(peak["oi"])
        build_price = float(peak["p"]) - float(first["p"])
        reversal_price = float(last["p"]) - float(peak["p"])
        recent_high = max(float(row["i"]) for row in market)
        recent_low = min(float(row["i"]) for row in market)
        failed_resistance = (
            ce_control is not None and recent_high >= ce_control
            and latest_index <= ce_control - LEVEL_MARGIN
        )
        reclaimed_support = (
            pe_control is not None and recent_low <= pe_control
            and latest_index >= pe_control + LEVEL_MARGIN
        )
        if (
            build_oi > 0 and unwind_oi < 0
            and build_price >= PRICE_MOVE and reversal_price <= -PRICE_MOVE
            and failed_resistance and basis_move < 0
        ):
            return _result(
                "LONG_TRAP", "DOWN", "CONFIRMED", "MEDIUM",
                [
                    f"Futures rose {build_price:+g} while OI increased {build_oi:+g}, then fell {reversal_price:+g} while OI changed {unwind_oi:+g}.",
                    f"Bank Nifty failed back below CE control {ce_control:g}.",
                    f"Basis changed {basis_move:+g} over five minutes, showing Futures relative weakness.",
                ],
                f"Continued acceptance below {ce_control:g} with weakening PE/Futures inventory.",
                f"Reclaim and acceptance above {ce_control:g}.",
                "Downside continuation toward the nearest verified support is possible.",
                metrics, ["OBSERVED_LONG_BUILDUP", "FUTURES_LONG_LIQUIDATION", "FAILED_CE_CONTROL", "BASIS_CONTRACTION"],
                ["OPTION_PREMIUM_CLASSIFICATION"],
            )

    long_setup = index_move >= PRICE_MOVE and futures_move >= PRICE_MOVE and oi_move > 0
    short_setup = index_move <= -PRICE_MOVE and futures_move <= -PRICE_MOVE and oi_move > 0
    if long_setup:
        basis_ok = basis_move >= -BASIS_TOLERANCE
        resistance_accepted = _accepted(market, ce_control, above=True)
        pe_supportive = pe_control is not None and pe_control <= latest_index
        confirmed = basis_ok and pe_supportive and (resistance_accepted or (ce_shift or 0) > 0)
        return _result(
            "TRUE_LONG_BUILDUP" if confirmed else "POTENTIAL_LONG_BUILDUP",
            "UP", "CONFIRMED" if confirmed else "POTENTIAL",
            "MEDIUM" if confirmed else "LOW",
            [
                f"Bank Nifty changed {index_move:+g} and Futures changed {futures_move:+g} over five minutes.",
                f"Futures OI changed {oi_move:+g}; basis changed {basis_move:+g}.",
                f"PE positive-OI control is {pe_control:g}." if pe_control is not None else "PE positive-OI control is unavailable.",
            ],
            "Acceptance above CE resistance with stable/expanding basis and persistent PE support.",
            "Loss of PE support or a failed breakout accompanied by Futures OI liquidation.",
            "Upside continuation is possible after resistance acceptance." if confirmed else "Long buildup is present but resistance confirmation is incomplete.",
            metrics, ["PRICE_UP", "FUTURES_UP", "FUTURES_OI_UP", "BASIS_NOT_CONTRACTING" if basis_ok else "BASIS_CONTRACTING"],
            ["OPTION_PREMIUM_CLASSIFICATION"],
        )
    if short_setup:
        basis_ok = basis_move <= BASIS_TOLERANCE
        support_accepted = _accepted(market, pe_control, above=False)
        ce_resistance = ce_control is not None and ce_control >= latest_index
        confirmed = basis_ok and ce_resistance and (support_accepted or (pe_shift or 0) < 0)
        return _result(
            "TRUE_SHORT_BUILDUP" if confirmed else "POTENTIAL_SHORT_BUILDUP",
            "DOWN", "CONFIRMED" if confirmed else "POTENTIAL",
            "MEDIUM" if confirmed else "LOW",
            [
                f"Bank Nifty changed {index_move:+g} and Futures changed {futures_move:+g} over five minutes.",
                f"Futures OI changed {oi_move:+g}; basis changed {basis_move:+g}.",
                f"CE positive-OI control is {ce_control:g}." if ce_control is not None else "CE positive-OI control is unavailable.",
            ],
            "Acceptance below PE support with stable/contracting basis and persistent CE resistance.",
            "Reclaim of PE support or a failed breakdown accompanied by Futures OI liquidation.",
            "Downside continuation is possible after support acceptance." if confirmed else "Short buildup is present but support confirmation is incomplete.",
            metrics, ["PRICE_DOWN", "FUTURES_DOWN", "FUTURES_OI_UP", "BASIS_NOT_EXPANDING" if basis_ok else "BASIS_EXPANDING"],
            ["OPTION_PREMIUM_CLASSIFICATION"],
        )

    return _result(
        "NO_EDGE", "NO_EDGE", "UNRESOLVED", "LOW",
        [
            f"Bank Nifty changed {index_move:+g}, Futures {futures_move:+g}, Futures OI {oi_move:+g}, and basis {basis_move:+g} over five minutes."
        ],
        "A synchronized buildup or a fully observed trap sequence must appear.",
        "Not applicable while the four-scenario evidence remains incomplete.",
        "Rotation or unresolved inventory interaction remains the base case.",
        metrics, ["NO_FOUR_SCENARIO_CONFIRMATION"],
        ["OPTION_PREMIUM_CLASSIFICATION"],
    )
