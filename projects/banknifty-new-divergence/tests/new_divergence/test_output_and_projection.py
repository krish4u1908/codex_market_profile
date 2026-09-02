from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest

from banknifty_profiler.new_divergence.contracts import EngineConfig, EventKind, MarketEvent
from banknifty_profiler.new_divergence.api import ProjectionReadModel
from banknifty_profiler.new_divergence.clock import parse_instant, session_date
from banknifty_profiler.new_divergence.output import (
    atomic_json,
    publish_run,
    verify_run,
    write_session_catalog,
)
from banknifty_profiler.new_divergence.provenance import RUNTIME_VERSION
from banknifty_profiler.new_divergence.projection import (
    _zones_from,
    bn_0945_close_reference,
    build_browser,
    futures_oi_rows,
    futures_volume_rows,
    intraday_inventory_rows,
    option_strike_oi_rows,
)
from banknifty_profiler.new_divergence.service import _browser_identity, serve

from .helpers import IST, event, green_episode_events


def test_atomic_run_and_browser_are_discovered_without_embedded_dates(tmp_path) -> None:
    events = green_episode_events()
    run_root = tmp_path / "runs"
    destination = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_TEST"},
    )
    assert destination.is_dir()
    assert not (run_root / "sessions").exists()
    source = json.loads((destination / "source_manifest.json").read_text(encoding="utf-8"))
    assert source["runtime"]["source_file_count"] > 0
    assert len(source["runtime"]["source_tree_sha256"]) == 64
    catalog = json.loads((run_root / "catalog.json").read_text(encoding="utf-8"))
    assert [row["session"] for row in catalog["sessions"]] == [events[0].session.isoformat()]
    assert catalog["sessions"][0]["methodology_compatible"] is True
    assert catalog["sessions"][0]["actual_scope_sessions"]["1-session"] == []
    browser = build_browser(run_root, tmp_path / "browser")
    assert (browser / "index.html").is_file()
    build_manifest = json.loads((browser / "build_manifest.json").read_text(encoding="utf-8"))
    assert build_manifest["runtime_version"] == RUNTIME_VERSION
    assert _browser_identity(browser) == {
        "browser_runtime_version": RUNTIME_VERSION,
        "required_methodology": EngineConfig().methodology_version,
    }
    payload = json.loads((browser / "sessions" / f"{events[0].session}.json").read_text(encoding="utf-8"))
    assert payload["rendering_policy"]["future_records_rendered"] is False
    assert payload["rendering_policy"]["chart_x_axis"] == "RECEIPT_TIMESTAMP"
    assert payload["rendering_policy"]["candidate_transitions_coloured_as_zones"] is False
    assert payload["summary"]["ledger"]["valid"] is True
    assert len(payload["states"]["rows"]) == len(payload["price"]["rows"])
    assert len(payload["confirmed_zones"]) == 1
    zone = payload["confirmed_zones"][0]
    assert zone["colour"] == "GREEN"
    assert zone["terminal_state"] == "RESOLVED"
    assert zone["confirmed_at"] < zone["ended_at"]
    cutoff = payload["price"]["rows"][10][0]
    prefix = ProjectionReadModel(browser).session(events[0].session.isoformat(), as_of=cutoff)
    assert len(prefix["price"]["rows"]) == 11
    assert len(prefix["states"]["rows"]) == 11
    assert all(row["published_at"] <= cutoff for row in prefix["transitions"])
    assert all(row["confirmed_at"] <= cutoff for row in prefix["confirmed_zones"])
    assert all(
        row["ended_at"] is None or row["ended_at"] <= cutoff
        for row in prefix["confirmed_zones"]
    )
    assert prefix["availability"]["future_observations_returned"] is False
    assert prefix["availability"]["future_futures_volume_returned"] is False


def test_replay_retains_futures_counter_and_publishes_prefix_safe_id_volume_profile(
    tmp_path,
) -> None:
    source = green_episode_events()
    futures_count = 0
    events = []
    for row in source:
        if row.kind == EventKind.FUTURES_TICK:
            futures_count += 1
            row = replace(row, values={**row.values, "volume": 1_000 + futures_count * 10})
        events.append(row)
    run_root = tmp_path / "runs"
    run = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_FUTURES_VOLUME"},
    )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["files"]["futures_market"] == "futures_market.jsonl"
    assert summary["futures_market_count"] == futures_count
    assert verify_run(run)["valid"] is True

    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    intraday = payload["intraday_inventory"]
    assert intraday["scope"] == "ID"
    assert intraday["futures_market_retained"] is True
    assert intraday["feature_flags"]["volume_profile"]["available"] is True
    fields = intraday["fields"]
    family_index = fields.index("family")
    volume_rows = [
        row for row in intraday["rows"]
        if row[family_index] == "BN_REF_FUT_VOLUME_VPOC"
    ]
    assert volume_rows
    assert payload["futures_volume"]["fields"] == [
        "t", "p", "v", "dv", "vs", "i", "symbol", "event_id",
    ]
    assert payload["futures_volume"]["rows"]

    cutoff = parse_instant(volume_rows[0][fields.index("t")]) - timedelta(milliseconds=1)
    prefix = ProjectionReadModel(browser).session(events[0].session.isoformat(), as_of=cutoff)
    assert len(prefix["intraday_inventory"]["rows"]) < len(intraday["rows"])
    assert prefix["availability"]["future_intraday_inventory_returned"] is False
    volume_time_index = prefix["futures_volume"]["fields"].index("t")
    assert all(
        parse_instant(row[volume_time_index]) <= cutoff
        for row in prefix["futures_volume"]["rows"]
    )
    assert prefix["availability"]["future_futures_volume_returned"] is False


def test_retaining_futures_volume_does_not_change_divergence_ledger(tmp_path) -> None:
    original = green_episode_events()
    with_volume = []
    counter = 1_000
    for row in original:
        if row.kind == EventKind.FUTURES_TICK:
            counter += 10
            row = replace(row, values={**row.values, "volume": counter})
        with_volume.append(row)
    plain = publish_run(
        tmp_path / "plain", original[0].session, original, EngineConfig(),
        source={"kind": "NO_FUTURES_VOLUME"},
    )
    retained = publish_run(
        tmp_path / "retained", with_volume[0].session, with_volume, EngineConfig(),
        source={"kind": "WITH_FUTURES_VOLUME"},
    )
    assert (plain / "transitions.jsonl").read_bytes() == (
        retained / "transitions.jsonl"
    ).read_bytes()


def test_new_runtime_contains_no_sample_date_literal() -> None:
    package = __import__("banknifty_profiler.new_divergence", fromlist=["x"]).__path__[0]
    from pathlib import Path
    offenders = []
    for path in Path(package).rglob("*"):
        if path.is_file() and path.suffix in {".py", ".js", ".html", ".css"}:
            if "2026-08-" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
    assert offenders == []


def test_futures_oi_projection_deduplicates_and_resets_delta_after_gap() -> None:
    def snapshot(identifier: str, timestamp: str, oi: float) -> dict[str, object]:
        return {
            "futures_oi": {
                "event_id": identifier,
                "receipt_timestamp": timestamp,
                "oi": oi,
                "price": 101.5,
                "symbol": "NSE:BANKNIFTY31APRFUT",
            }
        }

    evidence = [
        snapshot("oi-2", "2031-04-07T04:11:00Z", 1_020),
        snapshot("oi-1", "2031-04-07T04:10:00Z", 1_000),
        snapshot("oi-2", "2031-04-07T04:11:00Z", 1_020),
        snapshot("oi-3", "2031-04-07T04:12:00Z", 1_005),
        snapshot("oi-4", "2031-04-07T04:17:01Z", 1_100),
    ]
    rows = futures_oi_rows(evidence, max_gap_seconds=300)
    assert [row["event_id"] for row in rows] == ["oi-1", "oi-2", "oi-3", "oi-4"]
    assert [row["d"] for row in rows] == [None, 20.0, -15.0, None]


def test_futures_volume_projection_is_0945_baselined_gap_and_reset_safe() -> None:
    observations = [
        {
            "timestamp": f"2031-04-07T04:15:0{second}Z",
            "index_receipt_timestamp": f"2031-04-07T04:15:0{second}Z",
            "index_price": 100 + second,
        }
        for second in (1, 2, 3)
    ]
    rows = futures_volume_rows(
        [
            {"t": "2031-04-07T04:14:59Z", "p": 110, "v": 900,
             "symbol": "FUT", "event_id": "pre"},
            {"t": "2031-04-07T04:15:01Z", "p": 111, "v": 1_000,
             "symbol": "FUT", "event_id": "a"},
            {"t": "2031-04-07T04:15:02Z", "p": 112, "v": 1_025,
             "symbol": "FUT", "event_id": "b"},
            {"t": "2031-04-07T04:15:03Z", "p": 113, "v": 900,
             "symbol": "FUT", "event_id": "c"},
        ],
        observations,
        analysis_start=parse_instant("2031-04-07T04:15:00Z"),
        max_gap_seconds=5,
    )
    assert [row["event_id"] for row in rows] == ["a", "b", "c"]
    assert [row["dv"] for row in rows] == [None, 25.0, None]
    assert [row["vs"] for row in rows] == ["BASELINE", "VALID", "RESET"]
    assert rows[1]["i"] == 102.0


def test_intraday_inventory_uses_only_causal_visible_contributions() -> None:
    observations = [
        {
            "timestamp": f"2031-04-07T04:15:0{second}Z",
            "index_receipt_timestamp": f"2031-04-07T04:15:0{second}Z",
            "index_price": price,
        }
        for second, price in ((1, 100.0), (2, 126.0), (3, 151.0))
    ]
    selection = {
        "available": True,
        "selected_at": "2031-04-07T04:15:01Z",
        "CE": [{"symbol": "CE100"}],
        "PE": [{"symbol": "PE100"}],
    }
    rows = intraday_inventory_rows(
        observations,
        [
            {"t": "2031-04-07T04:15:01Z", "d": 10, "event_id": "f1"},
            {"t": "2031-04-07T04:15:02Z", "d": 20, "event_id": "f2"},
        ],
        [
            {"t": "2031-04-07T04:15:02Z", "d": -12, "symbol": "CE100", "event_id": "c1"},
            {"t": "2031-04-07T04:15:03Z", "d": 15, "symbol": "PE100", "event_id": "p1"},
            {"t": "2031-04-07T04:15:03Z", "d": 99, "symbol": "UNSELECTED", "event_id": "x"},
        ],
        [
            {"t": "2031-04-07T04:15:01Z", "dv": 10, "vs": "VALID", "i": 100, "event_id": "v1"},
            {"t": "2031-04-07T04:15:02Z", "dv": 30, "vs": "VALID", "i": 126, "event_id": "v2"},
        ],
        selection,
        session="2031-04-07",
        max_index_age_seconds=5,
    )
    assert {row["family"] for row in rows} == {
        "FUT_POS_OI_VPOC", "CE_NEG_OI_VPOC", "PE_POS_OI_VPOC",
        "BN_REF_FUT_VOLUME_VPOC",
    }
    latest_volume = [row for row in rows if row["family"] == "BN_REF_FUT_VOLUME_VPOC"][-1]
    assert latest_volume["control_value"] == 125.0
    assert latest_volume["value_area_low"] <= latest_volume["control_value"]
    assert latest_volume["control_value"] <= latest_volume["value_area_high"]
    assert all(row["scope"] == "ID" for row in rows)


def test_browser_projects_futures_oi_and_prefix_api_hides_future_receipts(tmp_path) -> None:
    base = green_episode_events()
    start = base[0].receipt_timestamp
    oi_events = [
        event("oi-pre", EventKind.FUTURES_OI, start + timedelta(seconds=5), 9_500, 9_999),
        event("oi-a", EventKind.FUTURES_OI, start + timedelta(seconds=365), 10_000, 10_001),
        event("oi-b", EventKind.FUTURES_OI, start + timedelta(seconds=395), 10_040, 10_002),
        event("oi-c", EventKind.FUTURES_OI, start + timedelta(seconds=425), 10_025, 10_003),
    ]
    events = sorted([*base, *oi_events], key=lambda row: row.sort_key)
    run_root = tmp_path / "runs"
    publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_TEST_WITH_FUTURES_OI"},
    )
    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    assert payload["futures_oi"]["fields"] == ["t", "oi", "d", "p", "symbol", "event_id"]
    assert [row[1] for row in payload["futures_oi"]["rows"]] == [9_500.0, 10_000.0, 10_040.0, 10_025.0]
    assert [row[2] for row in payload["futures_oi"]["rows"]] == [None, None, 40.0, -15.0]
    assert payload["rendering_policy"]["aligned_chart_x_domain"] == "VISIBLE_PRICE_RECEIPT_PREFIX"

    cutoff = oi_events[2].receipt_timestamp
    prefix = ProjectionReadModel(browser).session(events[0].session.isoformat(), as_of=cutoff)
    assert [row[-1] for row in prefix["futures_oi"]["rows"]] == ["oi-pre", "oi-a", "oi-b"]
    assert prefix["availability"]["future_futures_oi_returned"] is False


def test_zone_active_before_0945_is_clipped_not_lost() -> None:
    transitions = [
        {
            "episode_id": "episode-a",
            "state": "CONFIRMED",
            "colour": "RED",
            "published_at": "2031-04-07T04:10:00Z",
        },
        {
            "episode_id": "episode-a",
            "state": "RESOLVED",
            "colour": "RED",
            "published_at": "2031-04-07T04:20:00Z",
        },
        {
            "episode_id": "episode-old",
            "state": "CONFIRMED",
            "colour": "GREEN",
            "published_at": "2031-04-07T04:00:00Z",
        },
        {
            "episode_id": "episode-old",
            "state": "RESOLVED",
            "colour": "GREEN",
            "published_at": "2031-04-07T04:14:59Z",
        },
    ]
    zones = _zones_from(transitions, parse_instant("2031-04-07T04:15:00Z"))
    assert len(zones) == 1
    assert zones[0]["confirmed_at"] == "2031-04-07T04:15:00.000000Z"
    assert zones[0]["source_confirmed_at"] == "2031-04-07T04:10:00Z"
    assert zones[0]["ended_at"] == "2031-04-07T04:20:00Z"
    assert zones[0]["clipped_at_projection_start"] is True


def test_option_strike_projection_is_gap_safe_per_contract() -> None:
    rows = [
        {"t": "2031-04-07T04:10:00Z", "e": "10-04-2031", "k": "CE", "s": 10_000,
         "oi": 1_000, "p": 100, "v": 500, "symbol": "CE10000", "event_id": "chain-1"},
        {"t": "2031-04-07T04:11:00Z", "e": "10-04-2031", "k": "CE", "s": 10_000,
         "oi": 1_025, "p": 110, "v": 550, "symbol": "CE10000", "event_id": "chain-2"},
        {"t": "2031-04-07T04:17:01Z", "e": "10-04-2031", "k": "CE", "s": 10_000,
         "oi": 1_050, "p": 120, "v": 600, "symbol": "CE10000", "event_id": "chain-3"},
    ]
    projected = option_strike_oi_rows(rows, max_gap_seconds=300)
    assert [row["d"] for row in projected] == [None, 25.0, None]
    assert [row["dv"] for row in projected] == [None, 50.0, None]
    assert [row["vs"] for row in projected] == ["BASELINE", "VALID", "GAP_RESET"]


def test_option_volume_reset_is_not_rendered_as_negative_traded_volume() -> None:
    rows = [
        {"t": "2031-04-07T04:10:00Z", "e": "10-04-2031", "k": "PE", "s": 10_000,
         "oi": 1_000, "p": 100, "v": 500, "symbol": "PE10000", "event_id": "chain-1"},
        {"t": "2031-04-07T04:11:00Z", "e": "10-04-2031", "k": "PE", "s": 10_000,
         "oi": 1_010, "p": 101, "v": 450, "symbol": "PE10000", "event_id": "chain-2"},
    ]
    projected = option_strike_oi_rows(rows, max_gap_seconds=300)
    assert projected[1]["d"] == 10.0
    assert projected[1]["dv"] is None
    assert projected[1]["vs"] == "RESET"


def test_browser_projects_dedicated_option_strikes_and_prefix_hides_future(tmp_path) -> None:
    base = green_episode_events()
    start = base[0].receipt_timestamp

    def chain(identifier, offset, sequence, ce_oi, pe_oi, ce_volume, pe_volume):
        timestamp = start + timedelta(seconds=offset)
        return MarketEvent(
            event_id=identifier,
            session=base[0].session,
            kind=EventKind.OPTION_PRESSURE,
            symbol="NSE:NIFTYBANK-INDEX",
            event_timestamp=timestamp,
            receipt_timestamp=timestamp,
            sequence=sequence,
            values={
                "score": 0.0,
                "selected_expiry": "10-04-2031",
                "strike_oi": [
                    {"expiry": "10-04-2031", "option_type": "CE", "strike": 10_000,
                     "oi": ce_oi, "price": 100, "volume": ce_volume, "symbol": "CE10000"},
                    {"expiry": "10-04-2031", "option_type": "PE", "strike": 10_000,
                     "oi": pe_oi, "price": 110, "volume": pe_volume, "symbol": "PE10000"},
                ],
            },
        )

    chains = [
        chain("chain-a", 365, 20_001, 1_000, 1_200, 500, 600),
        chain("chain-b", 395, 20_002, 1_020, 1_190, 550, 640),
        chain("chain-c", 425, 20_003, 1_015, 1_230, 590, 700),
    ]
    events = sorted([*base, *chains], key=lambda row: row.sort_key)
    run_root = tmp_path / "runs"
    run = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_TEST_WITH_OPTION_STRIKES"},
    )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["option_strike_oi_count"] == 6
    assert summary["files"]["option_strike_oi"] == "option_strike_oi.jsonl"
    assert summary["files"]["session_reference"] == "session_reference.json"
    assert summary["session_reference_status"] == "LATE_FIRST_INDEX_TICK"
    assert "strike_oi" not in (run / "evidence_snapshots.jsonl").read_text(encoding="utf-8")

    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    assert payload["option_strike_oi"]["retained"] is True
    assert payload["option_strike_oi"]["fields"] == [
        "t", "e", "k", "s", "oi", "d", "p", "v", "dv", "vs", "symbol", "event_id"
    ]
    assert payload["option_strike_oi"]["analysis_start"] == "2031-04-07T04:15:00.000000Z"
    projected = [
        dict(zip(payload["option_strike_oi"]["fields"], row))
        for row in payload["option_strike_oi"]["rows"]
    ]
    assert [row["d"] for row in projected if row["k"] == "CE"] == [None, 20.0, -5.0]
    assert [row["d"] for row in projected if row["k"] == "PE"] == [None, -10.0, 40.0]
    assert [row["dv"] for row in projected if row["k"] == "CE"] == [None, 50.0, 40.0]
    assert [row["dv"] for row in projected if row["k"] == "PE"] == [None, 40.0, 60.0]
    assert payload["option_strike_oi"]["strike_selection"]["available"] is False

    prefix = ProjectionReadModel(browser).session(
        events[0].session.isoformat(), as_of=chains[1].receipt_timestamp
    )
    assert len(prefix["option_strike_oi"]["rows"]) == 4
    assert prefix["availability"]["future_option_strike_oi_returned"] is False
    assert prefix["availability"]["future_option_strike_volume_returned"] is False


def test_0945_close_atm_plus_three_otm_selection_is_fixed_and_volume_backed(tmp_path) -> None:
    base = green_episode_events()
    close_time = datetime(2031, 4, 7, 9, 45, tzinfo=IST)
    close_index = event("close-index", EventKind.INDEX_TICK, close_time, 105.0, 90_000)
    close_future = event(
        "close-future",
        EventKind.FUTURES_TICK,
        close_time + timedelta(milliseconds=100),
        110.0,
        90_001,
    )
    strikes = list(range(70, 141, 10))

    def chain(identifier: str, timestamp: datetime, sequence: int, increment: int) -> MarketEvent:
        strike_rows = []
        for option_type in ("CE", "PE"):
            for strike in strikes:
                strike_rows.append({
                    "expiry": "10-04-2031",
                    "option_type": option_type,
                    "strike": strike,
                    "oi": 10_000 + strike + increment,
                    "price": 100,
                    "volume": 1_000 + strike + increment * 2,
                    "symbol": f"{option_type}{strike}",
                })
        return MarketEvent(
            event_id=identifier,
            session=base[0].session,
            kind=EventKind.OPTION_PRESSURE,
            symbol="NSE:NIFTYBANK-INDEX",
            event_timestamp=timestamp,
            receipt_timestamp=timestamp,
            sequence=sequence,
            values={
                "score": 0.0,
                "selected_expiry": "10-04-2031",
                "strike_oi": strike_rows,
            },
        )

    chains = [
        chain("pre-close-chain", close_time - timedelta(seconds=55), 80_000, 0),
        chain("post-close-chain-1", close_time + timedelta(seconds=5), 90_002, 25),
        chain("post-close-chain-2", close_time + timedelta(seconds=65), 90_003, 50),
    ]
    events = sorted([*chains, *base, close_index, close_future], key=lambda row: row.sort_key)
    run_root = tmp_path / "runs"
    publish_run(
        run_root,
        base[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_0945_CLOSE_STRIKE_FLOW"},
    )

    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(base[0].session.isoformat())
    selection = payload["option_strike_oi"]["strike_selection"]
    assert selection["available"] is True
    assert selection["atm"] == 100.0  # 105 is tied; lower listed strike wins.
    assert selection["fixed_for_session"] is True
    assert selection["reference_close"]["status"] == "VALID_0945_BN_CLOSE"
    assert selection["reference_close"]["price"] == 105.0
    assert selection["reference_close"]["age_ms"] == 0.0
    assert [row["strike"] for row in selection["CE"]] == [100.0, 110.0, 120.0, 130.0]
    assert [row["strike"] for row in selection["PE"]] == [100.0, 90.0, 80.0, 70.0]
    assert selection["volume_retained"] is True
    assert payload["option_strike_oi"]["volume_retained"] is True

    projected = [
        dict(zip(payload["option_strike_oi"]["fields"], row))
        for row in payload["option_strike_oi"]["rows"]
    ]
    ce_atm = [row for row in projected if row["symbol"] == "CE100"]
    pe_atm = [row for row in projected if row["symbol"] == "PE100"]
    assert [row["d"] for row in ce_atm] == [None, 25.0]
    assert [row["dv"] for row in ce_atm] == [None, 50.0]
    assert [row["d"] for row in pe_atm] == [None, 25.0]
    assert [row["dv"] for row in pe_atm] == [None, 50.0]
    assert all(parse_instant(row["t"]) >= close_time for row in projected)

    early = ProjectionReadModel(browser).session(
        base[0].session.isoformat(), as_of=close_time + timedelta(seconds=1)
    )
    early_selection = early["option_strike_oi"]["strike_selection"]
    assert early_selection["available"] is False
    assert early_selection["reason"] == "AWAITING_FIRST_COMPLETE_CHAIN_RECEIPT"
    assert early_selection["CE"] == []
    assert early_selection["PE"] == []
    assert early["option_strike_oi"]["volume_retained"] is False
    assert early["option_strike_oi"]["rows"] == []


def test_0945_close_reference_rejects_a_stale_index_tick() -> None:
    reference = bn_0945_close_reference(
        [{
            "index_receipt_timestamp": "2031-04-07T09:44:57.999000+05:30",
            "index_price": 105.0,
        }],
        session="2031-04-07",
        index_symbol="NSE:NIFTYBANK-INDEX",
        max_age_ms=2_000,
    )
    assert reference["status"] == "STALE_0945_BN_CLOSE"
    assert reference["age_ms"] == pytest.approx(2_001)


def test_pre_strike_artifact_run_remains_compatible_with_explicit_unavailable_state(tmp_path) -> None:
    events = green_episode_events()
    run_root = tmp_path / "runs"
    run = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_PRE_STRIKE_RUNTIME"},
    )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    summary["files"].pop("option_strike_oi")
    summary["artifact_sha256"].pop("option_strike_oi")
    summary.pop("option_strike_oi_count")
    atomic_json(run / "summary.json", summary)
    (run / "option_strike_oi.jsonl").unlink()

    assert verify_run(run)["valid"] is True
    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    assert payload["option_strike_oi"]["retained"] is False
    assert payload["option_strike_oi"]["rows"] == []


def test_pre_futures_market_artifact_run_keeps_prior_profiles_compatible(tmp_path) -> None:
    events = green_episode_events()
    run_root = tmp_path / "runs"
    run = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_PRE_INTRADAY_VOLUME_RUNTIME"},
    )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    summary["files"].pop("futures_market")
    summary["artifact_sha256"].pop("futures_market")
    summary.pop("futures_market_count")
    atomic_json(run / "summary.json", summary)
    (run / "futures_market.jsonl").unlink()

    assert verify_run(run)["valid"] is True
    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    assert payload["intraday_inventory"]["futures_market_retained"] is False
    assert payload["intraday_inventory"]["feature_flags"]["volume_profile"]["available"] is False


def test_pre_session_reference_run_remains_compatible_with_0945_projection(
    tmp_path,
) -> None:
    events = green_episode_events()
    run_root = tmp_path / "runs"
    run = publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_PRE_SESSION_REFERENCE_RUNTIME"},
    )
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    summary["files"].pop("session_reference")
    summary["artifact_sha256"].pop("session_reference")
    summary.pop("session_reference_status")
    atomic_json(run / "summary.json", summary)
    (run / "session_reference.json").unlink()

    assert verify_run(run)["valid"] is True
    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    assert payload["option_strike_oi"]["retained"] is True
    selection = payload["option_strike_oi"]["strike_selection"]
    assert selection["available"] is False
    assert selection["reference_close"]["status"] == "VALID_0945_BN_CLOSE"
    assert selection["reason"] == "NO_COMPLETE_ATM_PLUS_THREE_OTM_CHAIN_AFTER_0945_CLOSE"


def test_scopes_use_actual_prior_eligible_sessions_not_calendar_subtraction(tmp_path) -> None:
    root = tmp_path / "runs"
    base = green_episode_events()
    for days in (-4, 0, 2):
        delta = timedelta(days=days)
        shifted = [
            replace(
                row,
                session=session_date(row.receipt_timestamp + delta),
                event_timestamp=row.event_timestamp + delta,
                receipt_timestamp=row.receipt_timestamp + delta,
            )
            for row in base
        ]
        publish_run(
            root,
            shifted[0].session,
            shifted,
            EngineConfig(),
            source={"kind": "SYNTHETIC_TEST"},
        )
    atomic_json(root / "2031-04-04" / "summary.json", {
        "session": "2031-04-04",
        "basis_observation_count": 0,
        "transition_count": 0,
        "ledger": {"valid": True},
    })
    catalog = write_session_catalog(root)
    latest = catalog["sessions"][-1]
    assert latest["actual_scope_sessions"] == {
        "intraday": ["2031-04-09"],
        "1-session": ["2031-04-07"],
        "2-session": ["2031-04-03", "2031-04-07"],
        "3-session": ["2031-04-03", "2031-04-07"],
    }


def test_modified_dense_artifact_loses_catalog_eligibility(tmp_path) -> None:
    events = green_episode_events()
    root = tmp_path / "runs"
    run = publish_run(
        root, events[0].session, events, EngineConfig(), source={"kind": "SYNTHETIC_TEST"}
    )
    with (run / "basis_observations.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    integrity = verify_run(run)
    assert not integrity["valid"]
    assert "ARTIFACT_HASH_MISMATCH:basis" in integrity["reasons"]
    catalog = write_session_catalog(root)
    assert catalog["sessions"][0]["eligible"] is False


def test_browser_uses_one_receipt_time_axis_and_never_colours_raw_candidates() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "src/banknifty_profiler/new_divergence/static_new/app.js").read_text(
        encoding="utf-8"
    )
    assert "index / (visible.length - 1)" not in script
    assert "new Date(row.t).getTime()" in script
    assert "visibleConfirmedZones" in script
    assert 'item.state === "CANDIDATE"' in script
    assert 'return "candidate"' in script


def test_browser_restores_market_history_but_suppresses_bars_before_0945(tmp_path) -> None:
    events = green_episode_events()
    root = tmp_path / "runs"
    publish_run(
        root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_0945_PROJECTION_BOUNDARY"},
    )
    browser = build_browser(root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    start = parse_instant(payload["projection_window"]["start"])
    boundary = parse_instant(payload["projection_window"]["bar_analysis_start"])
    assert payload["projection_window"]["rule"] == "FULL_MARKET_HISTORY_WITH_0945_BAR_BASELINE"
    assert start < boundary
    assert parse_instant(payload["price"]["rows"][0][0]) == start
    assert parse_instant(payload["states"]["rows"][0][0]) == start
    assert all(
        row[2] is None
        for row in payload["futures_oi"]["rows"]
        if parse_instant(row[0]) < boundary
    )
    assert all(parse_instant(row[0]) >= boundary for row in payload["option_strike_oi"]["rows"])
    assert all(parse_instant(row[0]) >= boundary for row in payload["cash_participation"]["rows"])


def test_landing_catalog_distinguishes_sample_ready_from_replay_ready() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "src/banknifty_profiler/new_divergence/static_new/app.js").read_text(
        encoding="utf-8"
    )
    page = (root / "src/banknifty_profiler/new_divergence/static_new/index.html").read_text(
        encoding="utf-8"
    )
    assert "Cash sample ready · replay pending" in script
    assert 'session.cash_sample_row_count' in script
    assert "causal replay opens only after run and ledger verification" in page


def test_market_and_oi_share_one_panel_domain_and_plot_margins() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    assert "const CHART_MARGIN = Object.freeze({ left: 58, right: 14 })" in script
    assert script.count("const margin = { ...CHART_MARGIN") == 3
    assert "const visiblePrice = priceRows.slice(0, cursor + 1)" in script
    assert "const first = new Date(visiblePrice[0].t).getTime()" in script
    assert "const last = new Date(visiblePrice.at(-1).t).getTime()" in script
    assert "function marketOiChart(" in script
    assert '.flatMap((row) => [Number(row.i), Number(row.f)])' in script
    assert 'byId("priceChart"), rows, oiRows, cursor, visibleZones' in script
    assert 'id="priceChart" height="680" data-logical-height="680"' in replay
    assert 'id="oiChart"' not in replay
    assert replay.count('class="chart-panel panel"') == 1
    assert "Index / Futures / adaptive Basis / Futures OI / ΔOI" in replay
    assert 'id="basisChart"' not in replay
    assert 'id="basisPanel"' not in replay
    assert 'id="frameBasis" type="checkbox" checked> Basis lane' in replay
    assert 'id="basisPlacement"' in replay
    assert 'class="line-basis"' in replay
    assert 'class="line-oi"' in replay
    assert 'class="bar-oi-positive"' in replay
    assert 'class="bar-oi-negative"' in replay
    assert "function drawInventoryLevels(" in script
    assert "function inventoryDisplayLines(" in script
    assert "priceGapToleranceSeconds, oiGapToleranceSeconds, inventoryLines" in script
    assert 'id="inventoryOiVpoc" type="checkbox" checked' in replay
    assert 'id="inventoryVolumeVpoc" type="checkbox" checked' in replay
    assert 'id="inventoryVolumeVah" type="checkbox" checked' in replay
    assert 'id="inventoryVolumeVal" type="checkbox" checked' in replay
    assert 'id="inventoryVolumeProfile" type="checkbox" checked' in replay
    assert 'id="inventoryScopeID" type="checkbox" checked' in replay
    assert 'id="inventoryScope1D" type="checkbox"' in replay
    assert 'id="inventoryScope2D" type="checkbox"' in replay
    assert 'id="inventoryScope3D" type="checkbox"' in replay
    assert "function ensureInventoryScopeSelection(" not in script
    assert 'byId(id).addEventListener("change", render)' in script
    assert 'id="inventoryVolumeStatus"' in replay
    assert "ID volume unavailable: replay this session with V1.0.13 or later." in script
    assert "Every scope may be switched off." in replay
    assert "function latestIntradayControls(" in script
    assert 'inventoryDisplayLines(inventoryBlock, intradayBlock, asOf)' in script
    assert 'id="inventoryVisibleCount"' in replay
    assert "None enter RED/GREEN divergence identification" in replay
    assert 'id="inventoryLevelList"' in replay


def test_replay_canvas_height_is_stable_across_repeated_frames() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    assert "canvas.dataset.logicalHeight" in script
    assert 'canvas.getAttribute("height")' not in script
    assert "canvas.style.height = `${height}px`" in script
    assert 'id="priceChart" height="680" data-logical-height="680"' in replay
    assert 'id="basisChart"' not in replay
    assert 'id="ceStrikeChart" height="300" data-logical-height="300"' in replay
    assert 'id="peStrikeChart" height="300" data-logical-height="300"' in replay
    for canvas_id in (
        "ceOiFlowChart", "peOiFlowChart", "ceVolumeFlowChart", "peVolumeFlowChart"
    ):
        assert f'id="{canvas_id}" height="210" data-logical-height="210"' in replay
    assert 'id="oiChart"' not in replay


def test_strike_oi_panels_use_full_width_right_rail_and_vertical_order() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    style = (static / "style.css").read_text(encoding="utf-8")
    assert replay.index('id="ceStrikeChart"') < replay.index('id="peStrikeChart"')
    assert 'class="replay-workspace"' in replay
    assert 'class="strike-column"' in replay
    assert ".strike-column { display: flex; flex-direction: column" in style
    assert ".replay-shell { width: 100%;" in style
    assert "grid-template-columns: minmax(0, 4fr) minmax(340px, 1fr)" in style
    assert "function latestStrikeSnapshot(" in script
    assert "function strikeOiSnapshotChart(" in script
    assert "const visiblePrice = priceRows.slice(0, cursor + 1)" in script
    assert "sharedMaximumOi" in script
    assert "compactQuantity(oi)" in script
    assert "`BN ${number(bn, 0)}`" in script
    assert "context.setLineDash([5, 4])" in script
    assert "row.e === selection.expiry" in script
    assert "ageSeconds > maxAgeSeconds" in script
    assert "CE OI snapshot" in replay
    assert "PE OI snapshot" in replay


def test_0945_close_strike_flow_panels_are_stacked_and_share_receipt_time_domain() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    identifiers = [
        'id="ceOiFlowChart"',
        'id="peOiFlowChart"',
        'id="ceVolumeFlowChart"',
        'id="peVolumeFlowChart"',
    ]
    assert [replay.index(identifier) for identifier in identifiers] == sorted(
        replay.index(identifier) for identifier in identifiers
    )
    assert replay.count('class="strike-flow-panel panel"') == 4
    assert "function strikeFlowChart(" in script
    assert "const visiblePrice = priceRows.slice(0, cursor + 1)" in script
    assert 'const field = metric === "oi" ? "d" : "dv"' in script
    assert 'metric === "oi" ? -maximum : 0' in script
    assert 'row[field] !== null' in script
    assert "renderStrikeFlowLegend" in script
    assert "strikeSelection.available === true" in script
    assert "time >= Math.max(first, analysisStart, selectedAt)" in script
    assert "receipt >= Math.max(first, analysisStart, selectedAt)" in script
    assert replay.count("BN 09:45 close ATM · fixed thereafter") == 2


def test_every_replay_frame_has_a_persistent_independent_visibility_control() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    style = (static / "style.css").read_text(encoding="utf-8")
    expected = {
        "frameMarket": "marketPanel",
        "frameCeOi": "ceOiFlowPanel",
        "framePeOi": "peOiFlowPanel",
        "frameCeVolume": "ceVolumeFlowPanel",
        "framePeVolume": "peVolumeFlowPanel",
        "frameCeSnapshot": "ceSnapshotPanel",
        "framePeSnapshot": "peSnapshotPanel",
        "frameInventoryList": "inventoryListPanel",
    }
    for control, target in expected.items():
        assert f'id="{control}" type="checkbox" checked' in replay
        assert f'id="{target}"' in replay
        assert f'{control}: "{target}"' in script
    assert 'const OVERLAY_TOGGLE_IDS = Object.freeze(["frameBasis"])' in script
    assert 'id="frameBasis" type="checkbox" checked' in replay
    assert 'window.sessionStorage.setItem(FRAME_STORAGE_KEY' in script
    assert "installFrameMaximizeControls();" in script
    assert 'event.key === "Escape"' in script
    assert ".frame-maximized" in style
    assert "restoreFrameVisibility();" in script
    assert 'classList.toggle("no-strike-column", !rightVisible)' in script
    assert ".replay-workspace.no-strike-column { grid-template-columns: minmax(0, 1fr); }" in style


def test_v1032_basis_futures_oi_and_delta_oi_overlay_one_market_canvas() -> None:
    root = Path(__file__).resolve().parents[2]
    static = root / "src/banknifty_profiler/new_divergence/static_new"
    script = (static / "app.js").read_text(encoding="utf-8")
    replay = (static / "replay.html").read_text(encoding="utf-8")
    assert "function adaptiveBasisLane(" in script
    assert "function drawAdaptiveBasisLane(" in script
    assert 'mode: "BETWEEN"' in script
    assert 'mode: "TOP"' in script
    assert "corridorBottom - corridorTop >= requestedLaneHeight" in script
    assert "const requestedLaneHeight = 180" in script
    assert "guide <= 4" in script
    assert "const priceBottom = height - margin.bottom" in script
    assert "const oiOverlayTop = priceTop + 22" in script
    assert "const oiOverlayBottom = Math.max(oiOverlayTop + 1, priceBottom - 48)" in script
    assert "const deltaZeroY = priceBottom - 23" in script
    assert "const deltaHalfHeight = 20" in script
    assert "participationHeight" not in script
    assert "oiLineTop" not in script
    assert "oiLineBottom" not in script
    assert "return basisLane.mode" in script
    assert 'id="basisPlacement"' in replay
    assert "Basis lane · between Index/Futures" in script
    assert "Basis lane · top" in script
    assert 'id="basisPanel"' not in replay


def test_service_rejects_browser_assets_built_by_another_runtime(tmp_path) -> None:
    atomic_json(tmp_path / "catalog.json", {"required_methodology": EngineConfig().methodology_version})
    atomic_json(tmp_path / "build_manifest.json", {"runtime_version": "older-runtime"})
    with pytest.raises(ValueError, match="browser projection runtime mismatch"):
        serve(tmp_path, "127.0.0.1", 8080)


def test_legacy_methodology_run_requires_replay_before_gui_eligibility(tmp_path) -> None:
    events = green_episode_events()
    root = tmp_path / "runs"
    publish_run(
        root,
        events[0].session,
        events,
        replace(EngineConfig(), methodology_version="LEGACY_UNSAFE_HORIZONS"),
        source={"kind": "SYNTHETIC_LEGACY_TEST"},
    )
    catalog = write_session_catalog(root)
    assert catalog["eligible_sessions"] == []
    assert catalog["sessions"][0]["eligible"] is False
    assert catalog["sessions"][0]["methodology_compatible"] is False
