from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import Lock


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AppendOnlyLedger:
    """A newline-delimited ledger whose acknowledged appends are durable."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, row: dict) -> None:
        self.append_many([row])

    def append_many(self, rows) -> None:
        encoded = b"".join(
            (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for row in rows
        )
        if not encoded:
            return
        with self._lock:
            existed = self.path.exists()
            with self.path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            # fsyncing only the new file is insufficient to make its directory
            # entry survive a power loss at the callback-before-ack boundary.
            if not existed:
                _fsync_directory(self.path.parent)

    def rows(self):
        if not self.path.exists():
            return []
        with self.path.open() as handle:
            return [json.loads(line) for line in handle if line.strip()]


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)
