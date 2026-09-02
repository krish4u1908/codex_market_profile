"""Authoritative replay-equivalent market-profile projection for live snapshots."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

from .clock import iso_utc, session_instant
from .contracts import EngineConfig, EventKind, MarketEvent
from .output import _futures_market_row, _option_strike_rows
from .projection import (
    STRIKE_REFERENCE_TIME,
    bn_0945_close_reference,
    close_0945_strike_selection,
    futures_oi_rows,
    futures_volume_rows,
    intraday_inventory_rows,
    option_strike_oi_rows,
)
from .volume_climax import compact_futures_volume_minutes


def _latest_by_family(rows: Iterable[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for source in rows:
        row = dict(source)
        result[str(row["family"])] = row
    return result


def live_profile_projection(
    events: Iterable[MarketEvent],
    observations: Iterable[Mapping[str, object]],
    evidence: Iterable[Mapping[str, object]],
    *,
    session: date,
    config: EngineConfig,
) -> dict[str, object]:
    """Build the same causal ID profile families used by completed replay."""

    event_rows = list(events)
    observation_rows = [dict(row) for row in observations]
    evidence_rows = [dict(row) for row in evidence]
    raw_strikes = [row for event in event_rows for row in _option_strike_rows(event)]
    strikes = option_strike_oi_rows(
        raw_strikes, max_gap_seconds=float(config.participation_max_age_seconds)
    )
    index_symbol = next(
        (event.symbol for event in event_rows if event.kind == EventKind.INDEX_TICK), None
    )
    close = bn_0945_close_reference(
        observation_rows,
        session=session.isoformat(),
        index_symbol=index_symbol,
        max_age_ms=float(config.match_tolerance_ms),
    )
    selection = close_0945_strike_selection(strikes, close)
    if selection.get("available") is True:
        selected_at = str(selection["selected_at"])
        selected_expiry = str(selection["expiry"])
        for row in strikes:
            if str(row.get("e")) == selected_expiry and str(row.get("t")) == selected_at:
                row["d"] = None
                row["dv"] = None
                row["vs"] = "MISSING" if row.get("v") is None else "BASELINE"

    futures_oi = futures_oi_rows(
        evidence_rows, max_gap_seconds=float(config.participation_max_age_seconds)
    )
    raw_futures = [
        row for event in event_rows
        if (row := _futures_market_row(event)) is not None
    ]
    analysis_start = session_instant(session, STRIKE_REFERENCE_TIME)
    futures_volume = futures_volume_rows(
        raw_futures,
        observation_rows,
        analysis_start=analysis_start,
        max_gap_seconds=float(config.participation_max_age_seconds),
    )
    futures_volume_minutes = compact_futures_volume_minutes(futures_volume)
    inventory = intraday_inventory_rows(
        observation_rows,
        futures_oi,
        strikes,
        futures_volume,
        selection,
        session=session.isoformat(),
        max_index_age_seconds=5.0,
    )
    history: dict[str, list[dict[str, object]]] = {}
    for source in inventory:
        row = dict(source)
        row["receipt"] = row.get("t")
        history.setdefault(str(row["family"]), []).append(row)

    latest_receipt = max((str(row["t"]) for row in strikes), default=None)
    selected_symbols = {
        str(contract.get("symbol", "")).upper()
        for side in ("CE", "PE")
        for contract in selection.get(side, [])
        if isinstance(contract, Mapping)
    }
    latest_strikes = [
        row for row in strikes
        if latest_receipt and row["t"] == latest_receipt
        and (not selected_symbols or str(row.get("symbol", "")).upper() in selected_symbols)
    ]
    return {
        "schema": "NEW_DIVERGENCE_LIVE_PROFILE_V1",
        "analysis_start": iso_utc(analysis_start),
        "strike_selection": selection,
        "option_strike_oi": latest_strikes,
        "futures_oi": futures_oi[-120:],
        "futures_volume": futures_volume[-120:],
        "futures_volume_minutes": futures_volume_minutes[-12:],
        "inventory_rows": inventory,
        "visible_intraday_inventory": _latest_by_family(inventory),
        "recent_intraday_inventory_shifts": {
            family: rows[-12:] for family, rows in history.items()
        },
    }
