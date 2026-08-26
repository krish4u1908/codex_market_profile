"""Incremental, repository-owned wiring for the verified analytical stack.

The frozen analytical modules remain the only authority for calculations.  This
module adapts typed live observations into their canonical input frames, keeps a
bounded per-session cache, and publishes only previously unseen material rows.
It deliberately contains no trading, signalling, or threshold logic.
"""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

import pandas as pd

from banknifty_profiler.context import availability as context_availability
from banknifty_profiler.cross_layer import state as cross_layer_state
from banknifty_profiler.divergence import dependency as divergence_dependency
from banknifty_profiler.divergence import detector as divergence_detector
from banknifty_profiler.gui import adapter as gui_adapter
from banknifty_profiler.inventory import engine as inventory_engine
from banknifty_profiler.lifecycle import raw_engine as lifecycle_engine
from banknifty_profiler.participation import raw_engine as participation_engine
from banknifty_profiler.participation import views as participation_views
from banknifty_profiler.raw_io import reader as raw_reader
from banknifty_profiler.runtime.timestamps import parse_timestamp, parse_timestamp_series
from banknifty_profiler.shadow.ledger import AppendOnlyLedger, atomic_json


INDEX_SYMBOL = "NSE:NIFTYBANK-INDEX"
KNOWN_CLASSES = frozenset({"INDEX", "FUTURES", "FUTURES_OI", "CE", "PE"})
CLASS_ORDER = {"INDEX": 0, "FUTURES": 1, "FUTURES_OI": 2, "CE": 3, "PE": 4}
LEDGER_NAMES = (
    "divergence_confirmations",
    "dependency_retriggers",
    "lifecycle_transitions",
    "inventory_winner_transitions",
    "participation_transitions",
    "cross_layer_transitions",
    "availability_transitions",
    "stale_recovery_transitions",
    "refusals_data_quality",
)
OBSERVATION_FIELDS = (
    "observation_id", "event_id", "session_date", "instrument_class",
    "canonical_symbol", "source_symbol", "receipt_timestamp",
    "exchange_timestamp", "price", "cumulative_volume", "open_interest",
    "previous_open_interest", "open_interest_change", "strike", "option_type",
    "expiry", "underlying_price", "forward_price", "source_file",
    "source_byte_offset", "source_row_number", "raw_record_id",
    "availability_status", "freshness_status", "out_of_order",
)


def _jsonable(value):
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    return value


def _hash(prefix: str, *parts: object) -> str:
    body = "|".join(json.dumps(_jsonable(part), sort_keys=True, separators=(",", ":"), default=str) for part in parts)
    return prefix + "-" + hashlib.sha256(body.encode()).hexdigest()[:24].upper()


def _as_mapping(observation: object) -> dict:
    if isinstance(observation, Mapping):
        return dict(observation)
    if is_dataclass(observation):
        return asdict(observation)
    if hasattr(observation, "to_dict"):
        return dict(observation.to_dict())
    raise TypeError("live observation must be a typed Mapping or dataclass")


def _number(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _truth(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def _expiry(value):
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return pd.Timestamp(value).date()
    text = str(value).strip()
    try:
        if text.replace(".", "", 1).isdigit() and float(text) > 10_000_000:
            return pd.to_datetime(float(text), unit="s", utc=True).tz_convert("Asia/Kolkata").date()
        parsed = pd.to_datetime(text, dayfirst="/" in text, errors="raise")
        return parsed.date()
    except (TypeError, ValueError, OverflowError):
        return None


def _write_csv(path: Path, rows: Iterable[Mapping[str, object]], fallback_fields: Iterable[str]) -> None:
    values = [_jsonable(dict(row)) for row in rows]
    fields = list(dict.fromkeys(key for row in values for key in row)) or list(fallback_fields)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _source_stream(row: Mapping[str, object]) -> str:
    """Return the physical collector stream, never an inferred instrument."""
    parts = str(row.get("source_file", "")).replace("\\", "/").split("/")
    if "raw" in parts:
        return "raw"
    if "oi" in parts:
        return "oi"
    return "unknown"


class LiveAnalyticalOrchestrator:
    """Route committed typed observations through the canonical processors.

    ``contract`` is the validated R6E shadow contract.  ``ledgers`` may be the
    ingestor's ledger mapping; missing analytical ledgers are created below its
    state root.  Public methods intentionally accept both one-observation
    callbacks and poll-sized batches.
    """

    def __init__(self, contract: Mapping[str, object], ledgers: MutableMapping[str, object] | None = None):
        self.c = dict(contract)
        self.config = dict(self.c.get("config", {}))
        self.state_root = Path(self.c["state_root"])
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_root / "live_analytical_orchestrator.json"
        self.stage_root = self.state_root / "analytical_observation_stage"
        self.stage_root.mkdir(parents=True, exist_ok=True)
        self.max_sessions = int(self.config.get("max_live_sessions", 8))
        self.ledgers: MutableMapping[str, object] = ledgers if ledgers is not None else {}
        for name in LEDGER_NAMES:
            self.ledgers.setdefault(name, AppendOnlyLedger(self.state_root / "ledgers" / f"{name}.jsonl"))
        self._ledger_seen = {name: self._existing_ids(name) for name in LEDGER_NAMES}
        self._sessions: dict[str, dict[str, dict]] = {}
        self._outputs: dict[str, dict] = {}
        self._last_order_key: dict[str, tuple] = {}
        self._dirty_sessions: set[str] = set()
        self._finalized_sessions: set[str] = set()
        self._fixed_cache_info: dict[str, dict] = {}
        self._fixed_profiles_memory: dict[tuple[str, str], tuple[str, dict]] = {}
        self._raw_hash_memory: dict[str, tuple[int, int, str]] = {}
        self._eligibility_memory: dict[tuple[str, str], dict] = {}
        self.callback_invocations = Counter()
        self._load()
        self._load_staged_observations()

    def __call__(self, observation: object):
        return self.on_observation(observation)

    def on_observation(self, observation: object) -> dict:
        """Durably stage one callback row in O(1); ``flush`` runs analytics.

        The ingestor invokes callbacks once per row and has no end-of-poll
        callback.  Eagerly rerunning batch primitives here would be quadratic.
        The live runner therefore calls :meth:`process` with the whole poll, or
        callback users call :meth:`flush` once after the poll.
        """
        self._stage([observation])
        row = _as_mapping(observation)
        session = str(row.get("session_date", ""))
        return self.snapshot(session) if session else self.snapshot()

    def process_observations(self, observations: Iterable[object]) -> dict[str, dict]:
        return self.process(observations)

    def process(self, observations: Iterable[object]) -> dict[str, dict]:
        """Stage a complete poll and recompute each affected session once."""
        changed = self._stage(observations)
        return self.flush(changed)

    def _stage(self, observations: Iterable[object]) -> set[str]:
        """Validate, order, and durably stage rows without analytical work."""
        prepared = []
        for observation in observations:
            try:
                row = self._prepare(observation)
            except (TypeError, ValueError) as error:
                raw = _as_mapping(observation)
                self._quality(raw, "ORCHESTRATOR_OBSERVATION_REFUSED", str(error))
                continue
            prepared.append(row)
        prepared.sort(key=self._order_key)
        changed: set[str] = set()
        for row in prepared:
            session = row["session_date"]
            if row["instrument_class"] not in KNOWN_CLASSES:
                self._quality(row, "UNKNOWN_SYMBOL", row.get("source_symbol", ""))
                continue
            if session in self._finalized_sessions:
                self._quality(row, "FINALIZED_SESSION_RECEIPT", session)
                continue
            bucket = self._sessions.setdefault(session, {})
            identity = row["observation_id"]
            # A checkpoint rewind or callback retry is idempotent, not a late
            # analytical receipt.  Test identity before the high-water mark.
            if identity in bucket:
                continue
            key = self._order_key(row)
            prior = self._last_order_key.get(session)
            if _truth(row.get("out_of_order")) or (prior is not None and key < prior):
                self._quality(row, "OUT_OF_ORDER_ANALYTICAL_RECEIPT", f"previous={prior!r} current={key!r}")
                continue
            bucket[identity] = row
            AppendOnlyLedger(self.stage_root / f"{session}.jsonl").append(row)
            self._last_order_key[session] = key if prior is None or key >= prior else prior
            changed.add(session)
        if changed:
            self._evict_sessions()
            self._dirty_sessions.update(changed)
        return changed

    def flush(self, session_dates: Iterable[str] | None = None) -> dict[str, dict]:
        """Run canonical batch primitives once for each dirty live session."""
        requested = set(session_dates) if session_dates is not None else set(self._dirty_sessions)
        targets = requested & set(self._dirty_sessions)
        if not targets:
            return {}
        previous = self._outputs
        computed = self._compute_sessions(targets)
        self._publish({session: computed[session] for session in targets}, previous)
        self._outputs = computed
        self._dirty_sessions.difference_update(targets)
        self._persist()
        return {session: self.snapshot(session) for session in sorted(targets)}

    def finalize_session(self, session_date: str) -> dict:
        """Flush and close one session against subsequent late callbacks."""
        self.flush([session_date])
        self._finalized_sessions.add(session_date)
        self._persist()
        return self.snapshot(session_date)

    def snapshot(self, session_date: str | None = None) -> dict:
        if not self._outputs:
            return self._empty_snapshot(session_date or "")
        selected = session_date or max(self._outputs)
        value = self._outputs.get(selected)
        return json.loads(json.dumps(value if value is not None else self._empty_snapshot(selected), default=str))

    def snapshot_all(self) -> dict[str, dict]:
        return {session: self.snapshot(session) for session in sorted(self._outputs)}

    def _prepare(self, observation: object) -> dict:
        raw = _as_mapping(observation)
        source_identifiers = raw.get("source_receipt_identifiers")
        source_identifiers = source_identifiers if isinstance(source_identifiers, Mapping) else {}
        row = {field: raw.get(field) for field in OBSERVATION_FIELDS}
        row["observation_id"] = str(raw.get("observation_id") or raw.get("event_id") or raw.get("raw_record_id") or "")
        if not row["observation_id"]:
            row["observation_id"] = _hash("OBS", raw.get("source_file"), raw.get("source_byte_offset"), raw.get("source_row_number"))
        instrument = str(raw.get("instrument_class") or raw.get("reason") or "UNKNOWN_SYMBOL").upper()
        aliases = {"CALL": "CE", "PUT": "PE", "FUTURE": "FUTURES_OI", "OPTION_OI": "UNKNOWN_SYMBOL", "IGNORED": "UNKNOWN_SYMBOL"}
        row["instrument_class"] = aliases.get(instrument, instrument)
        receipt = raw.get("receipt_timestamp") or raw.get("effective_timestamp")
        parsed = parse_timestamp(receipt, field_name="live analytical receipt timestamp")
        row["receipt_timestamp"] = parsed.isoformat()
        exchange = raw.get("exchange_timestamp") or raw.get("event_timestamp")
        row["exchange_timestamp"] = parse_timestamp(exchange, field_name="exchange event timestamp").isoformat() if exchange else None
        row["session_date"] = str(raw.get("session_date") or parsed.date().isoformat())
        row["canonical_symbol"] = str(raw.get("canonical_symbol") or raw.get("source_symbol") or raw.get("symbol") or "")
        row["source_symbol"] = str(raw.get("source_symbol") or raw.get("symbol") or row["canonical_symbol"])
        row["price"] = _number(raw.get("price", raw.get("last_price")))
        row["cumulative_volume"] = _number(raw.get("cumulative_volume", raw.get("volume")))
        row["open_interest"] = _number(raw.get("open_interest", raw.get("oi")))
        row["previous_open_interest"] = _number(raw.get("previous_open_interest"))
        row["open_interest_change"] = _number(raw.get("open_interest_change", raw.get("delta_oi")))
        row["strike"] = _number(raw.get("strike"))
        row["option_type"] = str(raw.get("option_type") or (row["instrument_class"] if row["instrument_class"] in {"CE", "PE"} else "FUT" if row["instrument_class"] == "FUTURES_OI" else ""))
        row["expiry"] = _jsonable(raw.get("expiry"))
        row["source_file"] = str(raw.get("source_file") or source_identifiers.get("file", ""))
        row["source_byte_offset"] = int(raw.get("source_byte_offset") or source_identifiers.get("byte_offset", 0) or 0)
        row["source_row_number"] = int(raw.get("source_row_number") or source_identifiers.get("source_row", 0) or 0)
        row["raw_record_id"] = str(raw.get("raw_record_id") or raw.get("event_id") or row["observation_id"])
        row["availability_status"] = str(raw.get("availability_status") or raw.get("status") or "AVAILABLE")
        row["freshness_status"] = str(raw.get("freshness_status") or "FRESH")
        row["out_of_order"] = _truth(raw.get("out_of_order"))
        if row["instrument_class"] == "INDEX" and row["canonical_symbol"] != INDEX_SYMBOL:
            raise ValueError(f"unsafe Index identity: {row['canonical_symbol']!r}")
        return _jsonable(row)

    @staticmethod
    def _order_key(row: Mapping[str, object]) -> tuple:
        return (
            parse_timestamp(row["receipt_timestamp"], field_name="live ordering receipt timestamp").value,
            CLASS_ORDER.get(str(row.get("instrument_class")), 99),
            str(row.get("canonical_symbol", "")), str(row.get("source_file", "")),
            int(row.get("source_byte_offset") or 0), int(row.get("source_row_number") or 0),
            str(row.get("observation_id", "")),
        )

    def _compute_sessions(self, targets: set[str]) -> dict[str, dict]:
        """Recompute only dirty sessions, retaining finalized prior outputs."""
        self.callback_invocations = Counter()
        results: dict[str, dict] = dict(self._outputs)
        for session in sorted(targets):
            rows = sorted(self._sessions[session].values(), key=self._order_key)
            market = self._market_frame(rows)
            oi = self._oi_frame(rows)
            futures = self._futures_symbol(rows)
            inventory = self._inventory(session, market, oi, futures)
            basis, frame, candidates = self._divergence(session, market, futures)
            prior_episode_count = sum(len(value.get("episodes", [])) for date_key, value in results.items() if date_key < session)
            candidates.sort(key=lambda row: parse_timestamp(row["confirmation_timestamp"], field_name="divergence confirmation"))
            for ordinal, episode in enumerate(candidates, prior_episode_count + 1):
                episode["episode_id"] = f"BDR1-{episode['evaluation_date']}-{episode['colour']}-{ordinal:03d}"
            series = {session: frame} if frame is not None and not frame.empty else {}
            self.callback_invocations["dependency"] += 1
            dependencies = divergence_dependency.group_episodes(candidates, series)
            # The frozen dependency function numbers groups globally.  Its
            # classifications are session-local; offset only the identity to
            # retain the exact chronological global numbering without opening
            # or recomputing finalized sessions.
            prior_group_count = len({row["dependency_group_id"] for date_key, value in results.items() if date_key < session for row in value.get("dependencies", [])})
            group_map = {}
            for row in dependencies:
                local = row["dependency_group_id"]
                if local not in group_map:
                    group_map[local] = f"HYP-{session}-{prior_group_count + len(group_map) + 1:03d}-{local.rsplit('-', 1)[-1]}"
                row["dependency_group_id"] = group_map[local]
            self.callback_invocations["lifecycle"] += 1
            lifecycle, resolution, responses = lifecycle_engine.build_lifecycle(candidates, dependencies, series, {session: self._index_frame(market)})

            causal_cutoff = max(parse_timestamp(row["receipt_timestamp"]) for row in rows)
            episodes = candidates
            deps = dependencies
            # The frozen batch lifecycle closes unresolved hypotheses at the
            # session boundary.  In live mode that row is not publishable until
            # its effective clock has actually arrived.
            life = []
            for source in lifecycle:
                if parse_timestamp(source["state_entry_timestamp"], field_name="lifecycle effective timestamp") > causal_cutoff:
                    continue
                row = dict(source)
                if row.get("state_exit_timestamp") and parse_timestamp(row["state_exit_timestamp"], field_name="lifecycle exit timestamp") > causal_cutoff:
                    row["state_exit_timestamp"] = ""
                life.append(row)
            dense_resolution = [row for row in resolution if parse_timestamp(row["availability_timestamp"], field_name="resolution availability timestamp") <= causal_cutoff]
            response_rows = responses
            participation = self._participation(session, rows, episodes, deps)
            self.callback_invocations["cross_layer"] += 1
            cross = cross_layer_state.build_material_transitions(inventory, episodes, life, dense_resolution, participation["transitions"])
            availability = self._availability(session, rows, inventory)
            result = {
                "session_date": session,
                "basis": basis,
                "inventory": inventory,
                "episodes": episodes,
                "dependencies": deps,
                "lifecycle": life,
                "resolution": dense_resolution,
                "responses": response_rows,
                "participation_dense": participation["dense"],
                "participation_transitions": participation["transitions"],
                "participation_summaries": participation["summaries"],
                "compatibility_snapshots": participation["compatibility"],
                "participation_view_seal": participation["seal"],
                "cross_layer_transitions": cross,
                "availability": availability,
                "fixed_inventory_cache": self._fixed_cache_info.get(session, {}),
            }
            result["gui_payload"] = self._gui_payload(result)
            result["callback_invocations"] = {key: 1 for key in self.callback_invocations}
            result["counts"] = {
                "observations": len(rows), "basis": len(basis),
                "inventory": len(inventory), "episodes": len(episodes),
                "dependencies": len(deps), "lifecycle": len(life),
                "resolution": len(dense_resolution), "participation_dense": len(participation["dense"]),
                "participation_transitions": len(participation["transitions"]),
                "participation_summaries": len(participation["summaries"]),
                "compatibility_snapshots": len(participation["compatibility"]),
                "cross_layer_transitions": len(cross),
            }
            results[session] = _jsonable(result)
        return results

    def _market_frame(self, rows: list[dict]) -> pd.DataFrame:
        values = []
        for row in rows:
            if _source_stream(row) != "raw" or row["instrument_class"] not in {"INDEX", "FUTURES"}:
                continue
            values.append({
                "session_date": row["session_date"], "symbol": row["canonical_symbol"],
                "event_timestamp": row.get("exchange_timestamp"), "receipt_timestamp": row["receipt_timestamp"],
                "availability_timestamp": row["receipt_timestamp"], "last_price": row.get("price"),
                "cumulative_volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""),
                "source_row": row.get("source_row_number", 0),
            })
        columns = ["session_date", "symbol", "event_timestamp", "receipt_timestamp", "availability_timestamp", "last_price", "cumulative_volume", "source_file", "source_row"]
        frame = pd.DataFrame(values, columns=columns)
        if not frame.empty:
            frame["receipt_timestamp"] = parse_timestamp_series(frame.receipt_timestamp, field_name="market receipt timestamp")
            frame["availability_timestamp"] = frame.receipt_timestamp.copy()
            frame["event_timestamp"] = parse_timestamp_series(frame.event_timestamp, field_name="market event timestamp", allow_missing=True)
            frame["last_price"] = pd.to_numeric(frame.last_price, errors="coerce")
            frame["cumulative_volume"] = pd.to_numeric(frame.cumulative_volume, errors="coerce")
            frame = frame.sort_values(["receipt_timestamp", "symbol", "source_file", "source_row"]).reset_index(drop=True)
        return frame

    def _oi_frame(self, rows: list[dict]) -> pd.DataFrame:
        values = []
        class_name = {"FUTURES_OI": "future", "CE": "call", "PE": "put"}
        for row in rows:
            if _source_stream(row) != "oi" or row["instrument_class"] not in class_name:
                continue
            values.append({
                "session_date": row["session_date"], "symbol": row["canonical_symbol"],
                "instrument_class": class_name[row["instrument_class"]], "expiry_date": _expiry(row.get("expiry")),
                "strike": row.get("strike"), "oi_observation_timestamp": row.get("exchange_timestamp"),
                "oi_receipt_timestamp": row["receipt_timestamp"], "availability_timestamp": row["receipt_timestamp"],
                "oi_close": row.get("open_interest"), "previous_oi": row.get("previous_open_interest"),
                "delta_oi": row.get("open_interest_change"), "instrument_price": row.get("price"),
                "cumulative_volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""),
                "source_row": row.get("source_row_number", 0),
            })
        columns = ["session_date", "symbol", "instrument_class", "expiry_date", "strike", "oi_observation_timestamp", "oi_receipt_timestamp", "availability_timestamp", "oi_close", "previous_oi", "delta_oi", "instrument_price", "cumulative_volume", "source_file", "source_row"]
        frame = pd.DataFrame(values, columns=columns)
        if frame.empty:
            return frame
        frame["oi_receipt_timestamp"] = parse_timestamp_series(frame.oi_receipt_timestamp, field_name="OI receipt timestamp")
        frame["availability_timestamp"] = frame.oi_receipt_timestamp.copy()
        frame["oi_observation_timestamp"] = parse_timestamp_series(frame.oi_observation_timestamp, field_name="OI observation timestamp", allow_missing=True)
        for field in ("strike", "oi_close", "previous_oi", "delta_oi", "instrument_price", "cumulative_volume"):
            frame[field] = pd.to_numeric(frame[field], errors="coerce")
        frame = frame.sort_values(["symbol", "availability_timestamp", "source_file", "source_row"]).reset_index(drop=True)
        grouped = frame.groupby("symbol", observed=True)
        # REST ``prev_oi``/``oich`` describe exchange prior-day fields.  The
        # canonical inventory reader deliberately derives poll-to-poll OI from
        # the current session instead, while the typed envelope retains the raw
        # fields for audit.
        frame["previous_oi"] = grouped.oi_close.shift()
        frame["delta_oi"] = frame.oi_close - frame.previous_oi
        frame["valid_receipt"] = frame.oi_close.notna() & frame.availability_timestamp.notna()
        frame["oi_changed"] = frame.delta_oi.ne(0) & frame.delta_oi.notna()
        frame["duplicate_record"] = frame.duplicated(["symbol", "availability_timestamp", "oi_close", "instrument_price"], keep="first")
        frame.loc[grouped.cumcount().eq(0) | ~frame.valid_receipt | frame.delta_oi.eq(0), "delta_oi"] = float("nan")
        return frame

    @staticmethod
    def _futures_symbol(rows: list[dict]) -> str:
        symbols = [row["canonical_symbol"] for row in rows if row["instrument_class"] in {"FUTURES", "FUTURES_OI"} and str(row.get("canonical_symbol", "")).endswith("FUT")]
        return Counter(symbols).most_common(1)[0][0] if symbols else ""

    def _inventory(self, session: str, market: pd.DataFrame, oi: pd.DataFrame, futures: str) -> list[dict]:
        self.callback_invocations["inventory"] += 1
        rows = [dict(row) for row in self.c.get("fixed_inventory_rows", self.config.get("fixed_inventory_rows", [])) if str(row.get("evaluation_date")) == session]
        future_expiries = sorted(value for value in oi.loc[(oi.instrument_class == "future") & oi.expiry_date.notna(), "expiry_date"].unique()) if not oi.empty else []
        option_expiries = sorted(value for value in oi.loc[oi.instrument_class.isin(["call", "put"]) & oi.expiry_date.notna(), "expiry_date"].unique()) if not oi.empty else []
        if not rows:
            rows.extend(self._fixed_inventory_rows(session, futures, future_expiries[0] if future_expiries else None, option_expiries[0] if option_expiries else None))
        tolerance = float(self.config.get("synchronization_tolerance_ms", 2000)) / 1000
        bin_points = float(self.config.get("inventory_bin_points", 25))
        frames: dict[str, pd.DataFrame] = {}
        if futures and not market.empty and {INDEX_SYMBOL, futures}.issubset(set(market.symbol)):
            price = inventory_engine.price_events(market, session, futures, INDEX_SYMBOL, tolerance)
            frames["BN_REF_FUT_VOLUME_VPOC"] = price
        if futures and not oi.empty and not market.empty and INDEX_SYMBOL in set(market.symbol):
            option_expiries = sorted(value for value in oi.loc[oi.instrument_class.isin(["call", "put"]), "expiry_date"].dropna().unique())
            option_expiry = option_expiries[0] if option_expiries else None
            joined = inventory_engine.oi_events(oi, market, session, futures, option_expiry, INDEX_SYMBOL, tolerance)
            for family in inventory_engine.FAMILIES[1:]:
                frames[family] = joined[joined.family == family].copy()
        for family in inventory_engine.FAMILIES:
            frame = frames.get(family)
            if frame is None or frame.empty:
                continue
            expiry = (future_expiries[0] if future_expiries else None) if family.startswith(("BN_", "FUT_")) else (option_expiries[0] if option_expiries else None)
            rows.extend(inventory_engine.transitions(frame, family, session, futures, expiry, bin_points))
        keyed = {}
        for row in rows:
            key = (row.get("horizon"), row.get("family"), row.get("control_effective_timestamp"), row.get("control_value"))
            keyed[key] = _jsonable(row)
        return [keyed[key] for key in sorted(keyed, key=lambda item: tuple(str(value) for value in item))]

    def _fixed_inventory_rows(self, session: str, futures: str, futures_expiry, option_expiry) -> list[dict]:
        """Build/cache prior-session profiles with canonical inventory functions."""
        data_value = self.c.get("data_root")
        if not data_value or not futures:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "RAW_ROOT_OR_SELECTED_FUTURES_MISSING"}
            return []
        data_root = Path(data_value)
        raw_root = data_root / "raw"
        oi_root = data_root / "oi"
        if not raw_root.is_dir() or not oi_root.is_dir() or "research" in data_root.resolve().parts:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "PERMITTED_RAW_ROOT_MISSING"}
            return []
        memory_key = (session, futures)
        if memory_key in self._fixed_profiles_memory:
            key, cached = self._fixed_profiles_memory[memory_key]
            return self._materialize_fixed_inventory(session, futures, futures_expiry, option_expiry, key, cached, True)
        common = sorted({path.name for path in raw_root.iterdir() if path.is_dir()} & {path.name for path in oi_root.iterdir() if path.is_dir()})
        prior = [value for value in common if value < session]
        if not prior:
            self._fixed_cache_info[session] = {"status": "UNAVAILABLE", "reason": "NO_PRIOR_RAW_SESSIONS"}
            return []
        canonical_config = {
            "index_symbol": INDEX_SYMBOL,
            "futures_symbol": futures,
            "discovery_start": prior[0],
            "discovery_end": prior[-1],
            "maximum_missing_oi_minutes": int(self.config.get("inventory_maximum_missing_oi_minutes", 0)),
            "join_tolerance_seconds": float(self.config.get("inventory_join_tolerance_seconds", 5)),
            "bin_points": float(self.config.get("inventory_bin_points", 25)),
        }
        paths = []
        for source_session in prior:
            paths.extend(sorted((raw_root / source_session).glob("events_*.jsonl")))
            paths.extend(sorted((oi_root / source_session).glob("oi_*.jsonl")))
        raw_hashes = {str(path.relative_to(data_root)): self._raw_sha(path) for path in paths}
        key = _hash("FIXED", self.c.get("engine_hash", ""), self.c.get("configuration_hash", ""), canonical_config, raw_hashes)
        cache_root = self.state_root / "fixed_inventory_cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        cache_path = cache_root / f"{key}.json"
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text())
            if cached.get("cache_key") != key:
                raise ValueError("fixed inventory cache key mismatch")
            cache_hit = True
        else:
            missing = [value for value in prior if (futures, value) not in self._eligibility_memory]
            if missing:
                discovery_config = {**canonical_config, "discovery_start": missing[0], "discovery_end": missing[-1]}
                discovered, _ = inventory_engine.discover_sessions(data_root, discovery_config)
                for row in discovered:
                    self._eligibility_memory[(futures, row["date"])] = row
            eligibility = [self._eligibility_memory[(futures, value)] for value in prior if (futures, value) in self._eligibility_memory]
            accepted = [row["date"] for row in eligibility if row["status"] == "ACCEPTED"]
            # R6C0I froze 2026-08-17 as rejected; live startup must not silently
            # rehabilitate it through a partial or changed discovery boundary.
            accepted = [value for value in accepted if value < session and value != "2026-08-17"]
            chain = accepted[-3:]
            profiles = []
            frames = {}
            contracts = {}
            for source_session in chain:
                source_oi = raw_reader.load_oi(oi_root, source_session)
                source_futures, source_futures_expiry, source_option_expiry = raw_reader.select_contracts(source_oi, source_session)
                source_market = raw_reader.load_market(raw_root, source_session, {INDEX_SYMBOL, source_futures})
                contracts[source_session] = (source_futures, source_futures_expiry, source_option_expiry)
                frames[source_session] = {
                    "price": inventory_engine.price_events(source_market, source_session, source_futures, INDEX_SYMBOL, canonical_config["join_tolerance_seconds"]),
                    "oi": inventory_engine.oi_events(source_oi, source_market, source_session, source_futures, source_option_expiry, INDEX_SYMBOL, canonical_config["join_tolerance_seconds"]),
                }
            for horizon, count in (("1D", 1), ("2D", 2), ("3D", 3)):
                sources = chain[-count:]
                if len(sources) < count:
                    continue
                for family in inventory_engine.FAMILIES:
                    parts = [frames[value]["price"] if family == "BN_REF_FUT_VOLUME_VPOC" else frames[value]["oi"][frames[value]["oi"].family == family] for value in sources]
                    sample = pd.concat(parts, ignore_index=True)
                    result = inventory_engine.profile(sample, canonical_config["bin_points"])
                    if result is None:
                        continue
                    profiles.append({
                        "horizon": horizon, "family": family, "source_sessions": "|".join(sources),
                        "freshness_receipt_timestamp": inventory_engine.iso(sample.receipt_timestamp.max()),
                        **_jsonable(result),
                    })
            august = next((row for row in eligibility if row.get("date") == "2026-08-17"), None)
            cached = {
                "cache_key": key, "profiles": profiles, "source_chain": chain,
                "eligibility": eligibility, "raw_input_hashes": raw_hashes,
                "august_17_status": "PRESERVED_REJECTION" if "2026-08-17" not in accepted else "ERROR_ACCEPTED",
                "august_17_reason": august.get("reason", "EXPLICIT_FROZEN_REJECTION") if august else "EXPLICIT_FROZEN_REJECTION",
            }
            cached = _jsonable(cached)
            atomic_json(cache_path, cached)
            cache_hit = False
        self._fixed_profiles_memory[memory_key] = (key, cached)
        return self._materialize_fixed_inventory(session, futures, futures_expiry, option_expiry, key, cached, cache_hit)

    def _materialize_fixed_inventory(self, session: str, futures: str, futures_expiry, option_expiry, key: str, cached: Mapping[str, object], cache_hit: bool) -> list[dict]:
        self._fixed_cache_info[session] = {
            "status": "AVAILABLE" if cached.get("profiles") else "INSUFFICIENT_PRIOR_SESSIONS",
            "cache_key": key, "cache_hit": cache_hit, "source_chain": cached.get("source_chain", []),
            "current_session_excluded": session not in cached.get("source_chain", []),
            "august_17_status": cached.get("august_17_status", ""),
            "raw_input_file_count": len(cached.get("raw_input_hashes", {})),
        }
        rows = []
        for profile in cached.get("profiles", []):
            family = profile["family"]
            expiry = futures_expiry if family.startswith(("BN_", "FUT_")) else option_expiry
            if expiry is None:
                continue
            rows.append(inventory_engine.record(
                session, profile["horizon"], family, profile["control_value"], profile["source_sessions"],
                f"{session}T09:15:00+05:30", profile["freshness_receipt_timestamp"], futures, expiry,
                profile["count"], profile["winning_bin_weight"], profile["runner_up_bin"],
                profile["runner_up_weight"], profile["tie_break_reason"],
            ))
        return rows

    def _raw_sha(self, path: Path) -> str:
        """Hash each immutable prior raw file at most once per process."""
        stat = path.stat()
        key = str(path.resolve())
        cached = self._raw_hash_memory.get(key)
        signature = (stat.st_size, stat.st_mtime_ns)
        if cached is not None and cached[:2] == signature:
            return cached[2]
        digest = inventory_engine.sha(path)
        self._raw_hash_memory[key] = (*signature, digest)
        return digest

    def _divergence(self, session: str, market: pd.DataFrame, futures: str):
        self.callback_invocations["synchronization"] += 1
        if not futures or market.empty or not {INDEX_SYMBOL, futures}.issubset(set(market.symbol)):
            return [], None, []
        basis = divergence_detector.causal_basis(market, session, INDEX_SYMBOL, futures, int(self.config.get("synchronization_tolerance_ms", 2000)))
        if not basis:
            return [], None, []
        self.callback_invocations["divergence_detector"] += 1
        frame = divergence_detector.derive(basis)
        candidates = []
        for row in divergence_detector.episodes(frame):
            if row.get("episode_type") not in {"GREEN_CONFIRMED", "RED_CONFIRMED"}:
                continue
            confirmation = parse_timestamp(row["confirmation_timestamp"], field_name="divergence confirmation")
            point = frame[frame.t == confirmation]
            if point.empty:
                continue
            current = point.iloc[-1]
            candidates.append({
                "evaluation_date": session,
                "colour": "GREEN" if row["episode_type"] == "GREEN_CONFIRMED" else "RED",
                "candidate_start_timestamp": row["start_timestamp"],
                "confirmation_timestamp": row["confirmation_timestamp"],
                "episode_end_timestamp": row["end_timestamp"],
                "index_at_confirmation": _jsonable(current["index"]),
                "futures_at_confirmation": _jsonable(current["futures"]),
                "basis_at_confirmation": _jsonable(current["basis"]),
                "index_receipt_timestamp": str(current["index_receipt_timestamp"]),
                "futures_receipt_timestamp": str(current["futures_receipt_timestamp"]),
                "reason_code": "LOCKED_P60_N5_TWO_OF_1M_3M_5M",
            })
        return _jsonable(basis), frame, candidates

    @staticmethod
    def _index_frame(market: pd.DataFrame) -> pd.DataFrame:
        if market.empty:
            return pd.DataFrame(columns=["t", "index"])
        values = market[(market.symbol == INDEX_SYMBOL) & market.receipt_timestamp.notna() & market.last_price.notna()].sort_values(["receipt_timestamp", "source_file", "source_row"])
        return values[["receipt_timestamp", "last_price"]].rename(columns={"receipt_timestamp": "t", "last_price": "index"})

    def _participation(self, session: str, rows: list[dict], episodes: list[dict], dependencies: list[dict]) -> dict:
        self.callback_invocations["participation"] += 1
        store = self._participation_store(rows)
        config = {
            "windows_minutes": list(self.config.get("participation_windows_minutes", [1, 3, 5])),
            "volume_spike_percentile": float(self.config.get("participation_volume_spike_percentile", .9)),
            "oi_spike_percentile": float(self.config.get("participation_oi_spike_percentile", .9)),
            "freshness_seconds": float(self.config.get("freshness_seconds", {}).get("futures_oi", 180)) if isinstance(self.config.get("freshness_seconds"), Mapping) else float(self.config.get("freshness_seconds", 180)),
            "strike_step": int(self.config.get("participation_strike_step", 100)),
            "near_strikes_each_side": int(self.config.get("participation_near_strikes_each_side", 3)),
        }
        futures_rows: list[dict] = []
        option_rows: list[dict] = []
        cutoff = max((parse_timestamp(row["receipt_timestamp"]).to_pydatetime() for row in rows), default=None)
        for episode in episodes:
            confirmation = parse_timestamp(episode["confirmation_timestamp"]).to_pydatetime()
            anchor = {**episode, "confirmation": confirmation, "end": cutoff or confirmation}
            times = [confirmation]
            if cutoff is not None:
                times.extend(sorted({item["receipt"] for values in store.oi.values() for item in values if confirmation < item["receipt"] <= cutoff}))
            for at in times:
                futures, options = participation_engine.participation_at(store, anchor, at, config)
                futures_rows.append(futures)
                option_rows.extend(options)
        return self._build_participation_views(session, futures_rows, option_rows, episodes, dependencies)

    @staticmethod
    def _participation_store(rows: list[dict]) -> participation_engine.RawStore:
        """Mirror ``RawStore.load_raw`` physical-stream lineage exactly."""
        store = participation_engine.RawStore()
        for row in rows:
            receipt = parse_timestamp(row["receipt_timestamp"], field_name="participation receipt").to_pydatetime()
            common = {"receipt": receipt, "price": row.get("price"), "volume": row.get("cumulative_volume"), "source_file": row.get("source_file", ""), "source_row": row.get("source_row_number", 0)}
            if _source_stream(row) == "raw" and row["instrument_class"] in KNOWN_CLASSES:
                store.market.setdefault(row["canonical_symbol"], []).append(common)
            elif _source_stream(row) == "oi" and row["instrument_class"] in {"FUTURES_OI", "CE", "PE"}:
                store.oi.setdefault(row["canonical_symbol"], []).append({**common, "oi": row.get("open_interest"), "strike": row.get("strike"), "option_type": row.get("option_type"), "expiry": str(row.get("expiry") or "")})
        store.finalize()
        return store

    def _build_participation_views(self, session: str, futures: list[dict], options: list[dict], episodes: list[dict], dependencies: list[dict]) -> dict:
        self.callback_invocations["participation_views"] += 1
        dependency = {row["episode_id"]: row for row in dependencies}
        anchors = [{**episode, "dependency_group_id": dependency.get(episode["episode_id"], {}).get("dependency_group_id", "")} for episode in episodes]
        with tempfile.TemporaryDirectory(prefix="r6e-live-views-", dir=self.state_root) as name:
            root = Path(name)
            native = root / "native"
            output = root / "views"
            native.mkdir()
            futures_path = native / "futures_participation.csv"
            options_path = native / "option_participation.csv"
            breadth_path = native / "option_strike_breadth.csv"
            anchor_path = native / "episode_anchors.csv"
            _write_csv(futures_path, futures, ("record_id", "episode_id", "evaluation_date", "observation_timestamp", "receipt_timestamp"))
            _write_csv(options_path, options, ("record_id", "episode_id", "evaluation_date", "observation_timestamp", "receipt_timestamp", "option_type"))
            _write_csv(breadth_path, participation_views.breadth(options), ("episode_id", "observation_timestamp", "selected_strike_count", "supportive_count", "contradictory_count", "mixed", "broad_agreement", "ce_pe_agreement"))
            _write_csv(anchor_path, anchors, ("episode_id", "evaluation_date", "colour", "confirmation_timestamp", "dependency_group_id"))
            seal = participation_views.build(native, anchor_path, breadth_path, output, "stream")
            dense = _read_csv(output / "dense_participation_view.csv")
            transitions = _read_csv(output / "transition_participation_ledger.csv")
            summaries = _read_csv(output / "episode_participation_summary.csv")
            compatibility = _read_csv(output / "legacy_compatibility_snapshot.csv")
        return {"dense": dense, "transitions": transitions, "summaries": summaries, "compatibility": compatibility, "seal": seal}

    def _availability(self, session: str, rows: list[dict], inventory: list[dict]) -> dict:
        latest = {}
        cutoff = max((parse_timestamp(row["receipt_timestamp"]) for row in rows), default=None)
        for row in rows:
            instant = parse_timestamp(row["receipt_timestamp"])
            kind = row["instrument_class"]
            if kind not in latest or instant > latest[kind]:
                latest[kind] = instant
        limits = self.config.get("freshness_seconds", {}) if isinstance(self.config.get("freshness_seconds"), Mapping) else {}
        def fresh(kind: str, seconds: float) -> bool:
            return cutoff is not None and kind in latest and 0 <= (cutoff - latest[kind]).total_seconds() <= seconds
        market = fresh("INDEX", float(limits.get("index", 10))) and fresh("FUTURES", float(limits.get("futures", 10)))
        layers = {}
        for horizon in ("1D", "2D", "3D"):
            present = any(row.get("horizon") == horizon for row in inventory)
            layers[horizon] = context_availability.LayerAvailability(horizon, "AVAILABLE" if present else "MISSING_PRIOR_SESSION", "CACHED_RAW_PRIOR_CONTEXT" if present else "INSUFFICIENT_PRIOR_SESSIONS")
        id_state = "AVAILABLE" if market else "STALE_DATA" if any(kind in latest for kind in ("INDEX", "FUTURES")) else "NOT_YET_AVAILABLE"
        layers["ID"] = context_availability.LayerAvailability("ID", id_state, "FRESH_SYNCHRONIZED_MARKET" if market else "MARKET_INPUT_STALE_OR_MISSING")
        participation_available = fresh("FUTURES_OI", float(limits.get("futures_oi", 180))) or fresh("CE", float(limits.get("ce", 180))) or fresh("PE", float(limits.get("pe", 180)))
        classified = context_availability.classify_context(layers, divergence_inputs_available=market, participation_inputs_available=participation_available)
        return {
            **classified,
            "layers": {horizon: {"state": layer.state, "reason": layer.reason} for horizon, layer in layers.items()},
            "index_state": "AVAILABLE" if fresh("INDEX", float(limits.get("index", 10))) else "STALE_OR_MISSING",
            "futures_state": "AVAILABLE" if fresh("FUTURES", float(limits.get("futures", 10))) else "STALE_OR_MISSING",
            "futures_oi_state": "AVAILABLE" if fresh("FUTURES_OI", float(limits.get("futures_oi", 180))) else "STALE_OR_MISSING",
            "ce_state": "AVAILABLE" if fresh("CE", float(limits.get("ce", 180))) else "STALE_OR_MISSING",
            "pe_state": "AVAILABLE" if fresh("PE", float(limits.get("pe", 180))) else "STALE_OR_MISSING",
            "calculation_timestamp": cutoff.isoformat() if cutoff is not None else "",
        }

    def _gui_payload(self, result: Mapping[str, object]) -> dict:
        self.callback_invocations["gui_projection"] += 1
        basis = [row for row in result["basis"] if row.get("validity_status") == "VALID"]
        price = [{"t": row.get("basis_timestamp", ""), "i": row.get("index_price", ""), "f": row.get("futures_price", ""), "b": row.get("basis_value", ""), "it": row.get("index_receipt_timestamp", ""), "ft": row.get("futures_receipt_timestamp", ""), "a": row.get("absolute_receipt_difference_ms", "")} for row in basis]
        mechanism = [gui_adapter._project(row, ("episode_id", "timestamp", "availability_timestamp", "resolution_mechanism_native", "resolution_mechanism_compatibility", "signed_basis_convergence", "index_contribution", "futures_contribution", "new_extreme_flag", "stalled_extreme_duration_seconds")) for row in result["resolution"]]
        payload = {
            "schema": "R6E_LIVE_SESSION_PAYLOAD_V1",
            "classification": self.config.get("classification", "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"),
            "date": result["session_date"],
            "availability": result["availability"],
            "price": gui_adapter._pack(price),
            "inventory": gui_adapter._pack(result["inventory"]),
            "episodes": gui_adapter._pack(result["episodes"]),
            "dependencies": gui_adapter._pack(result["dependencies"]),
            "lifecycle": gui_adapter._pack(result["lifecycle"]),
            "resolution_mechanisms": gui_adapter._pack(mechanism),
            "participation_dense": gui_adapter._pack(result["participation_dense"]),
            "participation_transitions": gui_adapter._pack(result["participation_transitions"]),
            "participation_summaries": gui_adapter._pack(result["participation_summaries"]),
            "compatibility_snapshots": gui_adapter._pack(result["compatibility_snapshots"]),
            "cross_layer_transitions": gui_adapter._pack(result["cross_layer_transitions"]),
        }
        payload["counts"] = {key: len(value.get("rows", [])) for key, value in payload.items() if isinstance(value, dict) and "rows" in value}
        payload["projection_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return payload

    def _publish(self, outputs: Mapping[str, dict], previous: Mapping[str, dict]) -> None:
        for session, result in outputs.items():
            cutoff = result["availability"].get("calculation_timestamp", "")
            for row in result["episodes"]:
                self._append_once("divergence_confirmations", row, row["episode_id"], cutoff)
            for row in result["dependencies"]:
                self._append_once("dependency_retriggers", row, f"dependency:{row['episode_id']}", cutoff)
            for row in result["lifecycle"]:
                self._append_once("lifecycle_transitions", row, str(row["record_id"]), cutoff)
            for row in result["inventory"]:
                identity = _hash("INVENTORY", row.get("evaluation_date"), row.get("horizon"), row.get("family"), row.get("control_effective_timestamp"), row.get("control_value"))
                self._append_once("inventory_winner_transitions", row, identity, cutoff)
            for row in result["participation_transitions"]:
                self._append_once("participation_transitions", row, str(row["transition_id"]), cutoff)
            for row in result["cross_layer_transitions"]:
                self._append_once("cross_layer_transitions", row, str(row["transition_id"]), cutoff)
            old = previous.get(session, {}).get("availability", {})
            current = result["availability"]
            for component, state in self._availability_states(current).items():
                prior = self._availability_states(old).get(component, "NOT_YET_AVAILABLE")
                if prior == state:
                    continue
                effective = current.get("calculation_timestamp") or cutoff
                event = {
                    "session_date": session, "component": component, "previous_state": prior,
                    "new_state": state, "effective_timestamp": effective,
                    "reason": "MATERIAL_AVAILABILITY_CHANGE",
                }
                identity = _hash("AVAILABILITY", session, component, effective, state)
                self._append_once("availability_transitions", event, identity, cutoff)
                if "STALE" in prior or "STALE" in state:
                    self._append_once("stale_recovery_transitions", event, _hash("STALE", session, component, effective, state), cutoff)

    @staticmethod
    def _availability_states(value: Mapping[str, object]) -> dict[str, str]:
        if not value:
            return {}
        result = {f"HORIZON_{key}": str(item.get("state", "")) for key, item in value.get("layers", {}).items()}
        for key in ("divergence_state", "participation_state", "index_state", "futures_state", "futures_oi_state", "ce_state", "pe_state", "overall_state"):
            if key in value:
                result[key.upper()] = str(value[key])
        return result

    def _append_once(self, ledger_name: str, row: Mapping[str, object], identity: str, calculation_timestamp: str) -> None:
        event_id = identity if identity.startswith(("BDR1-", "R6", "XL-")) else _hash("ANALYTICAL", ledger_name, identity)
        if event_id in self._ledger_seen[ledger_name]:
            return
        value = _jsonable(dict(row))
        value.setdefault("event_id", event_id)
        value.setdefault("calculation_timestamp", calculation_timestamp)
        value.setdefault("publication_timestamp", calculation_timestamp)
        value.setdefault("engine_hash", self.c.get("engine_hash", ""))
        value.setdefault("configuration_hash", self.c.get("configuration_hash", ""))
        value.setdefault("raw_run_id", self.c.get("raw_run_id", ""))
        self.ledgers[ledger_name].append(value)
        self._ledger_seen[ledger_name].add(event_id)

    def _quality(self, row: Mapping[str, object], reason: str, detail: str) -> None:
        identity = _hash("QUALITY", row.get("observation_id") or row.get("event_id") or row.get("raw_record_id"), reason)
        event_id = _hash("ANALYTICAL", "refusals_data_quality", identity)
        if event_id in self._ledger_seen["refusals_data_quality"]:
            return
        receipt = row.get("receipt_timestamp") or row.get("effective_timestamp") or ""
        try:
            effective = parse_timestamp(receipt).isoformat()
        except ValueError:
            effective = datetime.now().astimezone().isoformat()
        value = {
            "event_id": event_id, "session_date": str(row.get("session_date", "")),
            "effective_timestamp": effective, "publication_timestamp": effective,
            "source_receipt_identifiers": {"file": row.get("source_file", ""), "byte_offset": row.get("source_byte_offset", 0), "source_row": row.get("source_row_number", 0)},
            "engine_hash": self.c.get("engine_hash", ""), "configuration_hash": self.c.get("configuration_hash", ""),
            "raw_run_id": self.c.get("raw_run_id", ""), "status": "REFUSED", "reason": reason, "detail": detail,
        }
        self.ledgers["refusals_data_quality"].append(value)
        self._ledger_seen["refusals_data_quality"].add(event_id)

    def _existing_ids(self, ledger_name: str) -> set[str]:
        result = set()
        ledger = self.ledgers[ledger_name]
        rows = ledger.rows() if hasattr(ledger, "rows") else []
        for row in rows:
            identity = row.get("event_id") or row.get("transition_id") or row.get("record_id") or row.get("episode_id")
            if identity:
                result.add(str(identity))
        return result

    def _evict_sessions(self) -> None:
        for session in sorted(self._sessions)[:-self.max_sessions]:
            self._sessions.pop(session, None)
            self._outputs.pop(session, None)
            self._last_order_key.pop(session, None)

    def _persist(self) -> None:
        atomic_json(self.state_path, {
            "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
            "sessions": {session: list(bucket.values()) for session, bucket in self._sessions.items()},
            "outputs": self._outputs,
            "dirty_sessions": sorted(self._dirty_sessions),
            "finalized_sessions": sorted(self._finalized_sessions),
        })

    def _load(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            state = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"analytical orchestrator state corrupt: {error}") from error
        if state.get("version") != "R6E1R_LIVE_ANALYTICAL_STATE_V1":
            raise ValueError("analytical orchestrator state version mismatch")
        for session, rows in state.get("sessions", {}).items():
            self._sessions[session] = {str(row["observation_id"]): row for row in rows}
            if rows:
                self._last_order_key[session] = max(self._order_key(row) for row in rows)
        self._outputs = state.get("outputs", {})
        self._dirty_sessions = set(state.get("dirty_sessions", []))
        self._finalized_sessions = set(state.get("finalized_sessions", []))

    def _load_staged_observations(self) -> None:
        """Recover callback rows durably appended after the last state seal."""
        paths = sorted(self.stage_root.glob("????-??-??.jsonl"))[-self.max_sessions:]
        for path in paths:
            session = path.stem
            if session in self._finalized_sessions and session not in self._sessions:
                continue
            bucket = self._sessions.setdefault(session, {})
            recovered = False
            for row in AppendOnlyLedger(path).rows():
                identity = str(row["observation_id"])
                if identity not in bucket:
                    bucket[identity] = row
                    recovered = True
            if bucket:
                self._last_order_key[session] = max(self._order_key(row) for row in bucket.values())
            if recovered:
                self._dirty_sessions.add(session)
        self._evict_sessions()

    @staticmethod
    def _empty_snapshot(session: str) -> dict:
        empty = {name: [] for name in ("basis", "inventory", "episodes", "dependencies", "lifecycle", "resolution", "responses", "participation_dense", "participation_transitions", "participation_summaries", "compatibility_snapshots", "cross_layer_transitions")}
        return {"session_date": session, **empty, "availability": {"overall_state": "NO_VALID_MARKET_DATA"}, "gui_payload": {}, "callback_invocations": {}, "counts": {key: 0 for key in empty}}


__all__ = ["LiveAnalyticalOrchestrator"]
