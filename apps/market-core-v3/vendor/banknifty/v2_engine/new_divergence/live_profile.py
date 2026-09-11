"""Authoritative replay-equivalent market-profile projection for live snapshots."""

from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping

from .clock import iso_utc, parse_instant, session_instant
from .contracts import EngineConfig, EventKind, MarketEvent
from .directional_prediction import prediction_series, decision_bundles, predict_direction
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


def _minute_oi(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Keep the latest causally visible Futures-OI observation per minute."""
    minutes: dict[object, dict[str, object]] = {}
    for source in rows:
        row = dict(source)
        if row.get("t") is None or row.get("oi") is None:
            continue
        minute = parse_instant(str(row["t"])).replace(second=0, microsecond=0)
        minutes[minute] = row
    return [minutes[key] for key in sorted(minutes)]


def _selected_option_flow(
    rows: Iterable[Mapping[str, object]],
    selection: Mapping[str, object],
) -> list[dict[str, object]]:
    """Expose frozen 09:45 CE/PE slot 1-4 histories for synchronized lanes."""
    if selection.get("available") is not True or selection.get("selected_at") is None:
        return []
    selected_at = parse_instant(
        selection["selected_at"], field="ATM selection receipt timestamp"
    )
    expiry = str(selection.get("expiry", ""))
    contracts: dict[str, dict[str, object]] = {}
    for option_type in ("CE", "PE"):
        candidates = selection.get(option_type, [])
        if not isinstance(candidates, list):
            continue
        for source in candidates:
            if not isinstance(source, Mapping):
                continue
            contract = dict(source)
            slot = int(contract.get("slot", 0))
            if 1 <= slot <= 4:
                contracts[str(contract.get("symbol", "")).upper()] = contract

    result: list[dict[str, object]] = []
    for source in rows:
        row = dict(source)
        symbol = str(row.get("symbol", "")).upper()
        contract = contracts.get(symbol)
        if contract is None or (expiry and str(row.get("e", "")) != expiry):
            continue
        receipt = parse_instant(row.get("t"), field="ATM option flow receipt")
        if receipt < selected_at:
            continue
        result.append({
            "t": iso_utc(receipt),
            "k": str(contract.get("option_type", row.get("k", ""))).upper(),
            "s": float(contract.get("strike", row.get("s"))),
            "symbol": symbol,
            "slot": int(contract.get("slot", 0)),
            "oi": row.get("oi"),
            "d": row.get("d"),
            "v": row.get("v"),
            "dv": row.get("dv"),
            "vs": row.get("vs"),
        })
    return sorted(
        result,
        key=lambda row: (parse_instant(row["t"]), str(row["k"]), int(row["slot"])),
    )


def _atm_option_flow(
    rows: Iterable[Mapping[str, object]],
    selection: Mapping[str, object],
) -> list[dict[str, object]]:
    """Backward-compatible slot-1 view retained for older browser clients."""
    return [row for row in _selected_option_flow(rows, selection) if row["slot"] == 1]


def live_profile_projection(
    events: Iterable[MarketEvent],
    observations: Iterable[Mapping[str, object]],
    evidence: Iterable[Mapping[str, object]],
    *,
    session: date,
    config: EngineConfig,
    cash_vix_rows=(),
    through=None,
    direction_history=None,
    actual_publication=None,
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
    selected_option_flow = _selected_option_flow(strikes, selection)
    atm_option_flow = [row for row in selected_option_flow if row["slot"] == 1]
    cash_vix_rows=list(cash_vix_rows)
    if direction_history is None:
        direction_rows=prediction_series(observation_rows,futures_oi,cash_vix_rows,inventory,through=through)
    else:
        # Live publishes only the latest completed decision; never invent old
        # live calls during startup or rewrite an already published record.
        direction_rows=list(direction_history)
        latest_bundle=None
        for bundle in decision_bundles(observation_rows,futures_oi,cash_vix_rows,inventory,through=through):
            latest_bundle=bundle
        if latest_bundle is not None:
            cutoff=parse_instant(latest_bundle['input_cutoff'])
            previous=direction_rows[-1] if direction_rows else None
            as_of=parse_instant(actual_publication or latest_bundle['decision_at'])
            if (previous is None or parse_instant(previous['input_cutoff'])<cutoff) and 0<=(as_of-cutoff).total_seconds()<=30:
                scheduled=latest_bundle['decision_at']
                latest_bundle['decision_at']=iso_utc(as_of)
                latest_bundle['recent_cash_vix']=[r for r in cash_vix_rows if parse_instant(r['t'])<=as_of]
                visible_cash=latest_bundle['recent_cash_vix']
                if visible_cash and (as_of-parse_instant(visible_cash[-1].get('source_published_at') or visible_cash[-1]['t'])).total_seconds()>120:
                    # First observing an old sample at startup does not make its values fresh.
                    latest_bundle['recent_cash_vix']=[]
                decision=predict_direction(latest_bundle)
                decision['scheduled_at']=scheduled
                decision['previous_direction']=previous['direction'] if previous else None
                decision['change_reason']=('First live decision' if previous is None else 'Direction unchanged'
                    if previous['direction']==decision['direction'] else '; '.join(decision['drivers']))
                direction_rows.append(decision)
    return {
        "schema": "NEW_DIVERGENCE_LIVE_PROFILE_V1",
        "analysis_start": iso_utc(analysis_start),
        "strike_selection": selection,
        "option_strike_oi": latest_strikes,
        "atm_option_flow": atm_option_flow,
        "selected_option_flow": selected_option_flow,
        "futures_oi": futures_oi,
        "futures_oi_minutes": _minute_oi(futures_oi),
        "futures_volume": futures_volume,
        "futures_volume_minutes": futures_volume_minutes[-12:],
        "active_futures_symbol": (
            str(futures_volume[-1].get("symbol")) if futures_volume else None
        ),
        "inventory_rows": inventory,
        "visible_intraday_inventory": _latest_by_family(inventory),
        "recent_intraday_inventory_shifts": {
            family: rows[-12:] for family, rows in history.items()
        },
        "directional_prediction": direction_rows[-1] if direction_rows else None,
        "directional_prediction_history": direction_rows[-30:],
        "cash_vix": cash_vix_rows,
    }
