"""Replay and live adapters over one normalized event contract."""

from __future__ import annotations

import csv
import heapq
import json
from pathlib import Path
from typing import Iterable, Iterator

from .clock import parse_instant
from .contracts import MarketEvent


def load_events(path: Path) -> list[MarketEvent]:
    """Load normalized JSONL or CSV without inferring missing clocks."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".jsonl":
        rows = []
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(MarketEvent.from_dict(json.loads(line)))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise ValueError(f"invalid normalized event at {source}:{line_number}") from error
        return rows
    if source.suffix.lower() == ".csv":
        with source.open(newline="", encoding="utf-8") as handle:
            return [MarketEvent.from_dict(row) for row in csv.DictReader(handle)]
    raise ValueError(f"unsupported normalized event file: {source}")


class ReplayAdapter:
    """Deterministic receipt-ordered view over immutable source events."""

    def __init__(self, events: Iterable[MarketEvent]):
        materialized = list(events)
        identifiers = [event.event_id for event in materialized]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate event_id in replay input")
        sessions = {event.session for event in materialized}
        if len(sessions) > 1:
            raise ValueError("one ReplayAdapter may contain only one exchange session")
        self._events = tuple(sorted(materialized, key=lambda event: event.sort_key))

    @property
    def events(self) -> tuple[MarketEvent, ...]:
        return self._events

    def stream(self, *, as_of=None) -> Iterator[MarketEvent]:
        cutoff = None if as_of is None else parse_instant(as_of, field="replay as_of")
        for event in self._events:
            if cutoff is not None and event.receipt_timestamp > cutoff:
                break
            yield event

    def event_times(self) -> tuple:
        return tuple(event.receipt_timestamp for event in self._events)


class LiveAdapter:
    """In-memory receipt-order adapter for shadow-live integration.

    It accepts the same :class:`MarketEvent` objects as replay.  A bounded
    reordering window may be used before records are emitted.  Anything older
    than the already-emitted watermark is refused instead of backdated.
    """

    def __init__(self, *, reorder_seconds: float = 0.0):
        if reorder_seconds < 0:
            raise ValueError("reorder_seconds must be non-negative")
        self.reorder_seconds = float(reorder_seconds)
        self._heap: list[tuple] = []
        self._seen: set[str] = set()
        self._watermark = None
        self.refusals: list[dict[str, str]] = []

    def ingest(self, event: MarketEvent) -> bool:
        if event.event_id in self._seen:
            self.refusals.append({"event_id": event.event_id, "reason": "DUPLICATE_EVENT_ID"})
            return False
        if self._watermark is not None and event.receipt_timestamp < self._watermark:
            self.refusals.append({"event_id": event.event_id, "reason": "OUT_OF_ORDER_RECEIPT"})
            return False
        self._seen.add(event.event_id)
        heapq.heappush(self._heap, (event.sort_key, event))
        return True

    def drain(self, *, through=None, flush: bool = False) -> list[MarketEvent]:
        if not self._heap:
            return []
        if flush:
            cutoff = None
        elif through is not None:
            cutoff = parse_instant(through, field="live drain cutoff")
        else:
            newest = max(item[1].receipt_timestamp for item in self._heap)
            from datetime import timedelta

            cutoff = newest - timedelta(seconds=self.reorder_seconds)
        result = []
        while self._heap and (cutoff is None or self._heap[0][1].receipt_timestamp <= cutoff):
            _, event = heapq.heappop(self._heap)
            if self._watermark is not None and event.receipt_timestamp < self._watermark:
                self.refusals.append({"event_id": event.event_id, "reason": "OUT_OF_ORDER_RECEIPT"})
                continue
            self._watermark = event.receipt_timestamp
            result.append(event)
        return result
