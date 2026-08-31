"""Versioned nightly 1D/2D/3D context publication.

The collector tree is always treated as read-only.  A session revision stores
small, composable profile bins in SQLite; multi-day controls are recomputed by
summing those bins rather than averaging daily VPOCs.  Complete context
snapshots are also published as immutable JSON bundles for audit and recovery.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Iterable, Iterator, Mapping, Sequence
import uuid
from zoneinfo import ZoneInfo

import pandas as pd

from banknifty_profiler.inventory.engine import (
    FAMILIES,
    oi_events,
    price_events,
)
from banknifty_profiler.raw_io.reader import load_oi, select_contracts
from banknifty_profiler.runtime.timestamps import parse_timestamp_series

from .output import atomic_json, sha256_file
from .provenance import runtime_identity


IST = ZoneInfo("Asia/Kolkata")
ALGORITHM_VERSION = "NEW_DIVERGENCE_NIGHTLY_CONTEXT_V2_VALUE_AREA"
DATABASE_SCHEMA_VERSION = "2"
CONTEXT_SCHEMA = "NEW_DIVERGENCE_DAILY_CONTEXT_V2"
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
VOLUME_PROFILE_FAMILY = "BN_REF_FUT_VOLUME_VPOC"
# The context calculation contract is unchanged by later GUI-only releases.
# Keeping its producer identity stable lets a verified V1.0.12 context cache be
# reused without reopening multi-gigabyte raw sessions.
CONTEXT_RUNTIME_VERSION = "1.0.12"


@dataclass(frozen=True)
class NightlyContextConfig:
    timezone: str = "Asia/Kolkata"
    session_start: str = "09:15:00"
    session_end: str = "15:30:00"
    edge_grace_minutes: int = 5
    maximum_missing_market_minutes: int = 5
    maximum_missing_oi_minutes: int = 5
    join_tolerance_seconds: int = 5
    bin_points: int = 25
    value_area_fraction: float = 0.70
    near_otm_strikes: int = 3
    stability_seconds: int = 600
    algorithm_version: str = ALGORITHM_VERSION

    def validate(self) -> None:
        if self.timezone != "Asia/Kolkata":
            raise ValueError("nightly context timezone must be Asia/Kolkata")
        start = time.fromisoformat(self.session_start)
        end = time.fromisoformat(self.session_end)
        if start.tzinfo is not None or end.tzinfo is not None or start >= end:
            raise ValueError("session_start/session_end must be ordered IST wall times")
        if (self.session_start, self.session_end) != ("09:15:00", "15:30:00"):
            raise ValueError("V2 fixes the exchange session at 09:15:00–15:30:00 IST")
        for field in (
            "edge_grace_minutes",
            "maximum_missing_market_minutes",
            "maximum_missing_oi_minutes",
            "join_tolerance_seconds",
            "stability_seconds",
        ):
            if int(getattr(self, field)) < 0:
                raise ValueError(f"{field} must be non-negative")
        if self.bin_points != 25:
            raise ValueError("V2 fixes bin_points at 25")
        if not math.isclose(float(self.value_area_fraction), 0.70, rel_tol=0, abs_tol=1e-12):
            raise ValueError("V2 fixes value_area_fraction at 0.70")
        if self.join_tolerance_seconds != 5:
            raise ValueError("V2 fixes the causal Index join tolerance at 5 seconds")
        if self.near_otm_strikes < 1:
            raise ValueError("near_otm_strikes must be positive")
        if self.near_otm_strikes != 3:
            raise ValueError("V2 fixes near_otm_strikes at 3")
        if self.algorithm_version != ALGORITHM_VERSION:
            raise ValueError(f"algorithm_version must be {ALGORITHM_VERSION}")

    @property
    def canonical_json(self) -> str:
        return _canonical_json(asdict(self))

    @property
    def sha256(self) -> str:
        return _sha256_text(self.canonical_json)

    @classmethod
    def from_path(cls, path: Path | None) -> "NightlyContextConfig":
        if path is None:
            result = cls()
        else:
            row = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(row, dict):
                raise ValueError("nightly context configuration must be a JSON object")
            unknown = sorted(set(row) - set(cls.__dataclass_fields__))
            if unknown:
                raise ValueError(f"unknown nightly context settings: {unknown}")
            result = cls(**row)
        result.validate()
        return result


@dataclass(frozen=True)
class ProfileSummary:
    family: str
    total_weight: float
    weighted_price_sum: float
    evidence_count: int
    first_evidence_timestamp: str
    latest_evidence_timestamp: str
    contracts: tuple[str, ...]
    expiries: tuple[str, ...]
    bins: tuple[tuple[float, float, int], ...]


@dataclass(frozen=True)
class SessionRevision:
    revision_id: str
    session_date: str
    status: str
    reasons: tuple[str, ...]
    quick_manifest_sha256: str
    source_manifest_sha256: str
    source_manifest: Mapping[str, object]
    quality: Mapping[str, object]
    index_symbol: str
    futures_symbol: str
    futures_expiry: str | None
    option_expiry: str | None
    profiles: tuple[ProfileSummary, ...]
    reused: bool = False


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _iso(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).isoformat()


def _session_bounds(session: str, config: NightlyContextConfig) -> tuple[pd.Timestamp, pd.Timestamp]:
    day = date.fromisoformat(session)
    start = datetime.combine(day, time.fromisoformat(config.session_start), IST)
    end = datetime.combine(day, time.fromisoformat(config.session_end), IST)
    return pd.Timestamp(start), pd.Timestamp(end)


def _source_files(data_root: Path, session: str) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for kind, directory, pattern in (
        ("raw", data_root / "raw" / session, "events_*.jsonl"),
        ("oi", data_root / "oi" / session, "oi_*.jsonl"),
    ):
        result.extend((kind, path) for path in sorted(directory.glob(pattern)) if path.is_file())
    return result


def _quick_manifest(data_root: Path, session: str) -> tuple[dict[str, object], str]:
    files = []
    for kind, path in _source_files(data_root, session):
        stat = path.stat()
        files.append(
            {
                "kind": kind,
                "path": path.relative_to(data_root).as_posix(),
                "size_bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    value = {
        "schema": "COLLECTOR_SESSION_QUICK_MANIFEST_V1",
        "collector_root": str(data_root),
        "session": session,
        "files": files,
    }
    return value, _sha256_text(_canonical_json(value))


def _is_stable(quick_manifest: Mapping[str, object], stability_seconds: int) -> bool:
    files = quick_manifest.get("files", [])
    if not files:
        return False
    cutoff_ns = int((datetime.now(UTC).timestamp() - stability_seconds) * 1_000_000_000)
    return all(int(row["mtime_ns"]) <= cutoff_ns for row in files)


def _discover_sessions(data_root: Path, cutoff_session: date) -> list[str]:
    raw_root = data_root / "raw"
    oi_root = data_root / "oi"
    if not raw_root.is_dir() or not oi_root.is_dir():
        raise FileNotFoundError(f"collector root must contain raw/ and oi/: {data_root}")
    raw = {path.name for path in raw_root.iterdir() if path.is_dir()}
    oi = {path.name for path in oi_root.iterdir() if path.is_dir()}
    result = []
    for value in raw | oi:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            continue
        if parsed <= cutoff_session:
            result.append(value)
    return sorted(result)


def _scan_sources(
    data_root: Path,
    session: str,
    quick_manifest: Mapping[str, object],
) -> tuple[dict[str, object], Counter[str], int, list[str], list[dict[str, object]]]:
    files = []
    raw_symbols: Counter[str] = Counter()
    malformed_count = 0
    malformed_examples: list[str] = []
    raw_candidates: list[dict[str, object]] = []
    for row in quick_manifest["files"]:
        relative = str(row["path"])
        path = data_root / relative
        nonempty_lines = 0
        parsed_lines = 0
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                digest.update(raw_line)
                if not raw_line.strip():
                    continue
                nonempty_lines += 1
                try:
                    record = json.loads(raw_line.decode("utf-8", errors="strict"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    malformed_count += 1
                    if len(malformed_examples) < 20:
                        malformed_examples.append(f"{relative}:{line_number}")
                    continue
                parsed_lines += 1
                if row["kind"] == "raw" and isinstance(record, dict):
                    message = record.get("message", {})
                    if isinstance(message, dict) and isinstance(message.get("symbol"), str):
                        symbol = message["symbol"]
                        raw_symbols[symbol] += 1
                        upper = symbol.upper()
                        if (
                            ("NIFTYBANK" in upper or "BANKNIFTY" in upper)
                            and (upper.endswith("-INDEX") or "FUT" in upper)
                        ):
                            raw_candidates.append(
                                {
                                    "session_date": session,
                                    "symbol": symbol,
                                    "event_timestamp": record.get("event_time"),
                                    "receipt_timestamp": record.get("received_at"),
                                    "availability_timestamp": record.get("received_at"),
                                    "last_price": message.get("ltp", message.get("last_price")),
                                    "cumulative_volume": message.get(
                                        "vol_traded_today", message.get("volume")
                                    ),
                                    "last_traded_quantity": message.get("last_traded_qty"),
                                    "source_file": str(path),
                                    "source_row": line_number,
                                    "source_quality": "RAW_WEBSOCKET_EVENT",
                                }
                            )
        after = path.stat()
        if after.st_size != int(row["size_bytes"]) or after.st_mtime_ns != int(row["mtime_ns"]):
            raise ValueError(f"source changed during analysis: {relative}")
        files.append(
            {
                **row,
                "sha256": digest.hexdigest(),
                "nonempty_lines": nonempty_lines,
                "parsed_lines": parsed_lines,
            }
        )
    manifest = {
        "schema": "COLLECTOR_SESSION_SOURCE_MANIFEST_V1",
        "collector_root": str(data_root),
        "session": session,
        "files": files,
    }
    manifest["manifest_sha256"] = _sha256_text(_canonical_json(manifest))
    return manifest, raw_symbols, malformed_count, malformed_examples, raw_candidates


def _market_from_candidates(
    rows: Sequence[Mapping[str, object]], symbols: set[str]
) -> pd.DataFrame:
    selected = [dict(row) for row in rows if row["symbol"] in symbols]
    market = pd.DataFrame(selected)
    if market.empty:
        return market
    market["event_timestamp"] = parse_timestamp_series(
        market.event_timestamp,
        field_name="market event timestamp",
        allow_missing=True,
    )
    market["receipt_timestamp"] = parse_timestamp_series(
        market.receipt_timestamp,
        field_name="market receipt timestamp",
    )
    market["availability_timestamp"] = market.receipt_timestamp.copy()
    return market.sort_values(
        ["receipt_timestamp", "symbol", "source_file", "source_row"]
    ).reset_index(drop=True)


def _select_index_symbol(symbols: Counter[str]) -> str:
    preferred = "NSE:NIFTYBANK-INDEX"
    if symbols[preferred]:
        return preferred
    candidates = [
        symbol
        for symbol in symbols
        if symbol.upper().endswith("-INDEX")
        and ("NIFTYBANK" in symbol.upper() or "BANKNIFTY" in symbol.upper())
    ]
    if not candidates:
        return ""
    return sorted(candidates, key=lambda symbol: (-symbols[symbol], symbol))[0]


def _missing_minutes(
    frame: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    timestamp_column: str = "availability_timestamp",
) -> int:
    expected = pd.date_range(start, end - pd.Timedelta(minutes=1), freq="min")
    if frame.empty or timestamp_column not in frame:
        return len(expected)
    actual = set(frame[timestamp_column].dropna().dt.floor("min"))
    return sum(timestamp not in actual for timestamp in expected)


def _edge_reasons(
    frame: pd.DataFrame,
    timestamp_column: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    grace_minutes: int,
    prefix: str,
) -> list[str]:
    if frame.empty or timestamp_column not in frame:
        return [f"MISSING_{prefix}"]
    timestamps = frame[timestamp_column].dropna()
    if timestamps.empty:
        return [f"MISSING_{prefix}"]
    reasons = []
    grace = pd.Timedelta(minutes=grace_minutes)
    if timestamps.min() > start + grace:
        reasons.append(f"LATE_{prefix}_START")
    if timestamps.max() < end - grace:
        reasons.append(f"EARLY_{prefix}_END")
    return reasons


def _profile_summary(frame: pd.DataFrame, family: str, bin_points: int) -> ProfileSummary | None:
    if frame.empty:
        return None
    selected = frame.copy()
    selected["px"] = pd.to_numeric(selected["px"], errors="coerce")
    selected["w"] = pd.to_numeric(selected["w"], errors="coerce")
    selected = selected[selected.px.notna() & selected.w.gt(0)].copy()
    if selected.empty:
        return None
    selected["price_bin"] = selected.px.map(
        lambda value: float(round(float(value) / bin_points) * bin_points)
    )
    grouped = selected.groupby("price_bin", observed=True).w.agg(["sum", "count"])
    bins = tuple(
        (float(index), float(row["sum"]), int(row["count"]))
        for index, row in grouped.sort_index().iterrows()
    )
    timestamps = selected.receipt_timestamp.dropna()
    contracts = (
        tuple(sorted(str(value) for value in selected.symbol.dropna().unique()))
        if "symbol" in selected
        else ()
    )
    expiries = (
        tuple(sorted(str(value) for value in selected.expiry_date.dropna().unique()))
        if "expiry_date" in selected
        else ()
    )
    return ProfileSummary(
        family=family,
        total_weight=float(selected.w.sum()),
        weighted_price_sum=float((selected.px * selected.w).sum()),
        evidence_count=int(len(selected)),
        first_evidence_timestamp=_iso(timestamps.min()) if len(timestamps) else "",
        latest_evidence_timestamp=_iso(timestamps.max()) if len(timestamps) else "",
        contracts=contracts,
        expiries=expiries,
        bins=bins,
    )


def _rejected_revision(
    session: str,
    quick_sha: str,
    source_manifest: Mapping[str, object],
    reasons: Iterable[str],
    quality: Mapping[str, object],
    config: NightlyContextConfig,
    *,
    index_symbol: str = "",
    futures_symbol: str = "",
    futures_expiry: str | None = None,
    option_expiry: str | None = None,
) -> SessionRevision:
    source_sha = str(source_manifest.get("manifest_sha256", ""))
    revision_id = _sha256_text(
        _canonical_json(
            [session, quick_sha, source_sha, config.sha256, config.algorithm_version, CONTEXT_RUNTIME_VERSION]
        )
    )[:32]
    return SessionRevision(
        revision_id=revision_id,
        session_date=session,
        status="REJECTED",
        reasons=tuple(sorted(set(reasons))),
        quick_manifest_sha256=quick_sha,
        source_manifest_sha256=source_sha,
        source_manifest=source_manifest,
        quality=quality,
        index_symbol=index_symbol,
        futures_symbol=futures_symbol,
        futures_expiry=futures_expiry,
        option_expiry=option_expiry,
        profiles=(),
    )


def _analyze_session(
    data_root: Path,
    session: str,
    quick_manifest: Mapping[str, object],
    quick_sha: str,
    config: NightlyContextConfig,
) -> SessionRevision:
    manifest, raw_symbols, malformed_count, malformed_examples, raw_candidates = _scan_sources(
        data_root, session, quick_manifest
    )
    _, after_scan_sha = _quick_manifest(data_root, session)
    if after_scan_sha != quick_sha:
        raise ValueError(f"source file set changed during analysis: {session}")
    base_quality: dict[str, object] = {
        "malformed_json_records": malformed_count,
        "malformed_examples": malformed_examples,
        "raw_symbol_count": len(raw_symbols),
        "raw_record_count": sum(raw_symbols.values()),
    }
    reasons: list[str] = []
    raw_files = [row for row in manifest["files"] if row["kind"] == "raw"]
    oi_files = [row for row in manifest["files"] if row["kind"] == "oi"]
    if not raw_files:
        reasons.append("MISSING_RAW_FILES")
    if not oi_files:
        reasons.append("MISSING_OI_FILES")
    if malformed_count:
        reasons.append("MALFORMED_JSON_RECORDS")
    if reasons:
        return _rejected_revision(session, quick_sha, manifest, reasons, base_quality, config)

    index_symbol = _select_index_symbol(raw_symbols)
    if not index_symbol:
        reasons.append("MISSING_BANKNIFTY_INDEX")
    try:
        oi = load_oi(data_root / "oi", session)
    except (OSError, TypeError, ValueError) as error:
        return _rejected_revision(
            session,
            quick_sha,
            manifest,
            [*reasons, "OI_PARSER_ERROR"],
            {**base_quality, "parser_error": str(error)},
            config,
            index_symbol=index_symbol,
        )
    futures_symbol, futures_expiry, option_expiry = (
        select_contracts(oi, session) if not oi.empty else ("", None, None)
    )
    if not futures_symbol:
        reasons.append("MISSING_ACTIVE_FUTURES_OI")
    if option_expiry is None:
        reasons.append("MISSING_ACTIVE_OPTION_EXPIRY")
    if futures_symbol and not raw_symbols[futures_symbol]:
        reasons.append("MISSING_ACTIVE_FUTURES_TICKS")
    required_classes = set(oi.instrument_class) if not oi.empty else set()
    for instrument, reason in (
        ("future", "MISSING_FUTURES_OI"),
        ("call", "MISSING_CALL_OI"),
        ("put", "MISSING_PUT_OI"),
    ):
        if instrument not in required_classes:
            reasons.append(reason)

    market = pd.DataFrame()
    if index_symbol and futures_symbol:
        try:
            market = _market_from_candidates(raw_candidates, {index_symbol, futures_symbol})
        except (OSError, TypeError, ValueError) as error:
            reasons.append("MARKET_PARSER_ERROR")
            base_quality["parser_error"] = str(error)
    start, end = _session_bounds(session, config)
    index_market = market[market.symbol.eq(index_symbol)] if not market.empty else market
    futures_market = market[market.symbol.eq(futures_symbol)] if not market.empty else market
    reasons.extend(
        _edge_reasons(
            index_market,
            "receipt_timestamp",
            start,
            end,
            config.edge_grace_minutes,
            "INDEX_COVERAGE",
        )
    )
    reasons.extend(
        _edge_reasons(
            futures_market,
            "receipt_timestamp",
            start,
            end,
            config.edge_grace_minutes,
            "FUTURES_COVERAGE",
        )
    )
    missing_index_market = _missing_minutes(
        index_market, start, end, timestamp_column="receipt_timestamp"
    )
    missing_futures_market = _missing_minutes(
        futures_market, start, end, timestamp_column="receipt_timestamp"
    )
    if missing_index_market > config.maximum_missing_market_minutes:
        reasons.append("MATERIAL_INDEX_CONTINUITY_OUTAGE")
    if missing_futures_market > config.maximum_missing_market_minutes:
        reasons.append("MATERIAL_FUTURES_CONTINUITY_OUTAGE")
    futures_oi = (
        oi[oi.instrument_class.eq("future") & oi.symbol.eq(futures_symbol)]
        if not oi.empty
        else oi
    )
    options_oi = (
        oi[
            oi.instrument_class.isin(["call", "put"])
            & oi.expiry_date.astype(str).eq(str(option_expiry))
        ]
        if not oi.empty
        else oi
    )
    reasons.extend(
        _edge_reasons(
            futures_oi,
            "availability_timestamp",
            start,
            end,
            config.edge_grace_minutes,
            "FUTURES_OI_COVERAGE",
        )
    )
    reasons.extend(
        _edge_reasons(
            options_oi,
            "availability_timestamp",
            start,
            end,
            config.edge_grace_minutes,
            "OPTIONS_OI_COVERAGE",
        )
    )
    missing_futures_oi = _missing_minutes(futures_oi, start, end)
    missing_options_oi = _missing_minutes(options_oi, start, end)
    if missing_futures_oi > config.maximum_missing_oi_minutes:
        reasons.append("MATERIAL_FUTURES_OI_CONTINUITY_OUTAGE")
    if missing_options_oi > config.maximum_missing_oi_minutes:
        reasons.append("MATERIAL_OPTIONS_OI_CONTINUITY_OUTAGE")

    quality = {
        **base_quality,
        "index_first_receipt": _iso(index_market.receipt_timestamp.min()) if not index_market.empty else "",
        "index_last_receipt": _iso(index_market.receipt_timestamp.max()) if not index_market.empty else "",
        "futures_first_receipt": _iso(futures_market.receipt_timestamp.min()) if not futures_market.empty else "",
        "futures_last_receipt": _iso(futures_market.receipt_timestamp.max()) if not futures_market.empty else "",
        "oi_first_receipt": _iso(oi.availability_timestamp.min()) if not oi.empty else "",
        "oi_last_receipt": _iso(oi.availability_timestamp.max()) if not oi.empty else "",
        "missing_futures_oi_minutes": missing_futures_oi,
        "missing_options_oi_minutes": missing_options_oi,
        "missing_index_market_minutes": missing_index_market,
        "missing_futures_market_minutes": missing_futures_market,
        "selected_index_symbol": index_symbol,
        "selected_futures_symbol": futures_symbol,
        "selected_futures_expiry": None if futures_expiry is None else str(futures_expiry),
        "selected_option_expiry": None if option_expiry is None else str(option_expiry),
        "selected_option_symbols": sorted(str(value) for value in options_oi.symbol.unique()),
    }
    if reasons:
        return _rejected_revision(
            session,
            quick_sha,
            manifest,
            reasons,
            quality,
            config,
            index_symbol=index_symbol,
            futures_symbol=futures_symbol,
            futures_expiry=None if futures_expiry is None else str(futures_expiry),
            option_expiry=None if option_expiry is None else str(option_expiry),
        )

    price_frame = price_events(
        market,
        session,
        futures_symbol,
        index_symbol,
        config.join_tolerance_seconds,
    )
    oi_frame = oi_events(
        oi,
        market,
        session,
        futures_symbol,
        option_expiry,
        index_symbol,
        config.join_tolerance_seconds,
    )
    profiles = []
    for family in FAMILIES:
        frame = price_frame if family == "BN_REF_FUT_VOLUME_VPOC" else oi_frame[oi_frame.family.eq(family)]
        summary = _profile_summary(frame, family, config.bin_points)
        if summary is not None:
            profiles.append(summary)
    source_sha = str(manifest["manifest_sha256"])
    revision_id = _sha256_text(
        _canonical_json(
            [session, quick_sha, source_sha, config.sha256, config.algorithm_version, CONTEXT_RUNTIME_VERSION]
        )
    )[:32]
    return SessionRevision(
        revision_id=revision_id,
        session_date=session,
        status="ACCEPTED",
        reasons=("RAW_CONTINUITY_VERIFIED",),
        quick_manifest_sha256=quick_sha,
        source_manifest_sha256=source_sha,
        source_manifest=manifest,
        quality={**quality, "profile_families_with_evidence": [row.family for row in profiles]},
        index_symbol=index_symbol,
        futures_symbol=futures_symbol,
        futures_expiry=str(futures_expiry),
        option_expiry=str(option_expiry),
        profiles=tuple(profiles),
    )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETE','FAILED')),
    cutoff_session TEXT,
    algorithm_version TEXT NOT NULL,
    runtime_version TEXT NOT NULL,
    config_sha256 TEXT NOT NULL,
    config_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS session_revisions (
    revision_id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACCEPTED','REJECTED')),
    reasons_json TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    runtime_version TEXT NOT NULL,
    config_sha256 TEXT NOT NULL,
    quick_manifest_sha256 TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL,
    source_manifest_json TEXT NOT NULL,
    quality_json TEXT NOT NULL,
    index_symbol TEXT NOT NULL,
    futures_symbol TEXT NOT NULL,
    futures_expiry TEXT,
    option_expiry TEXT,
    UNIQUE(
        session_date, algorithm_version, runtime_version,
        config_sha256, quick_manifest_sha256
    )
);
CREATE INDEX IF NOT EXISTS session_revisions_lookup
    ON session_revisions(
        session_date, algorithm_version, runtime_version,
        config_sha256, quick_manifest_sha256
    );
CREATE TABLE IF NOT EXISTS session_profiles (
    revision_id TEXT NOT NULL REFERENCES session_revisions(revision_id),
    family TEXT NOT NULL,
    total_weight REAL NOT NULL,
    weighted_price_sum REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    first_evidence_timestamp TEXT NOT NULL,
    latest_evidence_timestamp TEXT NOT NULL,
    contracts_json TEXT NOT NULL,
    expiries_json TEXT NOT NULL,
    PRIMARY KEY(revision_id, family)
);
CREATE TABLE IF NOT EXISTS session_profile_bins (
    revision_id TEXT NOT NULL,
    family TEXT NOT NULL,
    price_bin REAL NOT NULL,
    weight REAL NOT NULL,
    evidence_count INTEGER NOT NULL,
    PRIMARY KEY(revision_id, family, price_bin),
    FOREIGN KEY(revision_id, family) REFERENCES session_profiles(revision_id, family)
);
CREATE TABLE IF NOT EXISTS context_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    cutoff_session TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'COMPLETE'),
    algorithm_version TEXT NOT NULL,
    runtime_version TEXT NOT NULL,
    config_sha256 TEXT NOT NULL,
    source_revision_ids_json TEXT NOT NULL,
    artifact_directory TEXT NOT NULL,
    context_sha256 TEXT NOT NULL,
    context_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS context_snapshots_latest
    ON context_snapshots(cutoff_session DESC, created_at DESC);
CREATE TABLE IF NOT EXISTS scope_controls (
    snapshot_id TEXT NOT NULL REFERENCES context_snapshots(snapshot_id),
    scope TEXT NOT NULL CHECK(scope IN ('1D','2D','3D')),
    family TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('AVAILABLE','UNAVAILABLE')),
    reason TEXT NOT NULL,
    control_value REAL,
    total_weight REAL,
    winning_bin_weight REAL,
    runner_up_bin REAL,
    runner_up_weight REAL,
    value_area_low REAL,
    value_area_high REAL,
    value_area_weight REAL,
    value_area_target_fraction REAL,
    value_area_achieved_fraction REAL,
    value_area_method TEXT,
    value_area_tie_expansions INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL,
    tie_break_reason TEXT,
    latest_evidence_timestamp TEXT,
    source_sessions_json TEXT NOT NULL,
    source_revision_ids_json TEXT NOT NULL,
    source_contracts_json TEXT NOT NULL,
    source_expiries_json TEXT NOT NULL,
    rejected_sources_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, scope, family)
);
CREATE VIEW IF NOT EXISTS latest_complete_context AS
SELECT * FROM context_snapshots
WHERE snapshot_id = (
    SELECT snapshot_id FROM context_snapshots
    ORDER BY cutoff_session DESC, created_at DESC LIMIT 1
);
"""


def _migrate_database_v1_to_v2(connection: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute("PRAGMA table_info(scope_controls)")
    }
    additions = (
        ("value_area_low", "REAL"),
        ("value_area_high", "REAL"),
        ("value_area_weight", "REAL"),
        ("value_area_target_fraction", "REAL"),
        ("value_area_achieved_fraction", "REAL"),
        ("value_area_method", "TEXT"),
        ("value_area_tie_expansions", "INTEGER NOT NULL DEFAULT 0"),
    )
    with connection:
        for name, declaration in additions:
            if name not in columns:
                connection.execute(f"ALTER TABLE scope_controls ADD COLUMN {name} {declaration}")
        connection.execute(
            "UPDATE schema_metadata SET value=? WHERE key='schema_version'",
            (DATABASE_SCHEMA_VERSION,),
        )


def _connect(database: Path, *, read_only: bool = False) -> sqlite3.Connection:
    connection = (
        sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30)
        if read_only
        else sqlite3.connect(database, timeout=30)
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    if read_only:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(SCHEMA_SQL)
    existing = connection.execute(
        "SELECT value FROM schema_metadata WHERE key='schema_version'"
    ).fetchone()
    if not read_only and existing is not None and existing["value"] == "1":
        _migrate_database_v1_to_v2(connection)
        existing = connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone()
    if existing is not None and existing["value"] != DATABASE_SCHEMA_VERSION:
        connection.close()
        raise ValueError(
            f"unsupported context database schema {existing['value']}; expected {DATABASE_SCHEMA_VERSION}"
        )
    if not read_only:
        connection.execute(
            "INSERT OR IGNORE INTO schema_metadata(key,value) VALUES('schema_version',?)",
            (DATABASE_SCHEMA_VERSION,),
        )
        connection.commit()
    return connection


def _load_cached_revision(
    connection: sqlite3.Connection,
    session: str,
    quick_sha: str,
    config: NightlyContextConfig,
) -> SessionRevision | None:
    row = connection.execute(
        """SELECT * FROM session_revisions
           WHERE session_date=? AND algorithm_version=? AND runtime_version=?
             AND config_sha256=? AND quick_manifest_sha256=?""",
        (session, config.algorithm_version, CONTEXT_RUNTIME_VERSION, config.sha256, quick_sha),
    ).fetchone()
    if row is None:
        return None
    profiles = []
    for profile in connection.execute(
        "SELECT * FROM session_profiles WHERE revision_id=? ORDER BY family", (row["revision_id"],)
    ):
        bins = tuple(
            (float(item["price_bin"]), float(item["weight"]), int(item["evidence_count"]))
            for item in connection.execute(
                """SELECT price_bin,weight,evidence_count FROM session_profile_bins
                   WHERE revision_id=? AND family=? ORDER BY price_bin""",
                (row["revision_id"], profile["family"]),
            )
        )
        profiles.append(
            ProfileSummary(
                family=profile["family"],
                total_weight=float(profile["total_weight"]),
                weighted_price_sum=float(profile["weighted_price_sum"]),
                evidence_count=int(profile["evidence_count"]),
                first_evidence_timestamp=profile["first_evidence_timestamp"],
                latest_evidence_timestamp=profile["latest_evidence_timestamp"],
                contracts=tuple(json.loads(profile["contracts_json"])),
                expiries=tuple(json.loads(profile["expiries_json"])),
                bins=bins,
            )
        )
    return SessionRevision(
        revision_id=row["revision_id"],
        session_date=row["session_date"],
        status=row["status"],
        reasons=tuple(json.loads(row["reasons_json"])),
        quick_manifest_sha256=row["quick_manifest_sha256"],
        source_manifest_sha256=row["source_manifest_sha256"],
        source_manifest=json.loads(row["source_manifest_json"]),
        quality=json.loads(row["quality_json"]),
        index_symbol=row["index_symbol"],
        futures_symbol=row["futures_symbol"],
        futures_expiry=row["futures_expiry"],
        option_expiry=row["option_expiry"],
        profiles=tuple(profiles),
        reused=True,
    )


def _store_revision(
    connection: sqlite3.Connection,
    revision: SessionRevision,
    config: NightlyContextConfig,
) -> None:
    with connection:
        connection.execute(
            """INSERT INTO session_revisions(
                revision_id,session_date,created_at,status,reasons_json,algorithm_version,
                runtime_version,config_sha256,quick_manifest_sha256,source_manifest_sha256,
                source_manifest_json,quality_json,index_symbol,futures_symbol,
                futures_expiry,option_expiry
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                revision.revision_id,
                revision.session_date,
                _utc_now(),
                revision.status,
                _canonical_json(revision.reasons),
                config.algorithm_version,
                CONTEXT_RUNTIME_VERSION,
                config.sha256,
                revision.quick_manifest_sha256,
                revision.source_manifest_sha256,
                _canonical_json(revision.source_manifest),
                _canonical_json(revision.quality),
                revision.index_symbol,
                revision.futures_symbol,
                revision.futures_expiry,
                revision.option_expiry,
            ),
        )
        for profile in revision.profiles:
            connection.execute(
                """INSERT INTO session_profiles VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    revision.revision_id,
                    profile.family,
                    profile.total_weight,
                    profile.weighted_price_sum,
                    profile.evidence_count,
                    profile.first_evidence_timestamp,
                    profile.latest_evidence_timestamp,
                    _canonical_json(profile.contracts),
                    _canonical_json(profile.expiries),
                ),
            )
            connection.executemany(
                """INSERT INTO session_profile_bins VALUES(?,?,?,?,?)""",
                (
                    (revision.revision_id, profile.family, price_bin, weight, count)
                    for price_bin, weight, count in profile.bins
                ),
            )


def _choose_control(
    bins: Mapping[float, float], weighted_mean: float
) -> tuple[float, str, float | None, float | None]:
    maximum = max(bins.values())
    candidates = sorted(price for price, weight in bins.items() if weight == maximum)
    reason = "NO_TIE"
    if len(candidates) > 1:
        reason = "TIE_WEIGHTED_MEAN"
        distance = min(abs(price - weighted_mean) for price in candidates)
        candidates = [price for price in candidates if abs(price - weighted_mean) == distance]
    if len(candidates) > 1:
        reason = "TIE_LOWER_BIN"
    winner = min(candidates)
    ranked = sorted(bins, key=lambda price: (-bins[price], price))
    runner = ranked[1] if len(ranked) > 1 else None
    return winner, reason, runner, None if runner is None else bins[runner]


def _volume_value_area(
    bins: Mapping[float, float],
    vpoc: float,
    *,
    bin_points: int,
    target_fraction: float,
) -> dict[str, object]:
    """Build one contiguous value area around VPOC.

    Expansion compares the immediately adjacent upper and lower price bins.
    The larger weight is included first; an exact tie includes both sides so
    the result has no artificial directional bias. Empty price levels are
    traversed as zero-weight bins, preserving a contiguous price interval.
    """

    normalized = {
        float(price): float(weight)
        for price, weight in bins.items()
        if math.isfinite(float(price)) and math.isfinite(float(weight)) and float(weight) >= 0
    }
    total = sum(normalized.values())
    if vpoc not in normalized or total <= 0:
        raise ValueError("volume value area requires a positive profile and an observed VPOC")
    if bin_points <= 0 or not 0 < target_fraction <= 1:
        raise ValueError("volume value-area settings are invalid")

    lower_bound = min(normalized)
    upper_bound = max(normalized)
    low = high = float(vpoc)
    included_weight = normalized[float(vpoc)]
    target_weight = total * target_fraction
    tie_expansions = 0
    while included_weight < target_weight and (low > lower_bound or high < upper_bound):
        lower = low - bin_points if low > lower_bound else None
        upper = high + bin_points if high < upper_bound else None
        lower_weight = -1.0 if lower is None else normalized.get(lower, 0.0)
        upper_weight = -1.0 if upper is None else normalized.get(upper, 0.0)
        if lower is not None and upper is not None and math.isclose(
            lower_weight, upper_weight, rel_tol=0, abs_tol=1e-12
        ):
            low = lower
            high = upper
            included_weight += lower_weight + upper_weight
            tie_expansions += 1
        elif upper is not None and upper_weight > lower_weight:
            high = upper
            included_weight += upper_weight
        elif lower is not None:
            low = lower
            included_weight += lower_weight
        else:
            break
    return {
        "value_area_low": low,
        "value_area_high": high,
        "value_area_weight": included_weight,
        "value_area_target_fraction": target_fraction,
        "value_area_achieved_fraction": included_weight / total,
        "value_area_method": "CONTIGUOUS_ADJACENT_70_PERCENT_FROM_VPOC",
        "value_area_tie_expansions": tie_expansions,
    }


def _value_area_defaults() -> dict[str, object]:
    return {
        "value_area_low": None,
        "value_area_high": None,
        "value_area_weight": None,
        "value_area_target_fraction": None,
        "value_area_achieved_fraction": None,
        "value_area_method": None,
        "value_area_tie_expansions": 0,
    }


def _control_row(
    scope: str,
    family: str,
    revisions: Sequence[SessionRevision],
    config: NightlyContextConfig,
) -> dict[str, object]:
    source_sessions = [row.session_date for row in revisions]
    source_revision_ids = [row.revision_id for row in revisions]
    family_profiles = {
        row.revision_id: next(
            (profile for profile in row.profiles if profile.family == family), None
        )
        for row in revisions
    }
    contracts = [
        {
            "session": row.session_date,
            "symbols": (
                list(family_profiles[row.revision_id].contracts)
                if family_profiles[row.revision_id] is not None
                and family_profiles[row.revision_id].contracts
                else (
                    [row.futures_symbol]
                    if family.startswith(("BN_", "FUT_")) and row.futures_symbol
                    else list(row.quality.get("selected_option_symbols", []))
                )
            ),
        }
        for row in revisions
    ]
    expiries = [
        {
            "session": row.session_date,
            "expiries": (
                list(family_profiles[row.revision_id].expiries)
                if family_profiles[row.revision_id] is not None
                and family_profiles[row.revision_id].expiries
                else [
                    value
                    for value in (
                        row.futures_expiry
                        if family.startswith(("BN_", "FUT_"))
                        else row.option_expiry,
                    )
                    if value
                ]
            ),
        }
        for row in revisions
    ]
    base = {
        "scope": scope,
        "family": family,
        "source_sessions": source_sessions,
        "source_revision_ids": source_revision_ids,
        "source_contracts": contracts,
        "source_expiries": expiries,
        **_value_area_defaults(),
    }
    if len(revisions) != int(scope[0]):
        return {
            **base,
            "status": "UNAVAILABLE",
            "reason": "INSUFFICIENT_COMPLETED_SOURCE_SESSIONS",
            "control_value": None,
            "total_weight": None,
            "winning_bin_weight": None,
            "runner_up_bin": None,
            "runner_up_weight": None,
            "evidence_count": 0,
            "tie_break_reason": None,
            "latest_evidence_timestamp": None,
        }
    rejected = [row for row in revisions if row.status != "ACCEPTED"]
    if rejected:
        return {
            **base,
            "status": "UNAVAILABLE",
            "reason": "SOURCE_SESSION_QUALITY_REJECTED",
            "rejected_sources": [
                {"session": row.session_date, "reasons": list(row.reasons)} for row in rejected
            ],
            "control_value": None,
            "total_weight": None,
            "winning_bin_weight": None,
            "runner_up_bin": None,
            "runner_up_weight": None,
            "evidence_count": 0,
            "tie_break_reason": None,
            "latest_evidence_timestamp": None,
        }
    profiles = [
        profile
        for revision in revisions
        for profile in revision.profiles
        if profile.family == family
    ]
    bins: defaultdict[float, float] = defaultdict(float)
    total_weight = 0.0
    weighted_price_sum = 0.0
    evidence_count = 0
    latest = ""
    for profile in profiles:
        total_weight += profile.total_weight
        weighted_price_sum += profile.weighted_price_sum
        evidence_count += profile.evidence_count
        latest = max(latest, profile.latest_evidence_timestamp)
        for price_bin, weight, _ in profile.bins:
            bins[price_bin] += weight
    if not bins or total_weight <= 0:
        return {
            **base,
            "status": "UNAVAILABLE",
            "reason": "NO_ELIGIBLE_FAMILY_EVIDENCE",
            "control_value": None,
            "total_weight": None,
            "winning_bin_weight": None,
            "runner_up_bin": None,
            "runner_up_weight": None,
            "evidence_count": 0,
            "tie_break_reason": None,
            "latest_evidence_timestamp": None,
        }
    winner, tie, runner, runner_weight = _choose_control(bins, weighted_price_sum / total_weight)
    value_area = (
        _volume_value_area(
            bins,
            winner,
            bin_points=config.bin_points,
            target_fraction=config.value_area_fraction,
        )
        if family == VOLUME_PROFILE_FAMILY
        else _value_area_defaults()
    )
    return {
        **base,
        "status": "AVAILABLE",
        "reason": "RAW_CAUSAL_INVENTORY_RECOMPUTED",
        "control_value": winner,
        "total_weight": total_weight,
        "winning_bin_weight": bins[winner],
        "runner_up_bin": runner,
        "runner_up_weight": runner_weight,
        "evidence_count": evidence_count,
        "tie_break_reason": tie,
        "latest_evidence_timestamp": latest,
        **value_area,
    }


def _build_context(
    cutoff_session: str,
    revisions: Sequence[SessionRevision],
    config: NightlyContextConfig,
) -> tuple[str, dict[str, object], list[dict[str, object]]]:
    revision_ids = [row.revision_id for row in revisions]
    snapshot_id = _sha256_text(
        _canonical_json(
            [cutoff_session, revision_ids, config.sha256, config.algorithm_version, CONTEXT_RUNTIME_VERSION]
        )
    )[:32]
    controls = []
    for scope, count in (("1D", 1), ("2D", 2), ("3D", 3)):
        selected = list(revisions[-count:]) if len(revisions) >= count else list(revisions)
        for family in FAMILIES:
            controls.append(_control_row(scope, family, selected, config))
    sessions = [
        {
            "session": row.session_date,
            "revision_id": row.revision_id,
            "status": row.status,
            "reasons": list(row.reasons),
            "index_symbol": row.index_symbol,
            "futures_symbol": row.futures_symbol,
            "futures_expiry": row.futures_expiry,
            "option_expiry": row.option_expiry,
            "source_manifest_sha256": row.source_manifest_sha256,
        }
        for row in revisions
    ]
    context = {
        "schema": CONTEXT_SCHEMA,
        "snapshot_id": snapshot_id,
        "status": "COMPLETE",
        "classification": CLASSIFICATION,
        "research_only": True,
        "production_weight": 0,
        "cutoff_source_session": cutoff_session,
        "selection_rule": "ONLY_SOURCE_SESSIONS_STRICTLY_BEFORE_THE_INTRADAY_SESSION",
        "created_at": _utc_now(),
        "algorithm_version": config.algorithm_version,
        "runtime_version": CONTEXT_RUNTIME_VERSION,
        "config_sha256": config.sha256,
        "coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
        "bin_points": config.bin_points,
        "value_area_fraction": config.value_area_fraction,
        "model_parameters_changed": False,
        "source_chain": sessions,
        "controls": controls,
        "causal_guarantees": [
            "CURRENT_INTRADAY_SESSION_EXCLUDED",
            "BACKWARD_INDEX_JOIN_ONLY",
            "NO_DAILY_VPOC_AVERAGING",
            "VALUE_AREA_EXPANDS_CONTIGUOUSLY_FROM_AGGREGATED_VOLUME_VPOC",
            "NO_THRESHOLD_OR_WEIGHT_TUNING",
            "REJECTED_SOURCE_SESSIONS_FAIL_CLOSED",
        ],
    }
    return snapshot_id, context, controls


def _write_snapshot_bundle(
    state_root: Path,
    cutoff_session: str,
    snapshot_id: str,
    context: Mapping[str, object],
    revisions: Sequence[SessionRevision],
) -> tuple[Path, str, Mapping[str, object]]:
    final = state_root / "daily_context" / cutoff_session / snapshot_id
    context_sha = _sha256_text(_canonical_json(context))
    if final.exists():
        if not final.is_dir() or not (final / "context.json").is_file():
            raise FileExistsError(f"snapshot target exists but is not a valid bundle: {final}")
        try:
            manifest = json.loads(
                (final / "sha256_manifest.json").read_text(encoding="utf-8")
            )
            for name, expected in manifest["files"].items():
                path = final / name
                if Path(name).name != name or not path.is_file() or sha256_file(path) != expected:
                    raise ValueError(f"invalid immutable artifact: {name}")
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise FileExistsError(f"existing snapshot bundle failed verification: {final}") from error
        existing = json.loads((final / "context.json").read_text(encoding="utf-8"))
        if existing.get("snapshot_id") != snapshot_id:
            raise FileExistsError(f"immutable snapshot collision: {final}")
        existing_sha = _sha256_text(_canonical_json(existing))
        return final, existing_sha, existing
    staging_root = state_root / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = staging_root / f"{snapshot_id}-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        atomic_json(staging / "context.json", context)
        atomic_json(
            staging / "source_manifest.json",
            {
                "schema": "NEW_DIVERGENCE_CONTEXT_SOURCES_V1",
                "snapshot_id": snapshot_id,
                "sessions": [
                    {
                        "session": row.session_date,
                        "revision_id": row.revision_id,
                        "source_manifest": row.source_manifest,
                        "quality": row.quality,
                    }
                    for row in revisions
                ],
                "runtime": runtime_identity(),
            },
        )
        hashes = {
            name: sha256_file(staging / name)
            for name in ("context.json", "source_manifest.json")
        }
        atomic_json(
            staging / "sha256_manifest.json",
            {
                "schema": "NEW_DIVERGENCE_CONTEXT_HASH_MANIFEST_V1",
                "snapshot_id": snapshot_id,
                "files": hashes,
            },
        )
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final, context_sha, context


def _store_snapshot(
    connection: sqlite3.Connection,
    snapshot_id: str,
    cutoff_session: str,
    context: Mapping[str, object],
    controls: Sequence[Mapping[str, object]],
    revisions: Sequence[SessionRevision],
    artifact_directory: Path,
    context_sha: str,
    config: NightlyContextConfig,
) -> bool:
    if connection.execute(
        "SELECT 1 FROM context_snapshots WHERE snapshot_id=?", (snapshot_id,)
    ).fetchone():
        return True
    with connection:
        connection.execute(
            """INSERT INTO context_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                cutoff_session,
                context["created_at"],
                "COMPLETE",
                config.algorithm_version,
                CONTEXT_RUNTIME_VERSION,
                config.sha256,
                _canonical_json([row.revision_id for row in revisions]),
                str(artifact_directory),
                context_sha,
                _canonical_json(context),
            ),
        )
        for row in controls:
            connection.execute(
                """INSERT INTO scope_controls(
                    snapshot_id,scope,family,status,reason,control_value,total_weight,
                    winning_bin_weight,runner_up_bin,runner_up_weight,value_area_low,
                    value_area_high,value_area_weight,value_area_target_fraction,
                    value_area_achieved_fraction,value_area_method,value_area_tie_expansions,
                    evidence_count,tie_break_reason,latest_evidence_timestamp,
                    source_sessions_json,source_revision_ids_json,source_contracts_json,
                    source_expiries_json,rejected_sources_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    row["scope"],
                    row["family"],
                    row["status"],
                    row["reason"],
                    row["control_value"],
                    row["total_weight"],
                    row["winning_bin_weight"],
                    row["runner_up_bin"],
                    row["runner_up_weight"],
                    row["value_area_low"],
                    row["value_area_high"],
                    row["value_area_weight"],
                    row["value_area_target_fraction"],
                    row["value_area_achieved_fraction"],
                    row["value_area_method"],
                    row["value_area_tie_expansions"],
                    row["evidence_count"],
                    row["tie_break_reason"],
                    row["latest_evidence_timestamp"],
                    _canonical_json(row["source_sessions"]),
                    _canonical_json(row["source_revision_ids"]),
                    _canonical_json(row["source_contracts"]),
                    _canonical_json(row["source_expiries"]),
                    # Rejected provenance remains explicit even when empty.
                    _canonical_json(row.get("rejected_sources", [])),
                ),
            )
    return False


@contextmanager
def _exclusive_lock(state_root: Path) -> Iterator[None]:
    lock_path = state_root / "nightly-context.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(f"another nightly context job holds {lock_path}") from error
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started_at={_utc_now()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def run_nightly_context(
    data_root: Path,
    state_root: Path,
    *,
    config: NightlyContextConfig | None = None,
    cutoff_session: date | None = None,
    stability_seconds: int | None = None,
) -> dict[str, object]:
    """Analyze new/changed completed sessions and publish one context snapshot."""

    source = Path(data_root).resolve()
    state = Path(state_root).resolve()
    selected_config = config or NightlyContextConfig()
    if stability_seconds is not None:
        selected_config = NightlyContextConfig(
            **{**asdict(selected_config), "stability_seconds": stability_seconds}
        )
    selected_config.validate()
    if state == source or source in state.parents:
        raise ValueError("state root must not be inside the read-only collector root")
    state.mkdir(parents=True, exist_ok=True)
    database = state / "context.sqlite3"
    with _exclusive_lock(state):
        connection = _connect(database)
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:12]}"
        requested_cutoff = cutoff_session or (datetime.now(IST).date() - timedelta(days=1))
        connection.execute(
            """INSERT INTO analysis_runs(
                run_id,started_at,status,cutoff_session,algorithm_version,runtime_version,
                config_sha256,config_json
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                run_id,
                _utc_now(),
                "RUNNING",
                requested_cutoff.isoformat(),
                selected_config.algorithm_version,
                CONTEXT_RUNTIME_VERSION,
                selected_config.sha256,
                selected_config.canonical_json,
            ),
        )
        connection.commit()
        try:
            discovered_sessions = _discover_sessions(source, requested_cutoff)
            if not discovered_sessions:
                raise ValueError(f"no completed raw/OI sessions found through {requested_cutoff}")
            # Only the immediate prior three discovered sessions can contribute
            # to the published 1D/2D/3D context. Keeping this boundary here
            # avoids parsing unrelated multi-gigabyte history during bootstrap.
            sessions = discovered_sessions[-3:]
            revisions: list[SessionRevision] = []
            analyzed = 0
            reused = 0
            for session in sessions:
                quick, quick_sha = _quick_manifest(source, session)
                if not _is_stable(quick, selected_config.stability_seconds):
                    raise ValueError(
                        f"required source session {session} is not stable for "
                        f"{selected_config.stability_seconds} seconds"
                    )
                revision = _load_cached_revision(connection, session, quick_sha, selected_config)
                if revision is None:
                    revision = _analyze_session(source, session, quick, quick_sha, selected_config)
                    _store_revision(connection, revision, selected_config)
                    analyzed += 1
                else:
                    reused += 1
                revisions.append(revision)
            if not revisions or revisions[-1].session_date != sessions[-1]:
                raise ValueError("latest completed source session was not eligible for analysis")
            source_chain = revisions
            cutoff = sessions[-1]
            snapshot_id, context, controls = _build_context(cutoff, source_chain, selected_config)
            existing = connection.execute(
                """SELECT artifact_directory,context_sha256,context_json
                   FROM context_snapshots WHERE snapshot_id=?""",
                (snapshot_id,),
            ).fetchone()
            if existing is None:
                artifact, context_sha, context = _write_snapshot_bundle(
                    state, cutoff, snapshot_id, context, source_chain
                )
                snapshot_reused = _store_snapshot(
                    connection,
                    snapshot_id,
                    cutoff,
                    context,
                    controls,
                    source_chain,
                    artifact,
                    context_sha,
                    selected_config,
                )
            else:
                context = json.loads(existing["context_json"])
                artifact, context_sha, _ = _write_snapshot_bundle(
                    state, cutoff, snapshot_id, context, source_chain
                )
                if artifact != Path(existing["artifact_directory"]):
                    raise ValueError("database snapshot path differs from deterministic artifact path")
                if context_sha != existing["context_sha256"]:
                    raise ValueError("database snapshot hash differs from immutable artifact")
                snapshot_reused = True
            available = sum(row["status"] == "AVAILABLE" for row in controls)
            result = {
                "schema": "NEW_DIVERGENCE_NIGHTLY_RESULT_V1",
                "status": "COMPLETE",
                "run_id": run_id,
                "database": str(database),
                "snapshot_id": snapshot_id,
                "cutoff_source_session": cutoff,
                "artifact_directory": str(artifact),
                "context_sha256": context_sha,
                "discovered_session_count": len(discovered_sessions),
                "selected_contributing_session_count": len(sessions),
                "analyzed_session_count": analyzed,
                "reused_session_count": reused,
                "source_chain": [row.session_date for row in source_chain],
                "source_quality": {row.session_date: row.status for row in source_chain},
                "available_control_count": available,
                "unavailable_control_count": len(controls) - available,
                "snapshot_reused": snapshot_reused,
                "model_parameters_changed": False,
            }
            connection.execute(
                """UPDATE analysis_runs SET completed_at=?,status='COMPLETE',result_json=?
                   WHERE run_id=?""",
                (_utc_now(), _canonical_json(result), run_id),
            )
            connection.commit()
            return result
        except Exception as error:
            connection.execute(
                """UPDATE analysis_runs SET completed_at=?,status='FAILED',error=? WHERE run_id=?""",
                (_utc_now(), f"{type(error).__name__}: {error}", run_id),
            )
            connection.commit()
            raise
        finally:
            connection.close()


def inspect_context(state_root: Path, snapshot_id: str | None = None) -> dict[str, object]:
    state = Path(state_root).resolve()
    database = state / "context.sqlite3"
    if not database.is_file():
        raise FileNotFoundError(f"context database not found: {database}")
    connection = _connect(database, read_only=True)
    try:
        if snapshot_id is None:
            row = connection.execute(
                "SELECT * FROM context_snapshots ORDER BY cutoff_session DESC,created_at DESC LIMIT 1"
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT * FROM context_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise ValueError("no complete context snapshot is available")
        artifact = Path(row["artifact_directory"])
        reasons = []
        manifest_path = artifact / "sha256_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for name, expected in manifest["files"].items():
                path = artifact / name
                if not path.is_file():
                    reasons.append(f"MISSING_ARTIFACT:{name}")
                elif sha256_file(path) != expected:
                    reasons.append(f"HASH_MISMATCH:{name}")
        except (KeyError, OSError, TypeError, json.JSONDecodeError) as error:
            reasons.append(f"MANIFEST_ERROR:{error}")
        context = json.loads(row["context_json"])
        context_path = artifact / "context.json"
        if context_path.is_file():
            try:
                artifact_context = json.loads(context_path.read_text(encoding="utf-8"))
                if _sha256_text(_canonical_json(artifact_context)) != row["context_sha256"]:
                    reasons.append("DATABASE_CONTEXT_HASH_MISMATCH")
                if artifact_context != context:
                    reasons.append("DATABASE_ARTIFACT_CONTEXT_MISMATCH")
            except (OSError, TypeError, json.JSONDecodeError) as error:
                reasons.append(f"CONTEXT_ERROR:{error}")
        controls = connection.execute(
            """SELECT scope,status,COUNT(*) AS count FROM scope_controls
               WHERE snapshot_id=? GROUP BY scope,status ORDER BY scope,status""",
            (row["snapshot_id"],),
        ).fetchall()
        return {
            "valid": not reasons,
            "reasons": reasons or ["OK"],
            "database": str(database),
            "snapshot_id": row["snapshot_id"],
            "cutoff_source_session": row["cutoff_session"],
            "artifact_directory": str(artifact),
            "source_chain": context["source_chain"],
            "control_counts": [dict(item) for item in controls],
            "model_parameters_changed": context["model_parameters_changed"],
        }
    finally:
        connection.close()
