from datetime import UTC, datetime, timedelta

from banknifty_profiler.new_divergence.scenario import inventory_scenario


START = datetime(2026, 8, 31, 4, 25, tzinfo=UTC)


def market(values):
    return [
        {"t": (START + timedelta(seconds=offset)).isoformat(), "i": index,
         "f": futures, "b": basis}
        for offset, index, futures, basis in values
    ]


def oi(values):
    return [
        {"t": (START + timedelta(seconds=offset)).isoformat(), "p": price, "oi": value}
        for offset, price, value in values
    ]


def bundle(market_rows, oi_rows, ce=120, pe=100):
    return {
        "causal_as_of": market_rows[-1]["t"],
        "recent_market": market_rows,
        "recent_futures_oi": oi_rows,
        "visible_intraday_inventory": {
            "CE_POS_OI_VPOC": {"control_value": ce},
            "PE_POS_OI_VPOC": {"control_value": pe},
        },
        "recent_intraday_inventory_shifts": {},
    }


def test_true_long_buildup_requires_basis_and_control_confirmation():
    result = inventory_scenario(bundle(
        market([(0, 100, 110, 10), (240, 130, 143, 13), (300, 135, 150, 15)]),
        oi([(0, 110, 1000), (300, 150, 1250)]),
    ))
    assert result["scenario"] == "TRUE_LONG_BUILDUP"
    assert result["direction"] == "UP"
    assert result["stage"] == "CONFIRMED"


def test_true_short_buildup_requires_support_acceptance():
    result = inventory_scenario(bundle(
        market([(0, 150, 165, 15), (240, 105, 115, 10), (300, 100, 108, 8)]),
        oi([(0, 165, 1000), (300, 108, 1300)]),
        ce=140, pe=120,
    ))
    assert result["scenario"] == "TRUE_SHORT_BUILDUP"
    assert result["direction"] == "DOWN"


def test_long_trap_requires_observed_buildup_then_liquidation_and_failure():
    result = inventory_scenario(bundle(
        market([(0, 100, 110, 10), (120, 130, 145, 15), (240, 110, 115, 5), (300, 105, 105, 0)]),
        oi([(0, 110, 1000), (120, 145, 1300), (300, 105, 1100)]),
        ce=120, pe=100,
    ))
    assert result["scenario"] == "LONG_TRAP"
    assert result["direction"] == "DOWN"
    assert "FUTURES_LONG_LIQUIDATION" in result["rules"]


def test_old_same_freeze_short_trap_path_is_removed_without_volume_evidence():
    result = inventory_scenario(bundle(
        market([(0, 130, 145, 15), (120, 95, 105, 10), (240, 110, 125, 15), (300, 120, 145, 25)]),
        oi([(0, 145, 1000), (120, 105, 1300), (300, 145, 1100)]),
        ce=130, pe=100,
    ))
    assert result["scenario"] != "CONFIRMED_SHORT_TRAP"
    assert not (result["direction"] == "UP" and result["stage"] == "CONFIRMED")


def test_missing_history_abstains_and_option_premium_is_never_invented():
    result = inventory_scenario({"recent_market": [], "recent_futures_oi": []})
    assert result["scenario"] == "NO_EDGE"
    assert result["stage"] == "UNAVAILABLE"
