from __future__ import annotations

from collections.abc import Iterable
import hashlib
import json
from pathlib import Path

from banknifty_profiler.runtime.configuration import (
    canonical_configuration_sha256,
    validate_canonical_runtime_config,
)
from banknifty_profiler.shadow.symbols import CANONICAL_INDEX_SYMBOL, SymbolRegistry


CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
ENGINE_SOURCE_MANIFEST_PATH = "manifests/r6e1r_engine_source_manifest.json"
ENGINE_SOURCE_MANIFEST_SHA256_PATH = (
    "manifests/r6e1r_engine_source_manifest.sha256"
)

# Runtime source identity is intentionally explicit. The verified R6D source
# manifest remains immutable historical evidence and cannot identify R6E code.
# Relative paths also make every startup source open reviewable/allowlisted.
ENGINE_SOURCE_ALLOWLIST = (
    "scripts/run_r6e_shadow.py",
    "src/banknifty_profiler/__init__.py",
    "src/banknifty_profiler/context/__init__.py",
    "src/banknifty_profiler/context/availability.py",
    "src/banknifty_profiler/cross_layer/__init__.py",
    "src/banknifty_profiler/cross_layer/state.py",
    "src/banknifty_profiler/divergence/__init__.py",
    "src/banknifty_profiler/divergence/dependency.py",
    "src/banknifty_profiler/divergence/detector.py",
    "src/banknifty_profiler/gui/__init__.py",
    "src/banknifty_profiler/gui/adapter.py",
    "src/banknifty_profiler/gui/static/live.js",
    "src/banknifty_profiler/gui/static/live_page.template",
    "src/banknifty_profiler/gui/static/style.css",
    "src/banknifty_profiler/inventory/__init__.py",
    "src/banknifty_profiler/inventory/engine.py",
    "src/banknifty_profiler/lifecycle/__init__.py",
    "src/banknifty_profiler/lifecycle/engine.py",
    "src/banknifty_profiler/lifecycle/raw_engine.py",
    "src/banknifty_profiler/participation/__init__.py",
    "src/banknifty_profiler/participation/raw_engine.py",
    "src/banknifty_profiler/participation/views.py",
    "src/banknifty_profiler/raw_io/__init__.py",
    "src/banknifty_profiler/raw_io/reader.py",
    "src/banknifty_profiler/runtime/__init__.py",
    "src/banknifty_profiler/runtime/configuration.py",
    "src/banknifty_profiler/runtime/timestamps.py",
    "src/banknifty_profiler/shadow/__init__.py",
    "src/banknifty_profiler/shadow/api.py",
    "src/banknifty_profiler/shadow/contracts.py",
    "src/banknifty_profiler/shadow/ingest.py",
    "src/banknifty_profiler/shadow/ledger.py",
    "src/banknifty_profiler/shadow/observation.py",
    "src/banknifty_profiler/shadow/orchestrator.py",
    "src/banknifty_profiler/shadow/state.py",
    "src/banknifty_profiler/shadow/symbols.py",
    "deploy/r6e1r/health_readiness_check.py",
    "deploy/r6e1r/read_only_gateway.py",
)


def _source_path(repo: Path, relative: str) -> Path:
    item = Path(relative)
    if item.is_absolute() or ".." in item.parts:
        raise ValueError(f"unsafe engine source allowlist path: {relative!r}")
    resolved_repo = repo.resolve()
    cursor = resolved_repo
    for part in item.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(
                f"allowlisted engine source symlink refused: {relative}"
            )
    path = (resolved_repo / item).resolve()
    if resolved_repo not in path.parents or not path.is_file():
        raise ValueError(f"allowlisted engine source missing: {relative}")
    return path


def engine_source_inventory(
    repo: Path,
    allowlist: Iterable[str] = ENGINE_SOURCE_ALLOWLIST,
) -> list[dict[str, object]]:
    """Hash only explicitly allowlisted current analytical runtime sources."""
    rows = []
    for relative in sorted(set(map(str, allowlist))):
        path = _source_path(repo, relative)
        payload = path.read_bytes()
        rows.append({
            "path": relative,
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    if not rows:
        raise ValueError("engine source allowlist must not be empty")
    return rows


def engine_hash(
    repo: Path,
    allowlist: Iterable[str] = ENGINE_SOURCE_ALLOWLIST,
) -> str:
    inventory = engine_source_inventory(repo, allowlist)
    canonical = (
        json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def verify_engine_source_manifest(
    repo: Path,
    manifest_path: str,
    expected_manifest_sha256: str,
    allowlist: Iterable[str] = ENGINE_SOURCE_ALLOWLIST,
) -> dict[str, object]:
    """Compare current allowlisted runtime bytes with an expected manifest.

    The expected manifest digest is supplied independently (the deployed
    configuration uses the checked-in ``.sha256`` companion), so successfully
    hashing whatever happens to be present cannot self-assert verification.
    """
    expected = str(expected_manifest_sha256).strip().lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError("engine source manifest SHA-256 must be 64 lowercase hex characters")
    path = _source_path(repo, manifest_path)
    payload = path.read_bytes()
    actual_manifest_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_manifest_sha256 != expected:
        raise ValueError("engine source manifest identity mismatch")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"engine source manifest is not valid JSON: {error}") from error
    current = engine_source_inventory(repo, allowlist)
    expected_paths = sorted(set(map(str, allowlist)))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "R6E1R_ENGINE_SOURCE_MANIFEST_V1"
        or manifest.get("classification") != CLASSIFICATION
        or manifest.get("allowlist") != expected_paths
        or manifest.get("file_count") != len(current)
        or manifest.get("files") != current
        or manifest.get("engine_hash") != engine_hash(repo, allowlist)
    ):
        raise ValueError("current engine sources do not match expected manifest")
    opened = set(expected_paths) | {str(manifest_path)}
    allowed = set(expected_paths) | {str(manifest_path)}
    return {
        "verified": actual_manifest_sha256 == expected,
        "manifest_path": str(manifest_path),
        "manifest_sha256": actual_manifest_sha256,
        "engine_hash": str(manifest["engine_hash"]),
        "file_count": len(current),
        "runtime_open_audit": {
            "observed_open_count": len(opened),
            "allowlisted_open_count": len(opened & allowed),
            "prohibited_open_count": len(opened - allowed),
        },
    }


def checked_in_engine_source_manifest_sha256(repo: Path) -> str:
    """Read the independent checked-in expected digest for default configs."""
    path = _source_path(repo, ENGINE_SOURCE_MANIFEST_SHA256_PATH)
    value = path.read_text().strip().split()[0]
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("checked-in engine source manifest digest is invalid")
    return value


def validate_shadow_contract(
    data_root: Path,
    state_root: Path,
    config_path: Path,
    bind: str,
    mode: str,
    *,
    authenticated_config_payload: bytes | None = None,
) -> dict:
    data = data_root.resolve()
    state = state_root.resolve()
    config_file = config_path.resolve()
    if mode != "shadow":
        raise ValueError("mode must be exactly shadow")
    if bind != "127.0.0.1":
        raise ValueError("shadow API must bind exactly 127.0.0.1")
    if not data.is_absolute() or not state.is_absolute() or not config_file.is_absolute():
        raise ValueError("all runtime paths must be absolute")
    if not data.is_dir():
        raise ValueError(f"raw data root missing: {data}")
    if "research" in data.parts:
        raise ValueError("research-derived analytical input is prohibited")
    if not (data / "raw").is_dir() or not (data / "oi").is_dir():
        raise ValueError("data root must contain physical raw and oi directories")
    repo = Path(__file__).resolve().parents[3]
    if state == data or data in state.parents:
        raise ValueError("state root must be outside read-only collector root")
    if state == repo or repo in state.parents:
        raise ValueError("state root must be outside source tree")
    if not config_file.is_file():
        raise ValueError("configuration missing")
    if authenticated_config_payload is None:
        raw_config = json.loads(config_file.read_text())
    else:
        try:
            raw_config = json.loads(authenticated_config_payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError("authenticated runtime configuration is invalid") from error
        if not isinstance(raw_config, dict):
            raise ValueError("authenticated runtime configuration is invalid")
    raw_config.setdefault("index_symbol", CANONICAL_INDEX_SYMBOL)
    raw_config.setdefault(
        "futures_selection_mode", "SESSION_NEAREST_UNEXPIRED_HIGHEST_OI"
    )
    raw_config.setdefault("selected_futures_by_session", {})
    raw_config.setdefault("analytical_refresh_seconds", 30.0)
    raw_config.setdefault("max_live_sessions", 32)
    raw_config.setdefault("engine_source_manifest_path", ENGINE_SOURCE_MANIFEST_PATH)
    if "engine_source_manifest_sha256" not in raw_config:
        raw_config["engine_source_manifest_sha256"] = (
            checked_in_engine_source_manifest_sha256(repo)
        )
    config = validate_canonical_runtime_config(raw_config)
    if config.get("index_symbol") != CANONICAL_INDEX_SYMBOL:
        raise ValueError(f"index_symbol must be exactly {CANONICAL_INDEX_SYMBOL}")
    if (
        config.get("futures_selection_mode")
        != "SESSION_NEAREST_UNEXPIRED_HIGHEST_OI"
    ):
        raise ValueError("invalid futures_selection_mode")
    if not isinstance(config.get("selected_futures_by_session"), dict):
        raise ValueError("selected_futures_by_session must be an object")
    SymbolRegistry(selected_by_session=config["selected_futures_by_session"])
    if config.get("allowed_bind") != "127.0.0.1":
        raise ValueError("configuration allowed_bind must be exactly 127.0.0.1")
    if config.get("analytical_threshold_overrides") is not None:
        raise ValueError("runtime analytical threshold overrides are prohibited")
    for key, value in config.get("freshness_seconds", {}).items():
        if type(value) not in (int, float) or value <= 0:
            raise ValueError(f"invalid freshness threshold: {key}")
    refresh = config.get("analytical_refresh_seconds")
    if type(refresh) not in (int, float) or not 1 <= refresh <= 300:
        raise ValueError("analytical_refresh_seconds must be between 1 and 300")
    max_sessions = config.get("max_live_sessions")
    if type(max_sessions) is not int or not 6 <= max_sessions <= 32:
        raise ValueError("max_live_sessions must be an integer between 6 and 32")

    manifest_path = config.get("engine_source_manifest_path")
    if manifest_path != ENGINE_SOURCE_MANIFEST_PATH:
        raise ValueError(
            f"engine_source_manifest_path must be exactly {ENGINE_SOURCE_MANIFEST_PATH}"
        )
    verification = verify_engine_source_manifest(
        repo,
        str(manifest_path),
        str(config.get("engine_source_manifest_sha256", "")),
    )
    source_inventory = engine_source_inventory(repo)
    return {
        "data_root": data,
        "state_root": state,
        "config_path": config_file,
        "config": config,
        "configuration_hash": canonical_configuration_sha256(config),
        "engine_hash": verification["engine_hash"],
        "engine_source_inventory": source_inventory,
        "engine_source_manifest_path": verification["manifest_path"],
        "engine_source_manifest_sha256": verification["manifest_sha256"],
        "engine_source_verified": verification["verified"],
        "runtime_source_open_audit": verification["runtime_open_audit"],
    }
