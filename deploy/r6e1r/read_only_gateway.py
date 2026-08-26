#!/usr/bin/env python3
"""Exact-route external gateway for the localhost R6E analytical API."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
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


def safe_query(path: str, raw: str) -> str | None:
    if not raw:
        return ""
    if not path.startswith("/api/"):
        return None
    values = parse_qs(raw, keep_blank_values=False)
    if not set(values).issubset({"date", "limit"}):
        return None
    date = values.get("date", [""])[0]
    if date and date != "latest" and date not in REPLAY_DATES:
        return None
    limit = values.get("limit", [""])[0]
    if limit and (not limit.isdigit() or not 1 <= int(limit) <= 5000):
        return None
    return urlencode({key: items[0] for key, items in values.items()})


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

        def log_message(self, format_: str, *args: object) -> None:
            # One structured record per request; journald handles rotation.
            print(json.dumps({
                "component": "r6e1r-readonly-gateway",
                "client": self.client_address[0],
                "request": self.requestline,
                "message": format_ % args,
            }, separators=(",", ":")), flush=True)

    return Gateway


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8805)
    parser.add_argument("--backend", default="http://127.0.0.1:18805")
    args = parser.parse_args()
    if args.backend != "http://127.0.0.1:18805":
        raise ValueError("backend must remain http://127.0.0.1:18805")
    ThreadingHTTPServer((args.bind, args.port), handler_for(args.backend)).serve_forever()


if __name__ == "__main__":
    main()
