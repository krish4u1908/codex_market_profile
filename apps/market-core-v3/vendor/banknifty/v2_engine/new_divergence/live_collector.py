"""Read-only, complete-line tailing of one collector session."""

from __future__ import annotations

from datetime import date
import io
import json
import os
from pathlib import Path
from typing import Mapping

from .collector_archive import CollectorArchiveAdapter
from .contracts import MarketEvent


def _normalizer(session: date, futures_symbol: str | None) -> CollectorArchiveAdapter:
    """Construct the archive normalizer without requiring a tar container."""

    adapter = CollectorArchiveAdapter.__new__(CollectorArchiveAdapter)
    adapter.archive = Path("LIVE_READ_ONLY_SOURCE")
    adapter.session = session
    adapter.start = None
    adapter.end = None
    adapter.requested_futures_symbol = (
        None if futures_symbol is None else futures_symbol.upper()
    )
    adapter.include_auxiliary = True
    adapter.chunk_size = 1
    adapter.strict = True
    adapter.stats = {}
    adapter._metadata_future = None
    adapter._metadata_index = None
    adapter._metadata_started_at = None
    adapter._sequence = 0
    adapter._exclusions = {}
    return adapter


class LiveCollectorTail:
    """Tail collector JSONL files without modifying or locking them."""

    def __init__(
        self,
        data_root: Path,
        session: date,
        *,
        offsets: Mapping[str, object] | None = None,
        futures_symbol: str | None = None,
    ) -> None:
        self.root = Path(data_root).resolve()
        self.session = session
        self.adapter = _normalizer(session, futures_symbol)
        self.offsets: dict[str, dict[str, int]] = {
            str(key): {
                "offset": int(value.get("offset", 0)),
                "line": int(value.get("line", 0)),
                "inode": int(value.get("inode", 0)),
            }
            for key, value in (offsets or {}).items()
            if isinstance(value, Mapping)
        }
        self._load_metadata()

    def _load_metadata(self) -> None:
        metadata = self.root / "metadata"
        if not metadata.is_dir():
            return
        for path in sorted(metadata.glob("startup_*.json")):
            try:
                self.adapter._consume_startup(io.BytesIO(path.read_bytes()))
            except OSError:
                continue

    def _sources(self) -> list[tuple[str, Path]]:
        day = self.session.isoformat()
        result: list[tuple[str, Path]] = []
        for kind, directory, pattern in (
            ("raw", self.root / "raw" / day, "events_*.jsonl"),
            ("oi", self.root / "oi" / day, "oi_*.jsonl"),
        ):
            if directory.is_dir():
                result.extend((kind, path) for path in sorted(directory.glob(pattern)))
        return result

    def poll(self) -> tuple[list[MarketEvent], dict[str, object]]:
        events: list[MarketEvent] = []
        for kind, path in self._sources():
            relative = str(path.relative_to(self.root))
            stat = path.stat()
            state = self.offsets.get(relative, {"offset": 0, "line": 0, "inode": stat.st_ino})
            if state["inode"] not in {0, stat.st_ino}:
                raise ValueError(f"live collector source rotated: {relative}")
            if stat.st_size < state["offset"]:
                raise ValueError(f"live collector source truncated: {relative}")
            with path.open("rb") as handle:
                handle.seek(state["offset"])
                while True:
                    beginning = handle.tell()
                    raw = handle.readline()
                    if not raw:
                        break
                    if not raw.endswith(b"\n"):
                        # The collector may still be writing this record. Leave
                        # it unread so the next poll sees the complete bytes.
                        handle.seek(beginning)
                        break
                    state["line"] += 1
                    if not raw.strip():
                        state["offset"] = handle.tell()
                        continue
                    try:
                        row = json.loads(raw)
                        if not isinstance(row, Mapping):
                            raise ValueError("row is not an object")
                        member = relative
                        if kind == "raw":
                            event = self.adapter._raw_event(row, member, state["line"], raw)
                            normalized = () if event is None else (event,)
                        else:
                            normalized = self.adapter._oi_events(row, member, state["line"], raw)
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                        raise ValueError(
                            f"invalid selected live row {relative}:{state['line']}: {error}"
                        ) from error
                    events.extend(normalized)
                    state["offset"] = handle.tell()
            state["inode"] = stat.st_ino
            self.offsets[relative] = state
        events.sort(key=lambda event: event.sort_key)
        return events, {key: dict(value) for key, value in sorted(self.offsets.items())}

