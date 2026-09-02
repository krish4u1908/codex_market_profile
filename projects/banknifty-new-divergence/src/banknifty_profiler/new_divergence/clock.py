"""Canonical clocks shared by replay and live operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def parse_instant(value: str | datetime, *, field: str = "timestamp") -> datetime:
    """Return one timezone-aware instant normalized to UTC.

    Naive values are refused.  No timezone is guessed and no precision is
    rounded away.
    """

    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"missing {field}")
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            result = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError as error:
            raise ValueError(f"malformed {field}: {value!r}") from error
    else:
        raise ValueError(f"unsupported {field} type: {type(value).__name__}")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"timezone-naive {field}: {value!r}")
    return result.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    return parse_instant(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def iso_ist(value: datetime) -> str:
    return parse_instant(value).astimezone(IST).isoformat(timespec="microseconds")


def session_date(value: datetime) -> date:
    return parse_instant(value).astimezone(IST).date()


def session_instant(day: date, local_time: time) -> datetime:
    return datetime.combine(day, local_time, IST).astimezone(UTC)


def inside_session_window(
    value: datetime,
    day: date,
    start: time,
    end: time,
    *,
    include_end: bool = False,
) -> bool:
    instant = parse_instant(value)
    left = session_instant(day, start)
    right = session_instant(day, end)
    return left <= instant <= right if include_end else left <= instant < right


@dataclass
class ReplayClock:
    """Visibility clock that never changes source timestamps."""

    start: datetime
    end: datetime
    current: datetime | None = None

    def __post_init__(self) -> None:
        self.start = parse_instant(self.start, field="replay start")
        self.end = parse_instant(self.end, field="replay end")
        if self.end < self.start:
            raise ValueError("replay end precedes start")
        self.current = self.start if self.current is None else parse_instant(
            self.current, field="replay current"
        )
        self._clamp()

    def _clamp(self) -> None:
        assert self.current is not None
        self.current = max(self.start, min(self.end, self.current))

    def advance_to(self, value: datetime) -> datetime:
        target = parse_instant(value, field="replay target")
        if target < self.current:
            raise ValueError("replay clock cannot move backwards through advance_to")
        self.current = target
        self._clamp()
        return self.current

    def seek(self, value: datetime) -> datetime:
        self.current = parse_instant(value, field="replay target")
        self._clamp()
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise ValueError("advance delta must be non-negative")
        assert self.current is not None
        return self.advance_to(self.current + delta)

    def visible(self, receipt_timestamp: datetime) -> bool:
        assert self.current is not None
        return parse_instant(receipt_timestamp) <= self.current
