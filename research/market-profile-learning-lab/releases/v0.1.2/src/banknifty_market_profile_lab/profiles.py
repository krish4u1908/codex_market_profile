"""Causal BankNifty-reference inventory profile reconstruction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable, Mapping, Sequence

from .io_utils import finite, iso_utc


FAMILIES = (
    "BN_REF_FUT_VOLUME_VPOC",
    "CE_NEG_OI_VPOC",
    "CE_POS_OI_VPOC",
    "FUT_NEG_OI_VPOC",
    "FUT_POS_OI_VPOC",
    "PE_NEG_OI_VPOC",
    "PE_POS_OI_VPOC",
)
VOLUME_FAMILY = "BN_REF_FUT_VOLUME_VPOC"


@dataclass(frozen=True)
class Contribution:
    timestamp: datetime
    family: str
    index_price: float
    weight: float
    source_id: str
    session: str

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError(f"unknown profile family: {self.family}")
        if not math.isfinite(self.index_price) or self.index_price <= 0:
            raise ValueError("contribution index price must be positive and finite")
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("contribution weight must be positive and finite")


def price_bin(value: float, bin_points: int) -> float:
    if bin_points <= 0:
        raise ValueError("bin_points must be positive")
    return float(round(float(value) / bin_points) * bin_points)


def choose_control(
    bins: Mapping[float, float], weighted_price_sum: float, total_weight: float
) -> tuple[float, str]:
    if not bins or total_weight <= 0:
        raise ValueError("a positive profile is required")
    maximum = max(bins.values())
    candidates = sorted(
        price for price, weight in bins.items()
        if math.isclose(float(weight), float(maximum), rel_tol=0, abs_tol=1e-12)
    )
    reason = "NO_TIE"
    if len(candidates) > 1:
        reason = "TIE_WEIGHTED_MEAN"
        mean = weighted_price_sum / total_weight
        distance = min(abs(price - mean) for price in candidates)
        candidates = [
            price for price in candidates
            if math.isclose(abs(price - mean), distance, rel_tol=0, abs_tol=1e-12)
        ]
    if len(candidates) > 1:
        reason = "TIE_LOWER_BIN"
    return min(candidates), reason


def value_area(
    bins: Mapping[float, float],
    vpoc: float,
    *,
    bin_points: int,
    target_fraction: float,
) -> tuple[float, float, float]:
    normalized = {
        float(price): float(weight)
        for price, weight in bins.items()
        if finite(price) is not None and finite(weight) is not None and float(weight) >= 0
    }
    total = sum(normalized.values())
    if vpoc not in normalized or total <= 0:
        raise ValueError("value area requires a positive observed VPOC")
    if not 0 < target_fraction <= 1:
        raise ValueError("target_fraction must be in (0, 1]")
    low = high = float(vpoc)
    included = normalized[float(vpoc)]
    lower_bound, upper_bound = min(normalized), max(normalized)
    target = total * target_fraction
    while included < target and (low > lower_bound or high < upper_bound):
        lower = low - bin_points if low > lower_bound else None
        upper = high + bin_points if high < upper_bound else None
        lower_weight = -1.0 if lower is None else normalized.get(lower, 0.0)
        upper_weight = -1.0 if upper is None else normalized.get(upper, 0.0)
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


def summarize_profile(
    contributions: Iterable[Contribution],
    *,
    family: str,
    scope: str,
    bin_points: int,
    value_area_fraction: float,
) -> dict[str, object] | None:
    selected = [row for row in contributions if row.family == family]
    if not selected:
        return None
    bins: defaultdict[float, float] = defaultdict(float)
    total_weight = 0.0
    weighted_price_sum = 0.0
    for row in selected:
        current_bin = price_bin(row.index_price, bin_points)
        bins[current_bin] += row.weight
        total_weight += row.weight
        weighted_price_sum += row.index_price * row.weight
    control, tie = choose_control(bins, weighted_price_sum, total_weight)
    low = high = achieved = None
    if family == VOLUME_FAMILY:
        low, high, achieved = value_area(
            bins,
            control,
            bin_points=bin_points,
            target_fraction=value_area_fraction,
        )
    return {
        "scope": scope,
        "family": family,
        "status": "AVAILABLE",
        "control_value": control,
        "value_area_low": low,
        "value_area_high": high,
        "value_area_target_fraction": value_area_fraction if family == VOLUME_FAMILY else None,
        "value_area_achieved_fraction": achieved,
        "total_weight": total_weight,
        "evidence_count": len(selected),
        "source_sessions": sorted({row.session for row in selected}),
        "first_evidence_timestamp": iso_utc(min(row.timestamp for row in selected)),
        "latest_evidence_timestamp": iso_utc(max(row.timestamp for row in selected)),
        "tie_break_reason": tie,
    }


def developing_rows(
    contributions: Sequence[Contribution],
    *,
    session: str,
    bin_points: int,
    value_area_fraction: float,
) -> list[dict[str, object]]:
    bins_by_family: dict[str, defaultdict[float, float]] = {}
    total_by_family: defaultdict[str, float] = defaultdict(float)
    weighted_by_family: defaultdict[str, float] = defaultdict(float)
    count_by_family: defaultdict[str, int] = defaultdict(int)
    last_display: dict[str, tuple[float, float | None, float | None]] = {}
    result: list[dict[str, object]] = []
    ordered = sorted(
        contributions,
        key=lambda row: (row.timestamp, row.family, row.source_id),
    )
    position = 0
    while position < len(ordered):
        timestamp = ordered[position].timestamp
        end = position
        changed: set[str] = set()
        triggers: defaultdict[str, list[str]] = defaultdict(list)
        while end < len(ordered) and ordered[end].timestamp == timestamp:
            row = ordered[end]
            current_bin = price_bin(row.index_price, bin_points)
            bins = bins_by_family.setdefault(row.family, defaultdict(float))
            bins[current_bin] += row.weight
            total_by_family[row.family] += row.weight
            weighted_by_family[row.family] += row.index_price * row.weight
            count_by_family[row.family] += 1
            changed.add(row.family)
            triggers[row.family].append(row.source_id)
            end += 1
        for family in sorted(changed):
            bins = bins_by_family[family]
            control, tie = choose_control(
                bins, weighted_by_family[family], total_by_family[family]
            )
            low = high = achieved = None
            if family == VOLUME_FAMILY:
                low, high, achieved = value_area(
                    bins,
                    control,
                    bin_points=bin_points,
                    target_fraction=value_area_fraction,
                )
            display = (control, low, high)
            if last_display.get(family) == display:
                continue
            last_display[family] = display
            result.append({
                "t": iso_utc(timestamp),
                "scope": "ID",
                "family": family,
                "status": "AVAILABLE",
                "control_value": control,
                "value_area_low": low,
                "value_area_high": high,
                "value_area_target_fraction": (
                    value_area_fraction if family == VOLUME_FAMILY else None
                ),
                "value_area_achieved_fraction": achieved,
                "total_weight": total_by_family[family],
                "evidence_count": count_by_family[family],
                "source_sessions": [session],
                "tie_break_reason": tie,
                "trigger_source_ids": sorted(triggers[family]),
            })
        position = end
    return result
