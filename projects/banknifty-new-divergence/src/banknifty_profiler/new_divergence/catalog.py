"""Dynamic exchange-session discovery with explicit quality gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from typing import Iterable

from .adapters import load_events
from .clock import iso_utc
from .contracts import EventKind, MarketEvent

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CANONICAL_FILES = {
    "inventory": "runs/stream_inventory/canonical_inventory.csv",
    "availability": "runs/stream_layers/layer_availability.csv",
    "cross_layer": "runs/stream_layers/canonical_cross_layer_transitions.csv",
    "episodes": "runs/stream_stack/native/raw_divergence_episodes.csv",
    "dependencies": "runs/stream_stack/native/raw_dependency_groups.csv",
    "lifecycle": "runs/stream_stack/native/raw_lifecycle_transitions.csv",
    "resolution": "runs/stream_stack/native/raw_resolution_observations.csv",
    "participation_dense": "runs/stream_stack/views/dense_participation_view.csv",
    "participation_transitions": "runs/stream_stack/views/transition_participation_ledger.csv",
    "participation_summary": "runs/stream_stack/views/episode_participation_summary.csv",
    "compatibility": "runs/stream_stack/views/legacy_compatibility_snapshot.csv",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class SessionEntry:
    session: str
    eligible: bool
    reasons: tuple[str, ...]
    event_files: tuple[str, ...]
    event_count: int
    first_receipt: str
    last_receipt: str
    kinds: dict[str, int]
    symbols: tuple[str, ...]
    file_hashes: dict[str, str]
    source: str = "NORMALIZED_EVENTS"
    available_horizons: tuple[str, ...] = ()
    scope_dates: dict[str, tuple[str, ...]] | None = None

    def to_dict(self) -> dict:
        row = asdict(self)
        row["reasons"] = list(self.reasons)
        row["event_files"] = list(self.event_files)
        row["symbols"] = list(self.symbols)
        row["available_horizons"] = list(self.available_horizons)
        row["scope_dates"] = {
            key: list(value) for key, value in (self.scope_dates or {}).items()
        }
        return row


class SessionCatalog:
    def __init__(self, entries: Iterable[SessionEntry]):
        ordered = sorted(entries, key=lambda entry: entry.session)
        if len({entry.session for entry in ordered}) != len(ordered):
            raise ValueError("duplicate session catalog entry")
        self.entries = tuple(ordered)

    @classmethod
    def discover_events(cls, root: Path) -> "SessionCatalog":
        base = Path(root).resolve()
        if not base.is_dir():
            raise FileNotFoundError(base)
        candidates = sorted({
            *base.rglob("events.jsonl"),
            *base.rglob("events.csv"),
            *base.rglob("events_*.jsonl"),
            *base.rglob("events_*.csv"),
        })
        grouped: dict[date, list[tuple[Path, MarketEvent]]] = {}
        for path in candidates:
            for event in load_events(path):
                grouped.setdefault(event.session, []).append((path, event))
        entries = []
        for day, records in sorted(grouped.items()):
            files = tuple(sorted({str(path.relative_to(base)) for path, _ in records}))
            events = sorted((event for _, event in records), key=lambda event: event.sort_key)
            counts = {kind.value: sum(event.kind == kind for event in events) for kind in EventKind}
            counts = {key: value for key, value in counts.items() if value}
            reasons = []
            if counts.get(EventKind.INDEX_TICK.value, 0) == 0:
                reasons.append("MISSING_INDEX_TICKS")
            if counts.get(EventKind.FUTURES_TICK.value, 0) == 0:
                reasons.append("MISSING_FUTURES_TICKS")
            hashes = {name: sha256_file(base / name) for name in files}
            entries.append(SessionEntry(
                session=day.isoformat(),
                eligible=not reasons,
                reasons=tuple(reasons) if reasons else ("NORMALIZED_CAUSAL_INPUT_AVAILABLE",),
                event_files=files,
                event_count=len(events),
                first_receipt=iso_utc(events[0].receipt_timestamp),
                last_receipt=iso_utc(events[-1].receipt_timestamp),
                kinds=counts,
                symbols=tuple(sorted({event.symbol for event in events if event.symbol})),
                file_hashes=hashes,
            ))
        return cls(entries)

    @classmethod
    def discover_canonical(cls, root: Path) -> "SessionCatalog":
        base = Path(root).resolve()
        paths = {name: base / relative for name, relative in CANONICAL_FILES.items()}
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"canonical inputs missing: {missing}")
        by_table: dict[str, dict[str, list[dict[str, str]]]] = {}
        dates: set[str] = set()
        for name, path in paths.items():
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            grouped: dict[str, list[dict[str, str]]] = {}
            for row in rows:
                value = row.get("evaluation_date") or row.get("date") or ""
                if DATE_RE.match(value):
                    grouped.setdefault(value, []).append(row)
                    dates.add(value)
            by_table[name] = grouped
        entries = []
        hashes = {name: sha256_file(path) for name, path in paths.items()}
        for day in sorted(dates):
            inventory = by_table["inventory"].get(day, [])
            availability = by_table["availability"].get(day, [])
            resolution = by_table["resolution"].get(day, [])
            reasons = []
            if not resolution:
                reasons.append("MISSING_SYNCHRONIZED_MARKET_ROWS")
            if not availability:
                reasons.append("MISSING_LAYER_AVAILABILITY")
            horizons = tuple(sorted({
                row.get("horizon", "") for row in availability
                if row.get("availability_state") == "AVAILABLE"
            }))
            scopes: dict[str, set[str]] = {}
            for row in inventory:
                horizon = row.get("horizon", "")
                raw = row.get("source_sessions", "")
                values = [value for value in re.split(r"[|,]", raw) if DATE_RE.match(value)]
                if horizon:
                    scopes.setdefault(horizon, set()).update(values)
            timestamps = [
                row.get("timestamp", "") for row in resolution if row.get("timestamp")
            ]
            entries.append(SessionEntry(
                session=day,
                eligible=not reasons,
                reasons=tuple(reasons) if reasons else ("SEALED_CANONICAL_SESSION_AVAILABLE",),
                event_files=tuple(CANONICAL_FILES.values()),
                event_count=sum(len(table.get(day, [])) for table in by_table.values()),
                first_receipt=min(timestamps) if timestamps else "",
                last_receipt=max(timestamps) if timestamps else "",
                kinds={name: len(table.get(day, [])) for name, table in by_table.items()},
                symbols=(),
                file_hashes=hashes,
                source="SEALED_R6D_CANONICAL",
                available_horizons=horizons,
                scope_dates={key: tuple(sorted(value)) for key, value in scopes.items()},
            ))
        return cls(entries)

    def get(self, session: str) -> SessionEntry:
        for entry in self.entries:
            if entry.session == session:
                return entry
        raise KeyError(f"session not discovered: {session}")

    def previous_eligible(self, session: str, count: int) -> tuple[SessionEntry, ...]:
        if count <= 0:
            raise ValueError("count must be positive")
        current = date.fromisoformat(session)
        eligible = [
            entry for entry in self.entries
            if entry.eligible and date.fromisoformat(entry.session) < current
        ]
        return tuple(eligible[-count:])

    def to_dict(self) -> dict:
        return {
            "schema": "NEW_DIVERGENCE_SESSION_CATALOG_V1",
            "sessions": [entry.to_dict() for entry in self.entries],
            "session_count": len(self.entries),
            "eligible_count": sum(entry.eligible for entry in self.entries),
        }

    def write(self, path: Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        raw = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
