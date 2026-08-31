"""Frozen raw-only BankNifty basis-divergence detector.

This module is deliberately data-root and output-root agnostic.  Callers pass
raw observations to :func:`causal_basis` and own all persistence.  It contains
no research-package, replay, forward-validator, or derived-table dependency.
"""
from __future__ import annotations
import math
from bisect import bisect_right
import numpy as np,pandas as pd
from banknifty_profiler.runtime.timestamps import parse_timestamp_series
MATCH_MS=2000;INDEX_MATERIAL=10.;BASIS_MATERIAL=5.;HIGH_Q=.8;LOW_Q=.2;ROBUST_Z=1.;MERGE_GAP=15.;HORIZONS=[1,3,5,10]
PERSIST=[('P30_N3',30,3),('P60_N5',60,5),('P180',180,5)]
def iso(x):return '' if pd.isna(x) else pd.Timestamp(x).isoformat()
def causal_basis(observations, date, index_symbol, futures_symbol, match_ms=MATCH_MS):
 z=observations;st=pd.Timestamp(date+'T09:15:00+05:30');en=pd.Timestamp(date+'T15:30:00+05:30');z=z[z.receipt_timestamp.notna()&z.last_price.notna()&(z.receipt_timestamp>=st)&(z.receipt_timestamp<=en)]
 ix=z[z.symbol==index_symbol].sort_values(['receipt_timestamp','source_file','source_row']);fu=z[z.symbol==futures_symbol].sort_values(['receipt_timestamp','source_file','source_row']);it=list(ix.receipt_timestamp);ip=list(map(float,ix.last_price));rows=[]
 for _,r in fu.iterrows():
  t=r.receipt_timestamp;j=bisect_right(it,t)-1
  if j<0:rows.append({'date':date,'basis_timestamp':iso(t),'index_receipt_timestamp':'','futures_receipt_timestamp':iso(t),'index_price':'','futures_price':float(r.last_price),'basis_value':'','absolute_receipt_difference_ms':'','index_data_age_seconds':'','futures_data_age_seconds':0,'matching_tolerance_ms':match_ms,'validity_status':'UNMATCHED_NO_PRIOR_INDEX'});continue
  dt=(t-it[j]).total_seconds()*1000;ok=0<=dt<=match_ms
  rows.append({'date':date,'basis_timestamp':iso(t),'index_receipt_timestamp':iso(it[j]),'futures_receipt_timestamp':iso(t),'index_price':ip[j],'futures_price':float(r.last_price),'basis_value':float(r.last_price)-ip[j] if ok else '','absolute_receipt_difference_ms':abs(dt),'index_data_age_seconds':dt/1000,'futures_data_age_seconds':0,'matching_tolerance_ms':match_ms,'validity_status':'VALID' if ok else 'UNMATCHED_TOLERANCE_EXCEEDED'})
 return rows
def past_row(df,i,mins):
 target=df.at[i,'t']-pd.Timedelta(minutes=mins);j=df.t.searchsorted(target,side='right')-1
 return None if j<0 else j
def derive(rows):
 df=pd.DataFrame(rows);df['t']=parse_timestamp_series(df.basis_timestamp,field_name='Basis receipt timestamp');valid=df.validity_status.eq('VALID');df['basis']=pd.to_numeric(df.basis_value,errors='coerce');df['index']=pd.to_numeric(df.index_price,errors='coerce');df['futures']=pd.to_numeric(df.futures_price,errors='coerce')
 for h in HORIZONS:
  ic=[];fc=[];bc=[];elapsed=[];counts=[]
  for i in range(len(df)):
   j=past_row(df,i,h)
   if j is None or not valid.iloc[i] or not valid.iloc[j]:ic.append(np.nan);fc.append(np.nan);bc.append(np.nan);elapsed.append(np.nan);counts.append(0)
   else:ic.append(df.at[i,'index']-df.at[j,'index']);fc.append(df.at[i,'futures']-df.at[j,'futures']);bc.append(df.at[i,'basis']-df.at[j,'basis']);elapsed.append((df.at[i,'t']-df.at[j,'t']).total_seconds());counts.append(int(valid.iloc[j:i+1].sum()))
  df[f'index_change_{h}m']=ic;df[f'futures_change_{h}m']=fc;df[f'basis_change_{h}m']=bc;df[f'actual_elapsed_{h}m_seconds']=elapsed;df[f'observation_count_{h}m']=counts
 med=[];pct=[];rz=[]
 vals=[]
 for i,r in df.iterrows():
  if valid.iloc[i]:vals.append(float(r.basis));a=np.asarray(vals);m=float(np.median(a));mad=float(np.median(np.abs(a-m)));med.append(m);pct.append(float((a<=r.basis).mean()));rz.append(0 if mad==0 else .6745*(r.basis-m)/mad)
  else:med.append(np.nan);pct.append(np.nan);rz.append(np.nan)
 df['basis_expanding_median']=med;df['basis_expanding_percentile']=pct;df['basis_robust_z']=rz
 for h in HORIZONS:
  state=[]
  for _,r in df.iterrows():
   ic=r[f'index_change_{h}m'];bc=r[f'basis_change_{h}m'];high=(r.basis_expanding_percentile>=HIGH_Q or r.basis_robust_z>=ROBUST_Z);low=(r.basis_expanding_percentile<=LOW_Q or r.basis_robust_z<=-ROBUST_Z)
   if not finite(ic) or not finite(bc):s='UNKNOWN_GAP'
   elif ic<=-INDEX_MATERIAL and (bc>=BASIS_MATERIAL or high):s='GREEN_CANDIDATE'
   elif ic>=INDEX_MATERIAL and (bc<=-BASIS_MATERIAL or low):s='RED_CANDIDATE'
   else:s='NEUTRAL_BLUE'
   state.append(s)
  df[f'state_{h}m']=state
 df['supporting_horizon_count']=df[['state_1m','state_3m','state_5m']].apply(lambda r:max(sum(x=='GREEN_CANDIDATE' for x in r),sum(x=='RED_CANDIDATE' for x in r)),axis=1)
 df['candidate_state']=df.apply(lambda r:'GREEN_CANDIDATE' if sum(r[f'state_{h}m']=='GREEN_CANDIDATE' for h in [1,3,5])>=2 else 'RED_CANDIDATE' if sum(r[f'state_{h}m']=='RED_CANDIDATE' for h in [1,3,5])>=2 else 'UNKNOWN_GAP' if r.validity_status!='VALID' else 'NEUTRAL_BLUE',axis=1)
 for name,secs,nobs in PERSIST:df[f'confirmed_{name}']=False;df[f'confirmation_{name}']=''
 for name,secs,nobs in PERSIST:
  start=0
  for i in range(len(df)):
   if i==0 or df.at[i,'candidate_state']!=df.at[i-1,'candidate_state'] or (df.at[i,'t']-df.at[i-1,'t']).total_seconds()>MERGE_GAP:start=i
   state=df.at[i,'candidate_state'];duration=(df.at[i,'t']-df.at[start,'t']).total_seconds();count=i-start+1
   if state in ('GREEN_CANDIDATE','RED_CANDIDATE') and duration>=secs and count>=nobs:df.at[i,f'confirmed_{name}']=True;df.at[i,f'confirmation_{name}']=iso(df.at[i,'t'])
 # frozen default colouring candidate: P60_N5 only
 cur=None;confirmation='';final=[]
 for i,r in df.iterrows():
  if r.candidate_state not in ('GREEN_CANDIDATE','RED_CANDIDATE'):cur=None;confirmation='';final.append('UNKNOWN_GAP' if r.candidate_state=='UNKNOWN_GAP' else 'NEUTRAL_BLUE');continue
  if cur!=r.candidate_state:cur=r.candidate_state;confirmation=''
  if r.confirmed_P60_N5 and not confirmation:confirmation=iso(r.t)
  final.append(('GREEN_CONFIRMED' if cur=='GREEN_CANDIDATE' else 'RED_CONFIRMED') if confirmation else 'NEUTRAL_BLUE')
 df['divergence_state']=final;return df
def finite(x):
 try:return math.isfinite(float(x))
 except:return False
def episodes(df):
 out=[];state=None;start=0
 for i in range(len(df)+1):
  s=df.at[i,'divergence_state'] if i<len(df) else None
  if s!=state:
   if state is not None:
    q=df.iloc[start:i];conf=q[q.divergence_state.isin(['GREEN_CONFIRMED','RED_CONFIRMED'])]
    etype=state;candidate='GREEN_CANDIDATE' if state=='GREEN_CONFIRMED' else 'RED_CANDIDATE' if state=='RED_CONFIRMED' else state;candidate_start=start
    if state in ('GREEN_CONFIRMED','RED_CONFIRMED'):
     j=start-1
     while j>=0 and df.at[j,'candidate_state']==candidate and (df.at[j+1,'t']-df.at[j,'t']).total_seconds()<=MERGE_GAP:candidate_start=j;j-=1
    full=df.iloc[candidate_start:i]
    out.append({'date':df.iloc[0].date,'episode_type':etype,'candidate_state':candidate,'start_timestamp':iso(full.t.iloc[0]),'confirmation_timestamp':iso(q.t.iloc[0]) if state in ('GREEN_CONFIRMED','RED_CONFIRMED') else '','end_timestamp':iso(q.t.iloc[-1]),'duration_seconds':(q.t.iloc[-1]-full.t.iloc[0]).total_seconds(),'observation_count':len(full),'maximum_index_movement':float(full['index'].max()-full['index'].min()) if full['index'].notna().any() else '','maximum_basis_movement':float(full.basis.max()-full.basis.min()) if full.basis.notna().any() else '','data_quality':'RAW_CAUSAL_MATCHED' if state!='UNKNOWN_GAP' else 'UNMATCHED_OR_STALE','direction':'DESCRIPTIVE_ONLY'})
   state=s;start=i
 return out
