from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import deque
from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

IST = "+05:30"


def parse_ts(value: str) -> datetime:
    value = value.replace(" ", "T")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError(f"timezone-naive timestamp: {value}")
    return result


def canonical_float(value):
    if value is None or value == "":
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def percentile_rank(history: list[float], value: float | None):
    if value is None or not history:
        return None
    return sum(x <= value for x in history) / len(history)


def robust_z(history: list[float], value: float | None):
    if value is None or len(history) < 3:
        return None
    median = statistics.median(history)
    mad = statistics.median(abs(x - median) for x in history)
    return 0.0 if mad == 0 and value == median else (None if mad == 0 else 0.67448975 * (value - median) / mad)


def elapsed_change(rows: list[dict], at: datetime, field: str, minutes: int):
    i=_right_index(rows,at)
    while i>=0 and rows[i].get(field) is None:i-=1
    current=rows[i] if i>=0 else None
    if current is None:return None
    cutoff = at - timedelta(minutes=minutes)
    j=_right_index(rows,cutoff)
    while j>=0 and rows[j].get(field) is None:j-=1
    prior=rows[j] if j>=0 else None
    return None if prior is None else current[field] - prior[field]


def window_increment(rows: list[dict], at: datetime, field: str, minutes: int = 5):
    eligible = [r for r in rows if at - timedelta(minutes=minutes) < r["receipt"] <= at and r.get(field) is not None]
    if len(eligible) < 2:
        return None, "MISSING_BOUNDARY"
    increments = 0.0
    reset = False
    duplicate = False
    for left, right in zip(eligible, eligible[1:]):
        if right["receipt"] == left["receipt"] and right[field] == left[field]:
            duplicate = True
            continue
        delta = right[field] - left[field]
        if delta < 0:
            reset = True
            continue
        increments += delta
    flags = ";".join(x for x, yes in (("RESET", reset), ("DUPLICATE", duplicate)) if yes) or "VALID"
    return increments, flags


def asof(rows: list[dict], at: datetime):
    i=_right_index(rows,at)
    return rows[i] if i>=0 else None


def _right_index(rows:list[dict],at:datetime):
    lo,hi=0,len(rows)
    while lo<hi:
        mid=(lo+hi)//2
        if rows[mid]["receipt"]<=at:lo=mid+1
        else:hi=mid
    return lo-1


def deterministic_id(*parts: object) -> str:
    return "R6B3-" + hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:24].upper()


def timing_cohort(confirmation: datetime, receipt: datetime) -> str:
    seconds = (receipt - confirmation).total_seconds()
    if seconds <= 0:
        return "PRE_EXISTING_AT_CONFIRMATION"
    if seconds <= 60:
        return "NEW_WITHIN_1_MINUTE"
    if seconds <= 180:
        return "NEW_WITHIN_3_MINUTES"
    if seconds <= 300:
        return "NEW_WITHIN_5_MINUTES"
    if seconds <= 600:
        return "NEW_WITHIN_10_MINUTES"
    return "NEW_AFTER_10_MINUTES"


def option_inventory_state(delta_oi, premium_change):
    if delta_oi is None or premium_change is None:
        return "INSUFFICIENT_EVIDENCE"
    oi = "UP" if delta_oi > 0 else "DOWN" if delta_oi < 0 else "UNCHANGED"
    premium = "UP" if premium_change > 0 else "DOWN" if premium_change < 0 else "UNCHANGED"
    if oi == "UNCHANGED" or premium == "UNCHANGED":
        return f"OI_{oi}_PREMIUM_{premium}"
    return {
        ("UP", "UP"): "PROBABLE_LONG_OPTION_DEMAND",
        ("UP", "DOWN"): "PROBABLE_WRITING_OR_SUPPLY",
        ("DOWN", "UP"): "PROBABLE_SHORT_COVERING_OR_POSITION_EXIT",
        ("DOWN", "DOWN"): "PROBABLE_LONG_UNWINDING_OR_POSITION_EXIT",
    }[(oi, premium)]


def conservative_semantic(colour, option_type, delta_oi, premium_change, underlying_change):
    if delta_oi is None or premium_change is None:
        return "INSUFFICIENT_EVIDENCE"
    if delta_oi == 0 or premium_change == 0:
        return "NEUTRAL_AMBIGUOUS"
    # Premium direction expected mechanically from the underlying is not independent evidence.
    mechanical = underlying_change is not None and underlying_change != 0 and (
        (option_type == "CE" and premium_change * underlying_change > 0)
        or (option_type == "PE" and premium_change * underlying_change < 0)
    )
    if mechanical:
        return "MECHANICALLY_ALIGNED_PREMIUM"
    bullish = (option_type == "CE" and ((delta_oi > 0 and premium_change > 0) or (delta_oi < 0 and premium_change > 0))) or (
        option_type == "PE" and ((delta_oi > 0 and premium_change < 0) or (delta_oi < 0 and premium_change < 0))
    )
    bearish = (option_type == "CE" and ((delta_oi > 0 and premium_change < 0) or (delta_oi < 0 and premium_change < 0))) or (
        option_type == "PE" and ((delta_oi > 0 and premium_change > 0) or (delta_oi < 0 and premium_change > 0))
    )
    # Explicit conservative exceptions required by R6B3.
    if delta_oi < 0 and premium_change < 0 and ((colour == "GREEN" and option_type == "CE") or (colour == "RED" and option_type == "PE")):
        return "NEUTRAL_AMBIGUOUS"
    expected_bullish = colour == "GREEN"
    return "SUPPORTIVE" if bullish == expected_bullish else "CONTRADICTORY" if bearish == expected_bullish else "NEUTRAL_AMBIGUOUS"


def select_strikes(chain: list[dict], underlying: float, step: int = 100, near: int = 3):
    expiries = sorted({r["expiry"] for r in chain if r.get("expiry")})
    if not expiries:
        return [], None, None
    expiry = expiries[0]
    current = [r for r in chain if r["expiry"] == expiry]
    strikes = sorted({r["strike"] for r in current if r.get("strike") is not None})
    if not strikes:
        return [], expiry, None
    atm = min(strikes, key=lambda x: (abs(x - underlying), x))
    allowed = set(strikes[max(0, strikes.index(atm)-near):strikes.index(atm)+near+1])
    return [r for r in current if r.get("strike") in allowed], expiry, atm


def read_episode_anchors(path: Path):
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["confirmation"] = parse_ts(r["confirmation_timestamp"])
        r["end"] = parse_ts(r.get("lifecycle_end") or r["confirmation_timestamp"])
    return rows


class RawStore:
    def __init__(self):
        self.market: dict[str, list[dict]] = {}
        self.oi: dict[str, list[dict]] = {}
        self.opened: list[dict] = []

    def _record_open(self, path: Path, phase: str):
        self.opened.append({"phase": phase, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    def ingest_market_file(self, path: Path, phase="A_B_RAW"):
        self._record_open(path, phase)
        with path.open(errors="replace") as fh:
            for offset, line in enumerate(fh, 1):
                try:
                    raw = json.loads(line); msg = raw.get("message", {}); symbol = msg.get("symbol", "")
                    receipt = parse_ts(raw["received_at"])
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                if "BANKNIFTY" not in symbol and "NIFTYBANK-INDEX" not in symbol:
                    continue
                price = canonical_float(msg.get("ltp")); volume = canonical_float(msg.get("vol_traded_today"))
                if price is None and volume is None:
                    continue
                self.market.setdefault(symbol, []).append({"receipt": receipt, "price": price, "volume": volume, "source_file": str(path), "source_row": offset})

    def ingest_oi_file(self, path: Path, phase="A_B_RAW"):
        self._record_open(path, phase)
        with path.open(errors="replace") as fh:
            for offset, line in enumerate(fh, 1):
                try:
                    raw = json.loads(line); receipt = parse_ts(raw["received_at"]); source = raw.get("source"); data = raw.get("response", {}).get("data", {})
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                if source == "option_chain":
                    expiry_data = data.get("expiryData", []); expiry = expiry_data[0].get("date") if expiry_data else None
                    items = data.get("optionsChain", [])
                elif source == "future_depth":
                    expiry = None; items = [dict(v, symbol=k) for k, v in raw.get("response", {}).get("d", {}).items()]
                else:
                    continue
                for item in items:
                    symbol = item.get("symbol", "")
                    if "BANKNIFTY" not in symbol or symbol.endswith("-INDEX"):
                        continue
                    option_type = "CE" if symbol.endswith("CE") else "PE" if symbol.endswith("PE") else "FUT"
                    row = {"receipt": receipt, "price": canonical_float(item.get("ltp")), "oi": canonical_float(item.get("oi")), "volume": canonical_float(item.get("volume", item.get("v"))), "strike": canonical_float(item.get("strike_price")), "option_type": option_type, "expiry": str(item.get("expiry") or expiry or ""), "source_file": str(path), "source_row": offset}
                    self.oi.setdefault(symbol, []).append(row)

    def finalize(self):
        for collection in (self.market, self.oi):
            for symbol, rows in collection.items():
                rows.sort(key=lambda r: (r["receipt"], r["source_file"], r["source_row"]))
                # Cache causal five-minute positive counter increments once. This
                # changes only computational complexity, not the open-left/closed-right rule.
                queue=deque();total=0.0;resets=0;duplicates=0
                for i, row in enumerate(rows):
                    delta=None;reset=False;duplicate=False
                    if i and rows[i-1].get("volume") is not None and row.get("volume") is not None:
                        if row["receipt"] == rows[i-1]["receipt"] and row["volume"] == rows[i-1]["volume"]: duplicate=True
                        elif row["volume"] < rows[i-1]["volume"]: reset=True
                        else: delta=row["volume"]-rows[i-1]["volume"]
                    queue.append((row["receipt"],delta,reset,duplicate))
                    if delta is not None:total+=delta
                    resets+=int(reset);duplicates+=int(duplicate)
                    start=row["receipt"]-timedelta(minutes=5)
                    while queue and queue[0][0]<=start:
                        _,old,old_reset,old_duplicate=queue.popleft()
                        if old is not None:total-=old
                        resets-=int(old_reset);duplicates-=int(old_duplicate)
                    row["cached_volume_5m"] = total if i > 0 and row.get("volume") is not None else None
                    row["cached_volume_status"] = ";".join(x for x, yes in (("RESET",resets>0),("DUPLICATE",duplicates>0)) if yes) or "VALID"
                for row in rows:
                    row["cached_delta_oi_5m"]=elapsed_change(rows,row["receipt"],"oi",5) if "oi" in row else None


def load_raw(date: str, market_root: Path, oi_root: Path, mode: str):
    store = RawStore()
    market_files = sorted((market_root/date).glob("events_*.jsonl"))
    oi_files = sorted((oi_root/date).glob("oi_*.jsonl"))
    if mode == "stream":
        # Incremental file/line receipt processing.
        for path in market_files: store.ingest_market_file(path)
        for path in oi_files: store.ingest_oi_file(path)
    elif mode == "batch":
        # Clean batch load, followed by one global chronological normalization.
        for path in reversed(market_files): store.ingest_market_file(path)
        for path in reversed(oi_files): store.ingest_oi_file(path)
    else:
        raise ValueError(mode)
    store.finalize()
    return store


def index_series(store: RawStore):
    candidates = [(s, r) for s, r in store.market.items() if s.endswith("-INDEX") and ("BANK" in s or "NIFTYBANK" in s)]
    return max(candidates, key=lambda x: len(x[1]))[1] if candidates else []


def futures_symbol(store: RawStore):
    candidates = [(s, r) for s, r in store.oi.items() if s.endswith("FUT")]
    return max(candidates, key=lambda x: len(x[1]))[0] if candidates else None


def participation_at(store: RawStore, episode: dict, at: datetime, cfg: dict):
    idx = index_series(store); idx_now = asof(idx, at); fut_symbol = futures_symbol(store); fut_rows = store.oi.get(fut_symbol, []) if fut_symbol else []
    fut_now = asof(fut_rows, at)
    futures = {"record_id": deterministic_id(episode["episode_id"], at.isoformat(), "FUT"), "episode_id": episode["episode_id"], "evaluation_date": at.date().isoformat(), "colour": episode["colour"], "observation_timestamp": at.isoformat(), "symbol": fut_symbol}
    if fut_now:
        futures.update({"receipt_timestamp": fut_now["receipt"].isoformat(), "price": fut_now["price"], "oi": fut_now["oi"], "receipt_age_seconds": (at-fut_now["receipt"]).total_seconds(), "source_file": fut_now["source_file"], "source_row": fut_now["source_row"]})
        for w in cfg["windows_minutes"]:
            futures[f"price_change_{w}m"] = elapsed_change(fut_rows, at, "price", w)
            futures[f"delta_oi_{w}m"] = elapsed_change(fut_rows, at, "oi", w)
        market_fut = store.market.get(fut_symbol, [])
        market_now=asof(market_fut,at);volume=market_now.get("cached_volume_5m") if market_now else None;flags=market_now.get("cached_volume_status","MISSING_BOUNDARY") if market_now else "MISSING_BOUNDARY"
        prior_volumes=[r["cached_volume_5m"] for r in market_fut if r["receipt"]<=at and r.get("cached_volume_5m") is not None]
        futures.update({"incremental_volume_5m": volume, "volume_status": flags, "volume_percentile": percentile_rank(prior_volumes, volume), "volume_robust_z": robust_z(prior_volumes, volume)})
        futures["volume_spike"] = futures["volume_percentile"] is not None and futures["volume_percentile"] >= cfg["volume_spike_percentile"]
        futures["stale"] = futures["receipt_age_seconds"] > cfg["freshness_seconds"]
    else:
        futures.update({"receipt_timestamp": None, "stale": True, "status": "MISSING"})
    underlying = idx_now["price"] if idx_now else None
    chain=[]
    for symbol, rows in store.oi.items():
        if not (symbol.endswith("CE") or symbol.endswith("PE")): continue
        row=asof(rows,at)
        if row: chain.append(dict(row,symbol=symbol))
    selected, expiry, atm = select_strikes(chain, underlying, cfg["strike_step"], cfg["near_strikes_each_side"]) if underlying is not None else ([],None,None)
    options=[];underlying_one=elapsed_change(idx,at,"price",1)
    for row in sorted(selected,key=lambda r:(r["option_type"],r["strike"],r["symbol"])):
        rows=store.oi[row["symbol"]]
        out={"record_id":deterministic_id(episode["episode_id"],at.isoformat(),row["symbol"]),"episode_id":episode["episode_id"],"evaluation_date":at.date().isoformat(),"colour":episode["colour"],"observation_timestamp":at.isoformat(),"confirmation_timestamp":episode["confirmation"].isoformat(),"timing_cohort":timing_cohort(episode["confirmation"],row["receipt"]),"symbol":row["symbol"],"option_type":row["option_type"],"strike":row["strike"],"expiry":expiry,"atm_reference":atm,"moneyness":"ATM" if row["strike"]==atm else ("OTM" if (row["option_type"]=="CE" and row["strike"]>atm) or (row["option_type"]=="PE" and row["strike"]<atm) else "ITM"),"selection_reason":"CAUSAL_ATM_PLUS_THREE_EACH_SIDE","selection_changed":None,"receipt_timestamp":row["receipt"].isoformat(),"receipt_age_seconds":(at-row["receipt"]).total_seconds(),"premium":row["price"],"oi":row["oi"],"cumulative_volume":row["volume"],"source_file":row["source_file"],"source_row":row["source_row"]}
        for w in cfg["windows_minutes"]:
            out[f"premium_change_{w}m"]=elapsed_change(rows,at,"price",w);out[f"delta_oi_{w}m"]=elapsed_change(rows,at,"oi",w)
        volume=row.get("cached_volume_5m");flags=row.get("cached_volume_status","MISSING_BOUNDARY");out["incremental_volume_5m"]=volume;out["volume_status"]=flags
        histories=[r["cached_volume_5m"] for r in rows if r["receipt"]<=at and r.get("cached_volume_5m") is not None]
        out["volume_percentile"]=percentile_rank(histories,volume);out["volume_robust_z"]=robust_z(histories,volume);out["volume_spike"]=out["volume_percentile"] is not None and out["volume_percentile"]>=cfg["volume_spike_percentile"]
        oi_hist=[abs(r.get("cached_delta_oi_5m") or 0) for r in rows if r["receipt"]<=at];out["oi_percentile"]=percentile_rank(oi_hist,abs(out.get("delta_oi_5m") or 0));out["oi_spike"]=out["oi_percentile"] is not None and out["oi_percentile"]>=cfg["oi_spike_percentile"]
        out["inventory_state"]=option_inventory_state(out.get("delta_oi_5m"),out.get("premium_change_5m"));out["semantic_classification"]=conservative_semantic(episode["colour"],row["option_type"],out.get("delta_oi_5m"),out.get("premium_change_5m"),underlying_one);out["stale"]=out["receipt_age_seconds"]>cfg["freshness_seconds"]
        options.append(out)
    return futures,options


def canonical_json_bytes(rows: list[dict]):
    return (json.dumps(rows,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str)+"\n").encode()
