"""Self-contained runtime identity for every published run."""

from __future__ import annotations

import hashlib
from pathlib import Path

RUNTIME_VERSION = "1.0.35"


def runtime_identity() -> dict[str, object]:
    root = Path(__file__).resolve().parent
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".html", ".js", ".css"}
    )
    digest = hashlib.sha256()
    inventory = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        item_hash = hashlib.sha256(content).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(item_hash))
        inventory.append({"path": relative, "sha256": item_hash})
    return {
        "runtime": "banknifty_profiler.new_divergence",
        "version": RUNTIME_VERSION,
        "source_tree_sha256": digest.hexdigest(),
        "source_file_count": len(inventory),
        "source_files": inventory,
    }
