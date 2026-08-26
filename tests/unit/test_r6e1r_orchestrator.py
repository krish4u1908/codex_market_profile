from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from banknifty_profiler.participation import views as participation_views
from banknifty_profiler.shadow import orchestrator as orchestrator_module
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.shadow.state import ShadowState
from banknifty_profiler.runtime.timestamps import parse_timestamp


IST = ZoneInfo("Asia/Kolkata")
SESSION = "2026-08-20"
INDEX = "NSE:NIFTYBANK-INDEX"
FUTURES = "NSE:BANKNIFTY26AUGFUT"


def contract(tmp_path: Path) -> dict:
    return {
        "state_root": tmp_path / "state",
        "engine_hash": "ENGINE",
        "configuration_hash": "CONFIG",
        "raw_run_id": "RAW-RUN",
        "config": {
            "synchronization_tolerance_ms": 2000,
            "freshness_seconds": {"index": 10, "futures": 10, "futures_oi": 180, "ce": 180, "pe": 180},
            "classification": "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL",
        },
    }


def observation(identity, instrument, symbol, instant, *, price=None, volume=None, oi=None, strike=None, expiry=None, stream=None, previous_oi=None, delta_oi=None):
    stream = stream or ("raw" if instrument in {"INDEX", "FUTURES"} else "oi")
    return {
        "observation_id": identity,
        "session_date": SESSION,
        "instrument_class": instrument,
        "canonical_symbol": symbol,
        "source_symbol": symbol,
        "receipt_timestamp": instant.isoformat(),
        "exchange_timestamp": instant.isoformat(),
        "price": price,
        "cumulative_volume": volume,
        "open_interest": oi,
        "previous_open_interest": previous_oi,
        "open_interest_change": delta_oi,
        "strike": strike,
        "expiry": expiry,
        "source_file": f"{stream}/{SESSION}/focused_fixture.jsonl",
        "source_byte_offset": int(identity[1:]) * 100,
        "source_row_number": int(identity[1:]),
        "raw_record_id": f"RAW-{identity}",
        "availability_status": "AVAILABLE",
        "freshness_status": "FRESH",
        "out_of_order": False,
    }


def full_stack_fixture() -> list[dict]:
    """A small but genuinely qualifying frozen-detector GREEN fixture."""
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    rows = []
    ordinal = 0

    def add(instrument, symbol, instant, **values):
        nonlocal ordinal
        ordinal += 1
        rows.append(observation(f"O{ordinal:04d}", instrument, symbol, instant, **values))

    # Index falls while the future drifts up, expanding basis.  Two frozen
    # horizons qualify after five minutes and P60_N5 confirms one episode.
    for step in range(49):
        instant = base + timedelta(seconds=10 * step)
        add("INDEX", INDEX, instant, price=57000 - step, volume=0)
        add("FUTURES", FUTURES, instant + timedelta(milliseconds=500), price=57020 + step * .1, volume=100 + step * 5)
        if step % 6 == 0:
            add("FUTURES_OI", FUTURES, instant + timedelta(milliseconds=600), price=57020 + step * .1, volume=100 + step * 5, oi=1000 + step * 10, expiry="2026-08-27")
            add("CE", "NSE:BANKNIFTY26AUG57000CE", instant + timedelta(milliseconds=700), price=200 + step * .2, volume=50 + step * 2, oi=500 + step * 8, strike=57000, expiry="2026-08-27")
            add("PE", "NSE:BANKNIFTY26AUG57000PE", instant + timedelta(milliseconds=800), price=180 - step * .1, volume=60 + step * 3, oi=600 + step * 7, strike=57000, expiry="2026-08-27")
    return rows


def ledger_counts(orchestrator: LiveAnalyticalOrchestrator) -> dict[str, int]:
    return {name: len(ledger.rows()) for name, ledger in orchestrator.ledgers.items()}


def assert_unique_stage_and_publication_ids(
    orchestrator: LiveAnalyticalOrchestrator,
) -> None:
    for path in orchestrator.stage_root.glob("*.jsonl"):
        identities = [
            row["observation_id"]
            for row in orchestrator_module.AppendOnlyLedger(path).rows()
        ]
        assert len(identities) == len(set(identities)), path
    for name, ledger in orchestrator.ledgers.items():
        identities = [row["event_id"] for row in ledger.rows()]
        assert len(identities) == len(set(identities)), name


def test_focused_fixture_reaches_every_canonical_callback_and_gui(tmp_path):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(full_stack_fixture())
    state = orchestrator.snapshot(SESSION)

    assert state["counts"]["basis"] > 0
    assert state["counts"]["inventory"] > 0
    assert state["counts"]["episodes"] == 1
    assert state["counts"]["dependencies"] == 1
    assert state["counts"]["lifecycle"] > 0
    assert state["counts"]["resolution"] > 0
    assert state["counts"]["participation_dense"] > 0
    assert state["counts"]["participation_transitions"] > 0
    assert state["counts"]["participation_summaries"] == 1
    assert state["counts"]["compatibility_snapshots"] == 1
    assert state["counts"]["cross_layer_transitions"] > 0
    assert {"FUTURES", "CE", "PE", "BREADTH", "JOINT"}.issubset({row["component"] for row in state["participation_transitions"]})
    assert state["participation_summaries"][0]["first_breadth_timestamp"]
    assert state["participation_summaries"][0]["first_joint_participation_timestamp"]
    assert state["availability"]["overall_state"] == "LIVE_INTRADAY_ONLY"
    assert state["availability"]["layers"]["ID"]["state"] == "AVAILABLE"
    assert all(state["availability"]["layers"][h]["state"] == "MISSING_PRIOR_SESSION" for h in ("1D", "2D", "3D"))
    assert state["gui_payload"]["counts"]["price"] > 0
    assert state["gui_payload"]["counts"]["inventory"] > 0
    assert state["gui_payload"]["projection_hash"]
    assert all(value == 1 for value in state["callback_invocations"].values())
    assert set(state["callback_invocations"]) == {"synchronization", "inventory", "divergence_detector", "dependency", "lifecycle", "participation", "participation_views", "cross_layer", "gui_projection"}
    assert all(not row.get("state_exit_timestamp") or row["state_exit_timestamp"] <= state["availability"]["calculation_timestamp"] for row in state["lifecycle"])
    lifecycle_ends = {}
    for row in state["lifecycle"]:
        lifecycle_ends[row["episode_id"]] = max(
            lifecycle_ends.get(row["episode_id"], ""), row["state_entry_timestamp"]
        )
    assert all(
        row["observation_timestamp"] <= lifecycle_ends[row["episode_id"]]
        for row in state["participation_dense"]
    )

    counts = ledger_counts(orchestrator)
    assert counts["divergence_confirmations"] == 1
    assert counts["dependency_retriggers"] == 1
    assert counts["lifecycle_transitions"] == state["counts"]["lifecycle"]
    assert counts["inventory_winner_transitions"] == state["counts"]["inventory"]
    assert counts["participation_transitions"] == state["counts"]["participation_transitions"]
    assert counts["cross_layer_transitions"] == state["counts"]["cross_layer_transitions"]


def test_restart_and_callback_retry_are_exactly_once(tmp_path):
    rows = full_stack_fixture()
    first = LiveAnalyticalOrchestrator(contract(tmp_path))
    first.process(rows)
    expected = first.snapshot(SESSION)
    before = ledger_counts(first)

    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    assert restarted.snapshot(SESSION) == expected
    assert restarted.process(rows) == {}
    assert restarted.on_observation(rows[-1]) == expected
    assert ledger_counts(restarted) == before
    assert restarted.ledgers["refusals_data_quality"].rows() == []


def test_missing_options_preserves_market_and_intraday_partial_context(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    rows = [
        observation("O0001", "INDEX", INDEX, base, price=57000, volume=0),
        observation("O0002", "FUTURES", FUTURES, base + timedelta(milliseconds=500), price=57020, volume=100),
        observation("O0003", "INDEX", INDEX, base + timedelta(seconds=1), price=57001, volume=0),
        observation("O0004", "FUTURES", FUTURES, base + timedelta(seconds=1, milliseconds=500), price=57021, volume=120),
    ]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(rows)
    state = orchestrator.snapshot(SESSION)
    assert state["counts"]["basis"] == 2
    assert state["counts"]["inventory"] > 0
    assert state["availability"]["overall_state"] == "LIVE_INTRADAY_ONLY"
    assert state["availability"]["divergence_state"] == "AVAILABLE"
    assert state["availability"]["participation_state"].startswith("SUSPENDED")
    assert state["availability"]["ce_state"] == "STALE_OR_MISSING"
    assert state["availability"]["pe_state"] == "STALE_OR_MISSING"


def test_poll_callback_routes_committed_typed_observations(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    data = tmp_path / "collector"
    session_root = data / "raw" / SESSION
    session_root.mkdir(parents=True)
    (data / "oi" / SESSION).mkdir(parents=True)
    runtime = contract(tmp_path)
    runtime.update({
        "data_root": data,
        "minimum_session_date": SESSION,
        "selected_futures_symbols": [FUTURES],
    })
    runtime["config"].update({
        "max_buffer_bytes_per_file": 1_048_576,
        "max_read_bytes_per_file_per_poll": 1_048_576,
    })
    records = []
    for offset, (symbol, price, volume) in enumerate(((INDEX, 57000, 0), (FUTURES, 57020, 100), (INDEX, 57001, 0), (FUTURES, 57021, 120))):
        instant = base + timedelta(milliseconds=500 * offset)
        records.append(json.dumps({
            "received_at": instant.isoformat(), "event_time": instant.isoformat(),
            "message": {"symbol": symbol, "ltp": price, "vol_traded_today": volume},
        }))
    (session_root / "events_09.jsonl").write_text("\n".join(records) + "\n")

    ingestor = IncrementalJSONLIngestor(runtime)
    orchestrator = LiveAnalyticalOrchestrator(runtime, ingestor.ledgers)
    ingestor.register_callback(orchestrator)
    committed = ingestor.poll()
    orchestrator.flush()
    state = orchestrator.snapshot(SESSION)
    assert len(committed) == 4
    assert state["counts"]["observations"] == 4
    assert state["counts"]["basis"] == 2
    assert state["counts"]["inventory"] > 0
    assert state["gui_payload"]["counts"]["price"] == 2
    ingestor.close()


def test_unknown_and_late_observations_are_audited_not_backdated(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    good = observation("O0002", "INDEX", INDEX, base + timedelta(seconds=2), price=57000)
    unknown = observation("O0003", "UNKNOWN_SYMBOL", "NSE:OTHER", base + timedelta(seconds=3), price=1)
    late = observation("O0001", "INDEX", INDEX, base + timedelta(seconds=1), price=56999)
    orchestrator.process([good])
    orchestrator.process([unknown, late])
    state = orchestrator.snapshot(SESSION)
    assert state["counts"]["observations"] == 1
    reasons = [row["reason"] for row in orchestrator.ledgers["refusals_data_quality"].rows()]
    assert reasons == ["OUT_OF_ORDER_ANALYTICAL_RECEIPT", "UNKNOWN_SYMBOL"] or reasons == ["UNKNOWN_SYMBOL", "OUT_OF_ORDER_ANALYTICAL_RECEIPT"]


def test_physical_stream_lineage_and_same_session_oi_delta_are_canonical(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    values = [
        observation("O0001", "INDEX", INDEX, base, price=57000, stream="raw"),
        # Embedded option-chain underlying must not enter the WS market frame.
        observation("O0002", "INDEX", INDEX, base + timedelta(milliseconds=100), price=99999, stream="oi"),
        # Raw premium events belong only to RawStore.market, never REST OI.
        observation("O0003", "CE", "NSE:BANKNIFTY26AUG57000CE", base + timedelta(milliseconds=200), price=210, oi=9999, strike=57000, expiry="2026-08-27", stream="raw"),
        observation("O0004", "CE", "NSE:BANKNIFTY26AUG57000CE", base + timedelta(milliseconds=300), price=200, oi=100, previous_oi=1, delta_oi=99, strike=57000, expiry="2026-08-27", stream="oi"),
        observation("O0005", "CE", "NSE:BANKNIFTY26AUG57000CE", base + timedelta(milliseconds=400), price=201, oi=110, previous_oi=2, delta_oi=108, strike=57000, expiry="2026-08-27", stream="oi"),
        # Depth-only raw rows have no canonical price/volume evidence.
        observation("O0006", "FUTURES", FUTURES, base + timedelta(milliseconds=500), stream="raw"),
    ]
    prepared = [orchestrator._prepare(row) for row in values]
    market = orchestrator._market_frame(prepared)
    oi = orchestrator._oi_frame(prepared)
    store = orchestrator._participation_store(prepared)

    assert list(market.last_price) == [57000]
    assert len(oi) == 2
    assert pd.isna(oi.iloc[0].delta_oi)
    assert oi.iloc[1].previous_oi == 100
    assert oi.iloc[1].delta_oi == 10
    assert list(store.market) == [INDEX, "NSE:BANKNIFTY26AUG57000CE"]
    assert list(store.oi) == ["NSE:BANKNIFTY26AUG57000CE"]
    assert len(store.oi["NSE:BANKNIFTY26AUG57000CE"]) == 2


def test_fixed_prior_context_uses_canonical_discovery_and_hash_cache(tmp_path, monkeypatch):
    data = tmp_path / "collector"
    prior = ["2026-08-14", "2026-08-15", "2026-08-16", "2026-08-17", "2026-08-18"]
    for session in prior + [SESSION]:
        (data / "raw" / session).mkdir(parents=True)
        (data / "oi" / session).mkdir(parents=True)
        (data / "raw" / session / "events_09.jsonl").write_text(f"raw-{session}\n")
        (data / "oi" / session / "oi_09.jsonl").write_text(f"oi-{session}\n")
    runtime = contract(tmp_path)
    runtime["data_root"] = data
    calls = {"discover": 0, "loaded": []}

    def discover(_root, config):
        calls["discover"] += 1
        dates = [value for value in prior if config["discovery_start"] <= value <= config["discovery_end"]]
        return ([{"date": value, "status": "ACCEPTED", "reason": "FIXTURE"} for value in dates], dates)

    def load_oi(_root, session):
        calls["loaded"].append(session)
        return pd.DataFrame()

    def price_events(_market, session, *_args):
        return pd.DataFrame([{"px": 57000 + int(session[-2:]), "w": 10, "receipt_timestamp": pd.Timestamp(f"{session}T15:00:00+05:30"), "source_file": f"raw/{session}", "source_row": 1}])

    def oi_events(_oi, _market, session, *_args):
        return pd.DataFrame([{"family": family, "px": 57000 + int(session[-2:]), "w": 5, "receipt_timestamp": pd.Timestamp(f"{session}T15:00:01+05:30"), "source_file": f"oi/{session}", "source_row": number} for number, family in enumerate(orchestrator_module.inventory_engine.FAMILIES[1:], 1)])

    monkeypatch.setattr(orchestrator_module.inventory_engine, "discover_sessions", discover)
    monkeypatch.setattr(orchestrator_module.raw_reader, "load_oi", load_oi)
    monkeypatch.setattr(orchestrator_module.raw_reader, "select_contracts", lambda _oi, _session: (FUTURES, pd.Timestamp("2026-08-27").date(), pd.Timestamp("2026-08-27").date()))
    monkeypatch.setattr(orchestrator_module.raw_reader, "load_market", lambda *_args: pd.DataFrame())
    monkeypatch.setattr(orchestrator_module.inventory_engine, "price_events", price_events)
    monkeypatch.setattr(orchestrator_module.inventory_engine, "oi_events", oi_events)

    first = LiveAnalyticalOrchestrator(runtime)
    rows = first._fixed_inventory_rows(SESSION, FUTURES, pd.Timestamp("2026-08-27").date(), pd.Timestamp("2026-08-27").date())
    assert len(rows) == 21
    assert {row["horizon"] for row in rows} == {"1D", "2D", "3D"}
    assert first._fixed_cache_info[SESSION]["source_chain"] == ["2026-08-15", "2026-08-16", "2026-08-18"]
    assert first._fixed_cache_info[SESSION]["current_session_excluded"]
    assert first._fixed_cache_info[SESSION]["august_17_status"] == "PRESERVED_REJECTION"
    assert set(calls["loaded"]) == {"2026-08-15", "2026-08-16", "2026-08-18"}
    assert calls["discover"] == 1

    monkeypatch.setattr(orchestrator_module.inventory_engine, "discover_sessions", lambda *_args: (_ for _ in ()).throw(AssertionError("cache miss")))
    restarted = LiveAnalyticalOrchestrator(runtime)
    cached = restarted._fixed_inventory_rows(SESSION, FUTURES, pd.Timestamp("2026-08-27").date(), pd.Timestamp("2026-08-27").date())
    assert cached == rows
    assert restarted._fixed_cache_info[SESSION]["cache_hit"]


def test_callback_staging_is_durable_and_flushes_once(tmp_path, monkeypatch):
    rows = full_stack_fixture()[:12]
    staged = LiveAnalyticalOrchestrator(contract(tmp_path))
    for row in rows:
        staged.on_observation(row)
    assert staged.snapshot(SESSION, flush_dirty=False)["availability"]["overall_state"] == "NO_VALID_MARKET_DATA"

    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    calls = []
    original = restarted._compute_sessions
    monkeypatch.setattr(restarted, "_compute_sessions", lambda targets: (calls.append(set(targets)), original(targets))[1])
    restarted.flush()
    assert calls == [{SESSION}]
    assert restarted.snapshot(SESSION)["counts"]["observations"] == len(rows)


def test_stage_failure_before_write_remains_replayable_and_unaccepted(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    row = observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original = orchestrator_module.AppendOnlyLedger.append_many
    failed = False

    def fail_before_write(ledger, values):
        nonlocal failed
        if ledger.path.parent == orchestrator.stage_root and not failed:
            failed = True
            assert row["observation_id"] not in orchestrator._sessions.get(
                SESSION, {}
            )
            assert SESSION not in orchestrator._dirty_sessions
            raise RuntimeError("synthetic pre-write stage failure")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger, "append_many", fail_before_write
    )
    with pytest.raises(RuntimeError, match="synthetic pre-write stage failure"):
        orchestrator.process_observations([row])
    assert row["observation_id"] not in orchestrator._sessions.get(SESSION, {})
    assert SESSION not in orchestrator._dirty_sessions
    assert not (orchestrator.stage_root / f"{SESSION}.jsonl").exists()

    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process_observations([row])
    staged = orchestrator_module.AppendOnlyLedger(
        orchestrator.stage_root / f"{SESSION}.jsonl"
    ).rows()
    assert [value["observation_id"] for value in staged] == ["O0001"]
    assert row["observation_id"] in orchestrator._sessions[SESSION]
    assert SESSION in orchestrator._dirty_sessions
    orchestrator.flush()
    before = ledger_counts(orchestrator)
    orchestrator.process_observations([row])
    orchestrator.flush()
    assert ledger_counts(orchestrator) == before
    assert_unique_stage_and_publication_ids(orchestrator)


def test_stage_and_publication_failure_after_write_reconcile_exactly_once(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    row = observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original = orchestrator_module.AppendOnlyLedger.append_many
    stage_failed = False

    def fail_after_stage_write(ledger, values):
        nonlocal stage_failed
        if ledger.path.parent == orchestrator.stage_root and not stage_failed:
            stage_failed = True
            assert row["observation_id"] not in orchestrator._sessions.get(
                SESSION, {}
            )
            assert SESSION not in orchestrator._dirty_sessions
            original(ledger, values)
            assert row["observation_id"] not in orchestrator._sessions.get(
                SESSION, {}
            )
            assert SESSION not in orchestrator._dirty_sessions
            raise RuntimeError("synthetic post-write stage failure")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many",
        fail_after_stage_write,
    )
    with pytest.raises(RuntimeError, match="synthetic post-write stage failure"):
        orchestrator.process_observations([row])
    assert row["observation_id"] in orchestrator._sessions[SESSION]
    assert SESSION in orchestrator._dirty_sessions
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    assert row["observation_id"] in orchestrator._sessions[SESSION]
    assert SESSION in orchestrator._dirty_sessions
    orchestrator.process_observations([row])

    publication_failed = False

    def fail_after_publication_write(ledger, values):
        nonlocal publication_failed
        if (
            ledger.path.name == "availability_transitions.jsonl"
            and not publication_failed
        ):
            publication_failed = True
            original(ledger, values)
            raise RuntimeError("synthetic post-write publication failure")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many",
        fail_after_publication_write,
    )
    with pytest.raises(
        RuntimeError, match="synthetic post-write publication failure"
    ):
        orchestrator.flush()
    assert orchestrator._ledger_seen["availability_transitions"]
    orchestrator.flush()
    before = ledger_counts(orchestrator)
    orchestrator.process_observations([row])
    orchestrator.flush()
    assert ledger_counts(orchestrator) == before
    assert_unique_stage_and_publication_ids(orchestrator)


@pytest.mark.parametrize(
    "ledger_name",
    (
        "divergence_confirmations",
        "dependency_retriggers",
        "lifecycle_transitions",
        "inventory_winner_transitions",
        "participation_transitions",
        "cross_layer_transitions",
        "availability_transitions",
        "stale_recovery_transitions",
    ),
)
def test_every_material_ledger_reconciles_post_append_restart_exactly_once(
    tmp_path, monkeypatch, ledger_name,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    target = orchestrator.ledgers[ledger_name].path
    original = orchestrator_module.AppendOnlyLedger.append_many
    failed = False

    def fail_after_write(ledger, values):
        nonlocal failed
        if ledger.path == target and not failed:
            failed = True
            original(ledger, values)
            raise RuntimeError(f"synthetic {ledger_name} post-write failure")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger, "append_many", fail_after_write
    )
    row = {
        "session_date": SESSION,
        "effective_timestamp": "2026-08-20T10:00:00+05:30",
        "status": "MATERIAL",
    }
    with pytest.raises(RuntimeError, match=ledger_name):
        orchestrator._append_once(
            ledger_name, row, f"{ledger_name}:fixture", row["effective_timestamp"],
        )
    physical = orchestrator.ledgers[ledger_name].rows()
    assert len(physical) == 1
    event_id = physical[0]["event_id"]
    assert event_id in orchestrator._ledger_seen[ledger_name]

    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    restarted._append_once(
        ledger_name, row, f"{ledger_name}:fixture", row["effective_timestamp"],
    )
    replayed = restarted.ledgers[ledger_name].rows()
    assert [value["event_id"] for value in replayed] == [event_id]


def test_partial_multi_session_stage_retry_never_duplicates(tmp_path, monkeypatch):
    first_session = SESSION
    second_session = "2026-08-21"
    first = observation(
        "O0001", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    )
    second = observation(
        "O0002", "INDEX", INDEX,
        datetime(2026, 8, 21, 9, 15, tzinfo=IST), price=57_100, volume=0,
    )
    second.update({
        "session_date": second_session,
        "source_file": f"raw/{second_session}/focused_fixture.jsonl",
    })
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original = orchestrator_module.AppendOnlyLedger.append_many
    failed = False

    def fail_after_second_session(ledger, values):
        nonlocal failed
        if (
            ledger.path.parent == orchestrator.stage_root
            and ledger.path.stem == second_session
            and not failed
        ):
            failed = True
            assert "O0001" in orchestrator._sessions[first_session]
            assert "O0002" not in orchestrator._sessions.get(second_session, {})
            original(ledger, values)
            assert "O0002" not in orchestrator._sessions.get(second_session, {})
            raise RuntimeError("synthetic partial multi-session failure")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many",
        fail_after_second_session,
    )
    with pytest.raises(RuntimeError, match="partial multi-session failure"):
        orchestrator.process_observations([first, second])
    assert set(orchestrator._dirty_sessions) == {first_session, second_session}
    assert "O0001" in orchestrator._sessions[first_session]
    assert "O0002" in orchestrator._sessions[second_session]

    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    assert set(orchestrator._dirty_sessions) == {first_session, second_session}
    assert "O0001" in orchestrator._sessions[first_session]
    assert "O0002" in orchestrator._sessions[second_session]
    orchestrator.process_observations([first, second])
    assert {
        path.stem: len(orchestrator_module.AppendOnlyLedger(path).rows())
        for path in orchestrator.stage_root.glob("*.jsonl")
    } == {first_session: 1, second_session: 1}
    orchestrator.flush()
    before = ledger_counts(orchestrator)
    orchestrator.process_observations([first, second])
    orchestrator.flush()
    assert ledger_counts(orchestrator) == before
    assert_unique_stage_and_publication_ids(orchestrator)


def test_registered_callback_stages_linearly_until_explicit_snapshot(tmp_path, monkeypatch):
    rows = full_stack_fixture()[:24]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    calls = []
    order_key_calls = 0
    original = orchestrator._compute_sessions
    original_order_key = orchestrator._order_key

    def counted_order_key(row):
        nonlocal order_key_calls
        order_key_calls += 1
        return original_order_key(row)

    monkeypatch.setattr(
        orchestrator,
        "_compute_sessions",
        lambda targets: (calls.append(set(targets)), original(targets))[1],
    )
    monkeypatch.setattr(orchestrator, "_order_key", counted_order_key)
    for row in rows:
        orchestrator.process_observations([row])
    assert calls == []
    # A one-record increment may inspect that record while validating, sorting,
    # and accepting it, but must never rescan all prior session observations.
    assert order_key_calls <= 3 * len(rows)
    assert orchestrator._last_order_key[SESSION] == original_order_key(rows[-1])
    assert orchestrator.snapshot(SESSION, flush_dirty=False)["counts"]["observations"] == 0
    assert orchestrator.snapshot(SESSION)["counts"]["observations"] == len(rows)
    assert calls == [{SESSION}]


def test_callback_crash_after_durable_stage_replays_and_flushes_before_final_seal(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    data = tmp_path / "collector"
    session_root = data / "raw" / SESSION
    session_root.mkdir(parents=True)
    (data / "oi" / SESSION).mkdir(parents=True)
    runtime = contract(tmp_path)
    runtime.update({
        "data_root": data,
        "minimum_session_date": SESSION,
        "selected_futures_symbols": [FUTURES],
    })
    runtime["config"].update({
        "max_buffer_bytes_per_file": 1_048_576,
        "max_read_bytes_per_file_per_poll": 1_048_576,
    })
    records = []
    for offset, (symbol, price) in enumerate(
        ((INDEX, 57_000), (FUTURES, 57_020), (INDEX, 57_001), (FUTURES, 57_021))
    ):
        instant = base + timedelta(milliseconds=500 * offset)
        records.append(json.dumps({
            "received_at": instant.isoformat(),
            "event_time": instant.isoformat(),
            "message": {
                "symbol": symbol, "ltp": price, "vol_traded_today": offset,
            },
        }))
    (session_root / "events_09.jsonl").write_text("\n".join(records) + "\n")

    failed_ingestor = IncrementalJSONLIngestor(runtime)
    failed_orchestrator = LiveAnalyticalOrchestrator(
        runtime, failed_ingestor.ledgers
    )
    failed_ingestor.register_callback(failed_orchestrator)
    # Staging callbacks do not invoke the analytical batch primitives, so a
    # simulated compute failure remains dormant until an explicit seal.
    monkeypatch.setattr(
        failed_orchestrator,
        "_compute_sessions",
        lambda _targets: (_ for _ in ()).throw(RuntimeError("synthetic flush crash")),
    )
    committed = failed_ingestor.poll()
    assert len(committed) == 4
    assert failed_ingestor.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 0
    with pytest.raises(RuntimeError, match="synthetic flush crash"):
        failed_orchestrator.flush()
    failed_ingestor.close()

    restarted_ingestor = IncrementalJSONLIngestor(runtime)
    restarted_orchestrator = LiveAnalyticalOrchestrator(
        runtime, restarted_ingestor.ledgers
    )
    restarted_ingestor.register_callback(restarted_orchestrator)
    assert restarted_ingestor.poll() == []
    sealed = restarted_orchestrator.snapshot(SESSION)
    assert sealed["counts"]["observations"] == 4
    assert sealed["counts"]["basis"] == 2
    restarted_ingestor.close()


def test_basis_backward_asof_accepts_exact_2000ms_and_never_joins_future(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    rows = [
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation("O0002", "FUTURES", FUTURES, base, price=57_020, volume=1),
        observation(
            "O0003", "FUTURES", FUTURES,
            base + timedelta(milliseconds=2000), price=57_021, volume=2,
        ),
        observation(
            "O0004", "FUTURES", FUTURES,
            base + timedelta(microseconds=2_000_001), price=57_022, volume=3,
        ),
    ]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(rows)
    basis = orchestrator.snapshot(SESSION)["basis"]
    assert [row["validity_status"] for row in basis] == [
        "VALID", "VALID", "UNMATCHED_TOLERANCE_EXCEEDED",
    ]
    assert basis[0]["absolute_receipt_difference_ms"] == 0
    assert basis[1]["absolute_receipt_difference_ms"] == 2000
    assert orchestrator.causality_metrics() == {
        "valid_basis_pairs": 2,
        "future_joins": 0,
        "synchronization_tolerance_violations": 0,
    }


def test_empty_poll_wall_clock_staleness_is_material_and_not_backdated(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    assert orchestrator.snapshot(SESSION)["availability"]["layers"]["ID"]["state"] == "AVAILABLE"
    stale_at = base + timedelta(seconds=20)
    assert orchestrator.refresh_staleness(stale_at)
    stale = orchestrator.snapshot(SESSION, flush_dirty=False)["availability"]
    assert stale["layers"]["ID"]["state"] == "STALE_DATA"
    assert stale["divergence_state"] == "STALE_DATA"
    assert stale["reference_timestamp"] == stale_at.isoformat()
    assert stale["calculation_timestamp"] == stale_at.isoformat()
    assert not orchestrator.refresh_staleness(stale_at + timedelta(seconds=1))
    rows = orchestrator.ledgers["stale_recovery_transitions"].rows()
    assert rows
    assert all(
        parse_timestamp(row["publication_timestamp"])
        >= parse_timestamp(row["effective_timestamp"])
        for row in rows
    )


def test_outputs_only_historical_preload_is_stale_for_live_latest(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    sealed = orchestrator.snapshot(SESSION)
    assert sealed["availability"]["divergence_state"] == "AVAILABLE"
    assert sealed["gui_payload"]["counts"]["price"] == 1
    explicit_reference = base + timedelta(seconds=5)
    current = orchestrator.operational_availability(explicit_reference)
    assert current["reference_timestamp"] == explicit_reference.isoformat()
    assert current["calculation_timestamp"] == explicit_reference.isoformat()
    orchestrator._sessions.clear()
    orchestrator._last_order_key.clear()

    operational = orchestrator.operational_availability(
        datetime(2026, 8, 26, 18, 0, tzinfo=IST)
    )
    assert operational["overall_state"] == "STALE_PARTIAL"
    assert operational["layers"]["ID"]["state"] == "STALE_DATA"
    assert operational["divergence_state"] == "STALE_DATA"
    assert operational["index_state"] == "STALE_OR_MISSING"
    assert operational["futures_state"] == "STALE_OR_MISSING"
    assert operational["market_display_enabled"] is True
    assert operational["calculation_timestamp"] == (
        "2026-08-26T18:00:00+05:30"
    )
    assert orchestrator.snapshot(SESSION, flush_dirty=False)["gui_payload"] == (
        sealed["gui_payload"]
    )


def test_finalized_session_compacts_raw_bucket_without_restart_reload(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    rows = [
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(rows)
    sealed = orchestrator.finalize_session(SESSION)
    assert sealed["counts"]["observations"] == 2
    assert SESSION not in orchestrator._sessions
    assert SESSION not in orchestrator._last_order_key
    assert SESSION not in orchestrator._dirty_sessions
    assert SESSION not in orchestrator._stage_seen
    assert len(orchestrator_module.AppendOnlyLedger(
        orchestrator.stage_root / f"{SESSION}.jsonl"
    ).rows()) == 2

    stage_reads = []
    original = LiveAnalyticalOrchestrator._read_unique_staged_rows
    monkeypatch.setattr(
        LiveAnalyticalOrchestrator,
        "_read_unique_staged_rows",
        lambda self, session: (
            stage_reads.append(session), original(self, session)
        )[1],
    )
    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    assert SESSION not in stage_reads
    assert SESSION not in restarted._sessions
    assert SESSION not in restarted._stage_seen
    assert restarted.snapshot(SESSION, flush_dirty=False) == sealed
    restarted.process(rows)
    assert SESSION not in restarted._sessions
    assert len(orchestrator_module.AppendOnlyLedger(
        restarted.stage_root / f"{SESSION}.jsonl"
    ).rows()) == 2
    assert {
        row["reason"]
        for row in restarted.ledgers["refusals_data_quality"].rows()
    } == {"FINALIZED_SESSION_RECEIPT"}


def test_verified_replay_outputs_survive_more_than_rolling_live_window(tmp_path):
    runtime = contract(tmp_path)
    runtime["config"]["max_live_sessions"] = 32
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    verified = list(orchestrator_module.gui_adapter.SESSIONS)
    later = [
        value.date().isoformat()
        for value in pd.date_range("2026-08-26", periods=33, freq="D")
    ]
    for session in verified + later:
        output = orchestrator._empty_snapshot(session)
        output["gui_payload"] = {
            "date": session, "projection_hash": f"projection-{session}",
        }
        orchestrator._outputs[session] = output
        orchestrator._finalized_sessions.add(session)
    orchestrator._evict_sessions()
    orchestrator._persist()

    restarted = LiveAnalyticalOrchestrator(runtime)
    available = restarted.snapshot_all(flush_dirty=False)
    assert set(verified).issubset(available)
    assert set(later[-32:]).issubset(available)
    assert later[0] not in available
    assert len(available) == len(verified) + 32


def test_null_futures_price_does_not_report_market_ready(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=None, volume=100,
        ),
    ])
    availability = orchestrator.snapshot(SESSION)["availability"]
    assert availability["layers"]["ID"]["state"] == "STALE_DATA"
    assert availability["futures_state"] == "STALE_OR_MISSING"
    assert availability["divergence_state"] == "STALE_DATA"


def test_operational_state_reads_never_trigger_dirty_analytical_flush(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    orchestrator.process_observations([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    calls = []
    original = orchestrator._compute_sessions
    monkeypatch.setattr(
        orchestrator,
        "_compute_sessions",
        lambda targets: (calls.append(set(targets)), original(targets))[1],
    )
    ingestor = SimpleNamespace(
        latest={}, latest_valid={}, metrics={},
        c={**runtime, "raw_run_id": "RAW-RUN"},
    )
    state = ShadowState(ingestor, {}, orchestrator)
    for _ in range(3):
        state.analytical_snapshot()
        state.availability()
        state.status()
    assert calls == []
    orchestrator.flush()
    assert calls == [{SESSION}]


def test_promoted_breadth_primitive_preserves_frozen_rows():
    options = [
        {"episode_id": "E1", "observation_timestamp": "2026-08-20T10:00:00+05:30", "option_type": "CE", "moneyness": "ATM", "semantic_classification": "SUPPORTIVE"},
        {"episode_id": "E1", "observation_timestamp": "2026-08-20T10:00:00+05:30", "option_type": "PE", "moneyness": "OTM", "semantic_classification": "CONTRADICTORY"},
    ]
    assert participation_views.breadth(options) == [{
        "episode_id": "E1", "observation_timestamp": "2026-08-20T10:00:00+05:30",
        "selected_strike_count": 2, "ce_strike_count": 1, "pe_strike_count": 1,
        "atm_count": 1, "otm_count": 1, "supportive_count": 1,
        "contradictory_count": 1, "mixed": True, "broad_agreement": False,
        "ce_pe_agreement": False,
    }]
