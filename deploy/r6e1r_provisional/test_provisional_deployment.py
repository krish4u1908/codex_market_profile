from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "deploy/r6e1r_provisional"
VALIDATOR = PACKAGE_ROOT / "validate_clean_start.py"
RENDERER = PACKAGE_ROOT / "render_service_units.py"
MANIFEST = ROOT / "manifests/r6e1r_provisional_deployment_package_manifest.json"
COMPANION = ROOT / "manifests/r6e1r_provisional_deployment_package_manifest.sha256"
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
BASE_COMMIT = "88f30e740d55376d1eb9ed091a4080b3372a2757"
FINAL_MANIFEST_SHA256 = (
    "b7bdbc5ed602aa1a5a737878bf5d20ad696764e7358ec8ca1b9cc3ed4943a013"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    collector = tmp_path / "collector"
    deployment = tmp_path / "deployment"
    (collector / "raw").mkdir(parents=True)
    (collector / "oi").mkdir()
    (deployment / "config").mkdir(parents=True)
    for directory in (
        collector,
        collector / "raw",
        collector / "oi",
        deployment,
        deployment / "config",
    ):
        directory.chmod(0o700)
    shutil.copyfile(
        PACKAGE_ROOT / "r6e1r-runtime-config.json.example",
        deployment / "config/r6e1r-runtime-config.json",
    )
    shutil.copyfile(
        PACKAGE_ROOT / "r6e1r-activation.json.example",
        deployment / "config/r6e1r-activation.json",
    )
    for path in (deployment / "config").iterdir():
        path.chmod(0o600)
    return collector, deployment


def _validator_command(
    action: str,
    collector: Path,
    deployment: Path,
) -> list[str]:
    return [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(VALIDATOR),
        action,
        "--repository-root",
        str(ROOT),
        "--collector-root",
        str(collector),
        "--deploy-root",
        str(deployment),
        "--state-root",
        str(deployment / "state"),
        "--runtime-config",
        str(deployment / "config/r6e1r-runtime-config.json"),
        "--activation",
        str(deployment / "config/r6e1r-activation.json"),
        "--attestation",
        str(
            deployment
            / "config/r6e1r-provisional-clean-start-attestation.json"
        ),
    ]


def _run_validator(
    action: str,
    collector: Path,
    deployment: Path,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        _validator_command(action, collector, deployment),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stderr == ""
    return result, json.loads(result.stdout)


def _prepare(tmp_path: Path) -> tuple[Path, Path, dict]:
    collector, deployment = _layout(tmp_path)
    completed, result = _run_validator("prepare", collector, deployment)
    assert completed.returncode == 0, result
    assert result["ok"] is True
    return collector, deployment, result


def test_provisional_package_manifest_is_exact_and_final_manifest_unchanged() -> None:
    engine_path = ROOT / "manifests/r6e1r_engine_source_manifest.json"
    engine = json.loads(engine_path.read_text())
    package = json.loads(MANIFEST.read_text())
    deployment_only = {
        "deploy/r6e1r_provisional/README.md",
        "deploy/r6e1r_provisional/render_service_units.py",
        "deploy/r6e1r_provisional/r6e1r-activation.json.example",
        "deploy/r6e1r_provisional/r6e1r-provisional-readonly-gateway.service",
        "deploy/r6e1r_provisional/r6e1r-provisional-shadow.service",
        "deploy/r6e1r_provisional/r6e1r-provisional-status.json",
        "deploy/r6e1r_provisional/r6e1r-runtime-config.json.example",
        "deploy/r6e1r_provisional/validate_clean_start.py",
        "manifests/r6e1r_engine_source_manifest.json",
        "manifests/r6e1r_engine_source_manifest.sha256",
    }
    expected = sorted(set(engine["allowlist"]) | deployment_only)
    assert package["schema"] == (
        "R6E1R_PROVISIONAL_DEPLOYMENT_PACKAGE_MANIFEST_V1"
    )
    assert package["classification"] == CLASSIFICATION
    assert package["engine_base_commit"] == BASE_COMMIT
    assert package["provisional_status"] == (
        "PROVISIONAL_CLEAN_START_FULL_SIX_PENDING"
    )
    assert package["final_equivalence_status"] == (
        "PENDING_FULL_SIX_ALL_NINE"
    )
    assert package["state_origin"] == "EMPTY_AT_PREPARATION"
    assert package["preloaded_state"] is False
    assert package["historical_replay_certified"] is False
    assert package["final_tag_authorized"] is False
    assert package["allowlist"] == expected
    assert package["file_count"] == len(expected) == len(package["files"]) == 48
    assert [row["path"] for row in package["files"]] == expected

    aggregate = hashlib.sha256()
    for row in package["files"]:
        path = ROOT / row["path"]
        assert path.is_file() and not path.is_symlink()
        assert row["size"] == path.stat().st_size
        assert row["sha256"] == _sha256(path)
        aggregate.update(
            f'{row["path"]}\0{row["sha256"]}\0{row["size"]}\n'.encode()
        )
    assert package["package_hash"] == aggregate.hexdigest()
    assert COMPANION.read_text().split() == [
        _sha256(MANIFEST),
        "manifests/r6e1r_provisional_deployment_package_manifest.json",
    ]

    # Option 2 adds a parallel package. It must not reseal or relax final V2.
    assert _sha256(
        ROOT / "manifests/r6e1r_deployment_package_manifest.json"
    ) == FINAL_MANIFEST_SHA256


def test_provisional_configuration_bytes_are_exact_a12_runtime_bytes() -> None:
    assert (
        (PACKAGE_ROOT / "r6e1r-runtime-config.json.example").read_bytes()
        == (ROOT / "deploy/r6e1r/r6e1r-runtime-config.json.example").read_bytes()
    )
    assert (
        (PACKAGE_ROOT / "r6e1r-activation.json.example").read_bytes()
        == (ROOT / "deploy/r6e1r/r6e1r-activation.json.example").read_bytes()
    )
    package = json.loads(MANIFEST.read_text())
    engine = json.loads(
        (ROOT / "manifests/r6e1r_engine_source_manifest.json").read_text()
    )
    assert package["engine_hash"] == engine["engine_hash"]
    assert package["engine_source_manifest_sha256"] == _sha256(
        ROOT / "manifests/r6e1r_engine_source_manifest.json"
    )


def test_status_contract_cannot_claim_final_verification() -> None:
    status = json.loads(
        (PACKAGE_ROOT / "r6e1r-provisional-status.json").read_text()
    )
    assert status == {
        "classification": CLASSIFICATION,
        "engine_base_commit": BASE_COMMIT,
        "final_equivalence_status": "PENDING_FULL_SIX_ALL_NINE",
        "final_tag_authorized": False,
        "historical_replay_certified": False,
        "limitations": [
            "state begins empty and is reconstructed only from collector sessions on or after 2026-08-26",
            "the six-session all-nine acceptance run is still pending",
            "verified historical preload and the final verification tag are prohibited",
            "the provisional state is not promoted into the final deployment",
        ],
        "preloaded_state": False,
        "schema": "R6E1R_PROVISIONAL_CLEAN_START_STATUS_V1",
        "state_origin": "EMPTY_AT_PREPARATION",
        "status": "PROVISIONAL_CLEAN_START_FULL_SIX_PENDING",
    }


def test_prepare_creates_only_empty_state_and_sanitized_attestation(
    tmp_path: Path,
) -> None:
    collector, deployment, result = _prepare(tmp_path)
    state = deployment / "state"
    attestation_path = (
        deployment / "config/r6e1r-provisional-clean-start-attestation.json"
    )
    assert state.is_dir() and list(state.iterdir()) == []
    assert state.stat().st_mode & 0o077 == 0
    assert attestation_path.stat().st_mode & 0o077 == 0
    assert result["state_mode"] == "NEW_EMPTY_STATE"
    assert result["preloaded_state"] is False
    assert result["historical_replay_certified"] is False
    assert result["final_tag_authorized"] is False

    attestation_text = attestation_path.read_text()
    attestation = json.loads(attestation_text)
    assert str(tmp_path) not in attestation_text
    assert str(collector) not in attestation_text
    assert str(deployment) not in attestation_text
    assert attestation["state_origin"] == "EMPTY_AT_PREPARATION"
    assert attestation["engine_base_commit"] == BASE_COMMIT

    completed, checked = _run_validator(
        "start-check", collector, deployment
    )
    assert completed.returncode == 0
    assert checked["ok"] is True
    assert checked["state_mode"] == "NEW_EMPTY_STATE"
    assert checked["state_file_count"] == 0
    assert checked["sqlite_status"] == "NOT_INITIALIZED"


def test_prepare_refuses_existing_state_and_never_overlays_it(
    tmp_path: Path,
) -> None:
    collector, deployment = _layout(tmp_path)
    state = deployment / "state"
    state.mkdir(mode=0o700)
    sentinel = state / "do-not-touch"
    sentinel.write_text("preserved\n")
    sentinel.chmod(0o600)
    completed, result = _run_validator("prepare", collector, deployment)
    assert completed.returncode == 1
    assert result["error_code"] == "STATE_ROOT_ALREADY_EXISTS"
    assert sentinel.read_text() == "preserved\n"
    assert not (
        deployment / "config/r6e1r-provisional-clean-start-attestation.json"
    ).exists()


def test_prepare_refuses_mutated_runtime_configuration(tmp_path: Path) -> None:
    collector, deployment = _layout(tmp_path)
    path = deployment / "config/r6e1r-runtime-config.json"
    value = json.loads(path.read_text())
    value["analytical_refresh_seconds"] = 31.0
    path.write_text(json.dumps(value) + "\n")
    path.chmod(0o600)
    completed, result = _run_validator("prepare", collector, deployment)
    assert completed.returncode == 1
    assert result["error_code"] == (
        "RUNTIME_CONFIGURATION_IDENTITY_MISMATCH"
    )
    assert not (deployment / "state").exists()


def test_start_check_accepts_private_runtime_state_and_sqlite(
    tmp_path: Path,
) -> None:
    collector, deployment, _result = _prepare(tmp_path)
    state = deployment / "state"
    checkpoints = state / "checkpoints.json"
    checkpoints.write_text("{}\n")
    checkpoints.chmod(0o600)
    analytical = state / "live_analytical_orchestrator.json"
    analytical.write_text(
        json.dumps(
            {
                "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
                "sessions": {},
                "outputs": {},
                "cross_layer_contexts": {},
                "dirty_sessions": [],
                "finalized_sessions": [],
            }
        )
        + "\n"
    )
    analytical.chmod(0o600)
    (state / "ledgers").mkdir(mode=0o700)
    (state / "analytical_observation_stage").mkdir(mode=0o700)
    database = state / "dedup.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table runtime_meta(key text primary key,value text not null)"
        )
    database.chmod(0o600)

    completed, result = _run_validator(
        "start-check", collector, deployment
    )
    assert completed.returncode == 0, result
    assert result["state_mode"] == "AUTHENTICATED_RESTART"
    assert result["state_file_count"] == 3
    assert result["state_directory_count"] == 2
    assert result["sqlite_status"] == "OK"


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("state_symlink", "STATE_TREE_INVALID"),
        ("public_state_file", "STATE_TREE_INVALID"),
        ("corrupt_sqlite", "DATABASE_QUICK_CHECK_FAILED"),
        ("public_attestation", "ATTESTATION_INVALID"),
    ),
)
def test_start_check_refuses_unsafe_or_corrupt_state(
    tmp_path: Path,
    mutation: str,
    error_code: str,
) -> None:
    collector, deployment, _result = _prepare(tmp_path)
    state = deployment / "state"
    if mutation == "state_symlink":
        (state / "unsafe").symlink_to(deployment / "config")
    elif mutation == "public_state_file":
        path = state / "unsafe"
        path.write_text("unsafe\n")
        path.chmod(0o644)
    elif mutation == "corrupt_sqlite":
        path = state / "dedup.sqlite3"
        path.write_bytes(b"not sqlite")
        path.chmod(0o600)
    elif mutation == "public_attestation":
        (
            deployment
            / "config/r6e1r-provisional-clean-start-attestation.json"
        ).chmod(0o644)
    completed, result = _run_validator(
        "start-check", collector, deployment
    )
    assert completed.returncode == 1
    assert result["error_code"] == error_code
    assert str(tmp_path) not in completed.stdout


def test_start_check_refuses_replaced_state_root(tmp_path: Path) -> None:
    collector, deployment, _result = _prepare(tmp_path)
    state = deployment / "state"
    original = deployment / "original-state"
    state.rename(original)
    state.mkdir(mode=0o700)
    completed, result = _run_validator(
        "start-check", collector, deployment
    )
    assert completed.returncode == 1
    assert result["error_code"] == "ATTESTATION_STATE_REPLACED"
    assert original.is_dir()


def test_unit_templates_pin_authenticated_bytes_and_isolate_names() -> None:
    backend = (
        PACKAGE_ROOT / "r6e1r-provisional-shadow.service"
    ).read_text()
    gateway = (
        PACKAGE_ROOT / "r6e1r-provisional-readonly-gateway.service"
    ).read_text()
    assert "Conflicts=r6e1r-shadow.service" in backend
    assert "Conflicts=r6e1r-readonly-gateway.service" in gateway
    assert "After=r6e1r-provisional-shadow.service" in gateway
    assert "r6e1r-v2-six-a12a586-v1.service" not in backend + gateway
    assert "CPUQuota=100%" in backend
    assert "127.0.0.1 --port 18805 --mode shadow" in backend
    assert "--require-isolation" in gateway
    assert "--backend http://127.0.0.1:18805" in gateway
    assert "/bin/sh -c" not in backend + gateway
    assert "exec 3<" not in backend + gateway
    assert "exec 4<" not in backend + gateway
    assert "exec 5<" not in backend + gateway
    assert "origin=sys.argv[1]" in backend + gateway
    assert "origin,config_path,activation_path=sys.argv[1:4]" in backend
    assert _sha256(VALIDATOR) in backend
    assert _sha256(ROOT / "scripts/run_r6e_shadow.py") in backend
    assert _sha256(
        PACKAGE_ROOT / "r6e1r-runtime-config.json.example"
    ) in backend
    assert _sha256(
        PACKAGE_ROOT / "r6e1r-activation.json.example"
    ) in backend
    assert _sha256(ROOT / "deploy/r6e1r/health_readiness_check.py") in (
        backend + gateway
    )
    assert _sha256(ROOT / "deploy/r6e1r/read_only_gateway.py") in gateway


def test_renderer_emits_only_distinct_provisional_units(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--repository-root",
            "/srv/r6e1r-provisional-repository",
            "--collector-root",
            "/srv/r6e1r-collector",
            "--deploy-root",
            "/srv/r6e1r-provisional-deployment",
            "--python",
            "/opt/r6e1r-venv/bin/python3",
            "--gateway-port",
            "8806",
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    value = json.loads(result.stdout)
    assert value["ok"] is True
    assert {row["name"] for row in value["units"]} == {
        "r6e1r-provisional-shadow.service",
        "r6e1r-provisional-readonly-gateway.service",
    }
    assert not (tmp_path / "r6e1r-shadow.service").exists()
    assert not (tmp_path / "r6e1r-readonly-gateway.service").exists()
    for row in value["units"]:
        path = tmp_path / row["name"]
        payload = path.read_bytes()
        assert row["sha256"] == hashlib.sha256(payload).hexdigest()
        assert row["size"] == len(payload)
        assert re.search(rb"@[A-Z0-9_]+@", payload) is None
    assert b"--port 8806" in (
        tmp_path / "r6e1r-provisional-readonly-gateway.service"
    ).read_bytes()


def test_rendered_backend_guard_executes_through_real_user_systemd() -> None:
    """Exercise the rendered pre-start command through the real unit parser."""
    runtime_root = Path(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    )
    runtime_units = runtime_root / "systemd/user"
    runtime_units.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="r6e1r-provisional-systemd-", dir=ROOT.parent
    ) as raw_root:
        test_root = Path(raw_root)
        collector, deployment, _result = _prepare(test_root)
        rendered_root = test_root / "rendered"
        rendered_root.mkdir(mode=0o700)
        rendered = subprocess.run(
            [
                sys.executable,
                str(RENDERER),
                "--repository-root",
                str(ROOT),
                "--collector-root",
                str(collector),
                "--deploy-root",
                str(deployment),
                "--python",
                sys.executable,
                "--gateway-port",
                "8805",
                "--output-dir",
                str(rendered_root),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert rendered.returncode == 0, rendered.stdout

        source = (
            rendered_root / "r6e1r-provisional-shadow.service"
        ).read_text()
        probe_lines: list[str] = []
        guarded_line = ""
        for line in source.splitlines():
            if line.startswith("Conflicts="):
                continue
            if line.startswith("ExecStartPre=") and "start-check" in line:
                guarded_line = line
            if line.startswith("ExecStart="):
                probe_lines.append("ExecStart=/usr/bin/true")
            elif line.startswith("ExecStartPost="):
                continue
            elif line.startswith("Restart="):
                probe_lines.append("Restart=no")
            else:
                probe_lines.append(line)
        assert guarded_line
        assert "/bin/sh" not in guarded_line

        suffix = hashlib.sha256(str(test_root).encode()).hexdigest()[:12]
        unit_name = f"r6e1r-provisional-guard-test-{suffix}.service"
        unit_path = runtime_units / unit_name
        assert not unit_path.exists()
        unit_path.write_text("\n".join(probe_lines) + "\n")
        unit_path.chmod(0o600)
        try:
            reloaded = subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            assert reloaded.returncode == 0, reloaded.stderr
            started = subprocess.run(
                ["systemctl", "--user", "start", unit_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert started.returncode == 0, started.stderr
            shown = subprocess.run(
                [
                    "systemctl",
                    "--user",
                    "show",
                    unit_name,
                    "--property=Result",
                    "--property=ExecMainStatus",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            assert shown.returncode == 0, shown.stderr
            assert "Result=success" in shown.stdout
            assert "ExecMainStatus=0" in shown.stdout
        finally:
            subprocess.run(
                ["systemctl", "--user", "stop", unit_name],
                capture_output=True,
                check=False,
                timeout=15,
            )
            unit_path.unlink(missing_ok=True)
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                check=False,
                timeout=15,
            )


@pytest.mark.parametrize("port", (8803, 8804, 8811))
def test_renderer_refuses_unapproved_ports_sanitized(
    tmp_path: Path,
    port: int,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(RENDERER),
            "--repository-root",
            "/srv/repository",
            "--collector-root",
            "/srv/collector",
            "--deploy-root",
            "/srv/deployment",
            "--python",
            "/opt/venv/bin/python3",
            "--gateway-port",
            str(port),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "schema": "R6E1R_PROVISIONAL_RENDERED_USER_UNITS_V1",
        "ok": False,
        "error": "PROVISIONAL_UNIT_RENDER_REFUSED",
    }
    assert result.stderr == ""


def test_runbook_never_authorizes_final_tag_or_full_six_interference() -> None:
    readme = (PACKAGE_ROOT / "README.md").read_text()
    normalized = " ".join(readme.split())
    assert "Keep `r6e1r-v2-six-a12a586-v1.service`" in readme
    assert "Keep collectors and existing ports 8803/8804 untouched" in readme
    assert "Do not create `r6e1r-live-shadow-verified`" in readme
    assert "Never copy or merge the provisional clean-start state" in normalized
    assert "validate_clean_start.py prepare" in readme
    assert "r6e1r-provisional-shadow.service" in readme
    assert "r6e1r-provisional-readonly-gateway.service" in readme
    assert "deploy/r6e1r/validate_preloaded_state.py" in readme


def test_package_contains_no_likely_credentials_or_private_host_values() -> None:
    forbidden = re.compile(
        r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,}|password\s*[:=]\s*[^<\s]+|"
        r"/opt/" r"banknifty|/home/[A-Za-z0-9._-]+)"
    )
    package = json.loads(MANIFEST.read_text())
    for row in package["files"]:
        path = ROOT / row["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert forbidden.search(text) is None, row["path"]
