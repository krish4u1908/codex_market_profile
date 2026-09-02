"""Strict configuration loading for the new divergence engine."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import EngineConfig


def load_config(path: Path | None) -> EngineConfig:
    if path is None:
        return EngineConfig()
    source = Path(path)
    try:
        row = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load engine config {source}: {error}") from error
    if not isinstance(row, dict):
        raise ValueError("engine config must be a JSON object")
    try:
        return EngineConfig.from_mapping(row)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid engine config {source}: {error}") from error
