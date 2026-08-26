from __future__ import annotations

import json
from copy import deepcopy

import pytest

from banknifty_profiler.context.availability import LayerAvailability, classify_context
from banknifty_profiler.cross_layer.state import build_material_transitions


def layers(one="AVAILABLE", two="AVAILABLE", three="AVAILABLE", intraday="AVAILABLE"):
    return {h: LayerAvailability(h, value, "MANUAL_TEST_FIXTURE") for h, value in zip(("1D", "2D", "3D", "ID"), (one, two, three, intraday))}


@pytest.mark.parametrize("fixture,expected", [
    (layers(), "LIVE_FULL_CONTEXT"),
    (layers(three="MISSING_PRIOR_SESSION"), "LIVE_PARTIAL_CONTEXT"),
    (layers(two="MISSING_PRIOR_SESSION", three="MISSING_PRIOR_SESSION"), "LIVE_PARTIAL_CONTEXT"),
    (layers(one="MISSING_PRIOR_SESSION", two="MISSING_PRIOR_SESSION", three="MISSING_PRIOR_SESSION"), "LIVE_INTRADAY_ONLY"),
    (layers(intraday="INCOMPLETE_RAW_DATA"), "FIXED_CONTEXT_ONLY"),
    (layers(three="STALE_DATA"), "STALE_PARTIAL"),
    (layers(one="INCOMPLETE_RAW_DATA", two="INCOMPLETE_RAW_DATA", three="INCOMPLETE_RAW_DATA", intraday="INCOMPLETE_RAW_DATA"), "NO_VALID_MARKET_DATA"),
])
def test_partial_context_degrades_independently(fixture, expected):
    result = classify_context(fixture, divergence_inputs_available=True, participation_inputs_available=True)
    assert result["overall_state"] == expected
    assert result["divergence_state"] == "AVAILABLE"
    assert result["participation_state"] == "AVAILABLE"


def test_components_suspend_only_for_own_missing_inputs():
    result = classify_context(layers(three="MISSING_PRIOR_SESSION"), divergence_inputs_available=False, participation_inputs_available=True)
    assert result["overall_state"] == "LIVE_PARTIAL_CONTEXT"
    assert result["divergence_state"].startswith("SUSPENDED")
    assert result["participation_state"] == "AVAILABLE"


def test_availability_requires_exact_horizons():
    with pytest.raises(ValueError, match="exactly"):
        classify_context({"ID": LayerAvailability("ID", "AVAILABLE", "x")}, divergence_inputs_available=True, participation_inputs_available=True)


def fixture_rows():
    inventory = [{"evaluation_date":"2026-08-20","horizon":"ID","family":"FUT_POS_OI_VPOC","control_value":"57325","control_effective_timestamp":"2026-08-20T09:45:00+05:30","winner_change_timestamp":"2026-08-20T09:45:00+05:30"}]
    episodes = [{"evaluation_date":"2026-08-20","episode_id":"E1","colour":"GREEN","confirmation_timestamp":"2026-08-20T09:46:00+05:30","index_receipt_timestamp":"2026-08-20T09:45:59+05:30","futures_receipt_timestamp":"2026-08-20T09:45:59.500000+05:30"}]
    lifecycle = [{"evaluation_date":"2026-08-20","episode_id":"E1","state_entry_timestamp":"2026-08-20T09:46:01+05:30","previous_state":"CONFIRMED","state":"ACTIVE","reason_code":"TEST","record_id":"L1"}]
    resolution = [
        {"evaluation_date":"2026-08-20","episode_id":"E1","availability_timestamp":"2026-08-20T09:46:02+05:30","resolution_mechanism_native":"UNRESOLVED","record_id":"R1"},
        {"evaluation_date":"2026-08-20","episode_id":"E1","availability_timestamp":"2026-08-20T09:46:03+05:30","resolution_mechanism_native":"UNRESOLVED","record_id":"R2"},
        {"evaluation_date":"2026-08-20","episode_id":"E1","availability_timestamp":"2026-08-20T09:46:04+05:30","resolution_mechanism_native":"INDEX_CATCH_UP","record_id":"R3"},
    ]
    participation = [{"transition_id":"P1","episode_id":"E1","component":"FUTURES","previous_state":"UNKNOWN","new_state":"LONG_BUILDUP","effective_timestamp":"2026-08-20T09:46:05+05:30","evidence_receipt_timestamp":"2026-08-20T09:46:05+05:30","constituent_effective_timestamps":json.dumps({"receipt":"2026-08-20T09:46:05+05:30"}),"reason_code":"TEST"}]
    return inventory, episodes, lifecycle, resolution, participation


def test_material_transitions_are_deduplicated_and_ordered():
    rows = build_material_transitions(*fixture_rows())
    assert [r["component"] for r in rows] == ["INVENTORY", "DIVERGENCE", "LIFECYCLE", "RESOLUTION", "RESOLUTION", "FUTURES_PARTICIPATION"]
    assert sum(r["component"] == "RESOLUTION" for r in rows) == 2
    assert len({r["transition_id"] for r in rows}) == len(rows)


def test_equal_timestamp_order_is_deterministic():
    args = list(fixture_rows())
    args[2][0]["state_entry_timestamp"] = "2026-08-20T09:46:00+05:30"
    rows = build_material_transitions(*args)
    same = [r["component"] for r in rows if r["effective_timestamp"] == "2026-08-20T09:46:00+05:30"]
    assert same == ["DIVERGENCE", "LIFECYCLE"]


def test_constituent_clock_cannot_be_backdated():
    args = list(fixture_rows())
    args[4][0]["constituent_effective_timestamps"] = json.dumps({"receipt":"2026-08-20T09:46:06+05:30"})
    with pytest.raises(ValueError, match="backdating"):
        build_material_transitions(*args)


def test_continuation_context_matches_one_global_chronological_build():
    first = fixture_rows()
    second = deepcopy(first)
    for component in second:
        for row in component:
            for key, value in list(row.items()):
                if isinstance(value, str):
                    row[key] = value.replace("2026-08-20", "2026-08-21")
            if "episode_id" in row:
                row["episode_id"] = "E2"
            if "record_id" in row:
                row["record_id"] += "-2"
            if "transition_id" in row:
                row["transition_id"] += "-2"
    combined = [left + right for left, right in zip(first, second)]
    global_rows, global_context = build_material_transitions(
        *combined, return_context=True
    )
    first_rows, first_context = build_material_transitions(
        *first, return_context=True
    )
    second_rows, second_context = build_material_transitions(
        *second, initial_context=first_context, return_context=True
    )

    assert first_rows + second_rows == global_rows
    assert second_context == global_context
    assert not any(row["component"] == "INVENTORY" for row in second_rows)
    assert next(
        row for row in second_rows if row["component"] == "DIVERGENCE"
    )["source_record_id"] == "episode:2"
    assert next(
        row for row in second_rows if row["component"] == "RESOLUTION"
    )["source_record_id"] == "resolution:4"


def test_continuation_context_rejects_corrupt_counts():
    with pytest.raises(ValueError, match="non-negative integer"):
        build_material_transitions(
            *fixture_rows(), initial_context={"inventory_source_count": -1}
        )
