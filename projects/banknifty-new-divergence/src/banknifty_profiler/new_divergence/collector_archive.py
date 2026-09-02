"""Read collector tar archives without unpacking their raw payloads.

Only BankNifty index, its metadata-selected futures contract, and compact OI
snapshots are normalized.  Selected records are externally sorted in bounded
chunks because tar member order is not assumed to be chronological.
"""

from __future__ import annotations

from contextlib import ExitStack
from datetime import date, datetime
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import re
import tarfile
import tempfile
from typing import BinaryIO, Iterator, Mapping
import uuid

from .clock import IST, iso_utc, parse_instant, session_date
from .contracts import EventKind, MarketEvent

RAW_MEMBER = re.compile(r"(?:^|/)raw/(?P<session>\d{4}-\d{2}-\d{2})/events_(?P<hour>\d{2})\.jsonl$")
OI_MEMBER = re.compile(r"(?:^|/)oi/(?P<session>\d{4}-\d{2}-\d{2})/oi_(?P<hour>\d{2})\.jsonl$")
STARTUP_MEMBER = re.compile(r"(?:^|/)metadata/startup_[^/]+\.json$")


class ActiveContractUnavailable(ValueError):
    """Raised when neither source metadata nor an audit override selects Futures."""


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _identifier(member: str, line_number: int, raw: bytes, kind: EventKind) -> str:
    digest = hashlib.sha256()
    digest.update(member.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(line_number).encode("ascii"))
    digest.update(b"\0")
    digest.update(raw)
    return f"collector-{kind.value.lower()}-{digest.hexdigest()[:24]}"


def _is_index_symbol(symbol: str) -> bool:
    leaf = symbol.upper().rsplit(":", 1)[-1]
    return leaf in {"NIFTYBANK-INDEX", "BANKNIFTY-INDEX"}


def _is_banknifty_future(symbol: str) -> bool:
    leaf = symbol.upper().rsplit(":", 1)[-1]
    return leaf.startswith("BANKNIFTY") and leaf.endswith("FUT") and not leaf.endswith(("CEFUT", "PEFUT"))


class CollectorArchiveAdapter:
    """Normalize one session from a `.tar.gz` collector delivery.

    `start` and `end` are absolute instants.  They constrain records, never
    rewrite source timestamps.  The metadata-provided contract symbol is used
    when present; callers may explicitly pin a symbol for independent audit.
    """

    def __init__(
        self,
        archive: Path,
        session: date,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        futures_symbol: str | None = None,
        include_auxiliary: bool = True,
        chunk_size: int = 25_000,
        strict: bool = True,
    ) -> None:
        self.archive = Path(archive).resolve()
        if not self.archive.is_file():
            raise FileNotFoundError(self.archive)
        self.session = session
        self.start = None if start is None else parse_instant(start, field="archive start")
        self.end = None if end is None else parse_instant(end, field="archive end")
        if self.start is not None and session_date(self.start) != session:
            raise ValueError("archive start is outside the requested exchange session")
        if self.end is not None and session_date(self.end) != session:
            raise ValueError("archive end is outside the requested exchange session")
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("archive end precedes start")
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self.requested_futures_symbol = None if futures_symbol is None else futures_symbol.upper()
        self.include_auxiliary = include_auxiliary
        self.chunk_size = chunk_size
        self.strict = strict
        self.stats: dict[str, object] = {}
        self._metadata_future: str | None = None
        self._metadata_index: str | None = None
        self._metadata_started_at: datetime | None = None
        self._sequence = 0
        self._exclusions: dict[str, int] = {}

    @property
    def selected_futures_symbol(self) -> str | None:
        return self.requested_futures_symbol or self._metadata_future

    @property
    def selected_index_symbol(self) -> str | None:
        return self._metadata_index

    def _exclude(self, reason: str) -> None:
        self._exclusions[reason] = self._exclusions.get(reason, 0) + 1

    def _within_window(self, timestamp: datetime) -> bool:
        if session_date(timestamp) != self.session:
            return False
        return not (
            self.start is not None and timestamp < self.start
            or self.end is not None and timestamp > self.end
        )

    def _wanted_hours(self) -> set[int] | None:
        if self.start is None or self.end is None:
            return None
        first = self.start.astimezone(IST).hour
        last = self.end.astimezone(IST).hour
        return set(range(first, last + 1))

    def _consume_startup(self, handle: BinaryIO) -> None:
        try:
            row = json.loads(handle.read().decode("utf-8"))
            started = parse_instant(row["started_at"], field="startup started_at")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return
        if session_date(started) != self.session:
            return
        if self._metadata_started_at is not None and started <= self._metadata_started_at:
            return
        futures = [
            str(symbol).upper() for symbol in row.get("future_oi_symbols", [])
            if _is_banknifty_future(str(symbol))
        ]
        indexes = [
            str(symbol).upper() for symbol in row.get("base_quote_symbols", [])
            if _is_index_symbol(str(symbol))
        ]
        self._metadata_future = futures[0] if len(futures) == 1 else None
        self._metadata_index = indexes[0] if len(indexes) == 1 else None
        self._metadata_started_at = started

    def _raw_event(self, row: Mapping[str, object], member: str, line_number: int, raw: bytes) -> MarketEvent | None:
        message = row.get("message")
        if not isinstance(message, Mapping):
            return None
        symbol = str(message.get("symbol", "")).upper()
        if _is_index_symbol(symbol):
            if self._metadata_index is not None and symbol != self._metadata_index:
                return None
            kind = EventKind.INDEX_TICK
        elif _is_banknifty_future(symbol):
            selected = self.selected_futures_symbol
            if selected is None:
                raise ActiveContractUnavailable(
                    "active BankNifty Futures is absent from startup metadata; provide futures_symbol"
                )
            if symbol != selected:
                return None
            kind = EventKind.FUTURES_TICK
        else:
            return None
        price = message.get("ltp", message.get("last_price"))
        if not _finite(price) or float(price) <= 0:
            self._exclude(f"{kind.value}_NON_PRICE_UPDATE")
            return None
        receipt = parse_instant(row["received_at"], field="collector received_at")
        if not self._within_window(receipt):
            return None
        event_time = parse_instant(row["event_time"], field="collector event_time")
        self._sequence += 1
        return MarketEvent(
            event_id=_identifier(member, line_number, raw, kind),
            session=self.session,
            kind=kind,
            symbol=symbol,
            event_timestamp=event_time,
            receipt_timestamp=receipt,
            sequence=self._sequence,
            values={
                "price": float(price),
                "volume": message.get("vol_traded_today", message.get("volume")),
                "timestamp_source": row.get("timestamp_source", ""),
                "timestamp_anomaly": bool(row.get("timestamp_anomaly", False)),
                "aggregation_status": row.get("aggregation_status", ""),
                "source_member": member,
                "source_line": line_number,
            },
        )

    def _future_oi_event(
        self, row: Mapping[str, object], member: str, line_number: int, raw: bytes
    ) -> MarketEvent | None:
        receipt_value = row.get("received_at")
        if receipt_value is None:
            return None
        receipt = parse_instant(receipt_value, field="OI received_at")
        if not self._within_window(receipt):
            return None
        response = row.get("response")
        if not isinstance(response, Mapping):
            return None
        payload = response.get("d")
        if not isinstance(payload, Mapping):
            return None
        requested = str(row.get("requested_symbol", "")).upper()
        selected = self.selected_futures_symbol
        candidates = [
            (str(symbol).upper(), values)
            for symbol, values in payload.items()
            if isinstance(values, Mapping) and _is_banknifty_future(str(symbol))
        ]
        if requested and _is_banknifty_future(requested):
            candidates.sort(key=lambda item: item[0] != requested)
        if candidates and selected is None:
            raise ActiveContractUnavailable(
                "active BankNifty Futures is absent from startup metadata; provide futures_symbol"
            )
        if selected is not None:
            candidates = [item for item in candidates if item[0] == selected]
        if not candidates:
            return None
        symbol, values = candidates[0]
        oi = values.get("oi")
        if not _finite(oi):
            raise ValueError("selected FUTURES_OI row has no finite oi")
        self._sequence += 1
        kind = EventKind.FUTURES_OI
        return MarketEvent(
            event_id=_identifier(member, line_number, raw, kind),
            session=self.session,
            kind=kind,
            symbol=symbol,
            event_timestamp=parse_instant(row["request_time"], field="OI request_time"),
            receipt_timestamp=receipt,
            sequence=self._sequence,
            values={
                "oi": float(oi),
                "previous_oi": values.get("pdoi"),
                "price": values.get("ltp"),
                "volume": values.get("v"),
                "expiry": values.get("expiry"),
                "source_member": member,
                "source_line": line_number,
            },
        )

    def _option_pressure_event(
        self, row: Mapping[str, object], member: str, line_number: int, raw: bytes
    ) -> MarketEvent | None:
        receipt_value = row.get("received_at")
        if receipt_value is None:
            return None
        receipt = parse_instant(receipt_value, field="option received_at")
        if not self._within_window(receipt):
            return None
        response = row.get("response")
        data = response.get("data") if isinstance(response, Mapping) else None
        chain = data.get("optionsChain") if isinstance(data, Mapping) else None
        if not isinstance(chain, list):
            return None
        expiry_data = data.get("expiryData") if isinstance(data, Mapping) else None
        selected_expiry = None
        if (
            isinstance(expiry_data, list)
            and expiry_data
            and isinstance(expiry_data[0], Mapping)
        ):
            selected_expiry = expiry_data[0].get("date") or expiry_data[0].get("expiry")
        if selected_expiry is None:
            raise ValueError("selected BankNifty option chain has no expiry identity")
        call_change = put_change = call_oi = put_oi = 0.0
        call_count = put_count = 0
        strike_oi = []
        seen_symbols: set[str] = set()
        for option in chain:
            if not isinstance(option, Mapping):
                continue
            symbol = str(option.get("symbol", "")).upper()
            if "BANKNIFTY" not in symbol:
                continue
            option_type = str(option.get("option_type", "")).upper()
            if option_type not in {"CE", "PE"}:
                continue
            if not _finite(option.get("oi")) or not _finite(option.get("oich")):
                raise ValueError("selected BankNifty option row has incomplete OI evidence")
            oi = float(option["oi"])
            change = float(option["oich"])
            if not symbol or symbol in seen_symbols:
                raise ValueError("selected BankNifty option chain has duplicate/missing symbols")
            if not _finite(option.get("strike_price")):
                raise ValueError("selected BankNifty option row has no finite strike")
            price = option.get("ltp")
            if price is not None and not _finite(price):
                raise ValueError("selected BankNifty option row has a non-finite price")
            volume = option.get("volume")
            if volume is not None and not _finite(volume):
                raise ValueError("selected BankNifty option row has a non-finite volume")
            seen_symbols.add(symbol)
            strike_oi.append({
                "expiry": str(selected_expiry),
                "option_type": option_type,
                "strike": float(option["strike_price"]),
                "oi": oi,
                "price": None if price is None else float(price),
                "volume": None if volume is None else float(volume),
                "symbol": symbol,
            })
            if option_type == "CE":
                call_change += change
                call_oi += oi
                call_count += 1
            elif option_type == "PE":
                put_change += change
                put_oi += oi
                put_count += 1
        if call_count + put_count == 0:
            return None
        denominator = abs(put_change) + abs(call_change)
        score = 0.0 if denominator == 0 else (put_change - call_change) / denominator
        self._sequence += 1
        kind = EventKind.OPTION_PRESSURE
        return MarketEvent(
            event_id=_identifier(member, line_number, raw, kind),
            session=self.session,
            kind=kind,
            symbol=str(row.get("input_symbol", "BANKNIFTY")),
            event_timestamp=parse_instant(row["request_time"], field="option request_time"),
            receipt_timestamp=receipt,
            sequence=self._sequence,
            values={
                "score": score,
                "metric": "PUT_MINUS_CALL_OI_CHANGE_NORMALIZED",
                "put_oi_change": put_change,
                "call_oi_change": call_change,
                "put_oi": put_oi,
                "call_oi": call_oi,
                "put_contracts": put_count,
                "call_contracts": call_count,
                "selected_expiry": str(selected_expiry),
                "strike_oi": sorted(
                    strike_oi,
                    key=lambda item: (
                        str(item["option_type"]),
                        float(item["strike"]),
                        str(item["symbol"]),
                    ),
                ),
                "source_member": member,
                "source_line": line_number,
            },
        )

    def _oi_events(
        self,
        row: Mapping[str, object],
        member: str,
        line_number: int,
        raw: bytes,
    ) -> tuple[MarketEvent, ...]:
        source = str(row.get("source", ""))
        if source == "future_depth":
            event = self._future_oi_event(row, member, line_number, raw)
        elif source == "option_chain":
            event = self._option_pressure_event(row, member, line_number, raw)
        else:
            event = None
        return () if event is None else (event,)

    def _flush_chunk(self, directory: Path, index: int, events: list[MarketEvent]) -> Path:
        events.sort(key=lambda event: event.sort_key)
        path = directory / f"chunk-{index:06d}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
        events.clear()
        return path

    def _build_chunks(self, directory: Path) -> list[Path]:
        chunks: list[Path] = []
        buffer: list[MarketEvent] = []
        selected_members: list[str] = []
        wanted_hours = self._wanted_hours()
        completed_raw_hours: set[int] = set()
        completed_oi_hours: set[int] = set()
        source_lines = invalid_lines = 0
        invalid_reasons: dict[str, int] = {}
        counts: dict[str, int] = {}
        with tarfile.open(self.archive, mode="r|gz") as archive:
            for member in archive:
                if not member.isfile():
                    continue
                raw_match = RAW_MEMBER.search(member.name)
                oi_match = OI_MEMBER.search(member.name)
                startup = STARTUP_MEMBER.search(member.name)
                if startup:
                    handle = archive.extractfile(member)
                    if handle is not None:
                        self._consume_startup(handle)
                    continue
                source_kind = None
                raw_hour = int(raw_match.group("hour")) if raw_match else None
                oi_hour = int(oi_match.group("hour")) if oi_match else None
                if (
                    raw_match
                    and raw_match.group("session") == self.session.isoformat()
                    and (wanted_hours is None or raw_hour in wanted_hours)
                ):
                    source_kind = "raw"
                elif (
                    self.include_auxiliary
                    and oi_match
                    and oi_match.group("session") == self.session.isoformat()
                    and (wanted_hours is None or oi_hour in wanted_hours)
                ):
                    source_kind = "oi"
                if source_kind is None:
                    continue
                selected_members.append(member.name)
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                for line_number, raw in enumerate(handle, 1):
                    if not raw.strip():
                        continue
                    source_lines += 1
                    try:
                        row = json.loads(raw)
                        if not isinstance(row, Mapping):
                            raise ValueError("row is not an object")
                        if source_kind == "raw":
                            event = self._raw_event(row, member.name, line_number, raw)
                            events = () if event is None else (event,)
                        else:
                            events = self._oi_events(row, member.name, line_number, raw)
                    except ActiveContractUnavailable:
                        raise
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                        invalid_lines += 1
                        reason = f"{type(error).__name__}:{str(error)[:160]}"
                        invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1
                        continue
                    for event in events:
                        buffer.append(event)
                        counts[event.kind.value] = counts.get(event.kind.value, 0) + 1
                        if len(buffer) >= self.chunk_size:
                            chunks.append(self._flush_chunk(directory, len(chunks), buffer))
                if source_kind == "raw":
                    assert raw_hour is not None
                    completed_raw_hours.add(raw_hour)
                else:
                    assert oi_hour is not None
                    completed_oi_hours.add(oi_hour)
                # A bounded intrahour replay can finish as soon as every named
                # hour member has been consumed.  This relies only on unique
                # archive member names, never on physical member ordering.
                if wanted_hours is not None and completed_raw_hours >= wanted_hours and (
                    not self.include_auxiliary or completed_oi_hours >= wanted_hours
                ):
                    break
        if buffer:
            chunks.append(self._flush_chunk(directory, len(chunks), buffer))
        self.stats = {
            "schema": "COLLECTOR_ARCHIVE_NORMALIZATION_V1",
            "archive": str(self.archive),
            "archive_size_bytes": self.archive.stat().st_size,
            "session": self.session.isoformat(),
            "start": None if self.start is None else iso_utc(self.start),
            "end": None if self.end is None else iso_utc(self.end),
            "selected_index_symbol": self.selected_index_symbol,
            "selected_futures_symbol": self.selected_futures_symbol,
            "selected_members": selected_members,
            "source_lines_seen": source_lines,
            "invalid_lines": invalid_lines,
            "invalid_reasons": dict(sorted(invalid_reasons.items())),
            "excluded_rows": dict(sorted(self._exclusions.items())),
            "normalized_counts": counts,
            "chunk_count": len(chunks),
            "ordering": "RECEIPT_TIMESTAMP_SEQUENCE_EVENT_ID",
            "raw_payload_extracted": False,
            "timestamp_fallback": "NONE",
            "strict_input": self.strict,
        }
        if self.strict and invalid_lines:
            leading = max(invalid_reasons, key=invalid_reasons.get)
            raise ValueError(
                f"collector archive contains {invalid_lines} invalid selected JSONL rows; "
                f"most frequent: {leading} ({invalid_reasons[leading]})"
            )
        return chunks

    def stream(self) -> Iterator[MarketEvent]:
        with tempfile.TemporaryDirectory(prefix="banknifty-normalized-") as temporary:
            chunks = self._build_chunks(Path(temporary))
            with ExitStack() as stack:
                handles = [stack.enter_context(path.open(encoding="utf-8")) for path in chunks]
                heap: list[tuple[tuple, int, MarketEvent]] = []
                for index, handle in enumerate(handles):
                    line = handle.readline()
                    if line:
                        event = MarketEvent.from_dict(json.loads(line))
                        heapq.heappush(heap, (event.sort_key, index, event))
                while heap:
                    _, index, event = heapq.heappop(heap)
                    yield event
                    line = handles[index].readline()
                    if line:
                        following = MarketEvent.from_dict(json.loads(line))
                        heapq.heappush(heap, (following.sort_key, index, following))

    def write_manifest(self, path: Path) -> None:
        if not self.stats:
            raise RuntimeError("stream must be consumed before writing its manifest")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(self.stats, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
