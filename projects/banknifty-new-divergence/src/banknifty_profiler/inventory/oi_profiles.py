from __future__ import annotations
import numpy as np
import pandas as pd

def _empty(reason,source_dates=()):
    return {"control_value":np.nan,"vpoc":np.nan,"total_weight":0.0,"weight_at_vpoc":0.0,"concentration_ratio":np.nan,"observation_count":0,"first_evidence_timestamp":"","latest_evidence_timestamp":"","profile_width":np.nan,"secondary_node":np.nan,"secondary_nodes":"","tie_status":"NO_TIE","staleness":True,"validity_reason":reason,"source_dates":"|".join(source_dates),"source_contracts":"","source_expiries":""}

def weighted_profile(frame,price_col,weight_col,bin_points=25,previous_vpoc=np.nan,source_dates=(),minimum_observations=2,stale_limit=5,evidence_time=None):
    needed=[price_col,weight_col,"symbol","expiry_date","availability_timestamp"]
    z=frame[[c for c in needed if c in frame]].copy()
    if price_col not in z or weight_col not in z:return _empty("MISSING_REQUIRED_COLUMN",source_dates)
    z=z.dropna(subset=[price_col,weight_col]);z=z[z[weight_col]>0]
    expiries=sorted(map(str,z.expiry_date.dropna().unique())) if "expiry_date" in z else []
    if len(expiries)>1:return _empty("MIXED_EXPIRY",source_dates)
    if len(z)<minimum_observations:return _empty("INSUFFICIENT_OBSERVATIONS",source_dates)
    z["bin"]=(z[price_col]/bin_points).round()*bin_points;q=z.groupby("bin")[weight_col].sum().sort_values(ascending=False,kind="stable");total=float(q.sum())
    if total<=0:return _empty("ZERO_WEIGHT",source_dates)
    tied=q[q==q.max()].index.astype(float).tolist();mean=float(np.average(z[price_col],weights=z[weight_col]));nearest=min(abs(x-mean) for x in tied);candidates=[x for x in tied if abs(x-mean)==nearest];rule="NO_TIE"
    if len(tied)>1:
        rule="TIE_WEIGHTED_MEAN"
        if len(candidates)>1 and np.isfinite(previous_vpoc):
            near=min(abs(x-previous_vpoc) for x in candidates);candidates=[x for x in candidates if abs(x-previous_vpoc)==near];rule="TIE_PREVIOUS_VPOC"
        if len(candidates)>1:rule="TIE_LOWER_BIN"
    vp=float(min(candidates));latest=pd.to_datetime(z.availability_timestamp).max();first=pd.to_datetime(z.availability_timestamp).min();age=(pd.Timestamp(evidence_time)-latest).total_seconds()/60 if evidence_time is not None else 0;stale=age>stale_limit;secondary=float(q.index[1]) if len(q)>1 else np.nan
    return {"control_value":vp,"vpoc":vp,"total_weight":total,"weight_at_vpoc":float(q.loc[vp]),"concentration_ratio":float(q.loc[vp]/total),"observation_count":len(z),"first_evidence_timestamp":first.isoformat(),"latest_evidence_timestamp":latest.isoformat(),"profile_width":float(q.index.max()-q.index.min()),"secondary_node":secondary,"secondary_nodes":"|".join(map(str,map(float,q.index[1:4]))),"tie_status":rule,"staleness":bool(stale),"validity_reason":"STALE" if stale else "OK","source_dates":"|".join(source_dates),"source_contracts":"|".join(sorted(z.symbol.unique())),"source_expiries":"|".join(expiries)}

def price_vpoc(futures,bin_points=25,previous_vpoc=np.nan,evidence_time=None,source_dates=()):
    z=futures.sort_values(["symbol","minute"]).copy();g=z.groupby("symbol",observed=True);prev=g.volume_total.shift();z["incremental_volume"]=z.volume_total-prev
    first=g.cumcount().eq(0);z.loc[first|z.volume_total.isna()|prev.isna()|z.incremental_volume.le(0),"incremental_volume"]=np.nan
    return weighted_profile(z,"ltp_close","incremental_volume",bin_points,previous_vpoc,source_dates,evidence_time=evidence_time)

def delta_profile(events,price_col="underlying_price",sign="positive",bin_points=25,previous_vpoc=np.nan,source_dates=(),evidence_time=None):
    z=events.copy()
    if "delta_oi" not in z:return _empty("NO_EVENTS",source_dates)
    z["profile_weight"]=z.delta_oi.clip(lower=0) if sign=="positive" else -z.delta_oi.clip(upper=0)
    return weighted_profile(z,price_col,"profile_weight",bin_points,previous_vpoc,source_dates,evidence_time=evidence_time)

def all_profiles(futures,options,source_dates=(),evidence_time=None,previous=None):
    previous=previous or {};q=options[options.moneyness.isin(["ATM","NEAR_OTM"])]
    out={"futures_positive":delta_profile(futures,sign="positive",source_dates=source_dates,evidence_time=evidence_time,previous_vpoc=previous.get("futures_positive",{}).get("vpoc",np.nan)),"futures_negative":delta_profile(futures,sign="negative",source_dates=source_dates,evidence_time=evidence_time,previous_vpoc=previous.get("futures_negative",{}).get("vpoc",np.nan))}
    for typ,code in [("call","ce"),("put","pe")]:
        z=q[q.instrument_class==typ]
        for sign in ["positive","negative"]:
            out[f"{code}_{sign}_underlying"]=delta_profile(z,"underlying_price",sign,source_dates=source_dates,evidence_time=evidence_time,previous_vpoc=previous.get(f"{code}_{sign}_underlying",{}).get("vpoc",np.nan))
            out[f"{code}_{sign}_strike"]=delta_profile(z,"strike",sign,100,source_dates=source_dates,evidence_time=evidence_time,previous_vpoc=previous.get(f"{code}_{sign}_strike",{}).get("vpoc",np.nan))
    return out

def migration(current,previous):
    a=current.get("vpoc",np.nan);b=previous.get("vpoc",np.nan);return a-b if np.isfinite(a) and np.isfinite(b) else np.nan

def node_change(current,previous):
    if current["validity_reason"]!="OK":return "NO_VALID_NODE"
    if previous.get("validity_reason")!="OK" or current["vpoc"]!=previous.get("vpoc"):return "NEW_NODE_CREATION"
    d=current["concentration_ratio"]-previous["concentration_ratio"]
    return "EXISTING_NODE_STRENGTHENING" if d>.05 else ("EXISTING_NODE_WEAKENING" if d<-.05 else "NODE_STABLE")
