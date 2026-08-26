#!/usr/bin/env python3
"""Exact-route external gateway for the localhost R6E analytical API."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


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
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
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
HIDDEN_RUNTIME_PATHS = (
    "/opt/banknifty-collector/data-prod-v4",
    "/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/state",
    "/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/config",
)


def verify_runtime_isolation() -> dict[str, object]:
    """Refuse service startup unless the minimal bwrap root is effective."""
    hidden = all(not Path(path).exists() for path in HIDDEN_RUNTIME_PATHS)
    user_runtime_hidden = not Path(f"/run/user/{os.getuid()}").exists()
    try:
        visible_pids = [
            item.name for item in Path("/proc").iterdir() if item.name.isdigit()
        ]
    except OSError:
        visible_pids = []
    process_namespace_private = 1 <= len(visible_pids) <= 2
    if not (hidden and user_runtime_hidden and process_namespace_private):
        raise RuntimeError("gateway runtime isolation contract unavailable")
    return {
        "collector_state_config_hidden": hidden,
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
                with urlopen(request, timeout=30) as response:
                    body = b"" if getattr(self, "_head_only", False) else response.read(MAX_RESPONSE_BYTES + 1)
                    if len(body) > MAX_RESPONSE_BYTES:
                        return self._json_error(502, "UPSTREAM_RESPONSE_LIMIT")
                    content_type = response.headers.get("Content-Type", "application/octet-stream")
                    return self._send(response.status, body, content_type)
            except HTTPError as error:
                body = b"" if getattr(self, "_head_only", False) else error.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    return self._json_error(502, "UPSTREAM_RESPONSE_LIMIT")
                return self._send(
                    error.code, body,
                    error.headers.get("Content-Type", "application/json; charset=utf-8"),
                )
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
    parser.add_argument("--require-isolation", action="store_true")
    parser.add_argument("--isolation-self-test", action="store_true")
    args = parser.parse_args()
    if args.backend != "http://127.0.0.1:18805":
        raise ValueError("backend must remain http://127.0.0.1:18805")
    if args.require_isolation or args.isolation_self_test:
        result = verify_runtime_isolation()
        if args.isolation_self_test:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return
    ThreadingHTTPServer((args.bind, args.port), handler_for(args.backend)).serve_forever()


if __name__ == "__main__":
    main()
