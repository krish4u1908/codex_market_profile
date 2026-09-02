from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from banknifty_profiler.new_divergence.contracts import EventKind, MarketEvent

IST = ZoneInfo("Asia/Kolkata")


def event(
    identifier: str,
    kind: EventKind,
    timestamp: datetime,
    value: float,
    sequence: int,
    *,
    symbol: str | None = None,
) -> MarketEvent:
    values = {"price": value}
    if kind == EventKind.OPTION_PRESSURE:
        values = {"score": value}
    elif kind == EventKind.FUTURES_OI:
        values = {"oi": value}
    return MarketEvent(
        event_id=identifier,
        session=timestamp.astimezone(IST).date(),
        kind=kind,
        symbol=symbol or ("NSE:NIFTYBANK-INDEX" if kind == EventKind.INDEX_TICK else "NSE:DYNAMICFUT"),
        event_timestamp=timestamp,
        receipt_timestamp=timestamp,
        values=values,
        sequence=sequence,
    )


def green_episode_events() -> list[MarketEvent]:
    day = date(2031, 4, 7)
    start = datetime(2031, 4, 7, 9, 39, tzinfo=IST)
    rows = []
    sequence = 0
    for step in range(38):
        timestamp = start + timedelta(seconds=15 * step)
        if timestamp < datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=45):
            index_price, basis = 100.0, 5.0
        elif timestamp < datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=47, second=30):
            index_price, basis = 88.0, 11.0
        else:
            index_price, basis = 88.0, 5.0
        sequence += 1
        rows.append(event(f"i-{step}", EventKind.INDEX_TICK, timestamp, index_price, sequence))
        sequence += 1
        rows.append(event(
            f"f-{step}", EventKind.FUTURES_TICK, timestamp + timedelta(milliseconds=250),
            index_price + basis, sequence,
        ))
    return rows
