from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any
from zoneinfo import ZoneInfo

from banknifty_profiler.runtime.timestamps import parse_timestamp
from banknifty_profiler.shadow.ledger import AppendOnlyLedger, atomic_json
from banknifty_profiler.shadow.observation import TypedObservation
from banknifty_profiler.shadow.symbols import (
    InstrumentClass,
    SymbolClassification,
    SymbolRegistry,
    normalize_expiry,
)


IST = ZoneInfo("Asia/Kolkata")
_OBSERVED_CLASSES = {
    InstrumentClass.INDEX.value,
    InstrumentClass.FUTURES.value,
    InstrumentClass.FUTURES_OI.value,
    InstrumentClass.CE.value,
    InstrumentClass.PE.value,
}
_MARKET_PAYLOAD_FIELDS = (
    "type", "ltp", "vol_traded_today", "last_traded_qty",
    "bid_price", "ask_price", "bid_price1", "ask_price1",
)
_OI_PAYLOAD_FIELDS = (
    "ltp", "volume", "v", "oi", "prev_oi", "pdoi", "oich", "strike_price",
    "option_type", "expiry", "bid", "ask", "ltpch", "ltt",
)


def now() -> str:
    return datetime.now(IST).isoformat()


def event_id(kind: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:24].upper()
    return f"{kind}-{digest}"


def _committed_prefix_fingerprint(path: Path, offset: int) -> str:
    """Bounded fingerprint for an already committed immutable prefix.

    The persisted mtime detects ordinary same-inode rewrites.  Head, midpoint
    and tail content make that identity independently content-backed without
    rescanning a multi-GB growing file on every poll.
    """
    window = 4096
    digest = hashlib.sha256()
    digest.update(str(offset).encode())
    if offset <= 0:
        return digest.hexdigest()
    with path.open("rb") as handle:
        _update_committed_prefix_fingerprint(digest, handle, offset, window)
    return digest.hexdigest()


def _committed_prefix_fingerprint_from_handle(handle, offset: int) -> str:
    window = 4096
    digest = hashlib.sha256()
    digest.update(str(offset).encode())
    if offset > 0:
        _update_committed_prefix_fingerprint(digest, handle, offset, window)
    return digest.hexdigest()


def _update_committed_prefix_fingerprint(
    digest, handle, offset: int, window: int,
) -> None:
    handle.seek(0)
    digest.update(handle.read(min(window, offset)))
    if offset > window * 2:
        middle_start = max(0, (offset // 2) - (window // 2))
        handle.seek(middle_start)
        digest.update(handle.read(min(window, offset - middle_start)))
    if offset > window:
        handle.seek(max(0, offset - window))
        digest.update(handle.read(min(window, offset)))


def _exact_range_fingerprint(path: Path, start: int, end: int) -> str:
    """Hash a bounded byte range exactly.

    Selection look-ahead is capped by ``selection_probe_budget``, so retaining
    an exact identity for its incomplete tail is bounded.  This lets an
    unchanged restart avoid opening the raw source while still failing closed
    if those already-inspected bytes are rewritten before an append.
    """
    if start < 0 or end < start:
        raise ValueError("invalid fingerprint range")
    digest = hashlib.sha256()
    remaining = end - start
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining:
            payload = handle.read(min(65_536, remaining))
            if not payload:
                raise ValueError("source changed while hashing inspected range")
            digest.update(payload)
            remaining -= len(payload)
    return digest.hexdigest()


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _oi_change(current: int | float | None, previous: int | float | None, explicit: object) -> int | float | None:
    supplied = _number(explicit)
    if supplied is not None:
        return supplied
    if current is None or previous is None:
        return None
    return current - previous


def _quote_price(item: dict[str, Any], side: str) -> int | float | None:
    """Return the best allow-listed quote from collector market/depth shapes."""
    direct = item.get(side)
    if isinstance(direct, list):
        for level in direct:
            if isinstance(level, dict):
                value = _number(level.get("price"))
                if value is not None:
                    return value
        direct = None
    value = _number(direct)
    if value is not None:
        return value
    prefix = "bid" if side in {"bid", "bids"} else "ask"
    for name in (f"{prefix}_price1", f"{prefix}_price"):
        value = _number(item.get(name))
        if value is not None:
            return value
    return None


class IncrementalJSONLIngestor:
    """Checkpoint growing JSONL files and emit typed observations causally."""

    _INTEGRITY_BLOCK_BYTES = 65_536

    def __init__(
        self,
        contract: dict[str, Any],
        on_observation: Callable[[TypedObservation], object] | object | None = None,
    ):
        self.c = contract
        self.data = contract["data_root"]
        self.state = contract["state_root"]
        self.state.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.state / "checkpoints.json"
        self.checkpoints = self._load_checkpoints()
        self.buffer_limit = int(contract["config"]["max_buffer_bytes_per_file"])
        self.read_limit = int(contract["config"]["max_read_bytes_per_file_per_poll"])
        self.symbols = SymbolRegistry(
            contract.get("selected_futures_symbols"),
            contract["config"].get("selected_futures_by_session"),
        )
        ledger_names = (
            "raw_file_checkpoints", "divergence_confirmations", "dependency_retriggers",
            "lifecycle_transitions", "inventory_winner_transitions", "participation_transitions",
            "cross_layer_transitions", "availability_transitions", "stale_recovery_transitions",
            "refusals_data_quality", "normalized_raw_events",
        )
        self.ledgers = {
            name: AppendOnlyLedger(self.state / "ledgers" / f"{name}.jsonl")
            for name in ledger_names
        }
        normalized_rows = self.ledgers["normalized_raw_events"].rows()
        self._normalized_seen = {row.get("event_id") for row in normalized_rows}
        self._normalized_out_of_order = {
            row.get("event_id"): bool(row.get("out_of_order"))
            for row in normalized_rows
        }
        self._quality_seen = {
            row.get("event_id") for row in self.ledgers["refusals_data_quality"].rows()
        }
        self._checkpoint_seen = {
            row.get("event_id") for row in self.ledgers["raw_file_checkpoints"].rows()
        }
        self._quality_pending: list[dict[str, Any]] = []
        self._quality_pending_ids: set[str] = set()
        self._checkpoint_pending: list[dict[str, Any]] = []
        self._checkpoint_dirty = False
        self.db = sqlite3.connect(self.state / "dedup.sqlite3")
        self.db.execute("create table if not exists seen(id text primary key)")
        self.db.execute("create table if not exists runtime_meta(key text primary key,value text not null)")
        persisted_run = self.db.execute(
            "select value from runtime_meta where key='raw_run_id'"
        ).fetchone()
        if persisted_run is None:
            self.db.execute(
                "insert into runtime_meta(key,value) values ('raw_run_id',?)",
                (str(self.c["raw_run_id"]),),
            )
        else:
            # A process restart continues the same durable raw run.  Generating
            # a fresh UUID would split one exactly-once publication history.
            self.c["raw_run_id"] = persisted_run[0]
        self.db.execute(
            "create table if not exists observation_outbox("
            "id text primary key,payload text not null)"
        )
        self.db.execute(
            "create table if not exists futures_candidate_outbox("
            "id text primary key,session_date text not null,"
            "receipt_timestamp text,payload text not null)"
        )
        candidate_columns = {
            row[1]
            for row in self.db.execute("pragma table_info(futures_candidate_outbox)")
        }
        if "receipt_timestamp" not in candidate_columns:
            self.db.execute(
                "alter table futures_candidate_outbox add column receipt_timestamp text"
            )
        # Older replay state predates the causal candidate-watermark column.
        # Populate it once from the durable payload rather than reparsing every
        # unresolved candidate on every live poll.
        for candidate_id, payload in self.db.execute(
            "select id,payload from futures_candidate_outbox "
            "where receipt_timestamp is null"
        ).fetchall():
            receipt = TypedObservation(**json.loads(payload)).receipt_timestamp
            self.db.execute(
                "update futures_candidate_outbox set receipt_timestamp=? where id=?",
                (receipt, candidate_id),
            )
        self.db.execute(
            "create index if not exists futures_candidate_receipt "
            "on futures_candidate_outbox(receipt_timestamp)"
        )
        self.db.execute(
            "create table if not exists futures_selection_probe("
            "source_file text primary key,session_date text not null,"
            "start_offset integer not null,probe_offset integer not null,"
            "identity text not null,prefix_fingerprint text not null,"
            "mtime_ns_at_probe integer not null,replay_target integer,"
            "bytes_consumed integer not null default 0,"
            "inspected_offset integer not null default 0,"
            "inspected_fingerprint text not null default '',"
            "size_at_probe integer not null default -1,"
            "authority_fingerprint text not null default '')"
        )
        probe_columns = {
            row[1]
            for row in self.db.execute("pragma table_info(futures_selection_probe)")
        }
        if "bytes_consumed" not in probe_columns:
            self.db.execute(
                "alter table futures_selection_probe "
                "add column bytes_consumed integer not null default 0"
            )
            self.db.execute(
                "update futures_selection_probe set bytes_consumed="
                "max(probe_offset-start_offset,0)"
            )
        inspected_schema_added = False
        if "inspected_offset" not in probe_columns:
            self.db.execute(
                "alter table futures_selection_probe "
                "add column inspected_offset integer not null default 0"
            )
            inspected_schema_added = True
        if "inspected_fingerprint" not in probe_columns:
            self.db.execute(
                "alter table futures_selection_probe "
                "add column inspected_fingerprint text not null default ''"
            )
            inspected_schema_added = True
        authority_schema_added = False
        if "size_at_probe" not in probe_columns:
            self.db.execute(
                "alter table futures_selection_probe "
                "add column size_at_probe integer not null default -1"
            )
            authority_schema_added = True
        if "authority_fingerprint" not in probe_columns:
            self.db.execute(
                "alter table futures_selection_probe "
                "add column authority_fingerprint text not null default ''"
            )
            authority_schema_added = True
        if inspected_schema_added or authority_schema_added:
            # The old implementation could charge one static tail repeatedly,
            # so bytes_consumed cannot prove how far it was actually inspected.
            # Reset unselected legacy probes to their durable complete-line
            # cursor and reparse from there once.  A selected legacy authority
            # retains its target but is refused below because it has no exact
            # authority identity.
            rows = self.db.execute(
                "select source_file,start_offset,probe_offset,replay_target "
                "from futures_selection_probe"
            ).fetchall()
            empty_fingerprint = hashlib.sha256(b"").hexdigest()
            for rel, start, probe_offset, replay_target in rows:
                reset_offset = (
                    int(start) if replay_target is None else int(probe_offset)
                )
                path = self.data / str(rel)
                prefix_fingerprint = ""
                mtime_ns = 0
                size_at_probe = -1
                if replay_target is None and path.is_file():
                    prefix_fingerprint = _committed_prefix_fingerprint(
                        path, reset_offset,
                    )
                    stat = path.stat()
                    mtime_ns = stat.st_mtime_ns
                    size_at_probe = stat.st_size
                self.db.execute(
                    "update futures_selection_probe set inspected_offset=?,"
                    "inspected_fingerprint=?,probe_offset=?,bytes_consumed=?,"
                    "prefix_fingerprint=?,mtime_ns_at_probe=?,size_at_probe=?,"
                    "authority_fingerprint=? "
                    "where source_file=?",
                    (
                        reset_offset,
                        empty_fingerprint,
                        reset_offset,
                        max(0, reset_offset - int(start)),
                        prefix_fingerprint,
                        mtime_ns,
                        size_at_probe,
                        empty_fingerprint,
                        str(rel),
                    ),
                )
        self.db.execute(
            "create table if not exists quarantined_source("
            "source_file text primary key,session_date text not null,"
            "reason text not null,expected_identity text not null,"
            "expected_offset integer not null,expected_fingerprint text not null,"
            "detected_identity text not null,detected_size integer not null,"
            "invalidates_selection integer not null,detected_at text not null)"
        )
        self.db.execute(
            "create table if not exists file_prefix_block("
            "source_file text not null,block_index integer not null,"
            "byte_count integer not null,digest text not null,"
            "primary key(source_file,block_index))"
        )
        self.db.execute(
            "create table if not exists file_integrity_scrub("
            "source_file text primary key,next_block integer not null default 0,"
            "updated_at text not null)"
        )
        self.db.execute(
            "create table if not exists unknown_symbol_audit("
            "session_date text not null,source_symbol text not null,reason text not null,"
            "observation_count integer not null,first_receipt text not null,last_receipt text not null,"
            "first_source_file text not null,first_byte_offset integer not null,first_source_row integer not null,"
            "last_source_file text not null,last_byte_offset integer not null,last_source_row integer not null,"
            "primary key(session_date,source_symbol,reason))"
        )
        self.db.execute(
            "create table if not exists file_checkpoint("
            "source_file text primary key,offset integer not null,row_number integer not null,"
            "identity text not null,size_at_commit integer not null,updated_at text not null,"
            "frontier text,prefix_fingerprint text not null default '',"
            "mtime_ns_at_commit integer not null default 0)"
        )
        checkpoint_columns = {
            row[1] for row in self.db.execute("pragma table_info(file_checkpoint)")
        }
        if "prefix_fingerprint" not in checkpoint_columns:
            self.db.execute(
                "alter table file_checkpoint add column prefix_fingerprint text not null default ''"
            )
        if "mtime_ns_at_commit" not in checkpoint_columns:
            self.db.execute(
                "alter table file_checkpoint add column mtime_ns_at_commit integer not null default 0"
            )
        for rel, checkpoint in self.checkpoints.items():
            self.db.execute(
                "insert or ignore into file_checkpoint("
                "source_file,offset,row_number,identity,size_at_commit,updated_at,frontier,"
                "prefix_fingerprint,mtime_ns_at_commit) values (?,?,?,?,?,?,?,?,?)",
                (
                    rel, checkpoint.get("offset", 0), checkpoint.get("row", 0),
                    checkpoint.get("identity", ""), checkpoint.get("size_at_commit", 0),
                    checkpoint.get("updated_at", now()), None,
                    checkpoint.get("prefix_fingerprint", ""),
                    checkpoint.get("mtime_ns_at_commit", 0),
                ),
            )
        self.db.commit()
        self.checkpoints = {
            row[0]: {
                "offset": row[1], "row": row[2], "identity": row[3],
                "size_at_commit": row[4], "updated_at": row[5],
                "prefix_fingerprint": row[6], "mtime_ns_at_commit": row[7],
            }
            for row in self.db.execute(
                "select source_file,offset,row_number,identity,size_at_commit,updated_at,"
                "prefix_fingerprint,mtime_ns_at_commit "
                "from file_checkpoint"
            )
        }
        self.latest = {
            key.removeprefix("latest:"): value
            for key, value in self.db.execute(
                "select key,value from runtime_meta where key like 'latest:%'"
            )
        }
        self.latest_valid = {
            key.removeprefix("latest_valid:"): value
            for key, value in self.db.execute(
                "select key,value from runtime_meta where key like 'latest_valid:%'"
            )
        }
        high_water = self.db.execute(
            "select value from runtime_meta where key='causal_high_water'"
        ).fetchone()
        self._causal_high_water = high_water[0] if high_water else None
        self._selection_probe_exhausted = {
            key.removeprefix("selection_probe_exhausted:")
            for key, _ in self.db.execute(
                "select key,value from runtime_meta "
                "where key like 'selection_probe_exhausted:%'"
            )
        }
        self._quarantined_sources = {
            str(row[0]): {
                "session_date": str(row[1]),
                "reason": str(row[2]),
                "expected_identity": str(row[3]),
                "expected_offset": int(row[4]),
                "expected_fingerprint": str(row[5]),
                "detected_identity": str(row[6]),
                "detected_size": int(row[7]),
                "invalidates_selection": bool(row[8]),
                "detected_at": str(row[9]),
            }
            for row in self.db.execute(
                "select source_file,session_date,reason,expected_identity,"
                "expected_offset,expected_fingerprint,detected_identity,"
                "detected_size,invalidates_selection,detected_at "
                "from quarantined_source"
            )
        }
        for key, symbol in self.db.execute(
            "select key,value from runtime_meta where key like 'selected_futures:%'"
        ):
            self.symbols.selected_by_session[key.removeprefix("selected_futures:")] = frozenset((symbol,))
        self._stream_frontiers = {
            key.removeprefix("stream_frontier:"): value
            for key, value in self.db.execute(
                "select key,value from runtime_meta where key like 'stream_frontier:%'"
            )
        }
        self._stream_frontiers.update({
            rel: frontier
            for rel, frontier in self.db.execute(
                "select source_file,frontier from file_checkpoint where frontier is not null"
            )
        })
        self._poll_incomplete: dict[str, bool] = {}
        self._inflight: list[str] = []
        self._discovery_signature: tuple | None = None
        self._discovery_paths: tuple[Path, ...] = ()
        self.callbacks: list[tuple[str, Callable[..., object]]] = []
        if on_observation is not None:
            self.register_callback(on_observation)
        self.metrics = {
            "records": 0, "observations": 0, "duplicates": 0, "malformed": 0,
            "unknown_observations": 0, "deferred_lines": 0, "bytes": 0, "polls": 0,
            "projection_padding_lines": 0, "candidate_selection_lookahead_reads": 0,
            "candidate_selection_probe_bytes": 0,
            "candidate_selection_probe_refusals": 0,
            "candidate_source_quarantine_refusals": 0,
            "started": time.monotonic(), "max_buffer": 0,
        }
        self.selection_probe_budget = max(self.read_limit, self.buffer_limit)
        self._queue_quarantine_audits()

    def register_callback(self, callback: Callable[[TypedObservation], object] | object) -> None:
        registration = self._callback_registration(callback)
        if registration not in self.callbacks:
            self.callbacks.append(registration)

    @staticmethod
    def _callback_registration(callback: object) -> tuple[str, Callable[..., object]]:
        batch = getattr(callback, "process_observations", None)
        if callable(batch):
            return "batch", batch
        if callable(callback):
            return "single", callback
        handler = getattr(callback, "on_observation", None)
        if callable(handler):
            return "single", handler
        raise TypeError(
            "observation callback must be callable, expose on_observation, "
            "or expose process_observations"
        )

    add_callback = register_callback

    def _load_checkpoints(self) -> dict[str, dict[str, Any]]:
        if not self.checkpoint_path.exists():
            return {}
        try:
            return json.loads(self.checkpoint_path.read_text())
        except Exception as error:
            raise ValueError(f"checkpoint state corrupt: {error}") from error

    def discover(self) -> list[Path]:
        signature = self._directory_signature()
        if signature == self._discovery_signature:
            return list(self._discovery_paths)
        minimum = self.c.get("minimum_session_date", "")
        paths = [
            *self.data.glob("raw/*/events_*.jsonl"),
            *self.data.glob("oi/*/oi_*.jsonl"),
        ]
        self._discovery_paths = tuple(
            sorted(path for path in paths if path.parent.name >= minimum)
        )
        self._discovery_signature = signature
        return list(self._discovery_paths)

    def _directory_signature(self) -> tuple:
        """Detect session/hour rotation without globbing every file each poll."""
        minimum = self.c.get("minimum_session_date", "")
        values = []
        for kind in ("raw", "oi"):
            root = self.data / kind
            stat = root.stat()
            values.append((kind, stat.st_dev, stat.st_ino, stat.st_mtime_ns))
            for session in sorted(
                path for path in root.iterdir()
                if path.is_dir() and path.name >= minimum
            ):
                session_stat = session.stat()
                values.append((
                    kind, session.name, session_stat.st_dev,
                    session_stat.st_ino, session_stat.st_mtime_ns,
                ))
        return tuple(values)

    def _validated_source_paths(self, paths: Iterable[Path]) -> list[Path]:
        """Validate a caller-supplied changed-file hint for schedule replay."""
        result = []
        minimum = self.c.get("minimum_session_date", "")
        for value in paths:
            path = Path(value).resolve()
            try:
                relative = path.relative_to(self.data)
            except ValueError as error:
                raise ValueError("hinted source path is outside raw data root") from error
            parts = relative.parts
            valid_name = (
                len(parts) == 3
                and parts[0] in {"raw", "oi"}
                and parts[1] >= minimum
                and (
                    parts[0] == "raw" and parts[2].startswith("events_")
                    or parts[0] == "oi" and parts[2].startswith("oi_")
                )
                and parts[2].endswith(".jsonl")
            )
            if not valid_name or not path.is_file():
                raise ValueError(f"invalid hinted physical source path: {relative}")
            result.append(path)
        return sorted(set(result))

    def _classify(self, path: Path, record: dict[str, Any]) -> tuple[str, object]:
        """Compatibility classifier backed by the canonical registry."""
        receipt = record.get("received_at")
        if "/raw/" in str(path):
            symbol = record.get("message", {}).get("symbol", "")
            classification = self.symbols.classify(symbol, source_kind="market")
            return classification.instrument_class.value, receipt
        source = record.get("source")
        if source == "future_depth":
            return InstrumentClass.FUTURES_OI.value, receipt
        if source == "option_chain":
            return InstrumentClass.OPTION_OI.value, receipt
        return InstrumentClass.UNKNOWN_SYMBOL.value, receipt

    def poll(
        self,
        callback: Callable[[TypedObservation], object] | object | None = None,
        *,
        source_paths: Iterable[Path] | None = None,
    ) -> list[TypedObservation]:
        begun = time.monotonic()
        self.metrics["polls"] += 1
        # A no-callback poll hands observations to its caller.  Reaching the
        # next poll proves that hand-off returned; a clean close proves the
        # same.  Until then those rows remain a durable replayable outbox.
        self._acknowledge(self._inflight)
        self._inflight = []
        pending_before = self._pending_observations()
        pending_files = {observation.source_file for observation in pending_before}
        pending_files.update(
            json.loads(payload).get("source_file", "")
            for (payload,) in self.db.execute(
                "select payload from futures_candidate_outbox"
            )
        )
        self._quarantine_missing_probe_sources()
        self._quarantine_missing_candidate_sources()
        paths = (
            self.discover()
            if source_paths is None
            else self._validated_source_paths(source_paths)
        )
        self._poll_incomplete = {}
        for path in paths:
            rel = str(path.relative_to(self.data))
            parts = Path(rel).parts
            if rel in self._quarantined_sources:
                # A replaced/truncated source cannot contribute new canonical
                # evidence.  It is deliberately absent from the causal
                # watermark so one bad layer cannot freeze already-durable
                # Index observations or other valid sources forever.
                self._poll_incomplete[rel] = False
                continue
            if self._quarantine_changed_probe_replay(path):
                self._poll_incomplete[rel] = False
                continue
            if self._quarantine_changed_candidate_source(path):
                self._poll_incomplete[rel] = False
                continue
            # Contract discovery has its own bounded durable cursor.  It never
            # advances the primary OI checkpoint or stages option rows.  Once
            # depth selects a contract, primary ingestion replays every probed
            # byte before the raw Futures candidate can be released.
            selection_probe = (
                len(parts) == 3
                and parts[0] == "oi"
                and self._session_has_candidates(parts[1])
                and parts[1] not in self._selection_probe_exhausted
                and not self.symbols.selected_futures_for_session(parts[1])
            )
            replay_catchup = rel in self._selection_replay_sources()
            candidate_source_catchup = rel in self._selected_candidate_source_files()
            if selection_probe:
                self._probe_futures_selection(path, parts[1])
            elif rel in pending_files and not (
                replay_catchup or candidate_source_catchup
            ):
                checkpoint = self.checkpoints.get(rel, {"offset": 0})
                self._poll_incomplete[rel] = checkpoint.get("offset", 0) < path.stat().st_size
            else:
                self._read_file(path)
        if self._checkpoint_dirty:
            self._flush_checkpoints()
            atomic_json(self.checkpoint_path, self.checkpoints)
            self._checkpoint_dirty = False
        with self.db:
            self._retire_exhausted_candidates()
            self._release_selected_candidates(ready_only=True)
            self._cleanup_replayed_selection_probes()
        watermark = self._safe_watermark()
        candidate_barrier = self._unresolved_candidate_watermark()
        observations = self._pending_observations(
            watermark, exclusive_before=candidate_barrier
        )
        observations.sort(key=TypedObservation.causal_sort_key)

        committed: list[TypedObservation] = []
        provisional_high_water = self._causal_high_water
        for observation in observations:
            observation = self._mark_ordering(observation, provisional_high_water)
            if not observation.out_of_order and observation.status == "OBSERVED":
                if provisional_high_water is None or parse_timestamp(
                    observation.receipt_timestamp, field_name="provisional receipt timestamp"
                ) >= parse_timestamp(provisional_high_water, field_name="provisional high-water"):
                    provisional_high_water = observation.receipt_timestamp
            if observation.instrument_class == InstrumentClass.UNKNOWN_SYMBOL.value:
                self._quality(
                    "UNKNOWN_SYMBOL", observation.source_file, observation.source_row_number,
                    observation.source_byte_offset, observation.observation_id,
                    f"symbol={observation.source_symbol!r} classification={observation.classification_reason}",
                )
            committed.append(observation)
        self._flush_quality()
        self._ledger_observations(committed)

        handlers = list(self.callbacks)
        if callback is not None:
            handlers.append(self._callback_registration(callback))
        if handlers and committed:
            for mode, handler in handlers:
                if mode == "batch":
                    handler(committed)
                else:
                    for observation in committed:
                        handler(observation)
            self._advance_clocks(committed)
            self._persist_runtime_clocks()
            self._acknowledge([observation.observation_id for observation in committed])
        elif committed:
            self._advance_clocks(committed)
            self._persist_runtime_clocks()
            self._inflight = [observation.observation_id for observation in committed]
        self.metrics["observations"] += len(committed)
        self.metrics["last_poll_ms"] = (time.monotonic() - begun) * 1000
        return committed

    def _pending_observations(
        self,
        watermark: object = ...,
        *,
        exclusive_before: object | None = None,
    ) -> list[TypedObservation]:
        rows = self.db.execute("select payload from observation_outbox").fetchall()
        observations = [TypedObservation(**json.loads(payload)) for (payload,) in rows]
        if watermark is ...:
            eligible = observations
        elif watermark is None:
            return []
        else:
            eligible = [
                observation for observation in observations
                if parse_timestamp(
                    observation.receipt_timestamp,
                    field_name="outbox receipt watermark",
                ) <= watermark
            ]
        if exclusive_before is None:
            return eligible
        # An unresolved Futures candidate is not itself in observation_outbox.
        # Hold equal-clock rows as well as later rows so candidate release has
        # one deterministic causal tie-break opportunity on every schedule.
        return [
            observation for observation in eligible
            if parse_timestamp(
                observation.receipt_timestamp,
                field_name="unresolved candidate strict receipt barrier",
            ) < exclusive_before
        ]

    def _unresolved_candidate_watermark(self):
        candidate = self.db.execute(
            "select min(receipt_timestamp) from futures_candidate_outbox"
        ).fetchone()[0]
        return (
            parse_timestamp(
                candidate,
                field_name="unresolved futures candidate causal watermark",
            )
            if candidate is not None
            else None
        )

    def _safe_watermark(self):
        blocking = [
            rel for rel, incomplete in self._poll_incomplete.items() if incomplete
        ]
        if not blocking:
            return ...
        if any(rel not in self._stream_frontiers for rel in blocking):
            return None
        return min(
            parse_timestamp(
                self._stream_frontiers[rel],
                field_name="stream causal frontier",
            )
            for rel in blocking
        )

    def _selected_candidate_source_files(self) -> set[str]:
        result = set()
        for session, payload in self.db.execute(
            "select session_date,payload from futures_candidate_outbox"
        ):
            if self.symbols.selected_futures_for_session(session):
                result.add(str(json.loads(payload).get("source_file", "")))
        return result

    def _session_has_candidates(self, session: str) -> bool:
        return self.db.execute(
            "select 1 from futures_candidate_outbox where session_date=? limit 1",
            (session,),
        ).fetchone() is not None

    def _selection_authority_unreplayed(self, session: str) -> bool:
        return (
            self.db.execute(
                "select 1 from futures_selection_probe "
                "where session_date=? and replay_target is not null limit 1",
                (session,),
            ).fetchone() is not None
            and not self._selection_replay_ready(session)
        )

    def _quarantine_committed_source(
        self,
        path: Path,
        checkpoint: dict[str, Any],
        reason: str,
    ) -> None:
        rel = str(path.relative_to(self.data))
        session = Path(rel).parts[1]
        is_candidate_source = any(
            str(json.loads(payload).get("source_file", "")) == rel
            for (payload,) in self.db.execute(
                "select payload from futures_candidate_outbox "
                "where session_date=?",
                (session,),
            )
        )
        self._quarantine_source(
            path,
            session=session,
            reason=reason,
            expected_identity=str(checkpoint.get("identity", "")),
            expected_offset=int(checkpoint.get("offset", 0)),
            expected_fingerprint=str(checkpoint.get("prefix_fingerprint", "")),
            invalidates_selection=(
                is_candidate_source
                and self._selection_authority_unreplayed(session)
            ),
        )

    @staticmethod
    def _source_mutation_reason(
        path: Path,
        *,
        expected_identity: str,
        expected_offset: int,
        expected_fingerprint: str,
        expected_mtime_ns: int,
        expected_size_at_commit: int | None = None,
    ) -> str | None:
        stat = path.stat()
        identity = f"{stat.st_dev}:{stat.st_ino}"
        if identity != expected_identity:
            return "FILE_REPLACED"
        if stat.st_size < expected_offset:
            return "FILE_TRUNCATED"
        stat_changed = (
            expected_size_at_commit is None
            or stat.st_size != expected_size_at_commit
            or (
                expected_mtime_ns
                and stat.st_mtime_ns != expected_mtime_ns
            )
        )
        if stat_changed and expected_offset > 0 and expected_fingerprint:
            current = _committed_prefix_fingerprint(path, expected_offset)
            if current != expected_fingerprint:
                return "FILE_REPLACED_IN_PLACE"
            if (
                stat.st_size == expected_offset
                and expected_mtime_ns
                and stat.st_mtime_ns != expected_mtime_ns
            ):
                return "FILE_REPLACED_IN_PLACE"
        return None

    def _committed_source_mutation_reason(
        self,
        path: Path,
        rel: str,
        checkpoint: dict[str, Any],
    ) -> str | None:
        reason = self._source_mutation_reason(
            path,
            expected_identity=str(checkpoint.get("identity", "")),
            expected_offset=int(checkpoint.get("offset", 0)),
            expected_fingerprint=str(checkpoint.get("prefix_fingerprint", "")),
            expected_mtime_ns=int(checkpoint.get("mtime_ns_at_commit", 0) or 0),
            expected_size_at_commit=int(
                checkpoint.get("size_at_commit", 0) or 0
            ),
        )
        if reason is not None:
            return reason
        stat = path.stat()
        stat_changed = (
            stat.st_size != int(checkpoint.get("size_at_commit", 0) or 0)
            or (
                int(checkpoint.get("mtime_ns_at_commit", 0) or 0)
                and stat.st_mtime_ns
                != int(checkpoint.get("mtime_ns_at_commit", 0) or 0)
            )
        )
        committed_offset = int(checkpoint.get("offset", 0))
        scrub_exists = self.db.execute(
            "select 1 from file_integrity_scrub where source_file=?",
            (rel,),
        ).fetchone() is not None
        if committed_offset > 0 and (stat_changed or scrub_exists):
            # The rotating cursor advances on unchanged polls too.  A final
            # append must not be able to freeze the cursor forever immediately
            # after an unsampled old block was rewritten.  Work remains
            # bounded to the sentinels plus one 64-KiB block per poll.
            if self._bounded_prefix_block_integrity(
                path, rel, committed_offset,
            ) is not True:
                return "FILE_REPLACED_IN_PLACE"
        return None

    def _new_complete_prefix_blocks(
        self,
        path: Path,
        rel: str,
        committed_offset: int,
        *,
        handle=None,
    ) -> list[tuple[int, int, str]]:
        """Hash new blocks and refresh the bounded prior partial block."""
        block_count = (
            (int(committed_offset) + self._INTEGRITY_BLOCK_BYTES - 1)
            // self._INTEGRITY_BLOCK_BYTES
        )
        if block_count <= 0:
            return []
        existing = self.db.execute(
            "select block_index,byte_count from file_prefix_block "
            "where source_file=? order by block_index desc limit 1",
            (rel,),
        ).fetchone()
        if existing is None:
            start = 0
        elif int(existing[1]) < self._INTEGRITY_BLOCK_BYTES:
            start = int(existing[0])
        else:
            start = int(existing[0]) + 1
        if start >= block_count:
            return []
        def collect(source) -> list[tuple[int, int, str]]:
            rows: list[tuple[int, int, str]] = []
            for block_index in range(start, block_count):
                source.seek(block_index * self._INTEGRITY_BLOCK_BYTES)
                expected = min(
                    self._INTEGRITY_BLOCK_BYTES,
                    int(committed_offset)
                    - block_index * self._INTEGRITY_BLOCK_BYTES,
                )
                payload = source.read(expected)
                if len(payload) != expected:
                    raise ValueError(
                        f"source changed while hashing committed block: {rel}"
                    )
                rows.append((
                    block_index,
                    len(payload),
                    hashlib.sha256(payload).hexdigest(),
                ))
            return rows

        if handle is not None:
            return collect(handle)
        with path.open("rb") as source:
            return collect(source)

    def _bounded_prefix_block_integrity(
        self,
        path: Path,
        rel: str,
        committed_offset: int,
    ) -> bool | None:
        """Scrub bounded sentinels plus one durable rotating prefix block.

        Every committed block, including the prior partial tail, has a durable
        digest.  A changed-file poll checks
        the head, midpoint and tail blocks and advances one rotating block, so
        the reproduced middle rewrite is immediate while arbitrary corruption
        receives complete eventual coverage without a multi-hundred-MB rescan
        on every append.
        """
        block_count = (
            (int(committed_offset) + self._INTEGRITY_BLOCK_BYTES - 1)
            // self._INTEGRITY_BLOCK_BYTES
        )
        if block_count <= 0:
            return None
        count, minimum, maximum = self.db.execute(
            "select count(*),min(block_index),max(block_index) "
            "from file_prefix_block "
            "where source_file=? and block_index<?",
            (rel, block_count),
        ).fetchone()
        count = int(count)
        if count == 0:
            return None
        first_block = int(minimum)
        protected_count = block_count - first_block
        if (
            protected_count <= 0
            or count != protected_count
            or int(maximum) != block_count - 1
        ):
            return False
        scrub = self.db.execute(
            "select next_block from file_integrity_scrub where source_file=?",
            (rel,),
        ).fetchone()
        rotating = (
            first_block
            + ((int(scrub[0]) - first_block) % protected_count)
            if scrub
            else first_block
        )
        midpoint = min(
            block_count - 1,
            max(
                first_block,
                (int(committed_offset) // 2) // self._INTEGRITY_BLOCK_BYTES,
            ),
        )
        targets = sorted({first_block, midpoint, block_count - 1, rotating})
        expected = {
            int(block_index): (int(byte_count), str(digest))
            for block_index, byte_count, digest in self.db.execute(
                "select block_index,byte_count,digest from file_prefix_block "
                f"where source_file=? and block_index in ({','.join('?' for _ in targets)})",
                (rel, *targets),
            )
        }
        if set(expected) != set(targets):
            return False
        with path.open("rb") as handle:
            for block_index in targets:
                byte_count, digest = expected[block_index]
                handle.seek(block_index * self._INTEGRITY_BLOCK_BYTES)
                payload = handle.read(byte_count)
                if (
                    len(payload) != byte_count
                    or hashlib.sha256(payload).hexdigest() != digest
                ):
                    return False
        with self.db:
            self.db.execute(
                "insert into file_integrity_scrub(source_file,next_block,updated_at) "
                "values (?,?,?) on conflict(source_file) do update set "
                "next_block=excluded.next_block,updated_at=excluded.updated_at",
                (
                    rel,
                    first_block
                    + ((rotating - first_block + 1) % protected_count),
                    now(),
                ),
            )
        return True

    def _full_prefix_block_integrity(
        self,
        path: Path,
        rel: str,
        committed_offset: int,
    ) -> tuple[bool, int]:
        """Verify every committed block once at a session-seal boundary.

        Poll-time work deliberately remains bounded.  A finalized historical
        session, however, is a release/deployment boundary: all durable block
        identities are streamed exactly once so an arbitrary unsampled old
        rewrite cannot be promoted into a sealed replay.  The file must remain
        a stable, complete snapshot for the duration of this check.
        """
        committed_offset = int(committed_offset)
        block_count = (
            committed_offset + self._INTEGRITY_BLOCK_BYTES - 1
        ) // self._INTEGRITY_BLOCK_BYTES
        if block_count <= 0:
            return True, 0
        rows = self.db.execute(
            "select block_index,byte_count,digest from file_prefix_block "
            "where source_file=? order by block_index",
            (rel,),
        ).fetchall()
        if len(rows) != block_count:
            return False, 0
        before = path.stat()
        checkpoint = self.checkpoints.get(rel, {})
        if (
            f"{before.st_dev}:{before.st_ino}"
            != str(checkpoint.get("identity", ""))
            or before.st_size != committed_offset
        ):
            return False, 0
        verified = 0
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            ):
                return False, 0
            for expected_index, row in enumerate(rows):
                block_index, byte_count, digest = row
                expected_bytes = min(
                    self._INTEGRITY_BLOCK_BYTES,
                    committed_offset
                    - expected_index * self._INTEGRITY_BLOCK_BYTES,
                )
                if (
                    int(block_index) != expected_index
                    or int(byte_count) != expected_bytes
                    or not re.fullmatch(r"[0-9a-f]{64}", str(digest))
                ):
                    return False, verified
                payload = handle.read(expected_bytes)
                if (
                    len(payload) != expected_bytes
                    or hashlib.sha256(payload).hexdigest() != str(digest)
                ):
                    return False, verified
                verified += 1
            after_handle = os.fstat(handle.fileno())
        try:
            after_path = path.stat()
        except FileNotFoundError:
            return False, verified
        stable = (
            (after_handle.st_dev, after_handle.st_ino, after_handle.st_size,
             after_handle.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            and (after_path.st_dev, after_path.st_ino, after_path.st_size,
                 after_path.st_mtime_ns)
            == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        )
        return stable, verified

    def verify_committed_sources(
        self,
        session_dates: Iterable[str] | None = None,
    ) -> dict[str, int]:
        """Exhaustively bind finalized checkpoints to their source prefixes."""
        requested = set(map(str, session_dates or ()))
        checked_files = 0
        checked_blocks = 0
        failures: list[str] = []
        for rel, checkpoint in sorted(self.checkpoints.items()):
            parts = Path(rel).parts
            if len(parts) != 3 or (requested and parts[1] not in requested):
                continue
            checked_files += 1
            path = self.data / rel
            reason = None
            if rel in self._quarantined_sources or not path.is_file():
                reason = "FILE_REPLACED_IN_PLACE"
            else:
                reason = self._committed_source_mutation_reason(
                    path, rel, checkpoint,
                )
                if reason is None:
                    valid, blocks = self._full_prefix_block_integrity(
                        path, rel, int(checkpoint.get("offset", 0)),
                    )
                    checked_blocks += blocks
                    if not valid:
                        reason = "FILE_REPLACED_IN_PLACE"
            if reason is not None:
                if rel not in self._quarantined_sources:
                    self._quarantine_committed_source(path, checkpoint, reason)
                failures.append(rel)
        self._flush_quality()
        if failures:
            raise ValueError("committed source integrity verification failed")
        return {
            "source_files": checked_files,
            "prefix_blocks": checked_blocks,
        }

    def _quarantine_changed_probe_replay(self, path: Path) -> bool:
        """Reject a probe prefix that is no longer the primary replay source."""
        rel = str(path.relative_to(self.data))
        row = self.db.execute(
            "select session_date,start_offset,probe_offset,identity,"
            "prefix_fingerprint,mtime_ns_at_probe,replay_target,"
            "inspected_offset,size_at_probe,authority_fingerprint "
            "from futures_selection_probe "
            "where source_file=?",
            (rel,),
        ).fetchone()
        if row is None:
            return False
        (
            session, start_offset, probe_offset, identity, fingerprint,
            mtime_ns, replay_target, inspected_offset, size_at_probe,
            authority_fingerprint,
        ) = row
        target = int(replay_target) if replay_target is not None else int(probe_offset)
        primary_offset = int(
            self.checkpoints.get(rel, {"offset": 0}).get("offset", 0)
        )
        if replay_target is not None and primary_offset >= target:
            return False
        if int(size_at_probe) < 0 and replay_target is not None:
            self._quarantine_source(
                path,
                session=str(session),
                reason=(
                    "FUTURES_SELECTION_PROBE_"
                    "LEGACY_AUTHORITY_UNVERIFIABLE"
                ),
                expected_identity=str(identity),
                expected_offset=target,
                expected_fingerprint=str(authority_fingerprint),
                invalidates_selection=True,
            )
            return True
        stat = path.stat()
        stat_changed = (
            int(size_at_probe) < 0
            or stat.st_size != int(size_at_probe)
            or (int(mtime_ns) and stat.st_mtime_ns != int(mtime_ns))
        )
        reason = self._source_mutation_reason(
            path,
            expected_identity=str(identity),
            expected_offset=target,
            expected_fingerprint=str(fingerprint),
            expected_mtime_ns=int(mtime_ns),
            expected_size_at_commit=(
                int(size_at_probe) if int(size_at_probe) >= 0 else None
            ),
        )
        if (
            reason is None
            and stat_changed
            and target > int(start_offset)
            and _exact_range_fingerprint(path, int(start_offset), target)
            != str(authority_fingerprint)
        ):
            reason = "FILE_REPLACED_IN_PLACE"
        if reason is None:
            return False
        self._quarantine_source(
            path,
            session=str(session),
            reason=f"FUTURES_SELECTION_PROBE_{reason}",
            expected_identity=str(identity),
            expected_offset=target,
            expected_fingerprint=str(fingerprint),
            invalidates_selection=True,
        )
        return True

    def _quarantine_changed_candidate_source(self, path: Path) -> bool:
        """Retire a candidate whose already-checkpointed raw source mutated."""
        rel = str(path.relative_to(self.data))
        rows = self.db.execute(
            "select session_date,payload from futures_candidate_outbox"
        ).fetchall()
        sessions = {
            str(session)
            for session, payload in rows
            if str(json.loads(payload).get("source_file", "")) == rel
        }
        if not sessions:
            return False
        checkpoint = self.checkpoints.get(rel)
        if checkpoint is None:
            return False
        reason = self._committed_source_mutation_reason(path, rel, checkpoint)
        if reason is None:
            return False
        # A physical source belongs to exactly one session by validated path.
        session = next(iter(sessions))
        self._quarantine_source(
            path,
            session=session,
            reason=f"FUTURES_CANDIDATE_SOURCE_{reason}",
            expected_identity=str(checkpoint.get("identity", "")),
            expected_offset=int(checkpoint.get("offset", 0)),
            expected_fingerprint=str(checkpoint.get("prefix_fingerprint", "")),
            # A selection seen only by look-ahead cannot survive corruption
            # of the raw candidate path: otherwise a later raw hour could be
            # published before the selecting depth bytes were replayed.  A
            # selection whose OI authority was already replayed remains valid.
            invalidates_selection=not self._selection_replay_ready(session),
        )
        return True

    def _quarantine_missing_candidate_sources(self) -> None:
        rows = self.db.execute(
            "select session_date,payload from futures_candidate_outbox"
        ).fetchall()
        missing: dict[str, str] = {}
        for session, payload in rows:
            rel = str(json.loads(payload).get("source_file", ""))
            if rel and not (self.data / rel).is_file():
                missing.setdefault(rel, str(session))
        for rel, session in missing.items():
            checkpoint = self.checkpoints.get(rel, {})
            self._quarantine_source(
                self.data / rel,
                session=session,
                reason="FUTURES_CANDIDATE_SOURCE_MISSING",
                expected_identity=str(checkpoint.get("identity", "")),
                expected_offset=int(checkpoint.get("offset", 0)),
                expected_fingerprint=str(
                    checkpoint.get("prefix_fingerprint", "")
                ),
                invalidates_selection=self._selection_authority_unreplayed(
                    session
                ),
            )

    def _quarantine_missing_probe_sources(self) -> None:
        """Fail closed when unreplayed selection authority disappears."""
        rows = self.db.execute(
            "select source_file,session_date,start_offset,probe_offset,"
            "replay_target,identity,authority_fingerprint "
            "from futures_selection_probe"
        ).fetchall()
        for (
            rel, session, start_offset, probe_offset, replay_target, identity,
            authority_fingerprint,
        ) in rows:
            path = self.data / str(rel)
            target = (
                int(replay_target)
                if replay_target is not None
                else int(probe_offset)
            )
            primary_offset = int(
                self.checkpoints.get(str(rel), {"offset": 0}).get("offset", 0)
            )
            if path.is_file() or (
                replay_target is not None and primary_offset >= target
            ):
                continue
            self._quarantine_source(
                path,
                session=str(session),
                reason="FUTURES_SELECTION_PROBE_MISSING",
                expected_identity=str(identity),
                expected_offset=max(int(start_offset), target),
                expected_fingerprint=str(authority_fingerprint),
                invalidates_selection=True,
            )

    def _quarantine_source(
        self,
        path: Path,
        *,
        session: str,
        reason: str,
        expected_identity: str,
        expected_offset: int,
        expected_fingerprint: str,
        invalidates_selection: bool,
    ) -> None:
        """Persistently exclude mutated bytes and unblock unaffected layers."""
        rel = str(path.relative_to(self.data))
        if rel in self._quarantined_sources:
            return
        stat = path.stat() if path.is_file() else None
        detected_identity = (
            f"{stat.st_dev}:{stat.st_ino}" if stat is not None else "<MISSING>"
        )
        detected_size = int(stat.st_size) if stat is not None else -1
        detected_at = now()
        quarantine = {
            "session_date": session,
            "reason": reason,
            "expected_identity": expected_identity,
            "expected_offset": int(expected_offset),
            "expected_fingerprint": expected_fingerprint,
            "detected_identity": detected_identity,
            "detected_size": detected_size,
            "invalidates_selection": bool(invalidates_selection),
            "detected_at": detected_at,
        }
        with self.db:
            self.db.execute(
                "insert into quarantined_source("
                "source_file,session_date,reason,expected_identity,expected_offset,"
                "expected_fingerprint,detected_identity,detected_size,"
                "invalidates_selection,detected_at) values (?,?,?,?,?,?,?,?,?,?)",
                (
                    rel, session, reason, expected_identity, int(expected_offset),
                    expected_fingerprint, detected_identity, detected_size,
                    int(invalidates_selection), detected_at,
                ),
            )
            if invalidates_selection:
                # A dynamically selected contract cannot outlive the physical
                # depth prefix that selected it.
                self.symbols.selected_by_session.pop(session, None)
                self.db.execute(
                    "delete from runtime_meta where key=?",
                    (f"selected_futures:{session}",),
                )
                candidate_rows = self.db.execute(
                    "select id,payload from futures_candidate_outbox "
                    "where session_date=?",
                    (session,),
                ).fetchall()
                self.db.execute(
                    "delete from futures_selection_probe where session_date=?",
                    (session,),
                )
                refusal_reason = "FUTURES_SELECTION_EVIDENCE_QUARANTINED"
            else:
                candidate_rows = [
                    (candidate_id, payload)
                    for candidate_id, payload in self.db.execute(
                        "select id,payload from futures_candidate_outbox "
                        "where session_date=?",
                        (session,),
                    )
                    if str(json.loads(payload).get("source_file", "")) == rel
                ]
                refusal_reason = "FUTURES_CANDIDATE_SOURCE_QUARANTINED"
            refused = [
                replace(
                    TypedObservation(**json.loads(payload)),
                    classification_reason=refusal_reason,
                )
                for _, payload in candidate_rows
            ]
            self._aggregate_unknown(refused)
            self.db.executemany(
                "delete from futures_candidate_outbox where id=?",
                [(candidate_id,) for candidate_id, _ in candidate_rows],
            )
        self._quarantined_sources[rel] = quarantine
        self.metrics["candidate_source_quarantine_refusals"] += len(candidate_rows)
        self._queue_quarantine_audit(rel, quarantine)

    def _queue_quarantine_audit(self, rel: str, row: dict[str, Any]) -> None:
        self._quality(
            str(row["reason"]),
            rel,
            0,
            int(row["expected_offset"]),
            (
                f"{row['expected_identity']}->{row['detected_identity']}:"
                f"{row['detected_size']}"
            ),
            (
                f"expected_identity={row['expected_identity']} "
                f"expected_offset={row['expected_offset']} "
                f"expected_fingerprint={row['expected_fingerprint']} "
                f"detected_identity={row['detected_identity']} "
                f"detected_size={row['detected_size']}"
            ),
            effective_timestamp=str(row["detected_at"]),
        )

    def _queue_quarantine_audits(self) -> None:
        for rel, row in self._quarantined_sources.items():
            self._queue_quarantine_audit(rel, row)

    def _selection_replay_sources(self) -> set[str]:
        result = set()
        for rel, target in self.db.execute(
            "select source_file,replay_target from futures_selection_probe "
            "where replay_target is not null"
        ):
            checkpoint = self.checkpoints.get(str(rel), {"offset": 0})
            if int(checkpoint.get("offset", 0)) < int(target):
                result.add(str(rel))
        return result

    def _selection_probe_used(self, session: str) -> int:
        return int(self.db.execute(
            "select coalesce(sum(bytes_consumed),0) "
            "from futures_selection_probe where session_date=?",
            (session,),
        ).fetchone()[0])

    def _mark_selection_probe_exhausted(self, session: str) -> None:
        self._selection_probe_exhausted.add(session)
        with self.db:
            # Exhaustion ends selection look-ahead, not causal ingestion.  The
            # primary cursor must replay every inspected OI row before the
            # candidate is audited away and held market rows are published.
            self.db.execute(
                "update futures_selection_probe set replay_target=probe_offset "
                "where session_date=?",
                (session,),
            )
            self.db.execute(
                "insert into runtime_meta(key,value) values (?,?) "
                "on conflict(key) do update set value=excluded.value",
                (f"selection_probe_exhausted:{session}", "1"),
            )

    def _probe_futures_selection(self, path: Path, session: str) -> None:
        """Search OI depth with a bounded durable cursor, without ingestion."""
        rel = str(path.relative_to(self.data))
        stat = path.stat()
        identity = f"{stat.st_dev}:{stat.st_ino}"
        primary_offset = int(self.checkpoints.get(rel, {"offset": 0}).get("offset", 0))
        row = self.db.execute(
            "select start_offset,probe_offset,identity,prefix_fingerprint,"
            "mtime_ns_at_probe,replay_target,bytes_consumed,inspected_offset,"
            "inspected_fingerprint,size_at_probe,authority_fingerprint "
            "from futures_selection_probe "
            "where source_file=?",
            (rel,),
        ).fetchone()
        if row is None:
            start = offset = inspected_offset = primary_offset
            fingerprint = _committed_prefix_fingerprint(path, offset)
            inspected_fingerprint = hashlib.sha256(b"").hexdigest()
            authority_fingerprint = hashlib.sha256(b"").hexdigest()
            size_at_probe = stat.st_size
            mtime_ns = stat.st_mtime_ns
            replay_target = None
            bytes_consumed = 0
        else:
            (
                start, offset, prior_identity, fingerprint, mtime_ns,
                replay_target, bytes_consumed, inspected_offset,
                inspected_fingerprint, size_at_probe, authority_fingerprint,
            ) = row
            if prior_identity != identity:
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_REPLACED",
                    expected_identity=str(prior_identity),
                    expected_offset=int(inspected_offset),
                    expected_fingerprint=str(fingerprint),
                    invalidates_selection=True,
                )
                return
            if int(inspected_offset) < int(offset):
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_TRUNCATED",
                    expected_identity=str(prior_identity),
                    expected_offset=int(offset),
                    expected_fingerprint=str(fingerprint),
                    invalidates_selection=True,
                )
                return
            if stat.st_size < int(inspected_offset):
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_TRUNCATED",
                    expected_identity=str(prior_identity),
                    expected_offset=int(inspected_offset),
                    expected_fingerprint=str(inspected_fingerprint),
                    invalidates_selection=True,
                )
                return
            unchanged_probe = (
                int(size_at_probe) >= 0
                and stat.st_size == int(size_at_probe)
                and int(inspected_offset) == stat.st_size
                and (not int(mtime_ns) or stat.st_mtime_ns == int(mtime_ns))
                and primary_offset <= int(offset)
            )
            if unchanged_probe:
                offset = int(offset)
                inspected_offset = int(inspected_offset)
                bytes_consumed = int(bytes_consumed)
                self._poll_incomplete[rel] = offset < stat.st_size
                if (
                    replay_target is None
                    and inspected_offset > offset
                    and bytes_consumed >= self.selection_probe_budget
                ):
                    self._quarantine_source(
                        path,
                        session=session,
                        reason=(
                            "FUTURES_SELECTION_PROBE_"
                            "INCOMPLETE_LINE_BUDGET_EXHAUSTED"
                        ),
                        expected_identity=identity,
                        expected_offset=inspected_offset,
                        expected_fingerprint=str(inspected_fingerprint),
                        invalidates_selection=True,
                    )
                    self._poll_incomplete[rel] = False
                return
            if (
                int(offset) > int(start)
                and _exact_range_fingerprint(
                    path, int(start), int(offset),
                ) != str(authority_fingerprint)
            ):
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",
                    expected_identity=str(prior_identity),
                    expected_offset=int(offset),
                    expected_fingerprint=str(authority_fingerprint),
                    invalidates_selection=True,
                )
                return
            if int(offset) > 0 and (
                _committed_prefix_fingerprint(path, int(offset)) != fingerprint
                or (
                    stat.st_size == int(offset)
                    and int(mtime_ns)
                    and stat.st_mtime_ns != int(mtime_ns)
                )
            ):
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",
                    expected_identity=str(prior_identity),
                    expected_offset=int(offset),
                    expected_fingerprint=str(fingerprint),
                    invalidates_selection=True,
                )
                return
            if primary_offset > int(offset):
                offset = primary_offset
                fingerprint = _committed_prefix_fingerprint(path, offset)
                inspected_offset = max(int(inspected_offset), int(offset))
                inspected_fingerprint = _exact_range_fingerprint(
                    path, int(offset), int(inspected_offset),
                )
                authority_fingerprint = _exact_range_fingerprint(
                    path, int(start), int(offset),
                )
                mtime_ns = stat.st_mtime_ns
        start = int(start)
        offset = int(offset)
        inspected_offset = int(inspected_offset)
        bytes_consumed = int(bytes_consumed)
        self._poll_incomplete[rel] = offset < stat.st_size
        if replay_target is not None:
            return
        stat_unchanged = (
            stat.st_size == inspected_offset
            and (not int(mtime_ns) or stat.st_mtime_ns == int(mtime_ns))
        )
        if stat_unchanged:
            # In particular, an incomplete static tail reaches this branch on
            # every empty poll and after restart.  Its exact identity and end
            # are durable, so no raw byte is opened or charged again.
            if (
                inspected_offset > offset
                and bytes_consumed >= self.selection_probe_budget
            ):
                self._quarantine_source(
                    path,
                    session=session,
                    reason=(
                        "FUTURES_SELECTION_PROBE_"
                        "INCOMPLETE_LINE_BUDGET_EXHAUSTED"
                    ),
                    expected_identity=identity,
                    expected_offset=inspected_offset,
                    expected_fingerprint=str(inspected_fingerprint),
                    invalidates_selection=True,
                )
                self._poll_incomplete[rel] = False
            return

        # A same-size mtime change or an append must first prove that the exact
        # previously inspected incomplete tail still exists.  The append read
        # below naturally includes that bounded tail; a same-size touch reads
        # it once and updates the durable stat identity.
        if stat.st_size == inspected_offset:
            actual_fingerprint = _exact_range_fingerprint(
                path, offset, inspected_offset,
            )
            self.metrics["candidate_selection_lookahead_reads"] += bool(
                inspected_offset - offset
            )
            self.metrics["candidate_selection_probe_bytes"] += (
                inspected_offset - offset
            )
            if actual_fingerprint != str(inspected_fingerprint):
                self._quarantine_source(
                    path,
                    session=session,
                    reason="FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",
                    expected_identity=identity,
                    expected_offset=inspected_offset,
                    expected_fingerprint=str(inspected_fingerprint),
                    invalidates_selection=True,
                )
                self._poll_incomplete[rel] = False
                return
            with self.db:
                self.db.execute(
                    "update futures_selection_probe set mtime_ns_at_probe=? "
                    "where source_file=?",
                    (stat.st_mtime_ns, rel),
                )
            return

        remaining = self.selection_probe_budget - self._selection_probe_used(session)
        if remaining <= 0:
            self._mark_selection_probe_exhausted(session)
            return
        unique_bytes = min(
            self.read_limit,
            remaining,
            stat.st_size - inspected_offset,
        )
        read_end = inspected_offset + unique_bytes
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(read_end - offset)
        if len(chunk) != read_end - offset:
            self._quarantine_source(
                path,
                session=session,
                reason="FUTURES_SELECTION_PROBE_FILE_TRUNCATED",
                expected_identity=identity,
                expected_offset=read_end,
                expected_fingerprint=str(inspected_fingerprint),
                invalidates_selection=True,
            )
            self._poll_incomplete[rel] = False
            return
        self.metrics["candidate_selection_lookahead_reads"] += bool(chunk)
        self.metrics["candidate_selection_probe_bytes"] += len(chunk)
        prior_tail_length = inspected_offset - offset
        if (
            hashlib.sha256(chunk[:prior_tail_length]).hexdigest()
            != str(inspected_fingerprint)
        ):
            self._quarantine_source(
                path,
                session=session,
                reason="FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",
                expected_identity=identity,
                expected_offset=inspected_offset,
                expected_fingerprint=str(inspected_fingerprint),
                invalidates_selection=True,
            )
            self._poll_incomplete[rel] = False
            return
        bytes_consumed += unique_bytes
        last_newline = chunk.rfind(b"\n")
        if last_newline < 0:
            inspected_fingerprint = hashlib.sha256(chunk).hexdigest()
            with self.db:
                self.db.execute(
                    "insert into futures_selection_probe("
                    "source_file,session_date,start_offset,probe_offset,identity,"
                    "prefix_fingerprint,mtime_ns_at_probe,replay_target,"
                    "bytes_consumed,inspected_offset,inspected_fingerprint,"
                    "size_at_probe,authority_fingerprint) "
                    "values (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "on conflict(source_file) do update set "
                    "probe_offset=excluded.probe_offset,"
                    "identity=excluded.identity,"
                    "prefix_fingerprint=excluded.prefix_fingerprint,"
                    "mtime_ns_at_probe=excluded.mtime_ns_at_probe,"
                    "replay_target=excluded.replay_target,"
                    "bytes_consumed=excluded.bytes_consumed,"
                    "inspected_offset=excluded.inspected_offset,"
                    "inspected_fingerprint=excluded.inspected_fingerprint,"
                    "size_at_probe=excluded.size_at_probe,"
                    "authority_fingerprint=excluded.authority_fingerprint",
                    (
                        rel, session, int(start), offset, identity,
                        str(fingerprint), stat.st_mtime_ns, replay_target,
                        bytes_consumed, read_end, inspected_fingerprint,
                        stat.st_size, authority_fingerprint,
                    ),
                )
            if self._selection_probe_used(session) >= self.selection_probe_budget:
                self._quarantine_source(
                    path,
                    session=session,
                    reason=(
                        "FUTURES_SELECTION_PROBE_"
                        "INCOMPLETE_LINE_BUDGET_EXHAUSTED"
                    ),
                    expected_identity=identity,
                    expected_offset=read_end,
                    expected_fingerprint=str(inspected_fingerprint),
                    invalidates_selection=True,
                )
                self._poll_incomplete[rel] = False
            return
        selected = None
        cursor = offset
        for line in chunk[: last_newline + 1].splitlines(keepends=True):
            cursor += len(line)
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                receipt = self._timestamp(
                    record.get("received_at"),
                    "selection probe receipt timestamp", required=True,
                )
                assert receipt is not None
                if parse_timestamp(receipt).to_pydatetime() > datetime.now(IST):
                    continue
            except (AttributeError, json.JSONDecodeError, ValueError):
                continue
            if record.get("source") != "future_depth":
                continue
            response = record.get("response")
            values = response.get("d") if isinstance(response, dict) else None
            if not isinstance(values, dict):
                continue
            selected = self.symbols.select_session_futures(
                session,
                (
                    (symbol, item.get("expiry"), item.get("oi"))
                    for symbol, item in values.items()
                    if isinstance(item, dict)
                ),
                as_of_date=receipt[:10],
            )
            if selected:
                break
        self._poll_incomplete[rel] = cursor < stat.st_size
        new_fingerprint = _committed_prefix_fingerprint(path, cursor)
        authority_fingerprint = _exact_range_fingerprint(path, start, cursor)
        inspected_fingerprint = hashlib.sha256(
            chunk[cursor - offset :]
        ).hexdigest()
        with self.db:
            self.db.execute(
                "insert into futures_selection_probe("
                "source_file,session_date,start_offset,probe_offset,identity,"
                "prefix_fingerprint,mtime_ns_at_probe,replay_target,"
                "bytes_consumed,inspected_offset,inspected_fingerprint,"
                "size_at_probe,authority_fingerprint) "
                "values (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "on conflict(source_file) do update set "
                "probe_offset=excluded.probe_offset,identity=excluded.identity,"
                "prefix_fingerprint=excluded.prefix_fingerprint,"
                "mtime_ns_at_probe=excluded.mtime_ns_at_probe,"
                "bytes_consumed=excluded.bytes_consumed,"
                "inspected_offset=excluded.inspected_offset,"
                "inspected_fingerprint=excluded.inspected_fingerprint,"
                "size_at_probe=excluded.size_at_probe,"
                "authority_fingerprint=excluded.authority_fingerprint",
                (
                    rel, session, start, cursor, identity, new_fingerprint,
                    stat.st_mtime_ns, None, bytes_consumed, read_end,
                    inspected_fingerprint, stat.st_size,
                    authority_fingerprint,
                ),
            )
            if selected:
                self.db.execute(
                    "insert into runtime_meta(key,value) values (?,?) "
                    "on conflict(key) do update set value=excluded.value",
                    (f"selected_futures:{session}", selected),
                )
                self.db.execute(
                    "update futures_selection_probe set replay_target=probe_offset "
                    "where session_date=?",
                    (session,),
                )
        if not selected and self._selection_probe_used(session) >= self.selection_probe_budget:
            self._mark_selection_probe_exhausted(session)

    def _candidate_source_ready(self, candidate: TypedObservation) -> bool:
        rel = candidate.source_file
        path = self.data / rel
        if not path.is_file():
            return False
        stat = path.stat()
        checkpoint = self.checkpoints.get(rel)
        if checkpoint is None:
            return False
        identity = f"{stat.st_dev}:{stat.st_ino}"
        offset = int(checkpoint.get("offset", 0))
        if checkpoint.get("identity") != identity or offset != stat.st_size:
            return False
        if int(checkpoint.get("size_at_commit", 0) or 0) != stat.st_size:
            return False
        expected_mtime = int(checkpoint.get("mtime_ns_at_commit", 0) or 0)
        return not expected_mtime or stat.st_mtime_ns == expected_mtime

    def _selection_replay_ready(self, session: str) -> bool:
        for rel, target in self.db.execute(
            "select source_file,replay_target from futures_selection_probe "
            "where session_date=? and replay_target is not null",
            (session,),
        ):
            if int(self.checkpoints.get(str(rel), {"offset": 0}).get("offset", 0)) < int(target):
                return False
        return True

    def _cleanup_replayed_selection_probes(self) -> None:
        sessions = {
            str(session)
            for (session,) in self.db.execute(
                "select distinct session_date from futures_selection_probe"
            )
        }
        for session in sessions:
            if (
                self.symbols.selected_futures_for_session(session)
                and self._selection_replay_ready(session)
                and not self._session_has_candidates(session)
            ):
                self.db.execute(
                    "delete from futures_selection_probe where session_date=?",
                    (session,),
                )

    def _retire_exhausted_candidates(self) -> None:
        rows = self.db.execute(
            "select id,session_date,payload from futures_candidate_outbox"
        ).fetchall()
        refused = []
        deleted = []
        for candidate_id, session, payload in rows:
            if (
                session not in self._selection_probe_exhausted
                or not self._selection_replay_ready(session)
            ):
                continue
            refused.append(replace(
                TypedObservation(**json.loads(payload)),
                classification_reason="FUTURES_SELECTION_SEARCH_LIMIT",
            ))
            deleted.append((candidate_id,))
        self._aggregate_unknown(refused)
        self.db.executemany(
            "delete from futures_candidate_outbox where id=?", deleted,
        )
        self.metrics["candidate_selection_probe_refusals"] += len(deleted)
        for session in {row.session_date for row in refused}:
            self.db.execute(
                "delete from futures_selection_probe where session_date=?",
                (session,),
            )

    def _acknowledge(self, observation_ids: list[str]) -> None:
        if not observation_ids:
            return
        self.db.executemany(
            "delete from observation_outbox where id=?",
            [(observation_id,) for observation_id in observation_ids],
        )
        self.db.commit()

    def _ledger_observations(self, observations: list[TypedObservation]) -> None:
        rows = [
            observation.to_dict()
            for observation in observations
            if observation.event_id not in self._normalized_seen
        ]
        if not rows:
            return
        self.ledgers["normalized_raw_events"].append_many(rows)
        self._normalized_seen.update(row["event_id"] for row in rows)
        self._normalized_out_of_order.update(
            (row["event_id"], bool(row.get("out_of_order"))) for row in rows
        )

    def _mark_ordering(
        self,
        observation: TypedObservation,
        previous: str | None,
    ) -> TypedObservation:
        kind = observation.instrument_class
        if kind not in _OBSERVED_CLASSES or observation.status != "OBSERVED":
            return observation
        if observation.event_id in self._normalized_seen:
            return (
                observation.marked_out_of_order()
                if self._normalized_out_of_order.get(observation.event_id)
                else observation
            )
        receipt = parse_timestamp(observation.receipt_timestamp, field_name="live receipt timestamp")
        if previous is not None and receipt < parse_timestamp(previous, field_name="previous live receipt timestamp"):
            self._quality(
                "OUT_OF_ORDER_RECEIPT", observation.source_file, observation.source_row_number,
                observation.source_byte_offset, observation.observation_id,
                f"previous={previous} current={observation.receipt_timestamp}",
            )
            return observation.marked_out_of_order()
        return observation

    def _advance_clocks(self, observations: list[TypedObservation]) -> None:
        for observation in observations:
            kind = observation.instrument_class
            if (
                kind not in _OBSERVED_CLASSES
                or observation.status != "OBSERVED"
                or observation.out_of_order
            ):
                continue
            receipt = parse_timestamp(
                observation.receipt_timestamp, field_name="acknowledged receipt timestamp"
            )
            if self._causal_high_water is None or receipt >= parse_timestamp(
                self._causal_high_water, field_name="acknowledged high-water"
            ):
                self._causal_high_water = observation.receipt_timestamp
            prior = self.latest.get(kind)
            if prior is None or receipt >= parse_timestamp(prior, field_name="latest instrument receipt"):
                self.latest[kind] = observation.receipt_timestamp
            if self._has_valid_evidence(observation):
                valid_prior = self.latest_valid.get(kind)
                if valid_prior is None or receipt >= parse_timestamp(
                    valid_prior, field_name="latest valid instrument receipt"
                ):
                    self.latest_valid[kind] = observation.receipt_timestamp

    @staticmethod
    def _has_valid_evidence(observation: TypedObservation) -> bool:
        stream = observation.source_stream or observation.source_file.split("/", 1)[0]
        if observation.instrument_class in {
            InstrumentClass.INDEX.value,
            InstrumentClass.FUTURES.value,
        }:
            return stream == "raw" and observation.price is not None
        if observation.instrument_class in {
            InstrumentClass.FUTURES_OI.value,
            InstrumentClass.CE.value,
            InstrumentClass.PE.value,
        }:
            return stream == "oi" and observation.open_interest is not None
        return False

    def _persist_runtime_clocks(self) -> None:
        values = [(f"latest:{key}", value) for key, value in self.latest.items()]
        values.extend(
            (f"latest_valid:{key}", value)
            for key, value in self.latest_valid.items()
        )
        if self._causal_high_water is not None:
            values.append(("causal_high_water", self._causal_high_water))
        values.extend(
            (f"selected_futures:{session}", min(symbols))
            for session, symbols in self.symbols.selected_by_session.items()
            if symbols
        )
        self.db.executemany(
            "insert into runtime_meta(key,value) values (?,?) "
            "on conflict(key) do update set value=excluded.value",
            values,
        )
        self.db.commit()

    def _read_file(self, path: Path) -> list[TypedObservation]:
        rel = str(path.relative_to(self.data))
        stat = path.stat()
        identity = f"{stat.st_dev}:{stat.st_ino}"
        checkpoint = self.checkpoints.get(rel, {"offset": 0, "identity": identity, "row": 0})
        canonical = self.db.execute(
            "select offset,row_number,identity,size_at_commit,updated_at,frontier,"
            "prefix_fingerprint,mtime_ns_at_commit "
            "from file_checkpoint where source_file=?", (rel,),
        ).fetchone()
        if canonical is not None:
            if checkpoint.get("offset", 0) < canonical[0]:
                self.metrics["duplicates"] += max(
                    1, canonical[1] - checkpoint.get("row", 0)
                )
            checkpoint = {
                "offset": canonical[0], "row": canonical[1], "identity": canonical[2],
                "size_at_commit": canonical[3], "updated_at": canonical[4],
                "prefix_fingerprint": canonical[6], "mtime_ns_at_commit": canonical[7],
            }
            self.checkpoints[rel] = checkpoint
            if canonical[5] is not None:
                self._stream_frontiers[rel] = canonical[5]
        mutation_reason = self._committed_source_mutation_reason(
            path, rel, checkpoint,
        )
        if mutation_reason is not None:
            self._quarantine_committed_source(path, checkpoint, mutation_reason)
            self._poll_incomplete[rel] = False
            return []
        if stat.st_size == checkpoint["offset"]:
            # A discovered but never-initialized growing stream is a causal
            # barrier: another file must not publish past an unknown first
            # receipt.  Once initialized its receipt frontier is a lower bound,
            # but temporary EOF is not a producer watermark: exact ordering of
            # later cross-stream appends still requires producer finalization.
            # Any such backdated append is detected against the acknowledged
            # high-water and remains auditable rather than silently reordered.
            self._poll_incomplete[rel] = (
                stat.st_size == 0 and rel not in self._stream_frontiers
            )
            return []
        expected_stat = (
            stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
        )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            opened_stat = (
                opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns,
            )
            if opened_stat[:2] != expected_stat[:2]:
                self._quarantine_committed_source(
                    path, checkpoint, "FILE_REPLACED",
                )
                self._poll_incomplete[rel] = False
                return []
            if (
                opened.st_size < stat.st_size
                or (
                    opened.st_size == stat.st_size
                    and opened.st_mtime_ns != stat.st_mtime_ns
                )
            ):
                self._quarantine_committed_source(
                    path, checkpoint, "FILE_REPLACED_IN_PLACE",
                )
                self._poll_incomplete[rel] = False
                return []
            handle.seek(checkpoint["offset"])
            snapshot_size = opened.st_size
            chunk = handle.read(
                min(self.read_limit, snapshot_size - checkpoint["offset"])
            )
            last_newline = chunk.rfind(b"\n")
            if last_newline >= 0:
                captured_offset = checkpoint["offset"] + last_newline + 1
                prefix_blocks = self._new_complete_prefix_blocks(
                    path, rel, captured_offset, handle=handle,
                )
                prefix_fingerprint = _committed_prefix_fingerprint_from_handle(
                    handle, captured_offset,
                )
                after_read = os.fstat(handle.fileno())
                try:
                    path_after = path.stat()
                except FileNotFoundError:
                    self._quarantine_committed_source(
                        path, checkpoint, "FILE_REPLACED",
                    )
                    self._poll_incomplete[rel] = False
                    return []
                if (
                    (after_read.st_dev, after_read.st_ino) != expected_stat[:2]
                    or (path_after.st_dev, path_after.st_ino) != expected_stat[:2]
                ):
                    if (path_after.st_dev, path_after.st_ino) != expected_stat[:2]:
                        self._quarantine_committed_source(
                            path, checkpoint, "FILE_REPLACED",
                        )
                        self._poll_incomplete[rel] = False
                    return []
                if (
                    after_read.st_size < snapshot_size
                    or path_after.st_size < after_read.st_size
                    or (
                        after_read.st_size == snapshot_size
                        and after_read.st_mtime_ns != opened.st_mtime_ns
                    )
                    or (
                        path_after.st_size == after_read.st_size
                        and path_after.st_mtime_ns != after_read.st_mtime_ns
                    )
                ):
                    self._quarantine_committed_source(
                        path, checkpoint, "FILE_REPLACED_IN_PLACE",
                    )
                    self._poll_incomplete[rel] = False
                    return []
                # Same-inode monotonic growth is a valid immutable snapshot.
                # Commit only bytes bounded by snapshot_size and leave newer
                # bytes visible to the next incremental poll.
                stat = path_after
        self.metrics["bytes"] += len(chunk)
        self.metrics["max_buffer"] = max(self.metrics["max_buffer"], len(chunk))
        if last_newline < 0:
            self._poll_incomplete[rel] = True
            if len(chunk) > self.buffer_limit:
                self._refuse("INCOMPLETE_LINE_BUFFER_LIMIT", rel, checkpoint, stat)
            else:
                self.metrics["deferred_lines"] += 1
            return []

        complete = chunk[: last_newline + 1]
        result: list[TypedObservation] = []
        staged: list[tuple[str, list[TypedObservation]]] = []
        offset = checkpoint["offset"]
        row_number = checkpoint["row"]
        for line in complete.splitlines(keepends=True):
            line_start = offset
            offset += len(line)
            row_number += 1
            # R6E1R's byte-exact raw projection leaves whitespace-only padding
            # rows so selected records retain their authoritative physical row
            # coordinate.  Production files are never modified; ordinary blank
            # JSONL rows are harmless no-record rows.  They advance the durable
            # checkpoint but never create a refusal, normalized row, or outbox.
            if not line.strip():
                self.metrics["projection_padding_lines"] += 1
                continue
            raw_id = event_id("RAW", rel, line_start, hashlib.sha256(line).hexdigest())
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                self.metrics["malformed"] += 1
                self._quality("MALFORMED_JSONL", rel, row_number, line_start, raw_id)
                staged.append((raw_id, []))
                continue
            if not isinstance(record, dict):
                self.metrics["malformed"] += 1
                self._quality("INVALID_JSONL_RECORD", rel, row_number, line_start, raw_id)
                staged.append((raw_id, []))
                continue
            try:
                normalized = self._normalize_record(
                    path, record, rel=rel, row_number=row_number,
                    byte_offset=line_start, raw_record_id=raw_id,
                )
            except ValueError as error:
                self._quality("TIMESTAMP_REFUSED", rel, row_number, line_start, raw_id, str(error))
                staged.append((raw_id, []))
                continue
            self.metrics["records"] += 1
            result.extend(normalized)
            staged.append((raw_id, normalized))

        # Refusals and the typed outbox are durable before a checkpoint can
        # make these complete source lines unreachable.
        frontier = next(
            (
                observation.receipt_timestamp
                for _, observations in reversed(staged)
                for observation in reversed(observations)
            ),
            self._stream_frontiers.get(rel),
        )
        if frontier is not None:
            self._stream_frontiers[rel] = frontier
        self._poll_incomplete[rel] = offset < stat.st_size
        self._flush_quality()
        committed_at = now()
        checkpoint = {
            "offset": offset, "identity": identity, "row": row_number,
            "size_at_commit": stat.st_size, "updated_at": committed_at,
            "prefix_fingerprint": prefix_fingerprint,
            "mtime_ns_at_commit": stat.st_mtime_ns,
        }
        self._persist_raw_batch(
            staged,
            rel=rel,
            stream_frontier=frontier,
            checkpoint=checkpoint,
            prefix_blocks=prefix_blocks,
        )
        self.checkpoints[rel] = checkpoint
        self._checkpoint_dirty = True
        checkpoint_event_id = event_id("CHECKPOINT", rel, offset, identity)
        if checkpoint_event_id not in self._checkpoint_seen:
            self._checkpoint_pending.append({
                "event_id": checkpoint_event_id,
                "session_date": rel.split("/")[1],
                "effective_timestamp": committed_at,
                "publication_timestamp": committed_at,
                "source_receipt_identifiers": {"file": rel, "offset": offset, "identity": identity},
                "engine_hash": self.c["engine_hash"],
                "configuration_hash": self.c["configuration_hash"],
                "raw_run_id": self.c["raw_run_id"],
                "status": "COMMITTED", "reason": "COMPLETE_LINES_ONLY",
            })
        return result

    def _persist_raw_batch(
        self,
        staged: list[tuple[str, list[TypedObservation]]],
        *,
        rel: str,
        stream_frontier: str | None,
        checkpoint: dict[str, Any],
        prefix_blocks: list[tuple[int, int, str]],
    ) -> None:
        with self.db:
            self.db.executemany(
                "insert into observation_outbox(id,payload) values (?,?)",
                [
                    (
                        observation.observation_id,
                        json.dumps(
                            observation.to_dict(),
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    )
                    for _, observations in staged
                    for observation in observations
                    if observation.instrument_class in _OBSERVED_CLASSES
                    and observation.status == "OBSERVED"
                ],
            )
            candidates = [
                observation
                for _, observations in staged
                for observation in observations
                if observation.classification_reason == "FUTURES_SELECTION_PENDING"
            ]
            self.db.executemany(
                "insert into futures_candidate_outbox("
                "id,session_date,receipt_timestamp,payload) values (?,?,?,?)",
                [
                    (
                        observation.observation_id,
                        observation.session_date,
                        observation.receipt_timestamp,
                        json.dumps(
                            observation.to_dict(), sort_keys=True, separators=(",", ":"),
                        ),
                    )
                    for observation in candidates
                ],
            )
            if stream_frontier is not None:
                self.db.execute(
                    "insert into runtime_meta(key,value) values (?,?) "
                    "on conflict(key) do update set value=excluded.value",
                    (f"stream_frontier:{rel}", stream_frontier),
                )
            self.db.execute(
                "insert into file_checkpoint("
                "source_file,offset,row_number,identity,size_at_commit,updated_at,frontier,"
                "prefix_fingerprint,mtime_ns_at_commit) values (?,?,?,?,?,?,?,?,?) "
                "on conflict(source_file) do update set offset=excluded.offset,"
                "row_number=excluded.row_number,identity=excluded.identity,"
                "size_at_commit=excluded.size_at_commit,updated_at=excluded.updated_at,"
                "frontier=excluded.frontier,prefix_fingerprint=excluded.prefix_fingerprint,"
                "mtime_ns_at_commit=excluded.mtime_ns_at_commit",
                (
                    rel, checkpoint["offset"], checkpoint["row"], checkpoint["identity"],
                    checkpoint["size_at_commit"], checkpoint["updated_at"], stream_frontier,
                    checkpoint["prefix_fingerprint"], checkpoint["mtime_ns_at_commit"],
                ),
            )
            self.db.executemany(
                "insert into file_prefix_block("
                "source_file,block_index,byte_count,digest) values (?,?,?,?) "
                "on conflict(source_file,block_index) do update set "
                "byte_count=excluded.byte_count,digest=excluded.digest",
                [
                    (rel, block_index, byte_count, digest)
                    for block_index, byte_count, digest in prefix_blocks
                ],
            )
            if prefix_blocks:
                first_block = min(row[0] for row in prefix_blocks)
                self.db.execute(
                    "insert or ignore into file_integrity_scrub("
                    "source_file,next_block,updated_at) values (?,?,?)",
                    (rel, first_block, checkpoint["updated_at"]),
                )
            unknown = [
                observation
                for _, observations in staged
                for observation in observations
                if observation.instrument_class not in _OBSERVED_CLASSES
                or observation.status != "OBSERVED"
                if observation.classification_reason != "FUTURES_SELECTION_PENDING"
            ]
            self._aggregate_unknown(unknown)
            self.db.executemany(
                "insert into runtime_meta(key,value) values (?,?) "
                "on conflict(key) do update set value=excluded.value",
                [
                    (f"selected_futures:{session}", min(symbols))
                    for session, symbols in self.symbols.selected_by_session.items()
                    if symbols
                ],
            )
            # Candidate release is intentionally deferred until the bounded
            # selection probe has been replayed through the primary checkpoint
            # and the candidate's raw source is caught up.  Releasing here can
            # invert an equal-clock INDEX/FUTURES tie across a chunk boundary.

    def _release_selected_candidates(self, *, ready_only: bool = False) -> None:
        rows = self.db.execute(
            "select id,session_date,payload from futures_candidate_outbox "
            "order by session_date,id"
        ).fetchall()
        released: list[TypedObservation] = []
        refused: list[TypedObservation] = []
        deleted: list[tuple[str]] = []
        for candidate_id, session, payload in rows:
            selected = self.symbols.selected_futures_for_session(session)
            if not selected:
                continue
            # The look-ahead selector is not analytical evidence.  No pending
            # candidate--including a contract that will be refused as
            # unselected--may cross or remove the causal barrier until every
            # probed authority byte has passed through primary ingestion.
            if ready_only and not self._selection_replay_ready(session):
                continue
            candidate = TypedObservation(**json.loads(payload))
            classification = self.symbols.classify(
                candidate.source_symbol, source_kind="market", session_date=session,
            )
            if classification.instrument_class is InstrumentClass.FUTURES:
                if ready_only and not (
                    self._candidate_source_ready(candidate)
                    and self._selection_replay_ready(session)
                ):
                    continue
                item_number = candidate.source_receipt_identifiers.get("item_number", 0)
                identity = event_id(
                    "OBS", candidate.raw_record_id, item_number,
                    InstrumentClass.FUTURES.value, candidate.source_symbol,
                )
                released.append(replace(
                    candidate,
                    observation_id=identity,
                    event_id=identity,
                    instrument_class=InstrumentClass.FUTURES.value,
                    canonical_symbol=candidate.source_symbol,
                    availability_status="AVAILABLE",
                    freshness_status="FRESH_AT_RECEIPT",
                    status="OBSERVED",
                    reason=InstrumentClass.FUTURES.value,
                    classification_reason=classification.reason,
                ))
            else:
                refused.append(replace(
                    candidate,
                    classification_reason=classification.reason,
                ))
            deleted.append((candidate_id,))
        self.db.executemany(
            "insert or ignore into observation_outbox(id,payload) values (?,?)",
            [
                (
                    observation.observation_id,
                    json.dumps(
                        observation.to_dict(), sort_keys=True, separators=(",", ":"),
                    ),
                )
                for observation in released
            ],
        )
        self._aggregate_unknown(refused)
        self.db.executemany(
            "delete from futures_candidate_outbox where id=?", deleted,
        )
        for session in {row[1] for row in rows}:
            remaining = self.db.execute(
                "select 1 from futures_candidate_outbox where session_date=? limit 1",
                (session,),
            ).fetchone()
            if remaining is None:
                self.db.execute(
                    "delete from futures_selection_probe where session_date=?",
                    (session,),
                )

    def _aggregate_unknown(self, observations: list[TypedObservation]) -> None:
        grouped: dict[tuple[str, str, str], list[TypedObservation]] = {}
        for observation in observations:
            key = (
                observation.session_date,
                observation.source_symbol or "<MISSING_SYMBOL>",
                observation.classification_reason,
            )
            grouped.setdefault(key, []).append(observation)
        for (session, symbol, reason), rows in grouped.items():
            rows.sort(key=TypedObservation.causal_sort_key)
            first, last = rows[0], rows[-1]
            existing = self.db.execute(
                "select observation_count,first_receipt,last_receipt,"
                "first_source_file,first_byte_offset,first_source_row,"
                "last_source_file,last_byte_offset,last_source_row "
                "from unknown_symbol_audit where session_date=? and source_symbol=? and reason=?",
                (session, symbol, reason),
            ).fetchone()
            if existing is not None:
                old_first_key = (
                    parse_timestamp(existing[1], field_name="unknown first receipt"),
                    existing[3], existing[4], existing[5],
                )
                old_last_key = (
                    parse_timestamp(existing[2], field_name="unknown last receipt"),
                    existing[6], existing[7], existing[8],
                )
                new_first_key = (
                    parse_timestamp(first.receipt_timestamp, field_name="unknown first receipt"),
                    first.source_file, first.source_byte_offset, first.source_row_number,
                )
                new_last_key = (
                    parse_timestamp(last.receipt_timestamp, field_name="unknown last receipt"),
                    last.source_file, last.source_byte_offset, last.source_row_number,
                )
                if old_first_key <= new_first_key:
                    first_values = (existing[1], existing[3], existing[4], existing[5])
                else:
                    first_values = (
                        first.receipt_timestamp, first.source_file,
                        first.source_byte_offset, first.source_row_number,
                    )
                if old_last_key >= new_last_key:
                    last_values = (existing[2], existing[6], existing[7], existing[8])
                else:
                    last_values = (
                        last.receipt_timestamp, last.source_file,
                        last.source_byte_offset, last.source_row_number,
                    )
                count = existing[0] + len(rows)
            else:
                count = len(rows)
                first_values = (
                    first.receipt_timestamp, first.source_file,
                    first.source_byte_offset, first.source_row_number,
                )
                last_values = (
                    last.receipt_timestamp, last.source_file,
                    last.source_byte_offset, last.source_row_number,
                )
            self.db.execute(
                "insert into unknown_symbol_audit values (?,?,?,?,?,?,?,?,?,?,?,?) "
                "on conflict(session_date,source_symbol,reason) do update set "
                "observation_count=excluded.observation_count,first_receipt=excluded.first_receipt,"
                "last_receipt=excluded.last_receipt,first_source_file=excluded.first_source_file,"
                "first_byte_offset=excluded.first_byte_offset,first_source_row=excluded.first_source_row,"
                "last_source_file=excluded.last_source_file,last_byte_offset=excluded.last_byte_offset,"
                "last_source_row=excluded.last_source_row",
                (
                    session, symbol, reason, count,
                    first_values[0], last_values[0], first_values[1],
                    first_values[2], first_values[3], last_values[1],
                    last_values[2], last_values[3],
                ),
            )
            self.metrics["unknown_observations"] += len(rows)

    def unknown_symbol_audit(self) -> list[dict[str, Any]]:
        columns = (
            "session_date", "source_symbol", "reason", "observation_count",
            "first_receipt", "last_receipt", "first_source_file", "first_byte_offset",
            "first_source_row", "last_source_file", "last_byte_offset", "last_source_row",
        )
        return [
            dict(zip(columns, row, strict=True))
            for row in self.db.execute(
                "select * from unknown_symbol_audit order by session_date,source_symbol,reason"
            )
        ]

    def _normalize_record(
        self,
        path: Path,
        record: dict[str, Any],
        *,
        rel: str,
        row_number: int,
        byte_offset: int,
        raw_record_id: str,
    ) -> list[TypedObservation]:
        receipt = self._timestamp(record.get("received_at"), "live receipt timestamp", required=True)
        assert receipt is not None
        receipt_clock = parse_timestamp(
            receipt, field_name="live receipt timestamp"
        ).to_pydatetime()
        publication_clock = datetime.now(IST)
        if receipt_clock > publication_clock:
            raise ValueError("future live receipt timestamp")
        session_date = rel.split("/")[1]
        publication = publication_clock.isoformat()
        if "/raw/" in str(path):
            event_timestamp = self._timestamp(record.get("event_time"), "exchange/event timestamp")
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            classification = self.symbols.classify(
                message.get("symbol", ""), source_kind="market", session_date=session_date,
            )
            payload = self._selected(message, _MARKET_PAYLOAD_FIELDS)
            payload.update(self._selected(
                record,
                ("timestamp_source", "receive_lag_seconds", "timestamp_anomaly", "aggregation_status"),
            ))
            return [self._envelope(
                classification, item=message, receipt=receipt, event_timestamp=event_timestamp,
                session_date=session_date, rel=rel, row_number=row_number, byte_offset=byte_offset,
                raw_record_id=raw_record_id, item_number=0, publication=publication,
                canonical_payload=payload,
            )]

        request_timestamp = self._timestamp(record.get("request_time"), "request/event timestamp")
        source = str(record.get("source") or "")
        response = record.get("response") if isinstance(record.get("response"), dict) else {}
        if source == "future_depth":
            values = response.get("d") if isinstance(response.get("d"), dict) else {}
            items = [(str(symbol), item) for symbol, item in values.items() if isinstance(item, dict)]
            if not items:
                return [self._empty_container(
                    InstrumentClass.FUTURES_OI, str(record.get("requested_symbol") or ""),
                    receipt, request_timestamp, session_date, rel, row_number, byte_offset,
                    raw_record_id, publication, source,
                )]
            self.symbols.select_session_futures(
                session_date,
                (
                    (symbol, item.get("expiry"), item.get("oi"))
                    for symbol, item in items
                ),
                as_of_date=receipt[:10],
            )
            result = []
            for item_number, (symbol, item) in enumerate(items):
                enriched = dict(item)
                enriched["symbol"] = symbol
                classification = self.symbols.classify(
                    symbol, source_kind=source, expiry=item.get("expiry"),
                    session_date=session_date,
                )
                payload = self._selected(enriched, _OI_PAYLOAD_FIELDS)
                payload.update(self._selected(record, ("source", "requested_symbol", "latency_ms")))
                result.append(self._envelope(
                    classification, item=enriched, receipt=receipt, event_timestamp=request_timestamp,
                    session_date=session_date, rel=rel, row_number=row_number, byte_offset=byte_offset,
                    raw_record_id=raw_record_id, item_number=item_number, publication=publication,
                    canonical_payload=payload,
                ))
            return result

        if source == "option_chain":
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            chain = data.get("optionsChain") if isinstance(data.get("optionsChain"), list) else []
            items = [item for item in chain if isinstance(item, dict)]
            if not items:
                return [self._empty_container(
                    InstrumentClass.OPTION_OI, str(record.get("requested_symbol") or ""),
                    receipt, request_timestamp, session_date, rel, row_number, byte_offset,
                    raw_record_id, publication, source,
                )]
            expiry_data = data.get("expiryData") if isinstance(data.get("expiryData"), list) else []
            default_expiry = next((
                expiry.get("date", expiry.get("expiry"))
                for expiry in expiry_data
                if isinstance(expiry, dict) and expiry.get("date", expiry.get("expiry"))
            ), None)
            index_item = next((
                item for item in items if item.get("symbol") == "NSE:NIFTYBANK-INDEX"
            ), {})
            underlying = _number(index_item.get("ltp"))
            forward = _number(index_item.get("fp"))
            result = []
            for item_number, item in enumerate(items):
                symbol = str(item.get("symbol") or "")
                item_expiry = item.get("expiry") or default_expiry
                classification = self.symbols.classify(
                    symbol, source_kind=source,
                    expiry=item_expiry if symbol != "NSE:NIFTYBANK-INDEX" else None,
                    strike=item.get("strike_price"), option_type=item.get("option_type"),
                    session_date=session_date,
                )
                payload = self._selected(item, _OI_PAYLOAD_FIELDS)
                payload.update(self._selected(record, ("source", "requested_symbol", "latency_ms")))
                result.append(self._envelope(
                    classification, item=item, receipt=receipt, event_timestamp=request_timestamp,
                    session_date=session_date, rel=rel, row_number=row_number, byte_offset=byte_offset,
                    raw_record_id=raw_record_id, item_number=item_number, publication=publication,
                    canonical_payload=payload, underlying_price=underlying, forward_price=forward,
                ))
            return result

        unknown = self.symbols.classify(
            record.get("requested_symbol", ""), source_kind=source,
            session_date=session_date,
        )
        return [self._envelope(
            unknown, item={}, receipt=receipt, event_timestamp=request_timestamp,
            session_date=session_date, rel=rel, row_number=row_number, byte_offset=byte_offset,
            raw_record_id=raw_record_id, item_number=0, publication=publication,
            canonical_payload=self._selected(record, ("source", "requested_symbol", "latency_ms")),
        )]

    def _envelope(
        self,
        classification: SymbolClassification,
        *,
        item: dict[str, Any],
        receipt: str,
        event_timestamp: str | None,
        session_date: str,
        rel: str,
        row_number: int,
        byte_offset: int,
        raw_record_id: str,
        item_number: int,
        publication: str,
        canonical_payload: dict[str, Any],
        underlying_price: int | float | None = None,
        forward_price: int | float | None = None,
    ) -> TypedObservation:
        price = _number(item.get("ltp"))
        volume = _number(item.get("vol_traded_today", item.get("volume", item.get("v"))))
        oi = _number(item.get("oi"))
        previous_oi = _number(item.get("prev_oi", item.get("pdoi")))
        delta_oi = _oi_change(oi, previous_oi, item.get("oich"))
        observation_id = event_id(
            "OBS", raw_record_id, item_number, classification.instrument_class.value,
            classification.canonical_symbol or classification.source_symbol,
        )
        known = classification.known
        expiry = classification.expiry or normalize_expiry(item.get("expiry"))
        strike = classification.strike if classification.strike is not None else _number(item.get("strike_price"))
        option_type = classification.option_type or (
            str(item.get("option_type")).upper() if item.get("option_type") else None
        )
        source_stream = rel.split("/", 1)[0]
        bid_price = _quote_price(item, "bids" if isinstance(item.get("bids"), list) else "bid")
        ask_price = _quote_price(item, "ask")
        identifiers = {
            "file": rel, "byte_offset": byte_offset, "source_row": row_number,
            "raw_record_id": raw_record_id, "item_number": item_number,
            "source_stream": source_stream,
        }
        return TypedObservation(
            observation_id=observation_id, event_id=observation_id, session_date=session_date,
            instrument_class=classification.instrument_class.value,
            canonical_symbol=classification.canonical_symbol, source_symbol=classification.source_symbol,
            receipt_timestamp=receipt, event_timestamp=event_timestamp,
            exchange_timestamp=event_timestamp, price=price, cumulative_volume=volume,
            open_interest=oi, previous_open_interest=previous_oi, open_interest_change=delta_oi,
            oi=oi, previous_oi=previous_oi, delta_oi=delta_oi, strike=strike,
            option_type=option_type, expiry=expiry, expiry_date=expiry,
            underlying_price=underlying_price, forward_price=forward_price,
            source_file=rel, source_byte_offset=byte_offset, source_row_number=row_number,
            source_row=row_number, raw_record_id=raw_record_id,
            availability_status="AVAILABLE" if known else "REFUSED_UNKNOWN_SYMBOL",
            freshness_status="FRESH_AT_RECEIPT" if known else "NOT_APPLICABLE",
            out_of_order=False, canonical_payload=canonical_payload,
            effective_timestamp=receipt, publication_timestamp=publication,
            source_receipt_identifiers=identifiers, engine_hash=self.c["engine_hash"],
            configuration_hash=self.c["configuration_hash"], raw_run_id=self.c["raw_run_id"],
            status="OBSERVED" if known else "FILTERED",
            reason=classification.instrument_class.value,
            classification_reason=classification.reason,
            source_stream=source_stream, bid_price=bid_price, ask_price=ask_price,
        )

    def _empty_container(
        self,
        instrument_class: InstrumentClass,
        source_symbol: str,
        receipt: str,
        event_timestamp: str | None,
        session_date: str,
        rel: str,
        row_number: int,
        byte_offset: int,
        raw_record_id: str,
        publication: str,
        source: str,
    ) -> TypedObservation:
        audit_symbol = source_symbol or f"<{source.upper()}_EMPTY>"
        classification = SymbolClassification(
            instrument_class, None, audit_symbol,
            reason="EMPTY_SOURCE_CONTAINER",
        )
        observation = self._envelope(
            classification, item={}, receipt=receipt, event_timestamp=event_timestamp,
            session_date=session_date, rel=rel, row_number=row_number, byte_offset=byte_offset,
            raw_record_id=raw_record_id, item_number=0, publication=publication,
            canonical_payload={"source": source, "empty": True},
        )
        values = observation.to_dict()
        values.update({
            "availability_status": "MISSING_SOURCE_PAYLOAD",
            "freshness_status": "NOT_APPLICABLE", "status": "FILTERED",
        })
        return TypedObservation(**values)

    @staticmethod
    def _timestamp(value: object, field_name: str, required: bool = False) -> str | None:
        if value in (None, "") and not required:
            return None
        return parse_timestamp(value, field_name=field_name).isoformat()

    @staticmethod
    def _selected(source: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
        return {
            name: source[name]
            for name in names
            if name in source and isinstance(source[name], (str, int, float, bool, type(None)))
        }

    def _quality(
        self,
        reason: str,
        rel: str,
        row: int,
        offset: int,
        key: str,
        detail: str = "",
        *,
        effective_timestamp: str | None = None,
    ) -> None:
        effective = (
            parse_timestamp(
                effective_timestamp,
                field_name="quality effective timestamp",
            ).isoformat()
            if effective_timestamp is not None
            else now()
        )
        publication = now()
        quality_event_id = event_id("QUALITY", reason, key, rel, row, offset)
        if quality_event_id in self._quality_seen or quality_event_id in self._quality_pending_ids:
            return
        self._quality_pending.append({
            "event_id": quality_event_id,
            "session_date": rel.split("/")[1],
            "effective_timestamp": effective,
            "publication_timestamp": publication,
            "source_receipt_identifiers": {
                "file": rel, "source_row": row, "byte_offset": offset,
            },
            "engine_hash": self.c["engine_hash"],
            "configuration_hash": self.c["configuration_hash"],
            "raw_run_id": self.c["raw_run_id"], "status": "REFUSED",
            "reason": reason, "detail": detail,
        })
        self._quality_pending_ids.add(quality_event_id)

    def _flush_quality(self) -> None:
        if not self._quality_pending:
            return
        self.ledgers["refusals_data_quality"].append_many(self._quality_pending)
        self._quality_seen.update(self._quality_pending_ids)
        self._quality_pending = []
        self._quality_pending_ids = set()

    def _flush_checkpoints(self) -> None:
        rows = [
            row for row in self._checkpoint_pending
            if row["event_id"] not in self._checkpoint_seen
        ]
        if rows:
            self.ledgers["raw_file_checkpoints"].append_many(rows)
            self._checkpoint_seen.update(row["event_id"] for row in rows)
        self._checkpoint_pending = []

    def _refuse(self, reason: str, rel: str, checkpoint: dict[str, Any], stat: Any) -> None:
        self._quality(
            reason, rel, checkpoint.get("row", 0), checkpoint.get("offset", 0),
            f"{stat.st_dev}:{stat.st_ino}", f"checkpoint={checkpoint} size={stat.st_size}",
        )

    def checkpoint_health(self) -> dict[str, Any]:
        """Return measured durable-state integrity without rescanning raw data."""
        # HTTP readiness runs on a different thread from ingestion.  A short
        # independent read connection avoids sharing sqlite connection state.
        with sqlite3.connect(self.state / "dedup.sqlite3") as audit_db:
            sqlite_result = audit_db.execute("pragma quick_check").fetchone()
            canonical = {
                row[0]: (int(row[1]), int(row[2]), str(row[3]))
                for row in audit_db.execute(
                    "select source_file,offset,row_number,identity from file_checkpoint"
                )
            }
            pending = audit_db.execute(
                "select count(*) from observation_outbox"
            ).fetchone()[0]
        sqlite_ok = sqlite_result == ("ok",)
        memory = {
            rel: (
                int(checkpoint.get("offset", 0)),
                int(checkpoint.get("row", 0)),
                str(checkpoint.get("identity", "")),
            )
            for rel, checkpoint in self.checkpoints.items()
        }
        consistent = canonical == memory
        return {
            "valid": sqlite_ok and consistent,
            "sqlite_quick_check": sqlite_result[0] if sqlite_result else "MISSING",
            "checkpoint_count": len(canonical),
            "memory_database_consistent": consistent,
            "pending_observations": pending,
        }

    def close(self) -> None:
        self._acknowledge(self._inflight)
        self._inflight = []
        self._flush_quality()
        self.db.close()
