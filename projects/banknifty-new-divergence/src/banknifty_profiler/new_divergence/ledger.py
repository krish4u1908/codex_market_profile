"""Append-only, hash-chained transition ledger."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import EpisodeTransition


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_hash(row: Mapping[str, object], previous_hash: str) -> str:
    payload = {key: value for key, value in row.items() if key not in {"previous_hash", "record_hash"}}
    raw = f"{previous_hash}\n{canonical_json(payload)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TransitionLedger:
    """Hash transitions before optional durable JSONL append."""

    def __init__(self, path: Path | None = None):
        self.path = None if path is None else Path(path)
        self.records: list[EpisodeTransition] = []
        self._identifiers: set[str] = set()
        self._last_hash = ""
        if self.path is not None and self.path.exists():
            verified = verify_ledger(self.path)
            if not verified["valid"]:
                raise ValueError(f"cannot append to invalid ledger: {verified['reason']}")
            rows = _read_rows(self.path)
            if rows:
                raise FileExistsError(
                    "existing non-empty ledger requires state restoration, which is not implemented"
                )

    @property
    def last_hash(self) -> str:
        return self._last_hash

    def append(self, transition: EpisodeTransition) -> EpisodeTransition:
        if transition.transition_id in self._identifiers:
            raise ValueError(f"duplicate transition_id: {transition.transition_id}")
        unsigned = transition.to_dict(include_hash=False)
        digest = record_hash(unsigned, self._last_hash)
        sealed = replace(transition, previous_hash=self._last_hash, record_hash=digest)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = canonical_json(sealed.to_dict()) + "\n"
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        self.records.append(sealed)
        self._identifiers.add(sealed.transition_id)
        self._last_hash = digest
        return sealed


def _read_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSON at line {line_number}") from error
            if not isinstance(row, dict):
                raise ValueError(f"ledger line {line_number} is not an object")
            rows.append(row)
    return rows


def verify_rows(rows: Iterable[Mapping[str, object]]) -> dict[str, object]:
    previous = ""
    seen: set[str] = set()
    count = 0
    for count, row in enumerate(rows, 1):
        identifier = str(row.get("transition_id", ""))
        if not identifier:
            return {"valid": False, "records": count - 1, "reason": f"line {count}: missing transition_id"}
        if identifier in seen:
            return {"valid": False, "records": count - 1, "reason": f"line {count}: duplicate transition_id"}
        if row.get("previous_hash", "") != previous:
            return {"valid": False, "records": count - 1, "reason": f"line {count}: broken previous_hash"}
        expected = record_hash(row, previous)
        if row.get("record_hash") != expected:
            return {"valid": False, "records": count - 1, "reason": f"line {count}: record_hash mismatch"}
        previous = expected
        seen.add(identifier)
    return {"valid": True, "records": count, "last_hash": previous, "reason": "OK"}


def verify_ledger(path: Path) -> dict[str, object]:
    try:
        return verify_rows(_read_rows(path))
    except (OSError, ValueError) as error:
        return {"valid": False, "records": 0, "reason": str(error)}
