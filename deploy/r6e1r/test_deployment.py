from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parent
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"


def _bubblewrap_prefix() -> list[str]:
    return [
        "/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--share-net",
        "--disable-userns", "--assert-userns-disabled", "--die-with-parent",
        "--new-session", "--cap-drop", "ALL", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", str(ROOT), "/app/deploy/r6e1r", "--dev", "/dev",
        "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/run",
        "--chdir", "/app", "/usr/bin/python3", "-I", "-B",
    ]


def _run_in_gateway_systemd_boundary(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Exercise bwrap below the same compatible user-unit restrictions."""
    properties = [
        "WorkingDirectory=" + str(ROOT.parents[1]),
        "UMask=0077",
        "UnsetEnvironment=SSH_AUTH_SOCK DBUS_SESSION_BUS_ADDRESS",
        "KeyringMode=private",
        "MemoryHigh=192M", "MemoryMax=256M", "MemorySwapMax=0",
        "CPUQuota=50%", "TasksMax=128", "LimitNOFILE=4096",
        "OOMPolicy=stop", "NoNewPrivileges=true", "PrivateTmp=true",
        "PrivateDevices=true", "ProtectHome=true", "ProtectSystem=strict",
        "ReadOnlyPaths=" + str(ROOT.parents[1]),
        "InaccessiblePaths=-/opt/banknifty-collector/data-prod-v4",
        "InaccessiblePaths=-/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/state",
        "InaccessiblePaths=-/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/config",
        f"InaccessiblePaths=-/run/user/{os.getuid()}/gnupg",
        "ProtectControlGroups=true", "ProtectKernelModules=true",
        "ProtectClock=true", "RestrictSUIDSGID=true",
        "RestrictNamespaces=~net", "LockPersonality=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=",
    ]
    systemd = [
        "/usr/bin/systemd-run", "--user", "--wait", "--collect", "--pipe",
        "--quiet",
    ]
    for value in properties:
        systemd.extend(("--property", value))
    return subprocess.run(
        [*systemd, "--", *_bubblewrap_prefix(), *command],
        check=True, capture_output=True, text=True, timeout=15,
    )


def test_user_units_are_isolated_and_resource_bounded() -> None:
    backend = (ROOT / "r6e1r-shadow.service").read_text()
    gateway = (ROOT / "r6e1r-readonly-gateway.service").read_text()
    combined = backend + gateway

    assert "User=" not in combined and "Group=" not in combined
    assert "WantedBy=default.target" in backend
    assert "WantedBy=default.target" in gateway
    assert "multi-user.target" not in combined
    assert "/var/lib/" not in combined and "/etc/banknifty" not in combined
    assert "PYTHONPATH=/opt/banknifty/repositories/banknifty-market-profiler/src" in backend
    assert "--bind 127.0.0.1 --port 18805" in backend
    assert "--bind 0.0.0.0 --port 8805 --backend http://127.0.0.1:18805" in gateway
    assert "8803" not in combined and "8804" not in combined
    assert "Restart=on-failure" in backend and "Restart=on-failure" in gateway
    for directive in (
        "MemoryHigh=", "MemoryMax=", "CPUQuota=", "TasksMax=",
        "NoNewPrivileges=true", "ProtectSystem=strict", "StandardOutput=journal",
        "UnsetEnvironment=SSH_AUTH_SOCK DBUS_SESSION_BUS_ADDRESS",
        "KeyringMode=private", "PrivateDevices=true",
        "ProtectKernelModules=true",
    ):
        assert directive in backend and directive in gateway
    assert "network.target" not in combined
    assert "ExecStart=/usr/bin/bwrap" in gateway
    assert "ExecStartPost=/usr/bin/bwrap" in gateway
    assert "--unshare-all --unshare-user --share-net" in gateway
    assert "--disable-userns --assert-userns-disabled" in gateway
    assert "--clearenv" in gateway and "--require-isolation" in gateway
    assert "RestrictNamespaces=~net" in gateway
    assert "InaccessiblePaths=" in gateway
    # These systemd-created namespaces prevent rootless bwrap from mounting its
    # private procfs. The backend retains them; bwrap supplies the gateway's
    # stronger private PID/mount/UTS boundary and verifies it at startup.
    for incompatible in (
        "ProtectKernelTunables=true", "ProtectKernelLogs=true",
        "ProtectHostname=true",
    ):
        assert incompatible in backend and incompatible not in gateway
    prefix = " ".join(_bubblewrap_prefix())
    assert f"ExecStart={prefix} /app/deploy/r6e1r/read_only_gateway.py" in gateway
    assert f"ExecStartPost={prefix} /app/deploy/r6e1r/health_readiness_check.py" in gateway
    for hidden in (
        "/opt/banknifty-collector/data-prod-v4",
        "r6e1r_final_live_shadow/state",
        "r6e1r_final_live_shadow/config",
        "%t/gnupg",
    ):
        assert hidden in gateway


def test_templates_are_non_secret_and_preserve_runtime_contract() -> None:
    activation = json.loads((ROOT / "r6e1r-activation.json.example").read_text())
    config = json.loads((ROOT / "r6e1r-runtime-config.json.example").read_text())
    assert activation["activation_day"] == "2026-08-26"
    assert activation["classification"] == CLASSIFICATION
    assert config["timezone"] == "Asia/Kolkata"
    assert config["synchronization_tolerance_ms"] == 2000
    assert config["index_symbol"] == "NSE:NIFTYBANK-INDEX"
    assert config["selected_futures_by_session"] == {}
    assert config["analytical_threshold_overrides"] is None
    assert config["max_live_sessions"] == 32
    assert config["engine_source_manifest_path"] == (
        "manifests/r6e1r_engine_source_manifest.json"
    )
    repo = ROOT.parents[1]
    manifest_path = repo / config["engine_source_manifest_path"]
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert config["engine_source_manifest_sha256"] == actual
    companion = (
        repo / "manifests/r6e1r_engine_source_manifest.sha256"
    ).read_text().split()
    assert companion == [actual, config["engine_source_manifest_path"]]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "R6E1R_ENGINE_SOURCE_MANIFEST_V1"
    assert manifest["classification"] == CLASSIFICATION
    assert manifest["file_count"] == len(manifest["files"])
    serialized = json.dumps({"activation": activation, "config": config}).lower()
    for token in ("password", "api_key", "secret", "credential", "token"):
        assert token not in serialized


class _ProbeHandler(BaseHTTPRequestHandler):
    readiness_status = 503
    readiness = {
        "ready": False,
        "reasons": ["STALE_DATA"],
        "availability_state": "STALE_PARTIAL",
        "checkpoint_valid": True,
        "future_joins": 0,
        "synchronization_tolerance_violations": 0,
        "manifest_verified": True,
    }

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            status = 200
            value = {"alive": True, "classification": CLASSIFICATION}
        elif self.path == "/api/readiness":
            status = self.readiness_status
            value = self.readiness
        else:
            status = 404
            value = {"error": "NOT_FOUND"}
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture()
def probe_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_health_helper_accepts_structured_stale_readiness(probe_server: str) -> None:
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    result = module["probe"](probe_server, 2.0)
    assert result["health_http_status"] == 200
    assert result["readiness_http_status"] == 503
    assert result["ready"] is False
    assert result["readiness_reasons"] == ["STALE_DATA"]
    assert result["checkpoint_valid"] is True
    assert result["future_joins"] == 0
    assert result["synchronization_tolerance_violations"] == 0
    assert result["manifest_verified"] is True


@pytest.mark.parametrize(
    "override",
    (
        {"reasons": ["CHECKPOINT_INTEGRITY_FAILED"]},
        {"checkpoint_valid": False},
        {"future_joins": 1},
        {"synchronization_tolerance_violations": 1},
        {"manifest_verified": False},
        {"reasons": []},
    ),
)
def test_health_helper_rejects_non_benign_503(
    probe_server: str, monkeypatch: pytest.MonkeyPatch, override: dict,
) -> None:
    monkeypatch.setattr(
        _ProbeHandler,
        "readiness",
        {**_ProbeHandler.readiness, **override},
    )
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    with pytest.raises(RuntimeError):
        module["probe"](probe_server, 2.0)


def test_gateway_bubblewrap_self_test_hides_same_uid_runtime() -> None:
    result = _run_in_gateway_systemd_boundary([
        "/app/deploy/r6e1r/read_only_gateway.py",
        "--backend", "http://127.0.0.1:18805", "--isolation-self-test",
    ])
    value = json.loads(result.stdout)
    assert value["collector_state_config_hidden"] is True
    assert value["user_runtime_hidden"] is True
    assert value["process_namespace_private"] is True
    assert value["visible_pid_count"] <= 2


def test_gateway_post_start_probe_runs_in_same_systemd_bubblewrap_boundary() -> None:
    result = _run_in_gateway_systemd_boundary([
        "/app/deploy/r6e1r/health_readiness_check.py", "--help",
    ])
    assert "--base-url BASE_URL" in result.stdout


@pytest.mark.parametrize(
    "value",
    (
        "https://127.0.0.1:8805",
        "http://user:password@127.0.0.1:8805",
        "http://127.0.0.1",
        "http://127.0.0.1:8805/api/health",
        "http://127.0.0.1:8805?target=elsewhere",
    ),
)
def test_health_helper_refuses_unsafe_or_ambiguous_origins(value: str) -> None:
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    with pytest.raises(ValueError):
        module["normalized_base_url"](value)


def test_health_helper_never_logs_credentials_from_invalid_origin() -> None:
    secret = "probe-password-must-not-appear"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "health_readiness_check.py"),
            "--base-url",
            f"http://user:{secret}@127.0.0.1:8805",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert json.loads(result.stdout)["base_url"] == "REDACTED_INVALID_ORIGIN"
