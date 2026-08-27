#!/usr/bin/env python3
"""Exact-route external gateway for the localhost R6E analytical API."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROUTES = frozenset({
    "/", "/live", "/assets/live.js", "/assets/style.css",
    "/api/health", "/api/readiness", "/api/status", "/api/session",
    "/api/chart", "/api/inventory", "/api/divergence", "/api/lifecycle",
    "/api/participation", "/api/transitions", "/api/availability", "/api/audit",
})
REPLAY_DATES = frozenset({
    "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-18", "2026-08-19", "2026-08-20",
})
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CONCURRENT_REQUESTS = 8
CLIENT_SOCKET_TIMEOUT_SECONDS = 5.0
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
}
QUERY_KEYS = {
    "/api/status": frozenset({"date"}),
    "/api/session": frozenset({"date"}),
    "/api/chart": frozenset({"date"}),
    "/api/inventory": frozenset({"date", "limit"}),
    "/api/divergence": frozenset({"date", "limit"}),
    "/api/lifecycle": frozenset({"date", "limit"}),
    "/api/participation": frozenset({"date", "limit"}),
    "/api/transitions": frozenset({"date", "limit"}),
    "/api/availability": frozenset({"date"}),
    "/api/audit": frozenset({"date", "limit"}),
}
REQUIRED_HIDDEN_PATH_COUNT = 3


class _BackendNoRedirectHandler(HTTPRedirectHandler):
    """Keep every upstream fetch on the configured localhost authority."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        return None


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Bound public request lifetime, concurrency, and buffered response RSS."""

    daemon_threads = True
    block_on_close = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler: type[BaseHTTPRequestHandler],
        *,
        max_concurrent_requests: int = MAX_CONCURRENT_REQUESTS,
        client_timeout_seconds: float = CLIENT_SOCKET_TIMEOUT_SECONDS,
    ) -> None:
        if max_concurrent_requests < 1:
            raise ValueError("max_concurrent_requests must be positive")
        if not 0 < client_timeout_seconds <= 30:
            raise ValueError("client_timeout_seconds must be in (0, 30]")
        self.client_timeout_seconds = float(client_timeout_seconds)
        self._request_slots = threading.BoundedSemaphore(
            max_concurrent_requests
        )
        self._active_lock = threading.Lock()
        self._active_requests = 0
        super().__init__(server_address, request_handler)

    def get_request(self) -> tuple[socket.socket, object]:
        request, address = super().get_request()
        request.settimeout(self.client_timeout_seconds)
        return request, address

    def active_request_count(self) -> int:
        with self._active_lock:
            return self._active_requests

    def _release_request_slot(self) -> None:
        with self._active_lock:
            self._active_requests -= 1
        self._request_slots.release()

    def _reject_overload(self, request: socket.socket) -> None:
        body = b'{"error":"GATEWAY_BUSY"}'
        response = (
            b"HTTP/1.0 503 Service Unavailable\r\n"
            b"Content-Type: application/json; charset=utf-8\r\n"
            b"Cache-Control: no-store\r\n"
            b"X-Content-Type-Options: nosniff\r\n"
            b"Connection: close\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        try:
            request.sendall(response)
        except OSError:
            pass
        finally:
            self.shutdown_request(request)

    def process_request(self, request: socket.socket, client_address: object) -> None:
        if not self._request_slots.acquire(blocking=False):
            self._reject_overload(request)
            return
        with self._active_lock:
            self._active_requests += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release_request_slot()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: object,
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release_request_slot()

    def handle_error(self, request: object, client_address: object) -> None:
        # Socket timeouts and disconnects are expected on a public boundary;
        # never emit attacker-controlled request/address detail or tracebacks.
        del request, client_address


def validated_hidden_paths(values: Sequence[str]) -> tuple[Path, ...]:
    """Authenticate the three caller-supplied collector/state/config paths."""
    if len(values) != REQUIRED_HIDDEN_PATH_COUNT:
        raise ValueError(
            "isolation requires exactly three repeated --hidden-path values"
        )
    hidden_paths: list[Path] = []
    for value in values:
        path = Path(value)
        if (
            not value
            or value.startswith("//")
            or not path.is_absolute()
            or path == Path("/")
        ):
            raise ValueError("each --hidden-path must be an absolute non-root path")
        if ".." in path.parts or str(path) != value:
            raise ValueError("each --hidden-path must be canonical")
        hidden_paths.append(path)
    if len(set(hidden_paths)) != len(hidden_paths):
        raise ValueError("--hidden-path values must be distinct")
    return tuple(hidden_paths)


def _path_exists(path: Path) -> bool:
    return path.exists()


def _visible_pid_names() -> list[str]:
    return [item.name for item in Path("/proc").iterdir() if item.name.isdigit()]


def verify_runtime_isolation(
    hidden_paths: Sequence[str] | Sequence[Path],
) -> dict[str, object]:
    """Refuse service startup unless the minimal bwrap root is effective."""
    supplied = validated_hidden_paths([str(path) for path in hidden_paths])
    hidden = all(not _path_exists(path) for path in supplied)
    user_runtime_hidden = not _path_exists(Path(f"/run/user/{os.getuid()}"))
    try:
        visible_pids = _visible_pid_names()
    except OSError:
        visible_pids = []
    process_namespace_private = 1 <= len(visible_pids) <= 2
    if not (hidden and user_runtime_hidden and process_namespace_private):
        raise RuntimeError("gateway runtime isolation contract unavailable")
    return {
        "collector_state_config_hidden": hidden,
        "hidden_path_count": len(supplied),
        "user_runtime_hidden": user_runtime_hidden,
        "visible_pid_count": len(visible_pids),
        "process_namespace_private": process_namespace_private,
    }


def safe_query(path: str, raw: str) -> str | None:
    if not raw:
        return ""
    if path not in QUERY_KEYS or len(raw) > 2048:
        return None
    try:
        values = parse_qs(
            raw, keep_blank_values=True, strict_parsing=True, max_num_fields=8,
        )
    except ValueError:
        return None
    if not set(values).issubset(QUERY_KEYS[path]):
        return None
    if any(len(items) != 1 or items[0] == "" for items in values.values()):
        return None
    date = values.get("date", [""])[0]
    if date and date != "latest" and date not in REPLAY_DATES:
        return None
    limit = values.get("limit", [""])[0]
    if limit and (not limit.isdigit() or not 1 <= int(limit) <= 5000):
        return None
    return urlencode(
        [(key, values[key][0]) for key in sorted(values)]
    )


def handler_for(backend: str) -> type[BaseHTTPRequestHandler]:
    class Gateway(BaseHTTPRequestHandler):
        server_version = "R6EReadOnlyGateway"
        sys_version = ""

        def setup(self) -> None:
            super().setup()
            timeout = float(getattr(
                self.server,
                "client_timeout_seconds",
                CLIENT_SOCKET_TIMEOUT_SECONDS,
            ))
            self._header_deadline = threading.Timer(
                timeout, self._expire_incomplete_headers
            )
            self._header_deadline.daemon = True
            self._header_deadline.start()

        def _expire_incomplete_headers(self) -> None:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        def _cancel_header_deadline(self) -> None:
            deadline = getattr(self, "_header_deadline", None)
            if deadline is not None:
                deadline.cancel()

        def parse_request(self) -> bool:
            try:
                return super().parse_request()
            finally:
                # `parse_request` reads every header; cancellation therefore
                # happens only after the complete request head is available.
                self._cancel_header_deadline()

        def finish(self) -> None:
            self._cancel_header_deadline()
            super().finish()

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not getattr(self, "_head_only", False):
                self.wfile.write(body)

        def _json_error(self, status: int, code: str) -> None:
            self._send(
                status, json.dumps({"error": code}, separators=(",", ":")).encode(),
                "application/json; charset=utf-8",
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = safe_query(parsed.path, parsed.query)
            if parsed.path not in ROUTES or query is None:
                return self._json_error(404, "NOT_FOUND")
            target = f"{backend}{parsed.path}{'?' + query if query else ''}"
            request = Request(target, method="HEAD" if getattr(self, "_head_only", False) else "GET")
            try:
                # The backend route is allowlisted, but urllib's default
                # opener would follow an upstream Location to a different
                # host. Refuse redirects so the gateway cannot become an SSRF
                # relay if the localhost backend is compromised or misrouted.
                with build_opener(_BackendNoRedirectHandler()).open(
                    request, timeout=30,
                ) as response:
                    body = b"" if getattr(self, "_head_only", False) else response.read(MAX_RESPONSE_BYTES + 1)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return self._json_error(502, "UPSTREAM_RESPONSE_LIMIT")
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
                    return self._send(response.status, body, content_type)
            except HTTPError as error:
                try:
                    if 300 <= error.code < 400:
                        return self._json_error(502, "UPSTREAM_REDIRECT_REFUSED")
                    body = b"" if getattr(self, "_head_only", False) else error.read(MAX_RESPONSE_BYTES + 1)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return self._json_error(502, "UPSTREAM_RESPONSE_LIMIT")
                    return self._send(
                        error.code, body,
                        error.headers.get("Content-Type", "application/json; charset=utf-8"),
                    )
                finally:
                    error.close()
            except (URLError, TimeoutError):
                return self._json_error(503, "ANALYTICAL_BACKEND_UNAVAILABLE")

        def do_HEAD(self) -> None:  # noqa: N802
            self._head_only = True
            self.do_GET()

        def _read_only(self) -> None:
            self._json_error(405, "READ_ONLY_GATEWAY")

        do_POST = _read_only
        do_PUT = _read_only
        do_PATCH = _read_only
        do_DELETE = _read_only

        def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
            # Never persist attacker-controlled request lines, path/query
            # values, or parser diagnostics. Journald receives only normalized
            # method/allowlisted-route/query-key/status metadata.
            parsed = urlparse(self.path)
            query = safe_query(parsed.path, parsed.query)
            route = parsed.path if parsed.path in ROUTES else "UNRECOGNIZED"
            query_keys = []
            if query is not None and query:
                query_keys = sorted(parse_qs(query, keep_blank_values=True))
            method = self.command if self.command in {
                "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE",
            } else "OTHER"
            print(json.dumps({
                "component": "r6e1r-readonly-gateway",
                "method": method,
                "route": route,
                "query_keys": query_keys,
                "status": int(code) if str(code).isdigit() else 0,
            }, separators=(",", ":")), flush=True)

        def log_message(self, *_: object) -> None:
            pass

    return Gateway


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8805)
    parser.add_argument("--backend", default="http://127.0.0.1:18805")
    parser.add_argument(
        "--hidden-path",
        action="append",
        default=[],
        metavar="ABSOLUTE_PATH",
        help=(
            "absolute collector/state/config path hidden from the gateway; "
            "repeat exactly three times when isolation verification is enabled"
        ),
    )
    parser.add_argument("--require-isolation", action="store_true")
    parser.add_argument("--isolation-self-test", action="store_true")
    args = parser.parse_args()
    if args.backend != "http://127.0.0.1:18805":
        raise ValueError("backend must remain http://127.0.0.1:18805")
    isolation_requested = args.require_isolation or args.isolation_self_test
    if isolation_requested:
        try:
            hidden_paths = validated_hidden_paths(args.hidden_path)
        except ValueError as error:
            parser.error(str(error))
        result = verify_runtime_isolation(hidden_paths)
        if args.isolation_self_test:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
    elif args.hidden_path:
        parser.error("--hidden-path requires an isolation verification mode")
    with BoundedThreadingHTTPServer(
        (args.bind, args.port), handler_for(args.backend)
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
