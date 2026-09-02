"""Explicit, read-only local server for a built browser projection."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .api import ProjectionReadModel
from .codex_replay import CodexAppServerClient, CodexReplayError, ReplayCodexGateway
from .commentary import GENERATION_REVISION, CommentaryStore, ReplayCommentaryCoordinator, ReplayCommentaryQueue
from .provenance import RUNTIME_VERSION


def _browser_identity(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "build_manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    return {
        "browser_runtime_version": manifest.get("runtime_version"),
        "required_methodology": catalog.get("required_methodology"),
    }


class _Handler(SimpleHTTPRequestHandler):
    codex_gateway: ReplayCodexGateway | None = None
    codex_access_token: str | None = None
    commentary: ReplayCommentaryCoordinator | None = None
    commentary_queue: ReplayCommentaryQueue | None = None

    def _json(self, status: int, value: object) -> None:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - inherited HTTP API
        request = urlparse(self.path)
        if request.path == "/healthz":
            identity = _browser_identity(Path(self.directory))
            self._json(200, {
                "status": "ok",
                "mode": "read-only-research",
                "runtime_version": RUNTIME_VERSION,
                **identity,
            })
            return
        if request.path == "/api/v1/catalog":
            try:
                self._json(200, ProjectionReadModel(Path(self.directory)).catalog())
            except (OSError, ValueError) as error:
                self._json(500, {"error": str(error)})
            return
        if request.path == "/api/v1/codex/status":
            if self.codex_gateway is None:
                self._json(200, {
                    "schema": "NEW_DIVERGENCE_CODEX_REPLAY_STATUS_V1",
                    "state": "DISABLED",
                    "detail": "replay Codex gateway is not configured",
                    "prompting_enabled": False,
                    "production_data_access": False,
                })
            else:
                self._json(200, self.codex_gateway.status())
            return
        if request.path == "/api/v1/commentary/current":
            query = parse_qs(request.query)
            session = query.get("session", [""])[0]
            as_of = query.get("as_of", [""])[0]
            if not session or not as_of or self.commentary is None:
                self._json(400 if self.commentary else 503, {"error": "session, as_of and configured commentary are required"})
                return
            exact = self.commentary.store.exact(session, as_of)
            if (exact is not None and exact.get("generation_revision") == GENERATION_REVISION
                    and exact.get("codex_status") == "AVAILABLE"):
                self._json(200, {**exact, "delivery_state": "STORED"})
                return
            queue_state = self.commentary_queue.request(session, as_of) if self.commentary_queue else "DISABLED"
            prior = self.commentary.store.current(session, as_of)
            if prior is not None:
                self._json(200, {**prior, "delivery_state": queue_state,
                                 "requested_as_of": as_of, "stale_for_cursor": True})
            else:
                self._json(202, {"schema": "NEW_DIVERGENCE_COMMENTARY_PENDING_V1",
                                 "session": session, "as_of": as_of, "delivery_state": queue_state})
            return
        if request.path == "/api/v1/commentary/status":
            if self.commentary_queue is None:
                self._json(503, {"state": "DISABLED"})
            else:
                self._json(200, self.commentary_queue.status())
            return
        if request.path == "/api/v1/commentary/history":
            query = parse_qs(request.query)
            session = query.get("session", [""])[0]
            if not session or self.commentary is None:
                self._json(400 if self.commentary else 503, {"error": "session and configured commentary are required"})
                return
            self._json(200, {"session": session, "commentary": self.commentary.store.history(session)})
            return
        prefix = "/api/v1/sessions/"
        if request.path.startswith(prefix):
            session = unquote(request.path[len(prefix):])
            if not session or "/" in session:
                self._json(404, {"error": "unknown API route"})
                return
            query = parse_qs(request.query)
            as_of_values = query.get("as_of", [])
            if len(as_of_values) > 1:
                self._json(400, {"error": "as_of may be specified once"})
                return
            try:
                payload = ProjectionReadModel(Path(self.directory)).session(
                    session,
                    as_of=as_of_values[0] if as_of_values else None,
                )
                self._json(200, payload)
            except KeyError as error:
                self._json(404, {"error": str(error)})
            except (OSError, TypeError, ValueError) as error:
                self._json(400, {"error": str(error)})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - inherited HTTP API
        request = urlparse(self.path)
        if request.path != "/api/v1/codex/explain":
            self._json(404, {"error": "unknown API route"})
            return
        if self.codex_gateway is None or not self.codex_gateway.prompting_enabled:
            self._json(503, {"error": "replay Codex explanations are not configured"})
            return
        supplied = self.headers.get("X-New-Divergence-Codex-Token", "")
        expected = self.codex_access_token or ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            self._json(401, {"error": "valid replay Codex access token required"})
            return
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            self._json(415, {"error": "Content-Type must be application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid Content-Length"})
            return
        if length <= 0 or length > 2_048:
            self._json(413, {"error": "request body must be between 1 and 2048 bytes"})
            return
        try:
            value = json.loads(self.rfile.read(length))
            result = self.codex_gateway.explain(value)
            self._json(200, result)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            self._json(400, {"error": str(error)})
        except CodexReplayError as error:
            text = str(error)
            status = 429 if "rate limit" in text or "already running" in text else 503
            self._json(status, {"error": text})


def _read_access_token(path: Path | None) -> str | None:
    if path is None:
        return None
    token_path = Path(path).resolve()
    if not token_path.is_file():
        raise FileNotFoundError(f"Codex access token file is not readable: {token_path}")
    token = token_path.read_text(encoding="utf-8").strip()
    if not 32 <= len(token) <= 256 or any(character.isspace() for character in token):
        raise ValueError("Codex access token must contain 32 to 256 non-whitespace characters")
    return token


def serve(
    directory: Path,
    host: str,
    port: int,
    *,
    codex_host: str = "127.0.0.1",
    codex_port: int = 4500,
    codex_cwd: Path = Path("/home/codexuser/banknifty-codex-worker"),
    codex_token_file: Path | None = None,
    commentary_db: Path | None = None,
) -> None:
    root = Path(directory).resolve()
    if not (root / "catalog.json").is_file():
        raise FileNotFoundError(f"browser projection is not built: {root}")
    identity = _browser_identity(root)
    if identity["browser_runtime_version"] != RUNTIME_VERSION:
        raise ValueError(
            "browser projection runtime mismatch: "
            f"built={identity['browser_runtime_version']!r}, installed={RUNTIME_VERSION!r}; "
            "run build-browser again"
        )
    token = _read_access_token(codex_token_file)
    gateway = ReplayCodexGateway(
        root,
        CodexAppServerClient(codex_host, codex_port, codex_cwd),
        prompting_enabled=token is not None,
    )
    commentary = None if token is None else ReplayCommentaryCoordinator(
        root,
        CommentaryStore(commentary_db or (root / "commentary.sqlite3")),
        gateway.client,
    )
    commentary_queue = None if commentary is None else ReplayCommentaryQueue(commentary)
    if commentary_queue is not None:
        commentary_queue.start()
    class Handler(_Handler):
        codex_gateway = gateway
        codex_access_token = token
        pass

    Handler.commentary = commentary
    Handler.commentary_queue = commentary_queue

    handler = partial(Handler, directory=str(root))
    try:
        with ThreadingHTTPServer((host, port), handler) as server:
            server.serve_forever()
    finally:
        if commentary_queue is not None:
            commentary_queue.stop()
