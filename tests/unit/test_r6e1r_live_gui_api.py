from __future__ import annotations

import json
import hashlib
from http.server import ThreadingHTTPServer
from pathlib import Path
import runpy
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from banknifty_profiler.gui.adapter import PRODUCT_CLASSIFICATION, SESSIONS
from banknifty_profiler.shadow.api import create_server
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
        "pe_state": "AVAILABLE", "calculation_timestamp": "2026-08-19T10:00:02+05:30",
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
    inventory = [{
        "evaluation_date": date, "horizon": horizon, "family": "BN_REF_FUT_VOLUME_VPOC",
        "control_value": 57000 + index * 10,
        "control_effective_timestamp": f"{date}T{'10:00:00' if horizon == 'ID' else '09:15:00'}+05:30",
        "source_file": "/opt/private/raw.jsonl", "raw_input_hashes": "secret-token",
    } for index, horizon in enumerate(("3D", "2D", "1D", "ID"))]
    episodes = [{
        "episode_id": "BDR1-TEST", "evaluation_date": date, "colour": "GREEN",
        "confirmation_timestamp": f"{date}T10:00:01+05:30", "episode_end_timestamp": "",
        "source_file": "/opt/private/raw.jsonl",
    }]
    lifecycle = [{
        "record_id": "LIFE-1", "episode_id": "BDR1-TEST", "state": "ACTIVE",
        "state_entry_timestamp": f"{date}T10:00:01+05:30", "reason_code": "FROZEN_STATE",
        "source_file": "/opt/private/raw.jsonl",
    }]
    participation = [{
        "record_id": "PART-1", "view_record_kind": "OPTION", "option_type": "CE",
        "symbol": "NSE:BANKNIFTY26AUG57000CE", "observation_timestamp": f"{date}T10:00:02+05:30",
        "receipt_timestamp": f"{date}T10:00:01.900000+05:30", "receipt_age_seconds": 0.1,
        "incremental_volume_5m": 100, "delta_oi_5m": 50,
        "source_file": "/opt/private/oi.jsonl", "source_row": 99,
    }]
    gui = {
        "date": date, "classification": PRODUCT_CLASSIFICATION, "availability": layer_state,
        "price": price, "projection_hash": "a" * 64,
    }
    return {
        "session_date": date, "availability": layer_state, "gui_payload": gui,
        "inventory": inventory, "episodes": episodes, "dependencies": [],
        "lifecycle": lifecycle, "resolution": [],
        "participation_dense": participation, "participation_transitions": [],
        "participation_summaries": [], "cross_layer_transitions": [],
        "counts": {"price": 2, "inventory": 1, "participation_dense": 1},
    }


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
    c = {
        "config": {"classification": PRODUCT_CLASSIFICATION},
        "engine_hash": "b" * 64,
        "configuration_hash": "c" * 64,
        "engine_source_verified": True,
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
    assert chart["availability"]["layers"]["3D"]["state"] == "MISSING_PRIOR_SESSION"
    assert chart["availability"]["layers"]["ID"]["state"] == "AVAILABLE"


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
    assert "--port 8805 --backend http://127.0.0.1:18805" in gateway
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
