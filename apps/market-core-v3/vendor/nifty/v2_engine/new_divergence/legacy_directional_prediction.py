"""Aggressive causal direction classification independent of VPOC.

The primary direction is decided from synchronized price, Futures, basis,
Futures OI, weighted Cash and India VIX.  Intraday VPOC is deliberately only a
confidence/evidence modifier: it cannot create, suppress or reverse the call.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import timedelta
import math
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo

from .clock import iso_utc, parse_instant


HORIZON_MINUTES = 5
IST = ZoneInfo("Asia/Kolkata")
DECISION_STATES = {
    "AGGRESSIVE_LONG",
    "FUTURES_LED_LONG",
    "SHORT_COVERING_RALLY",
    "LONG_TRAP_RISK",
    "AGGRESSIVE_SHORT",
    "FUTURES_LED_SHORT",
    "LONG_UNWINDING_DECLINE",
    "SHORT_SQUEEZE_RISK",
    "UP_PRESSURE",
    "DOWN_PRESSURE",
}


def _finite(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _rows(
    source: object,
    *,
    timestamp_keys: tuple[str, ...] = ("t", "timestamp", "receipt_timestamp"),
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if not isinstance(source, list):
        return result
    for item in source:
        if not isinstance(item, Mapping):
            continue
        stamp = next((item.get(key) for key in timestamp_keys if item.get(key)), None)
        if stamp is None:
            continue
        try:
            instant = parse_instant(str(stamp))
        except ValueError:
            continue
        result.append({**dict(item), "_instant": instant, "t": iso_utc(instant)})
    return sorted(result, key=lambda row: row["_instant"])


def _window(rows: list[dict[str, object]], minutes: int = HORIZON_MINUTES) -> list[dict[str, object]]:
    if len(rows) < 2:
        return rows
    cutoff = rows[-1]["_instant"] - timedelta(minutes=minutes)
    selected = [row for row in rows if row["_instant"] >= cutoff]
    return selected if len(selected) >= 2 else rows[-2:]


def _value(row: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        value = _finite(row.get(key))
        if value is not None:
            return value
    return None


def _move(rows: list[dict[str, object]], *keys: str) -> float | None:
    selected = [(_value(row, *keys), row) for row in _window(rows)]
    values = [(value, row) for value, row in selected if value is not None]
    if len(values) < 2:
        return None
    return float(values[-1][0]) - float(values[0][0])


def _sign(value: float | None, tolerance: float = 0.0) -> int:
    if value is None or abs(value) <= tolerance:
        return 0
    return 1 if value > 0 else -1


def _bounded(value: float | None, scale: float, maximum: float) -> float:
    if value is None or scale <= 0:
        return 0.0
    return max(-maximum, min(maximum, value / scale * maximum))


def _cash_vix(bundle: Mapping[str, object]) -> tuple[dict[str, object] | None, float | None, float | None]:
    rows = _rows(bundle.get("recent_cash_vix", []))
    if not rows:
        return None, None, None
    latest = rows[-1]
    cash_change = _value(latest, "cash_rolling_change", "cash_momentum_5m")
    vix_change = _value(latest, "vix_rolling_change", "vix_rate_5m_pct")
    return latest, cash_change, vix_change


def _vpoc_modifier(bundle: Mapping[str, object], direction: str, index: float) -> tuple[float, str]:
    """Return a bounded alignment modifier without changing direction."""
    controls = bundle.get("visible_intraday_inventory", {})
    history = bundle.get("recent_intraday_inventory_shifts", {})
    aligned = 0.0
    reasons: list[str] = []
    if isinstance(history, Mapping):
        deltas = []
        for values in history.values():
            if not isinstance(values, list) or len(values) < 2:
                continue
            old = _finite(values[-2].get("control_value")) if isinstance(values[-2], Mapping) else None
            new = _finite(values[-1].get("control_value")) if isinstance(values[-1], Mapping) else None
            if old is not None and new is not None and old != new:
                deltas.append(new - old)
        net = sum(_sign(value) for value in deltas)
        if net:
            agrees = (direction == "UP" and net > 0) or (direction == "DOWN" and net < 0)
            aligned += 0.75 if agrees else -0.75
            reasons.append(f"latest VPOC migration vote {net:+d} {'aligns' if agrees else 'conflicts'}")
    if isinstance(controls, Mapping):
        pe = controls.get("PE_POS_OI_VPOC")
        ce = controls.get("CE_POS_OI_VPOC")
        pe_level = _finite(pe.get("control_value")) if isinstance(pe, Mapping) else None
        ce_level = _finite(ce.get("control_value")) if isinstance(ce, Mapping) else None
        acceptance = (
            direction == "UP" and pe_level is not None and index >= pe_level
        ) or (
            direction == "DOWN" and ce_level is not None and index <= ce_level
        )
        conflict = (
            direction == "UP" and ce_level is not None and index < ce_level
        ) or (
            direction == "DOWN" and pe_level is not None and index > pe_level
        )
        if acceptance:
            aligned += 0.5
            reasons.append("price is accepted on the supportive side of the positive-OI control")
        elif conflict:
            aligned -= 0.5
            reasons.append("nearest positive-OI control conflicts with the primary call")
    return max(-1.25, min(1.25, aligned)), "; ".join(reasons) or "VPOC unavailable/neutral"


def predict_direction(bundle: Mapping[str, object]) -> dict[str, object]:
    """Force one causal UP/DOWN opinion and name the underlying market state."""
    market = _rows(bundle.get("recent_market", []))
    oi = _rows(bundle.get("recent_futures_oi", []))
    if not market:
        raise ValueError("direction prediction requires synchronized market history")
    latest = market[-1]
    index = _value(latest, "i", "index_price")
    if index is None:
        raise ValueError("direction prediction requires a finite NIFTY index")

    index_move = _move(market, "i", "index_price")
    futures_move = _move(market, "f", "futures_price")
    basis_move = _move(market, "b", "basis")
    oi_move = _move(oi, "oi")
    cash_row, cash_change, vix_change = _cash_vix(bundle)
    price_sign = _sign(index_move, 0.25)
    futures_sign = _sign(futures_move, 0.25)
    basis_sign = _sign(basis_move, 0.10)
    oi_sign = _sign(oi_move)
    cash_sign = _sign(cash_change, 0.0005)
    vix_sign = _sign(vix_change, 0.0005)

    # Primary score excludes VPOC by contract.  OI is interpreted through the
    # price response: rising OI strengthens that direction, falling OI labels
    # covering/unwinding but still supports the observed short-horizon move.
    score = _bounded(index_move, 15.0, 3.0) + _bounded(futures_move, 15.0, 2.0)
    score += _bounded(basis_move, 10.0, 1.25)
    score += cash_sign * 2.25
    score -= vix_sign * 1.50
    if price_sign:
        score += price_sign * (2.0 if oi_sign > 0 else 1.15 if oi_sign < 0 else 0.35)
    elif futures_sign:
        score += futures_sign * (1.25 if oi_sign > 0 else 0.65)

    long_trap = (
        price_sign >= 0 and futures_sign >= 0 and basis_sign > 0 and oi_sign > 0
        and cash_sign < 0 and vix_sign > 0
    )
    short_squeeze = (
        price_sign <= 0 and futures_sign <= 0 and basis_sign < 0 and oi_sign > 0
        and cash_sign > 0 and vix_sign < 0
    )
    if long_trap:
        direction = "DOWN"
        state = "LONG_TRAP_RISK"
        score = -max(4.0, abs(score))
    elif short_squeeze:
        direction = "UP"
        state = "SHORT_SQUEEZE_RISK"
        score = max(4.0, abs(score))
    else:
        if score == 0:
            score = float(price_sign or futures_sign or basis_sign or (1 if cash_sign >= 0 else -1)) * 0.1
        direction = "UP" if score > 0 else "DOWN"
        if direction == "UP" and price_sign > 0 and oi_sign > 0 and cash_sign > 0 and vix_sign < 0:
            state = "AGGRESSIVE_LONG"
        elif direction == "UP" and price_sign > 0 and oi_sign > 0 and basis_sign > 0 and cash_sign <= 0 and vix_sign <= 0:
            state = "FUTURES_LED_LONG"
        elif direction == "UP" and price_sign > 0 and oi_sign < 0:
            state = "SHORT_COVERING_RALLY"
        elif direction == "DOWN" and price_sign < 0 and oi_sign > 0 and cash_sign < 0 and vix_sign > 0:
            state = "AGGRESSIVE_SHORT"
        elif direction == "DOWN" and price_sign < 0 and oi_sign > 0 and basis_sign < 0 and cash_sign >= 0 and vix_sign >= 0:
            state = "FUTURES_LED_SHORT"
        elif direction == "DOWN" and price_sign < 0 and oi_sign < 0:
            state = "LONG_UNWINDING_DECLINE"
        else:
            state = "UP_PRESSURE" if direction == "UP" else "DOWN_PRESSURE"

    vpoc_modifier, vpoc_read = _vpoc_modifier(bundle, direction, index)
    adjusted_strength = abs(score) + vpoc_modifier
    confidence = "HIGH" if adjusted_strength >= 7.0 else "MEDIUM" if adjusted_strength >= 4.0 else "LOW"
    if cash_row is None and confidence == "HIGH":
        confidence = "MEDIUM"

    drivers = [
        f"Index 5m {index_move:+.2f}" if index_move is not None else "Index 5m unavailable",
        f"Futures 5m {futures_move:+.2f}" if futures_move is not None else "Futures 5m unavailable",
        f"Basis 5m {basis_move:+.2f}" if basis_move is not None else "Basis 5m unavailable",
        f"Futures OI 5m {oi_move:+.0f}" if oi_move is not None else "Futures OI 5m unavailable",
        f"Cash slope {cash_change:+.4f}" if cash_change is not None else "Cash slope unavailable",
        f"VIX slope {vix_change:+.4f}" if vix_change is not None else "VIX slope unavailable",
    ]
    invalidation = (
        "Cash rolls down with VIX rising and price loses its five-minute impulse."
        if direction == "UP" else
        "Cash rolls up with VIX falling and price reclaims its five-minute impulse."
    )
    return {
        "schema": "NIFTY_AGGRESSIVE_DIRECTION_V1",
        "classification": "EXPERIMENTAL_FORCED_DIRECTION_NOT_VALIDATED",
        "causal_as_of": latest["t"],
        "horizon_minutes": HORIZON_MINUTES,
        "direction": direction,
        "state": state,
        "confidence": confidence,
        "core_score": round(score, 4),
        "vpoc_modifier": round(vpoc_modifier, 4),
        "vpoc_role": "CONFIDENCE_MODIFIER_ONLY",
        "headline": f"{direction} · {state.replace('_', ' ')}",
        "drivers": drivers,
        "vpoc_read": vpoc_read,
        "invalidation": invalidation,
        "metrics": {
            "index": index,
            "index_change_5m": index_move,
            "futures_change_5m": futures_move,
            "basis_change_5m": basis_move,
            "futures_oi_change_5m": oi_move,
            "cash_rolling_change": cash_change,
            "vix_rolling_change": vix_change,
        },
        "aggressive": True,
    }


def prediction_series(
    market_rows: Iterable[Mapping[str, object]],
    oi_rows: Iterable[Mapping[str, object]],
    cash_vix_rows: Iterable[Mapping[str, object]],
    intraday_rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Create one server-side causal decision per completed minute."""
    market = _rows([dict(row) for row in market_rows])
    oi = _rows([dict(row) for row in oi_rows])
    cash = _rows([dict(row) for row in cash_vix_rows])
    inventory = _rows([dict(row) for row in intraday_rows])
    by_minute: dict[object, dict[str, object]] = {}
    for row in market:
        minute = row["_instant"].replace(second=0, microsecond=0)
        local = minute.astimezone(IST)
        if local.hour < 9 or (local.hour == 9 and local.minute < 45):
            continue
        by_minute[minute] = row
    oi_times = [row["_instant"] for row in oi]
    cash_times = [row["_instant"] for row in cash]
    inventory_times = [row["_instant"] for row in inventory]
    history: dict[str, list[dict[str, object]]] = {}
    latest_controls: dict[str, dict[str, object]] = {}
    inventory_cursor = 0
    result: list[dict[str, object]] = []
    ordered_market = list(market)
    market_times = [row["_instant"] for row in ordered_market]
    for checkpoint in (by_minute[key] for key in sorted(by_minute)):
        instant = checkpoint["_instant"]
        market_end = bisect_right(market_times, instant)
        oi_end = bisect_right(oi_times, instant)
        cash_end = bisect_right(cash_times, instant)
        while inventory_cursor < len(inventory) and inventory_times[inventory_cursor] <= instant:
            row = inventory[inventory_cursor]
            family = str(row.get("family", ""))
            if family:
                compact = {
                    "receipt": row["t"],
                    "control_value": row.get("control_value"),
                }
                latest_controls[family] = compact
                history.setdefault(family, []).append(compact)
            inventory_cursor += 1
        bundle = {
            "recent_market": ordered_market[:market_end][-1200:],
            "recent_futures_oi": oi[:oi_end][-30:],
            "recent_cash_vix": cash[:cash_end][-12:],
            "visible_intraday_inventory": latest_controls,
            "recent_intraday_inventory_shifts": {
                family: rows[-3:] for family, rows in history.items()
            },
        }
        prediction = predict_direction(bundle)
        result.append({
            "t": prediction["causal_as_of"],
            "direction": prediction["direction"],
            "state": prediction["state"],
            "confidence": prediction["confidence"],
            "score": prediction["core_score"],
            "vpoc_modifier": prediction["vpoc_modifier"],
            "headline": prediction["headline"],
            "drivers": prediction["drivers"],
            "invalidation": prediction["invalidation"],
            "metrics": prediction["metrics"],
        })
    return result
