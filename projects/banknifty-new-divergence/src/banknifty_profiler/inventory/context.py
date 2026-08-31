"""Causal inventory context adapter over caller-supplied canonical records."""
from __future__ import annotations

import math
import pandas as pd


def _finite(value):
    try:return math.isfinite(float(value))
    except (TypeError,ValueError):return False


def context_at(records, evaluation_date, timestamp, index_price):
    """Return nearest causal control; never opens or falls back to a table."""
    cutoff=pd.Timestamp(timestamp)
    eligible=[]
    for row in records:
        if row.get("evaluation_date")!=evaluation_date or not _finite(row.get("control_value")):continue
        effective=pd.Timestamp(row["control_effective_timestamp"])
        if effective<=cutoff:
            eligible.append((effective,row))
    latest={}
    for effective,row in sorted(eligible,key=lambda x:x[0]):
        latest[(row["horizon"],row["family"])]=row
    if not latest:return {"status":"NO_CAUSAL_INVENTORY","nearest_control":None}
    nearest=min(latest.values(),key=lambda r:abs(float(r["control_value"])-float(index_price)))
    value=float(nearest["control_value"]); distance=float(index_price)-value
    return {"status":"VALID","nearest_control":{"horizon":nearest["horizon"],"family":nearest["family"],"value":value,"effective_timestamp":nearest["control_effective_timestamp"]},"distance":distance,"relationship":"NEAR" if abs(distance)<=20 else "ABOVE" if distance>0 else "BELOW"}
