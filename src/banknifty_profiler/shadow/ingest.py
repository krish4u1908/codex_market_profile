from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
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

    The persisted mtime detects ordinary same-inode rewrites.  Head/tail
    content makes that identity independently content-backed without rescanning
    a multi-GB growing file on every poll.
    """
    window = 4096
    digest = hashlib.sha256()
    digest.update(str(offset).encode())
    if offset <= 0:
        return digest.hexdigest()
    with path.open("rb") as handle:
        head = handle.read(min(window, offset))
        digest.update(head)
        if offset > window:
            handle.seek(max(0, offset - window))
            digest.update(handle.read(min(window, offset)))
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
            "id text primary key,session_date text not null,payload text not null)"
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
            "projection_padding_lines": 0,
            "started": time.monotonic(), "max_buffer": 0,
        }

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
        with self.db:
            self._release_selected_candidates()
        pending_before = self._pending_observations()
        pending_files = {observation.source_file for observation in pending_before}
        pending_files.update(
            json.loads(payload).get("source_file", "")
            for (payload,) in self.db.execute(
                "select payload from futures_candidate_outbox"
            )
        )
        paths = (
            self.discover()
            if source_paths is None
            else self._validated_source_paths(source_paths)
        )
        self._poll_incomplete = {}
        for path in paths:
            rel = str(path.relative_to(self.data))
            if rel in pending_files:
                checkpoint = self.checkpoints.get(rel, {"offset": 0})
                self._poll_incomplete[rel] = checkpoint.get("offset", 0) < path.stat().st_size
            else:
                self._read_file(path)
        if self._checkpoint_dirty:
            self._flush_checkpoints()
            atomic_json(self.checkpoint_path, self.checkpoints)
            self._checkpoint_dirty = False
        watermark = self._safe_watermark()
        observations = self._pending_observations(watermark)
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

    def _pending_observations(self, watermark: object = ...) -> list[TypedObservation]:
        rows = self.db.execute("select payload from observation_outbox").fetchall()
        observations = [TypedObservation(**json.loads(payload)) for (payload,) in rows]
        if watermark is ...:
            return observations
        if watermark is None:
            return []
        return [
            observation for observation in observations
            if parse_timestamp(
                observation.receipt_timestamp,
                field_name="outbox receipt watermark",
            ) <= watermark
        ]

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
        if checkpoint["identity"] != identity:
            self._poll_incomplete[rel] = True
            self._refuse("FILE_REPLACED", rel, checkpoint, stat)
            return []
        if stat.st_size < checkpoint["offset"]:
            self._poll_incomplete[rel] = True
            self._refuse("FILE_TRUNCATED", rel, checkpoint, stat)
            return []
        if checkpoint["offset"] > 0:
            expected_fingerprint = str(checkpoint.get("prefix_fingerprint", ""))
            expected_mtime = int(checkpoint.get("mtime_ns_at_commit", 0) or 0)
            current_fingerprint = _committed_prefix_fingerprint(path, checkpoint["offset"])
            if (
                expected_fingerprint
                and (
                    current_fingerprint != expected_fingerprint
                    or (
                        stat.st_size == checkpoint["offset"]
                        and expected_mtime
                        and stat.st_mtime_ns != expected_mtime
                    )
                )
            ):
                self._poll_incomplete[rel] = True
                self._refuse("FILE_REPLACED_IN_PLACE", rel, checkpoint, stat)
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
        with path.open("rb") as handle:
            handle.seek(checkpoint["offset"])
            chunk = handle.read(min(self.read_limit, stat.st_size - checkpoint["offset"]))
        self.metrics["bytes"] += len(chunk)
        self.metrics["max_buffer"] = max(self.metrics["max_buffer"], len(chunk))
        last_newline = chunk.rfind(b"\n")
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
            "prefix_fingerprint": _committed_prefix_fingerprint(path, offset),
            "mtime_ns_at_commit": stat.st_mtime_ns,
        }
        self._persist_raw_batch(
            staged, rel=rel, stream_frontier=frontier, checkpoint=checkpoint,
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
                "insert into futures_candidate_outbox(id,session_date,payload) values (?,?,?)",
                [
                    (
                        observation.observation_id,
                        observation.session_date,
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
            self._release_selected_candidates()

    def _release_selected_candidates(self) -> None:
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
            candidate = TypedObservation(**json.loads(payload))
            classification = self.symbols.classify(
                candidate.source_symbol, source_kind="market", session_date=session,
            )
            if classification.instrument_class is InstrumentClass.FUTURES:
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
    ) -> None:
        timestamp = now()
        quality_event_id = event_id("QUALITY", reason, key, rel, row, offset)
        if quality_event_id in self._quality_seen or quality_event_id in self._quality_pending_ids:
            return
        self._quality_pending.append({
            "event_id": quality_event_id,
            "session_date": rel.split("/")[1],
            "effective_timestamp": timestamp, "publication_timestamp": timestamp,
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
