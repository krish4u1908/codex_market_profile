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

# Runtime source identity is intentionally explicit. The verified R6D source
# manifest remains immutable historical evidence and cannot identify R6E code.
# Relative paths also make every startup source open reviewable/allowlisted.
ENGINE_SOURCE_ALLOWLIST = (
    "scripts/run_r6e_shadow.py",
    "src/banknifty_profiler/context/availability.py",
    "src/banknifty_profiler/cross_layer/state.py",
    "src/banknifty_profiler/divergence/dependency.py",
    "src/banknifty_profiler/divergence/detector.py",
    "src/banknifty_profiler/gui/adapter.py",
    "src/banknifty_profiler/inventory/engine.py",
    "src/banknifty_profiler/lifecycle/raw_engine.py",
    "src/banknifty_profiler/participation/raw_engine.py",
    "src/banknifty_profiler/participation/views.py",
    "src/banknifty_profiler/raw_io/reader.py",
    "src/banknifty_profiler/runtime/configuration.py",
    "src/banknifty_profiler/runtime/timestamps.py",
    "src/banknifty_profiler/shadow/api.py",
    "src/banknifty_profiler/shadow/contracts.py",
    "src/banknifty_profiler/shadow/ingest.py",
    "src/banknifty_profiler/shadow/ledger.py",
    "src/banknifty_profiler/shadow/observation.py",
    "src/banknifty_profiler/shadow/orchestrator.py",
    "src/banknifty_profiler/shadow/state.py",
    "src/banknifty_profiler/shadow/symbols.py",
)


def _source_path(repo: Path, relative: str) -> Path:
    item = Path(relative)
    if item.is_absolute() or ".." in item.parts:
        raise ValueError(f"unsafe engine source allowlist path: {relative!r}")
    resolved_repo = repo.resolve()
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


def validate_shadow_contract(
    data_root: Path,
    state_root: Path,
    config_path: Path,
    bind: str,
    mode: str,
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
    raw_config = json.loads(config_file.read_text())
    raw_config.setdefault("index_symbol", CANONICAL_INDEX_SYMBOL)
    raw_config.setdefault(
        "futures_selection_mode", "SESSION_NEAREST_UNEXPIRED_HIGHEST_OI"
    )
    raw_config.setdefault("selected_futures_by_session", {})
    raw_config.setdefault("analytical_refresh_seconds", 30.0)
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

    source_inventory = engine_source_inventory(repo)
    canonical_sources = (
        json.dumps(source_inventory, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    return {
        "data_root": data,
        "state_root": state,
        "config_path": config_file,
        "config": config,
        "configuration_hash": canonical_configuration_sha256(config),
        "engine_hash": hashlib.sha256(canonical_sources).hexdigest(),
        "engine_source_inventory": source_inventory,
        "engine_source_verified": True,
    }
