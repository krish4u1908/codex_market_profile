"""Small deterministic persistence and parsing helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable, Iterator, Mapping, Sequence


def parse_instant(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid timestamp: {value!r}")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"timestamp lacks timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp lacks timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) else None


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row is not an object")
            rows.append(value)
    return rows


def iter_jsonl(path: Path) -> Iterator[dict[str, object]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row is not an object")
            yield value


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def atomic_text(path: Path, content: str, mode: int = 0o600) -> None:
    _atomic_bytes(path, content.encode("utf-8"), mode=mode)


def atomic_json(path: Path, value: object, mode: int = 0o600) -> None:
    atomic_text(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        mode=mode,
    )


def atomic_jsonl(path: Path, rows: Iterable[Mapping[str, object]], mode: int = 0o600) -> None:
    content = "".join(canonical_json(dict(row)) + "\n" for row in rows)
    atomic_text(path, content, mode=mode)


def unpack_rows(value: object, *, name: str) -> list[dict[str, object]]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} is not a packed object")
    fields = value.get("fields")
    rows = value.get("rows")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes)):
        raise ValueError(f"{name}.fields is invalid")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ValueError(f"{name}.rows is invalid")
    names = [str(field) for field in fields]
    if len(names) != len(set(names)):
        raise ValueError(f"{name}.fields contains duplicates")
    result: list[dict[str, object]] = []
    for position, row in enumerate(rows):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
            raise ValueError(f"{name}.rows[{position}] is invalid")
        if len(row) != len(names):
            raise ValueError(f"{name}.rows[{position}] width differs from fields")
        result.append(dict(zip(names, row)))
    return result


def ensure_new_directory(path: Path) -> Path:
    destination = Path(path).resolve()
    if destination.exists():
        if any(destination.iterdir()) if destination.is_dir() else True:
            raise FileExistsError(f"refusing to overwrite non-empty output: {destination}")
    else:
        destination.mkdir(parents=True)
    return destination
