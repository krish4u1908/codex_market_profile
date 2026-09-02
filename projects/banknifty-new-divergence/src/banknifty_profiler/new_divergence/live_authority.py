"""Durable, single-session calculation authority for read-only live monitoring."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Iterable, Mapping

from .clock import iso_utc, parse_instant
from .contracts import EngineConfig, MarketEvent
from .engine import CausalDivergenceEngine
from .ledger import canonical_json
from .provenance import RUNTIME_VERSION
from .projection import confirmed_zones
from .scenario import inventory_scenario
from .live_profile import live_profile_projection


def _record_hash(previous: str, payload: Mapping[str, object]) -> str:
    return hashlib.sha256(f"{previous}\n{canonical_json(payload)}".encode()).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class LiveAuthority:
    """Own one monotonic event stream, engine instance, and SSE sequence."""

    def __init__(self, state_root: Path, session: date, config: EngineConfig | None = None):
        self.root = Path(state_root).resolve() / session.isoformat()
        self.root.mkdir(parents=True, exist_ok=True)
        self.session = session
        self.config = config or EngineConfig()
        self.events_path = self.root / "events.jsonl"
        self.publications_path = self.root / "publications.jsonl"
        self.checkpoint_path = self.root / "checkpoint.json"
        self.engine = CausalDivergenceEngine(self.config)
        self.events: list[MarketEvent] = []
        self.publications: list[dict[str, object]] = []
        self.pending: list[MarketEvent] = []
        self.source_offsets: dict[str, object] = {}
        self.status = "RECOVERING"
        self.recovery_mode = "NOT_RECOVERED"
        self._event_ids: set[str] = set()
        self._pending_ids: set[str] = set()
        self._event_hash = ""
        self._publication_hash = ""
        self._sequence = 0
        self._profile_cache_sequence = -1
        self._profile_cache: dict[str, object] | None = None
        self._last_sort_key: tuple | None = None
        self._condition = threading.Condition(threading.RLock())

    def _read_chain(self, path: Path, kind: str) -> list[dict[str, object]]:
        if not path.exists():
            return []
        result: list[dict[str, object]] = []
        previous = ""
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                payload = row.get("payload")
                if not isinstance(payload, dict) or row.get("previous_hash", "") != previous:
                    raise ValueError(f"invalid {kind} journal chain at line {number}")
                expected = _record_hash(previous, payload)
                if row.get("record_hash") != expected:
                    raise ValueError(f"invalid {kind} journal hash at line {number}")
                previous = expected
                result.append(row)
        return result

    def recover(self) -> dict[str, object]:
        with self._condition:
            event_rows = self._read_chain(self.events_path, "event")
            publication_rows = self._read_chain(self.publications_path, "publication")
            if len(event_rows) != len(publication_rows):
                raise ValueError("live event/publication journal counts differ")
            self.engine = CausalDivergenceEngine(self.config)
            self.events = []
            self._event_ids = set()
            self._last_sort_key = None
            for sealed in event_rows:
                event = MarketEvent.from_dict(sealed["payload"])
                if event.session != self.session:
                    raise ValueError("live journal session mismatch")
                self.engine.ingest(event)
                self.events.append(event)
                self._event_ids.add(event.event_id)
                self._last_sort_key = event.sort_key
            self.publications = [dict(row["payload"]) for row in publication_rows]
            sequences = [int(row.get("sequence", -1)) for row in self.publications]
            if sequences != list(range(1, len(sequences) + 1)):
                raise ValueError("live publication sequence is not contiguous")
            self._event_hash = "" if not event_rows else str(event_rows[-1]["record_hash"])
            self._publication_hash = "" if not publication_rows else str(publication_rows[-1]["record_hash"])
            self._sequence = len(self.publications)
            self._profile_cache_sequence = -1
            self._profile_cache = None
            self.pending = []
            self._pending_ids = set()
            self.source_offsets = {}
            mode = "VERIFIED_JOURNAL_RECONSTRUCTION"
            if self.checkpoint_path.exists():
                checkpoint = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                verified = (
                    checkpoint.get("schema") == "NEW_DIVERGENCE_LIVE_CHECKPOINT_V1"
                    and checkpoint.get("event_hash") == self._event_hash
                    and checkpoint.get("publication_hash") == self._publication_hash
                    and int(checkpoint.get("sequence", -1)) == self._sequence
                )
                if verified:
                    pending = [MarketEvent.from_dict(row) for row in checkpoint.get("pending", [])]
                    if any(row.session != self.session for row in pending):
                        raise ValueError("checkpoint pending-event session mismatch")
                    self.pending = sorted(pending, key=lambda row: row.sort_key)
                    self._pending_ids = {row.event_id for row in self.pending}
                    self.source_offsets = dict(checkpoint.get("source_offsets", {}))
                    mode = "CHECKPOINT_VERIFIED"
            self.recovery_mode = mode
            self.status = "CATCHING_UP"
            self._write_checkpoint()
            return {"mode": mode, "events": len(self.events), "pending": len(self.pending), "sequence": self._sequence}

    def _append(self, path: Path, payload: Mapping[str, object], previous: str) -> str:
        digest = _record_hash(previous, payload)
        row = {"payload": payload, "previous_hash": previous, "record_hash": digest}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return digest

    def _write_checkpoint(self) -> None:
        _atomic_json(self.checkpoint_path, {
            "schema": "NEW_DIVERGENCE_LIVE_CHECKPOINT_V1",
            "runtime_version": RUNTIME_VERSION,
            "session": self.session.isoformat(),
            "event_hash": self._event_hash,
            "publication_hash": self._publication_hash,
            "sequence": self._sequence,
            "source_offsets": self.source_offsets,
            "pending": [row.to_dict() for row in self.pending],
            "status": self.status,
        })

    def stage(self, events: Iterable[MarketEvent], offsets: Mapping[str, object]) -> int:
        with self._condition:
            accepted = 0
            for event in events:
                if event.session != self.session:
                    raise ValueError("live source session mismatch")
                if event.event_id in self._event_ids or event.event_id in self._pending_ids:
                    continue
                self.pending.append(event)
                self._pending_ids.add(event.event_id)
                accepted += 1
            self.pending.sort(key=lambda row: row.sort_key)
            self.source_offsets = dict(offsets)
            self._write_checkpoint()
            return accepted

    def commit_ready(self, through: datetime | str | None = None, *, flush: bool = False) -> int:
        cutoff = None if flush else parse_instant(through, field="live commit cutoff")
        committed = 0
        with self._condition:
            while self.pending and (cutoff is None or self.pending[0].receipt_timestamp <= cutoff):
                event = self.pending[0]
                if self._last_sort_key is not None and event.sort_key < self._last_sort_key:
                    raise ValueError(f"late live event precedes committed watermark: {event.event_id}")
                self.pending.pop(0)
                self._pending_ids.remove(event.event_id)
                before_observations = len(self.engine.observations)
                before_evidence = len(self.engine.evidence_snapshots)
                transitions = self.engine.ingest(event)
                self._event_hash = self._append(self.events_path, event.to_dict(), self._event_hash)
                self.events.append(event)
                self._event_ids.add(event.event_id)
                self._last_sort_key = event.sort_key
                self._sequence += 1
                publication = {
                    "schema": "NEW_DIVERGENCE_LIVE_EVENT_V1",
                    "sequence": self._sequence,
                    "published_at": iso_utc(event.receipt_timestamp),
                    "event": event.to_dict(),
                    "basis_observation": None if len(self.engine.observations) == before_observations else self.engine.observations[-1].to_dict(),
                    "evidence": None if len(self.engine.evidence_snapshots) == before_evidence else self.engine.evidence_snapshots[-1].to_dict(),
                    "transitions": [row.to_dict() for row in transitions],
                }
                self._publication_hash = self._append(
                    self.publications_path, publication, self._publication_hash
                )
                self.publications.append(publication)
                committed += 1
            self.status = "LIVE"
            self._write_checkpoint()
            if committed:
                self._condition.notify_all()
        return committed

    def set_status(self, status: str) -> None:
        with self._condition:
            self.status = str(status)
            self._write_checkpoint()
            self._condition.notify_all()

    def after(self, sequence: int) -> list[dict[str, object]]:
        with self._condition:
            return [dict(row) for row in self.publications if int(row["sequence"]) > sequence]

    def wait_after(self, sequence: int, timeout: float = 15.0) -> list[dict[str, object]]:
        with self._condition:
            rows = self.after(sequence)
            if not rows:
                self._condition.wait(timeout)
                rows = self.after(sequence)
            return rows

    def snapshot(self) -> dict[str, object]:
        with self._condition:
            observations = [row.to_dict() for row in self.engine.observations]
            evidence = [row.to_dict() for row in self.engine.evidence_snapshots]
            transitions = [row.to_dict() for row in self.engine.transitions]
            if self._profile_cache is None or self._profile_cache_sequence != self._sequence:
                self._profile_cache = live_profile_projection(
                    self.events, observations, evidence,
                    session=self.session, config=self.config,
                )
                self._profile_cache_sequence = self._sequence
            profile = dict(self._profile_cache)
            return {
                "schema": "NEW_DIVERGENCE_LIVE_SNAPSHOT_V1",
                "runtime_version": RUNTIME_VERSION,
                "session": self.session.isoformat(),
                "status": self.status,
                "recovery_mode": self.recovery_mode,
                "sequence": self._sequence,
                "server_time": iso_utc(datetime.now().astimezone()),
                "events": [row.to_dict() for row in self.events],
                "observations": observations,
                "evidence": evidence,
                "transitions": transitions,
                "confirmed_zones": confirmed_zones(transitions),
                "profile": profile,
                "pending_count": len(self.pending),
                "source_offsets": dict(self.source_offsets),
                "production_weight": self.config.production_weight,
            }

    def status_snapshot(self) -> dict[str, object]:
        """Return operational state without projecting or serializing the day."""
        with self._condition:
            return {
                "session": self.session.isoformat(),
                "status": self.status,
                "recovery_mode": self.recovery_mode,
                "sequence": self._sequence,
                "server_time": iso_utc(datetime.now().astimezone()),
                "pending_count": len(self.pending),
            }

    def _profile_locked(self) -> dict[str, object]:
        observations = [row.to_dict() for row in self.engine.observations]
        evidence = [row.to_dict() for row in self.engine.evidence_snapshots]
        if self._profile_cache is None or self._profile_cache_sequence != self._sequence:
            self._profile_cache = live_profile_projection(
                self.events, observations, evidence,
                session=self.session, config=self.config,
            )
            self._profile_cache_sequence = self._sequence
        return dict(self._profile_cache)

    def profile_snapshot(self) -> dict[str, object]:
        """Return only the live profile contract used by the polling endpoint."""
        with self._condition:
            profile = self._profile_locked()
            return {
                "session": self.session.isoformat(),
                "sequence": self._sequence,
                "profile": profile,
                "backend_scenario": self._scenario_locked(profile),
            }

    def _scenario_locked(self, profile: dict[str, object]) -> dict[str, object]:
        observations = [row.to_dict() for row in self.engine.observations[-1200:]]
        return inventory_scenario({
            "causal_as_of": observations[-1]["timestamp"] if observations else None,
            "recent_market": observations,
            "recent_futures_oi": profile.get("futures_oi", []),
            "recent_futures_volume_minutes": profile.get("futures_volume_minutes", []),
            "visible_intraday_inventory": profile.get("visible_intraday_inventory", {}),
            "recent_intraday_inventory_shifts": profile.get("recent_intraday_inventory_shifts", {}),
        })

    @staticmethod
    def _sample(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        if limit <= 0:
            return []
        if limit == 1:
            return rows[-1:]
        if len(rows) <= limit:
            return rows
        indices = {0, len(rows) - 1}
        for step in range(1, limit - 1):
            indices.add(round(step * (len(rows) - 1) / (limit - 1)))
        return [rows[index] for index in sorted(indices)]

    def browser_snapshot(self, *, observation_limit: int | None = 4000) -> dict[str, object]:
        """Return a bounded mobile bootstrap or the complete desktop history."""
        with self._condition:
            observations = [row.to_dict() for row in self.engine.observations]
            evidence = [row.to_dict() for row in self.engine.evidence_snapshots]
            transitions = [row.to_dict() for row in self.engine.transitions]
            profile = self._profile_locked()
            return {
                "schema": "NEW_DIVERGENCE_LIVE_BROWSER_SNAPSHOT_V1",
                "runtime_version": RUNTIME_VERSION,
                "session": self.session.isoformat(),
                "status": self.status,
                "recovery_mode": self.recovery_mode,
                "sequence": self._sequence,
                "server_time": iso_utc(datetime.now().astimezone()),
                "events": [],
                "observations": (
                    observations if observation_limit is None
                    else self._sample(observations, observation_limit)
                ),
                "observation_count": len(observations),
                "observations_sampled": (
                    observation_limit is not None
                    and len(observations) > observation_limit
                ),
                "evidence": evidence[-1:],
                "transitions": transitions[-50:],
                "confirmed_zones": confirmed_zones(transitions),
                "profile": profile,
                "backend_scenario": self._scenario_locked(profile),
                "pending_count": len(self.pending),
                "production_weight": self.config.production_weight,
            }

    def observation_history(self, *, before: int, limit: int) -> dict[str, object]:
        """Return an exact older observation slice for progressive browser hydration.

        ``before`` is an exclusive observation offset captured from the initial
        snapshot. Appending live observations does not move any older offsets.
        """
        with self._condition:
            total = len(self.engine.observations)
            end = max(0, min(before, total))
            start = max(0, end - limit)
            rows = [row.to_dict() for row in self.engine.observations[start:end]]
            return {
                "schema": "NEW_DIVERGENCE_LIVE_OBSERVATION_HISTORY_V1",
                "session": self.session.isoformat(),
                "start": start,
                "end": end,
                "total": total,
                "complete": start == 0,
                "observations": rows,
            }

    def commentary_snapshot(self) -> dict[str, object]:
        """Return the bounded causal prefix required by central commentary."""
        with self._condition:
            return {
                "session": self.session.isoformat(),
                "sequence": self._sequence,
                "server_time": iso_utc(datetime.now().astimezone()),
                "events": [row.to_dict() for row in self.events[-20:]],
                "observations": [row.to_dict() for row in self.engine.observations[-1200:]],
                "evidence": [row.to_dict() for row in self.engine.evidence_snapshots[-1:]],
                "transitions": [row.to_dict() for row in self.engine.transitions[-12:]],
                "profile": self._profile_locked(),
            }
