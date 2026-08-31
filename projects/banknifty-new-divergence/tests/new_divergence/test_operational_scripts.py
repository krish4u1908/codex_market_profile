from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_shell_operational_scripts_parse() -> None:
    for name in (
        "install.sh",
        "publish_replay.sh",
        "install_gui_service.sh",
        "install_nightly_context.sh",
        "run_nightly_context.sh",
        "install_sample_generator.sh",
        "scripts/run_banknifty_samples.sh.in",
    ):
        subprocess.run(["bash", "-n", str(ROOT / name)], check=True)


def test_replay_publisher_refuses_root_and_overwrite_is_not_implemented() -> None:
    script = (ROOT / "publish_replay.sh").read_text(encoding="utf-8")
    assert "run this replay as the normal project owner, not with sudo" in script
    assert "replay-archive" in script
    assert "verify-run" in script
    assert "build-browser" in script
    assert "--context-state-root" in script
    assert "--disable-oi-vpoc" in script
    assert "--disable-volume-profile" in script
    assert "rm -" not in script


def test_service_defaults_to_localhost_and_non_root_account() -> None:
    script = (ROOT / "install_gui_service.sh").read_text(encoding="utf-8")
    assert 'gui_host="127.0.0.1"' in script
    assert '"${service_user}" != "root"' in script
    assert "--context-state-root" in script
    assert "--disable-oi-vpoc" in script
    assert "--disable-volume-profile" in script
    assert "--acknowledge-research-only" in (
        ROOT / "systemd" / "banknifty-new-divergence-gui.service.in"
    ).read_text(encoding="utf-8")


def test_v1022_central_commentary_uses_server_token_and_loopback_worker() -> None:
    installer = (ROOT / "install_gui_service.sh").read_text(encoding="utf-8")
    service = (
        ROOT / "systemd" / "banknifty-new-divergence-gui.service.in"
    ).read_text(encoding="utf-8")
    replay = (
        ROOT / "src" / "banknifty_profiler" / "new_divergence" / "static_new" / "replay.html"
    ).read_text(encoding="utf-8")
    script = (
        ROOT / "src" / "banknifty_profiler" / "new_divergence" / "static_new" / "app.js"
    ).read_text(encoding="utf-8")
    assert 'codex_host="127.0.0.1"' in installer
    assert 'openssl rand -hex 32' in installer
    assert 'codex-gui.token' in installer
    assert 'install -o root -g "${service_group}" -m 0640' in installer
    assert '--codex-token-file "$CODEX_TOKEN_FILE"' in service
    assert "ReadOnlyPaths=@CODEX_TOKEN_FILE@" in service
    assert 'id="codexQuestion"' not in replay
    assert "<textarea" not in replay
    assert "Central market-profile commentary" in replay
    assert 'id="codexAccessToken"' not in replay
    assert "/api/v1/commentary/current" in script
    assert "Codex explanation and rule details" in script
    assert "Central commentary: enabled; internal token remains server-side" in installer
    assert "enter in each browser tab" not in installer
    assert '--commentary-db "$COMMENTARY_DB"' in service
    assert "ReadWritePaths=" in service


def test_operations_claim_checkpointed_live_only_in_v1017() -> None:
    operations = (ROOT / "docs" / "OPERATIONS.md").read_text(encoding="utf-8")
    assert "| Live |" in operations
    assert "Yes (V1.0.18)" in operations
    assert "fails closed" in operations


def test_nightly_installer_is_safe_and_install_only_by_default() -> None:
    installer = (ROOT / "install_nightly_context.sh").read_text(encoding="utf-8")
    service = (
        ROOT / "systemd" / "banknifty-new-divergence-nightly.service.in"
    ).read_text(encoding="utf-8")
    timer = (
        ROOT / "systemd" / "banknifty-new-divergence-nightly.timer.in"
    ).read_text(encoding="utf-8")
    assert 'enable_timer=0' in installer
    assert "--enable" in installer
    assert '"${service_user}" != "root"' in installer
    assert "must not be the filesystem root" in installer
    assert "ReadOnlyPaths=@DATA_ROOT@" in service
    assert "PrivateNetwork=true" in service
    assert "Restart=on-failure" in service
    assert "RestartSec=5min" in service
    assert "Restart=on-failure" in service
    assert "nightly-context" in service
    assert "00:15:00 Asia/Kolkata" in timer
    assert "Persistent=true" in timer


def test_sample_generator_installs_beside_collector_and_runs_at_1540_ist() -> None:
    installer = (ROOT / "install_sample_generator.sh").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_banknifty_samples.sh.in").read_text(encoding="utf-8")
    service = (
        ROOT / "systemd" / "banknifty-new-divergence-samples.service.in"
    ).read_text(encoding="utf-8")
    timer = (
        ROOT / "systemd" / "banknifty-new-divergence-samples.timer.in"
    ).read_text(encoding="utf-8")
    assert 'collector_root="${COLLECTOR_ROOT:-/opt/banknifty-collector}"' in installer
    assert "generate_banknifty_samples_v1_0_14.py" in installer
    assert "enable_timer=0" in installer
    assert "--enable" in installer
    assert "generate-samples" in runner or "sample_generator" in runner
    assert "build-browser" in runner
    assert "--context-state-root" in runner
    assert "ReadOnlyPaths=@DATA_ROOT@" in service
    assert "ReadWritePaths=@OUTPUT_ROOT@ @BROWSER_ROOT@" in service
    assert "PrivateNetwork=true" in service
    assert "15:40:00 Asia/Kolkata" in timer
    assert "OnCalendar=*-*-* 15:40:00 Asia/Kolkata" in timer
    assert "Mon..Fri" not in timer
    assert "Persistent=true" in timer


def test_v111_replay_and_gui_defaults_use_one_direct_session_root() -> None:
    publisher = (ROOT / "publish_replay.sh").read_text(encoding="utf-8")
    gui_installer = (ROOT / "install_gui_service.sh").read_text(encoding="utf-8")
    assert 'DIVERGENCE_RUN_ROOT:-${HOME}/divergence/sessions' in publisher
    assert 'run_directory="${run_root}/${session_day}"' in publisher
    assert 'run_directory="${run_root}/sessions/${session_day}"' not in publisher
    assert 'run_root="${service_home}/divergence/sessions"' in gui_installer
    assert "separate non-nested directories" in publisher
    assert "separate non-nested directories" in gui_installer
    assert "must not be the filesystem root" in publisher
