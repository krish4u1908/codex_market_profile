"""Causal minute-volume aggregation and the V1.0.35 climax gate."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import math
from typing import Iterable, Mapping

from .clock import iso_utc, parse_instant


VOLUME_CLIMAX_MULTIPLIER = 2.5
VOLUME_BASELINE_MINUTES = 5
_INVALID_STATUSES = {
    "BASELINE", "MISSING", "GAP_RESET", "RESET", "NO_SYNCHRONIZED_INDEX",
}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _minute(value: object):
    instant = parse_instant(value, field="Futures volume receipt timestamp")
    return instant.replace(second=0, microsecond=0)


def compact_futures_volume_minutes(
    rows: Iterable[Mapping[str, object]],
    *,
    multiplier: float = VOLUME_CLIMAX_MULTIPLIER,
    baseline_minutes: int = VOLUME_BASELINE_MINUTES,
    include_partial: bool = True,
) -> list[dict[str, object]]:
    """Aggregate visible cumulative-counter deltas without future leakage.

    The final visible minute is explicitly partial.  A partial minute may become
    a climax once its already-received positive deltas cross the fixed threshold;
    later volume is never needed to make that decision.  Baselines, however,
    always consist of five exact, contiguous, prior *complete* minutes.
    """

    if not math.isfinite(float(multiplier)) or float(multiplier) <= 0:
        raise ValueError("volume climax multiplier must be finite and positive")
    if baseline_minutes <= 0:
        raise ValueError("baseline_minutes must be positive")

    ordered: list[dict[str, object]] = []
    for source in rows:
        if not isinstance(source, Mapping) or source.get("t") is None:
            continue
        receipt = parse_instant(source.get("t"), field="Futures volume receipt timestamp")
        status = str(source.get("vs", "MISSING")).upper()
        delta = _finite(source.get("dv"))
        ordered.append({"receipt": receipt, "status": status, "delta": delta})
    ordered.sort(key=lambda row: row["receipt"])
    if not ordered:
        return []

    groups: dict[object, list[dict[str, object]]] = defaultdict(list)
    for row in ordered:
        groups[row["receipt"].replace(second=0, microsecond=0)].append(row)
    minutes = sorted(groups)
    result: list[dict[str, object]] = []
    for position, minute in enumerate(minutes):
        receipts = groups[minute]
        statuses = {str(row["status"]) for row in receipts}
        invalid = sorted(statuses & _INVALID_STATUSES)
        is_partial = position == len(minutes) - 1
        status = (
            "INVALID_" + "_".join(invalid)
            if invalid else "PARTIAL" if is_partial else "COMPLETE"
        )
        increments = [
            (row["receipt"], float(row["delta"]))
            for row in receipts
            if row["status"] == "VALID"
            and row["delta"] is not None
            and float(row["delta"]) > 0
        ]
        volume = sum(delta for _, delta in increments)
        next_receipt = (
            groups[minutes[position + 1]][0]["receipt"]
            if position + 1 < len(minutes) else None
        )
        result.append({
            "minute_utc": iso_utc(minute),
            "first_receipt_utc": iso_utc(receipts[0]["receipt"]),
            "last_receipt_utc": iso_utc(receipts[-1]["receipt"]),
            "complete_available_receipt_utc": (
                iso_utc(next_receipt) if next_receipt is not None else None
            ),
            "volume": volume,
            "status": status,
            "baseline_mean": None,
            "threshold": None,
            "ratio": None,
            "climax_cross_receipt_utc": None,
            "eligible": False,
            "ineligible_reason": "INSUFFICIENT_PRIOR_COMPLETE_MINUTES",
            "_increments": increments,
        })

    for position, current in enumerate(result):
        if position < baseline_minutes:
            continue
        prior = result[position - baseline_minutes:position]
        current_minute = parse_instant(current["minute_utc"])
        expected = [
            current_minute - timedelta(minutes=offset)
            for offset in range(baseline_minutes, 0, -1)
        ]
        actual = [parse_instant(row["minute_utc"]) for row in prior]
        if actual != expected:
            current["ineligible_reason"] = "MISSING_OR_GAPPED_BASELINE_MINUTE"
            continue
        if any(row["status"] != "COMPLETE" for row in prior):
            current["ineligible_reason"] = "INCOMPLETE_OR_INVALID_BASELINE_MINUTE"
            continue
        baseline = [float(row["volume"]) for row in prior]
        if any(value <= 0 for value in baseline):
            current["ineligible_reason"] = "NON_POSITIVE_BASELINE_MINUTE"
            continue
        if str(current["status"]).startswith("INVALID_"):
            current["ineligible_reason"] = "INVALID_CURRENT_MINUTE"
            continue
        mean = sum(baseline) / baseline_minutes
        threshold = float(multiplier) * mean
        current["baseline_mean"] = mean
        current["threshold"] = threshold
        current["ratio"] = float(current["volume"]) / mean
        current["eligible"] = True
        current["ineligible_reason"] = None
        cumulative = 0.0
        for receipt, delta in current["_increments"]:
            cumulative += delta
            if cumulative >= threshold:
                current["climax_cross_receipt_utc"] = iso_utc(receipt)
                break

    visible = result if include_partial else [row for row in result if row["status"] != "PARTIAL"]
    for row in visible:
        row.pop("_increments", None)
    return visible


def is_volume_climax(row: Mapping[str, object]) -> bool:
    """Return the inclusive, unrounded 2.5x decision."""

    ratio = _finite(row.get("ratio"))
    return (
        row.get("eligible") is True
        and ratio is not None
        and ratio >= VOLUME_CLIMAX_MULTIPLIER
        and row.get("climax_cross_receipt_utc") is not None
    )
