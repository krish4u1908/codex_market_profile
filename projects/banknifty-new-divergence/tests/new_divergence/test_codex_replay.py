from __future__ import annotations

from collections import deque
from functools import partial
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from banknifty_profiler.new_divergence.api import ProjectionReadModel
from banknifty_profiler.new_divergence.codex_replay import (
    CodexAppServerClient,
    CodexReplayError,
    QUESTION_LABELS,
    ReplayCodexGateway,
    replay_fact_bundle,
    validate_explain_request,
)
from banknifty_profiler.new_divergence.contracts import EngineConfig
from banknifty_profiler.new_divergence.output import publish_run
from banknifty_profiler.new_divergence.projection import build_browser
from banknifty_profiler.new_divergence.service import _Handler

from .helpers import green_episode_events


def _browser(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    events = green_episode_events()
    run_root = tmp_path / "runs"
    publish_run(
        run_root,
        events[0].session,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_CODEX_REPLAY_TEST"},
    )
    browser = build_browser(run_root, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(events[0].session.isoformat())
    return browser, payload


def test_fact_bundle_ends_at_exact_receipt_and_excludes_future(tmp_path) -> None:
    browser, payload = _browser(tmp_path)
    cutoff = payload["price"]["rows"][10][0]
    bundle, bundle_hash = replay_fact_bundle(
        ProjectionReadModel(browser), payload["session"], cutoff
    )
    assert bundle["causal_as_of"] == cutoff
    assert bundle["observation_count"] == 11
    assert bundle["latest_market"]["t"] == cutoff
    assert bundle["latest_state"]["t"] == cutoff
    assert "recent_futures_volume_minutes" in bundle
    assert len(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()) < 96_000
    assert len(bundle_hash) == 64
    assert all(row["published_at"] <= cutoff for row in bundle["recent_visible_transitions"])

    between = payload["price"]["rows"][10][0][:-1] + "1Z"
    with pytest.raises(ValueError, match="exactly match"):
        replay_fact_bundle(ProjectionReadModel(browser), payload["session"], between)


def test_explain_request_has_no_free_form_prompt_surface() -> None:
    value = {
        "session": "2031-04-07",
        "as_of": "2031-04-07T04:15:01.000000Z",
        "question_id": "CURRENT_CONTEXT",
    }
    assert validate_explain_request(value) == (
        "2031-04-07", "2031-04-07T04:15:01.000000Z", "CURRENT_CONTEXT"
    )
    for extra in ("prompt", "path", "raw_market_data"):
        with pytest.raises(ValueError, match="only session"):
            validate_explain_request({**value, extra: "untrusted"})
    with pytest.raises(ValueError, match="allow-listed"):
        validate_explain_request({**value, "question_id": "RUN_A_SHELL"})


class _FakeSocket:
    def __init__(self, answer: dict[str, object]):
        self.sent: list[dict[str, object]] = []
        self.closed = False
        self.messages = deque([
            {"id": 0, "result": {"userAgent": "test"}},
            {"id": 1, "result": {"thread": {"id": "thr_test"}}},
            {"id": 2, "result": {"turn": {"id": "turn_test"}}},
            {
                "method": "item/completed",
                "params": {"item": {
                    "type": "agentMessage", "id": "item_test",
                    "text": json.dumps(answer),
                }},
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn_test", "status": "completed"}},
            },
        ])

    def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def recv(self, timeout=None) -> str:
        return json.dumps(self.messages.popleft())

    def close(self) -> None:
        self.closed = True


def test_app_server_client_uses_read_only_never_approval_and_structured_output() -> None:
    as_of = "2031-04-07T04:15:01.000000Z"
    answer = {
        "headline": "Neutral published state",
        "summary": "Only the supplied replay prefix was considered.",
        "analysis": "The visible basis and published state are neutral at this receipt.",
        "evidence_trace": ["Latest state row at the requested receipt."],
        "observations": ["Basis is visible."],
        "limitations": ["No later observations are available."],
        "causal_as_of": as_of,
        "diagnostic_only": True,
    }
    socket = _FakeSocket(answer)
    client = CodexAppServerClient(
        cwd=Path("/restricted/worker"),
        connector=lambda _uri, _timeout: socket,
    )
    result = client.explain("CURRENT_CONTEXT", {
        "causal_as_of": as_of,
        "verified_prefix_sha256": "0" * 64,
    })
    assert result == answer
    thread_start = next(row for row in socket.sent if row["method"] == "thread/start")
    turn_start = next(row for row in socket.sent if row["method"] == "turn/start")
    assert thread_start["params"]["approvalPolicy"] == "never"
    assert thread_start["params"]["sandbox"] == "read-only"
    assert turn_start["params"]["approvalPolicy"] == "never"
    assert turn_start["params"]["sandboxPolicy"] == {
        "type": "readOnly", "networkAccess": False,
    }
    assert turn_start["params"]["outputSchema"]["additionalProperties"] is False
    assert turn_start["params"]["outputSchema"]["properties"]["evidence_trace"]["maxItems"] == 8
    assert turn_start["params"]["outputSchema"]["properties"]["evidence_trace"]["items"]["maxLength"] == 600
    assert client.timeout_seconds == 90.0
    assert socket.sent[-1]["method"] == "thread/delete"
    assert socket.closed is True


def test_app_server_client_rejects_wrong_causal_cursor() -> None:
    socket = _FakeSocket({
        "headline": "Wrong cursor",
        "summary": "This must fail closed.",
        "analysis": "The answer intentionally carries the wrong cursor.",
        "evidence_trace": [],
        "observations": [],
        "limitations": [],
        "causal_as_of": "2031-04-07T04:15:02.000000Z",
        "diagnostic_only": True,
    })
    client = CodexAppServerClient(
        cwd=Path("/restricted/worker"),
        connector=lambda _uri, _timeout: socket,
    )
    with pytest.raises(CodexReplayError, match="causal cursor"):
        client.explain("CURRENT_CONTEXT", {
            "causal_as_of": "2031-04-07T04:15:01.000000Z",
        })


def test_app_server_client_interrupts_any_tool_or_command_item() -> None:
    socket = _FakeSocket({})
    socket.messages = deque([
        {"id": 0, "result": {"userAgent": "test"}},
        {"id": 1, "result": {"thread": {"id": "thr_test"}}},
        {"id": 2, "result": {"turn": {"id": "turn_test"}}},
        {
            "method": "item/started",
            "params": {"item": {"type": "commandExecution", "id": "tool_test"}},
        },
        {"id": 3, "result": {}},
    ])
    client = CodexAppServerClient(
        cwd=Path("/restricted/worker"),
        connector=lambda _uri, _timeout: socket,
    )
    with pytest.raises(CodexReplayError, match="disallowed diagnostic item"):
        client.explain("CURRENT_CONTEXT", {
            "causal_as_of": "2031-04-07T04:15:01.000000Z",
        })
    interrupt = next(row for row in socket.sent if row["method"] == "turn/interrupt")
    assert interrupt["params"] == {"threadId": "thr_test", "turnId": "turn_test"}


class _FakeClient:
    host = "127.0.0.1"
    port = 4500

    def __init__(self) -> None:
        self.calls = 0

    def explain(self, question_id, bundle):
        self.calls += 1
        return {
            "headline": question_id,
            "summary": bundle["verified_prefix_sha256"],
            "analysis": "Only the verified fact bundle was used.",
            "evidence_trace": [],
            "observations": [],
            "limitations": [],
            "causal_as_of": bundle["causal_as_of"],
            "diagnostic_only": True,
        }


def test_gateway_caches_same_verified_cursor_and_question(tmp_path) -> None:
    browser, payload = _browser(tmp_path)
    cutoff = payload["price"]["rows"][10][0]
    client = _FakeClient()
    gateway = ReplayCodexGateway(
        browser, client, prompting_enabled=True, minimum_interval_seconds=0
    )
    request = {
        "session": payload["session"], "as_of": cutoff,
        "question_id": next(iter(QUESTION_LABELS)),
    }
    first = gateway.explain(request)
    second = gateway.explain(request)
    assert first["cached"] is False
    assert second["cached"] is True
    assert client.calls == 1


def test_http_explanation_endpoint_requires_token_and_returns_json(tmp_path) -> None:
    browser, payload = _browser(tmp_path)
    cutoff = payload["price"]["rows"][10][0]

    class FakeGateway:
        prompting_enabled = True

        def status(self):
            return {"state": "REACHABLE_UNVERIFIED", "prompting_enabled": True}

        def explain(self, value):
            return {
                "schema": "NEW_DIVERGENCE_CODEX_REPLAY_EXPLANATION_V1",
                "as_of": value["as_of"],
                "answer": {"headline": "test"},
            }

    class Handler(_Handler):
        codex_gateway = FakeGateway()
        codex_access_token = "x" * 64

        def log_message(self, _format, *args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, directory=str(browser))
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/v1/codex/explain"
        body = json.dumps({
            "session": payload["session"], "as_of": cutoff,
            "question_id": "CURRENT_CONTEXT",
        }).encode()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, data=body, headers={"Content-Type": "application/json"}))
        assert error.value.code == 401
        response = urlopen(Request(url, data=body, headers={
            "Content-Type": "application/json",
            "X-New-Divergence-Codex-Token": "x" * 64,
        }))
        result = json.loads(response.read())
        assert result["as_of"] == cutoff
        assert result["answer"]["headline"] == "test"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
