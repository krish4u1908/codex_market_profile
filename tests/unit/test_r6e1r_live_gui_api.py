from __future__ import annotations

import json
import hashlib
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
import runpy
import threading
from types import MappingProxyType
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import banknifty_profiler.shadow.api as api_module
from banknifty_profiler.gui.adapter import PRODUCT_CLASSIFICATION, SESSIONS
from banknifty_profiler.shadow.api import create_server
from banknifty_profiler.shadow.ledger import AppendOnlyLedger
from banknifty_profiler.shadow.contracts import (
    CLASSIFICATION,
    engine_hash,
    engine_source_inventory,
    verify_engine_source_manifest,
)


class Ledger:
    def rows(self):
        return [{
            "event_id": "QUALITY-1", "session_date": "2026-08-19",
            "effective_timestamp": "2026-08-19T10:00:00+05:30",
            "publication_timestamp": "2026-08-19T10:00:00+05:30",
            "status": "REFUSED", "reason": "MALFORMED_RECORD",
            "detail": "secret-token /opt/private/raw.jsonl",
            "source_receipt_identifiers": {"file": "/opt/private/raw.jsonl"},
        }]


def availability(index="AVAILABLE", futures="AVAILABLE"):
    return {
        "overall_state": "LIVE_INTRADAY_ONLY",
        "market_display_enabled": True,
        "divergence_state": "AVAILABLE" if index == futures == "AVAILABLE" else "SUSPENDED_REQUIRED_INPUT_UNAVAILABLE",
        "participation_state": "AVAILABLE",
        "index_state": index, "futures_state": futures,
        "futures_oi_state": "AVAILABLE", "ce_state": "STALE_OR_MISSING",
        "pe_state": "AVAILABLE", "calculation_timestamp": "2026-08-19T10:00:03+05:30",
        "layers": {
            "3D": {"state": "MISSING_PRIOR_SESSION", "reason": "INSUFFICIENT_PRIOR_SESSIONS"},
            "2D": {"state": "MISSING_PRIOR_SESSION", "reason": "INSUFFICIENT_PRIOR_SESSIONS"},
            "1D": {"state": "AVAILABLE", "reason": "CACHED_RAW_PRIOR_CONTEXT"},
            "ID": {"state": "AVAILABLE", "reason": "FRESH_SYNCHRONIZED_MARKET"},
        },
    }


def snapshot(date="2026-08-19", state=None):
    layer_state = state or availability()
    price = {
        "fields": ["t", "i", "f", "b", "it", "ft", "a", "source_file"],
        "rows": [
            [f"{date}T10:00:00+05:30", 57000, 57080, 80, f"{date}T09:59:59.900000+05:30", f"{date}T10:00:00+05:30", 100, "/opt/private/raw.jsonl"],
            [f"{date}T10:00:01+05:30", 57001, 57082, 81, f"{date}T10:00:00.900000+05:30", f"{date}T10:00:01+05:30", 100, "/opt/private/raw.jsonl"],
        ],
    }
    families = (
        "BN_REF_FUT_VOLUME_VPOC", "FUT_POS_OI_VPOC", "FUT_NEG_OI_VPOC",
        "CE_POS_OI_VPOC", "CE_NEG_OI_VPOC", "PE_POS_OI_VPOC",
        "PE_NEG_OI_VPOC",
    )
    inventory = [
        {
            "evaluation_date": date,
            "horizon": horizon,
            "family": family,
            "sign": "VOLUME" if family == "BN_REF_FUT_VOLUME_VPOC" else (
                "POSITIVE" if "_POS_" in family else "NEGATIVE"
            ),
            "control_value": 57_000 + horizon_index * 20 + family_index * 5,
            "control_effective_timestamp": (
                f"{date}T{'10:00:00' if horizon == 'ID' else '09:15:00'}+05:30"
            ),
            "contract": "NSE:BANKNIFTY26AUGFUT",
            "expiry": "2026-08-27",
            "eligible_observation_count": 12,
            "excluded_observation_count": 0,
            "authority_basis": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
            "canonical_control_name": family,
            "user_facing_label": (
                "BN-REF FUT VOL-VPOC"
                if family == "BN_REF_FUT_VOLUME_VPOC" else family
            ),
            "source_file": "/opt/private/raw.jsonl",
            "raw_input_hashes": "secret-token",
        }
        for horizon_index, horizon in enumerate(("3D", "2D", "1D", "ID"))
        for family_index, family in enumerate(families)
    ]
    episodes = [{
        "episode_id": "BDR1-TEST", "evaluation_date": date, "colour": "GREEN",
        "confirmation_timestamp": f"{date}T10:00:01+05:30", "episode_end_timestamp": "",
        "index_at_confirmation": 57_001, "futures_at_confirmation": 57_082,
        "basis_at_confirmation": 81,
        "source_file": "/opt/private/raw.jsonl",
    }]
    dependencies = [{
        "episode_id": "BDR1-TEST",
        "dependency_group_id": f"HYP-{date}-001-GREEN",
        "classification": "NEW_INDEPENDENT_HYPOTHESIS",
        "retrigger_flag": False,
        "previous_episode_id": "",
        "reason_code": "FIRST_SESSION_EPISODE",
        "source_file": "/opt/private/raw.jsonl",
    }]
    lifecycle = [{
        "record_id": "LIFE-1", "episode_id": "BDR1-TEST", "state": "ACTIVE",
        "state_entry_timestamp": f"{date}T10:00:01+05:30", "reason_code": "FROZEN_STATE",
        "source_file": "/opt/private/raw.jsonl",
    }]
    resolution = [{
        "episode_id": "BDR1-TEST",
        "timestamp": f"{date}T10:00:02+05:30",
        "availability_timestamp": f"{date}T10:00:02+05:30",
        "resolution_mechanism_native": "FUTURES_LED_CONVERGENCE",
        "resolution_mechanism_compatibility": "BASIS_CONVERGENCE",
        "signed_basis_convergence": 4,
        "index_contribution": 1,
        "futures_contribution": 3,
        "source_file": "/opt/private/raw.jsonl",
    }]
    participation = [
        {
            "record_id": "PART-FUTURES-1",
            "view_record_kind": "FUTURES",
            "option_type": "",
            "symbol": "NSE:BANKNIFTY26AUGFUT",
            "observation_timestamp": f"{date}T10:00:02+05:30",
            "receipt_timestamp": f"{date}T10:00:01.900000+05:30",
            "receipt_age_seconds": 0.1,
            "price": 57_082,
            "oi": 1_200_000,
            "incremental_volume_5m": 1_000,
            "volume_percentile": 0.92,
            "volume_robust_z": 2.1,
            "delta_oi_1m": 10,
            "delta_oi_3m": 30,
            "delta_oi_5m": 50,
            "price_change_1m": 0,
            "price_change_3m": 6,
            "price_change_5m": 10,
            "inventory_state": "LONG_BUILDUP",
            "source_file": "/opt/private/oi.jsonl",
            "source_row": 98,
        },
        {
            "record_id": "PART-CE-1",
            "view_record_kind": "OPTION",
            "option_type": "CE",
            "symbol": "NSE:BANKNIFTY26AUG57000CE",
            "strike": 57_000,
            "expiry": "2026-08-27",
            "moneyness": "ATM",
            "observation_timestamp": f"{date}T10:00:02.100000+05:30",
            "receipt_timestamp": f"{date}T10:00:02+05:30",
            "receipt_age_seconds": 0.1,
            "premium": 240,
            "oi": 600_000,
            "incremental_volume_5m": 500,
            "volume_percentile": 0.85,
            "volume_robust_z": 1.7,
            "delta_oi_1m": 5,
            "delta_oi_3m": 15,
            "delta_oi_5m": 25,
            "premium_change_1m": 0,
            "premium_change_3m": 4,
            "premium_change_5m": 7,
            "semantic_classification": "SUPPORTIVE",
            "source_file": "/opt/private/oi.jsonl",
            "source_row": 99,
        },
        {
            "record_id": "PART-PE-1",
            "view_record_kind": "OPTION",
            "option_type": "PE",
            "symbol": "NSE:BANKNIFTY26AUG57000PE",
            "strike": 57_000,
            "expiry": "2026-08-27",
            "moneyness": "ATM",
            "observation_timestamp": f"{date}T10:00:02.200000+05:30",
            "receipt_timestamp": f"{date}T10:00:02.100000+05:30",
            "receipt_age_seconds": 0.1,
            "premium": 220,
            "oi": 550_000,
            "incremental_volume_5m": 450,
            "volume_percentile": 0.81,
            "volume_robust_z": 1.5,
            "delta_oi_1m": -4,
            "delta_oi_3m": -12,
            "delta_oi_5m": -20,
            "premium_change_1m": -1,
            "premium_change_3m": -3,
            "premium_change_5m": -6,
            "semantic_classification": "CONTRADICTORY",
            "source_file": "/opt/private/oi.jsonl",
            "source_row": 100,
        },
    ]
    participation_transitions = [
        {
            "transition_id": "PT-FUTURES-1",
            "episode_id": "BDR1-TEST",
            "dependency_group_id": f"HYP-{date}-001-GREEN",
            "component": "FUTURES",
            "previous_state": "UNOBSERVED",
            "new_state": "LONG_BUILDUP",
            "effective_timestamp": f"{date}T10:00:01.900000+05:30",
            "evidence_receipt_timestamp": f"{date}T10:00:01.900000+05:30",
            "calculation_timestamp": f"{date}T10:00:02+05:30",
            "reason_code": "MATERIAL_FUTURES_STATE_CHANGE",
            "raw_source_references": "/opt/private/oi.jsonl:98",
        },
        {
            "transition_id": "PT-CE-1",
            "episode_id": "BDR1-TEST",
            "dependency_group_id": f"HYP-{date}-001-GREEN",
            "component": "CE",
            "previous_state": "UNOBSERVED",
            "new_state": "NEUTRAL",
            "effective_timestamp": f"{date}T10:00:01.500000+05:30",
            "evidence_receipt_timestamp": f"{date}T10:00:01.500000+05:30",
            "calculation_timestamp": f"{date}T10:00:02+05:30",
            "reason_code": "MATERIAL_STRIKE_STATE_CHANGE",
        },
        {
            "transition_id": "PT-CE-2",
            "episode_id": "BDR1-TEST",
            "dependency_group_id": f"HYP-{date}-001-GREEN",
            "component": "CE",
            "previous_state": "NEUTRAL",
            "new_state": "SUPPORTIVE",
            "effective_timestamp": f"{date}T10:00:02+05:30",
            "evidence_receipt_timestamp": f"{date}T10:00:02+05:30",
            "calculation_timestamp": f"{date}T10:00:02.100000+05:30",
            "reason_code": "MATERIAL_STRIKE_STATE_CHANGE",
        },
        {
            "transition_id": "PT-PE-1",
            "episode_id": "BDR1-TEST",
            "dependency_group_id": f"HYP-{date}-001-GREEN",
            "component": "PE",
            "previous_state": "UNOBSERVED",
            "new_state": "CONTRADICTORY",
            "effective_timestamp": f"{date}T10:00:02.100000+05:30",
            "evidence_receipt_timestamp": f"{date}T10:00:02.100000+05:30",
            "calculation_timestamp": f"{date}T10:00:02.200000+05:30",
            "reason_code": "MATERIAL_STRIKE_STATE_CHANGE",
        },
    ]
    cross_layer_transitions = [
        {
            "transition_id": "XL-INVENTORY-1",
            "evaluation_date": date,
            "effective_timestamp": f"{date}T10:00:00+05:30",
            "component": "INVENTORY",
            "state_key": "ID:FUT_POS_OI_VPOC",
            "previous_state": "NOT_YET_AVAILABLE",
            "new_state": "AVAILABLE:57060",
            "reason_code": "CONTROL_AVAILABLE_OR_WINNER_CHANGED",
            "episode_id": "",
            "horizon": "ID",
            "family": "FUT_POS_OI_VPOC",
            "constituent_effective_timestamps": (
                f'{{"control_effective_timestamp":"{date}T10:00:00+05:30"}}'
            ),
            "source_record_id": "inventory:1",
            "source_file": "/opt/private/raw.jsonl",
        },
        {
            "transition_id": "XL-DIVERGENCE-1",
            "evaluation_date": date,
            "effective_timestamp": f"{date}T10:00:01+05:30",
            "component": "DIVERGENCE",
            "state_key": "BDR1-TEST",
            "previous_state": "CANDIDATE",
            "new_state": "GREEN_CONFIRMED",
            "reason_code": "FROZEN_DIVERGENCE_CONFIRMED",
            "episode_id": "BDR1-TEST",
            "horizon": "",
            "family": "",
            "constituent_effective_timestamps": (
                f'{{"confirmation_timestamp":"{date}T10:00:01+05:30"}}'
            ),
            "source_record_id": "episode:1",
            "raw_source_references": "secret-token /opt/private/raw.jsonl:101",
        },
    ]
    gui = {
        "date": date, "classification": PRODUCT_CLASSIFICATION, "availability": layer_state,
        "price": price, "projection_hash": "a" * 64,
    }
    return {
        "session_date": date, "availability": layer_state, "gui_payload": gui,
        "inventory": inventory, "episodes": episodes, "dependencies": dependencies,
        "lifecycle": lifecycle, "resolution": resolution,
        "participation_dense": participation,
        "participation_transitions": participation_transitions,
        "participation_summaries": [],
        "cross_layer_transitions": cross_layer_transitions,
        "counts": {
            "price": 2,
            "inventory": len(inventory),
            "dependencies": len(dependencies),
            "participation_dense": len(participation),
            "participation_transitions": len(participation_transitions),
            "cross_layer_transitions": len(cross_layer_transitions),
        },
    }


def crossed_clock_snapshot(date="2026-08-19", state=None):
    """Two valid backward joins whose Index/Futures path order is crossed."""
    value = snapshot(date=date, state=state)
    value["gui_payload"]["price"] = {
        "fields": ["t", "i", "f", "b", "it", "ft", "a", "source_file"],
        "rows": [
            [
                f"{date}T10:00:01+05:30", 57_000, 57_082, 82,
                f"{date}T09:59:59.500000+05:30",
                f"{date}T10:00:01+05:30", 1_500,
                "/opt/private/raw.jsonl",
            ],
            [
                f"{date}T10:00:00+05:30", 57_001, 57_080, 79,
                f"{date}T09:59:59.900000+05:30",
                f"{date}T10:00:00+05:30", 100,
                "/opt/private/raw.jsonl",
            ],
        ],
    }
    return value


class Orchestrator:
    def __init__(self, latest):
        self.outputs = {date: snapshot(date) for date in SESSIONS}
        self.latest = latest
        self.causality = {
            "valid_basis_pairs": 2,
            "future_joins": 0,
            "synchronization_tolerance_violations": 0,
        }

    def snapshot(self, date=None, *, flush_dirty=False):
        assert flush_dirty is False
        return self.outputs.get(date, self.latest) if date else self.latest

    def snapshot_all(self, *, flush_dirty=False):
        assert flush_dirty is False
        return self.outputs

    def causality_metrics(self):
        return dict(self.causality)


class Ingestor:
    _static_root = Path("src/banknifty_profiler/gui/static")
    _static_inventory = []
    for _static_name in ("live.js", "live_page.template", "style.css"):
        _static_payload = (_static_root / _static_name).read_bytes()
        _static_inventory.append({
            "path": f"src/banknifty_profiler/gui/static/{_static_name}",
            "size": len(_static_payload),
            "sha256": hashlib.sha256(_static_payload).hexdigest(),
        })
    c = {
        "config": {"classification": PRODUCT_CLASSIFICATION},
        "engine_hash": "b" * 64,
        "configuration_hash": "c" * 64,
        "engine_source_verified": True,
        "engine_source_inventory": _static_inventory,
        "runtime_source_open_audit": {"prohibited_open_count": 0},
    }
    metrics = {"polls": 10, "bytes": 2000}
    latest = {
        "INDEX": "2026-08-19T10:00:01+05:30",
        "FUTURES": "2026-08-19T10:00:01+05:30",
        "CE": "2026-08-19T10:00:00+05:30",
        "raw_path": "/opt/private/raw.jsonl",
    }
    ledgers = {"refusals_data_quality": Ledger()}

    def checkpoint_health(self):
        return {"valid": True}


class State:
    started = None

    def __init__(self, value=None):
        self.value = value or snapshot()
        self.orchestrator = Orchestrator(self.value)
        self.ingestor = Ingestor()

    def analytical_snapshot(self):
        return self.value

    def availability(self):
        return self.value["availability"]

    def ages(self):
        return {"INDEX": 1, "FUTURES": 1, "CE": 181, "raw_path": 1}

    def readiness(self):
        return {
            "ready": True, "reasons": [], "engine_hash": "b" * 64,
            "configuration_hash": "c" * 64, "checkpoint_valid": True,
            "future_joins": 0, "synchronization_tolerance_violations": 0,
            "manifest_verified": True,
        }


@pytest.fixture
def server():
    value = create_server(State(), "127.0.0.1", 0)
    thread = threading.Thread(target=value.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{value.server_address[1]}"
    finally:
        value.shutdown()
        thread.join()
        value.server_close()


def request(base, path, method="GET"):
    try:
        with urlopen(Request(base + path, method=method)) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def test_all_required_read_only_endpoints(server):
    for path in (
        "health", "readiness", "status", "session", "chart", "inventory",
        "divergence", "lifecycle", "participation", "transitions",
        "availability", "audit",
    ):
        status, headers, body = request(server, f"/api/{path}")
        assert status == 200, path
        assert json.loads(body)
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"


def test_api_never_exposes_raw_rows_paths_or_secrets(server):
    combined = b""
    for path in (
        "/api/status", "/api/session", "/api/chart", "/api/inventory",
        "/api/divergence", "/api/lifecycle", "/api/participation",
        "/api/transitions", "/api/availability", "/api/audit",
    ):
        combined += request(server, path)[2]
    text = combined.decode()
    for prohibited in ("/opt/private", "secret-token", "source_file", "source_row", "raw_input_hashes"):
        assert prohibited not in text


def test_chart_has_separate_multi_point_clocks_and_canonical_basis(server):
    chart = json.loads(request(server, "/api/chart")[2])
    assert chart["price"]["fields"] == ["t", "i", "f", "b", "it", "ft", "a"]
    assert len(chart["price"]["rows"]) == 2
    assert chart["price"]["rows"][0][4] != chart["price"]["rows"][0][5]
    assert chart["price"]["rows"][0][3] == 80
    for row in chart["price"]["rows"]:
        basis_clock = datetime.fromisoformat(row[0])
        index_clock = datetime.fromisoformat(row[4])
        futures_clock = datetime.fromisoformat(row[5])
        age_ms = (futures_clock - index_clock).total_seconds() * 1_000
        assert basis_clock == futures_clock
        assert 0 <= age_ms <= 2_000
        assert row[6] == pytest.approx(age_ms)
    assert chart["availability"]["layers"]["3D"]["state"] == "MISSING_PRIOR_SESSION"
    assert chart["availability"]["layers"]["ID"]["state"] == "AVAILABLE"


def test_chart_projects_canonical_dependency_and_complete_participation(server):
    chart = json.loads(request(server, "/api/chart")[2])
    assert chart["dependencies"]["fields"] == [
        "episode_id", "dependency_group_id", "classification", "retrigger_flag",
        "previous_episode_id", "reason_code",
    ]
    dependency = dict(zip(
        chart["dependencies"]["fields"], chart["dependencies"]["rows"][0],
    ))
    assert dependency == {
        "episode_id": "BDR1-TEST",
        "dependency_group_id": "HYP-2026-08-19-001-GREEN",
        "classification": "NEW_INDEPENDENT_HYPOTHESIS",
        "retrigger_flag": False,
        "previous_episode_id": "",
        "reason_code": "FIRST_SESSION_EPISODE",
    }
    assert chart["counts"]["dependencies"] == 1

    payload = json.loads(request(server, "/api/participation")[2])
    rows = {row["record_id"]: row for row in payload["rows"]}
    assert rows["PART-FUTURES-1"]["price_change_1m"] == 0
    assert [rows["PART-FUTURES-1"][f"price_change_{window}"] for window in ("1m", "3m", "5m")] == [0, 6, 10]
    assert [rows["PART-CE-1"][f"premium_change_{window}"] for window in ("1m", "3m", "5m")] == [0, 4, 7]
    assert [rows["PART-PE-1"][f"premium_change_{window}"] for window in ("1m", "3m", "5m")] == [-1, -3, -6]
    assert {row["component"] for row in payload["transitions"]} == {
        "FUTURES", "CE", "PE",
    }
    assert [
        row["new_state"] for row in payload["transitions"]
        if row["component"] == "CE"
    ] == ["NEUTRAL", "SUPPORTIVE"]
    assert "raw_source_references" not in json.dumps(payload)


def test_transitions_endpoint_projects_allowlisted_cross_layer_tail(server):
    payload = json.loads(request(server, "/api/transitions?limit=1")[2])
    assert payload["session_date"] == "2026-08-19"
    assert payload["count"] == 2
    assert payload["returned_count"] == 1
    assert payload["truncated"] is True
    assert payload["rows"] == [{
        "transition_id": "XL-DIVERGENCE-1",
        "evaluation_date": "2026-08-19",
        "effective_timestamp": "2026-08-19T10:00:01+05:30",
        "component": "DIVERGENCE",
        "state_key": "BDR1-TEST",
        "previous_state": "CANDIDATE",
        "new_state": "GREEN_CONFIRMED",
        "reason_code": "FROZEN_DIVERGENCE_CONFIRMED",
        "episode_id": "BDR1-TEST",
        "horizon": "",
        "family": "",
    }]
    assert payload["participation_count"] == 4
    assert len(payload["participation_rows"]) == 1
    assert payload["participation_rows"][0]["transition_id"] == "PT-PE-1"
    encoded = json.dumps(payload)
    for prohibited in (
        "constituent_effective_timestamps", "source_record_id",
        "raw_source_references", "/opt/private", "secret-token",
    ):
        assert prohibited not in encoded


def test_api_preserves_crossed_canonical_clocks_without_repairing_them():
    value = State(crossed_clock_snapshot())
    service = create_server(value, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        chart = json.loads(request(base, "/api/chart")[2])
        rows = chart["price"]["rows"]
        # The API preserves the analytical publication order. The browser must
        # independently sort each rendered path on its own canonical clock.
        assert [row[0] for row in rows] == [
            "2026-08-19T10:00:01+05:30",
            "2026-08-19T10:00:00+05:30",
        ]
        for row in rows:
            basis_clock = datetime.fromisoformat(row[0])
            index_clock = datetime.fromisoformat(row[4])
            futures_clock = datetime.fromisoformat(row[5])
            age_ms = (futures_clock - index_clock).total_seconds() * 1_000
            assert basis_clock == futures_clock
            assert 0 <= age_ms <= 2_000
            assert row[6] == pytest.approx(age_ms)
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_verified_replay_selection_and_arbitrary_date_refusal(server):
    for date in SESSIONS:
        session = json.loads(request(server, f"/api/session?date={date}")[2])
        chart = json.loads(request(server, f"/api/chart?date={date}")[2])
        assert session["mode"] == "HISTORICAL_REPLAY"
        assert session["session_date"] == chart["session_date"] == date
    status, _, body = request(server, "/api/chart?date=2026-08-17")
    assert status == 400
    assert json.loads(body)["error"] == "UNVERIFIED_SESSION"


def test_verified_but_absent_replay_is_explicitly_unavailable():
    value = State()
    missing = SESSIONS[0]
    del value.orchestrator.outputs[missing]
    service = create_server(value, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        for endpoint in ("session", "chart", "inventory"):
            status, _, body = request(
                base, f"/api/{endpoint}?date={missing}"
            )
            assert status == 404
            assert json.loads(body)["error"] == "REPLAY_SESSION_UNAVAILABLE"
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_live_latest_uses_wall_clock_staleness_but_replay_remains_sealed():
    class OperationallyStale(State):
        def availability(self):
            stale = availability("STALE_OR_MISSING", "STALE_OR_MISSING")
            stale["overall_state"] = "STALE_PARTIAL"
            stale["divergence_state"] = "STALE_DATA"
            stale["layers"]["ID"] = {
                "state": "STALE_DATA", "reason": "MARKET_INPUT_STALE_OR_MISSING",
            }
            stale["receipt_ages_seconds"] = {"INDEX": 600, "FUTURES": 600}
            return stale

    value = OperationallyStale()
    service = create_server(value, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        status, _, body = request(base, "/api/readiness")
        assert status == 503
        assert "STALE_DATA" in json.loads(body)["reasons"]
        latest = json.loads(request(base, "/api/chart")[2])
        assert latest["stale_warning"] is True
        assert latest["warning_reason"] == "STALE_DATA"
        assert latest["display_state"] == "LAST_VALID_CHART_WITH_STALE_WARNING"
        assert len(latest["price"]["rows"]) == 2
        replay = json.loads(
            request(base, f"/api/chart?date={SESSIONS[-1]}")[2]
        )
        assert replay["stale_warning"] is False
        assert replay["availability"]["index_state"] == "AVAILABLE"
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_health_stays_up_while_stale_readiness_is_503():
    stale = availability("STALE_OR_MISSING", "STALE_OR_MISSING")
    value = State(snapshot(state=stale))
    service = create_server(value, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        assert request(base, "/api/health")[0] == 200
        status, _, body = request(base, "/api/readiness")
        assert status == 503
        assert "STALE_DATA" in json.loads(body)["reasons"]
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_static_live_gui_and_head_are_available(server):
    status, headers, body = request(server, "/")
    assert status == 200
    assert PRODUCT_CLASSIFICATION.encode() in body
    assert b"/assets/live.js" in body
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    status, _, body = request(server, "/api/health", "HEAD")
    assert status == 200 and body == b""


def test_static_assets_are_immutable_after_server_start(tmp_path, monkeypatch):
    source_root = Path("src/banknifty_profiler/gui/static")
    for name in ("live_page.template", "live.js", "style.css"):
        (tmp_path / name).write_bytes((source_root / name).read_bytes())
    monkeypatch.setattr(api_module, "STATIC_ROOT", tmp_path)
    expected = (tmp_path / "live.js").read_bytes()
    service = api_module.create_server(State(), "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        (tmp_path / "live.js").write_bytes(b"MUTATED_UNVERIFIED_BROWSER_CODE")
        status, _, body = request(base, "/assets/live.js")
        assert status == 200
        assert body == expected
        assert b"MUTATED_UNVERIFIED_BROWSER_CODE" not in body
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_static_mutation_between_contract_and_server_start_is_refused(
    tmp_path, monkeypatch,
):
    source_root = Path("src/banknifty_profiler/gui/static")
    for name in ("live_page.template", "live.js", "style.css"):
        (tmp_path / name).write_bytes((source_root / name).read_bytes())
    monkeypatch.setattr(api_module, "STATIC_ROOT", tmp_path)
    (tmp_path / "live.js").write_bytes(b"MUTATED_BEFORE_SERVER_START")
    with pytest.raises(ValueError, match="static asset identity mismatch"):
        api_module.create_server(State(), "127.0.0.1", 0)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutating_methods_are_refused(server, method):
    status, _, body = request(server, "/api/status", method)
    assert status == 405
    assert json.loads(body)["error"] == "READ_ONLY_API"


@pytest.mark.parametrize("path", ["/api/order", "/api/trade", "/api/alert", "/api/write", "/private"])
def test_no_mutating_or_arbitrary_routes_exist(server, path):
    assert request(server, path)[0] == 404


def test_live_gui_has_persistent_master_child_controls_and_no_analytics():
    root = Path("src/banknifty_profiler/gui/static")
    source = (root / "live.js").read_text()
    page = (root / "live_page.template").read_text()
    assert "localStorage" in source
    assert "data-master" in source and "data-child" in source
    assert "state.settings.masters" in source and "state.settings.children" in source
    assert "i - f" not in source and "f - i" not in source
    assert "synchronization_tolerance_ms" not in source
    assert "SUCCESS" not in page + source and "FAILURE" not in page + source
    assert page.index('data-market="index"') < page.index('data-market="futures"')
    assert "STALE DATA · LAST VALID CHART" in source


def test_offline_replay_also_persists_toggle_selection():
    source = Path("src/banknifty_profiler/gui/static/app.js").read_text()
    assert "r6d-replay-display-v1" in source
    assert "saveToggles" in source


def test_repeated_api_reads_never_trigger_analytical_flush():
    class CountingOrchestrator(Orchestrator):
        def __init__(self, latest):
            super().__init__(latest)
            self.reads = 0
            self.flushes = 0

        def snapshot(self, date=None, *, flush_dirty=True):
            self.reads += 1
            if flush_dirty:
                self.flushes += 1
            return self.outputs.get(date, self.latest) if date else self.latest

        def snapshot_all(self, *, flush_dirty=True):
            self.reads += 1
            if flush_dirty:
                self.flushes += 1
            return self.outputs

    runtime = State()
    runtime.orchestrator = CountingOrchestrator(runtime.value)
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        for _ in range(3):
            for path in ("/api/health", "/api/status", "/api/chart", "/api/session"):
                assert request(base, path)[0] == 200
        assert runtime.orchestrator.reads > 0
        assert runtime.orchestrator.flushes == 0
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_bounded_api_prefers_sealed_view_and_projects_only_requested_tail():
    class TailObservedRows(list):
        def __init__(self, rows):
            super().__init__(rows)
            self.iterations = 0
            self.slices = []

        def __iter__(self):
            self.iterations += 1
            raise AssertionError("bounded endpoint iterated the complete dense artifact")

        def __getitem__(self, key):
            if isinstance(key, slice):
                self.slices.append(key)
            return super().__getitem__(key)

    runtime = State()
    published = dict(runtime.value)
    dense = TailObservedRows(runtime.value["participation_dense"])
    assert len(dense) > 1
    published["participation_dense"] = dense

    class SealedViewOrchestrator(Orchestrator):
        def __init__(self, latest):
            super().__init__(latest)
            self.view_reads = 0
            self.snapshot_reads = 0

        def sealed_read_view(self, date=None):
            self.view_reads += 1
            value = self.outputs.get(date, published) if date else published
            return MappingProxyType(value)

        def snapshot(self, date=None, *, flush_dirty=True):
            self.snapshot_reads += 1
            raise AssertionError("public API requested a full copied snapshot")

    runtime.value = published
    runtime.orchestrator = SealedViewOrchestrator(published)
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        payload = json.loads(request(base, "/api/participation?limit=1")[2])
        assert payload["count"] == len(dense)
        assert payload["returned_count"] == 1
        assert len(payload["rows"]) == 1
        assert runtime.orchestrator.view_reads == 1
        assert runtime.orchestrator.snapshot_reads == 0
        assert dense.iterations == 0
        assert dense.slices == [slice(-1, None, None)]
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_live_api_captures_snapshot_and_availability_from_one_generation():
    older = snapshot("2026-08-19", availability())
    newer = snapshot(
        "2026-08-20", availability(index="STALE_OR_MISSING"),
    )

    class CompositeOrchestrator(Orchestrator):
        def __init__(self):
            super().__init__(newer)
            self.composite_reads = 0

        def sealed_operational_read_view(self):
            self.composite_reads += 1
            return (
                MappingProxyType(older),
                MappingProxyType(older["availability"]),
            )

        def sealed_read_view(self, date=None):
            raise AssertionError("live API split the composite read generation")

    runtime = State(newer)
    runtime.orchestrator = CompositeOrchestrator()
    runtime.availability = lambda: (_ for _ in ()).throw(
        AssertionError("live API independently read operational availability")
    )
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        payload = json.loads(request(base, "/api/chart")[2])
        assert payload["session_date"] == "2026-08-19"
        assert payload["availability"]["index_state"] == "AVAILABLE"
        assert payload["availability"]["futures_state"] == "AVAILABLE"
        assert runtime.orchestrator.composite_reads == 1
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_chart_uses_sealed_material_resolution_without_dense_rescan():
    class DenseResolution(list):
        def __init__(self, rows):
            super().__init__(rows)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            raise AssertionError("chart iterated the dense resolution ledger")

    runtime = State()
    published = dict(runtime.value)
    dense = DenseResolution(runtime.value["resolution"] * 100)
    published["resolution"] = dense
    gui = dict(runtime.value["gui_payload"])
    gui["resolution_mechanisms"] = {
        "fields": [
            "episode_id", "timestamp", "availability_timestamp",
            "resolution_mechanism_native",
            "resolution_mechanism_compatibility",
        ],
        "rows": [[
            "BDR1-TEST", "2026-08-19T10:00:02+05:30",
            "2026-08-19T10:00:02+05:30", "FUTURES_LED_CONVERGENCE",
            "BASIS_CONVERGENCE",
        ]],
    }
    published["gui_payload"] = gui

    class MaterialViewOrchestrator(Orchestrator):
        def sealed_read_view(self, date=None):
            return MappingProxyType(published)

    runtime.value = published
    runtime.orchestrator = MaterialViewOrchestrator(published)
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        payload = json.loads(request(base, "/api/chart")[2])
        assert payload["counts"]["resolution_mechanisms"] == 1
        assert payload["resolution_mechanisms"]["rows"][0][0] == "BDR1-TEST"
        assert dense.iterations == 0
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_audit_and_readiness_use_runtime_wide_sealed_causality():
    runtime = State()
    published = dict(runtime.value)
    published["public_causality_counters"] = {
        "valid_basis_pairs": 7,
        "future_joins": 0,
        "synchronization_tolerance_violations": 0,
    }

    class SealedCausalityOrchestrator(Orchestrator):
        def sealed_operational_generation(self):
            return (
                MappingProxyType(published),
                MappingProxyType(published["availability"]),
                MappingProxyType({
                    "valid_basis_pairs": 11,
                    "future_joins": 2,
                    "synchronization_tolerance_violations": 3,
                }),
            )

        def causality_metrics(self):
            raise AssertionError("API split the sealed operational generation")

    runtime.value = published
    runtime.orchestrator = SealedCausalityOrchestrator(published)
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        audit = json.loads(request(base, "/api/audit")[2])
        assert audit["future_joins"] == 2
        assert audit["synchronization_tolerance_violations"] == 3
        status, _, body = request(base, "/api/readiness")
        readiness = json.loads(body)
        assert status == 503
        assert readiness["ready"] is False
        assert "FUTURE_JOIN_DETECTED" in readiness["reasons"]
        assert "SYNCHRONIZATION_TOLERANCE_VIOLATION" in readiness["reasons"]
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_audit_double_collects_one_stable_production_ledger_vector():
    class GenerationalLedger:
        def __init__(self, snapshots):
            self.snapshots = snapshots
            self.calls = 0

        def audit_snapshot(self):
            value = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
            self.calls += 1
            return value

    def audit_value(generation, count):
        return {
            "row_count": count,
            "duplicate_ids": 0,
            "timestamp_backdating": 0,
            "tail": [],
            "generation": (
                True, 1, generation, count, generation, generation,
                hashlib.sha256(str(generation).encode()).hexdigest(),
            ),
        }

    first = GenerationalLedger([
        audit_value(1, 1), audit_value(2, 2),
        audit_value(2, 2), audit_value(2, 2),
    ])
    second = GenerationalLedger([audit_value(10, 1)] * 4)
    runtime = State()
    runtime.ingestor.ledgers = {
        "normalized_raw_events": first,
        "raw_file_checkpoints": second,
    }
    runtime.ingestor._normalized_seen = {"A", "B"}
    runtime.ingestor._checkpoint_seen = {"C"}
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        audit = json.loads(request(base, "/api/audit")[2])
        assert audit["measured_ledger_rows"] == 3
        assert audit["duplicate_analytical_ids"] == 0
        assert first.calls == second.calls == 4
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_audit_fails_closed_on_producer_identity_index_mismatch(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "normalized.jsonl")
    ledger.append({"event_id": "A"})
    ledger.append({"event_id": "A"})
    runtime = State()
    runtime.ingestor.ledgers = {"normalized_raw_events": ledger}
    runtime.ingestor._normalized_seen = {"A"}
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        status, _, body = request(base, "/api/audit")
        assert status == 500
        assert json.loads(body) == {"error": "INTERNAL_STATE_UNAVAILABLE"}
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_audit_limit_and_repeated_concurrent_reads_use_incremental_sealed_cache():
    class NoDenseIteration(list):
        def __init__(self, rows):
            super().__init__(rows)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            raise AssertionError("audit request iterated dense analytical rows")

    class IncrementalAuditLedger:
        def __init__(self):
            self.values = [self.row(1), self.row(2)]
            self.scan_sizes = []
            self.rows_calls = 0

        @staticmethod
        def row(ordinal):
            instant = f"2026-08-19T10:00:0{ordinal}+05:30"
            return {
                "event_id": f"QUALITY-{ordinal}",
                "session_date": "2026-08-19",
                "effective_timestamp": instant,
                "publication_timestamp": instant,
                "status": "REFUSED",
                "reason": f"REASON-{ordinal}",
            }

        def scan_from(self, boundary, consume):
            start = 0 if boundary is None else boundary
            pending = self.values[start:]
            self.scan_sizes.append(len(pending))
            for row in pending:
                consume(row)
            return len(self.values)

        def rows(self):
            self.rows_calls += 1
            raise AssertionError("audit endpoint loaded the complete ledger")

    runtime = State()
    published = dict(runtime.value)
    dense = NoDenseIteration(runtime.value["participation_dense"])
    published["participation_dense"] = dense
    published["public_audit_counters"] = {
        "timestamp_backdating": 0,
        "duplicate_analytical_ids": 0,
        "measured_snapshot_rows": 987,
    }

    class SealedAuditOrchestrator(Orchestrator):
        def sealed_read_view(self, date=None):
            return MappingProxyType(published)

        def snapshot(self, date=None, *, flush_dirty=True):
            raise AssertionError("audit endpoint requested a full snapshot")

    ledger = IncrementalAuditLedger()
    runtime.value = published
    runtime.orchestrator = SealedAuditOrchestrator(published)
    runtime.ingestor.ledgers = {"refusals_data_quality": ledger}
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        first = json.loads(request(base, "/api/audit?limit=1")[2])
        second = json.loads(request(base, "/api/audit?limit=1")[2])
        assert first["refusal_count"] == second["refusal_count"] == 2
        assert first["refusals"][0]["event_id"] == "QUALITY-2"
        assert first["measured_ledger_rows"] == 2
        assert first["measured_snapshot_rows"] == 987

        ledger.values.append(ledger.row(3))
        responses = []

        def read_audit():
            responses.append(
                json.loads(request(base, "/api/audit?limit=1")[2])
            )

        readers = [threading.Thread(target=read_audit) for _ in range(6)]
        for reader in readers:
            reader.start()
        for reader in readers:
            reader.join()
        assert len(responses) == 6
        assert all(value["refusal_count"] == 3 for value in responses)
        assert all(
            value["refusals"][0]["event_id"] == "QUALITY-3"
            for value in responses
        )
        assert all(value["measured_ledger_rows"] == 3 for value in responses)
        assert ledger.rows_calls == 0
        assert ledger.scan_sizes[0:2] == [2, 0]
        assert sum(ledger.scan_sizes) == 3
        assert dense.iterations == 0
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_audit_fails_closed_on_naive_publication_clock():
    class InvalidClockLedger:
        def __init__(self):
            self.scanned = False

        def scan_from(self, boundary, consume):
            if not self.scanned:
                consume({
                    "event_id": "QUALITY-INVALID-CLOCK",
                    "effective_timestamp": "2026-08-19T10:00:00+05:30",
                    "publication_timestamp": "2026-08-19T10:00:01",
                })
                self.scanned = True
            return 1

    runtime = State()
    runtime.ingestor.ledgers = {
        "refusals_data_quality": InvalidClockLedger(),
    }
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        status, _, body = request(base, "/api/audit?limit=1")
        assert status == 500
        assert json.loads(body) == {"error": "INTERNAL_STATE_UNAVAILABLE"}
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_external_gateway_query_allowlist_is_exact():
    gateway = runpy.run_path("deploy/r6e1r/read_only_gateway.py")
    safe_query = gateway["safe_query"]
    assert safe_query("/api/chart", "date=2026-08-19") == "date=2026-08-19"
    assert safe_query("/api/inventory", "limit=100&date=2026-08-19") == "date=2026-08-19&limit=100"
    assert safe_query("/api/chart", "date=2026-08-17") is None
    assert safe_query("/api/chart", "target=http://example.invalid") is None
    assert safe_query("/api/chart", "target=") is None
    assert safe_query("/api/chart", "date=2026-08-19&date=2026-08-20") is None
    assert safe_query("/api/chart", "date=2026-08-19&limit=100") is None
    assert safe_query("/assets/live.js", "date=2026-08-19") is None
    assert "/api/order" not in gateway["ROUTES"]


def test_external_gateway_proxies_only_allowlisted_get_and_head(server):
    module = runpy.run_path("deploy/r6e1r/read_only_gateway.py")
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), module["handler_for"](server))
    thread = threading.Thread(target=gateway.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{gateway.server_address[1]}"
    try:
        assert request(base, "/")[0] == 200
        assert request(base, "/api/chart?date=2026-08-19")[0] == 200
        assert request(base, "/api/chart?upstream=http://example.invalid")[0] == 404
        assert request(base, "/api/order")[0] == 404
        status, _, body = request(base, "/api/health", "HEAD")
        assert status == 200 and body == b""
        assert request(base, "/api/status", "POST")[0] == 405
    finally:
        gateway.shutdown(); thread.join(); gateway.server_close()


def test_gateway_logs_only_normalized_metadata(server, capsys):
    module = runpy.run_path("deploy/r6e1r/read_only_gateway.py")
    gateway = ThreadingHTTPServer(
        ("127.0.0.1", 0), module["handler_for"](server)
    )
    thread = threading.Thread(target=gateway.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{gateway.server_address[1]}"
    attacker_value = "do-not-log-secret-value"
    try:
        assert request(
            base, f"/api/chart?target={attacker_value}"
        )[0] == 404
        assert request(base, "/api/inventory?date=2026-08-19&limit=10")[0] == 200
    finally:
        gateway.shutdown(); thread.join(); gateway.server_close()
    output = capsys.readouterr().out
    assert attacker_value not in output
    assert "target" not in output
    records = [json.loads(line) for line in output.splitlines() if line]
    assert records
    assert all(set(record) == {
        "component", "method", "route", "query_keys", "status",
    } for record in records)
    assert records[0]["route"] == "/api/chart"
    assert records[0]["query_keys"] == []
    assert records[0]["status"] == 404
    assert records[1]["query_keys"] == ["date", "limit"]


def test_service_templates_keep_backend_local_and_ports_isolated():
    root = Path("deploy/r6e1r")
    backend = (root / "r6e1r-shadow.service").read_text()
    gateway = (root / "r6e1r-readonly-gateway.service").read_text()
    combined = backend + gateway
    assert "--bind 127.0.0.1 --port 18805" in backend
    assert (
        "--port @R6E1R_GATEWAY_PORT@ --backend http://127.0.0.1:18805"
        in gateway
    )
    assert "/opt/" not in backend + gateway
    assert "8803" not in combined and "8804" not in combined
    assert ".env" not in combined
    assert not any(
        line.startswith("Environment=") for line in combined.splitlines()
    )


def test_audit_reports_measured_nonzero_runtime_values():
    class AuditLedger:
        def rows(self):
            return [
                {
                    "event_id": "DUPLICATE", "session_date": "2026-08-19",
                    "effective_timestamp": "2026-08-19T10:00:02+05:30",
                    "publication_timestamp": "2026-08-19T10:00:01+05:30",
                },
                {
                    "event_id": "DUPLICATE", "session_date": "2026-08-19",
                    "effective_timestamp": "2026-08-19T10:00:00+05:30",
                    "publication_timestamp": "2026-08-19T10:00:01+05:30",
                },
            ]

    value = State()
    value.orchestrator.causality = {
        "valid_basis_pairs": 1,
        "future_joins": 2,
        "synchronization_tolerance_violations": 3,
    }
    value.ingestor.ledgers = {"material": AuditLedger()}
    value.ingestor.c = {
        **value.ingestor.c,
        "engine_source_verified": False,
        "runtime_source_open_audit": {"prohibited_open_count": 4},
    }
    service = create_server(value, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    try:
        audit = json.loads(request(base, "/api/audit")[2])
        assert audit["future_joins"] == 2
        assert audit["synchronization_tolerance_violations"] == 3
        assert audit["timestamp_backdating"] == 1
        assert audit["duplicate_analytical_ids"] == 1
        assert audit["prohibited_runtime_opens"] == 4
        assert audit["manifest_verified"] is False
        assert audit["measured_ledger_rows"] == 2
    finally:
        service.shutdown(); thread.join(); service.server_close()


def test_expected_source_manifest_detects_current_source_mutation(tmp_path):
    (tmp_path / "a.py").write_text("A\n")
    (tmp_path / "b.py").write_text("B\n")
    allowlist = ("a.py", "b.py")
    inventory = engine_source_inventory(tmp_path, allowlist)
    manifest = {
        "schema": "R6E1R_ENGINE_SOURCE_MANIFEST_V1",
        "classification": CLASSIFICATION,
        "allowlist": list(allowlist),
        "file_count": len(inventory),
        "files": inventory,
        "engine_hash": engine_hash(tmp_path, allowlist),
    }
    path = tmp_path / "manifest.json"
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert verify_engine_source_manifest(
        tmp_path, "manifest.json", expected, allowlist,
    )["verified"] is True
    (tmp_path / "b.py").write_text("MUTATED\n")
    with pytest.raises(ValueError, match="current engine sources"):
        verify_engine_source_manifest(
            tmp_path, "manifest.json", expected, allowlist,
        )
