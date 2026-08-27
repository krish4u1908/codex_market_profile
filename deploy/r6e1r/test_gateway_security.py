from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import pytest
import runpy
import socket
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


GATEWAY = runpy.run_path(str(Path(__file__).with_name("read_only_gateway.py")))
BoundedThreadingHTTPServer = GATEWAY["BoundedThreadingHTTPServer"]
handler_for = GATEWAY["handler_for"]
validated_hidden_paths = GATEWAY["validated_hidden_paths"]
verify_runtime_isolation = GATEWAY["verify_runtime_isolation"]
RUNTIME_GLOBALS = GATEWAY["main"].__globals__


def _wait_for_active(server, expected: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.active_request_count() == expected:
            return
        time.sleep(0.01)
    raise AssertionError(
        f"active request count did not reach {expected}: "
        f"{server.active_request_count()}"
    )


def _server(*, request_limit: int, client_timeout: float):
    server = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler_for("http://127.0.0.1:1"),
        max_concurrent_requests=request_limit,
        client_timeout_seconds=client_timeout,
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def _stop_server(server, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
    assert not thread.is_alive()


def _plain_server(handler: type[BaseHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return server, thread


def _stop_plain_server(server, thread: threading.Thread) -> None:
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()
    assert not thread.is_alive()


def test_gateway_memory_and_socket_budgets_fit_service_limit() -> None:
    max_response = GATEWAY["MAX_RESPONSE_BYTES"]
    max_requests = GATEWAY["MAX_CONCURRENT_REQUESTS"]
    assert max_response <= 8 * 1024 * 1024
    assert max_requests <= 8
    assert max_response * max_requests <= 64 * 1024 * 1024
    assert 0 < GATEWAY["CLIENT_SOCKET_TIMEOUT_SECONDS"] <= 5


def test_gateway_source_contains_no_concrete_host_paths() -> None:
    source = Path(__file__).with_name("read_only_gateway.py").read_text()
    assert "/opt/" not in source
    assert "HIDDEN_RUNTIME_PATHS" not in source


def test_hidden_paths_require_three_distinct_canonical_absolute_values() -> None:
    assert tuple(map(str, validated_hidden_paths([
        "/collector", "/analytical-state", "/runtime-config",
    ]))) == ("/collector", "/analytical-state", "/runtime-config")
    invalid = (
        [],
        ["/collector"],
        ["/collector", "/state", "/config", "/extra"],
        ["collector", "/state", "/config"],
        ["/", "/state", "/config"],
        ["//collector", "/state", "/config"],
        ["/collector", "/collector", "/config"],
        ["/collector/../collector", "/state", "/config"],
    )
    for values in invalid:
        with pytest.raises(ValueError):
            validated_hidden_paths(values)


def test_runtime_isolation_checks_only_supplied_hidden_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []

    def path_exists(path: Path) -> bool:
        checked.append(str(path))
        return False

    monkeypatch.setitem(RUNTIME_GLOBALS, "_path_exists", path_exists)
    monkeypatch.setitem(RUNTIME_GLOBALS, "_visible_pid_names", lambda: ["1", "2"])
    monkeypatch.setattr(GATEWAY["os"], "getuid", lambda: 424242)
    result = verify_runtime_isolation([
        "/collector", "/analytical-state", "/runtime-config",
    ])
    assert result["collector_state_config_hidden"] is True
    assert result["hidden_path_count"] == 3
    assert checked == [
        "/collector", "/analytical-state", "/runtime-config",
        "/run/user/424242",
    ]

    monkeypatch.setitem(
        RUNTIME_GLOBALS,
        "_path_exists",
        lambda path: str(path) == "/analytical-state",
    )
    with pytest.raises(RuntimeError, match="isolation contract unavailable"):
        verify_runtime_isolation([
            "/collector", "/analytical-state", "/runtime-config",
        ])


@pytest.mark.parametrize("mode", ("--require-isolation", "--isolation-self-test"))
def test_isolation_modes_require_hidden_path_arguments(
    mode: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["read_only_gateway.py", mode])
    with pytest.raises(SystemExit) as caught:
        GATEWAY["main"]()
    assert caught.value.code == 2


def test_self_test_forwards_required_hidden_paths(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[str] = []

    def verify(paths) -> dict[str, object]:
        observed.extend(map(str, paths))
        return {
            "collector_state_config_hidden": True,
            "hidden_path_count": len(paths),
            "process_namespace_private": True,
            "user_runtime_hidden": True,
            "visible_pid_count": 1,
        }

    monkeypatch.setitem(RUNTIME_GLOBALS, "verify_runtime_isolation", verify)
    monkeypatch.setattr(sys, "argv", [
        "read_only_gateway.py",
        "--isolation-self-test",
        "--hidden-path", "/collector",
        "--hidden-path", "/analytical-state",
        "--hidden-path", "/runtime-config",
    ])
    GATEWAY["main"]()
    assert observed == ["/collector", "/analytical-state", "/runtime-config"]
    assert json.loads(capsys.readouterr().out)["hidden_path_count"] == 3


def test_hidden_paths_are_refused_without_isolation_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", [
        "read_only_gateway.py",
        "--hidden-path", "/collector",
        "--hidden-path", "/analytical-state",
        "--hidden-path", "/runtime-config",
    ])
    with pytest.raises(SystemExit) as caught:
        GATEWAY["main"]()
    assert caught.value.code == 2


def test_gateway_refuses_overload_without_starting_another_handler() -> None:
    server, thread = _server(request_limit=1, client_timeout=2.0)
    slow = socket.create_connection(server.server_address, timeout=1)
    overloaded = None
    try:
        _wait_for_active(server, 1)
        overloaded = socket.create_connection(server.server_address, timeout=1)
        overloaded.sendall(b"GET /api/health HTTP/1.0\r\n\r\n")
        response = overloaded.recv(4096)
        assert response.startswith(b"HTTP/1.0 503 Service Unavailable\r\n")
        assert b'{"error":"GATEWAY_BUSY"}' in response
        assert server.active_request_count() == 1
    finally:
        if overloaded is not None:
            overloaded.close()
        slow.close()
        _wait_for_active(server, 0)
        _stop_server(server, thread)


def test_incomplete_client_is_closed_and_releases_slot_after_timeout() -> None:
    server, thread = _server(request_limit=1, client_timeout=0.1)
    slow = socket.create_connection(server.server_address, timeout=1)
    try:
        _wait_for_active(server, 1)
        _wait_for_active(server, 0)
        slow.settimeout(1)
        assert slow.recv(1) == b""
    finally:
        slow.close()
        _stop_server(server, thread)


def test_trickle_client_cannot_extend_absolute_header_deadline() -> None:
    server, thread = _server(request_limit=1, client_timeout=0.15)
    slow = socket.create_connection(server.server_address, timeout=1)
    try:
        _wait_for_active(server, 1)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and server.active_request_count():
            try:
                slow.sendall(b"G")
            except OSError:
                break
            time.sleep(0.03)
        _wait_for_active(server, 0)
    finally:
        slow.close()
        _stop_server(server, thread)


@pytest.mark.parametrize("method", ("GET", "HEAD"))
def test_backend_redirect_is_refused_without_fetching_location(method: str) -> None:
    class Sink(BaseHTTPRequestHandler):
        requests = 0

        def do_GET(self) -> None:  # noqa: N802
            type(self).requests += 1
            self.send_response(200)
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *_: object) -> None:
            pass

    sink, sink_thread = _plain_server(Sink)

    class Redirect(BaseHTTPRequestHandler):
        def _redirect(self) -> None:
            self.send_response(302)
            self.send_header(
                "Location",
                f"http://127.0.0.1:{sink.server_address[1]}/captured",
            )
            self.end_headers()

        do_GET = _redirect
        do_HEAD = _redirect

        def log_message(self, *_: object) -> None:
            pass

    redirect, redirect_thread = _plain_server(Redirect)
    gateway = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler_for(f"http://127.0.0.1:{redirect.server_address[1]}"),
    )
    gateway_thread = threading.Thread(target=gateway.serve_forever)
    gateway_thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{gateway.server_address[1]}/api/health",
            method=method,
        )
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=2)
        assert caught.value.code == 502
        if method == "GET":
            assert json.loads(caught.value.read()) == {
                "error": "UPSTREAM_REDIRECT_REFUSED",
            }
        assert Sink.requests == 0
    finally:
        _stop_server(gateway, gateway_thread)
        _stop_plain_server(redirect, redirect_thread)
        _stop_plain_server(sink, sink_thread)
