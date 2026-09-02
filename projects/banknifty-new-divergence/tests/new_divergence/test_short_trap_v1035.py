from datetime import UTC, datetime, timedelta

from banknifty_profiler.new_divergence.scenario import inventory_scenario
from banknifty_profiler.new_divergence.volume_climax import (
    compact_futures_volume_minutes,
    is_volume_climax,
)


START = datetime(2026, 8, 31, 4, 15, 10, tzinfo=UTC)


def volume_rows(values, statuses=None):
    statuses = statuses or ["VALID"] * len(values)
    return [
        {
            "t": (START + timedelta(minutes=offset)).isoformat(),
            "dv": value,
            "vs": statuses[offset],
        }
        for offset, value in enumerate(values)
    ]


def facts(*, confirm=False, volume=250.0, same_minute_reclaim=False):
    raw_volume = volume_rows([100, 100, 100, 100, 100, volume])
    market = [
        {"t": START.isoformat(), "i": 100, "f": 100, "b": 10},
        {"t": (START + timedelta(minutes=5)).isoformat(), "i": 88, "f": 90, "b": 5},
    ]
    oi = [
        {"t": START.isoformat(), "p": 100, "oi": 1000},
        {"t": (START + timedelta(minutes=5)).isoformat(), "p": 90, "oi": 1020},
    ]
    as_of = START + timedelta(minutes=5)
    if same_minute_reclaim:
        market.append({
            "t": (START + timedelta(minutes=5, seconds=30)).isoformat(),
            "i": 100, "f": 108, "b": 8,
        })
        oi.append({
            "t": (START + timedelta(minutes=5, seconds=30)).isoformat(),
            "p": 108, "oi": 1010,
        })
        as_of = START + timedelta(minutes=5, seconds=30)
    if confirm:
        raw_volume.append({
            "t": (START + timedelta(minutes=6)).isoformat(), "dv": 20, "vs": "VALID",
        })
        market.append({
            "t": (START + timedelta(minutes=6)).isoformat(),
            "i": 100, "f": 108, "b": 8,
        })
        oi.append({
            "t": (START + timedelta(minutes=6)).isoformat(),
            "p": 108, "oi": 1010,
        })
        as_of = START + timedelta(minutes=6)
    return {
        "causal_as_of": as_of.isoformat(),
        "recent_market": market,
        "recent_futures_oi": oi,
        "recent_futures_volume_minutes": compact_futures_volume_minutes(raw_volume),
        "visible_intraday_inventory": {
            "PE_POS_OI_VPOC": {"control_value": 92},
            "CE_POS_OI_VPOC": {"control_value": 110},
        },
        "recent_intraday_inventory_shifts": {},
    }


def test_inclusive_unrounded_2_5x_gate_excludes_current_from_baseline():
    rows = compact_futures_volume_minutes(volume_rows([100, 100, 100, 100, 100, 250]))
    climax = rows[-1]
    assert climax["baseline_mean"] == 100
    assert climax["ratio"] == 2.5
    assert climax["volume"] == 250
    assert is_volume_climax(climax)


def test_2_499x_is_not_a_climax():
    rows = compact_futures_volume_minutes(volume_rows([100, 100, 100, 100, 100, 249.9]))
    assert rows[-1]["ratio"] == 2.499
    assert not is_volume_climax(rows[-1])


def test_gap_or_reset_in_baseline_is_ineligible():
    statuses = ["VALID", "VALID", "GAP_RESET", "VALID", "VALID", "VALID"]
    rows = compact_futures_volume_minutes(
        volume_rows([100, 100, None, 100, 100, 300], statuses)
    )
    assert rows[-1]["eligible"] is False
    assert rows[-1]["ineligible_reason"] == "INCOMPLETE_OR_INVALID_BASELINE_MINUTE"


def test_climax_creates_no_edge_candidate_not_buy_signal():
    result = inventory_scenario(facts())
    assert result["scenario"] == "SHORT_TRAP_CANDIDATE"
    assert result["direction"] == "NO_EDGE"
    assert result["stage"] == "OBSERVING"
    assert result["metrics"]["volume_climax_ratio"] == 2.5
    assert result["metrics"]["signal_available_receipt_utc"] is None


def test_same_minute_reclaim_cannot_confirm_short_trap():
    result = inventory_scenario(facts(same_minute_reclaim=True))
    assert result["scenario"] == "SHORT_TRAP_CANDIDATE"
    assert result["direction"] == "NO_EDGE"


def test_later_minute_reclaim_covering_basis_and_control_confirms():
    result = inventory_scenario(facts(confirm=True))
    assert result["scenario"] == "CONFIRMED_SHORT_TRAP"
    assert result["direction"] == "UP"
    assert result["stage"] == "CONFIRMED"
    metrics = result["metrics"]
    assert metrics["signal_available_receipt_utc"] > metrics["first_climax_receipt_utc"]
    assert metrics["climax_to_signal_gap_seconds"] == 60


def test_price_and_oi_sequence_without_2_5x_volume_cannot_confirm():
    result = inventory_scenario(facts(confirm=True, volume=249.9))
    assert result["scenario"] != "CONFIRMED_SHORT_TRAP"

