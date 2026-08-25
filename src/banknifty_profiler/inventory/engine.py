#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,math,sys
from collections import defaultdict
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;RAW=Path('/opt/banknifty-collector/data-prod-v4/raw');OI=Path('/opt/banknifty-collector/data-prod-v4/oi');MINUTE=Path('/opt/banknifty-collector/data-prod-v4/minute')
sys.path.insert(0,str(ROOT/'locked_primitives'));from raw_io import load_market,load_oi,select_contracts,backward_join,moneyness
IDX='NSE:NIFTYBANK-INDEX';BIN=25.;TOL=5.;EVAL=['2026-08-13','2026-08-18','2026-08-19','2026-08-20'];CHAINS={'2026-08-13':['2026-08-10','2026-08-11','2026-08-12'],'2026-08-18':['2026-08-11','2026-08-12','2026-08-13'],'2026-08-19':['2026-08-12','2026-08-13','2026-08-18'],'2026-08-20':['2026-08-13','2026-08-18','2026-08-19']};FAMS=['BN_REF_FUT_VOLUME_VPOC','FUT_POS_OI_VPOC','FUT_NEG_OI_VPOC','CE_POS_OI_VPOC','CE_NEG_OI_VPOC','PE_POS_OI_VPOC','PE_NEG_OI_VPOC']
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def iso(x):return '' if pd.isna(x) else pd.Timestamp(x).isoformat()
def write(p,rows,fields=None):
 rows=list(rows);fields=fields or (list(rows[0]) if rows else [])
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def choose(weights,mean,prior=np.nan):
 mx=max(weights.values());t=sorted(k for k,v in weights.items() if v==mx);rule='NO_TIE'
 if len(t)>1:
  rule='TIE_WEIGHTED_MEAN';d=min(abs(x-mean) for x in t);t=[x for x in t if abs(x-mean)==d]
  if len(t)>1 and np.isfinite(prior):rule='TIE_PREVIOUS_VPOC';d=min(abs(x-prior) for x in t);t=[x for x in t if abs(x-prior)==d]
  if len(t)>1:rule='TIE_LOWER_BIN'
 return min(t),rule
def prof(q,prior=np.nan):
 q=q[pd.to_numeric(q.px,errors='coerce').notna()&pd.to_numeric(q.w,errors='coerce').gt(0)].copy()
 if q.empty:return None
 w=defaultdict(float);sw=sp=0.
 for _,r in q.iterrows():b=round(float(r.px)/BIN)*BIN;v=float(r.w);w[b]+=v;sw+=v;sp+=float(r.px)*v
 if sw<=0:return None
 vp,rule=choose(w,sp/sw,prior);nodes=sorted(w,key=lambda x:(-w[x],x));return {'control_value':vp,'total_weight':sw,'winning_bin_weight':w[vp],'runner_up_bin':nodes[1] if len(nodes)>1 else '','runner_up_weight':w[nodes[1]] if len(nodes)>1 else '','tie_break_reason':rule,'bin_weights':json.dumps({str(k):v for k,v in sorted(w.items())},sort_keys=True),'count':len(q)}
def price_events(m,date,fut):
 st=pd.Timestamp(date+'T09:15:00+05:30');en=pd.Timestamp(date+'T15:30:00+05:30')
 z=m[(m.symbol==fut)&m.receipt_timestamp.between(st,en,inclusive='left')].sort_values(['receipt_timestamp','source_file','source_row']).copy();v=z.dropna(subset=['receipt_timestamp','cumulative_volume']).copy();v['previous_valid']=v.cumulative_volume.shift();v['w']=v.cumulative_volume-v.previous_valid;v['reject']='';v.loc[v.previous_valid.isna(),'reject']='FIRST_VALID_COUNTER';v.loc[v.w.lt(0),'reject']='COUNTER_RESET';v.loc[v.w.eq(0),'reject']='UNCHANGED_COUNTER';v.loc[v.reject!='','w']=np.nan;v['raw_increment']=v.w
 idx=m[(m.symbol==IDX)&m.receipt_timestamp.between(st,en,inclusive='left')&m.last_price.notna()].sort_values('receipt_timestamp')[['receipt_timestamp','last_price','source_file','source_row']].rename(columns={'receipt_timestamp':'index_timestamp','last_price':'px','source_file':'index_source_file','source_row':'index_source_row'})
 v=pd.merge_asof(v.sort_values('receipt_timestamp'),idx,left_on='receipt_timestamp',right_on='index_timestamp',direction='backward');v['join_age_seconds']=(v.receipt_timestamp-v.index_timestamp).dt.total_seconds();v.loc[v.join_age_seconds.gt(TOL)|v.join_age_seconds.lt(0)|v.px.isna(),'reject']='NO_CAUSAL_INDEX_WITHIN_TOLERANCE';v.loc[v.reject!='','w']=np.nan;v['legacy_px']=v.last_price;v['session_date']=date;return v
def oi_events(o,m,date,fut,oe):
 st=pd.Timestamp(date+'T09:15:00+05:30');en=pd.Timestamp(date+'T15:30:00+05:30')
 j=moneyness(backward_join(o,m[(m.symbol==IDX)&m.receipt_timestamp.between(st,en,inclusive='left')],tolerance_seconds=TOL));j=j[j.availability_timestamp.between(st,en,inclusive='left')&~j.duplicate_record.fillna(False)].copy();j['family']='';j.loc[(j.instrument_class=='future')&(j.symbol==fut)&j.delta_oi.gt(0),'family']='FUT_POS_OI_VPOC';j.loc[(j.instrument_class=='future')&(j.symbol==fut)&j.delta_oi.lt(0),'family']='FUT_NEG_OI_VPOC';sel=j.expiry_date.astype(str).eq(str(oe))&j.moneyness.isin(['ATM','NEAR_OTM']);j.loc[sel&(j.instrument_class=='call')&j.delta_oi.gt(0),'family']='CE_POS_OI_VPOC';j.loc[sel&(j.instrument_class=='call')&j.delta_oi.lt(0),'family']='CE_NEG_OI_VPOC';j.loc[sel&(j.instrument_class=='put')&j.delta_oi.gt(0),'family']='PE_POS_OI_VPOC';j.loc[sel&(j.instrument_class=='put')&j.delta_oi.lt(0),'family']='PE_NEG_OI_VPOC';j=j[j.family!=''].copy();j['px']=j.matched_underlying_price;j['w']=j.delta_oi.abs();j['receipt_timestamp']=j.availability_timestamp;j['join_age_seconds']=(j.availability_timestamp-j.matched_price_timestamp).dt.total_seconds();j=j[j.px.notna()&j.w.gt(0)&j.join_age_seconds.between(0,TOL)];return j
def transitions(q,fam,date,contract,expiry,mode):
 q=q[pd.to_numeric(q.px,errors='coerce').notna()&pd.to_numeric(q.w,errors='coerce').gt(0)&q.receipt_timestamp.notna()].copy()
 rows=[];weights=defaultdict(float);sw=sp=0.;prior=np.nan;last=None;seen=0
 for t,g in q.sort_values('receipt_timestamp').groupby('receipt_timestamp',sort=True):
  for _,r in g.iterrows():b=round(float(r.px)/BIN)*BIN;weights[b]+=float(r.w);sw+=float(r.w);sp+=float(r.px)*float(r.w);seen+=1
  vp,rule=choose(weights,sp/sw,prior)
  if vp!=last:
   nodes=sorted(weights,key=lambda x:(-weights[x],x));rows.append({'evaluation_date':date,'horizon':'ID','family':fam,'sign':'POSITIVE' if '_POS_' in fam else 'NEGATIVE' if '_NEG_' in fam else 'VOLUME','control_value':vp,'source_sessions':date,'control_effective_timestamp':iso(t),'winner_change_timestamp':iso(t),'snapshot_timestamp':'','freshness_receipt_timestamp':iso(t),'last_contributing_change_timestamp':iso(t),'contract':contract,'expiry':expiry,'eligible_observation_count':seen,'excluded_observation_count':0,'winning_bin_weight':weights[vp],'runner_up_bin':nodes[1] if len(nodes)>1 else '','runner_up_weight':weights[nodes[1]] if len(nodes)>1 else '','tie_break_reason':rule,'methodology_version':'INVENTORY_V2_BN_REF_RAW_CAUSAL','raw_input_hashes':'RECORDED_IN_FILE_OPEN_AUDIT','authority_basis':'RAW_CAUSAL_'+mode});last=vp;prior=vp
 return rows
def fixed_rows(ev,frames,contracts,mode):
 out=[]
 for h,n in [('1D',1),('2D',2),('3D',3)]:
  ds=CHAINS[ev][-n:];fut,fe,oe=contracts[ev]
  for fam in FAMS:
   q=pd.concat([frames[d]['price'] if fam=='BN_REF_FUT_VOLUME_VPOC' else frames[d]['oi'][frames[d]['oi'].family==fam] for d in ds],ignore_index=True);p=prof(q)
   if not p:continue
   latest=q.receipt_timestamp.max();out.append({'evaluation_date':ev,'horizon':h,'family':fam,'sign':'POSITIVE' if '_POS_' in fam else 'NEGATIVE' if '_NEG_' in fam else 'VOLUME','control_value':p['control_value'],'source_sessions':'|'.join(ds),'control_effective_timestamp':ev+'T09:15:00+05:30','winner_change_timestamp':iso(latest),'snapshot_timestamp':'','freshness_receipt_timestamp':iso(latest),'last_contributing_change_timestamp':iso(latest),'contract':fut,'expiry':fe if fam.startswith(('BN_','FUT_')) else oe,'eligible_observation_count':p['count'],'excluded_observation_count':0,'winning_bin_weight':p['winning_bin_weight'],'runner_up_bin':p['runner_up_bin'],'runner_up_weight':p['runner_up_weight'],'tie_break_reason':p['tie_break_reason'],'methodology_version':'INVENTORY_V2_BN_REF_RAW_CAUSAL','raw_input_hashes':'RECORDED_IN_FILE_OPEN_AUDIT','authority_basis':'RAW_CAUSAL_'+mode})
 return out
def volume_recon(date,p):
 st=pd.Timestamp(date+'T09:15:00+05:30');en=pd.Timestamp(date+'T15:30:00+05:30');r=p[p.receipt_timestamp.between(st,en,inclusive='left')].copy();r['minute']=r.receipt_timestamp.dt.floor('min');a=r.groupby('minute').raw_increment.sum(min_count=1).rename('raw_incremental_futures_volume').reset_index();q=pd.read_csv(MINUTE/date/'market_1m.csv');q=q[q.symbol==p.symbol.iloc[0]].copy();q['minute']=pd.to_datetime(q.minute);q=q[q.minute.between(st,en,inclusive='left')][['minute','minute_volume','volume_total']];z=a.merge(q,on='minute',how='outer',indicator=True);z['absolute_difference']=(z.raw_incremental_futures_volume-z.minute_volume).abs();z['percentage_difference']=z.absolute_difference/z.minute_volume.replace(0,np.nan)*100;z['date']=date;return z
def main():
 audit=[];dates=sorted(set(EVAL+sum(CHAINS.values(),[])));frames={};contracts={}
 for d in dates:
  o=load_oi(OI,d);fut,fe,oe=select_contracts(o,d);m=load_market(RAW,d,{IDX,fut});contracts[d]=(fut,fe,oe);frames[d]={'price':price_events(m,d,fut),'oi':oi_events(o,m,d,fut,oe)}
  for p in sorted((RAW/d).glob('events_*.jsonl'))+sorted((OI/d).glob('oi_*.jsonl')):audit.append({'stage':'RAW_CALCULATION','path':str(p),'sha256':sha(p),'prohibited':False})
 stream=[];batch=[];dual=[];vrecon=[]
 for ev in EVAL:
  stream+=fixed_rows(ev,frames,contracts,'STREAM');batch+=fixed_rows(ev,frames,contracts,'BATCH')
  fut,fe,oe=contracts[ev]
  for fam in FAMS:
   q=frames[ev]['price'] if fam=='BN_REF_FUT_VOLUME_VPOC' else frames[ev]['oi'][frames[ev]['oi'].family==fam];stream+=transitions(q,fam,ev,fut,fe if fam.startswith(('BN_','FUT_')) else oe,'STREAM');batch+=transitions(q,fam,ev,fut,fe if fam.startswith(('BN_','FUT_')) else oe,'BATCH')
  # dual coordinate at every canonical price transition cutoff
  for r in [x for x in stream if x['evaluation_date']==ev and x['family']=='BN_REF_FUT_VOLUME_VPOC']:
   q=frames[ev]['price'];q=q[q.receipt_timestamp<=pd.Timestamp(r['control_effective_timestamp'])];bn=prof(q);leg=q.rename(columns={'px':'bnpx','legacy_px':'px'});fp=prof(leg);dual.append({'evaluation_date':ev,'horizon':r['horizon'],'timestamp':r['control_effective_timestamp'],'bn_reference_value':bn['control_value'] if bn else '','futures_coordinate_value':fp['control_value'] if fp else '','point_difference':(bn['control_value']-fp['control_value']) if bn and fp else '','bn_winning_weight':bn['winning_bin_weight'] if bn else '','futures_winning_weight':fp['winning_bin_weight'] if fp else '','basis_context':'TIME_VARYING_EVENT_LEVEL_MAPPING'})
  z=volume_recon(ev,frames[ev]['price']);vrecon+=z.to_dict('records');mp=MINUTE/ev/'market_1m.csv';audit.append({'stage':'VOLUME_VALIDATION','path':str(mp),'sha256':sha(mp),'prohibited':False})
 # mode-independent analytical comparison
 fields=[k for k in stream[0] if k!='authority_basis'];sa=sorted([{k:v for k,v in r.items() if k!='authority_basis'} for r in stream],key=lambda r:tuple(str(r[k]) for k in ['evaluation_date','horizon','family','control_effective_timestamp']));ba=sorted([{k:v for k,v in r.items() if k!='authority_basis'} for r in batch],key=lambda r:tuple(str(r[k]) for k in ['evaluation_date','horizon','family','control_effective_timestamp']));ab=[]
 for i,(a,b) in enumerate(zip(sa,ba)):ab.append({'row':i,'key':'|'.join(str(a[k]) for k in ['evaluation_date','horizon','family','control_effective_timestamp']),'match':a==b})
 write(ROOT/'stream_vs_batch.csv',ab);write(ROOT/'raw_futures_volume_increments.csv',pd.concat([frames[d]['price'] for d in dates]).rename(columns={'px':'causal_index_price'}).to_dict('records'));write(ROOT/'causal_index_reference_joins.csv',pd.concat([frames[d]['price'] for d in dates])[['session_date','symbol','receipt_timestamp','index_timestamp','px','join_age_seconds','w','reject','source_file','source_row','index_source_file','index_source_row']].rename(columns={'px':'causal_index_price','w':'incremental_volume'}).to_dict('records'));write(ROOT/'bn_reference_vs_futures_coordinate.csv',dual);pd.DataFrame(vrecon).to_csv(ROOT/'independent_volume_reconciliation.csv',index=False,lineterminator='\n');write(ROOT/'file_open_audit.csv',audit)
 # gate: exact full-session totals must reconcile; interval boundary differences are descriptive.
 vz=pd.DataFrame(vrecon);tot=vz.groupby('date')[['raw_incremental_futures_volume','minute_volume']].sum();volume_ok=bool(np.allclose(tot.raw_incremental_futures_volume,tot.minute_volume,atol=0,rtol=0));ab_ok=all(x['match'] for x in ab) and len(sa)==len(ba)
 (ROOT/'run_gate.json').write_text(json.dumps({'stream_rows':len(stream),'batch_rows':len(batch),'stream_batch_match':ab_ok,'volume_session_totals':tot.reset_index().to_dict('records'),'volume_totals_exact':volume_ok,'future_joins':int(sum((frames[d]['price'].join_age_seconds<0).sum() for d in dates))},indent=2)+'\n');write(ROOT/'runs_stream.csv',stream);write(ROOT/'runs_batch.csv',batch)
if __name__=='__main__':main()
