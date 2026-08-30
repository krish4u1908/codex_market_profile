"""Build causal shift episodes and separately sealed future labels."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from pathlib import Path
import statistics
from typing import Iterable, Mapping, Sequence

from .io_utils import (
    atomic_json,
    atomic_jsonl,
    canonical_json,
    finite,
    iso_utc,
    load_json,
    parse_instant,
    read_jsonl,
    sha256_file,
    sha256_text,
    unpack_rows,
)
from .profiles import (
    Contribution,
    FAMILIES,
    VOLUME_FAMILY,
    developing_rows,
    summarize_profile,
)


FEATURE_NAMES = (
    "price_return_1m",
    "price_return_5m",
    "price_return_15m",
    "basis",
    "basis_change_5m",
    "futures_oi_delta",
    "ce_delta_oi_total",
    "pe_delta_oi_total",
    "pe_minus_ce_delta",
    "option_flow_age_seconds",
    "futures_oi_age_seconds",
    "CE_POS_OI_VPOC_shift",
    "CE_NEG_OI_VPOC_shift",
    "PE_POS_OI_VPOC_shift",
    "PE_NEG_OI_VPOC_shift",
    "FUT_POS_OI_VPOC_shift",
    "FUT_NEG_OI_VPOC_shift",
    "BN_REF_FUT_VOLUME_VPOC_shift",
    "shift_family_count",
    "upward_shift_count",
    "downward_shift_count",
    "profile_confluence_count",
    "nearest_support_distance",
    "nearest_resistance_distance",
    "basis_state_numeric",
    "supporting_horizons",
    "ce_minus_pe_upward_migration",
    "price_inside_volume_value_area",
)


@dataclass
class SessionData:
    session: str
    payload_path: Path
    payload_sha256: str
    summary_path: Path
    summary_sha256: str
    observations: list[dict[str, object]]
    price_times: list[datetime]
    prices: list[dict[str, object]]
    futures_oi: list[dict[str, object]]
    option_oi: list[dict[str, object]]
    states: list[dict[str, object]]
    contributions: list[Contribution]
    inventory_rows: list[dict[str, object]]
    reconstructed_inventory_rows: list[dict[str, object]]
    analysis_start: datetime
    strike_selected_at: datetime | None
    strike_symbols: dict[str, str]
    futures_market_retained: bool
    input_files: list[dict[str, object]]


def validate_config(config: Mapping[str, object]) -> dict[str, object]:
    if config.get("schema") != "BANKNIFTY_MARKET_PROFILE_LEARNING_CONFIG_V1":
        raise ValueError("unexpected learning configuration schema")
    splits = config.get("splits")
    if not isinstance(splits, Mapping):
        raise ValueError("splits are missing")
    seen: set[str] = set()
    result_splits: dict[str, list[str]] = {}
    for split in ("train", "validation", "holdout"):
        raw = splits.get(split)
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"split {split} must be a non-empty date list")
        values = [str(value) for value in raw]
        if values != sorted(values) or len(values) != len(set(values)):
            raise ValueError(f"split {split} must be sorted and unique")
        overlap = seen.intersection(values)
        if overlap:
            raise ValueError(f"split dates overlap: {sorted(overlap)}")
        seen.update(values)
        result_splits[split] = values
    if not max(result_splits["train"]) < min(result_splits["validation"]):
        raise ValueError("training dates must precede validation dates")
    if not max(result_splits["validation"]) < min(result_splits["holdout"]):
        raise ValueError("validation dates must precede holdout dates")
    horizons = config.get("horizons_minutes")
    if horizons != [5, 15, 30]:
        raise ValueError("pilot horizons must be exactly [5, 15, 30]")
    for key in (
        "direction_threshold_points",
        "profile_bin_points",
        "value_area_fraction",
        "max_index_age_seconds",
        "level_touch_tolerance_points",
    ):
        if finite(config.get(key)) is None:
            raise ValueError(f"configuration field {key} is not finite")
    return {**dict(config), "splits": result_splits}


def _verify_run_artifacts(run_directory: Path, summary: Mapping[str, object]) -> list[dict[str, object]]:
    files = summary.get("files")
    hashes = summary.get("artifact_sha256")
    if not isinstance(files, Mapping) or not isinstance(hashes, Mapping):
        raise ValueError(f"{run_directory}: summary lacks artifact contract")
    verified: list[dict[str, object]] = []
    for key, relative_value in sorted(files.items()):
        relative = str(relative_value)
        if Path(relative).name != relative:
            raise ValueError(f"{run_directory}: unsafe artifact path {relative!r}")
        path = run_directory / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        expected = str(hashes.get(key, ""))
        if actual != expected:
            raise ValueError(f"{path}: artifact hash differs from summary")
        verified.append({
            "kind": str(key),
            "path": str(path),
            "sha256": actual,
            "size_bytes": path.stat().st_size,
        })
    return verified


def _causal_index_matcher(
    observations: Sequence[Mapping[str, object]], *, max_age_seconds: float
):
    rows: list[tuple[datetime, datetime, float]] = []
    for row in observations:
        index_price = finite(row.get("index_price"))
        if index_price is None:
            continue
        rows.append((
            parse_instant(row.get("timestamp")),
            parse_instant(row.get("index_receipt_timestamp")),
            index_price,
        ))
    rows.sort(key=lambda item: item[0])
    timestamps = [row[0] for row in rows]

    def match(value: object) -> float | None:
        receipt = value if isinstance(value, datetime) else parse_instant(value)
        position = bisect_right(timestamps, receipt) - 1
        if position < 0:
            return None
        _, index_receipt, price = rows[position]
        age = (receipt - index_receipt).total_seconds()
        if age < 0 or age > max_age_seconds:
            return None
        return price

    return match


def _futures_volume_contributions(
    rows: Sequence[Mapping[str, object]],
    observations: Sequence[Mapping[str, object]],
    *,
    session: str,
    analysis_start: datetime,
    max_gap_seconds: float,
) -> list[Contribution]:
    index_by_receipt = {
        parse_instant(row["timestamp"]): finite(row.get("index_price"))
        for row in observations
    }
    unique: dict[str, dict[str, object]] = {}
    for source in rows:
        event_id = str(source.get("event_id", "")).strip()
        symbol = str(source.get("symbol", "")).upper().strip()
        if not event_id or not symbol:
            raise ValueError("Futures market row has incomplete identity")
        receipt = parse_instant(source.get("t"))
        if receipt < analysis_start:
            continue
        volume = finite(source.get("v"))
        current = {
            "event_id": event_id,
            "symbol": symbol,
            "t": receipt,
            "volume": volume,
            "index_price": index_by_receipt.get(receipt),
        }
        if event_id in unique and unique[event_id] != current:
            raise ValueError(f"Futures market event {event_id!r} is inconsistent")
        unique[event_id] = current
    ordered = sorted(unique.values(), key=lambda row: (row["t"], row["event_id"]))
    previous_by_symbol: dict[str, dict[str, object]] = {}
    contributions: list[Contribution] = []
    for row in ordered:
        previous = previous_by_symbol.get(str(row["symbol"]))
        if previous is not None and row["volume"] is not None and previous["volume"] is not None:
            gap = (row["t"] - previous["t"]).total_seconds()
            delta = float(row["volume"]) - float(previous["volume"])
            index_price = finite(row.get("index_price"))
            if 0 <= gap <= max_gap_seconds and delta > 0 and index_price is not None:
                contributions.append(Contribution(
                    timestamp=row["t"],
                    family=VOLUME_FAMILY,
                    index_price=index_price,
                    weight=delta,
                    source_id=str(row["event_id"]),
                    session=session,
                ))
        previous_by_symbol[str(row["symbol"])] = row
    return contributions


def _inventory_contributions(
    futures_oi: Sequence[Mapping[str, object]],
    option_oi: Sequence[Mapping[str, object]],
    observations: Sequence[Mapping[str, object]],
    futures_market: Sequence[Mapping[str, object]],
    *,
    session: str,
    analysis_start: datetime,
    strike_selected_at: datetime | None,
    strike_symbols: Mapping[str, str],
    max_index_age_seconds: float,
    max_gap_seconds: float,
) -> list[Contribution]:
    match_index = _causal_index_matcher(
        observations, max_age_seconds=max_index_age_seconds
    )
    result: list[Contribution] = []
    for row in futures_oi:
        delta = finite(row.get("d"))
        receipt = parse_instant(row.get("t"))
        if receipt < analysis_start or delta is None or delta == 0:
            continue
        index_price = match_index(receipt)
        if index_price is None:
            continue
        result.append(Contribution(
            timestamp=receipt,
            family="FUT_POS_OI_VPOC" if delta > 0 else "FUT_NEG_OI_VPOC",
            index_price=index_price,
            weight=abs(delta),
            source_id=str(row.get("event_id", "")),
            session=session,
        ))
    for row in option_oi:
        symbol = str(row.get("symbol", "")).upper()
        option_type = strike_symbols.get(symbol)
        delta = finite(row.get("d"))
        receipt = parse_instant(row.get("t"))
        if (
            receipt < analysis_start
            or (strike_selected_at is not None and receipt < strike_selected_at)
            or option_type not in {"CE", "PE"}
            or delta is None
            or delta == 0
        ):
            continue
        index_price = match_index(receipt)
        if index_price is None:
            continue
        result.append(Contribution(
            timestamp=receipt,
            family=f"{option_type}_{'POS' if delta > 0 else 'NEG'}_OI_VPOC",
            index_price=index_price,
            weight=abs(delta),
            source_id=f"{row.get('event_id', '')}:{symbol}",
            session=session,
        ))
    result.extend(_futures_volume_contributions(
        futures_market,
        observations,
        session=session,
        analysis_start=analysis_start,
        max_gap_seconds=max_gap_seconds,
    ))
    return sorted(result, key=lambda row: (row.timestamp, row.family, row.source_id))


def _float_equal(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is None and right is None
    lvalue, rvalue = finite(left), finite(right)
    return (
        lvalue is not None
        and rvalue is not None
        and math.isclose(lvalue, rvalue, rel_tol=0, abs_tol=1e-9)
    )


def _verify_inventory_equivalence(
    published: Sequence[Mapping[str, object]],
    reconstructed: Sequence[Mapping[str, object]],
    *,
    session: str,
) -> None:
    if len(published) != len(reconstructed):
        raise ValueError(
            f"{session}: reconstructed inventory count {len(reconstructed)} "
            f"differs from published count {len(published)}"
        )
    fields = ("t", "family", "control_value", "value_area_low", "value_area_high")
    for position, (expected, actual) in enumerate(zip(published, reconstructed)):
        for field in fields:
            if field in {"control_value", "value_area_low", "value_area_high"}:
                equal = _float_equal(expected.get(field), actual.get(field))
            else:
                equal = expected.get(field) == actual.get(field)
            if not equal:
                raise ValueError(
                    f"{session}: inventory reconstruction mismatch at row {position} "
                    f"field {field}: published={expected.get(field)!r} "
                    f"reconstructed={actual.get(field)!r}"
                )


def load_session(
    run_root: Path,
    gui_root: Path,
    entry: Mapping[str, object],
    config: Mapping[str, object],
) -> SessionData:
    session = str(entry.get("session"))
    payload_relative = entry.get("payload")
    if not isinstance(payload_relative, str):
        raise ValueError(f"{session}: eligible session has no payload")
    payload_path = gui_root / payload_relative
    payload_value = load_json(payload_path)
    if not isinstance(payload_value, Mapping):
        raise ValueError(f"{payload_path}: payload is not an object")
    payload = dict(payload_value)
    run_directory = run_root / session
    summary_path = run_directory / "summary.json"
    summary_value = load_json(summary_path)
    if not isinstance(summary_value, Mapping):
        raise ValueError(f"{summary_path}: summary is not an object")
    summary = dict(summary_value)
    if str(summary.get("session")) != session or str(payload.get("session")) != session:
        raise ValueError(f"{session}: session identity mismatch")
    input_files = _verify_run_artifacts(run_directory, summary)
    files = summary.get("files")
    if not isinstance(files, Mapping):
        raise ValueError(f"{summary_path}: files contract is invalid")
    observations = read_jsonl(run_directory / str(files["basis"]))
    futures_market_relative = files.get("futures_market")
    if futures_market_relative is None:
        futures_market_retained = False
        futures_market: list[dict[str, object]] = []
    elif isinstance(futures_market_relative, str):
        futures_market_retained = True
        futures_market = read_jsonl(run_directory / futures_market_relative)
    else:
        raise ValueError(
            f"{session}: futures_market artifact declaration must be a filename"
        )
    futures_oi = unpack_rows(payload.get("futures_oi"), name=f"{session}.futures_oi")
    option_oi = unpack_rows(payload.get("option_strike_oi"), name=f"{session}.option_strike_oi")
    states = unpack_rows(payload.get("states"), name=f"{session}.states")
    inventory_value = payload.get("intraday_inventory")
    inventory_rows = unpack_rows(inventory_value, name=f"{session}.intraday_inventory")
    if not isinstance(inventory_value, Mapping):
        raise ValueError(f"{session}: intraday inventory is invalid")
    analysis_start = parse_instant(inventory_value.get("analysis_start"))
    selection = payload.get("option_strike_oi", {})
    strike_selection = selection.get("strike_selection", {}) if isinstance(selection, Mapping) else {}
    strike_symbols: dict[str, str] = {}
    strike_selected_at: datetime | None = None
    if isinstance(strike_selection, Mapping):
        if strike_selection.get("available") is True and strike_selection.get("selected_at"):
            strike_selected_at = parse_instant(strike_selection["selected_at"])
        for option_type in ("CE", "PE"):
            contracts = strike_selection.get(option_type, [])
            if isinstance(contracts, list):
                for contract in contracts:
                    if isinstance(contract, Mapping) and contract.get("symbol"):
                        strike_symbols[str(contract["symbol"]).upper()] = option_type
    runtime_config = payload.get("config", {})
    gap_seconds = (
        finite(runtime_config.get("participation_max_age_seconds"))
        if isinstance(runtime_config, Mapping) else None
    )
    if gap_seconds is None:
        raise ValueError(f"{session}: participation gap is unavailable")
    contributions = _inventory_contributions(
        futures_oi,
        option_oi,
        observations,
        futures_market,
        session=session,
        analysis_start=analysis_start,
        strike_selected_at=strike_selected_at,
        strike_symbols=strike_symbols,
        max_index_age_seconds=float(config["max_index_age_seconds"]),
        max_gap_seconds=gap_seconds,
    )
    reconstructed = developing_rows(
        contributions,
        session=session,
        bin_points=int(config["profile_bin_points"]),
        value_area_fraction=float(config["value_area_fraction"]),
    )
    _verify_inventory_equivalence(inventory_rows, reconstructed, session=session)
    prices = sorted(observations, key=lambda row: parse_instant(row["timestamp"]))
    price_times = [parse_instant(row["timestamp"]) for row in prices]
    return SessionData(
        session=session,
        payload_path=payload_path,
        payload_sha256=sha256_file(payload_path),
        summary_path=summary_path,
        summary_sha256=sha256_file(summary_path),
        observations=observations,
        price_times=price_times,
        prices=prices,
        futures_oi=sorted(futures_oi, key=lambda row: parse_instant(row["t"])),
        option_oi=sorted(option_oi, key=lambda row: parse_instant(row["t"])),
        states=sorted(states, key=lambda row: parse_instant(row["t"])),
        contributions=contributions,
        inventory_rows=inventory_rows,
        reconstructed_inventory_rows=reconstructed,
        analysis_start=analysis_start,
        strike_selected_at=strike_selected_at,
        strike_symbols=strike_symbols,
        futures_market_retained=futures_market_retained,
        input_files=input_files,
    )


def _asof(rows: Sequence[Mapping[str, object]], field: str, cutoff: datetime) -> Mapping[str, object] | None:
    if not rows:
        return None
    timestamps = [parse_instant(row[field]) for row in rows]
    position = bisect_right(timestamps, cutoff) - 1
    return None if position < 0 else rows[position]


def _price_asof(data: SessionData, cutoff: datetime) -> Mapping[str, object] | None:
    position = bisect_right(data.price_times, cutoff) - 1
    return None if position < 0 else data.prices[position]


def _price_change(data: SessionData, cutoff: datetime, minutes: int) -> float | None:
    current = _price_asof(data, cutoff)
    previous = _price_asof(data, cutoff - timedelta(minutes=minutes))
    if current is None or previous is None:
        return None
    left, right = finite(current.get("index_price")), finite(previous.get("index_price"))
    return None if left is None or right is None else left - right


def _basis_change(data: SessionData, cutoff: datetime, minutes: int) -> float | None:
    current = _price_asof(data, cutoff)
    previous = _price_asof(data, cutoff - timedelta(minutes=minutes))
    if current is None or previous is None:
        return None
    left, right = finite(current.get("basis")), finite(previous.get("basis"))
    return None if left is None or right is None else left - right


def _latest_option_flow(data: SessionData, cutoff: datetime) -> dict[str, object]:
    eligible = [
        row for row in data.option_oi
        if str(row.get("symbol", "")).upper() in data.strike_symbols
        and parse_instant(row["t"]) <= cutoff
    ]
    if not eligible:
        return {"t": None, "CE": None, "PE": None, "rows": []}
    latest = max(parse_instant(row["t"]) for row in eligible)
    receipt_rows = [row for row in eligible if parse_instant(row["t"]) == latest]
    totals = {"CE": 0.0, "PE": 0.0}
    observed = {"CE": False, "PE": False}
    selected: list[dict[str, object]] = []
    for row in receipt_rows:
        symbol = str(row.get("symbol", "")).upper()
        option_type = data.strike_symbols.get(symbol)
        delta = finite(row.get("d"))
        if option_type in totals and delta is not None:
            totals[option_type] += delta
            observed[option_type] = True
            selected.append({
                "option_type": option_type,
                "strike": row.get("s"),
                "delta_oi": delta,
                "premium": row.get("p"),
                "volume_delta": row.get("dv"),
                "symbol": symbol,
            })
    selected.sort(key=lambda row: abs(float(row["delta_oi"])), reverse=True)
    return {
        "t": iso_utc(latest),
        "CE": totals["CE"] if observed["CE"] else None,
        "PE": totals["PE"] if observed["PE"] else None,
        "rows": selected[:8],
    }


def _prior_context(
    target_session: str,
    all_sessions: Mapping[str, SessionData],
    config: Mapping[str, object],
) -> list[dict[str, object]]:
    previous = sorted(session for session in all_sessions if session < target_session)
    result: list[dict[str, object]] = []
    for count, scope in ((1, "1D"), (2, "2D"), (3, "3D")):
        selected_dates = previous[-count:]
        contributions = [
            contribution
            for session in selected_dates
            for contribution in all_sessions[session].contributions
        ]
        for family in FAMILIES:
            summary = summarize_profile(
                contributions,
                family=family,
                scope=scope,
                bin_points=int(config["profile_bin_points"]),
                value_area_fraction=float(config["value_area_fraction"]),
            )
            if summary is not None:
                result.append(summary)
    return result


def _level_candidates(
    current_state: Mapping[str, Mapping[str, object]],
    prior: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    raw: list[dict[str, object]] = []
    sources: list[Mapping[str, object]] = [*current_state.values(), *prior]
    for row in sources:
        scope = str(row.get("scope", "ID"))
        family = str(row.get("family", ""))
        for kind, field in (
            ("VPOC", "control_value"),
            ("VAL", "value_area_low"),
            ("VAH", "value_area_high"),
        ):
            value = finite(row.get(field))
            if value is None:
                continue
            raw.append({"level": value, "scope": scope, "family": family, "kind": kind})
    grouped: defaultdict[float, list[dict[str, object]]] = defaultdict(list)
    for row in raw:
        grouped[float(row["level"])].append(row)
    return [
        {"level": level, "sources": sorted(rows, key=canonical_json), "confluence": len(rows)}
        for level, rows in sorted(grouped.items())
    ]


def _episode_components(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    previous: dict[str, Mapping[str, object]] = {}
    components: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda value: (parse_instant(value["t"]), str(value["family"]))):
        family = str(row["family"])
        prior = previous.get(family)
        previous[family] = row
        if prior is None:
            continue
        old = finite(prior.get("control_value"))
        new = finite(row.get("control_value"))
        if old is None or new is None or math.isclose(old, new, rel_tol=0, abs_tol=1e-12):
            # Volume value-area changes with a stable VPOC remain real display
            # changes, but this pilot's directional episodes require a control shift.
            continue
        components.append({
            "t": str(row["t"]),
            "family": family,
            "previous_control": old,
            "new_control": new,
            "shift_points": new - old,
            "previous_value_area_low": prior.get("value_area_low"),
            "previous_value_area_high": prior.get("value_area_high"),
            "new_value_area_low": row.get("value_area_low"),
            "new_value_area_high": row.get("value_area_high"),
            "total_weight": row.get("total_weight"),
            "evidence_count": row.get("evidence_count"),
            "trigger_source_ids": list(row.get("trigger_source_ids", [])),
        })
    return components


def _group_components(
    components: Sequence[Mapping[str, object]], merge_seconds: float
) -> list[list[dict[str, object]]]:
    ordered = sorted((dict(row) for row in components), key=lambda row: parse_instant(row["t"]))
    groups: list[list[dict[str, object]]] = []
    for row in ordered:
        if not groups:
            groups.append([row])
            continue
        last_time = parse_instant(groups[-1][-1]["t"])
        current = parse_instant(row["t"])
        if 0 <= (current - last_time).total_seconds() <= merge_seconds:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def _future_label(
    data: SessionData,
    cutoff: datetime,
    horizon: int,
    threshold: float,
    sensitivities: Sequence[float],
) -> dict[str, object]:
    current = _price_asof(data, cutoff)
    if current is None:
        return {"available": False, "reason": "NO_CURRENT_PRICE"}
    current_price = finite(current.get("index_price"))
    if current_price is None:
        return {"available": False, "reason": "NO_CURRENT_INDEX_PRICE"}
    target = cutoff + timedelta(minutes=horizon)
    end_position = bisect_left(data.price_times, target)
    if end_position >= len(data.price_times):
        return {"available": False, "reason": "HORIZON_EXCEEDS_SESSION"}
    end_time = data.price_times[end_position]
    if (end_time - target).total_seconds() > 30:
        return {"available": False, "reason": "NO_NEAR_HORIZON_PRICE"}
    start_position = bisect_right(data.price_times, cutoff)
    path = data.prices[start_position:end_position + 1]
    path_prices = [finite(row.get("index_price")) for row in path]
    path_values = [value for value in path_prices if value is not None]
    end_price = finite(data.prices[end_position].get("index_price"))
    if end_price is None or not path_values:
        return {"available": False, "reason": "NO_FUTURE_PATH"}
    delta = end_price - current_price

    def classify(limit: float) -> str:
        if delta >= limit:
            return "UP"
        if delta <= -limit:
            return "DOWN"
        return "ROTATION"

    return {
        "available": True,
        "horizon_minutes": horizon,
        "target_timestamp": iso_utc(target),
        "observed_timestamp": iso_utc(end_time),
        "start_price": current_price,
        "end_price": end_price,
        "delta_points": delta,
        "high_price": max(path_values),
        "low_price": min(path_values),
        "maximum_favourable_up": max(path_values) - current_price,
        "maximum_favourable_down": current_price - min(path_values),
        "direction": classify(threshold),
        "sensitivity": {str(int(limit)): classify(limit) for limit in sensitivities},
    }


def _feature_values(
    data: SessionData,
    cutoff: datetime,
    components: Sequence[Mapping[str, object]],
    current_inventory: Mapping[str, Mapping[str, object]],
    level_candidates: Sequence[Mapping[str, object]],
) -> tuple[dict[str, float | None], dict[str, object]]:
    current = _price_asof(data, cutoff)
    if current is None:
        raise ValueError(f"{data.session}: shift has no causal price")
    index_price = finite(current.get("index_price"))
    basis = finite(current.get("basis"))
    if index_price is None:
        raise ValueError(f"{data.session}: shift has no finite Index price")
    latest_futures = _asof(data.futures_oi, "t", cutoff)
    futures_delta = finite(latest_futures.get("d")) if latest_futures else None
    futures_age = (
        (cutoff - parse_instant(latest_futures["t"])).total_seconds()
        if latest_futures else None
    )
    option = _latest_option_flow(data, cutoff)
    option_time = parse_instant(option["t"]) if option["t"] else None
    option_age = (cutoff - option_time).total_seconds() if option_time else None
    state = _asof(data.states, "t", cutoff)
    state_value = str(state.get("s", "")) if state else ""
    state_numeric = 1.0 if "GREEN" in state_value else -1.0 if "RED" in state_value else 0.0
    supporting = finite(state.get("n")) if state else None
    shifts = {family: 0.0 for family in FAMILIES}
    for component in components:
        family = str(component["family"])
        if family in shifts:
            shifts[family] += float(component["shift_points"])
    support_levels = [float(row["level"]) for row in level_candidates if float(row["level"]) <= index_price]
    resistance_levels = [float(row["level"]) for row in level_candidates if float(row["level"]) >= index_price]
    confluence = max((int(row.get("confluence", 1)) for row in level_candidates), default=0)
    volume = current_inventory.get(VOLUME_FAMILY)
    inside_value_area = None
    if volume:
        low, high = finite(volume.get("value_area_low")), finite(volume.get("value_area_high"))
        if low is not None and high is not None:
            inside_value_area = 1.0 if low <= index_price <= high else 0.0
    ce_migration = shifts["CE_POS_OI_VPOC"] + shifts["CE_NEG_OI_VPOC"]
    pe_migration = shifts["PE_POS_OI_VPOC"] + shifts["PE_NEG_OI_VPOC"]
    features: dict[str, float | None] = {
        "price_return_1m": _price_change(data, cutoff, 1),
        "price_return_5m": _price_change(data, cutoff, 5),
        "price_return_15m": _price_change(data, cutoff, 15),
        "basis": basis,
        "basis_change_5m": _basis_change(data, cutoff, 5),
        "futures_oi_delta": futures_delta,
        "ce_delta_oi_total": finite(option.get("CE")),
        "pe_delta_oi_total": finite(option.get("PE")),
        "pe_minus_ce_delta": (
            None if finite(option.get("PE")) is None or finite(option.get("CE")) is None
            else float(option["PE"]) - float(option["CE"])
        ),
        "option_flow_age_seconds": option_age,
        "futures_oi_age_seconds": futures_age,
        **{f"{family}_shift": shifts[family] for family in FAMILIES},
        "shift_family_count": float(len({str(row["family"]) for row in components})),
        "upward_shift_count": float(sum(float(row["shift_points"]) > 0 for row in components)),
        "downward_shift_count": float(sum(float(row["shift_points"]) < 0 for row in components)),
        "profile_confluence_count": float(confluence),
        "nearest_support_distance": (
            index_price - max(support_levels) if support_levels else None
        ),
        "nearest_resistance_distance": (
            min(resistance_levels) - index_price if resistance_levels else None
        ),
        "basis_state_numeric": state_numeric,
        "supporting_horizons": supporting,
        "ce_minus_pe_upward_migration": ce_migration - pe_migration,
        "price_inside_volume_value_area": inside_value_area,
    }
    if set(features) != set(FEATURE_NAMES):
        raise AssertionError("feature contract differs from FEATURE_NAMES")
    features = {name: features[name] for name in FEATURE_NAMES}
    context = {
        "index_price": index_price,
        "futures_price": finite(current.get("futures_price")),
        "basis": basis,
        "price_receipt_timestamp": current.get("timestamp"),
        "latest_futures_oi": None if latest_futures is None else dict(latest_futures),
        "latest_option_flow": option,
        "latest_basis_state": None if state is None else dict(state),
    }
    return features, context


def _scaler(cases: Sequence[Mapping[str, object]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for feature in FEATURE_NAMES:
        values = [
            finite(case.get("features_raw", {}).get(feature))
            for case in cases
            if isinstance(case.get("features_raw"), Mapping)
        ]
        present = [value for value in values if value is not None]
        if not present:
            result[feature] = {"center": 0.0, "scale": 1.0, "count": 0.0}
            continue
        center = statistics.median(present)
        deviations = [abs(value - center) for value in present]
        scale = statistics.median(deviations) * 1.4826
        if not math.isfinite(scale) or scale < 1e-9:
            scale = statistics.pstdev(present) if len(present) > 1 else 1.0
        if not math.isfinite(scale) or scale < 1e-9:
            scale = 1.0
        result[feature] = {"center": center, "scale": scale, "count": float(len(present))}
    return result


def _normalize(
    raw: Mapping[str, object], scaler: Mapping[str, Mapping[str, float]]
) -> dict[str, float]:
    result: dict[str, float] = {}
    for feature in FEATURE_NAMES:
        value = finite(raw.get(feature))
        center = float(scaler[feature]["center"])
        scale = float(scaler[feature]["scale"])
        normalized = 0.0 if value is None else (value - center) / scale
        result[feature] = max(-8.0, min(8.0, normalized))
    return result


def _training_summary(
    cases: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    config: Mapping[str, object],
) -> dict[str, object]:
    label_by_case = {str(row["case_id"]): row for row in labels}
    horizons: dict[str, object] = {}
    for horizon in config["horizons_minutes"]:
        paired: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
        for case in cases:
            label = label_by_case.get(str(case["case_id"]))
            outcome = None if label is None else label.get("outcomes", {}).get(str(horizon))
            if isinstance(outcome, Mapping) and outcome.get("available") is True:
                paired.append((case, outcome))
        directions = Counter(str(outcome["direction"]) for _, outcome in paired)
        feature_rows = []
        for feature in FEATURE_NAMES:
            points = [
                (finite(case["features"].get(feature)), finite(outcome.get("delta_points")))
                for case, outcome in paired
            ]
            valid = [(x, y) for x, y in points if x is not None and y is not None]
            correlation = 0.0
            if len(valid) >= 3:
                xs = [x for x, _ in valid]
                ys = [y for _, y in valid]
                mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
                numerator = sum((x - mean_x) * (y - mean_y) for x, y in valid)
                denominator = math.sqrt(
                    sum((x - mean_x) ** 2 for x in xs)
                    * sum((y - mean_y) ** 2 for y in ys)
                )
                if denominator > 0:
                    correlation = numerator / denominator
            means = {}
            for direction in ("UP", "DOWN", "ROTATION"):
                selected = [
                    finite(case["features"].get(feature))
                    for case, outcome in paired
                    if outcome["direction"] == direction
                ]
                present = [value for value in selected if value is not None]
                means[direction] = None if not present else statistics.fmean(present)
            feature_rows.append({
                "feature": feature,
                "correlation_with_forward_points": correlation,
                "normalized_mean_by_direction": means,
                "count": len(valid),
            })
        feature_rows.sort(
            key=lambda row: abs(float(row["correlation_with_forward_points"])),
            reverse=True,
        )
        horizons[str(horizon)] = {
            "case_count": len(paired),
            "class_counts": dict(sorted(directions.items())),
            "feature_statistics": feature_rows,
        }
    family_patterns: dict[str, object] = {}
    for family in FAMILIES:
        rows = []
        for case in cases:
            shift = finite(case.get("features_raw", {}).get(f"{family}_shift"))
            label = label_by_case.get(str(case["case_id"]))
            outcome = None if label is None else label.get("outcomes", {}).get("15")
            if shift in (None, 0) or not isinstance(outcome, Mapping) or outcome.get("available") is not True:
                continue
            rows.append((shift, str(outcome["direction"]), float(outcome["delta_points"])))
        family_patterns[family] = {
            "count": len(rows),
            "upward_shift": dict(Counter(direction for shift, direction, _ in rows if shift > 0)),
            "downward_shift": dict(Counter(direction for shift, direction, _ in rows if shift < 0)),
            "mean_forward_points_upward_shift": (
                None if not any(shift > 0 for shift, _, _ in rows)
                else statistics.fmean(delta for shift, _, delta in rows if shift > 0)
            ),
            "mean_forward_points_downward_shift": (
                None if not any(shift < 0 for shift, _, _ in rows)
                else statistics.fmean(delta for shift, _, delta in rows if shift < 0)
            ),
        }
    return {
        "schema": "BANKNIFTY_MARKET_PROFILE_TRAINING_SUMMARY_V1",
        "classification": config["classification"],
        "session_count": len({str(case["session"]) for case in cases}),
        "episode_count": len(cases),
        "horizons": horizons,
        "family_shift_patterns_15m": family_patterns,
        "interpretation_boundary": [
            "OI changes do not identify buyer-versus-writer initiation.",
            "Rows from one session are correlated; the effective sample size is the session count.",
            "Only causal prefix features are present in cases; outcomes are stored separately.",
            "Correlation is descriptive and is not proof of a stable directional edge."
        ],
    }


def build_dataset(
    *,
    run_root: Path,
    gui_root: Path,
    config_path: Path,
    output_root: Path,
) -> dict[str, object]:
    config_value = load_json(config_path)
    if not isinstance(config_value, Mapping):
        raise ValueError("configuration must be a JSON object")
    config = validate_config(config_value)
    catalog_value = load_json(gui_root / "catalog.json")
    if not isinstance(catalog_value, Mapping):
        raise ValueError("GUI catalog is invalid")
    entries = {
        str(entry.get("session")): entry
        for entry in catalog_value.get("sessions", [])
        if isinstance(entry, Mapping) and isinstance(entry.get("payload"), str)
    }
    required = {
        session
        for dates in config["splits"].values()
        for session in dates
    }
    missing = sorted(required - set(entries))
    if missing:
        raise ValueError(f"configured sessions lack payloads: {missing}")
    all_sessions: dict[str, SessionData] = {}
    for session, entry in sorted(entries.items()):
        all_sessions[session] = load_session(run_root, gui_root, entry, config)
    cases_by_split: dict[str, list[dict[str, object]]] = {
        "train": [], "validation": [], "holdout": []
    }
    labels_by_split: dict[str, list[dict[str, object]]] = {
        "train": [], "validation": [], "holdout": []
    }
    session_audit: list[dict[str, object]] = []
    for split, dates in config["splits"].items():
        for session in dates:
            data = all_sessions[session]
            prior = _prior_context(session, all_sessions, config)
            components = _episode_components(data.reconstructed_inventory_rows)
            groups = _group_components(components, float(config["episode_merge_seconds"]))
            current_inventory: dict[str, Mapping[str, object]] = {}
            inventory_ordered = sorted(
                data.reconstructed_inventory_rows,
                key=lambda row: (parse_instant(row["t"]), str(row["family"])),
            )
            inventory_position = 0
            produced = 0
            for group in groups:
                cutoff = max(parse_instant(row["t"]) for row in group)
                while (
                    inventory_position < len(inventory_ordered)
                    and parse_instant(inventory_ordered[inventory_position]["t"]) <= cutoff
                ):
                    row = inventory_ordered[inventory_position]
                    current_inventory[str(row["family"])] = row
                    inventory_position += 1
                levels = _level_candidates(current_inventory, prior)
                features_raw, market_context = _feature_values(
                    data, cutoff, group, current_inventory, levels
                )
                identity = {
                    "session": session,
                    "cutoff": iso_utc(cutoff),
                    "components": [
                        {
                            "family": row["family"],
                            "previous_control": row["previous_control"],
                            "new_control": row["new_control"],
                        }
                        for row in sorted(group, key=lambda row: str(row["family"]))
                    ],
                }
                case_id = f"{session}-{sha256_text(canonical_json(identity))[:16]}"
                case = {
                    "schema": "BANKNIFTY_MARKET_PROFILE_CAUSAL_CASE_V1",
                    "case_id": case_id,
                    "session": session,
                    "split": split,
                    "causal_cutoff": iso_utc(cutoff),
                    "shift_components": sorted(group, key=lambda row: str(row["family"])),
                    "market_context": market_context,
                    "intraday_inventory": [
                        dict(current_inventory[family])
                        for family in sorted(current_inventory)
                    ],
                    "prior_inventory_context": prior,
                    "level_candidates": levels,
                    "features_raw": features_raw,
                    "features": {},
                    "availability": {
                        "families": sorted(current_inventory),
                        "prior_scopes": sorted({str(row["scope"]) for row in prior}),
                    },
                    "classification": config["classification"],
                }
                case_hash = sha256_text(canonical_json(case))
                label = {
                    "schema": "BANKNIFTY_MARKET_PROFILE_SEALED_LABEL_V1",
                    "case_id": case_id,
                    "case_sha256": case_hash,
                    "session": session,
                    "split": split,
                    "outcomes": {
                        str(horizon): _future_label(
                            data,
                            cutoff,
                            int(horizon),
                            float(config["direction_threshold_points"]),
                            [float(value) for value in config["direction_sensitivity_points"]],
                        )
                        for horizon in config["horizons_minutes"]
                    },
                }
                cases_by_split[split].append(case)
                labels_by_split[split].append(label)
                produced += 1
            session_audit.append({
                "session": session,
                "split": split,
                "published_inventory_rows": len(data.inventory_rows),
                "reconstructed_inventory_rows": len(data.reconstructed_inventory_rows),
                "control_shift_components": len(components),
                "episodes": produced,
                "prior_context_rows": len(prior),
                "futures_market_retained": data.futures_market_retained,
                "bn_reference_futures_volume_available": any(
                    row.family == VOLUME_FAMILY for row in data.contributions
                ),
                "inventory_equivalence": "PASS",
            })
    scaler = _scaler(cases_by_split["train"])
    for split, cases in cases_by_split.items():
        for case in cases:
            case["features"] = _normalize(case["features_raw"], scaler)
            matching = next(
                row for row in labels_by_split[split]
                if row["case_id"] == case["case_id"]
            )
            matching["case_sha256"] = sha256_text(canonical_json(case))
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "cases").mkdir()
    (output_root / "labels").mkdir()
    (output_root / "metadata").mkdir()
    (output_root / "summaries").mkdir()
    (output_root / "candidates").mkdir()
    (output_root / "candidate_workspaces").mkdir()
    (output_root / "forecasts").mkdir()
    (output_root / "scores").mkdir()
    (output_root / "reports").mkdir()
    (output_root / "logs").mkdir()
    (output_root / "holdout").mkdir()
    atomic_json(output_root / "metadata" / "learning_config.json", config)
    atomic_json(output_root / "metadata" / "feature_scaler.json", scaler)
    for split in ("train", "validation", "holdout"):
        atomic_jsonl(output_root / "cases" / f"{split}.jsonl", cases_by_split[split])
        atomic_jsonl(output_root / "labels" / f"{split}.jsonl", labels_by_split[split])
    # Labels remain orchestrator-only. Candidate Codex workspaces never contain
    # this directory, and the required Codex permission profile denies the rest
    # of the filesystem.
    for path in (output_root / "labels").iterdir():
        path.chmod(0o600)
    training_summary = _training_summary(
        cases_by_split["train"], labels_by_split["train"], config
    )
    atomic_json(output_root / "summaries" / "training_summary.json", training_summary)
    input_files: list[dict[str, object]] = [
        {
            "kind": "learning_config",
            "path": str(Path(config_path).resolve()),
            "sha256": sha256_file(config_path),
            "size_bytes": Path(config_path).stat().st_size,
        },
        {
            "kind": "gui_catalog",
            "path": str((gui_root / "catalog.json").resolve()),
            "sha256": sha256_file(gui_root / "catalog.json"),
            "size_bytes": (gui_root / "catalog.json").stat().st_size,
        },
    ]
    for session, data in sorted(all_sessions.items()):
        input_files.extend([
            {
                "kind": "browser_payload",
                "session": session,
                "path": str(data.payload_path.resolve()),
                "sha256": data.payload_sha256,
                "size_bytes": data.payload_path.stat().st_size,
            },
            {
                "kind": "run_summary",
                "session": session,
                "path": str(data.summary_path.resolve()),
                "sha256": data.summary_sha256,
                "size_bytes": data.summary_path.stat().st_size,
            },
            *({**row, "session": session} for row in data.input_files),
        ])
    manifest = {
        "schema": "BANKNIFTY_MARKET_PROFILE_INPUT_MANIFEST_V1",
        "classification": config["classification"],
        "files": input_files,
        "splits": config["splits"],
        "counts": {
            split: {
                "sessions": len(config["splits"][split]),
                "episodes": len(cases_by_split[split]),
                "labels": len(labels_by_split[split]),
            }
            for split in ("train", "validation", "holdout")
        },
        "inventory_reconstruction": "EXACT_EQUIVALENCE_VERIFIED_AGAINST_V1_0_19_BROWSER",
        "prior_context": "CAUSALLY_RECONSTRUCTED_COMBINED_1D_2D_3D_FROM_PREVIOUS_ELIGIBLE_SESSIONS",
    }
    manifest["manifest_sha256"] = sha256_text(canonical_json(manifest))
    atomic_json(output_root / "metadata" / "input_manifest.json", manifest)
    atomic_json(output_root / "metadata" / "session_audit.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_SESSION_AUDIT_V1",
        "sessions": session_audit,
    })
    atomic_json(output_root / "holdout" / "SEALED.json", {
        "schema": "BANKNIFTY_MARKET_PROFILE_HOLDOUT_SEAL_V1",
        "state": "SEALED",
        "sessions": config["splits"]["holdout"],
        "cases_sha256": sha256_file(output_root / "cases" / "holdout.jsonl"),
        "labels_sha256": sha256_file(output_root / "labels" / "holdout.jsonl"),
        "rule": "Candidate generation is forbidden after holdout opening.",
    })
    return manifest
