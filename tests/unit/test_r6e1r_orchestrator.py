from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from banknifty_profiler.participation import views as participation_views
from banknifty_profiler.cross_layer.state import build_material_transitions
from banknifty_profiler.shadow import ledger as ledger_module
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


def independent_confirmation_fixture() -> list[dict]:
    """Extend the GREEN fixture through an unresolved then confirmed RED run."""
    rows = full_stack_fixture()
    base = datetime(2026, 8, 20, 9, 23, 10, tzinfo=IST)
    ordinal = len(rows)
    for step in range(16):
        instant = base + timedelta(seconds=10 * step)
        ordinal += 1
        rows.append(observation(
            f"O{ordinal:04d}", "INDEX", INDEX, instant,
            price=56_952 + 2 * (step + 1), volume=0,
        ))
        ordinal += 1
        rows.append(observation(
            f"O{ordinal:04d}", "FUTURES", FUTURES,
            instant + timedelta(milliseconds=500),
            price=57_024.8 - .2 * (step + 1),
            volume=345 + 5 * (step + 1),
        ))
    return rows


def provisional_expiration_fixture() -> tuple[list[dict], dict]:
    """Expose a terminal expiration before a later standalone Index response."""
    rows = full_stack_fixture()
    shift = timedelta(hours=6, minutes=5)
    for row in rows:
        for field in ("receipt_timestamp", "exchange_timestamp"):
            row[field] = (
                datetime.fromisoformat(row[field]) + shift
            ).isoformat()

    ordinal = len(rows)

    def add(instrument, symbol, instant, **values):
        nonlocal ordinal
        ordinal += 1
        rows.append(observation(
            f"O{ordinal:04d}", instrument, symbol, instant, **values,
        ))

    # These constituent receipts fall after the last stable lifecycle state.
    # They are admitted only while the 15:30 expiration extends the live
    # participation window.
    add(
        "FUTURES_OI", FUTURES,
        datetime(2026, 8, 20, 15, 29, 30, tzinfo=IST),
        price=57_025, volume=900, oi=3_000, expiry="2026-08-27",
    )
    add(
        "CE", "NSE:BANKNIFTY26AUG57000CE",
        datetime(2026, 8, 20, 15, 29, 30, 100_000, tzinfo=IST),
        price=240, volume=500, oi=2_500, strike=57_000,
        expiry="2026-08-27",
    )
    add(
        "PE", "NSE:BANKNIFTY26AUG57000PE",
        datetime(2026, 8, 20, 15, 30, tzinfo=IST),
        price=140, volume=600, oi=2_600, strike=57_000,
        expiry="2026-08-27",
    )
    late_index = observation(
        f"O{ordinal + 1:04d}", "INDEX", INDEX,
        datetime(2026, 8, 20, 15, 31, tzinfo=IST),
        price=56_975, volume=0,
    )
    return rows, late_index


def ledger_counts(orchestrator: LiveAnalyticalOrchestrator) -> dict[str, int]:
    return {name: len(ledger.rows()) for name, ledger in orchestrator.ledgers.items()}


def material_ledger_fixture(ledger_name: str) -> dict:
    instant = "2026-08-20T10:00:00+05:30"
    return {
        "divergence_confirmations": {
            "episode_id": "BDR1-FIXTURE", "evaluation_date": SESSION,
            "candidate_start_timestamp": instant,
            "confirmation_timestamp": instant,
            "index_receipt_timestamp": instant,
            "futures_receipt_timestamp": instant, "colour": "GREEN",
            "index_at_confirmation": 57_000,
            "futures_at_confirmation": 57_020,
            "basis_at_confirmation": 20,
        },
        "dependency_retriggers": {
            "episode_id": "BDR1-FIXTURE",
            "dependency_group_id": "HYP-FIXTURE",
            "root_episode_id": "BDR1-FIXTURE",
            "classification": "NEW_INDEPENDENT_HYPOTHESIS",
            "reason_code": "FIRST_SESSION_EPISODE", "member_number": 1,
            "previous_episode_id": "", "gap_seconds": None,
            "favourable_response_before_retrigger": False,
            "adverse_response_before_retrigger": False,
            "opposite_episode_before_retrigger": False,
            "previous_hypothesis_resolved": True,
            "retrigger_flag": False,
        },
        "lifecycle_transitions": {
            "record_id": "R6B2R-FIXTURE", "episode_id": "BDR1-FIXTURE",
            "dependency_group_id": "HYP-FIXTURE",
            "evaluation_date": SESSION, "state": "DIVERGENCE_DETECTED",
            "colour": "GREEN",
            "previous_state": "NOT_YET_DETECTED",
            "reason_code": "RAW_LOCKED_CONFIRMATION",
            "state_entry_timestamp": instant, "causal_input_cutoff": instant,
        },
        "inventory_winner_transitions": {
            "evaluation_date": SESSION, "horizon": "ID",
            "family": "BN_REF_FUT_VOLUME_VPOC", "control_value": 57_000,
            "sign": "VOLUME", "source_sessions": SESSION,
            "control_effective_timestamp": instant,
            "winner_change_timestamp": instant, "snapshot_timestamp": "",
            "freshness_receipt_timestamp": instant,
            "last_contributing_change_timestamp": instant,
            "contract": FUTURES, "expiry": "2026-08-27",
            "eligible_observation_count": 1, "excluded_observation_count": 0,
            "winning_bin_weight": 1.0, "runner_up_bin": "",
            "runner_up_weight": "", "tie_break_reason": "NO_TIE",
            "methodology_version": "INVENTORY_V2_BN_REF_RAW_CAUSAL",
            "raw_input_hashes": "RECORDED_IN_FILE_OPEN_AUDIT",
            "authority_basis": "RAW_CAUSAL_BANKNIFTY_REFERENCE",
            "canonical_control_name": "BN_REF_FUT_VOLUME_VPOC",
            "user_facing_label": "BN-REF FUT VOL-VPOC",
            "canonical_revision": (
                "INVENTORY_CANONICAL_REVISION_2_BN_REFERENCE_RAW_CAUSAL"
            ),
        },
        "participation_transitions": {
            "transition_id": "R6B3R-FIXTURE", "episode_id": "BDR1-FIXTURE",
            "component": "FUTURES", "previous_state": "UNOBSERVED",
            "new_state": "AVAILABLE", "reason_code": "MATERIAL_CHANGE",
            "dependency_group_id": "HYP-FIXTURE",
            "constituent_effective_timestamps": json.dumps({
                "futures": instant
            }),
            "raw_source_references": "raw/fixture.jsonl:1",
            "effective_timestamp": instant,
            "evidence_receipt_timestamp": instant,
        },
        "cross_layer_transitions": {
            "transition_id": "XL-FIXTURE", "source_record_id": "SOURCE-1",
            "evaluation_date": SESSION, "component": "INVENTORY",
            "state_key": "ID:BN_REF_FUT_VOLUME_VPOC",
            "previous_state": "NOT_YET_AVAILABLE", "new_state": "AVAILABLE",
            "reason_code": "CONTROL_AVAILABLE_OR_WINNER_CHANGED",
            "constituent_effective_timestamps": json.dumps({
                "control_effective_timestamp": instant
            }),
            "episode_id": "", "horizon": "ID",
            "family": "BN_REF_FUT_VOLUME_VPOC",
            "effective_timestamp": instant,
        },
        "availability_transitions": {
            "session_date": SESSION, "component": "INDEX_STATE",
            "previous_state": "NOT_YET_AVAILABLE", "new_state": "AVAILABLE",
            "reason": "MATERIAL_AVAILABILITY_CHANGE",
            "effective_timestamp": instant,
        },
        "stale_recovery_transitions": {
            "session_date": SESSION, "component": "INDEX_STATE",
            "previous_state": "STALE", "new_state": "AVAILABLE",
            "reason": "MATERIAL_AVAILABILITY_CHANGE",
            "effective_timestamp": instant,
        },
    }[ledger_name]


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


def persist_one_mutable_session(
    tmp_path: Path,
) -> tuple[LiveAnalyticalOrchestrator, dict]:
    instant = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    row = observation(
        "O0001", "INDEX", INDEX, instant, price=57_000, volume=0,
    )
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([row])
    orchestrator.flush()
    assert orchestrator.state_path.is_file()
    assert (orchestrator.stage_root / f"{SESSION}.jsonl").is_file()
    return orchestrator, row


def test_sealed_read_view_is_stable_across_copy_on_write_publication(
    tmp_path, monkeypatch,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    first = orchestrator._empty_snapshot(SESSION)
    first["generation"] = "first"
    orchestrator._outputs = {SESSION: first}
    orchestrator._dirty_sessions.add(SESSION)
    monkeypatch.setattr(
        orchestrator,
        "flush",
        lambda *_args, **_kwargs: pytest.fail(
            "sealed read view attempted analytical work"
        ),
    )

    view = orchestrator.sealed_read_view(SESSION)
    assert view["generation"] == "first"
    assert view["inventory"] is first["inventory"]
    with pytest.raises(TypeError):
        view["generation"] = "mutated"

    second = orchestrator._empty_snapshot(SESSION)
    second["generation"] = "second"
    orchestrator._outputs = {SESSION: second}

    assert view["generation"] == "first"
    assert orchestrator.sealed_read_view(SESSION)["generation"] == "second"
    assert orchestrator.sealed_session_dates() == (SESSION,)


def test_restart_compacts_legacy_dense_gui_resolution_projection(tmp_path):
    runtime = contract(tmp_path)
    first = LiveAnalyticalOrchestrator(runtime)
    output = first._empty_snapshot(SESSION)
    fields = [
        "episode_id", "timestamp", "resolution_mechanism_native",
    ]
    output["gui_payload"] = {
        "schema": "R6E_LIVE_SESSION_PAYLOAD_V1",
        "date": SESSION,
        "resolution_mechanisms": {
            "fields": fields,
            "rows": [
                ["E1", f"{SESSION}T09:15:00+05:30", "PENDING"],
                ["E1", f"{SESSION}T09:15:01+05:30", "PENDING"],
                ["E1", f"{SESSION}T09:15:02+05:30", "BASIS_CONVERGENCE"],
            ],
        },
        "counts": {"resolution_mechanisms": 3},
        "projection_hash": "legacy-dense-projection",
    }
    first._outputs = {SESSION: output}
    first._sessions = {SESSION: {}}
    first._persist()

    restarted = LiveAnalyticalOrchestrator(runtime)
    gui = restarted.sealed_read_view(SESSION)["gui_payload"]
    assert gui["resolution_mechanisms"]["rows"] == [
        ["E1", f"{SESSION}T09:15:00+05:30", "PENDING"],
        ["E1", f"{SESSION}T09:15:02+05:30", "BASIS_CONVERGENCE"],
    ]
    assert gui["counts"]["resolution_mechanisms"] == 2
    assert gui["projection_hash"] != "legacy-dense-projection"


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


def test_periodic_flush_keeps_mutable_closure_fields_out_of_event_ledgers(
    tmp_path,
):
    rows = full_stack_fixture()
    incremental = LiveAnalyticalOrchestrator(contract(tmp_path / "incremental"))
    incremental.process(rows[:95])
    early = incremental.snapshot(SESSION)
    assert early["counts"]["episodes"] == 1
    assert early["counts"]["lifecycle"] == 1
    assert early["lifecycle"][0]["state_exit_timestamp"] == ""

    first_end = early["episodes"][0]["episode_end_timestamp"]
    incremental.process(rows[95:])
    final = incremental.snapshot(SESSION)
    assert final["episodes"][0]["episode_end_timestamp"] > first_end
    assert final["lifecycle"][0]["state_exit_timestamp"]
    assert all(
        "episode_end_timestamp" not in row
        for row in incremental.ledgers["divergence_confirmations"].rows()
    )
    assert all(
        "state_exit_timestamp" not in row
        for row in incremental.ledgers["lifecycle_transitions"].rows()
    )

    one_shot = LiveAnalyticalOrchestrator(contract(tmp_path / "one-shot"))
    one_shot.process(rows)
    expected = one_shot.snapshot(SESSION)
    assert final["episodes"] == expected["episodes"]
    assert final["lifecycle"] == expected["lifecycle"]
    for name in ("divergence_confirmations", "lifecycle_transitions"):
        actual_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in incremental.ledgers[name].rows()
        )
        expected_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in one_shot.ledgers[name].rows()
        )
        assert actual_rows == expected_rows
    assert_unique_stage_and_publication_ids(incremental)


def test_provisional_expiration_and_linked_rows_publish_only_if_sealed(
    tmp_path,
):
    prefix, late_index = provisional_expiration_fixture()
    periodic = LiveAnalyticalOrchestrator(contract(tmp_path / "periodic"))
    periodic.process(prefix)
    provisional = periodic.snapshot(SESSION)

    expiration = next(
        row for row in provisional["lifecycle"]
        if row["state"] == "EXPIRED_OR_UNRESOLVED"
        and row["reason_code"]
        == "LIFECYCLE_END_WITHOUT_FAVOURABLE_RESPONSE"
    )
    episode_id = expiration["episode_id"]
    provisional_participation_ids = {
        row["transition_id"]
        for row in provisional["participation_transitions"]
        if row["episode_id"] == episode_id
    }
    assert provisional_participation_ids
    provisional_source_ids = {
        expiration["record_id"],
    } | provisional_participation_ids
    provisional_linked_cross_ids = {
        row["transition_id"]
        for row in provisional["cross_layer_transitions"]
        if row["source_record_id"] in provisional_source_ids
    }
    assert provisional_linked_cross_ids
    assert expiration["record_id"] not in {
        row["record_id"]
        for row in periodic.ledgers["lifecycle_transitions"].rows()
    }
    assert not provisional_participation_ids & {
        row["transition_id"]
        for row in periodic.ledgers["participation_transitions"].rows()
    }
    assert not provisional_linked_cross_ids & {
        row["transition_id"]
        for row in periodic.ledgers["cross_layer_transitions"].rows()
    }

    periodic.process([late_index])
    final = periodic.snapshot(SESSION)
    assert final["responses"] == [{
        "episode_id": episode_id,
        "first_favourable_timestamp": "2026-08-20T15:31:00+05:30",
        "first_adverse_timestamp": "2026-08-20T15:27:40+05:30",
        "ordering": "ADVERSE_FIRST",
    }]
    assert expiration["record_id"] not in {
        row["record_id"] for row in final["lifecycle"]
    }
    final_participation_ids = {
        row["transition_id"] for row in final["participation_transitions"]
    }
    disappeared_participation_ids = (
        provisional_participation_ids - final_participation_ids
    )
    assert len(disappeared_participation_ids) == 6
    last_stable_lifecycle_entry = max(
        row["state_entry_timestamp"]
        for row in provisional["lifecycle"]
        if row["record_id"] != expiration["record_id"]
    )
    assert all(
        row["effective_timestamp"] > last_stable_lifecycle_entry
        for row in provisional["participation_transitions"]
        if row["transition_id"] in disappeared_participation_ids
    )
    final_cross_ids = {
        row["transition_id"] for row in final["cross_layer_transitions"]
    }
    disappeared_cross_ids = provisional_linked_cross_ids - final_cross_ids
    assert len(disappeared_cross_ids) == 7
    assert not disappeared_participation_ids & {
        row["transition_id"]
        for row in periodic.ledgers["participation_transitions"].rows()
    }
    assert not disappeared_cross_ids & {
        row["transition_id"]
        for row in periodic.ledgers["cross_layer_transitions"].rows()
    }
    periodic.finalize_session(SESSION)

    one_shot = LiveAnalyticalOrchestrator(contract(tmp_path / "one-shot"))
    one_shot.process([*prefix, late_index])
    expected = one_shot.finalize_session(SESSION)
    for artifact in (
        "lifecycle", "participation_transitions", "cross_layer_transitions",
    ):
        assert final[artifact] == expected[artifact]

    material_ledgers = tuple(
        name for name in orchestrator_module.LEDGER_NAMES
        if name != "refusals_data_quality"
    )
    assert len(material_ledgers) == 8
    for name in material_ledgers:
        actual_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in periodic.ledgers[name].rows()
        )
        expected_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in one_shot.ledgers[name].rows()
        )
        assert actual_rows == expected_rows, name
    sealed = LiveAnalyticalOrchestrator(contract(tmp_path / "sealed"))
    sealed.process(prefix)
    sealed.finalize_session(SESSION)
    assert expiration["record_id"] in {
        row["record_id"]
        for row in sealed.ledgers["lifecycle_transitions"].rows()
    }
    assert provisional_participation_ids <= {
        row["transition_id"]
        for row in sealed.ledgers["participation_transitions"].rows()
    }
    assert provisional_linked_cross_ids <= {
        row["transition_id"]
        for row in sealed.ledgers["cross_layer_transitions"].rows()
    }
    for orchestrator in (periodic, one_shot, sealed):
        assert all(
            "episode_end_timestamp" not in row
            for row in orchestrator.ledgers[
                "divergence_confirmations"
            ].rows()
        )
        assert all(
            "state_exit_timestamp" not in row
            for row in orchestrator.ledgers["lifecycle_transitions"].rows()
        )
        assert_unique_stage_and_publication_ids(orchestrator)


def test_unconfirmed_candidate_defers_terminal_group_publication(
    tmp_path,
):
    rows = independent_confirmation_fixture()
    periodic = LiveAnalyticalOrchestrator(contract(tmp_path / "periodic"))
    periodic.process(rows[:155])
    provisional = periodic.snapshot(SESSION)

    assert len(provisional["episodes"]) == 1
    terminal_group = provisional["dependencies"][-1]["dependency_group_id"]
    candidate_start = "2026-08-20T09:24:40.500000+05:30"
    unstable_lifecycle_ids = {
        row["record_id"] for row in provisional["lifecycle"]
        if row["dependency_group_id"] == terminal_group
        and row["state_entry_timestamp"] > candidate_start
    }
    assert unstable_lifecycle_ids
    assert provisional["gui_payload"]["lifecycle"]["rows"]
    assert periodic._pending_unstable_dependency_groups == {
        SESSION: terminal_group
    }
    assert len(periodic.ledgers["divergence_confirmations"].rows()) == 1
    assert len(periodic.ledgers["dependency_retriggers"].rows()) == 1
    assert not periodic.ledgers["lifecycle_transitions"].rows()
    assert not periodic.ledgers["participation_transitions"].rows()
    assert not [
        row for row in periodic.ledgers["cross_layer_transitions"].rows()
        if row.get("episode_id")
    ]

    periodic.process(rows[155:])
    final = periodic.snapshot(SESSION)
    assert len(final["episodes"]) == 2
    assert len({
        row["dependency_group_id"] for row in final["dependencies"]
    }) == 2
    assert not unstable_lifecycle_ids & {
        row["record_id"] for row in final["lifecycle"]
    }

    one_shot = LiveAnalyticalOrchestrator(contract(tmp_path / "one-shot"))
    one_shot.process(rows)
    expected = one_shot.snapshot(SESSION)
    assert final["lifecycle"] == expected["lifecycle"]
    assert final["participation_transitions"] == expected[
        "participation_transitions"
    ]
    assert final["cross_layer_transitions"] == expected[
        "cross_layer_transitions"
    ]
    for name in (
        "divergence_confirmations", "dependency_retriggers",
        "lifecycle_transitions", "participation_transitions",
        "cross_layer_transitions",
    ):
        actual_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in periodic.ledgers[name].rows()
        )
        expected_rows = sorted(
            orchestrator_module._material_ledger_content(name, row)
            for row in one_shot.ledgers[name].rows()
        )
        assert actual_rows == expected_rows
    assert_unique_stage_and_publication_ids(periodic)


def test_finalize_releases_deferred_group_after_restart_failure_exactly_once(
    tmp_path, monkeypatch,
):
    rows = independent_confirmation_fixture()[:155]
    root = tmp_path / "deferred-restart"
    orchestrator = LiveAnalyticalOrchestrator(contract(root))
    orchestrator.process(rows)
    provisional = orchestrator.snapshot(SESSION)
    assert provisional["lifecycle"]
    assert not orchestrator.ledgers["lifecycle_transitions"].rows()

    restarted = LiveAnalyticalOrchestrator(contract(root))
    original_append = orchestrator_module.AppendOnlyLedger.append_many
    failed = False

    def fail_after_deferred_write(ledger, values):
        nonlocal failed
        if (
            ledger.path.name == "lifecycle_transitions.jsonl"
            and not failed
        ):
            failed = True
            original_append(ledger, values)
            raise RuntimeError("synthetic deferred publication failure")
        return original_append(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many",
        fail_after_deferred_write,
    )
    with pytest.raises(
        RuntimeError, match="synthetic deferred publication failure"
    ):
        restarted.finalize_session(SESSION)
    assert SESSION not in restarted._finalized_sessions

    recovered = LiveAnalyticalOrchestrator(contract(root))
    recovered.finalize_session(SESSION)
    before = ledger_counts(recovered)
    recovered.finalize_session(SESSION)
    assert ledger_counts(recovered) == before
    assert len(recovered.ledgers["lifecycle_transitions"].rows()) == len(
        provisional["lifecycle"]
    )
    assert len(recovered.ledgers["participation_transitions"].rows()) == len(
        provisional["participation_transitions"]
    )
    assert len([
        row for row in recovered.ledgers["cross_layer_transitions"].rows()
        if row.get("episode_id")
    ]) == len([
        row for row in provisional["cross_layer_transitions"]
        if row.get("episode_id")
    ])
    assert_unique_stage_and_publication_ids(recovered)


def test_periodic_and_one_shot_publish_same_sealed_availability_events(
    tmp_path,
):
    rows = full_stack_fixture()
    periodic = LiveAnalyticalOrchestrator(contract(tmp_path / "periodic"))
    periodic.process(rows[:95])
    periodic.snapshot(SESSION)
    periodic.process(rows[95:])
    periodic.snapshot(SESSION)
    assert periodic.ledgers["availability_transitions"].rows() == []
    periodic_final = periodic.finalize_session(SESSION)

    one_shot = LiveAnalyticalOrchestrator(contract(tmp_path / "one-shot"))
    one_shot.process(rows)
    one_shot_final = one_shot.finalize_session(SESSION)
    assert {
        key: value for key, value in periodic_final["availability"].items()
        if key != "calculation_timestamp"
    } == {
        key: value for key, value in one_shot_final["availability"].items()
        if key != "calculation_timestamp"
    }

    runtime_fields = {
        "publication_timestamp", "calculation_timestamp", "raw_run_id",
    }
    for ledger_name in (
        "availability_transitions", "stale_recovery_transitions",
    ):
        periodic_rows = [
            {key: value for key, value in row.items() if key not in runtime_fields}
            for row in periodic.ledgers[ledger_name].rows()
        ]
        one_shot_rows = [
            {key: value for key, value in row.items() if key not in runtime_fields}
            for row in one_shot.ledgers[ledger_name].rows()
        ]
        assert periodic_rows == one_shot_rows
    availability_rows = periodic.ledgers["availability_transitions"].rows()
    assert len(availability_rows) == 12
    assert all(
        row["reason"] == "SESSION_AVAILABILITY_SEAL"
        and row["effective_timestamp"]
        == periodic_final["availability"]["evidence_cutoff_timestamp"]
        for row in availability_rows
    )


@pytest.mark.parametrize(
    ("ledger_name", "identity", "row", "mutable_field", "stable_field"),
    (
        (
            "divergence_confirmations",
            "BDR1-2026-08-20-GREEN-001",
            {
                **material_ledger_fixture("divergence_confirmations"),
                "episode_id": "BDR1-2026-08-20-GREEN-001",
                "episode_end_timestamp": "2026-08-20T10:01:00+05:30",
            },
            "episode_end_timestamp",
            "colour",
        ),
        (
            "lifecycle_transitions",
            "R6B2R-IMMUTABLE-ONE",
            {
                **material_ledger_fixture("lifecycle_transitions"),
                "record_id": "R6B2R-IMMUTABLE-ONE",
                "state_exit_timestamp": "",
            },
            "state_exit_timestamp",
            "reason_code",
        ),
    ),
)
def test_same_material_identity_requires_same_immutable_content(
    tmp_path, ledger_name, identity, row, mutable_field, stable_field,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    calculation = "2026-08-20T10:02:00+05:30"
    orchestrator._append_once(ledger_name, row, identity, calculation)

    closure_update = dict(row)
    closure_update[mutable_field] = "2026-08-20T10:03:00+05:30"
    orchestrator._append_once(
        ledger_name, closure_update, identity, calculation
    )
    physical = orchestrator.ledgers[ledger_name].rows()
    assert len(physical) == 1
    assert mutable_field not in physical[0]

    conflict = dict(closure_update)
    conflict[stable_field] = "DIFFERENT_STABLE_CONTENT"
    with pytest.raises(ValueError, match="different immutable content"):
        orchestrator._append_once(
            ledger_name, conflict, identity, calculation
        )
    assert orchestrator.ledgers[ledger_name].rows() == physical


def test_duplicate_physical_material_identity_is_refused_at_startup(tmp_path):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    row = material_ledger_fixture("divergence_confirmations")
    row["episode_id"] = "BDR1-2026-08-20-GREEN-001"
    identity = "BDR1-2026-08-20-GREEN-001"
    orchestrator._append_once(
        "divergence_confirmations", row, identity,
        "2026-08-20T10:00:00+05:30",
    )
    ledger = orchestrator.ledgers["divergence_confirmations"]
    ledger.append(ledger.rows()[0])

    with pytest.raises(ValueError, match="duplicate physical event identity"):
        LiveAnalyticalOrchestrator(runtime)


@pytest.mark.parametrize("ledger_name", orchestrator_module.LEDGER_NAMES)
def test_material_startup_refuses_schema_empty_unique_event(
    tmp_path, ledger_name,
):
    runtime = contract(tmp_path)
    ledger = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"] / "ledgers" / f"{ledger_name}.jsonl"
    )
    ledger.append({"event_id": "MALFORMED-BUT-UNIQUE"})

    with pytest.raises(ValueError, match=f"append-only {ledger_name} row 1"):
        LiveAnalyticalOrchestrator(runtime)


def test_divergence_startup_refuses_naive_candidate_timestamp(tmp_path):
    builder = LiveAnalyticalOrchestrator(contract(tmp_path / "builder"))
    builder._append_once(
        "divergence_confirmations",
        material_ledger_fixture("divergence_confirmations"),
        "BDR1-CANDIDATE-CLOCK",
        "2026-08-20T10:00:00+05:30",
    )
    row = dict(builder.ledgers["divergence_confirmations"].rows()[0])
    row["candidate_start_timestamp"] = "2026-08-20T09:55:00"

    runtime = contract(tmp_path / "target")
    ledger = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"]
        / "ledgers"
        / "divergence_confirmations.jsonl"
    )
    ledger.append(row)
    with pytest.raises(
        ValueError, match="timezone-aware candidate_start_timestamp"
    ):
        LiveAnalyticalOrchestrator(runtime)


@pytest.mark.parametrize("provenance", ("missing", "UNKNOWN"))
def test_orchestrator_refusal_startup_requires_timestamp_provenance(
    tmp_path, provenance,
):
    builder = LiveAnalyticalOrchestrator(contract(tmp_path / "builder"))
    builder._quality(
        {
            "observation_id": "O-BUILD-REFUSAL",
            "session_date": SESSION,
            "receipt_timestamp": "2026-08-20T10:00:00+05:30",
            "source_file": f"raw/{SESSION}/events_10.jsonl",
            "source_byte_offset": 0,
            "source_row_number": 1,
        },
        "SYNTHETIC_REFUSAL",
        "fixture",
    )
    row = dict(builder.ledgers["refusals_data_quality"].rows()[0])
    if provenance == "missing":
        row.pop("effective_timestamp_provenance")
    else:
        row["effective_timestamp_provenance"] = provenance

    runtime = contract(tmp_path / "target")
    ledger = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"]
        / "ledgers"
        / "refusals_data_quality.jsonl"
    )
    ledger.append(row)
    with pytest.raises(
        ValueError, match="invalid effective_timestamp_provenance"
    ):
        LiveAnalyticalOrchestrator(runtime)


@pytest.mark.parametrize(
    ("field", "value"),
    (("file", None), ("byte_offset", True), ("source_row", -1)),
)
def test_orchestrator_refusal_startup_requires_source_coordinates(
    tmp_path, field, value,
):
    builder = LiveAnalyticalOrchestrator(contract(tmp_path / "builder"))
    builder._quality(
        {
            "observation_id": "O-BUILD-COORDINATES",
            "session_date": SESSION,
            "receipt_timestamp": "2026-08-20T10:00:00+05:30",
            "source_file": f"raw/{SESSION}/events_10.jsonl",
            "source_byte_offset": 0,
            "source_row_number": 1,
        },
        "SYNTHETIC_REFUSAL",
        "fixture",
    )
    row = dict(builder.ledgers["refusals_data_quality"].rows()[0])
    if value is None:
        row["source_receipt_identifiers"].pop(field)
    else:
        row["source_receipt_identifiers"][field] = value

    runtime = contract(tmp_path / "target")
    ledger = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"]
        / "ledgers"
        / "refusals_data_quality.jsonl"
    )
    ledger.append(row)
    with pytest.raises(ValueError, match=f"identifiers.{field}"):
        LiveAnalyticalOrchestrator(runtime)


def test_stage_startup_refuses_partial_row_that_has_identity_and_order_fields(
    tmp_path,
):
    runtime = contract(tmp_path)
    stage = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"]
        / "analytical_observation_stage"
        / f"{SESSION}.jsonl"
    )
    stage.append({
        "observation_id": "O0001",
        "session_date": SESSION,
        "instrument_class": "INDEX",
        "canonical_symbol": INDEX,
        "source_symbol": INDEX,
        "receipt_timestamp": "2026-08-20T10:00:00+05:30",
        "source_file": f"raw/{SESSION}/events_10.jsonl",
        "source_stream": "raw",
        "source_byte_offset": 0,
        "source_row_number": 1,
        "raw_record_id": "RAW-O0001",
        "availability_status": "AVAILABLE",
        "freshness_status": "FRESH",
        "out_of_order": False,
    })

    with pytest.raises(ValueError, match="missing required fields"):
        LiveAnalyticalOrchestrator(runtime)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("source_symbol", "mismatched canonical/source symbol"),
        ("source_path", "invalid source file identity"),
        ("option_symbol", "invalid option identity"),
        ("option_strike", "invalid option identity"),
        ("option_expiry", "invalid option identity"),
        ("futures_symbol", "invalid Futures identity"),
    ),
)
def test_stage_startup_refuses_class_identity_tampering(
    tmp_path, mutation, message,
):
    instant = datetime(2026, 8, 20, 10, 0, tzinfo=IST)
    builder = LiveAnalyticalOrchestrator(contract(tmp_path / "builder"))
    row = builder._prepare(observation(
        "O0001",
        "CE",
        "NSE:BANKNIFTY26AUG57000CE",
        instant,
        price=200,
        volume=10,
        oi=500,
        strike=57_000,
        expiry="2026-08-27",
    ))
    if mutation == "source_symbol":
        row["source_symbol"] = "NSE:BANKNIFTY26AUG57100CE"
    elif mutation == "source_path":
        row["source_file"] = f"raw/{SESSION}/focused_fixture.jsonl"
        row["source_receipt_identifiers"]["file"] = row["source_file"]
    elif mutation == "option_symbol":
        row["canonical_symbol"] = "NSE:BANKNIFTY-INVALID-CE"
        row["source_symbol"] = row["canonical_symbol"]
    elif mutation == "option_strike":
        row["strike"] = 57_100
    elif mutation == "option_expiry":
        row["expiry"] = "2026-09-24"
        row["expiry_date"] = row["expiry"]
    else:
        row["instrument_class"] = "FUTURES"
        row["canonical_symbol"] = "NSE:BANKNIFTY-FUT"
        row["source_symbol"] = row["canonical_symbol"]
        row["source_stream"] = "raw"
        row["source_file"] = f"raw/{SESSION}/focused_fixture.jsonl"
        row["source_receipt_identifiers"]["source_stream"] = "raw"
        row["source_receipt_identifiers"]["file"] = row["source_file"]

    runtime = contract(tmp_path / "target")
    stage = orchestrator_module.AppendOnlyLedger(
        runtime["state_root"]
        / "analytical_observation_stage"
        / f"{SESSION}.jsonl"
    )
    stage.append(row)
    with pytest.raises(ValueError, match=message):
        LiveAnalyticalOrchestrator(runtime)


def test_material_append_refuses_schema_empty_row_before_persistence(tmp_path):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    with pytest.raises(ValueError, match="invalid episode_id"):
        orchestrator._append_once(
            "divergence_confirmations",
            {"event_id": "BDR1-MALFORMED-BUT-UNIQUE"},
            "BDR1-MALFORMED-BUT-UNIQUE",
            "2026-08-20T10:00:00+05:30",
        )
    assert orchestrator.ledgers["divergence_confirmations"].rows() == []


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


def test_inventory_uses_five_second_clock_while_basis_remains_two_seconds(
    tmp_path,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    rows = [
        observation("O0001", "INDEX", INDEX, base, price=57000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES, base + timedelta(seconds=3),
            price=57025, volume=100,
        ),
        observation(
            "O0003", "FUTURES", FUTURES, base + timedelta(seconds=4),
            price=57026, volume=120,
        ),
    ]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(rows)
    state = orchestrator.snapshot(SESSION)

    assert [row["validity_status"] for row in state["basis"]] == [
        "UNMATCHED_TOLERANCE_EXCEEDED",
        "UNMATCHED_TOLERANCE_EXCEEDED",
    ]
    assert [row["absolute_receipt_difference_ms"] for row in state["basis"]] == [
        3000.0,
        4000.0,
    ]
    intraday = [
        row for row in state["inventory"]
        if row["horizon"] == "ID"
        and row["family"] == "BN_REF_FUT_VOLUME_VPOC"
    ]
    assert len(intraday) == 1
    assert intraday[0]["eligible_observation_count"] == 1
    assert orchestrator.causality_metrics()["valid_basis_pairs"] == 0


def test_cross_layer_context_survives_restart_and_keeps_fallback_local(tmp_path):
    first_rows = full_stack_fixture()
    first = LiveAnalyticalOrchestrator(contract(tmp_path))
    first.process(first_rows)
    first_state = first.finalize_session(SESSION)
    first_resolution_count = len(first_state["resolution"])
    assert first._cross_layer_contexts[SESSION]["inventory_source_count"] == 0

    second_session = "2026-08-21"
    second_rows = []
    for row in full_stack_fixture():
        value = json.loads(json.dumps(row).replace(SESSION, second_session))
        value["observation_id"] += "-D2"
        value["raw_record_id"] += "-D2"
        second_rows.append(value)
    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    restarted.process(second_rows)
    second_state = restarted.finalize_session(second_session)

    divergence = next(
        row for row in second_state["cross_layer_transitions"]
        if row["component"] == "DIVERGENCE"
    )
    resolution = next(
        row for row in second_state["cross_layer_transitions"]
        if row["component"] == "RESOLUTION"
    )
    inventory = next(
        row for row in second_state["cross_layer_transitions"]
        if row["component"] == "INVENTORY"
    )
    assert divergence["source_record_id"] == "episode:2"
    assert resolution["source_record_id"] == (
        f"resolution:{first_resolution_count + 1}"
    )
    assert inventory["source_record_id"] == "inventory:1"
    assert restarted._cross_layer_contexts[second_session][
        "inventory_source_count"
    ] == 0

    again = LiveAnalyticalOrchestrator(contract(tmp_path))
    assert again._cross_layer_contexts == restarted._cross_layer_contexts
    assert ledger_counts(again) == ledger_counts(restarted)


def test_canonical_cross_layer_sessions_equal_one_global_build_after_restart(
    tmp_path,
):
    second_session = "2026-08-21"
    runtime = contract(tmp_path)
    runtime["config"]["fixed_inventory_rows"] = [
        orchestrator_module.inventory_engine.record(
            session, "3D", "FUT_POS_OI_VPOC", 57325, session,
            f"{session}T09:15:00+05:30",
            f"{session}T09:15:00+05:30", FUTURES, "2026-08-27",
            1, 1.0, "", "", "NO_TIE",
        )
        for session in (SESSION, second_session)
    ]
    first = LiveAnalyticalOrchestrator(runtime)
    first.process(full_stack_fixture())
    first_state = first.finalize_session(SESSION)

    second_rows = []
    for row in full_stack_fixture():
        value = json.loads(json.dumps(row).replace(SESSION, second_session))
        value["observation_id"] += "-D2"
        value["raw_record_id"] += "-D2"
        second_rows.append(value)
    restarted = LiveAnalyticalOrchestrator(runtime)
    restarted.process(second_rows)
    second_state = restarted.finalize_session(second_session)

    expected = build_material_transitions(
        first_state["inventory"] + second_state["inventory"],
        first_state["episodes"] + second_state["episodes"],
        first_state["lifecycle"] + second_state["lifecycle"],
        first_state["resolution"] + second_state["resolution"],
        first_state["participation_transitions"]
        + second_state["participation_transitions"],
    )
    actual = (
        first_state["cross_layer_transitions"]
        + second_state["cross_layer_transitions"]
    )
    assert actual == expected
    assert not any(
        row["component"] == "INVENTORY"
        and row["horizon"] == "3D"
        and row["family"] == "FUT_POS_OI_VPOC"
        for row in second_state["cross_layer_transitions"]
    )
    final_context = restarted._cross_layer_contexts[second_session]
    assert final_context["inventory_source_count"] == (
        len(first_state["inventory"]) + len(second_state["inventory"])
    )


def test_earlier_session_mutation_is_refused_after_successor_publication(tmp_path):
    second_session = "2026-08-21"
    first_row = observation(
        "O0001", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57000,
    )
    second_row = observation(
        "O0002", "INDEX", INDEX,
        datetime(2026, 8, 21, 9, 15, tzinfo=IST), price=57100,
    )
    second_row.update({
        "session_date": second_session,
        "source_file": f"raw/{second_session}/focused_fixture.jsonl",
    })
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([first_row, second_row])
    orchestrator.flush([SESSION, second_session])

    late_prefix_mutation = observation(
        "O0003", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 16, tzinfo=IST), price=57001,
    )
    orchestrator.process([late_prefix_mutation])
    assert "O0003" not in orchestrator._sessions[SESSION]
    assert "OUT_OF_ORDER_SESSION_RECEIPT" in {
        row["reason"]
        for row in orchestrator.ledgers["refusals_data_quality"].rows()
    }


def test_multi_session_publication_is_strictly_chronological(tmp_path, monkeypatch):
    second_session = "2026-08-21"
    first_row = observation(
        "O0001", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57000,
    )
    second_row = observation(
        "O0002", "INDEX", INDEX,
        datetime(2026, 8, 21, 9, 15, tzinfo=IST), price=57100,
    )
    second_row.update({
        "session_date": second_session,
        "source_file": f"raw/{second_session}/focused_fixture.jsonl",
    })
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([second_row, first_row])
    original = orchestrator._publish
    observed = []

    def capture(outputs, previous):
        observed.extend(outputs)
        return original(outputs, previous)

    monkeypatch.setattr(orchestrator, "_publish", capture)
    orchestrator.flush([second_session, SESSION])
    assert observed == [SESSION, second_session]


def test_later_session_requires_finalized_or_same_flush_predecessor(tmp_path):
    first = LiveAnalyticalOrchestrator(contract(tmp_path))
    first.process([
        observation(
            "O0001", "INDEX", INDEX,
            datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57000,
        )
    ])
    first.flush([SESSION])
    second_session = "2026-08-21"
    row = observation(
        "O0002", "INDEX", INDEX,
        datetime(2026, 8, 21, 9, 15, tzinfo=IST), price=57100,
    )
    row.update({
        "session_date": second_session,
        "source_file": f"raw/{second_session}/focused_fixture.jsonl",
    })
    first.process([row])
    with pytest.raises(ValueError, match="before finalizing predecessor"):
        first.flush([second_session])
    assert second_session in first._dirty_sessions

    first.finalize_session(SESSION)
    first.flush([second_session])
    assert second_session not in first._dirty_sessions


@pytest.mark.parametrize("failure_mode", ("before_replace", "after_replace"))
def test_flush_state_persistence_failure_retains_retryable_context(
    tmp_path, monkeypatch, failure_mode,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(full_stack_fixture())
    original = orchestrator_module.atomic_json
    failed = False

    def fail_once(path, value):
        nonlocal failed
        if path == orchestrator.state_path and not failed:
            failed = True
            if failure_mode == "after_replace":
                original(path, value)
            raise OSError(f"synthetic {failure_mode} state failure")
        return original(path, value)

    monkeypatch.setattr(orchestrator_module, "atomic_json", fail_once)
    with pytest.raises(OSError, match=failure_mode):
        orchestrator.flush()
    assert orchestrator._outputs == {}
    assert orchestrator._cross_layer_contexts == {}
    assert SESSION in orchestrator._dirty_sessions
    durable_counts = ledger_counts(orchestrator)

    orchestrator.flush()
    assert SESSION not in orchestrator._dirty_sessions
    assert orchestrator._cross_layer_contexts[SESSION][
        "resolution_source_count"
    ] > 0
    assert ledger_counts(orchestrator) == durable_counts
    assert_unique_stage_and_publication_ids(orchestrator)


def test_finalize_state_failure_does_not_mutate_live_session(
    tmp_path, monkeypatch,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process(full_stack_fixture())
    orchestrator.flush()
    original = orchestrator_module.atomic_json
    failed = False

    def fail_once(path, value):
        nonlocal failed
        if path == orchestrator.state_path and not failed:
            failed = True
            raise OSError("synthetic finalize state failure")
        return original(path, value)

    monkeypatch.setattr(orchestrator_module, "atomic_json", fail_once)
    with pytest.raises(OSError, match="finalize state failure"):
        orchestrator.finalize_session(SESSION)
    assert SESSION not in orchestrator._finalized_sessions
    assert SESSION in orchestrator._sessions

    orchestrator.finalize_session(SESSION)
    assert SESSION in orchestrator._finalized_sessions
    assert SESSION not in orchestrator._sessions


def test_legacy_context_migration_refuses_evicted_finalized_prefix(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    later = "2026-08-21"
    (state_root / "live_analytical_orchestrator.json").write_text(json.dumps({
        "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
        "sessions": {},
        "outputs": {later: LiveAnalyticalOrchestrator._empty_snapshot(later)},
        "dirty_sessions": [],
        "finalized_sessions": [SESSION, later],
    }))
    with pytest.raises(ValueError, match="clean rebuild required"):
        LiveAnalyticalOrchestrator(contract(tmp_path))


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


def test_noncanonical_session_date_is_refused_before_stage_path_use(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    escaped = tmp_path / "escaped.jsonl"
    unsafe = observation("O0001", "INDEX", INDEX, base, price=57000)
    unsafe["session_date"] = str(escaped.with_suffix(""))

    orchestrator.process([unsafe])

    assert not escaped.exists()
    assert not list(orchestrator.stage_root.glob("*.jsonl"))
    refusals = orchestrator.ledgers["refusals_data_quality"].rows()
    assert len(refusals) == 1
    assert refusals[0]["reason"] == "ORCHESTRATOR_OBSERVATION_REFUSED"
    assert "unsafe analytical session date" in refusals[0]["detail"]


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


def test_restart_refuses_tampered_mutable_session_content(tmp_path):
    orchestrator, _row = persist_one_mutable_session(tmp_path)
    state = json.loads(orchestrator.state_path.read_text())
    state["sessions"][SESSION][0]["price"] = 99_999
    orchestrator.state_path.write_text(json.dumps(state))

    with pytest.raises(
        ValueError,
        match="content mismatch with durable stage.*O0001",
    ):
        LiveAnalyticalOrchestrator(contract(tmp_path))


def test_restart_refuses_duplicate_mutable_session_identity(tmp_path):
    orchestrator, _row = persist_one_mutable_session(tmp_path)
    state = json.loads(orchestrator.state_path.read_text())
    state["sessions"][SESSION].append(dict(state["sessions"][SESSION][0]))
    orchestrator.state_path.write_text(json.dumps(state))

    with pytest.raises(
        ValueError,
        match="duplicate persisted analytical observation identity.*O0001",
    ):
        LiveAnalyticalOrchestrator(contract(tmp_path))


@pytest.mark.parametrize(
    "unsafe_session",
    ("../ledgers/refusals_data_quality", "20260820"),
)
def test_restart_refuses_unsafe_or_noncanonical_persisted_session_key(
    tmp_path, unsafe_session,
):
    orchestrator, _row = persist_one_mutable_session(tmp_path)
    state = json.loads(orchestrator.state_path.read_text())
    state["sessions"] = {
        unsafe_session: state["sessions"].pop(SESSION),
    }
    orchestrator.state_path.write_text(json.dumps(state))

    with pytest.raises(ValueError, match="persisted analytical session key"):
        LiveAnalyticalOrchestrator(contract(tmp_path))


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("output_key", "analytical output key"),
        ("output_session", "output has mismatched session_date"),
        ("output_missing_session", "output has mismatched session_date"),
        ("output_orphan", "outputs lack mutable or finalized"),
        ("context_key", "cross-layer context key"),
        ("context_value", "cross-layer context is not an object"),
        ("context_orphan", "context authority mismatch"),
        ("context_missing", "context authority mismatch"),
        ("dirty_container", "dirty_sessions must be a list"),
        ("dirty_item", "dirty_sessions item 1"),
        ("dirty_duplicate", "dirty_sessions contains duplicate"),
        ("dirty_without_session", "dirty_sessions are missing mutable"),
        ("finalized_container", "finalized_sessions must be a list"),
        ("finalized_item", "finalized_sessions item 1"),
        ("finalized_mutable", "finalized_sessions retain mutable"),
        ("dirty_finalized_overlap", "overlap finalized_sessions"),
    ),
)
def test_restart_refuses_malformed_persisted_session_containers(
    tmp_path, corruption, message,
):
    runtime = contract(tmp_path)
    runtime["state_root"].mkdir(parents=True, exist_ok=True)
    state = {
        "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
        "sessions": {SESSION: []},
        "outputs": {
            SESSION: LiveAnalyticalOrchestrator._empty_snapshot(SESSION),
        },
        "cross_layer_contexts": {
            SESSION: orchestrator_module.cross_layer_state.empty_material_context(),
        },
        "dirty_sessions": [],
        "finalized_sessions": [],
    }
    if corruption == "output_key":
        state["outputs"] = {"20260820": state["outputs"].pop(SESSION)}
    elif corruption == "output_session":
        state["outputs"][SESSION]["session_date"] = "2026-08-21"
    elif corruption == "output_missing_session":
        state["outputs"][SESSION].pop("session_date")
    elif corruption == "output_orphan":
        state["sessions"] = {}
    elif corruption == "context_key":
        state["cross_layer_contexts"] = {
            "20260820": state["cross_layer_contexts"].pop(SESSION),
        }
    elif corruption == "context_value":
        state["cross_layer_contexts"][SESSION] = []
    elif corruption == "context_orphan":
        state["cross_layer_contexts"]["2026-08-21"] = (
            orchestrator_module.cross_layer_state.empty_material_context()
        )
    elif corruption == "context_missing":
        state["sessions"]["2026-08-21"] = []
        state["outputs"]["2026-08-21"] = (
            LiveAnalyticalOrchestrator._empty_snapshot("2026-08-21")
        )
    elif corruption == "dirty_container":
        state["dirty_sessions"] = SESSION
    elif corruption == "dirty_item":
        state["dirty_sessions"] = ["20260820"]
    elif corruption == "dirty_duplicate":
        state["sessions"][SESSION] = []
        state["dirty_sessions"] = [SESSION, SESSION]
    elif corruption == "dirty_without_session":
        state["sessions"] = {}
        state["dirty_sessions"] = [SESSION]
    elif corruption == "finalized_container":
        state["finalized_sessions"] = SESSION
    elif corruption == "finalized_item":
        state["finalized_sessions"] = ["20260820"]
    elif corruption == "finalized_mutable":
        state["sessions"][SESSION] = []
        state["finalized_sessions"] = [SESSION]
    else:
        state["sessions"][SESSION] = []
        state["dirty_sessions"] = [SESSION]
        state["finalized_sessions"] = [SESSION]
    (runtime["state_root"] / "live_analytical_orchestrator.json").write_text(
        json.dumps(state)
    )

    with pytest.raises(ValueError, match=message):
        LiveAnalyticalOrchestrator(runtime)


def test_restart_refuses_mutable_session_without_durable_stage(tmp_path):
    orchestrator, _row = persist_one_mutable_session(tmp_path)
    (orchestrator.stage_root / f"{SESSION}.jsonl").unlink()

    with pytest.raises(
        ValueError,
        match="missing from durable stage.*O0001",
    ):
        LiveAnalyticalOrchestrator(contract(tmp_path))


def test_restart_refuses_noncanonical_state_session_before_stage_path(tmp_path):
    orchestrator, _row = persist_one_mutable_session(tmp_path)
    state = json.loads(orchestrator.state_path.read_text())
    state["sessions"]["../../outside"] = state["sessions"].pop(SESSION)
    orchestrator.state_path.write_text(json.dumps(state))

    with pytest.raises(
        ValueError,
        match="persisted analytical session key is invalid",
    ):
        LiveAnalyticalOrchestrator(contract(tmp_path))
    assert not (tmp_path / "outside.jsonl").exists()


def test_stage_failure_before_write_remains_replayable_and_unaccepted(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    row = observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original = orchestrator_module.AppendOnlyLedger.append_many_retained
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
        orchestrator_module.AppendOnlyLedger,
        "append_many_retained", fail_before_write,
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
    original_retained = (
        orchestrator_module.AppendOnlyLedger.append_many_retained
    )
    original_standard = orchestrator_module.AppendOnlyLedger.append_many
    stage_failed = False

    def fail_after_stage_write(ledger, values):
        nonlocal stage_failed
        if ledger.path.parent == orchestrator.stage_root and not stage_failed:
            stage_failed = True
            assert row["observation_id"] not in orchestrator._sessions.get(
                SESSION, {}
            )
            assert SESSION not in orchestrator._dirty_sessions
            original_retained(ledger, values)
            assert row["observation_id"] not in orchestrator._sessions.get(
                SESSION, {}
            )
            assert SESSION not in orchestrator._dirty_sessions
            raise RuntimeError("synthetic post-write stage failure")
        return original_retained(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many_retained",
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
            original_standard(ledger, values)
            raise RuntimeError("synthetic post-write publication failure")
        return original_standard(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many",
        fail_after_publication_write,
    )
    with pytest.raises(
        RuntimeError, match="synthetic post-write publication failure"
    ):
        orchestrator.finalize_session(SESSION)
    assert orchestrator._ledger_seen["availability_transitions"]
    assert SESSION not in orchestrator._finalized_sessions

    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    restarted.finalize_session(SESSION)
    before = ledger_counts(restarted)
    restarted.finalize_session(SESSION)
    assert ledger_counts(restarted) == before
    assert len(restarted.ledgers["availability_transitions"].rows()) == 12
    assert_unique_stage_and_publication_ids(restarted)


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
    row = material_ledger_fixture(ledger_name)
    calculation = "2026-08-20T10:00:00+05:30"
    with pytest.raises(RuntimeError, match=ledger_name):
        orchestrator._append_once(
            ledger_name, row, f"{ledger_name}:fixture", calculation,
        )
    physical = orchestrator.ledgers[ledger_name].rows()
    assert len(physical) == 1
    event_id = physical[0]["event_id"]
    assert event_id in orchestrator._ledger_seen[ledger_name]

    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    restarted._append_once(
        ledger_name, row, f"{ledger_name}:fixture", calculation,
    )
    replayed = restarted.ledgers[ledger_name].rows()
    assert [value["event_id"] for value in replayed] == [event_id]


def test_quality_ledger_reconciles_post_append_exception_exactly_once(
    tmp_path, monkeypatch,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    ledger = orchestrator.ledgers["refusals_data_quality"]
    original = ledger.append_many
    failed = False

    def fail_after_write(values):
        nonlocal failed
        if not failed:
            failed = True
            original(values)
            raise RuntimeError("synthetic quality post-write failure")
        return original(values)

    monkeypatch.setattr(ledger, "append_many", fail_after_write)
    row = {
        "observation_id": "O-REFUSED-ONE",
        "session_date": SESSION,
        # Invalid evidence clocks use a wall-clock effective timestamp.  The
        # retry must still identify the same durable refusal event.
        "receipt_timestamp": "invalid-receipt-clock",
        "source_file": f"raw/{SESSION}/events.jsonl",
        "source_byte_offset": 100,
        "source_row_number": 1,
    }
    with pytest.raises(RuntimeError, match="quality post-write failure"):
        orchestrator._quality(row, "SYNTHETIC_REFUSAL", "stable detail")
    physical = ledger.rows()
    assert len(physical) == 1
    assert parse_timestamp(physical[0]["effective_timestamp"]).tzinfo is not None
    assert (
        physical[0]["effective_timestamp_provenance"]
        == "WALL_CLOCK_FALLBACK"
    )
    assert physical[0]["event_id"] in orchestrator._ledger_seen[
        "refusals_data_quality"
    ]

    orchestrator._quality(row, "SYNTHETIC_REFUSAL", "stable detail")
    assert ledger.rows() == physical
    restarted = LiveAnalyticalOrchestrator(contract(tmp_path))
    restarted._quality(row, "SYNTHETIC_REFUSAL", "stable detail")
    assert restarted.ledgers["refusals_data_quality"].rows() == physical
    with pytest.raises(ValueError, match="different immutable content"):
        restarted._quality(row, "SYNTHETIC_REFUSAL", "changed detail")
    assert restarted.ledgers["refusals_data_quality"].rows() == physical


def test_quality_valid_evidence_clock_is_immutable_after_ambiguous_append(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    ledger = orchestrator.ledgers["refusals_data_quality"]
    original = ledger.append_many
    failed = False

    def fail_after_write(values):
        nonlocal failed
        if not failed:
            failed = True
            original(values)
            raise RuntimeError("synthetic valid-clock post-write failure")
        return original(values)

    monkeypatch.setattr(ledger, "append_many", fail_after_write)
    row = {
        "observation_id": "O-REFUSED-VALID-CLOCK",
        "session_date": SESSION,
        "receipt_timestamp": "2026-08-20T10:00:00.123456+05:30",
        "source_file": f"raw/{SESSION}/events.jsonl",
        "source_byte_offset": 200,
        "source_row_number": 2,
    }
    with pytest.raises(RuntimeError, match="valid-clock post-write failure"):
        orchestrator._quality(row, "SYNTHETIC_REFUSAL", "stable detail")
    physical = ledger.rows()
    assert len(physical) == 1
    assert physical[0]["effective_timestamp"] == row["receipt_timestamp"]
    assert physical[0]["effective_timestamp_provenance"] == "EVIDENCE"

    restarted = LiveAnalyticalOrchestrator(runtime)
    restarted._quality(row, "SYNTHETIC_REFUSAL", "stable detail")
    assert restarted.ledgers["refusals_data_quality"].rows() == physical

    changed_clock = dict(row)
    changed_clock["receipt_timestamp"] = "2026-08-20T10:00:00.123457+05:30"
    with pytest.raises(ValueError, match="different immutable content"):
        restarted._quality(
            changed_clock, "SYNTHETIC_REFUSAL", "stable detail"
        )
    assert restarted.ledgers["refusals_data_quality"].rows() == physical


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
    original = orchestrator_module.AppendOnlyLedger.append_many_retained
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
        "append_many_retained",
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


def test_stage_ambiguity_with_unrelated_tail_is_durably_quarantined(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    attempted = observation(
        "O9101", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    )
    unrelated = orchestrator._prepare(observation(
        "O9102", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, 1, tzinfo=IST),
        price=57_001, volume=0,
    ))
    original = orchestrator_module.AppendOnlyLedger.append_many_retained
    injected = False

    def append_attempt_and_unrelated_tail(ledger, values):
        nonlocal injected
        if ledger.path.parent == orchestrator.stage_root and not injected:
            injected = True
            original(ledger, values)
            with ledger.path.open("ab") as handle:
                handle.write((
                    json.dumps(unrelated, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode())
                handle.flush()
                os.fsync(handle.fileno())
            raise RuntimeError("synthetic unrelated durable tail")
        return original(ledger, values)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many_retained",
        append_attempt_and_unrelated_tail,
    )
    with pytest.raises(ValueError, match="ambiguity quarantined"):
        orchestrator.process_observations([attempted])
    assert orchestrator._sessions.get(SESSION, {}) == {}
    assert orchestrator._stage_recovery_failure_path(SESSION).is_file()

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger, "append_many_retained", original,
    )
    with pytest.raises(ValueError, match="stage is quarantined"):
        orchestrator.process_observations([attempted])
    assert orchestrator._sessions.get(SESSION, {}) == {}
    with pytest.raises(ValueError, match="stage is quarantined"):
        LiveAnalyticalOrchestrator(runtime)


def test_stage_quarantine_poison_survives_marker_write_failure(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    attempted = observation(
        "O9201", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    )
    unrelated = orchestrator._prepare(observation(
        "O9202", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, 1, tzinfo=IST),
        price=57_001, volume=0,
    ))
    original_append = orchestrator_module.AppendOnlyLedger.append_many_retained
    original_atomic = orchestrator_module.atomic_json
    injected = False

    def append_unrelated_tail(ledger, values):
        nonlocal injected
        if ledger.path.parent == orchestrator.stage_root and not injected:
            injected = True
            original_append(ledger, values)
            with ledger.path.open("ab") as handle:
                handle.write((
                    json.dumps(unrelated, sort_keys=True, separators=(",", ":"))
                    + "\n"
                ).encode())
                handle.flush()
                os.fsync(handle.fileno())
            raise RuntimeError("synthetic unrelated durable tail")
        return original_append(ledger, values)

    def fail_recovery_marker(path, value):
        if path.name.endswith(".recovery_failed.json"):
            raise OSError("synthetic recovery marker failure")
        return original_atomic(path, value)

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many_retained", append_unrelated_tail,
    )
    monkeypatch.setattr(orchestrator_module, "atomic_json", fail_recovery_marker)
    with pytest.raises(OSError, match="recovery marker failure"):
        orchestrator.process_observations([attempted])

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "append_many_retained", original_append,
    )
    monkeypatch.setattr(orchestrator_module, "atomic_json", original_atomic)
    with pytest.raises(ValueError, match="stage is quarantined"):
        orchestrator.process_observations([attempted])
    assert orchestrator._sessions.get(SESSION, {}) == {}
    assert SESSION in orchestrator._poisoned_stage_sessions
    stage_path = orchestrator.stage_root / f"{SESSION}.jsonl"
    assert [
        json.loads(line)["observation_id"]
        for line in stage_path.read_text().splitlines()
    ] == ["O9201", "O9202"]
    # The pre-append intent remains durable even though the later quarantine
    # marker write failed. Trusted ledger startup rediscovers the unrelated
    # tail, persists the generic quarantine, and the session cannot restart.
    generic = orchestrator_module.AppendOnlyLedger(stage_path)
    with pytest.raises(ValueError, match="quarantined"):
        generic.rows()
    assert generic._append_quarantine_path.is_file()
    with pytest.raises(ValueError, match="quarantined"):
        LiveAnalyticalOrchestrator(runtime)
    assert not orchestrator._stage_recovery_failure_path(SESSION).exists()


def test_retained_stage_append_recovers_exact_full_tail_after_ack_failure(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    attempted = observation(
        "O9251", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    )

    original_ack = orchestrator_module.AppendOnlyLedger.acknowledge_retained_append

    def fail_before_intent_clear(ledger, receipt, *, accepted_identities):
        if ledger.path.parent == orchestrator.stage_root:
            raise OSError("synthetic crash before retained-intent ACK")
        return original_ack(
            ledger, receipt, accepted_identities=accepted_identities,
        )

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "acknowledge_retained_append", fail_before_intent_clear,
    )
    with pytest.raises(OSError, match="retained-intent ACK"):
        orchestrator.process_observations([attempted])
    intent = (
        orchestrator.stage_root
        / f"{SESSION}.jsonl.append_intent.json"
    )
    assert intent.is_file()

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "acknowledge_retained_append", original_ack,
    )
    restarted = LiveAnalyticalOrchestrator(runtime)
    assert not intent.exists()
    assert list(restarted._sessions[SESSION]) == ["O9251"]
    restarted.process_observations([attempted])
    assert [
        row["observation_id"]
        for row in restarted._stage_ledger(SESSION).rows()
    ] == ["O9251"]


def test_retained_stage_append_survives_crash_before_caller_accept(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    attempted = observation(
        "O9255", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST),
        price=57_000, volume=0,
    )

    def crash_before_accept(_session, _rows):
        raise RuntimeError("synthetic crash before caller accept")

    monkeypatch.setattr(
        orchestrator, "_accept_durable_stage_rows", crash_before_accept,
    )
    with pytest.raises(RuntimeError, match="before caller accept"):
        orchestrator.process_observations([attempted])
    intent = (
        orchestrator.stage_root / f"{SESSION}.jsonl.append_intent.json"
    )
    assert intent.is_file()
    assert orchestrator._sessions.get(SESSION, {}) == {}

    restarted = LiveAnalyticalOrchestrator(runtime)
    assert not intent.exists()
    assert list(restarted._sessions[SESSION]) == ["O9255"]
    restarted.process_observations([attempted])
    assert [
        row["observation_id"]
        for row in restarted._stage_ledger(SESSION).rows()
    ] == ["O9255"]


def test_same_process_retry_resolves_ack_failure_before_dedup_and_next_row(
    tmp_path, monkeypatch,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    first = observation(
        "O9256", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST),
        price=57_000, volume=0,
    )
    second = observation(
        "O9257", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, 1, tzinfo=IST),
        price=57_001, volume=0,
    )
    original_ack = orchestrator_module.AppendOnlyLedger.acknowledge_retained_append
    failed = False

    def fail_first_ack(ledger, receipt, *, accepted_identities):
        nonlocal failed
        if ledger.path.parent == orchestrator.stage_root and not failed:
            failed = True
            raise OSError("synthetic one-time retained ACK failure")
        return original_ack(
            ledger, receipt, accepted_identities=accepted_identities,
        )

    monkeypatch.setattr(
        orchestrator_module.AppendOnlyLedger,
        "acknowledge_retained_append", fail_first_ack,
    )
    with pytest.raises(OSError, match="one-time retained ACK failure"):
        orchestrator.process_observations([first])
    intent = (
        orchestrator.stage_root / f"{SESSION}.jsonl.append_intent.json"
    )
    assert intent.is_file()
    assert list(orchestrator._sessions[SESSION]) == ["O9256"]

    # The exact replay must resolve the retained generic receipt before the
    # `_stage_seen` identity shortcut. A later row must then append normally.
    orchestrator.process_observations([first])
    assert not intent.exists()
    orchestrator.process_observations([second])
    assert not intent.exists()
    assert [
        row["observation_id"]
        for row in orchestrator._stage_ledger(SESSION).rows()
    ] == ["O9256", "O9257"]


def test_normal_stage_uses_one_retained_intent_and_four_steady_state_fsyncs(
    tmp_path, monkeypatch,
):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original_fsync = ledger_module.os.fsync
    fsync_count = 0

    def counted_fsync(descriptor):
        nonlocal fsync_count
        fsync_count += 1
        return original_fsync(descriptor)

    monkeypatch.setattr(ledger_module.os, "fsync", counted_fsync)
    orchestrator.process_observations([observation(
        "O9253", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST),
        price=57_000, volume=0,
    )])
    first_append_fsyncs = fsync_count
    orchestrator.process_observations([observation(
        "O9254", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, 1, tzinfo=IST),
        price=57_001, volume=0,
    )])

    # First creation adds one directory-entry fsync; a normal later append is
    # intent-file fsync + intent-directory fsync + data fsync + ACK-directory
    # fsync. The superseded two-intent path required seven steady-state fsyncs.
    assert first_append_fsyncs == 5
    assert fsync_count - first_append_fsyncs == 4
    assert not orchestrator._stage_append_intent_path(SESSION).exists()
    assert not (
        orchestrator.stage_root / f"{SESSION}.jsonl.append_intent.json"
    ).exists()


def test_legacy_stage_append_intent_still_recovers_exact_tail(tmp_path):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    expected = orchestrator._prepare(observation(
        "O9252", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST),
        price=57_000, volume=0,
    ))
    ledger = orchestrator._raw_stage_ledger(SESSION)
    boundary = ledger.append_boundary()
    orchestrator._write_stage_append_intent(SESSION, boundary, [expected])
    ledger.append_many([expected])

    restarted = LiveAnalyticalOrchestrator(runtime)
    assert not restarted._stage_append_intent_path(SESSION).exists()
    assert list(restarted._sessions[SESSION]) == ["O9252"]


def test_stage_append_intent_rejects_oversize_tail_before_decoding(
    tmp_path, monkeypatch,
):
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    expected = orchestrator._prepare(observation(
        "O9261", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    ))
    unrelated = orchestrator._prepare(observation(
        "O9262", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, 1, tzinfo=IST),
        price=57_001, volume=0,
    ))
    ledger = orchestrator._raw_stage_ledger(SESSION)
    boundary = ledger.append_boundary()
    orchestrator._write_stage_append_intent(SESSION, boundary, [expected])
    ledger.append_many([expected, unrelated])

    monkeypatch.setattr(
        ledger,
        "scan_from",
        lambda *_args, **_kwargs: pytest.fail(
            "oversize intent recovery decoded the unexpected tail"
        ),
    )
    with pytest.raises(ValueError, match="stage is quarantined"):
        orchestrator._recover_stage_append_intent(SESSION)
    assert orchestrator._stage_recovery_failure_path(SESSION).is_file()


def test_stage_identity_requires_identical_normalized_content(tmp_path):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    original = observation(
        "O9103", "INDEX", INDEX,
        datetime(2026, 8, 20, 9, 15, tzinfo=IST), price=57_000, volume=0,
    )
    orchestrator.process_observations([original])
    changed = dict(original)
    changed["price"] = 57_001
    with pytest.raises(ValueError, match="identity reused with different content"):
        orchestrator.process_observations([changed])
    assert len(orchestrator._stage_ledger(SESSION).rows()) == 1


def test_material_identity_index_uses_one_fixed_digest_mapping(tmp_path):
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    row = material_ledger_fixture("inventory_winner_transitions")
    orchestrator._append_once(
        "inventory_winner_transitions", row, "fixed-digest",
        row["control_effective_timestamp"],
    )
    assert orchestrator._ledger_seen is orchestrator._ledger_content
    digests = list(orchestrator._ledger_content["inventory_winner_transitions"].values())
    assert len(digests) == 1
    assert len(digests[0]) == 64
    int(digests[0], 16)


def test_registered_callback_stages_linearly_until_explicit_snapshot(tmp_path, monkeypatch):
    rows = full_stack_fixture()[:24]
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    calls = []
    order_key_calls = 0
    stage_prime_calls = 0
    original = orchestrator._compute_sessions
    original_order_key = orchestrator._order_key
    stage_ledger = orchestrator._stage_ledger(SESSION)
    original_stage_prime = stage_ledger._read_and_prime_locked

    def counted_order_key(row):
        nonlocal order_key_calls
        order_key_calls += 1
        return original_order_key(row)

    def counted_stage_prime():
        nonlocal stage_prime_calls
        stage_prime_calls += 1
        return original_stage_prime()

    monkeypatch.setattr(
        orchestrator,
        "_compute_sessions",
        lambda targets: (calls.append(set(targets)), original(targets))[1],
    )
    monkeypatch.setattr(orchestrator, "_order_key", counted_order_key)
    monkeypatch.setattr(stage_ledger, "_read_and_prime_locked", counted_stage_prime)
    for row in rows:
        orchestrator.process_observations([row])
    assert calls == []
    # A one-record increment may inspect that record while validating, sorting,
    # and accepting it, but must never rescan all prior session observations.
    assert order_key_calls <= 3 * len(rows)
    assert stage_prime_calls == 1
    assert orchestrator._stage_ledger(SESSION) is stage_ledger
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


def test_staleness_refresh_retry_after_persist_crash_is_exactly_once(
    tmp_path, monkeypatch,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    runtime = contract(tmp_path)
    orchestrator = LiveAnalyticalOrchestrator(runtime)
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    orchestrator.snapshot(SESSION)

    stale_at = base + timedelta(seconds=20)
    monkeypatch.setattr(
        orchestrator,
        "_persist_values",
        lambda **_values: (_ for _ in ()).throw(
            RuntimeError("synthetic availability state persist crash")
        ),
    )
    with pytest.raises(
        RuntimeError, match="synthetic availability state persist crash"
    ):
        orchestrator.refresh_staleness(stale_at)

    availability_before = (
        orchestrator.ledgers["availability_transitions"].rows()
    )
    stale_before = orchestrator.ledgers["stale_recovery_transitions"].rows()
    availability_ids = {row["event_id"] for row in availability_before}
    stale_ids = {row["event_id"] for row in stale_before}
    assert len(availability_before) == len(availability_ids) == 5
    assert len(stale_before) == len(stale_ids) == 4
    assert all(row.get("evidence_identity") for row in availability_before)
    effective = {
        row["component"]: row["effective_timestamp"]
        for row in availability_before
    }
    assert effective["INDEX_STATE"] == (
        base + timedelta(seconds=10)
    ).isoformat()
    assert effective["FUTURES_STATE"] == (
        base + timedelta(milliseconds=500, seconds=10)
    ).isoformat()
    assert effective["HORIZON_ID"] == (
        base + timedelta(seconds=10)
    ).isoformat()
    assert all(
        row["effective_timestamp"] != stale_at.isoformat()
        for row in availability_before
    )

    # The state file still contains the pre-stale generation.  A new process
    # must recognize the durable transition rows and persist the later wall
    # clock without appending a second semantic freshness transition.
    restarted = LiveAnalyticalOrchestrator(runtime)
    assert restarted.refresh_staleness(stale_at + timedelta(seconds=30))
    assert restarted.ledgers["availability_transitions"].rows() == (
        availability_before
    )
    assert restarted.ledgers["stale_recovery_transitions"].rows() == stale_before
    assert {
        row["event_id"]
        for row in restarted.ledgers["availability_transitions"].rows()
    } == availability_ids
    assert {
        row["event_id"]
        for row in restarted.ledgers["stale_recovery_transitions"].rows()
    } == stale_ids

    persisted = LiveAnalyticalOrchestrator(runtime)
    availability = persisted.snapshot(SESSION, flush_dirty=False)["availability"]
    assert availability["layers"]["ID"]["state"] == "STALE_DATA"
    assert availability["divergence_state"] == "STALE_DATA"
    assert availability["reference_timestamp"] == (
        stale_at + timedelta(seconds=30)
    ).isoformat()


def test_stale_index_suspends_divergence_while_futures_remains_fresh(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
        observation(
            "O0003", "FUTURES", FUTURES,
            base + timedelta(seconds=9), price=57_021, volume=2,
        ),
    ])
    orchestrator.snapshot(SESSION)

    reference = base + timedelta(seconds=12)
    availability = orchestrator.operational_availability(reference)
    assert availability["index_state"] == "STALE_OR_MISSING"
    assert availability["futures_state"] == "AVAILABLE"
    assert availability["layers"]["ID"]["state"] == "STALE_DATA"
    assert availability["divergence_state"] == "STALE_DATA"
    assert availability["receipt_ages_seconds"]["INDEX"] == 12
    assert availability["receipt_ages_seconds"]["FUTURES"] == 3


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
    orchestrator.finalize_session(SESSION)

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


def test_operational_availability_reads_only_immutable_published_view(tmp_path):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    orchestrator.snapshot(SESSION)

    class WriterOwnedSessions(dict):
        def __contains__(self, _key):
            raise AssertionError("API traversed writer-owned sessions")

        def __getitem__(self, _key):
            raise AssertionError("API traversed writer-owned sessions")

        def __iter__(self):
            raise AssertionError("API traversed writer-owned sessions")

    orchestrator._sessions = WriterOwnedSessions()
    current = orchestrator.operational_availability(
        base + timedelta(seconds=5)
    )
    assert current["index_state"] == "AVAILABLE"
    assert current["futures_state"] == "AVAILABLE"
    assert current["receipt_ages_seconds"]["INDEX"] == 5
    assert current["receipt_ages_seconds"]["FUTURES"] == 4.5


def test_sealed_operational_view_keeps_snapshot_and_overlay_on_one_generation(
    tmp_path,
):
    base = datetime(2026, 8, 20, 9, 15, tzinfo=IST)
    orchestrator = LiveAnalyticalOrchestrator(contract(tmp_path))
    orchestrator.process([
        observation("O0001", "INDEX", INDEX, base, price=57_000, volume=0),
        observation(
            "O0002", "FUTURES", FUTURES,
            base + timedelta(milliseconds=500), price=57_020, volume=1,
        ),
    ])
    published = orchestrator.snapshot(SESSION)

    # Model the writer having built/swapped the next analytical output before
    # it publishes the corresponding composite operational generation.
    replacement = json.loads(json.dumps(published))
    replacement["session_date"] = "2026-08-21"
    replacement["availability"]["index_state"] = "STALE_OR_MISSING"
    orchestrator._outputs = {"2026-08-21": replacement}

    view, availability, causality = orchestrator.sealed_operational_generation(
        base + timedelta(seconds=5)
    )
    assert view["session_date"] == SESSION
    assert availability["index_state"] == "AVAILABLE"
    assert availability["futures_state"] == "AVAILABLE"
    assert availability["receipt_ages_seconds"]["INDEX"] == 5
    assert availability["receipt_ages_seconds"]["FUTURES"] == 4.5
    assert causality == published["public_causality_counters"]


def test_shadow_state_age_read_never_iterates_mutable_receipt_mapping():
    class ConcurrentReceipts(dict):
        def items(self):
            raise RuntimeError("dictionary changed size during iteration")

    ingestor = SimpleNamespace(
        latest_valid=ConcurrentReceipts({
            "INDEX": datetime.now(IST).isoformat(),
            "FUTURES": datetime.now(IST).isoformat(),
            "UNSAFE_DYNAMIC_KEY": datetime.now(IST).isoformat(),
        }),
        latest={},
    )
    ages = ShadowState(ingestor, {}).ages()
    assert set(ages) == {"INDEX", "FUTURES"}
    assert all(value is not None and value >= 0 for value in ages.values())


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
        orchestrator._cross_layer_contexts[session] = (
            orchestrator_module.cross_layer_state.empty_material_context()
        )
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
