#!/usr/bin/env python3
"""Prepare and authenticate an isolated provisional R6E1R clean start.

This validator deliberately uses only the Python standard library.  It does
not accept an equivalence result, a state manifest, or preloaded analytical
state.  Its only mutable operation is the one-time creation of a new empty
private state directory and a path/hash-bound attestation beside the runtime
configuration.

All stdout is sanitized.  Host paths, source filenames, database values, and
market records are never printed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile
from typing import Any, NoReturn, Sequence


SCHEMA = "R6E1R_PROVISIONAL_CLEAN_START_VALIDATION_V1"
ATTESTATION_SCHEMA = "R6E1R_PROVISIONAL_CLEAN_START_ATTESTATION_V1"
PACKAGE_SCHEMA = "R6E1R_PROVISIONAL_DEPLOYMENT_PACKAGE_MANIFEST_V1"
STATUS_SCHEMA = "R6E1R_PROVISIONAL_CLEAN_START_STATUS_V1"
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
PROVISIONAL_STATUS = "PROVISIONAL_CLEAN_START_FULL_SIX_PENDING"
FINAL_GATE = "PENDING_FULL_SIX_ALL_NINE"
ENGINE_BASE_COMMIT = "88f30e740d55376d1eb9ed091a4080b3372a2757"
ACTIVATION_DAY = "2026-08-26"
PACKAGE_MANIFEST_RELATIVE = (
    "manifests/r6e1r_provisional_deployment_package_manifest.json"
)
PACKAGE_COMPANION_RELATIVE = (
    "manifests/r6e1r_provisional_deployment_package_manifest.sha256"
)
ENGINE_MANIFEST_RELATIVE = "manifests/r6e1r_engine_source_manifest.json"
RUNTIME_CONFIG_RELATIVE = (
    "deploy/r6e1r_provisional/r6e1r-runtime-config.json.example"
)
ACTIVATION_RELATIVE = (
    "deploy/r6e1r_provisional/r6e1r-activation.json.example"
)
STATUS_RELATIVE = (
    "deploy/r6e1r_provisional/r6e1r-provisional-status.json"
)
ATTESTATION_NAME = "r6e1r-provisional-clean-start-attestation.json"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class ValidationError(Exception):
    """An expected refusal whose code is safe to expose."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def refuse(code: str) -> NoReturn:
    raise ValidationError(code)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        refuse("PACKAGE_FILE_UNREADABLE")
    return digest.hexdigest()


def canonical_json_sha256(value: dict[str, Any]) -> str:
    payload = (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    return sha256_bytes(payload)


def require_hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or HASH_PATTERN.fullmatch(value) is None:
        refuse(code)
    return value


def require_absolute_path(value: str, code: str) -> Path:
    path = Path(value)
    if (
        not value
        or value.startswith("//")
        or not path.is_absolute()
        or path == Path("/")
        or ".." in path.parts
        or str(path) != value
    ):
        refuse(code)
    return path


def require_no_symlink_components(path: Path, code: str) -> None:
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except OSError:
            refuse(code)
        if stat.S_ISLNK(value.st_mode):
            refuse(code)


def require_plain_directory(
    path: Path,
    code: str,
    *,
    owned: bool = False,
    private: bool = False,
) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError:
        refuse(code)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISDIR(value.st_mode):
        refuse(code)
    if owned and value.st_uid != os.getuid():
        refuse(code)
    if private and stat.S_IMODE(value.st_mode) & 0o077:
        refuse(code)
    return value


def require_plain_file(
    path: Path,
    code: str,
    *,
    owned: bool = False,
    private: bool = False,
) -> os.stat_result:
    try:
        value = path.lstat()
    except OSError:
        refuse(code)
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        refuse(code)
    if owned and value.st_uid != os.getuid():
        refuse(code)
    if private and stat.S_IMODE(value.st_mode) & 0o077:
        refuse(code)
    return value


def load_json_object(path: Path, code: str) -> dict[str, Any]:
    require_plain_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        refuse(code)
    if not isinstance(value, dict):
        refuse(code)
    return value


def safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        refuse("PACKAGE_MANIFEST_INVALID")
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        refuse("PACKAGE_MANIFEST_INVALID")
    return value


def repository_file(repository: Path, relative: str) -> Path:
    safe_relative_path(relative)
    cursor = repository
    for part in Path(relative).parts:
        cursor = cursor / part
        try:
            value = cursor.lstat()
        except OSError:
            refuse("PACKAGE_FILE_UNREADABLE")
        if stat.S_ISLNK(value.st_mode):
            refuse("PACKAGE_FILE_SYMLINK")
    require_plain_file(cursor, "PACKAGE_FILE_UNREADABLE")
    return cursor


def verify_package(repository: Path) -> dict[str, Any]:
    require_plain_directory(repository, "REPOSITORY_ROOT_INVALID")
    require_no_symlink_components(repository, "REPOSITORY_ROOT_INVALID")
    manifest_path = repository_file(repository, PACKAGE_MANIFEST_RELATIVE)
    companion_path = repository_file(repository, PACKAGE_COMPANION_RELATIVE)
    manifest_sha256 = sha256_file(manifest_path)
    try:
        companion = companion_path.read_text(encoding="ascii").split()
    except (OSError, UnicodeError):
        refuse("PACKAGE_COMPANION_INVALID")
    if companion != [manifest_sha256, PACKAGE_MANIFEST_RELATIVE]:
        refuse("PACKAGE_COMPANION_INVALID")

    package = load_json_object(manifest_path, "PACKAGE_MANIFEST_INVALID")
    allowlist = package.get("allowlist")
    files = package.get("files")
    if (
        package.get("schema") != PACKAGE_SCHEMA
        or package.get("classification") != CLASSIFICATION
        or package.get("provisional_status") != PROVISIONAL_STATUS
        or package.get("final_equivalence_status") != FINAL_GATE
        or package.get("engine_base_commit") != ENGINE_BASE_COMMIT
        or package.get("state_origin") != "EMPTY_AT_PREPARATION"
        or package.get("preloaded_state") is not False
        or package.get("historical_replay_certified") is not False
        or package.get("final_tag_authorized") is not False
        or not isinstance(allowlist, list)
        or allowlist != sorted(set(allowlist))
        or not isinstance(files, list)
        or package.get("file_count") != len(allowlist)
        or len(files) != len(allowlist)
    ):
        refuse("PACKAGE_MANIFEST_INVALID")

    expected_rows: list[dict[str, Any]] = []
    aggregate = hashlib.sha256()
    for relative, row in zip(allowlist, files, strict=True):
        if not isinstance(row, dict) or row.get("path") != relative:
            refuse("PACKAGE_MANIFEST_INVALID")
        path = repository_file(repository, relative)
        payload_sha256 = sha256_file(path)
        size = path.stat().st_size
        expected = {
            "path": relative,
            "sha256": payload_sha256,
            "size": size,
        }
        if row != expected:
            refuse("PACKAGE_FILE_IDENTITY_MISMATCH")
        expected_rows.append(expected)
        aggregate.update(
            f"{relative}\0{payload_sha256}\0{size}\n".encode("utf-8")
        )
    if package.get("files") != expected_rows:
        refuse("PACKAGE_MANIFEST_INVALID")
    if package.get("package_hash") != aggregate.hexdigest():
        refuse("PACKAGE_AGGREGATE_MISMATCH")

    engine_manifest_path = repository_file(
        repository, ENGINE_MANIFEST_RELATIVE
    )
    engine_manifest_sha256 = sha256_file(engine_manifest_path)
    engine_manifest = load_json_object(
        engine_manifest_path, "ENGINE_MANIFEST_INVALID"
    )
    engine_hash = require_hash(
        engine_manifest.get("engine_hash"), "ENGINE_HASH_INVALID"
    )
    if (
        package.get("engine_source_manifest_sha256")
        != engine_manifest_sha256
        or package.get("engine_hash") != engine_hash
    ):
        refuse("ENGINE_IDENTITY_MISMATCH")

    runtime_template = repository_file(repository, RUNTIME_CONFIG_RELATIVE)
    runtime_config = load_json_object(
        runtime_template, "RUNTIME_CONFIGURATION_INVALID"
    )
    runtime_configuration_hash = canonical_json_sha256(runtime_config)
    if (
        runtime_config.get("classification") != CLASSIFICATION
        or runtime_config.get("analytical_threshold_overrides") is not None
        or runtime_config.get("engine_source_manifest_path")
        != ENGINE_MANIFEST_RELATIVE
        or runtime_config.get("engine_source_manifest_sha256")
        != engine_manifest_sha256
        or package.get("runtime_configuration_hash")
        != runtime_configuration_hash
    ):
        refuse("RUNTIME_CONFIGURATION_INVALID")

    activation_path = repository_file(repository, ACTIVATION_RELATIVE)
    activation = load_json_object(activation_path, "ACTIVATION_INVALID")
    if (
        activation.get("activation_day") != ACTIVATION_DAY
        or activation.get("classification") != CLASSIFICATION
        or set(activation) != {"activation_day", "classification", "scope"}
    ):
        refuse("ACTIVATION_INVALID")

    status_path = repository_file(repository, STATUS_RELATIVE)
    status = load_json_object(status_path, "STATUS_CONTRACT_INVALID")
    if (
        status.get("schema") != STATUS_SCHEMA
        or status.get("classification") != CLASSIFICATION
        or status.get("status") != PROVISIONAL_STATUS
        or status.get("final_equivalence_status") != FINAL_GATE
        or status.get("engine_base_commit") != ENGINE_BASE_COMMIT
        or status.get("state_origin") != "EMPTY_AT_PREPARATION"
        or status.get("preloaded_state") is not False
        or status.get("historical_replay_certified") is not False
        or status.get("final_tag_authorized") is not False
    ):
        refuse("STATUS_CONTRACT_INVALID")

    return {
        "manifest_sha256": manifest_sha256,
        "package_hash": str(package["package_hash"]),
        "package_file_count": len(expected_rows),
        "engine_manifest_sha256": engine_manifest_sha256,
        "engine_hash": engine_hash,
        "runtime_template_sha256": sha256_file(runtime_template),
        "runtime_configuration_hash": runtime_configuration_hash,
        "activation_sha256": sha256_file(activation_path),
        "status_contract_sha256": sha256_file(status_path),
    }


def validate_layout(args: argparse.Namespace) -> dict[str, Any]:
    repository = require_absolute_path(
        args.repository_root, "REPOSITORY_ROOT_INVALID"
    )
    collector = require_absolute_path(
        args.collector_root, "COLLECTOR_ROOT_INVALID"
    )
    deployment = require_absolute_path(
        args.deploy_root, "DEPLOYMENT_ROOT_INVALID"
    )
    state = require_absolute_path(args.state_root, "STATE_ROOT_INVALID")
    runtime_config = require_absolute_path(
        args.runtime_config, "RUNTIME_CONFIGURATION_INVALID"
    )
    activation = require_absolute_path(args.activation, "ACTIVATION_INVALID")
    attestation = require_absolute_path(
        args.attestation, "ATTESTATION_PATH_INVALID"
    )

    if state != deployment / "state":
        refuse("STATE_ROOT_INVALID")
    if runtime_config != deployment / "config/r6e1r-runtime-config.json":
        refuse("RUNTIME_CONFIGURATION_INVALID")
    if activation != deployment / "config/r6e1r-activation.json":
        refuse("ACTIVATION_INVALID")
    if attestation != deployment / "config" / ATTESTATION_NAME:
        refuse("ATTESTATION_PATH_INVALID")
    protected = (repository, collector, deployment)
    for index, left in enumerate(protected):
        for right in protected[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                refuse("ROOTS_OVERLAP")

    require_plain_directory(repository, "REPOSITORY_ROOT_INVALID")
    require_plain_directory(collector, "COLLECTOR_ROOT_INVALID")
    require_no_symlink_components(collector, "COLLECTOR_ROOT_INVALID")
    collector_stat = require_plain_directory(
        collector, "COLLECTOR_ROOT_INVALID"
    )
    for child in (collector / "raw", collector / "oi"):
        require_plain_directory(child, "COLLECTOR_STREAM_ROOT_INVALID")
        if not os.access(child, os.R_OK | os.X_OK):
            refuse("COLLECTOR_STREAM_ROOT_UNREADABLE")
    deployment_stat = require_plain_directory(
        deployment,
        "DEPLOYMENT_ROOT_INVALID",
        owned=True,
        private=True,
    )
    require_no_symlink_components(deployment, "DEPLOYMENT_ROOT_INVALID")
    config_root = deployment / "config"
    require_plain_directory(
        config_root,
        "CONFIGURATION_ROOT_INVALID",
        owned=True,
        private=True,
    )
    require_plain_file(
        runtime_config,
        "RUNTIME_CONFIGURATION_INVALID",
        owned=True,
        private=True,
    )
    require_plain_file(
        activation,
        "ACTIVATION_INVALID",
        owned=True,
        private=True,
    )
    return {
        "repository": repository,
        "collector": collector,
        "collector_stat": collector_stat,
        "deployment": deployment,
        "deployment_stat": deployment_stat,
        "state": state,
        "runtime_config": runtime_config,
        "activation": activation,
        "attestation": attestation,
    }


def verify_deployed_configuration(
    layout: dict[str, Any], package: dict[str, Any]
) -> dict[str, str]:
    runtime_payload = layout["runtime_config"].read_bytes()
    activation_payload = layout["activation"].read_bytes()
    if sha256_bytes(runtime_payload) != package["runtime_template_sha256"]:
        refuse("RUNTIME_CONFIGURATION_IDENTITY_MISMATCH")
    if sha256_bytes(activation_payload) != package["activation_sha256"]:
        refuse("ACTIVATION_IDENTITY_MISMATCH")
    try:
        runtime_config = json.loads(runtime_payload)
        activation = json.loads(activation_payload)
    except json.JSONDecodeError:
        refuse("DEPLOYED_CONFIGURATION_INVALID")
    if not isinstance(runtime_config, dict) or not isinstance(activation, dict):
        refuse("DEPLOYED_CONFIGURATION_INVALID")
    if canonical_json_sha256(runtime_config) != package["runtime_configuration_hash"]:
        refuse("RUNTIME_CONFIGURATION_IDENTITY_MISMATCH")
    if (
        runtime_config.get("engine_source_manifest_sha256")
        != package["engine_manifest_sha256"]
        or activation.get("activation_day") != ACTIVATION_DAY
        or activation.get("classification") != CLASSIFICATION
    ):
        refuse("DEPLOYED_CONFIGURATION_INVALID")
    return {
        "runtime_config_sha256": sha256_bytes(runtime_payload),
        "activation_sha256": sha256_bytes(activation_payload),
    }


def path_sha256(path: Path) -> str:
    return sha256_bytes(str(path).encode("utf-8"))


def directory_identity(value: os.stat_result) -> dict[str, int]:
    return {"device": int(value.st_dev), "inode": int(value.st_ino)}


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.lexists(path):
            refuse("ATTESTATION_ALREADY_EXISTS")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def prepare_clean_start(
    layout: dict[str, Any],
    package: dict[str, Any],
    deployed: dict[str, str],
) -> dict[str, Any]:
    state = layout["state"]
    attestation = layout["attestation"]
    if os.path.lexists(state):
        refuse("STATE_ROOT_ALREADY_EXISTS")
    if os.path.lexists(attestation):
        refuse("ATTESTATION_ALREADY_EXISTS")

    try:
        os.mkdir(state, 0o700)
    except OSError:
        refuse("STATE_ROOT_CREATE_FAILED")
    created_stat = state.lstat()
    try:
        value = {
            "schema": ATTESTATION_SCHEMA,
            "classification": CLASSIFICATION,
            "status": PROVISIONAL_STATUS,
            "final_equivalence_status": FINAL_GATE,
            "engine_base_commit": ENGINE_BASE_COMMIT,
            "state_origin": "EMPTY_AT_PREPARATION",
            "preloaded_state": False,
            "historical_replay_certified": False,
            "final_tag_authorized": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "package_manifest_sha256": package["manifest_sha256"],
            "package_hash": package["package_hash"],
            "engine_manifest_sha256": package["engine_manifest_sha256"],
            "engine_hash": package["engine_hash"],
            "runtime_config_sha256": deployed["runtime_config_sha256"],
            "runtime_configuration_hash": package[
                "runtime_configuration_hash"
            ],
            "activation_sha256": deployed["activation_sha256"],
            "activation_day": ACTIVATION_DAY,
            "status_contract_sha256": package["status_contract_sha256"],
            "repository_path_sha256": path_sha256(layout["repository"]),
            "collector_path_sha256": path_sha256(layout["collector"]),
            "deployment_path_sha256": path_sha256(layout["deployment"]),
            "state_path_sha256": path_sha256(state),
            "collector_identity": directory_identity(layout["collector_stat"]),
            "deployment_identity": directory_identity(
                layout["deployment_stat"]
            ),
            "state_identity": directory_identity(created_stat),
        }
        _atomic_private_json(attestation, value)
    except Exception:
        try:
            current = state.lstat()
            if (
                current.st_dev == created_stat.st_dev
                and current.st_ino == created_stat.st_ino
            ):
                state.rmdir()
        except OSError:
            pass
        raise
    return {
        "state_mode": "NEW_EMPTY_STATE",
        "attestation_sha256": sha256_file(attestation),
    }


def validate_state_tree(state: Path) -> dict[str, Any]:
    state_stat = require_plain_directory(
        state, "STATE_ROOT_INVALID", owned=True, private=True
    )
    file_count = 0
    directory_count = 0
    sidecars = 0
    for current, directory_names, file_names in os.walk(
        state, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        for name in directory_names:
            child = current_path / name
            require_plain_directory(
                child, "STATE_TREE_INVALID", owned=True, private=True
            )
            directory_count += 1
        for name in file_names:
            child = current_path / name
            require_plain_file(
                child, "STATE_TREE_INVALID", owned=True, private=True
            )
            if name.endswith(("-journal", "-wal", "-shm")):
                sidecars += 1
            file_count += 1

    checkpoints = state / "checkpoints.json"
    if checkpoints.exists():
        value = load_json_object(checkpoints, "CHECKPOINT_JSON_INVALID")
        if not all(isinstance(key, str) for key in value):
            refuse("CHECKPOINT_JSON_INVALID")
    orchestrator = state / "live_analytical_orchestrator.json"
    if orchestrator.exists():
        value = load_json_object(orchestrator, "ANALYTICAL_STATE_INVALID")
        if value.get("version") != "R6E1R_LIVE_ANALYTICAL_STATE_V1":
            refuse("ANALYTICAL_STATE_INVALID")
    database = state / "dedup.sqlite3"
    sqlite_status = "NOT_INITIALIZED"
    if database.exists() and sidecars == 0:
        try:
            uri = database.resolve(strict=True).as_uri() + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True) as connection:
                quick_check = [
                    str(row[0])
                    for row in connection.execute("pragma quick_check")
                ]
        except (OSError, sqlite3.Error, ValueError):
            refuse("DATABASE_QUICK_CHECK_FAILED")
        if quick_check != ["ok"]:
            refuse("DATABASE_QUICK_CHECK_FAILED")
        sqlite_status = "OK"
    elif database.exists():
        # A hard-stop can leave a legitimate SQLite recovery sidecar.  The
        # authenticated runtime owns recovery; immutable preflight must not
        # misread or delete it.
        sqlite_status = "RUNTIME_RECOVERY_PENDING"
    return {
        "identity": directory_identity(state_stat),
        "file_count": file_count,
        "directory_count": directory_count,
        "sidecar_count": sidecars,
        "sqlite_status": sqlite_status,
        "state_mode": "NEW_EMPTY_STATE" if not file_count else "AUTHENTICATED_RESTART",
    }


def validate_attestation(
    layout: dict[str, Any],
    package: dict[str, Any],
    deployed: dict[str, str],
) -> dict[str, Any]:
    attestation_path = layout["attestation"]
    require_plain_file(
        attestation_path,
        "ATTESTATION_INVALID",
        owned=True,
        private=True,
    )
    value = load_json_object(attestation_path, "ATTESTATION_INVALID")
    expected_scalars = {
        "schema": ATTESTATION_SCHEMA,
        "classification": CLASSIFICATION,
        "status": PROVISIONAL_STATUS,
        "final_equivalence_status": FINAL_GATE,
        "engine_base_commit": ENGINE_BASE_COMMIT,
        "state_origin": "EMPTY_AT_PREPARATION",
        "preloaded_state": False,
        "historical_replay_certified": False,
        "final_tag_authorized": False,
        "package_manifest_sha256": package["manifest_sha256"],
        "package_hash": package["package_hash"],
        "engine_manifest_sha256": package["engine_manifest_sha256"],
        "engine_hash": package["engine_hash"],
        "runtime_config_sha256": deployed["runtime_config_sha256"],
        "runtime_configuration_hash": package["runtime_configuration_hash"],
        "activation_sha256": deployed["activation_sha256"],
        "activation_day": ACTIVATION_DAY,
        "status_contract_sha256": package["status_contract_sha256"],
        "repository_path_sha256": path_sha256(layout["repository"]),
        "collector_path_sha256": path_sha256(layout["collector"]),
        "deployment_path_sha256": path_sha256(layout["deployment"]),
        "state_path_sha256": path_sha256(layout["state"]),
    }
    if any(value.get(key) != expected for key, expected in expected_scalars.items()):
        refuse("ATTESTATION_IDENTITY_MISMATCH")
    if not isinstance(value.get("created_at"), str) or not value["created_at"]:
        refuse("ATTESTATION_INVALID")
    if value.get("collector_identity") != directory_identity(
        layout["collector_stat"]
    ):
        refuse("ATTESTATION_IDENTITY_MISMATCH")
    if value.get("deployment_identity") != directory_identity(
        layout["deployment_stat"]
    ):
        refuse("ATTESTATION_IDENTITY_MISMATCH")
    state = validate_state_tree(layout["state"])
    if value.get("state_identity") != state["identity"]:
        refuse("ATTESTATION_STATE_REPLACED")
    return {
        "state_mode": state["state_mode"],
        "state_file_count": state["file_count"],
        "state_directory_count": state["directory_count"],
        "sqlite_status": state["sqlite_status"],
        "attestation_sha256": sha256_file(attestation_path),
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("action", choices=("prepare", "start-check"))
    value.add_argument("--repository-root", required=True)
    value.add_argument("--collector-root", required=True)
    value.add_argument("--deploy-root", required=True)
    value.add_argument("--state-root", required=True)
    value.add_argument("--runtime-config", required=True)
    value.add_argument("--activation", required=True)
    value.add_argument("--attestation", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        layout = validate_layout(args)
        package = verify_package(layout["repository"])
        deployed = verify_deployed_configuration(layout, package)
        if args.action == "prepare":
            detail = prepare_clean_start(layout, package, deployed)
        else:
            detail = validate_attestation(layout, package, deployed)
        result = {
            "schema": SCHEMA,
            "ok": True,
            "action": args.action,
            "classification": CLASSIFICATION,
            "status": PROVISIONAL_STATUS,
            "final_equivalence_status": FINAL_GATE,
            "engine_base_commit": ENGINE_BASE_COMMIT,
            "package_file_count": package["package_file_count"],
            "package_hash": package["package_hash"],
            "engine_hash": package["engine_hash"],
            "preloaded_state": False,
            "historical_replay_certified": False,
            "final_tag_authorized": False,
            **detail,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ValidationError as error:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "error_code": error.code,
        }
    except Exception:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "error_code": "INTERNAL_VALIDATION_ERROR",
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 1


if __name__ == "__main__":
    sys.exit(main())
