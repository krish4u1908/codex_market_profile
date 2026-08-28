#!/usr/bin/env python3
"""Render the isolated provisional R6E1R user-service templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Mapping, Sequence


SCHEMA = "R6E1R_PROVISIONAL_RENDERED_USER_UNITS_V1"
TEMPLATE_NAMES = (
    "r6e1r-provisional-shadow.service",
    "r6e1r-provisional-readonly-gateway.service",
)
TOKEN_PATTERN = re.compile(r"@[A-Z0-9_]+@")
SAFE_ABSOLUTE_PATH = re.compile(
    r"/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+\Z"
)
SANDBOX_HIDDEN_PREFIXES = (
    Path("/home"),
    Path("/root"),
    Path("/tmp"),
    Path("/var/tmp"),
    Path("/run/user"),
)
REQUIRED_TOKENS = {
    "r6e1r-provisional-shadow.service": frozenset(
        {
            "@R6E1R_REPOSITORY_ROOT@",
            "@R6E1R_COLLECTOR_ROOT@",
            "@R6E1R_DEPLOY_ROOT@",
            "@R6E1R_PYTHON@",
        }
    ),
    "r6e1r-provisional-readonly-gateway.service": frozenset(
        {
            "@R6E1R_REPOSITORY_ROOT@",
            "@R6E1R_COLLECTOR_ROOT@",
            "@R6E1R_DEPLOY_ROOT@",
            "@R6E1R_GATEWAY_PORT@",
        }
    ),
}


class RenderError(ValueError):
    """A sanitized deployment-template refusal."""


def _absolute_path(value: str, label: str) -> str:
    if not SAFE_ABSOLUTE_PATH.fullmatch(value):
        raise RenderError(f"{label} must be a normalized absolute path")
    path = Path(value)
    if ".." in path.parts or str(path) != value:
        raise RenderError(f"{label} must be a normalized absolute path")
    return value


def _replacements(args: argparse.Namespace) -> Mapping[str, str]:
    port = int(args.gateway_port)
    if port < 8805 or port > 8810:
        raise RenderError("gateway port must be in the approved range")
    repository = _absolute_path(args.repository_root, "repository root")
    collector = _absolute_path(args.collector_root, "collector root")
    deployment = _absolute_path(args.deploy_root, "deployment root")
    python = _absolute_path(args.python, "Python executable")
    protected = tuple(Path(value) for value in (
        repository,
        collector,
        deployment,
    ))
    for path in (*protected, Path(python)):
        if any(
            path == prefix or prefix in path.parents
            for prefix in SANDBOX_HIDDEN_PREFIXES
        ):
            raise RenderError("service input path conflicts with unit sandboxing")
    for index, left in enumerate(protected):
        for right in protected[index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                raise RenderError(
                    "repository, collector, and deployment roots must not overlap"
                )
    if Path(deployment) in Path(python).parents:
        raise RenderError(
            "Python executable must not be below the writable deployment root"
        )
    return {
        "@R6E1R_REPOSITORY_ROOT@": repository,
        "@R6E1R_COLLECTOR_ROOT@": collector,
        "@R6E1R_DEPLOY_ROOT@": deployment,
        "@R6E1R_PYTHON@": python,
        "@R6E1R_GATEWAY_PORT@": str(port),
    }


def render_units(
    template_root: Path,
    output_root: Path,
    replacements: Mapping[str, str],
) -> list[dict[str, object]]:
    if template_root.is_symlink() or output_root.is_symlink():
        raise RenderError("unit directories must not be symlinks")
    template_root = template_root.resolve()
    output_root = output_root.resolve()
    if output_root == template_root:
        raise RenderError("output directory must not replace sealed templates")
    if not output_root.is_dir():
        raise RenderError("output directory must be an existing plain directory")

    rendered: dict[str, bytes] = {}
    for name in TEMPLATE_NAMES:
        template = template_root / name
        if not template.is_file() or template.is_symlink():
            raise RenderError("sealed provisional template is unavailable")
        source = template.read_text(encoding="utf-8")
        observed_tokens = frozenset(TOKEN_PATTERN.findall(source))
        if observed_tokens != REQUIRED_TOKENS[name]:
            raise RenderError("sealed provisional template token set is invalid")
        for token in observed_tokens:
            source = source.replace(token, replacements[token])
        if TOKEN_PATTERN.search(source):
            raise RenderError("unresolved provisional unit token")
        rendered[name] = source.encode("utf-8")

    staged: list[tuple[Path, Path]] = []
    try:
        for name, payload in rendered.items():
            descriptor, temporary = tempfile.mkstemp(
                prefix=f".{name}.", dir=output_root
            )
            temporary_path = Path(temporary)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.chmod(0o644)
            staged.append((temporary_path, output_root / name))
        for temporary, target in staged:
            os.replace(temporary, target)
        directory = os.open(output_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)

    return [
        {
            "name": name,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
        for name, payload in sorted(rendered.items())
    ]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repository-root", required=True)
    value.add_argument("--collector-root", required=True)
    value.add_argument("--deploy-root", required=True)
    value.add_argument("--python", required=True)
    value.add_argument("--gateway-port", type=int, default=8805)
    value.add_argument("--output-dir", required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        rows = render_units(
            Path(__file__).resolve().parent,
            Path(args.output_dir),
            _replacements(args),
        )
        result = {"schema": SCHEMA, "ok": True, "units": rows}
    except Exception:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "error": "PROVISIONAL_UNIT_RENDER_REFUSED",
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
