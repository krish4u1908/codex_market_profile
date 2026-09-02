"""Typed contracts for the new divergence runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Mapping

from .clock import iso_ist, iso_utc, parse_instant, session_date


class EventKind(StrEnum):
    INDEX_TICK = "INDEX_TICK"
    FUTURES_TICK = "FUTURES_TICK"
    FUTURES_OI = "FUTURES_OI"
    OPTION_PRESSURE = "OPTION_PRESSURE"
    CASH_PRESSURE = "CASH_PRESSURE"
    CONTROL = "CONTROL"
    CONTROL_INTERACTION = "CONTROL_INTERACTION"
    HEARTBEAT = "HEARTBEAT"


class BasisState(StrEnum):
    GREEN_CANDIDATE = "GREEN_CANDIDATE"
    RED_CANDIDATE = "RED_CANDIDATE"
    NEUTRAL_BLUE = "NEUTRAL_BLUE"
    UNKNOWN_GAP = "UNKNOWN_GAP"
    OUTSIDE_DISCOVERY_WINDOW = "OUTSIDE_DISCOVERY_WINDOW"


class EpisodeState(StrEnum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    ROTATION = "ROTATION"
    NO_EDGE = "NO_EDGE"


TERMINAL_STATES = frozenset({
    EpisodeState.RESOLVED,
    EpisodeState.INVALIDATED,
    EpisodeState.EXPIRED,
    EpisodeState.ROTATION,
    EpisodeState.NO_EDGE,
})


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class MarketEvent:
    event_id: str
    session: date
    kind: EventKind
    symbol: str
    event_timestamp: datetime
    receipt_timestamp: datetime
    values: Mapping[str, Any] = field(default_factory=dict)
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        event_time = parse_instant(self.event_timestamp, field="event_timestamp")
        receipt = parse_instant(self.receipt_timestamp, field="receipt_timestamp")
        if session_date(receipt) != self.session:
            raise ValueError(
                f"declared session {self.session} differs from receipt session {session_date(receipt)}"
            )
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        object.__setattr__(self, "event_timestamp", event_time)
        object.__setattr__(self, "receipt_timestamp", receipt)
        object.__setattr__(self, "values", dict(self.values))
        self._validate_values()

    def _validate_values(self) -> None:
        if self.kind in {EventKind.INDEX_TICK, EventKind.FUTURES_TICK}:
            if not _finite(self.values.get("price")):
                raise ValueError(f"{self.kind} requires finite price")
        elif self.kind == EventKind.FUTURES_OI:
            if not _finite(self.values.get("oi")):
                raise ValueError("FUTURES_OI requires finite oi")
        elif self.kind in {EventKind.OPTION_PRESSURE, EventKind.CASH_PRESSURE}:
            score = self.values.get("score")
            if not _finite(score) or not -1 <= float(score) <= 1:
                raise ValueError(f"{self.kind} requires score in [-1, 1]")
        elif self.kind == EventKind.CONTROL:
            if not self.values.get("control_id") or not _finite(self.values.get("price")):
                raise ValueError("CONTROL requires control_id and finite price")

    @property
    def sort_key(self) -> tuple[datetime, int, str]:
        return self.receipt_timestamp, self.sequence, self.event_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session": self.session.isoformat(),
            "kind": self.kind.value,
            "symbol": self.symbol,
            "event_timestamp": iso_utc(self.event_timestamp),
            "receipt_timestamp": iso_utc(self.receipt_timestamp),
            "receipt_timestamp_ist": iso_ist(self.receipt_timestamp),
            "values": dict(self.values),
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "MarketEvent":
        receipt = parse_instant(row["receipt_timestamp"], field="receipt_timestamp")
        declared = row.get("session") or row.get("session_date")
        day = date.fromisoformat(str(declared)) if declared else session_date(receipt)
        values = row.get("values", {})
        if isinstance(values, str):
            values = json.loads(values)
        return cls(
            event_id=str(row["event_id"]),
            session=day,
            kind=EventKind(str(row["kind"])),
            symbol=str(row.get("symbol", "")),
            event_timestamp=parse_instant(row["event_timestamp"], field="event_timestamp"),
            receipt_timestamp=receipt,
            values=values,
            sequence=int(row.get("sequence", 0)),
        )


@dataclass(frozen=True)
class EngineConfig:
    session_start: time = time(9, 15)
    discovery_start: time = time(9, 45)
    discovery_end: time = time(14, 30)
    session_end: time = time(15, 30)
    match_tolerance_ms: int = 2_000
    index_material_points: float = 10.0
    basis_material_points: float = 5.0
    high_percentile: float = 0.80
    low_percentile: float = 0.20
    robust_z_threshold: float = 1.0
    horizons_minutes: tuple[int, ...] = (1, 3, 5)
    minimum_supporting_horizons: int = 2
    horizon_gap_tolerance_seconds: int = 15
    persistence_seconds: int = 60
    persistence_observations: int = 5
    merge_gap_seconds: int = 15
    candidate_timeout_seconds: int = 600
    active_timeout_seconds: int = 3_600
    participation_max_age_seconds: int = 300
    control_proximity_points: float = 20.0
    production_weight: int = 0
    methodology_version: str = "NEW_DIVERGENCE_V1_1_GAP_SAFE_HORIZONS"

    def __post_init__(self) -> None:
        if not self.session_start < self.discovery_start < self.discovery_end < self.session_end:
            raise ValueError("session/discovery windows are not chronological")
        if self.match_tolerance_ms <= 0:
            raise ValueError("match_tolerance_ms must be positive")
        if self.persistence_seconds < 0 or self.merge_gap_seconds < 0:
            raise ValueError("persistence and merge thresholds must be non-negative")
        if self.persistence_observations <= 0:
            raise ValueError("persistence_observations must be positive")
        if self.candidate_timeout_seconds <= 0 or self.active_timeout_seconds <= 0:
            raise ValueError("episode timeouts must be positive")
        if self.participation_max_age_seconds < 0 or self.control_proximity_points < 0:
            raise ValueError("evidence age/proximity thresholds must be non-negative")
        if self.index_material_points <= 0 or self.basis_material_points <= 0:
            raise ValueError("materiality thresholds must be positive")
        if not 0 <= self.low_percentile < self.high_percentile <= 1:
            raise ValueError("percentile thresholds must satisfy 0 <= low < high <= 1")
        if self.robust_z_threshold <= 0:
            raise ValueError("robust_z_threshold must be positive")
        if not self.horizons_minutes or any(x <= 0 for x in self.horizons_minutes):
            raise ValueError("horizons must contain positive minutes")
        if not 1 <= self.minimum_supporting_horizons <= len(self.horizons_minutes):
            raise ValueError("minimum supporting horizons exceeds configured horizons")
        if self.horizon_gap_tolerance_seconds <= 0:
            raise ValueError("horizon_gap_tolerance_seconds must be positive")
        if self.production_weight != 0:
            raise ValueError("new divergence runtime is research-only; production_weight must be zero")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "EngineConfig":
        fields = dict(values)
        for name in ("session_start", "discovery_start", "discovery_end", "session_end"):
            if name in fields and isinstance(fields[name], str):
                fields[name] = time.fromisoformat(fields[name])
        if "horizons_minutes" in fields:
            fields["horizons_minutes"] = tuple(int(x) for x in fields["horizons_minutes"])
        return cls(**fields)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for name in ("session_start", "discovery_start", "discovery_end", "session_end"):
            result[name] = getattr(self, name).isoformat()
        result["horizons_minutes"] = list(self.horizons_minutes)
        return result

    @property
    def sha256(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class BasisObservation:
    session: date
    timestamp: datetime
    index_receipt_timestamp: datetime
    futures_receipt_timestamp: datetime
    index_price: float
    futures_price: float
    basis: float
    synchronization_age_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.isoformat(),
            "timestamp": iso_utc(self.timestamp),
            "timestamp_ist": iso_ist(self.timestamp),
            "index_receipt_timestamp": iso_utc(self.index_receipt_timestamp),
            "futures_receipt_timestamp": iso_utc(self.futures_receipt_timestamp),
            "index_price": self.index_price,
            "futures_price": self.futures_price,
            "basis": self.basis,
            "synchronization_age_ms": self.synchronization_age_ms,
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "BasisObservation":
        return cls(
            session=date.fromisoformat(str(row["session"])),
            timestamp=parse_instant(row["timestamp"]),
            index_receipt_timestamp=parse_instant(row["index_receipt_timestamp"]),
            futures_receipt_timestamp=parse_instant(row["futures_receipt_timestamp"]),
            index_price=float(row["index_price"]),
            futures_price=float(row["futures_price"]),
            basis=float(row["basis"]),
            synchronization_age_ms=float(row["synchronization_age_ms"]),
        )


@dataclass(frozen=True)
class EvidenceSnapshot:
    as_of: datetime
    basis_state: BasisState
    supporting_horizons: int
    basis: BasisObservation
    horizon_evidence: Mapping[str, Mapping[str, Any]]
    basis_percentile: float
    basis_robust_z: float
    futures_oi: Mapping[str, Any] | None
    option_pressure: Mapping[str, Any] | None
    cash_pressure: Mapping[str, Any] | None
    control_interaction: Mapping[str, Any] | None
    nearest_control: Mapping[str, Any] | None
    contradictions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": iso_utc(self.as_of),
            "as_of_ist": iso_ist(self.as_of),
            "basis_state": self.basis_state.value,
            "supporting_horizons": self.supporting_horizons,
            "basis": self.basis.to_dict(),
            "horizon_evidence": {k: dict(v) for k, v in self.horizon_evidence.items()},
            "basis_percentile": self.basis_percentile,
            "basis_robust_z": self.basis_robust_z,
            "futures_oi": None if self.futures_oi is None else dict(self.futures_oi),
            "option_pressure": None if self.option_pressure is None else dict(self.option_pressure),
            "cash_pressure": None if self.cash_pressure is None else dict(self.cash_pressure),
            "control_interaction": None if self.control_interaction is None else dict(self.control_interaction),
            "nearest_control": None if self.nearest_control is None else dict(self.nearest_control),
            "contradictions": list(self.contradictions),
        }

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "EvidenceSnapshot":
        return cls(
            as_of=parse_instant(row["as_of"]),
            basis_state=BasisState(str(row["basis_state"])),
            supporting_horizons=int(row["supporting_horizons"]),
            basis=BasisObservation.from_dict(row["basis"]),
            horizon_evidence={str(key): dict(value) for key, value in row["horizon_evidence"].items()},
            basis_percentile=float(row["basis_percentile"]),
            basis_robust_z=float(row["basis_robust_z"]),
            futures_oi=row.get("futures_oi"),
            option_pressure=row.get("option_pressure"),
            cash_pressure=row.get("cash_pressure"),
            control_interaction=row.get("control_interaction"),
            nearest_control=row.get("nearest_control"),
            contradictions=tuple(str(value) for value in row.get("contradictions", [])),
        )


@dataclass(frozen=True)
class EpisodeTransition:
    transition_id: str
    episode_id: str
    session: date
    previous_state: str
    state: EpisodeState
    colour: str
    published_at: datetime
    effective_at: datetime
    candidate_started_at: datetime
    reason_codes: tuple[str, ...]
    evidence: EvidenceSnapshot
    previous_hash: str = ""
    record_hash: str = ""

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        row = {
            "transition_id": self.transition_id,
            "episode_id": self.episode_id,
            "session": self.session.isoformat(),
            "previous_state": self.previous_state,
            "state": self.state.value,
            "colour": self.colour,
            "direction": "DESCRIPTIVE_ONLY",
            "published_at": iso_utc(self.published_at),
            "published_at_ist": iso_ist(self.published_at),
            "effective_at": iso_utc(self.effective_at),
            "candidate_started_at": iso_utc(self.candidate_started_at),
            "reason_codes": list(self.reason_codes),
            "evidence": self.evidence.to_dict(),
        }
        if include_hash:
            row["previous_hash"] = self.previous_hash
            row["record_hash"] = self.record_hash
        return row

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "EpisodeTransition":
        return cls(
            transition_id=str(row["transition_id"]),
            episode_id=str(row["episode_id"]),
            session=date.fromisoformat(str(row["session"])),
            previous_state=str(row.get("previous_state", "")),
            state=EpisodeState(str(row["state"])),
            colour=str(row["colour"]),
            published_at=parse_instant(row["published_at"]),
            effective_at=parse_instant(row["effective_at"]),
            candidate_started_at=parse_instant(row["candidate_started_at"]),
            reason_codes=tuple(str(value) for value in row.get("reason_codes", [])),
            evidence=EvidenceSnapshot.from_dict(row["evidence"]),
            previous_hash=str(row.get("previous_hash", "")),
            record_hash=str(row.get("record_hash", "")),
        )
