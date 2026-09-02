#!/usr/bin/env python3
from datetime import datetime,timedelta
import hashlib

def ts(value):return datetime.fromisoformat(value.replace(' ','T'))
def causal_window(rows,at,time_field='receipt_timestamp',minutes=5):
    end=ts(at);start=end-timedelta(minutes=minutes)
    return [r for r in rows if r.get(time_field) and start<ts(r[time_field])<=end]
def timing_bucket(confirmation,receipt):
    if not receipt:return 'NOT_OBSERVED'
    seconds=(ts(receipt)-ts(confirmation)).total_seconds()
    if seconds<=0:return 'PRE_EXISTING_AT_CONFIRMATION'
    if seconds<=60:return 'NEW_WITHIN_1_MINUTE'
    if seconds<=180:return 'NEW_WITHIN_3_MINUTES'
    if seconds<=300:return 'NEW_WITHIN_5_MINUTES'
    if seconds<=600:return 'NEW_WITHIN_10_MINUTES'
    return 'NEW_AFTER_10_MINUTES'
def context(value):
    v=(value or '').upper()
    if 'SUPPORTIVE' in v:return 'SUPPORTIVE_CONTEXT'
    if 'CONTRADICT' in v:return 'CONTRADICTORY_CONTEXT'
    if 'MIXED' in v:return 'MIXED_CONTEXT'
    if 'INSUFFICIENT' in v:return 'INSUFFICIENT_FRESH_DATA'
    return 'NEUTRAL_AMBIGUOUS'
def deterministic_id(episode,receipt,symbol='AGGREGATE'):
    return 'R4-'+hashlib.sha256(f'{episode}|{receipt}|{symbol}'.encode()).hexdigest()[:20].upper()
