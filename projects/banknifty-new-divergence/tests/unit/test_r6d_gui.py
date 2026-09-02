from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from banknifty_profiler.gui.adapter import PRODUCT_CLASSIFICATION, SESSIONS, build_payload, source_contract, write_payload


ROOT = Path("/opt/banknifty/research/vpoc_oi_price_response_v2/clean_combined_profiler_r6c2r_full_stack")


@pytest.fixture(scope="module")
def payload():
    return build_payload(ROOT, "2026-08-18")


def unpack(value):
    return [dict(zip(value["fields"], row)) for row in value["rows"]]


def test_source_contract_is_sealed_and_hashed():
    contract = source_contract(ROOT)
    assert contract["version"] == "R6D_GUI_INPUT_SCHEMA_V1"
    assert len(contract["files"]) == 11
    assert all(len(item["sha256"]) == 64 for item in contract["files"].values())


def test_only_six_verified_sessions_are_accepted():
    assert len(SESSIONS) == 6
    with pytest.raises(ValueError, match="unverified session"):
        build_payload(ROOT, "2026-08-17")


def test_product_classification(payload):
    assert payload["classification"] == PRODUCT_CLASSIFICATION


def test_index_and_futures_are_separate_receipt_fields(payload):
    price = unpack(payload["price"])
    assert len(price) > 100
    assert all(row["it"] and row["ft"] for row in price)
    assert any(row["it"] != row["ft"] for row in price)


def test_basis_is_frozen_synchronized_value(payload):
    for row in unpack(payload["price"])[::251]:
        assert float(row["b"]) == pytest.approx(float(row["f"]) - float(row["i"]))
        assert float(row["a"]) >= 0
        assert float(row["a"]) <= 2000


def test_mixed_timestamps_are_chronological(payload):
    values = [row["t"] for row in unpack(payload["price"])]
    assert values == sorted(values)
    assert any("." in value.split("+")[0] for value in values)
    # Exact-second fixed-control clocks coexist with fractional raw receipts.
    controls = [row["control_effective_timestamp"] for row in unpack(payload["inventory"])]
    assert any("." not in value.split("+")[0] for value in controls)


def test_frozen_episode_counts_across_sessions():
    episodes=[]
    dependencies=[]
    for date in SESSIONS:
        p=build_payload(ROOT,date);episodes.extend(unpack(p["episodes"]));dependencies.extend(unpack(p["dependencies"]))
    assert len(episodes)==65
    assert sum(x["colour"]=="GREEN" for x in episodes)==41
    assert sum(x["colour"]=="RED" for x in episodes)==24
    assert sum(x["retrigger_flag"]=="True" for x in dependencies)==14


def test_inventory_values_are_unmodified(payload):
    assert len(unpack(payload["inventory"])) == payload["counts"]["inventory"]
    assert all(row["authority_basis"] == "RAW_CAUSAL_BANKNIFTY_REFERENCE" for row in unpack(payload["inventory"]))


def test_fixed_controls_are_effective_at_session_open(payload):
    fixed=[r for r in unpack(payload["inventory"]) if r["horizon"]!="ID"]
    assert fixed
    assert all(r["control_effective_timestamp"].endswith("T09:15:00+05:30") for r in fixed)


def test_intraday_controls_retain_causal_effective_timestamps(payload):
    intraday=[r for r in unpack(payload["inventory"]) if r["horizon"]=="ID"]
    assert intraday
    assert all(r["control_effective_timestamp"] >= payload["session"]["start"] for r in intraday)


def test_participation_dense_authority_is_preserved(payload):
    assert len(unpack(payload["participation_dense"])) == payload["counts"]["participation_dense"]


def test_four_participation_views_present(payload):
    assert unpack(payload["participation_dense"])
    assert unpack(payload["participation_transitions"])
    assert unpack(payload["participation_summaries"])
    assert unpack(payload["compatibility_snapshots"])


def test_participation_receipt_not_after_observation(payload):
    rows=unpack(payload["participation_dense"])
    assert all(row["receipt_timestamp"] <= row["observation_timestamp"] for row in rows)


def test_lifecycle_is_not_backdated(payload):
    assert all(row["causal_input_cutoff"] <= row["state_entry_timestamp"] for row in unpack(payload["lifecycle"]))


def test_no_success_failure_fields(payload):
    forbidden={"success","failure","pnl","order","entry","alert"}
    for key in ("episodes","lifecycle","resolution_mechanisms","participation_dense"):
        assert not forbidden.intersection({field.lower() for field in payload[key]["fields"]})


def test_gzip_payload_is_deterministic(tmp_path,payload):
    a=tmp_path/'a.gz';b=tmp_path/'b.gz';write_payload(payload,a);write_payload(payload,b)
    assert a.read_bytes()==b.read_bytes()
    assert json.loads(gzip.decompress(a.read_bytes()))["date"]=="2026-08-18"


def test_gui_source_uses_no_external_dependency():
    static=Path("src/banknifty_profiler/gui/static")
    text="\n".join(p.read_text() for p in static.iterdir())
    assert "https://" not in text and "http://" not in text


def test_gui_defaults_future_path_hidden():
    html=Path("src/banknifty_profiler/gui/static/replay.html").read_text()
    assert '<input id="reveal" type="checkbox">' in html


def test_master_and_child_controls_are_distinct():
    js=Path("src/banknifty_profiler/gui/static/app.js").read_text()
    assert "data-master" in js and "data-child" in js
    assert "state.toggles.masters" in js and "state.toggles.children" in js


def test_all_required_speeds_exist():
    html=Path("src/banknifty_profiler/gui/static/replay.html").read_text()
    for speed in (1,5,10,30):assert f'value="{speed}"' in html


def test_only_no_valid_market_data_disables_market():
    rows=[]
    for date in SESSIONS:rows.extend(build_payload(ROOT,date)["availability"])
    assert all(row["market_display_enabled"]=="True" for row in rows)


def test_missing_3d_2d_does_not_remove_intraday():
    p=build_payload(ROOT,"2026-08-11")
    states={r["horizon"]:r["availability_state"] for r in p["availability"]}
    assert states["3D"]==states["2D"]=="INSUFFICIENT_PRIOR_SESSIONS"
    assert states["1D"]==states["ID"]=="AVAILABLE"


def test_payload_contains_no_raw_collector_loader(payload):
    assert "source_file" not in payload["price"]["fields"]
    assert "raw_source_references" not in payload["participation_transitions"]["fields"]


def test_cross_layer_projection_is_inventory_only(payload):
    assert all(row["component"]=="INVENTORY" for row in unpack(payload["cross_layer_transitions"]))


def test_effective_and_snapshot_clocks_remain_separate(payload):
    assert {"control_effective_timestamp","snapshot_timestamp"}.issubset(payload["inventory"]["fields"])


def test_option_volume_disclaimer_present():
    js=Path("src/banknifty_profiler/gui/static/app.js").read_text()
    assert "cumulative traded-volume change between REST receipts" in js


def test_browser_has_no_analytical_thresholds():
    js=Path("src/banknifty_profiler/gui/static/app.js").read_text()
    for token in ("MATCH_MS","ROBUST_Z","PERSIST","synchronization_tolerance_ms"):
        assert token not in js
