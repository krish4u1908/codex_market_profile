"""Frozen partial-context classification without fabricated controls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

LAYER_STATES = frozenset({
    "AVAILABLE", "MISSING_PRIOR_SESSION", "INELIGIBLE_PRIOR_SESSION",
    "EXPIRY_MISMATCH", "INCOMPLETE_RAW_DATA", "STALE_DATA",
    "NOT_YET_AVAILABLE",
})
HORIZONS = ("1D", "2D", "3D", "ID")


@dataclass(frozen=True)
class LayerAvailability:
    horizon: str
    state: str
    reason: str

    def __post_init__(self) -> None:
        if self.horizon not in HORIZONS:
            raise ValueError(f"unsupported inventory horizon: {self.horizon}")
        if self.state not in LAYER_STATES:
            raise ValueError(f"unsupported layer availability state: {self.state}")


def classify_context(
    layers: Mapping[str, LayerAvailability],
    *,
    divergence_inputs_available: bool,
    participation_inputs_available: bool,
) -> dict[str, object]:
    """Classify independent horizon availability and component suspension.

    Missing inventory context never suspends divergence or participation;
    those components are governed only by their own required inputs.
    """
    if set(layers) != set(HORIZONS):
        raise ValueError("availability must contain exactly 1D, 2D, 3D and ID")
    for horizon, layer in layers.items():
        if layer.horizon != horizon:
            raise ValueError("layer key and horizon disagree")

    fixed = [layers[x].state for x in HORIZONS[:-1]]
    intraday = layers["ID"].state
    fixed_available = sum(x == "AVAILABLE" for x in fixed)
    intraday_available = intraday == "AVAILABLE"
    any_available = fixed_available > 0 or intraday_available
    any_stale = intraday == "STALE_DATA" or "STALE_DATA" in fixed

    if fixed_available == 3 and intraday_available:
        overall = "LIVE_FULL_CONTEXT"
    elif any_available and any_stale:
        overall = "STALE_PARTIAL"
    elif intraday_available and fixed_available:
        overall = "LIVE_PARTIAL_CONTEXT"
    elif intraday_available:
        overall = "LIVE_INTRADAY_ONLY"
    elif fixed_available:
        overall = "FIXED_CONTEXT_ONLY"
    else:
        overall = "NO_VALID_MARKET_DATA"

    return {
        "overall_state": overall,
        "market_display_enabled": overall != "NO_VALID_MARKET_DATA",
        "divergence_state": "AVAILABLE" if divergence_inputs_available else "SUSPENDED_REQUIRED_INPUT_UNAVAILABLE",
        "participation_state": "AVAILABLE" if participation_inputs_available else "SUSPENDED_REQUIRED_INPUT_UNAVAILABLE",
        "available_horizons": "|".join(h for h in HORIZONS if layers[h].state == "AVAILABLE"),
        "unavailable_horizons": "|".join(h for h in HORIZONS if layers[h].state != "AVAILABLE"),
    }
