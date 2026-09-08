#!/usr/bin/env python3
"""Exploratory, causal session features. Reads exports; never imports or edits the engine."""
from __future__ import annotations
import argparse, bisect, collections, csv, hashlib, json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent
IST = timezone(timedelta(hours=5, minutes=30))

def ts(s): return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
def isot(t): return datetime.fromtimestamp(t, timezone.utc).isoformat().replace('+00:00', 'Z')
def ist(t): return datetime.fromtimestamp(t, IST).isoformat()
def finite(x): return x is not None and isinstance(x, (float, int, np.number)) and math.isfinite(x)
def sgn(x, floor=0): return 1 if finite(x) and x > floor else -1 if finite(x) and x < -floor else 0
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(path, obj): Path(path).write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')
def unpack(block):
    rows = [dict(zip(block['fields'], r)) for r in block.get('rows', [])]
    for r in rows: r['_t'] = ts(r['t'])
    return sorted(rows, key=lambda r: r['_t'])

class Series:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda r: r['_t'])
        self.t = np.array([r['_t'] for r in self.rows], dtype=float)
    def before(self, end): return int(np.searchsorted(self.t, end, side='left')) - 1
    def at_or_before(self, end): return int(np.searchsorted(self.t, end, side='right')) - 1
    def window(self, end, minutes, freshness, maxgap):
        start = end - minutes * 60
        a, b = self.at_or_before(start), self.before(end)
        if a < 0 or b <= a: return None
        if start-self.t[a] > freshness or end-self.t[b] > freshness: return None
        if np.diff(self.t[a:b+1]).max(initial=0) > maxgap: return None
        return self.rows[a:b+1]

class Leg:
    """A pivot's extreme is known at confirmation, never backdated as a signal."""
    def __init__(self, threshold): self.threshold = threshold; self.reset()
    def reset(self):
        self.direction = 0; self.high = self.low = None
        self.high_t = self.low_t = self.confirmed = None
    def step(self, t, p):
        if self.high is None:
            self.high = self.low = p; self.high_t = self.low_t = t
            return None
        old = self.direction
        if old == 0:
            if p > self.high: self.high = p; self.high_t = t
            if p < self.low: self.low = p; self.low_t = t
            if p-self.low >= self.threshold:
                event = dict(old=0, new=1, extreme=self.low, extreme_t=self.low_t)
                self.direction = 1; self.high = p; self.high_t = t
            elif self.high-p >= self.threshold:
                event = dict(old=0, new=-1, extreme=self.high, extreme_t=self.high_t)
                self.direction = -1; self.low = p; self.low_t = t
            else: return None
        elif old == 1:
            if p >= self.high: self.high = p; self.high_t = t
            if self.high-p < self.threshold: return None
            event = dict(old=old, new=-1, extreme=self.high, extreme_t=self.high_t)
            self.direction = -1; self.low = p; self.low_t = t
        else:
            if p <= self.low: self.low = p; self.low_t = t
            if p-self.low < self.threshold: return None
            event = dict(old=old, new=1, extreme=self.low, extreme_t=self.low_t)
            self.direction = 1; self.high = p; self.high_t = t
        self.confirmed = t
        return dict(event, detected=t, price=p, threshold=self.threshold)

def price_states(prices, day):
    series = Series(prices); short, broad = Leg(25), Leg(75)
    start = ts(day+'T09:16:00+05:30'); stop = ts(day+'T15:30:00+05:30')
    states = {}; previous_t = None; last_boundary = None; segment = 0
    for t in np.arange(start, stop+1, 60):
        j = series.before(t)
        good = j >= 0 and t-series.t[j] <= 15
        if good and previous_t is not None:
            a = series.at_or_before(previous_t)
            good = np.diff(series.t[a:j+1]).max(initial=0) <= 60
        if not good:
            short.reset(); broad.reset(); previous_t = None; last_boundary = None
            continue
        if last_boundary is None: segment += 1
        p = series.rows[j]['i']; before = broad.direction
        be = broad.step(float(t), p); se = short.step(float(t), p)
        states[float(t)] = dict(short=short.direction, broad=broad.direction,
            broad_before=before, short_event=se, broad_event=be, segment=segment,
            broad_extreme=broad.high if broad.direction==1 else broad.low)
        previous_t = series.t[j]; last_boundary = t
    return states

def cash_features(rows, cutoff, pub):
    available = [r for r in rows if r['_t'] <= pub and r['_minute'] < cutoff]
    if not available or pub-available[-1]['_t'] > 120: return {}
    latest = available[-1]
    out = {'cash_source_minute': latest['minute_ist'], 'cash_publication': latest['t']}
    def valid(r, kind):
        if kind=='cash':
            return (finite(r.get('cash_weighted_pct')) and r.get('expected_constituent_count', 0)>0
                and r.get('cash_names')==r.get('expected_constituent_count'))
        return finite(r.get('vix_close')) and r['vix_close']>0
    def window(n, kind):
        w = available[-n-1:]
        if len(w)!=n+1 or any(not valid(r, kind) for r in w): return None
        if any(b['_minute']-a['_minute']!=60 for a,b in zip(w,w[1:])): return None
        return w
    for kind, raw, rolling in [('cash','cash_weighted_pct','cash_rolling_change'),('vix','vix_close','vix_rolling_change')]:
        if valid(latest,kind): out[kind+'_raw']=latest[raw]
        w=window(5,kind)
        if w:
            delta=w[-1][raw]-w[0][raw]
            out[kind+'_raw_change_5m']=delta
            if finite(latest.get(rolling)): out[kind+'_identity_error']=abs(latest[rolling]-delta/5)
        w=window(30,kind)
        if w:
            out[kind+'_raw_change_30m']=w[-1][raw]-w[0][raw]
            out[kind+'_from_30m_high']=w[-1][raw]-max(r[raw] for r in w)
            out[kind+'_from_30m_low']=w[-1][raw]-min(r[raw] for r in w)
    v5,v30=out.get('vix_raw_change_5m'),out.get('vix_raw_change_30m')
    if finite(v5) and finite(v30):
        s5,s30=sgn(v5,0.02-1e-9),sgn(v30,0.02-1e-9)
        out['vix_local_direction']=s5;out['vix_background_direction']=s30
        out['vix_local_background_opposed']=bool(s5*s30==-1)
    if 'cash_raw_change_5m' in out:
        out['cash_below_open_improving']=out['cash_raw'] < -0.01 and out['cash_raw_change_5m'] > 0.01
    return out

def option_features(series_by_symbol, selection, cutoff):
    if not selection.get('available') or ts(selection['selected_at']) > cutoff-300: return {}
    out={'fixed_atm': selection['atm']}
    for kind in ('CE','PE'):
        parts=[]
        for contract in selection[kind]:
            ser=series_by_symbol.get(contract['symbol']); w=ser.window(cutoff,5,90,90) if ser else None
            if not w or any(not finite(r.get('oi')) for r in w): continue
            first,last=w[0],w[-1]; delta=last['oi']-first['oi']
            d=np.diff([r['oi'] for r in w])
            premium=(last['p']/first['p']-1)*100 if finite(first.get('p')) and finite(last.get('p')) and first['p']>0 else None
            vv=[r.get('v') for r in w]
            vol=(vv[-1]-vv[0]) if all(finite(v) for v in vv) and np.diff(vv).min(initial=0)>=0 and not any(r.get('vs')=='GAP_RESET' for r in w[1:]) else None
            parts.append(dict(delta=delta,add=float(d[d>0].sum()),remove=float(-d[d<0].sum()),premium=premium,volume=vol,oi=last['oi']))
        prefix=kind.lower();out[prefix+'_coverage']=len(parts)
        if len(parts)!=len(selection[kind]) or len(parts)!=4: continue
        for key,label in [('delta','oi_delta_5m'),('add','oi_additions_5m'),('remove','oi_reductions_5m'),('oi','oi')]:
            out[prefix+'_'+label]=sum(p[key] for p in parts)
        out[prefix+'_add_premium_rise_contracts']=sum(p['delta']>0 and finite(p['premium']) and p['premium']>0 for p in parts)
        out[prefix+'_add_premium_fall_contracts']=sum(p['delta']>0 and finite(p['premium']) and p['premium']<0 for p in parts)
        if all(finite(p['premium']) for p in parts): out[prefix+'_mean_premium_change_pct_5m']=sum(p['premium'] for p in parts)/4
        if all(finite(p['volume']) for p in parts): out[prefix+'_volume_5m']=sum(p['volume'] for p in parts)
    return out

def volume_interval(series, end, minutes=5):
    w=series.window(end, minutes, 15, 60)
    if not w: return None
    if len({r.get('symbol') for r in w})!=1: return None
    vv=[r.get('v') for r in w]
    if not all(finite(v) for v in vv) or np.diff(vv).min(initial=0)<0: return None
    if any(r.get('vs') in ('GAP_RESET','BASELINE') for r in w[1:]): return None
    return sum(r['dv'] for r in w[1:] if r.get('vs')=='VALID' and finite(r.get('dv')) and r['dv']>0)

def mode(contrib):
    if not contrib: return None
    bins=collections.defaultdict(float);total=weighted=0
    for r in contrib:
        b=round(r['i']/25)*25;bins[b]+=r['dv'];total+=r['dv'];weighted+=r['i']*r['dv']
    if total<=0: return None
    high=max(bins.values()); candidates=[p for p,v in bins.items() if math.isclose(v,high,abs_tol=1e-9,rel_tol=0)]
    center=weighted/total
    return min(candidates,key=lambda p:(round(abs(p-center),9),p))

def volume_features(series, contributions, cutoff, inventory):
    out={};v=volume_interval(series,cutoff)
    if v is not None: out['futures_valid_volume_5m']=v
    prior=[volume_interval(series,cutoff-i*300) for i in range(1,5)]
    if v is not None and all(x is not None for x in prior) and np.median(prior)>0:
        out['futures_volume_ratio']=v/float(np.median(prior))
    c=contributions.rows[:contributions.before(cutoff)+1]
    cumulative=mode(c)
    if cumulative is not None: out['volume_cumulative_mode_reconstructed']=cumulative
    w=series.window(cutoff,15,15,60)
    if w and not any(r.get('vs') in ('GAP_RESET','BASELINE') for r in w[1:]):
        recent=[r for r in c if r['_t']>=cutoff-900]
        m=mode(recent)
        if m is not None: out['volume_recent_15m_mode']=m
    canonical=[r for r in inventory if r['_t']<cutoff and r['family']=='NIFTY_REF_FUT_VOLUME_VPOC']
    if canonical and finite(canonical[-1].get('control_value')):
        out['volume_cumulative_mode_canonical']=canonical[-1]['control_value']
        if cumulative is not None:
            out['volume_mode_reconstruction_matches']=canonical[-1]['control_value']==cumulative
        if 'volume_recent_15m_mode' in out:
            out['volume_recent_cumulative_distance']=out['volume_recent_15m_mode']-canonical[-1]['control_value']
    for fam in ('FUT_POS_OI_VPOC','FUT_NEG_OI_VPOC','CE_POS_OI_VPOC','CE_NEG_OI_VPOC','PE_POS_OI_VPOC','PE_NEG_OI_VPOC'):
        rr=[r for r in inventory if r['_t']<cutoff and r['family']==fam]
        if rr:
            out[fam.lower()]=rr[-1].get('control_value')
            out[fam.lower()+'_last_emitted_age_minutes']=(cutoff-rr[-1]['_t'])/60
    return out
