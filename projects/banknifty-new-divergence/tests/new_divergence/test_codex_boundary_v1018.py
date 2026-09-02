from pathlib import Path
import socket

import pytest

from banknifty_profiler.new_divergence.codex_bridge import CodexWorkerProbe
from banknifty_profiler.new_divergence.live_service import build_live_browser


def test_codex_probe_refuses_every_non_loopback_address() -> None:
    with pytest.raises(ValueError, match="loopback"):
        CodexWorkerProbe("0.0.0.0", 4500)
    with pytest.raises(ValueError, match="literal loopback"):
        CodexWorkerProbe("localhost", 4500)


def test_codex_probe_reports_reachable_without_enabling_prompts() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        status = CodexWorkerProbe("127.0.0.1", port).status()
    assert status["state"] == "REACHABLE_UNVERIFIED"
    assert status["prompting_enabled"] is False
    assert status["production_data_access"] is False


def test_codex_probe_fails_closed_when_worker_is_offline() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    assert CodexWorkerProbe("127.0.0.1", port).status()["state"] == "OFFLINE"


def test_live_browser_exposes_status_only_without_prompt_controls(tmp_path: Path) -> None:
    target = build_live_browser(tmp_path / "browser")
    html = (target / "live.html").read_text(encoding="utf-8")
    script = (target / "live.js").read_text(encoding="utf-8")
    assert 'id="codexStatus"' in html
    assert "/api/v1/codex/status" in script
    assert "prompt" not in html.lower().replace("prompts are disabled", "")
    assert "/api/v1/codex/ask" not in script


def test_codex_worker_unit_and_installer_are_localhost_only() -> None:
    project = Path(__file__).resolve().parents[2]
    installer = (project / "install_codex_worker.sh").read_text(encoding="utf-8")
    unit = (
        project / "systemd/banknifty-new-divergence-codex.service.in"
    ).read_text(encoding="utf-8")
    assert 'codex_host="127.0.0.1"' in installer
    assert "app-server --listen ws://@@CODEX_HOST@@:@@CODEX_PORT@@" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=@@CODEX_HOME@@ @@WORK_ROOT@@" in unit
