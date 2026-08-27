from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


SCRIPT = Path("scripts/run_r6e_shadow.py")


def _fake_dependency_contracts(fake_site: Path) -> dict[str, dict[str, object]]:
    contracts: dict[str, dict[str, object]] = {}
    for name in ("numpy", "pandas"):
        package = fake_site / name
        rows = []
        for path in sorted(package.rglob("*")):
            if not path.is_file():
                continue
            payload = path.read_bytes()
            digest = base64.urlsafe_b64encode(
                hashlib.sha256(payload).digest()
            ).rstrip(b"=").decode("ascii")
            rows.append((
                path.relative_to(fake_site).as_posix(),
                f"sha256={digest}",
                len(payload),
            ))
        record_relative = f"{name}-test.dist-info/RECORD"
        record = fake_site / record_relative
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(
            "".join(f"{path},{digest},{size}\n" for path, digest, size in rows)
            + f"{name}/__pycache__/installer-generated.pyc,,\n"
        )
        canonical = (
            json.dumps(sorted(rows), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
        contracts[record_relative] = {
            "prefixes": (f"{name}/",),
            "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        }
    return contracts


def _activation_probe(script: Path, repo: Path, fake_site: Path) -> str:
    package_init = repo / "src/banknifty_profiler/__init__.py"
    contracts = _fake_dependency_contracts(fake_site)
    return (
        "import pathlib,runpy;"
        f"m=runpy.run_path({str(script)!r});"
        "sources={'src/banknifty_profiler/__init__.py':"
        f"pathlib.Path({str(package_init)!r}).read_bytes()}};"
        f"m['activate_verified_repository'](pathlib.Path({str(repo)!r}),"
        f"sources,(pathlib.Path({str(fake_site)!r}),),"
        f"dependency_contracts={contracts!r})"
    )


def test_runtime_logs_are_structured_and_never_include_exception_detail(capsys):
    module = runpy.run_path(str(SCRIPT))
    emit = module["emit_runtime_log"]
    emit("SERVICE_RUNNING", "RUNNING")
    emit(
        "INGESTION_CYCLE_ERROR",
        "DEGRADED",
        error=RuntimeError(
            "secret-token raw={\"received_at\":\"private\"} "
            "/sensitive/private-source/raw-record.jsonl"
        ),
    )

    output = capsys.readouterr().out
    assert "secret-token" not in output
    assert "received_at" not in output
    assert "/sensitive/" not in output
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows == [
        {
            "classification": (
                "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
            ),
            "component": "r6e1r-shadow",
            "event": "SERVICE_RUNNING",
            "status": "RUNNING",
        },
        {
            "classification": (
                "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
            ),
            "component": "r6e1r-shadow",
            "error_type": "RuntimeError",
            "event": "INGESTION_CYCLE_ERROR",
            "status": "DEGRADED",
        },
    ]


def test_runtime_entrypoint_suppresses_tracebacks_and_error_text(capsys):
    module = runpy.run_path(str(SCRIPT))

    def fail_with_private_detail():
        raise RuntimeError(
            "secret-token raw={\"received_at\":\"private\"} "
            "/sensitive/private-source/raw-record.jsonl"
        )

    entrypoint = module["entrypoint"]
    entrypoint.__globals__["main"] = fail_with_private_detail
    assert entrypoint() == 1

    output = capsys.readouterr().out
    assert "secret-token" not in output
    assert "received_at" not in output
    assert "/sensitive/" not in output
    assert json.loads(output) == {
        "classification": (
            "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
        ),
        "component": "r6e1r-shadow",
        "error_type": "RuntimeError",
        "event": "SERVICE_FATAL",
        "status": "TERMINATED",
    }

    source = SCRIPT.read_text()
    assert 'state.last_error = f"INGESTION_ERROR:{error_type}"' in source
    assert "traceback.print" not in source
    assert "raise error" not in source
    assert "str(error)" not in source
    assert "repr(error)" not in source


def test_dependency_root_deduplicates_lib64_symlink(tmp_path):
    module = runpy.run_path(str(SCRIPT))
    environment = tmp_path / "venv"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site = environment / "lib" / version / "site-packages"
    site.mkdir(parents=True)
    (environment / "lib64").symlink_to("lib", target_is_directory=True)

    roots = module["_dependency_roots"](environment / "bin/python")

    assert roots == (site.resolve(),)


def test_activation_contract_is_exact_and_captured_before_later_mutation(
    tmp_path,
):
    module = runpy.run_path(str(SCRIPT))
    capture = module["capture_activation_before_import"]
    activation = tmp_path / "activation.json"
    expected = {
        "activation_day": "2026-08-26",
        "classification": (
            "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
        ),
        "scope": (
            "R6E1R isolated live shadow; 2026-08-25 and 2026-08-26 remain "
            "operational diagnostics and are not prospective evidence"
        ),
    }
    activation.write_text(json.dumps(expected))
    captured = capture(activation)
    activation.write_text(json.dumps({**expected, "activation_day": "2020-01-01"}))
    assert captured == expected

    activation.write_text(json.dumps({**expected, "extra": "not-allowed"}))
    try:
        capture(activation)
    except ValueError as error:
        assert str(error) == "activation contract mismatch"
    else:
        raise AssertionError("activation contract accepted an extra field")

    activation.write_text(json.dumps({**expected, "activation_day": "2026-08-25"}))
    try:
        capture(activation)
    except ValueError as error:
        assert str(error) == "activation contract mismatch"
    else:
        raise AssertionError("activation contract accepted a wrong day")


def test_manifest_failure_prevents_package_side_effect_before_import(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    (repo / "manifests").mkdir()
    (repo / "manifests/r6e1r_engine_source_manifest.json").write_text("{}\n")
    config = tmp_path / "runtime.json"
    config.write_text(json.dumps({
        "engine_source_manifest_sha256": "0" * 64,
    }))
    package = tmp_path / "fake-src/banknifty_profiler"
    package.mkdir(parents=True)
    marker = tmp_path / "package-imported"
    (package / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path / "fake-src")
    (tmp_path / "fake-src/sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
    )
    (script.parent / "argparse.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null",
            str(script), "--data-root", str(tmp_path / "data"),
            "--state-root", str(tmp_path / "state"),
            "--config", str(config), "--bind", "127.0.0.1",
            "--port", "18805", "--mode", "shadow",
            "--activation", str(tmp_path / "activation.json"),
        ],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert not marker.exists()
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["event"] == "SERVICE_FATAL"


def test_verified_repository_path_cannot_shadow_pandas_dependency(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    marker = tmp_path / "shadow-imported"
    customization_marker = tmp_path / "site-customization-imported"
    (repo / "src/pandas.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
    )
    (repo / "src/sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
    )
    fake_site = (
        tmp_path / "venv/lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    fake_pandas = fake_site / "pandas"
    fake_pandas.mkdir(parents=True)
    (fake_pandas / "__init__.py").write_text(
        "__version__ = '3.0.5'\nSAFE_DEPENDENCY = True\n"
    )
    fake_numpy = fake_site / "numpy"
    fake_numpy.mkdir()
    (fake_numpy / "__init__.py").write_text("__version__ = '2.5.2'\n")
    (fake_site / "editable.pth").write_text(str(repo / "src") + "\n")
    (fake_site / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(customization_marker)!r}).write_text('BAD')\n"
    )
    probe = _activation_probe(script, repo, fake_site) + (
        ";import pandas;print(pathlib.Path(pandas.__file__).resolve())"
    )
    hostile_tmp = tmp_path / "manager-selected-temp"
    hostile_tmp.mkdir()
    environment = os.environ.copy()
    environment.update({
        "TMPDIR": str(hostile_tmp),
        "TMP": str(hostile_tmp),
        "TEMP": str(hostile_tmp),
    })
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not marker.exists()
    assert not customization_marker.exists()
    assert str(repo / "src/pandas.py") not in completed.stdout
    assert str(fake_pandas / "__init__.py") not in completed.stdout
    assert "r6e1r-dependencies-" in completed.stdout
    assert completed.stdout.strip().startswith("/tmp/r6e1r-dependencies-")
    assert completed.stdout.strip().endswith("/pandas/__init__.py")
    assert not any(hostile_tmp.iterdir())


def test_verified_repository_rejects_drifted_dependency_version(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    fake_site = tmp_path / "site-packages"
    for name, version in (("numpy", "2.5.2"), ("pandas", "0.0.0")):
        dependency = fake_site / name
        dependency.mkdir(parents=True)
        (dependency / "__init__.py").write_text(
            f"__version__ = {version!r}\n"
        )
    probe = _activation_probe(script, repo, fake_site)
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "runtime dependency version or origin mismatch" in completed.stderr


def test_dependency_bytes_are_authenticated_before_import(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    fake_site = tmp_path / "site-packages"
    for name, version in (("numpy", "2.5.2"), ("pandas", "3.0.5")):
        dependency = fake_site / name
        dependency.mkdir(parents=True)
        (dependency / "__init__.py").write_text(
            f"__version__ = {version!r}\n"
        )
    contracts = _fake_dependency_contracts(fake_site)
    marker = tmp_path / "mutated-dependency-executed"
    (fake_site / "pandas/__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('BAD')\n"
        "__version__ = '3.0.5'\n"
    )
    package_init = package / "__init__.py"
    probe = (
        "import pathlib,runpy;"
        f"m=runpy.run_path({str(script)!r});"
        "sources={'src/banknifty_profiler/__init__.py':"
        f"pathlib.Path({str(package_init)!r}).read_bytes()}};"
        f"m['activate_verified_repository'](pathlib.Path({str(repo)!r}),"
        f"sources,(pathlib.Path({str(fake_site)!r}),),"
        f"dependency_contracts={contracts!r})"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "runtime dependency source identity mismatch" in completed.stderr
    assert not marker.exists()


def test_dependency_import_cannot_resolve_optional_module_from_repository(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    marker = tmp_path / "optional-module-imported"
    optional_name = "r6e1r_evil_optional_probe_9827"
    (repo / "src" / f"{optional_name}.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('BAD')\n"
    )
    fake_site = tmp_path / "site-packages"
    numpy = fake_site / "numpy"
    pandas = fake_site / "pandas"
    numpy.mkdir(parents=True)
    pandas.mkdir()
    (numpy / "__init__.py").write_text("__version__ = '2.5.2'\n")
    (pandas / "__init__.py").write_text(
        f"import {optional_name}\n__version__ = '3.0.5'\n"
    )
    probe = _activation_probe(script, repo, fake_site)
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not marker.exists()
    assert optional_name in completed.stderr


def test_lazy_dependency_import_cannot_use_repository_top_level_module(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    marker = tmp_path / "lazy-optional-imported"
    optional_name = "r6e1r_lazy_evil_optional_probe_7319"
    (repo / "src" / f"{optional_name}.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('BAD')\n"
    )
    fake_site = tmp_path / "site-packages"
    numpy = fake_site / "numpy"
    pandas = fake_site / "pandas"
    numpy.mkdir(parents=True)
    pandas.mkdir()
    (numpy / "__init__.py").write_text("__version__ = '2.5.2'\n")
    (pandas / "__init__.py").write_text(
        "import importlib\n__version__ = '3.0.5'\n"
        f"def lazy_probe():\n    importlib.import_module({optional_name!r})\n"
    )
    probe = _activation_probe(script, repo, fake_site) + (
        ";import pandas;pandas.lazy_probe()"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not marker.exists()
    assert optional_name in completed.stderr


def test_authenticated_import_uses_captured_bytes_after_source_replacement(
    tmp_path,
):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    package_init = package / "__init__.py"
    probe_module = package / "authenticated_probe.py"
    package_init.write_text("")
    probe_module.write_text("VALUE = 'AUTHENTICATED'\n")
    marker = tmp_path / "replacement-executed"
    fake_site = tmp_path / "site-packages"
    for name, version in (("numpy", "2.5.2"), ("pandas", "3.0.5")):
        dependency = fake_site / name
        dependency.mkdir(parents=True)
        (dependency / "__init__.py").write_text(
            f"__version__ = {version!r}\n"
        )
    replacement = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('BAD')\n"
        "VALUE = 'REPLACED'\n"
    )
    sources = {
        "src/banknifty_profiler/__init__.py": package_init.read_bytes(),
        "src/banknifty_profiler/authenticated_probe.py": (
            probe_module.read_bytes()
        ),
    }
    dependency_contracts = _fake_dependency_contracts(fake_site)
    probe = (
        "import pathlib,runpy;"
        f"m=runpy.run_path({str(script)!r});"
        f"sources={sources!r};"
        f"m['activate_verified_repository'](pathlib.Path({str(repo)!r}),"
        f"sources,(pathlib.Path({str(fake_site)!r}),),"
        f"dependency_contracts={dependency_contracts!r});"
        f"pathlib.Path({str(probe_module)!r}).write_text({replacement!r});"
        "import banknifty_profiler.authenticated_probe as p;print(p.VALUE)"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "AUTHENTICATED"
    assert not marker.exists()


def test_authenticated_import_refuses_unallowlisted_package_module(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    marker = tmp_path / "unallowlisted-executed"
    (package / "unallowlisted_probe.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('BAD')\n"
    )
    fake_site = tmp_path / "site-packages"
    for name, version in (("numpy", "2.5.2"), ("pandas", "3.0.5")):
        dependency = fake_site / name
        dependency.mkdir(parents=True)
        (dependency / "__init__.py").write_text(
            f"__version__ = {version!r}\n"
        )
    probe = _activation_probe(script, repo, fake_site) + (
        ";import banknifty_profiler.unallowlisted_probe"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "unauthenticated runtime module refused" in completed.stderr
    assert not marker.exists()


def test_dependency_cannot_preseed_authenticated_package_submodule(tmp_path):
    repo = tmp_path / "repo"
    script = repo / "scripts/run_r6e_shadow.py"
    script.parent.mkdir(parents=True)
    script.write_bytes(SCRIPT.read_bytes())
    package = repo / "src/banknifty_profiler"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    fake_site = tmp_path / "site-packages"
    numpy = fake_site / "numpy"
    pandas = fake_site / "pandas"
    numpy.mkdir(parents=True)
    pandas.mkdir()
    (numpy / "__init__.py").write_text("__version__ = '2.5.2'\n")
    (pandas / "__init__.py").write_text(
        "import sys, types\n"
        "sys.modules['banknifty_profiler.shadow.api'] = types.ModuleType("
        "'banknifty_profiler.shadow.api')\n"
        "__version__ = '3.0.5'\n"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c",
            _activation_probe(script, repo, fake_site),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "verified runtime package was preloaded" in completed.stderr


def test_checked_in_runtime_import_closure_loads_from_authenticated_bytes():
    repo = Path.cwd().resolve()
    script = repo / SCRIPT
    config = repo / "deploy/r6e1r/r6e1r-runtime-config.json.example"
    dependency_root = (
        repo / ".venv/lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    probe = (
        "import pathlib,runpy;"
        f"m=runpy.run_path({str(script)!r});"
        f"repo=pathlib.Path({str(repo)!r});"
        f"config=pathlib.Path({str(config)!r});"
        "_manifest,sources,_config=m["
        "'verify_engine_sources_before_import'](config,repo);"
        f"m['activate_verified_repository'](repo,sources,(pathlib.Path("
        f"{str(dependency_root)!r}),));"
        "from banknifty_profiler.shadow.api import create_server;"
        "from banknifty_profiler.shadow.contracts import validate_shadow_contract;"
        "from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor;"
        "from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator;"
        "print('AUTHENTICATED_IMPORT_CLOSURE_OK')"
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", "-B", "-X",
            "pycache_prefix=/dev/null", "-c", probe,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "AUTHENTICATED_IMPORT_CLOSURE_OK"
    assert completed.stderr == ""


class _RecoveredOrchestrator:
    def __init__(self, pending):
        self.pending = set(pending)
        self.finalized = []

    def pending_session_dates(self):
        return tuple(sorted(self.pending))

    def finalize_session(self, session):
        self.finalized.append(session)
        self.pending.discard(session)


class _IntegrityVerifier:
    def __init__(self):
        self.sessions = []

    def verify_committed_sources(self, sessions):
        self.sessions.extend(sessions)


def test_first_next_day_poll_finalizes_recovered_session_in_order():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    ingestor = _IntegrityVerifier()
    orchestrator = _RecoveredOrchestrator(["2026-08-26"])

    newest, finalized = finalize(
        ingestor, orchestrator, ["2026-08-27"],
    )

    assert newest == "2026-08-27"
    assert finalized == ("2026-08-26",)
    assert ingestor.sessions == ["2026-08-26"]
    assert orchestrator.finalized == ["2026-08-26"]


def test_multi_date_catchup_finalizes_every_prior_session_chronologically():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    ingestor = _IntegrityVerifier()
    orchestrator = _RecoveredOrchestrator(
        ["2026-08-25", "2026-08-26"],
    )

    newest, finalized = finalize(
        ingestor, orchestrator, ["2026-08-26", "2026-08-27"],
    )

    assert newest == "2026-08-27"
    assert finalized == ("2026-08-25", "2026-08-26")
    assert ingestor.sessions == ["2026-08-25", "2026-08-26"]
    assert orchestrator.finalized == ["2026-08-25", "2026-08-26"]


def test_integrity_failure_prevents_session_finalization():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    orchestrator = _RecoveredOrchestrator(["2026-08-26"])

    class RefusingIntegrity:
        def verify_committed_sources(self, _sessions):
            raise ValueError("synthetic integrity refusal")

    try:
        finalize(RefusingIntegrity(), orchestrator, ["2026-08-27"])
    except ValueError as error:
        assert str(error) == "synthetic integrity refusal"
    else:
        raise AssertionError("integrity refusal did not propagate")
    assert orchestrator.finalized == []
