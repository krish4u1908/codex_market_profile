from __future__ import annotations
import json,re
from pathlib import Path
import numpy as np,pandas as pd
from banknifty_profiler.runtime.timestamps import parse_timestamp_series

def load_market(raw_root:Path,date:str,symbols:set[str])->pd.DataFrame:
 rows=[]
 for path in sorted((raw_root/date).glob('events_*.jsonl')):
  with path.open(errors='replace') as fh:
   for offset,line in enumerate(fh,1):
    if not any(s in line for s in symbols):continue
    try:r=json.loads(line);m=r.get('message',{});sym=m.get('symbol')
    except json.JSONDecodeError:continue
    if sym not in symbols:continue
    rows.append({'session_date':date,'symbol':sym,'event_timestamp':r.get('event_time'),'receipt_timestamp':r.get('received_at'),'availability_timestamp':r.get('received_at'),'last_price':m.get('ltp'),'cumulative_volume':m.get('vol_traded_today'),'last_traded_quantity':m.get('last_traded_qty'),'source_file':str(path),'source_row':offset,'source_quality':'RAW_WEBSOCKET_EVENT'})
 z=pd.DataFrame(rows)
 if len(z):
  z['event_timestamp']=parse_timestamp_series(z.event_timestamp,field_name='market event timestamp',allow_missing=True)
  z['receipt_timestamp']=parse_timestamp_series(z.receipt_timestamp,field_name='market receipt timestamp')
  z['availability_timestamp']=z.receipt_timestamp.copy()
  z=z.sort_values(['receipt_timestamp','symbol','source_file','source_row']).reset_index(drop=True)
 return z

def load_oi(oi_root:Path,date:str)->pd.DataFrame:
 rows=[];expiry_cache={}
 for path in sorted((oi_root/date).glob('oi_*.jsonl')):
  with path.open(errors='replace') as fh:
   for offset,line in enumerate(fh,1):
    try:r=json.loads(line)
    except json.JSONDecodeError:continue
    receipt=r.get('received_at');request=r.get('request_time');source=r.get('source');response=r.get('response',{});items=[];selected=None
    if source=='option_chain':
     data=response.get('data',{});items=data.get('optionsChain',[]);eds=data.get('expiryData',[])
     if eds:selected=pd.to_datetime(eds[0].get('date'),dayfirst=True,errors='coerce').date()
    elif source=='future_depth':items=[dict(v,symbol=k) for k,v in response.get('d',{}).items()]
    for m in items:
     sym=m.get('symbol','')
     if 'BANKNIFTY' not in sym or sym.endswith('-INDEX'):continue
     typ='call' if sym.endswith('CE') else 'put' if sym.endswith('PE') else 'future';strike=m.get('strike_price') if typ!='future' else np.nan;epoch=m.get('expiry')
     if epoch not in (None,''):
      if epoch not in expiry_cache:expiry_cache[epoch]=pd.to_datetime(float(epoch),unit='s',utc=True).tz_convert('Asia/Kolkata').date()
      expiry=expiry_cache[epoch]
     else:expiry=selected
     rows.append({'session_date':date,'symbol':sym,'instrument_class':typ,'expiry_date':expiry,'strike':strike,'oi_observation_timestamp':request,'oi_receipt_timestamp':receipt,'availability_timestamp':receipt,'oi_close':m.get('oi'),'instrument_price':m.get('ltp'),'cumulative_volume':m.get('volume',m.get('v')),'source_file':str(path),'source_row':offset,'availability_quality':'EXACT_REST_RECEIPT','source_quality':'RAW_REST_OI'})
 z=pd.DataFrame(rows)
 if z.empty:return z
 z['oi_observation_timestamp']=parse_timestamp_series(z.oi_observation_timestamp,field_name='OI request timestamp',allow_missing=True)
 z['oi_receipt_timestamp']=parse_timestamp_series(z.oi_receipt_timestamp,field_name='OI receipt timestamp')
 z['availability_timestamp']=z.oi_receipt_timestamp.copy()
 z=z.sort_values(['symbol','availability_timestamp','source_file','source_row']).reset_index(drop=True);g=z.groupby('symbol',observed=True);z['previous_oi']=g.oi_close.shift();z['delta_oi_raw']=z.oi_close-z.previous_oi;z['valid_receipt']=z.oi_close.notna()&z.availability_timestamp.notna();z['oi_changed']=z.delta_oi_raw.ne(0)&z.delta_oi_raw.notna();z['duplicate_record']=z.duplicated(['symbol','availability_timestamp','oi_close','instrument_price'],keep='first');z['delta_oi']=z.delta_oi_raw.where(z.delta_oi_raw.ne(0));z.loc[g.cumcount().eq(0)|~z.valid_receipt,'delta_oi']=np.nan;z['last_valid_receipt_timestamp']=z.availability_timestamp.where(z.valid_receipt).groupby(z.symbol).ffill();z['last_change_timestamp']=z.availability_timestamp.where(z.oi_changed).groupby(z.symbol).ffill();z['freshness_age_minutes']=0.0;z['change_age_minutes']=(z.availability_timestamp-z.last_change_timestamp).dt.total_seconds()/60;return z

def select_contracts(o:pd.DataFrame,date:str):
 q=o[(o.instrument_class=='future')&(o.expiry_date.notna())&(o.expiry_date>=pd.Timestamp(date).date())]
 if q.empty:return '',None,None
 fe=min(q.expiry_date);f=q[q.expiry_date==fe].groupby('symbol').size().sort_values(ascending=False).index[0];opts=o[o.instrument_class.isin(['call','put']) & o.expiry_date.notna() & (o.expiry_date>=pd.Timestamp(date).date())];oe=min(opts.expiry_date) if len(opts) else None;return f,fe,oe

def backward_join(o:pd.DataFrame,index:pd.DataFrame,tolerance_seconds=None)->pd.DataFrame:
 z=o.sort_values('availability_timestamp').copy();p=index.dropna(subset=['receipt_timestamp','last_price']).sort_values('receipt_timestamp')[['receipt_timestamp','last_price','source_file','source_row']].rename(columns={'receipt_timestamp':'matched_price_timestamp','last_price':'matched_underlying_price','source_file':'matched_price_source_file','source_row':'matched_price_source_row'})
 if len(p):z=pd.merge_asof(z,p,left_on='availability_timestamp',right_on='matched_price_timestamp',direction='backward')
 else:z=z.assign(matched_price_timestamp=pd.Series(pd.NaT,index=z.index,dtype=z.availability_timestamp.dtype),matched_underlying_price=np.nan,matched_price_source_file='',matched_price_source_row=np.nan)
 z['join_age_seconds']=(z.availability_timestamp-z.matched_price_timestamp).dt.total_seconds();z['future_join']=z.join_age_seconds.lt(0)
 if tolerance_seconds is not None:z.loc[z.join_age_seconds.gt(tolerance_seconds)|z.join_age_seconds.isna(),'matched_underlying_price']=np.nan
 return z

def moneyness(o:pd.DataFrame,near=3)->pd.DataFrame:
 z=o.copy();z['moneyness']='FAR_DIAGNOSTIC'
 for t,g in z[z.instrument_class.isin(['call','put'])].groupby('availability_timestamp'):
  strikes=sorted(g.strike.dropna().unique());u=g.matched_underlying_price.dropna()
  if not strikes or u.empty:continue
  atm=min(strikes,key=lambda k:(abs(k-float(u.iloc[0])),k));pos={k:i for i,k in enumerate(strikes)};ai=pos[atm]
  for i,r in g.iterrows():
   d=pos.get(r.strike,999)-ai
   if d==0:v='ATM'
   elif r.instrument_class=='call' and 1<=d<=near or r.instrument_class=='put' and -near<=d<=-1:v='NEAR_OTM'
   elif r.instrument_class=='call' and -near<=d<=-1 or r.instrument_class=='put' and 1<=d<=near:v='NEAR_ITM'
   else:v='FAR_DIAGNOSTIC'
   z.at[i,'moneyness']=v
 return z
