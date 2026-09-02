"""Snapshot + resumable SSE service for the live calculation authority."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
import time
from urllib.parse import parse_qs, urlparse

from .codex_bridge import CodexWorkerProbe
from .codex_replay import CodexAppServerClient, CodexReplayError
from .commentary import CommentaryStore, LiveCommentaryCoordinator
from .live_runtime import LiveRuntime
from .provenance import RUNTIME_VERSION


def build_live_browser(output_root: Path) -> Path:
    target = Path(output_root).resolve()
    target.mkdir(parents=True, exist_ok=True)
    static = Path(__file__).with_name("static_live")
    replay_static = Path(__file__).with_name("static_new")
    for name in ("live.html", "live.js", "live.css"):
        shutil.copyfile(static / name, target / name)
    shutil.copyfile(replay_static / "style.css", target / "style.css")
    (target / "build_manifest.json").write_text(json.dumps({
        "schema": "NEW_DIVERGENCE_LIVE_BROWSER_BUILD_V1",
        "runtime_version": RUNTIME_VERSION,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


class _LiveHandler(SimpleHTTPRequestHandler):
    runtime: LiveRuntime
    codex_probe: CodexWorkerProbe
    commentary: LiveCommentaryCoordinator | None = None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'")
        super().end_headers()

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _requested_sequence(self, query: dict[str, list[str]]) -> int:
        header = self.headers.get("Last-Event-ID")
        value = header if header not in {None, ""} else query.get("after", ["0"])[0]
        sequence = int(value)
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        return sequence

    def _sse(self, after: int) -> None:
        snapshot = self.runtime.authority.status_snapshot()
        current = int(snapshot["sequence"])
        if after > current:
            self._json(409, {"error": "sequence is ahead of authority", "current_sequence": current})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        cursor = after
        try:
            while True:
                rows = self.runtime.authority.wait_after(cursor, timeout=15.0)
                if rows:
                    for row in rows:
                        cursor = int(row["sequence"])
                        body = json.dumps(row, sort_keys=True, separators=(",", ":"))
                        self.wfile.write(f"id: {cursor}\nevent: publication\ndata: {body}\n\n".encode())
                else:
                    status = self.runtime.authority.status_snapshot()
                    body = json.dumps({
                        "sequence": status["sequence"],
                        "status": status["status"],
                        "server_time": status["server_time"],
                    }, sort_keys=True, separators=(",", ":"))
                    self.wfile.write(f"event: heartbeat\ndata: {body}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:  # noqa: N802
        request = urlparse(self.path)
        query = parse_qs(request.query)
        if request.path == "/healthz":
            snapshot = self.runtime.authority.status_snapshot()
            status = "ok" if snapshot["status"] != "LIVE_RECOVERY_REQUIRED" else "error"
            codex_worker = self.codex_probe.status()
            self._json(200 if status == "ok" else 503, {
                "status": status,
                "mode": "read-only-live-research",
                "runtime_version": RUNTIME_VERSION,
                "browser_runtime_version": RUNTIME_VERSION,
                "live_status": snapshot["status"],
                "recovery_mode": snapshot["recovery_mode"],
                "sequence": snapshot["sequence"],
                "failure": self.runtime.failure,
                "codex_worker": codex_worker,
            })
            return
        if request.path == "/api/v1/live/snapshot":
            try:
                requested = int(query.get("max_points", ["4000"])[0])
            except (TypeError, ValueError):
                self._json(400, {"error": "max_points must be an integer"})
                return
            # A non-positive value explicitly requests the complete intraday
            # observation history (used by the desktop layout).
            observation_limit = None if requested <= 0 else max(1000, min(12000, requested))
            self._json(200, self.runtime.authority.browser_snapshot(
                observation_limit=observation_limit
            ))
            return
        if request.path == "/api/v1/live/history":
            try:
                before = int(query.get("before", ["0"])[0])
                requested_limit = int(query.get("limit", ["2000"])[0])
            except (TypeError, ValueError):
                self._json(400, {"error": "before and limit must be integers"})
                return
            if before < 0:
                self._json(400, {"error": "before must be non-negative"})
                return
            limit = max(250, min(4000, requested_limit))
            self._json(200, self.runtime.authority.observation_history(
                before=before, limit=limit
            ))
            return
        if request.path == "/api/v1/live/profile":
            self._json(200, self.runtime.authority.profile_snapshot())
            return
        if request.path == "/api/v1/codex/status":
            status = self.codex_probe.status()
            status["prompting_enabled"] = self.commentary is not None
            self._json(200, status)
            return
        if request.path == "/api/v1/commentary/current":
            if self.commentary is None:
                self._json(503, {"error": "central live commentary is not configured"})
                return
            snapshot = self.runtime.authority.status_snapshot()
            result = self.commentary.store.current(str(snapshot["session"]))
            if result is None:
                self._json(202, {"schema": "NEW_DIVERGENCE_COMMENTARY_PENDING_V1",
                                 "session": snapshot["session"], "delivery_state": "PENDING"})
            else:
                self._json(200, {**result, "delivery_state": "STORED"})
            return
        if request.path == "/api/v1/live/events":
            try:
                after = self._requested_sequence(query)
            except (TypeError, ValueError):
                self._json(400, {"error": "invalid after/Last-Event-ID sequence"})
                return
            current = int(self.runtime.authority.status_snapshot()["sequence"])
            if after > current:
                self._json(409, {"error": "sequence is ahead of authority", "current_sequence": current})
                return
            self._json(200, {"after": after, "current_sequence": current, "events": self.runtime.authority.after(after)})
            return
        if request.path == "/api/v1/live/stream":
            try:
                self._sse(self._requested_sequence(query))
            except (TypeError, ValueError):
                self._json(400, {"error": "invalid after/Last-Event-ID sequence"})
            return
        if request.path == "/":
            self.path = "/live.html"
        super().do_GET()


def serve_live(
    runtime: LiveRuntime,
    static_root: Path,
    host: str,
    port: int,
    *,
    codex_host: str = "127.0.0.1",
    codex_port: int = 4500,
    codex_cwd: Path = Path("/home/codexuser/banknifty-codex-worker"),
    commentary_db: Path | None = None,
    enable_commentary: bool = False,
) -> None:
    root = Path(static_root).resolve()
    manifest = json.loads((root / "build_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("runtime_version") != RUNTIME_VERSION:
        raise ValueError("live browser runtime mismatch; run build-live-browser again")
    _LiveHandler.runtime = runtime
    _LiveHandler.codex_probe = CodexWorkerProbe(codex_host, codex_port)
    _LiveHandler.commentary = None if not enable_commentary else LiveCommentaryCoordinator(
        CommentaryStore(commentary_db or (Path(static_root).resolve() / "commentary.sqlite3")),
        CodexAppServerClient(codex_host, codex_port, codex_cwd),
    )
    handler = partial(_LiveHandler, directory=str(root))
    runtime.start()
    commentary_stop = threading.Event()
    commentary_thread = None
    if _LiveHandler.commentary is not None:
        def generate_commentary() -> None:
            while not commentary_stop.wait(5.0):
                try:
                    _LiveHandler.commentary.generate(runtime.authority.commentary_snapshot())
                except (CodexReplayError, OSError, RuntimeError, TypeError, ValueError):
                    # Health remains independently observable; the live authority
                    # must never fail because optional commentary is unavailable.
                    continue

        commentary_thread = threading.Thread(
            target=generate_commentary,
            name="new-divergence-central-commentary",
            daemon=True,
        )
        commentary_thread.start()
    try:
        with ThreadingHTTPServer((host, port), handler) as server:
            server.serve_forever()
    finally:
        commentary_stop.set()
        if commentary_thread is not None:
            commentary_thread.join(timeout=2.0)
        runtime.stop()
