from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import signal
import threading
from urllib.parse import parse_qs, urlsplit

from .config import Config
from .runtime import Runtime
from .storage import encode


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MarketCore/3.0.0"

        def log_message(self, format, *args):
            pass

        def send(self, body, code=200, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                if url.path in {"/health", "/api/health"}:
                    with store.lock:
                        health = dict(store.health)
                    now = datetime.now(timezone.utc)
                    health["server_time"] = now.isoformat()
                    if health.get("last_price_at"):
                        health["price_age_seconds"] = (now - datetime.fromisoformat(health["last_price_at"])).total_seconds()
                        if health.get("market_open") and health["price_age_seconds"] > 30 and health.get("status") == "ready":
                            health["status"] = "stale"
                    if health.get("last_poll_at"):
                        health["poll_age_seconds"] = (now - datetime.fromisoformat(health["last_poll_at"])).total_seconds()
                        if health["poll_age_seconds"] > 3 * store.config.poll_seconds and health.get("status") == "ready":
                            health["status"] = "stale"
                    return self.send(encode(health))
                if url.path not in {"/api/live", "/api/catalog", "/api/replay"}:
                    return self.send(encode({"error": "Not found"}), 404)
                profile = query.get("profile", [""])[0]
                store.config.check_profile(profile)
                if url.path == "/api/catalog":
                    return self.send(encode(store.catalog(profile)))
                accepts_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
                if url.path == "/api/live":
                    current = store.live(profile)
                    if current is None:
                        with store.lock:
                            health = dict(store.health)
                        return self.send(encode({"waiting": True, "health": health}), 503)
                    body, compressed, etag = current
                    if self.headers.get("If-None-Match") == etag:
                        return self.send(b"", 304, {"ETag": etag})
                    return self.send(compressed if accepts_gzip else body, headers={"ETag": etag,
                        **({"Content-Encoding": "gzip"} if accepts_gzip else {})})
                compressed = store.replay(profile, query.get("key", [""])[0])
                self.send(compressed if accepts_gzip else gzip.decompress(compressed),
                    headers={"Content-Encoding": "gzip"} if accepts_gzip else {})
            except (ValueError, KeyError):
                self.send(encode({"error": "Invalid instrument, profile or session"}), 400)
            except FileNotFoundError:
                self.send(encode({"error": "Session unavailable"}), 404)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description="One shared market core for one instrument")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config = Config.read(args.config)
    runtime = Runtime(config)
    server = ThreadingHTTPServer((config.host, config.port), handler_for(runtime.store))
    server.daemon_threads = True
    def shutdown(*_):
        runtime.stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    runtime.start()
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        runtime.close()


if __name__ == "__main__":
    main()
