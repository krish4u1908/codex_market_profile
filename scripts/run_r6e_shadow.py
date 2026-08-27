#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import signal
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
LOG_COMPONENT = "r6e1r-shadow"
ENGINE_MANIFEST = "manifests/r6e1r_engine_source_manifest.json"
ACTIVATION_DAY = "2026-08-26"
ACTIVATION_SCOPE = (
    "R6E1R isolated live shadow; 2026-08-25 and 2026-08-26 remain "
    "operational diagnostics and are not prospective evidence"
)
RUNTIME_DEPENDENCY_VERSIONS = {
    "numpy": "2.5.2",
    "pandas": "3.0.5",
}
# Canonical wheel RECORD subsets for every third-party module that pandas and
# NumPy execute in production.  Installer-local files and console entry points
# are deliberately outside the runtime snapshot.  These aggregate identities
# authenticate the declared wheel paths before any dependency code executes;
# each declared file is then content-verified and copied from the verified
# bytes into a private process-lifetime snapshot.
RUNTIME_DEPENDENCY_CONTRACTS = {
    "numpy-2.5.2.dist-info/RECORD": {
        "prefixes": (
            "numpy/", "numpy.libs/", "numpy-2.5.2.dist-info/METADATA",
            "numpy-2.5.2.dist-info/WHEEL",
        ),
        "inventory_sha256": (
            "752e63b88266c8d1a4218b383b554109d80360dd738671b97e1d6f48f57dbcad"
        ),
    },
    "pandas-3.0.5.dist-info/RECORD": {
        "prefixes": (
            "pandas/", "pandas-3.0.5.dist-info/METADATA",
            "pandas-3.0.5.dist-info/WHEEL",
        ),
        "inventory_sha256": (
            "977bf54c0a5b4e91706f82ac1a83a3a1715712e840a9e843ba4c4bed93023054"
        ),
    },
    "python_dateutil-2.9.0.post0.dist-info/RECORD": {
        "prefixes": (
            "dateutil/", "python_dateutil-2.9.0.post0.dist-info/METADATA",
            "python_dateutil-2.9.0.post0.dist-info/WHEEL",
        ),
        "inventory_sha256": (
            "5af36f41e0656fc8a43d4bc64d8496935cef2c3e90e458a2fa3ca89f0873437d"
        ),
    },
    "six-1.17.0.dist-info/RECORD": {
        "prefixes": (
            "six.py", "six-1.17.0.dist-info/METADATA",
            "six-1.17.0.dist-info/WHEEL",
        ),
        "inventory_sha256": (
            "780e875381979ca596ceaf3fa99feb356a7f7a4e762ffc6c088f883cdb6d112b"
        ),
    },
}
_RUNTIME_DEPENDENCY_SNAPSHOT: tempfile.TemporaryDirectory[str] | None = None


def _is_safe_runtime_input(path: Path) -> bool:
    """Accept a regular path or an explicitly inherited `/proc/self/fd/N`."""
    if not path.is_file():
        return False
    if not path.is_symlink():
        return True
    parts = path.parts
    return (
        len(parts) == 5
        and parts[:4] == ("/", "proc", "self", "fd")
        and parts[4].isdigit()
    )


def _safe_log_token(value: object, fallback: str) -> str:
    token = str(value)
    return token if token and token.replace("_", "").isalnum() else fallback


def emit_runtime_log(
    event: str,
    status: str,
    *,
    error: BaseException | None = None,
) -> None:
    """Emit one bounded structured record without raw or exception detail."""
    record = {
        "classification": CLASSIFICATION,
        "component": LOG_COMPONENT,
        "event": _safe_log_token(event, "RUNTIME_EVENT"),
        "status": _safe_log_token(status, "UNKNOWN"),
    }
    if error is not None:
        record["error_type"] = _safe_log_token(
            type(error).__name__, "RUNTIME_ERROR"
        )
    print(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        flush=True,
    )


def verify_engine_sources_before_import(
    config_path: Path,
    repo: Path | None = None,
    *,
    authenticated_config_payload: bytes | None = None,
) -> tuple[dict[str, object], dict[str, bytes], bytes]:
    """Authenticate every repository runtime byte before package imports.

    This bootstrap deliberately uses only the standard library.  The runtime
    configuration supplies the independently staged manifest digest; the
    regular in-process contract verifier repeats the check after imports.
    """
    root = (repo or Path(__file__).resolve().parents[1]).resolve()
    try:
        if authenticated_config_payload is None:
            if not _is_safe_runtime_input(config_path):
                raise ValueError(
                    "pre-import runtime configuration is unavailable"
                )
            config_payload = config_path.read_bytes()
        else:
            if not isinstance(authenticated_config_payload, bytes):
                raise TypeError("authenticated configuration must be bytes")
            config_payload = authenticated_config_payload
        config = json.loads(config_payload)
        expected = config["engine_source_manifest_sha256"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("pre-import runtime configuration is invalid") from error
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise ValueError("pre-import engine manifest identity is invalid")

    manifest_path = root / ENGINE_MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("pre-import engine manifest is unavailable")
    payload = manifest_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("pre-import engine manifest identity mismatch")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError("pre-import engine manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise ValueError("pre-import engine manifest is invalid")
    allowlist = manifest.get("allowlist")
    rows = manifest.get("files")
    if (
        manifest.get("schema") != "R6E1R_ENGINE_SOURCE_MANIFEST_V1"
        or manifest.get("classification") != CLASSIFICATION
        or not isinstance(allowlist, list)
        or not allowlist
        or allowlist != sorted(set(allowlist))
        or not all(isinstance(item, str) for item in allowlist)
        or not isinstance(rows, list)
        or manifest.get("file_count") != len(allowlist)
        or len(rows) != len(allowlist)
    ):
        raise ValueError("pre-import engine manifest contract mismatch")

    inventory: list[dict[str, object]] = []
    authenticated_sources: dict[str, bytes] = {}
    for relative, expected_row in zip(allowlist, rows, strict=True):
        item = Path(relative)
        if item.is_absolute() or ".." in item.parts:
            raise ValueError("pre-import engine source path is unsafe")
        unresolved = root / item
        cursor = root
        for part in item.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError(
                    "pre-import engine source symlink is prohibited"
                )
        source = unresolved.resolve()
        if (
            root not in source.parents
            or not source.is_file()
            or source.is_symlink()
            or not isinstance(expected_row, dict)
        ):
            raise ValueError("pre-import engine source is unavailable")
        source_payload = source.read_bytes()
        actual = {
            "path": relative,
            "sha256": hashlib.sha256(source_payload).hexdigest(),
            "size": len(source_payload),
        }
        if expected_row != actual:
            raise ValueError("pre-import engine source identity mismatch")
        inventory.append(actual)
        authenticated_sources[relative] = source_payload
    canonical = (
        json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if manifest.get("engine_hash") != hashlib.sha256(canonical).hexdigest():
        raise ValueError("pre-import engine aggregate identity mismatch")
    return manifest, authenticated_sources, config_payload


def capture_activation_before_import(
    path: Path,
    *,
    authenticated_payload: bytes | None = None,
) -> dict[str, str]:
    """Capture and validate the immutable prospective-activation boundary."""
    try:
        if authenticated_payload is None:
            if not _is_safe_runtime_input(path):
                raise ValueError("activation contract is unavailable")
            payload = path.read_bytes()
        else:
            if not isinstance(authenticated_payload, bytes):
                raise TypeError("authenticated activation must be bytes")
            payload = authenticated_payload
        value = json.loads(payload)
    except (OSError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("activation contract is invalid") from error
    expected = {
        "activation_day": ACTIVATION_DAY,
        "classification": CLASSIFICATION,
        "scope": ACTIVATION_SCOPE,
    }
    if value != expected:
        raise ValueError("activation contract mismatch")
    return expected


class _AuthenticatedSourceImporter(
    importlib.abc.MetaPathFinder,
    importlib.abc.Loader,
):
    """Import only the exact package bytes captured during authentication."""

    def __init__(
        self,
        repository: Path,
        authenticated_sources: dict[str, bytes],
    ) -> None:
        self.repository = repository.resolve()
        self.modules: dict[str, tuple[str, bytes, bool]] = {}
        prefix = Path("src/banknifty_profiler")
        for relative, payload in authenticated_sources.items():
            path = Path(relative)
            try:
                package_relative = path.relative_to(prefix)
            except ValueError:
                continue
            if path.suffix != ".py":
                continue
            if package_relative.name == "__init__.py":
                parts = package_relative.parent.parts
                is_package = True
            else:
                parts = package_relative.with_suffix("").parts
                is_package = False
            fullname = ".".join(("banknifty_profiler", *parts))
            if fullname in self.modules:
                raise ValueError("authenticated package module is duplicated")
            self.modules[fullname] = (relative, payload, is_package)
        if "banknifty_profiler" not in self.modules:
            raise ValueError("authenticated runtime package is unavailable")

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del path, target
        if not (
            fullname == "banknifty_profiler"
            or fullname.startswith("banknifty_profiler.")
        ):
            return None
        entry = self.modules.get(fullname)
        if entry is None:
            raise ModuleNotFoundError(
                f"unauthenticated runtime module refused: {fullname!r}"
            )
        relative, _payload, is_package = entry
        origin = str((self.repository / relative).resolve())
        spec = importlib.machinery.ModuleSpec(
            fullname,
            self,
            origin=origin,
            is_package=is_package,
        )
        # Package code may derive non-Python resource locations from
        # ``__file__``/``__path__``. Those resource bytes are independently
        # authenticated before use; Python source imports never consult this
        # path because this finder fails closed for the entire namespace.
        spec.has_location = True
        if is_package:
            spec.submodule_search_locations = [str(Path(origin).parent)]
        return spec

    def create_module(
        self, spec: importlib.machinery.ModuleSpec,
    ) -> object | None:
        del spec
        return None

    def exec_module(self, module: object) -> None:
        fullname = str(getattr(module, "__name__", ""))
        entry = self.modules.get(fullname)
        if entry is None:
            raise ImportError("authenticated runtime module disappeared")
        relative, payload, _is_package = entry
        origin = str((self.repository / relative).resolve())
        code = compile(payload, origin, "exec", dont_inherit=True)
        exec(code, getattr(module, "__dict__"))


def _dependency_roots(executable: Path | None = None) -> tuple[Path, ...]:
    """Locate ordinary environment site-packages without executing `.pth`."""
    environment = (executable or Path(sys.executable)).parent.parent
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    roots: list[Path] = []
    for candidate in (
        environment / "lib" / version / "site-packages",
        environment / "lib64" / version / "site-packages",
    ):
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    if not roots:
        raise ValueError("runtime dependency root is unavailable")
    return tuple(roots)


def _dependency_record_rows(
    root: Path,
    record_relative: str,
    contract: dict[str, object],
) -> list[tuple[str, str, int]]:
    """Authenticate one canonical wheel RECORD subset without importing it."""
    record_item = Path(record_relative)
    prefixes = contract.get("prefixes")
    expected = contract.get("inventory_sha256")
    if (
        record_item.is_absolute()
        or ".." in record_item.parts
        or not isinstance(prefixes, (tuple, list))
        or not prefixes
        or not all(isinstance(value, str) and value for value in prefixes)
        or not isinstance(expected, str)
        or len(expected) != 64
        or any(value not in "0123456789abcdef" for value in expected)
    ):
        raise ValueError("runtime dependency contract is invalid")
    record_path = root / record_item
    cursor = root
    for part in record_item.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("runtime dependency RECORD symlink is prohibited")
    try:
        record_payload = record_path.read_bytes()
        decoded = record_payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("runtime dependency RECORD is unavailable") from error

    rows: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    try:
        declarations = csv.reader(decoded.splitlines())
        for declaration in declarations:
            if len(declaration) != 3:
                raise ValueError("runtime dependency RECORD row is invalid")
            relative, declared_hash, declared_size = declaration
            selected = any(
                relative == prefix
                or (prefix.endswith("/") and relative.startswith(prefix))
                for prefix in prefixes
            )
            if not selected:
                continue
            item = Path(relative)
            # Some installers append generated bytecode rows with no hash or
            # size. Production runs with ``-B`` and executes only the recorded
            # source/extension bytes copied below, so generated bytecode is
            # deliberately outside the authenticated wheel subset.
            if item.suffix == ".pyc" or "__pycache__" in item.parts:
                continue
            if (
                item.is_absolute()
                or ".." in item.parts
                or not declared_hash.startswith("sha256=")
                or not declared_size.isdigit()
                or relative in seen
            ):
                raise ValueError("runtime dependency RECORD row is unsafe")
            digest = declared_hash.removeprefix("sha256=")
            if len(digest) != 43 or any(
                value not in (
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    "abcdefghijklmnopqrstuvwxyz"
                    "0123456789-_"
                )
                for value in digest
            ):
                raise ValueError("runtime dependency RECORD digest is invalid")
            try:
                decoded_digest = base64.b64decode(
                    digest + "=" * (-len(digest) % 4),
                    altchars=b"-_",
                    validate=True,
                )
            except (ValueError, TypeError) as error:
                raise ValueError(
                    "runtime dependency RECORD digest is invalid"
                ) from error
            if len(decoded_digest) != hashlib.sha256().digest_size:
                raise ValueError("runtime dependency RECORD digest is invalid")
            size = int(declared_size)
            if str(size) != declared_size:
                raise ValueError("runtime dependency RECORD size is invalid")
            seen.add(relative)
            rows.append((relative, declared_hash, size))
    except csv.Error as error:
        raise ValueError("runtime dependency RECORD is invalid") from error
    if not rows:
        raise ValueError("runtime dependency RECORD subset is empty")
    canonical = (
        json.dumps(sorted(rows), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != expected:
        raise ValueError("runtime dependency inventory identity mismatch")
    return rows


def _capture_runtime_dependencies(
    roots: tuple[Path, ...],
    contracts: dict[str, dict[str, object]],
) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Copy exact authenticated wheel bytes into a private import snapshot."""
    if len(roots) != 1:
        raise ValueError("runtime dependency root must be unique")
    root = roots[0].resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("runtime dependency root is unsafe")
    if not isinstance(contracts, dict) or not contracts:
        raise ValueError("runtime dependency contracts are unavailable")

    declared: dict[str, tuple[str, int]] = {}
    for record_relative in sorted(contracts):
        contract = contracts[record_relative]
        if not isinstance(record_relative, str) or not isinstance(contract, dict):
            raise ValueError("runtime dependency contract is invalid")
        for relative, declared_hash, size in _dependency_record_rows(
            root, record_relative, contract,
        ):
            prior = declared.setdefault(relative, (declared_hash, size))
            if prior != (declared_hash, size):
                raise ValueError("runtime dependency declaration conflicts")

    # Production's systemd PrivateTmp makes explicit /tmp private to this unit.
    # Never honor TMPDIR/TMP/TEMP inherited from the manager: a shared chosen
    # directory would let another same-UID process replace a lazy-import target.
    temporary = tempfile.TemporaryDirectory(
        prefix="r6e1r-dependencies-", dir="/tmp",
    )
    snapshot = Path(temporary.name).resolve()
    snapshot.chmod(0o700)
    if snapshot.parent != Path("/tmp").resolve() or (
        snapshot.stat().st_mode & 0o777
    ) != 0o700:
        temporary.cleanup()
        raise ValueError("runtime dependency snapshot root is unsafe")
    try:
        for relative in sorted(declared):
            declared_hash, declared_size = declared[relative]
            item = Path(relative)
            source = root / item
            cursor = root
            for part in item.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise ValueError(
                        "runtime dependency source symlink is prohibited"
                    )
            if not source.is_file() or source.is_symlink():
                raise ValueError("runtime dependency source is unavailable")
            source_payload = source.read_bytes()
            actual_digest = base64.urlsafe_b64encode(
                hashlib.sha256(source_payload).digest()
            ).rstrip(b"=").decode("ascii")
            if (
                len(source_payload) != declared_size
                or declared_hash != f"sha256={actual_digest}"
            ):
                raise ValueError("runtime dependency source identity mismatch")
            target = snapshot / item
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_payload)
            if target.read_bytes() != source_payload:
                raise ValueError("runtime dependency snapshot write mismatch")
    except Exception:
        temporary.cleanup()
        raise
    return temporary, snapshot


def activate_verified_repository(
    repository: Path,
    authenticated_sources: dict[str, bytes],
    dependency_roots: tuple[Path, ...] | None = None,
    *,
    dependency_contracts: dict[str, dict[str, object]] | None = None,
) -> None:
    """Expose verified package bytes without shadowing trusted dependencies."""
    source_root = (repository / "src").resolve()
    source_dependency_roots = tuple(
        path.resolve() for path in (
            dependency_roots if dependency_roots is not None
            else _dependency_roots()
        )
    )
    if not source_dependency_roots or any(
        not root.is_dir() or source_root == root or source_root in root.parents
        for root in source_dependency_roots
    ):
        raise ValueError("runtime dependency root is unsafe")
    if any(
        name in sys.modules
        for name in ("numpy", "pandas", "dateutil", "six")
    ):
        raise ValueError("runtime dependency was preloaded")
    contracts = (
        dependency_contracts
        if dependency_contracts is not None
        else RUNTIME_DEPENDENCY_CONTRACTS
    )
    global _RUNTIME_DEPENDENCY_SNAPSHOT
    temporary, snapshot_root = _capture_runtime_dependencies(
        source_dependency_roots, contracts,
    )
    _RUNTIME_DEPENDENCY_SNAPSHOT = temporary
    roots = (snapshot_root,)
    # Never call site.main(): it executes `.pth`, sitecustomize and
    # usercustomize. Production ``-I -S`` starts without those effects. Add
    # only the ordinary environment package directories, followed by the
    # authenticated repository package root.
    excluded_roots = {source_root, *source_dependency_roots, *roots}
    sys.path[:] = [
        value for value in sys.path
        if Path(value or ".").resolve() not in excluded_roots
    ]
    sys.path.extend(map(str, roots))
    # Resolve and import numerical dependencies only from the private snapshot
    # before repository sources are visible. An unallowlisted top-level module
    # in repo/src or the original environment cannot satisfy an optional or
    # missing transitive dependency import.
    for dependency, expected_version in RUNTIME_DEPENDENCY_VERSIONS.items():
        dependency_spec = importlib.util.find_spec(dependency)
        if dependency_spec is None or not dependency_spec.origin:
            raise ValueError("verified runtime dependency is unavailable")
        dependency_path = Path(dependency_spec.origin).resolve()
        if not any(
            dependency_path == root or root in dependency_path.parents
            for root in roots
        ):
            raise ValueError("runtime dependency origin is untrusted")
        module = __import__(dependency)
        if (
            getattr(module, "__version__", None) != expected_version
            or not getattr(module, "__file__", None)
            or Path(module.__file__).resolve() != dependency_path
        ):
            raise ValueError("runtime dependency version or origin mismatch")
    # Install a namespace-wide fail-closed importer backed by the bytes held
    # in memory since manifest verification. No later path lookup can execute
    # a replaced source file or an unallowlisted sibling module.
    if any(
        name == "banknifty_profiler"
        or name.startswith("banknifty_profiler.")
        for name in sys.modules
    ):
        raise ValueError("verified runtime package was preloaded")
    importer = _AuthenticatedSourceImporter(repository, authenticated_sources)
    sys.meta_path.insert(0, importer)
    try:
        package = __import__("banknifty_profiler")
    except Exception:
        if importer in sys.meta_path:
            sys.meta_path.remove(importer)
        sys.modules.pop("banknifty_profiler", None)
        raise
    if (
        not getattr(package, "__file__", None)
        or Path(package.__file__).resolve()
        != source_root / "banknifty_profiler/__init__.py"
        or source_root in {Path(value or ".").resolve() for value in sys.path}
    ):
        if importer in sys.meta_path:
            sys.meta_path.remove(importer)
        sys.modules.pop("banknifty_profiler", None)
        raise ValueError("verified runtime package origin mismatch")


def finalize_prior_sessions(
    ingestor: IncrementalJSONLIngestor,
    orchestrator: LiveAnalyticalOrchestrator,
    observed_sessions: list[str],
) -> tuple[str | None, tuple[str, ...]]:
    """Seal every recovered/live session strictly before the newest one."""
    pending = set(orchestrator.pending_session_dates()) | set(observed_sessions)
    if not pending:
        return None, ()
    newest = max(pending)
    finalized = []
    for session_date in sorted(session for session in pending if session < newest):
        # Full-prefix verification is a session boundary, not poll-time work.
        # No arbitrary old-block rewrite can be promoted into sealed replay.
        ingestor.verify_committed_sources([session_date])
        orchestrator.finalize_session(session_date)
        finalized.append(session_date)
    return newest, tuple(finalized)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authenticated-config-input", type=Path)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--activation", type=Path, required=True)
    parser.add_argument("--authenticated-activation-input", type=Path)
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()

    # No banknifty_profiler package code may execute before this succeeds.
    repository = (
        args.repository_root.resolve()
        if args.repository_root is not None
        else Path(__file__).resolve().parents[1]
    )
    bootstrap_config_payload = globals().get(
        "_R6E1R_AUTHENTICATED_CONFIG_PAYLOAD"
    )
    bootstrap_activation_payload = globals().get(
        "_R6E1R_AUTHENTICATED_ACTIVATION_PAYLOAD"
    )
    _, authenticated_sources, config_payload = (
        verify_engine_sources_before_import(
            args.authenticated_config_input or args.config,
            repository,
            authenticated_config_payload=bootstrap_config_payload,
        )
    )
    activation = capture_activation_before_import(
        args.authenticated_activation_input or args.activation,
        authenticated_payload=bootstrap_activation_payload,
    )
    # Production starts with ``-I -S``: no repository PYTHONPATH,
    # sitecustomize, usercustomize, or script-directory shadow module can run
    # before the verifier. Restore only the venv dependencies, then expose the
    # authenticated package directory without adding repo/src globally.
    activate_verified_repository(repository, authenticated_sources)
    from banknifty_profiler.shadow.api import create_server
    from banknifty_profiler.shadow.contracts import validate_shadow_contract
    from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
    from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
    from banknifty_profiler.shadow.state import ShadowState

    contract = validate_shadow_contract(
        args.data_root,
        args.state_root,
        args.config,
        args.bind,
        args.mode,
        authenticated_config_payload=config_payload,
    )
    contract["raw_run_id"] = "R6E-" + uuid.uuid4().hex.upper()
    contract["minimum_session_date"] = activation["activation_day"]
    ingestor = IncrementalJSONLIngestor(contract)
    orchestrator = LiveAnalyticalOrchestrator(
        contract, ledgers=ingestor.ledgers
    )
    ingestor.register_callback(orchestrator)
    state = ShadowState(ingestor, activation, orchestrator)
    server = create_server(state, args.bind, args.port)
    stop = threading.Event()
    last_refresh = 0.0
    refresh_seconds = float(contract["config"]["analytical_refresh_seconds"])
    active_error_type = ""

    def halt(*_: object) -> None:
        stop.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    emit_runtime_log("SERVICE_STARTING", "STARTING")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    emit_runtime_log("SERVICE_RUNNING", "RUNNING")
    try:
        while not stop.is_set():
            try:
                observations = ingestor.poll()
                observed_sessions = sorted(
                    {row.session_date for row in observations}
                )
                _, finalized_sessions = finalize_prior_sessions(
                    ingestor, orchestrator, observed_sessions,
                )
                for _session_date in finalized_sessions:
                    emit_runtime_log("SESSION_FINALIZED", "SEALED")

                # Analytical rebuilds are bounded by the configured refresh
                # interval; callback staging is already durable and API reads
                # remain read-only.
                current = time.monotonic()
                if current - last_refresh >= refresh_seconds:
                    orchestrator.flush()
                    last_refresh = current
                orchestrator.refresh_staleness()
                state.last_error = ""
                if active_error_type:
                    emit_runtime_log("INGESTION_RECOVERED", "RUNNING")
                active_error_type = ""
            except Exception as error:
                error_type = _safe_log_token(
                    type(error).__name__, "RUNTIME_ERROR"
                )
                state.last_error = f"INGESTION_ERROR:{error_type}"
                if error_type != active_error_type:
                    emit_runtime_log(
                        "INGESTION_CYCLE_ERROR", "DEGRADED", error=error
                    )
                active_error_type = error_type
            stop.wait(float(contract["config"]["poll_interval_seconds"]))
    finally:
        emit_runtime_log("SERVICE_STOPPING", "STOPPING")
        server.server_close()
        try:
            orchestrator.flush()
        finally:
            ingestor.close()
        emit_runtime_log("SERVICE_STOPPED", "STOPPED")
    return 0


def entrypoint() -> int:
    try:
        return main()
    except Exception as error:
        # Never let an unhandled traceback place paths, records, configuration,
        # or exception text into the service journal.
        emit_runtime_log("SERVICE_FATAL", "TERMINATED", error=error)
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
