"""Causal short-trap candidate and confirmation classifier for V1.0.35."""

from __future__ import annotations

from datetime import timedelta
import math
from typing import Mapping

from .clock import iso_ist, iso_utc, parse_instant
from .volume_climax import is_volume_climax


OI_PERCENT_THRESHOLD = 1.5
RECLAIM_POINTS = 15.0
CONTROL_MARGIN = 5.0
EPISODE_EXPIRY_MINUTES = 5
COOL_RATIO = 1.5


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rows(bundle: Mapping[str, object], key: str, fields: tuple[str, ...]):
    source = bundle.get(key, [])
    result = []
    if not isinstance(source, list):
        return result
    for raw in source:
        if not isinstance(raw, Mapping):
            continue
        stamp = raw.get("t") or raw.get("timestamp") or raw.get("receipt_timestamp")
        if stamp is None:
            continue
        try:
            row = {"t": parse_instant(str(stamp))}
        except ValueError:
            continue
        valid = True
        for field in fields:
            aliases = {
                "i": ("i", "index_price"),
                "f": ("f", "futures_price", "p", "price"),
                "b": ("b", "basis"),
                "oi": ("oi",),
            }[field]
            value = next((_finite(raw.get(name)) for name in aliases if raw.get(name) is not None), None)
            if value is None:
                valid = False
                break
            row[field] = value
        if valid:
            result.append(row)
    return sorted(result, key=lambda row: row["t"])


def _at_or_before(rows, target, *, max_age_seconds: float = 90.0):
    selected = None
    for row in rows:
        if row["t"] > target:
            break
        selected = row
    if selected is None or (target - selected["t"]).total_seconds() > max_age_seconds:
        return None
    return selected


def _control(bundle: Mapping[str, object], family: str) -> float | None:
    controls = bundle.get("visible_intraday_inventory", {})
    row = controls.get(family) if isinstance(controls, Mapping) else None
    return _finite(row.get("control_value")) if isinstance(row, Mapping) else None


def _result(
    scenario: str,
    direction: str,
    stage: str,
    evidence: list[str],
    metrics: Mapping[str, object],
    rules: list[str],
    *,
    missing: list[str] | None = None,
) -> dict[str, object]:
    confirmed = stage == "CONFIRMED"
    return {
        "schema": "NEW_DIVERGENCE_INVENTORY_SCENARIO_V2",
        "analysis_method": "CAUSAL_VOLUME_CLIMAX_SHORT_TRAP_V1035",
        "scenario": scenario,
        "direction": direction,
        "stage": stage,
        "confidence": "MEDIUM" if confirmed else "LOW",
        "horizon_minutes": 15,
        "evidence": evidence,
        "confirmation": (
            "Maintain the reclaim with continued Futures OI liquidation and no loss of PE control."
            if confirmed else
            "Wait for a later-minute price reclaim, Futures OI liquidation, basis recovery, and PE-control reclaim."
        ),
        "invalidation": "Accepting below the probe low, an invalid volume baseline, or no confirmation within five minutes.",
        "expected": (
            "Upside continuation is possible from the signal receipt; this is not an order instruction."
            if confirmed else
            "No BUY or SELL direction is assigned while the candidate remains unconfirmed."
        ),
        "metrics": dict(metrics),
        "rules": rules,
        "missing_evidence": list(missing or ["OPTION_PREMIUM_TRADE_DIRECTION"]),
        "experimental": True,
    }


def _episodes(volume_rows: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    episodes: list[list[dict[str, object]]] = []
    active: list[dict[str, object]] | None = None
    cool_count = 0
    last_minute = None
    for row in volume_rows:
        minute = parse_instant(str(row.get("minute_utc")))
        ratio = _finite(row.get("ratio"))
        if last_minute is not None and minute - last_minute > timedelta(minutes=1):
            active = None
            cool_count = 0
        previous_cool = cool_count
        cool_count = cool_count + 1 if row.get("eligible") is True and ratio is not None and ratio < COOL_RATIO else 0
        if is_volume_climax(row):
            expired = active and minute - parse_instant(str(active[0]["minute_utc"])) > timedelta(minutes=EPISODE_EXPIRY_MINUTES)
            if active is None or previous_cool >= 2 or expired:
                active = []
                episodes.append(active)
            active.append(row)
            cool_count = 0
        last_minute = minute
    return episodes


def short_trap_scenario(bundle: Mapping[str, object]) -> dict[str, object] | None:
    """Return only a causal candidate/confirmation; otherwise defer to base scenarios."""

    market = _rows(bundle, "recent_market", ("i", "f", "b"))
    oi = _rows(bundle, "recent_futures_oi", ("f", "oi"))
    volume_source = bundle.get("recent_futures_volume_minutes", [])
    volume = [dict(row) for row in volume_source if isinstance(row, Mapping)] if isinstance(volume_source, list) else []
    if len(market) < 2 or len(oi) < 2 or not volume:
        return None
    episodes = _episodes(volume)
    if not episodes:
        return None

    as_of = parse_instant(str(bundle.get("causal_as_of") or market[-1]["t"]))
    candidate = None
    for episode in reversed(episodes):
        for climax in episode:
            cross_value = climax.get("climax_cross_receipt_utc")
            if cross_value is None:
                continue
            cross = parse_instant(str(cross_value))
            current_market = _at_or_before(market, cross)
            prior_market = _at_or_before(market, cross - timedelta(minutes=5))
            current_oi = _at_or_before(oi, cross)
            prior_oi = _at_or_before(oi, cross - timedelta(minutes=5))
            if None in (current_market, prior_market, current_oi, prior_oi):
                continue
            assert current_market and prior_market and current_oi and prior_oi
            prior_oi_value = float(prior_oi["oi"])
            if prior_oi_value <= 0:
                continue
            price_change = float(current_market["f"]) - float(prior_market["f"])
            oi_pct = (float(current_oi["oi"]) - prior_oi_value) / prior_oi_value * 100.0
            if price_change < 0 and oi_pct >= OI_PERCENT_THRESHOLD:
                candidate = {
                    "climax": climax,
                    "cross": cross,
                    "market": current_market,
                    "oi": current_oi,
                    "price_change": price_change,
                    "oi_pct": oi_pct,
                    "episode_start": episode[0],
                }
                break
        if candidate is not None:
            break
    if candidate is None:
        return None

    cross = candidate["cross"]
    climax_minute = parse_instant(str(candidate["climax"]["minute_utc"]))
    episode_start = parse_instant(str(candidate["episode_start"]["minute_utc"]))
    expiry = cross + timedelta(minutes=EPISODE_EXPIRY_MINUTES)
    if as_of > expiry + timedelta(minutes=1):
        return None
    pe_control = _control(bundle, "PE_POS_OI_VPOC")
    probe_rows = [row for row in market if cross - timedelta(minutes=5) <= row["t"] <= cross]
    probe_low = min(float(row["f"]) for row in probe_rows)
    index_probe_low = min(float(row["i"]) for row in probe_rows)
    signal = None
    for row in market:
        if row["t"] <= cross or row["t"].replace(second=0, microsecond=0) <= climax_minute:
            continue
        if row["t"] > expiry:
            break
        current_oi = _at_or_before(oi, row["t"])
        if current_oi is None:
            continue
        price_reclaimed = float(row["f"]) >= probe_low + RECLAIM_POINTS
        oi_liquidating = float(current_oi["oi"]) < float(candidate["oi"]["oi"])
        basis_recovered = float(row["b"]) > float(candidate["market"]["b"])
        control_reclaimed = (
            pe_control is not None
            and index_probe_low <= pe_control
            and float(row["i"]) >= pe_control + CONTROL_MARGIN
        )
        if price_reclaimed and oi_liquidating and basis_recovered and control_reclaimed:
            signal = {"market": row, "oi": current_oi}
            break

    climax = candidate["climax"]
    metrics = {
        "volume_climax_minute_utc": iso_utc(climax_minute),
        "volume_climax_minute_ist": iso_ist(climax_minute),
        "first_climax_receipt_utc": iso_utc(cross),
        "first_climax_receipt_ist": iso_ist(cross),
        "candidate_identified_receipt_utc": iso_utc(cross),
        "candidate_identified_receipt_ist": iso_ist(cross),
        "signal_available_receipt_utc": None,
        "signal_available_receipt_ist": None,
        "episode_start_minute_utc": iso_utc(episode_start),
        "episode_start_minute_ist": iso_ist(episode_start),
        "volume": climax.get("volume"),
        "volume_baseline_mean_5m": climax.get("baseline_mean"),
        "volume_climax_ratio": climax.get("ratio"),
        "volume_threshold_multiplier": 2.5,
        "futures_price_change_5m_at_candidate": candidate["price_change"],
        "futures_oi_pct_change_5m_at_candidate": candidate["oi_pct"],
        "probe_low_futures": probe_low,
        "pe_positive_control": pe_control,
        "climax_to_signal_gap_seconds": None,
    }
    evidence = [
        f"Minute Futures volume ratio was {float(climax['ratio']):.6g}x versus the exact prior-five-complete-minute mean.",
        f"At the crossing receipt Futures changed {candidate['price_change']:+.6g} over five minutes while OI changed {candidate['oi_pct']:+.6g}%.",
    ]
    if signal is not None:
        signal_time = signal["market"]["t"]
        metrics.update({
            "signal_available_receipt_utc": iso_utc(signal_time),
            "signal_available_receipt_ist": iso_ist(signal_time),
            "climax_to_signal_gap_seconds": (signal_time - cross).total_seconds(),
            "signal_futures_price": signal["market"]["f"],
            "signal_futures_oi": signal["oi"]["oi"],
            "signal_basis": signal["market"]["b"],
        })
        evidence.append(
            "A later market minute reclaimed price and PE control while Futures OI liquidated and basis recovered."
        )
        return _result(
            "CONFIRMED_SHORT_TRAP", "UP", "CONFIRMED", evidence, metrics,
            [
                "VOLUME_AT_LEAST_2_5X_PRIOR_FIVE_COMPLETE_MINUTES",
                "OBSERVED_SHORT_BUILDUP", "LATER_MINUTE_PRICE_RECLAIM",
                "FUTURES_SHORT_COVERING", "BASIS_RECOVERY", "RECLAIMED_PE_CONTROL",
                "SIGNAL_ANCHORED_TO_CONFIRMATION_RECEIPT",
            ],
        )

    expired = as_of > expiry
    missing = ["LATER_MINUTE_CONFIRMATION"]
    if pe_control is None:
        missing.append("PE_POSITIVE_OI_CONTROL")
    return _result(
        "SHORT_TRAP_CANDIDATE", "NO_EDGE", "EXPIRED" if expired else "OBSERVING",
        evidence, metrics,
        [
            "VOLUME_AT_LEAST_2_5X_PRIOR_FIVE_COMPLETE_MINUTES",
            "OBSERVED_SHORT_BUILDUP", "NO_DIRECTION_BEFORE_REVERSAL_CONFIRMATION",
            "EPISODE_DEDUPLICATED", "FIVE_MINUTE_EXPIRY",
        ],
        missing=missing,
    )
