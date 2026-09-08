"""Static GUI and read-only API proxy. No calculation package is imported."""
from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import signal
import threading
from urllib.parse import parse_qs, unquote, urlsplit


def handler_for(root, instrument, core_port):
    root = Path(root).resolve(strict=True)
    prefix = instrument.lower() + "-"
    allowed_profiles = [prefix + "v1062", prefix + "v200"]

    class Handler(BaseHTTPRequestHandler):
        server_version = "MarketGUI/3.0.0"

        def log_message(self, format, *args):
            pass

        def send(self, body, status=200, content_type="application/json; charset=utf-8", headers=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            try:
                if url.path == "/workspace-config.json":
                    return self.send(json.dumps({"instrument": instrument, "profiles": allowed_profiles,
                        "defaultProfile": prefix + "v200", "live": True, "defaultMode": "live",
                        "pollMilliseconds": 5000}).encode())
                if url.path == "/health":
                    return self.send(json.dumps({"status": "ok", "role": "gui", "instrument": instrument, "owns_engine": False}).encode())
                if url.path.startswith("/api/"):
                    if url.path not in {"/api/health", "/api/live", "/api/catalog", "/api/replay"}:
                        return self.send(b'{"error":"Not found"}', 404)
                    query = parse_qs(url.query)
                    if url.path != "/api/health" and query.get("profile", [""])[0] not in allowed_profiles:
                        return self.send(b'{"error":"Profile belongs to another instrument"}', 400)
                    connection = http.client.HTTPConnection("127.0.0.1", core_port, timeout=5)
                    try:
                        forwarded = {key: self.headers[key] for key in ("Accept-Encoding", "If-None-Match") if self.headers.get(key)}
                        connection.request("GET", self.path, headers=forwarded)
                        response = connection.getresponse()
                        body = response.read()
                        headers = {key: response.getheader(key) for key in ("Content-Encoding", "ETag") if response.getheader(key)}
                        return self.send(body, response.status, headers=headers)
                    finally:
                        connection.close()
                relative = unquote(url.path).lstrip("/") or "index.html"
                target = (root / relative).resolve()
                if root not in target.parents or not target.is_file():
                    return self.send(b'{"error":"Not found"}', 404)
                self.send(target.read_bytes(), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, http.client.HTTPException):
                self.send(b'{"error":"Core unavailable; this GUI remains independent"}', 502)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instrument", required=True, choices=["BANKNIFTY", "NIFTY"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--core-port", required=True, type=int)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(args.root, args.instrument, args.core_port))
    server.daemon_threads = True
    def shutdown(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
