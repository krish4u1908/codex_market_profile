#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,math,sys
from bisect import bisect_right
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent;CANON=BASE/'raw_pipeline_revision_1';sys.path.insert(0,str(CANON))
from src.raw_io import load_market
CFG=json.loads((CANON/'configuration.json').read_text());COLLECTOR=Path(CFG['collector_root']);DATES=sorted(CFG['evaluation_chains']);FUT=CFG['expected_futures_symbol']
MATCH_MS=2000;INDEX_MATERIAL=10.;BASIS_MATERIAL=5.;HIGH_Q=.8;LOW_Q=.2;ROBUST_Z=1.;MERGE_GAP=15.;HORIZONS=[1,3,5,10]
PERSIST=[('P30_N3',30,3),('P60_N5',60,5),('P180',180,5)]
def sha(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def iso(x):return '' if pd.isna(x) else pd.Timestamp(x).isoformat()
def write(path,rows,fields=None):
 rows=list(rows);fields=fields or (list(rows[0]) if rows else [])
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def causal_basis(date):
 z=load_market(COLLECTOR/'raw',date,{'NSE:NIFTYBANK-INDEX',FUT});st=pd.Timestamp(date+'T09:15:00+05:30');en=pd.Timestamp(date+'T15:30:00+05:30');z=z[z.receipt_timestamp.notna()&z.last_price.notna()&(z.receipt_timestamp>=st)&(z.receipt_timestamp<=en)]
 ix=z[z.symbol=='NSE:NIFTYBANK-INDEX'].sort_values('receipt_timestamp');fu=z[z.symbol==FUT].sort_values('receipt_timestamp');it=list(ix.receipt_timestamp);ip=list(map(float,ix.last_price));rows=[]
 for _,r in fu.iterrows():
  t=r.receipt_timestamp;j=bisect_right(it,t)-1
  if j<0:rows.append({'date':date,'basis_timestamp':iso(t),'index_receipt_timestamp':'','futures_receipt_timestamp':iso(t),'index_price':'','futures_price':float(r.last_price),'basis_value':'','absolute_receipt_difference_ms':'','index_data_age_seconds':'','futures_data_age_seconds':0,'matching_tolerance_ms':MATCH_MS,'validity_status':'UNMATCHED_NO_PRIOR_INDEX'});continue
  dt=(t-it[j]).total_seconds()*1000;ok=0<=dt<=MATCH_MS
  rows.append({'date':date,'basis_timestamp':iso(t),'index_receipt_timestamp':iso(it[j]),'futures_receipt_timestamp':iso(t),'index_price':ip[j],'futures_price':float(r.last_price),'basis_value':float(r.last_price)-ip[j] if ok else '','absolute_receipt_difference_ms':abs(dt),'index_data_age_seconds':dt/1000,'futures_data_age_seconds':0,'matching_tolerance_ms':MATCH_MS,'validity_status':'VALID' if ok else 'UNMATCHED_TOLERANCE_EXCEEDED'})
 return rows
def past_row(df,i,mins):
 target=df.at[i,'t']-pd.Timedelta(minutes=mins);j=df.t.searchsorted(target,side='right')-1
 return None if j<0 else j
def derive(rows):
 df=pd.DataFrame(rows);df['t']=pd.to_datetime(df.basis_timestamp);valid=df.validity_status.eq('VALID');df['basis']=pd.to_numeric(df.basis_value,errors='coerce');df['index']=pd.to_numeric(df.index_price,errors='coerce');df['futures']=pd.to_numeric(df.futures_price,errors='coerce')
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
def context(episodes,series):
 pr=pd.read_csv(BASE/'inventory_horizon_revision_1/profile_reconciliation.csv');mh=pd.read_csv(BASE/'inventory_horizon_revision_1/event_horizon_context.csv');ev=pd.read_csv(CANON/'canonical_corrected_events.csv');out=[]
 for ep in episodes:
  t=pd.Timestamp(ep['confirmation_timestamp'] or ep['start_timestamp']);q=pr[(pr.evaluation_date==ep['date'])&(pr.validity_status=='VALID')&(pr.horizon!='ID')].copy();levels=[]
  for _,r in q.iterrows():
   if finite(r.control_value):levels.append({'horizon':r.horizon,'family':r.profile_family,'value':float(r.control_value)})
  mt=pd.to_datetime(mh.confirmation_timestamp,utc=True).dt.tz_convert('Asia/Kolkata');mrow=mh[(mh.evaluation_date==ep['date'])&(mt<=t)].tail(1)
  if len(mrow):
   for k,v in json.loads(mrow.multi_horizon_context.iloc[0]).items():
    if k.startswith('ID_') and finite(v):levels.append({'horizon':'ID','family':k[3:],'value':float(v)})
  sg=series[(series.date==ep['date'])&(pd.to_datetime(series.basis_timestamp)<=t)].tail(1);px=float(sg['index'].iloc[0]) if len(sg) else np.nan;nearest=min(levels,key=lambda r:abs(r['value']-px)) if levels and finite(px) else None;nv=nearest['value'] if nearest else np.nan;relation='NEAR' if finite(nv) and abs(px-nv)<=20 else 'ABOVE' if finite(nv) and px>nv else 'BELOW' if finite(nv) else 'UNKNOWN'
  et=pd.to_datetime(ev.confirmation_timestamp,utc=True).dt.tz_convert('Asia/Kolkata');e=ev[(ev.evaluation_date==ep['date'])&(et<=t)].tail(1)
  out.append({'date':ep['date'],'episode_type':ep['episode_type'],'confirmation_timestamp':ep['confirmation_timestamp'],'index_price_at_context':px,'nearest_control_horizon':nearest['horizon'] if nearest else '','nearest_control_family':nearest['family'] if nearest else '','nearest_control_value':nv if finite(nv) else '','distance_to_control':px-nv if finite(px) and finite(nv) else '','control_relation':relation,'frozen_control_interaction':e.control_interaction.iloc[0] if len(e) else 'NO_CAUSAL_FROZEN_EVENT','futures_state':e.futures_consensus.iloc[0] if len(e) else 'UNKNOWN','ce_state':e.ce_state.iloc[0] if len(e) else 'UNKNOWN','pe_state':e.pe_state.iloc[0] if len(e) else 'UNKNOWN','evidence_layer':'BASIS_PLUS_FULL_INVENTORY_CONTEXT' if len(e) else 'BASIS_ONLY'})
 return out
def main():
 comps=[];series=[];eps=[]
 for d in DATES:
  r=causal_basis(d);comps+=r;df=derive(r);series.append(df);eps+=episodes(df)
 write(ROOT/'basis_component_matches.csv',comps)
 allseries=pd.concat(series,ignore_index=True);allseries.drop(columns=['t']).to_csv(ROOT/'synchronized_basis_series.csv',index=False,float_format='%.10g',lineterminator='\n')
 cols=['date','basis_timestamp','basis_value','basis_expanding_median','basis_expanding_percentile','basis_robust_z','candidate_state','divergence_state','supporting_horizon_count']+sum(([f'index_change_{h}m',f'futures_change_{h}m',f'basis_change_{h}m',f'state_{h}m',f'observation_count_{h}m',f'actual_elapsed_{h}m_seconds'] for h in HORIZONS),[])+sum(([f'confirmed_{n}',f'confirmation_{n}'] for n,_,_ in PERSIST),[])
 allseries[cols].to_csv(ROOT/'divergence_state_by_timestamp.csv',index=False,float_format='%.10g',lineterminator='\n');write(ROOT/'divergence_episode_inventory.csv',eps);ctx=context([e for e in eps if e['episode_type'] in ('GREEN_CONFIRMED','RED_CONFIRMED')],allseries);write(ROOT/'divergence_oi_vpoc_context.csv',ctx)
 threshold=[]
 for d,g in allseries.groupby('date'):
  for name,secs,n in PERSIST:threshold.append({'date':d,'candidate':name,'minimum_seconds':secs,'minimum_observations':n,'green_confirmations':int((g[f'confirmed_{name}']&(g.candidate_state=='GREEN_CANDIDATE')).sum()),'red_confirmations':int((g[f'confirmed_{name}']&(g.candidate_state=='RED_CANDIDATE')).sum()),'outcomes_used':False})
 write(ROOT/'basis_threshold_diagnostics.csv',threshold);docs(allseries,eps);replays(allseries,eps);manifest()
def docs(s,e):
 (ROOT/'METHODOLOGY.md').write_text(f'''# Methodology\n\n**BN basis-divergence diagnostic revision 1** is descriptive only and has zero production weight.\n\nFrozen before data processing: backward causal as-of tolerance {MATCH_MS} ms; index materiality {INDEX_MATERIAL} points; basis-change materiality {BASIS_MATERIAL} points; expanding high/low percentiles {HIGH_Q:.0%}/{LOW_Q:.0%}; robust |z| threshold {ROBUST_Z}; episode merge gap {MERGE_GAP} seconds. Parallel persistence definitions: 30 seconds/3 observations, 60 seconds/5 observations, and 180 seconds. Default visual confirmation uses 60 seconds/5 observations and at least two of 1m/3m/5m horizons.\n\nChanges use timestamp-based backward observations, never row offsets. Expanding regimes use only data available through T. Unknown/stale observations are gaps. No outcomes, profitability, or trading labels are calculated.\n''')
 (ROOT/'BASIS_ALIGNMENT_AUDIT.md').write_text(f'''# Basis Alignment Audit\n\nBasis equals causally matched futures minus index. Matching uses raw receipt timestamps and a fixed {MATCH_MS} ms tolerance. Future joins: 0. Valid samples: {int((s.validity_status=='VALID').sum())}; unmatched samples: {int((s.validity_status!='VALID').sum())}. Both replay panels share 09:15–15:30, x=58–1150, and one timestamp mapping. Gaps are not coloured.\n''')
 q=s[(s.date=='2026-08-18')&(pd.to_datetime(s.basis_timestamp).dt.time>=pd.Timestamp('10:40').time())&(pd.to_datetime(s.basis_timestamp).dt.time<=pd.Timestamp('11:30').time())]
 q.to_csv(ROOT/'AUG18_marked_zone_observations.csv',index=False,float_format='%.10g',lineterminator='\n')
 ep=[x for x in e if x['date']=='2026-08-18' and not (pd.Timestamp(x['end_timestamp']).time()<pd.Timestamp('10:40').time() or pd.Timestamp(x['start_timestamp']).time()>pd.Timestamp('11:30').time())]
 (ROOT/'AUG18_MARKED_ZONE_AUDIT.md').write_text('# August 18 Marked-Zone Audit\n\nThe hand-marked 10:40–11:30 area was not assumed to be one episode. Raw causal observations are in `AUG18_marked_zone_observations.csv`. Intersecting mechanically derived periods:\n\n'+('\n'.join(f"- {x['episode_type']}: {x['start_timestamp']} → {x['end_timestamp']}; confirmation {x['confirmation_timestamp'] or 'none'}; observations {x['observation_count']}." for x in ep) or '- No mechanically classified period intersects the zone.')+'\n\nNo subsequent outcome was inspected.\n')
def replays(s,e):
 links=[];css='body{background:#07141e;color:#dceaf3;font:14px system-ui;margin:15px}.tools{display:flex;flex-wrap:wrap;gap:12px}.chart{width:100%;background:#091b26}label{white-space:nowrap}.note{color:#ffc857}'
 for d,g in s.groupby('date'):
  de=[x for x in e if x['date']==d];critical={x[k] for x in de for k in ('start_timestamp','confirmation_timestamp','end_timestamp') if x.get(k)};step=max(1,len(g)//5000);keep=pd.concat([g.iloc[::step],g[g.basis_timestamp.isin(critical)]]).drop_duplicates('basis_timestamp').sort_values('basis_timestamp').copy();records=keep[['basis_timestamp','index_price','futures_price','basis_value','absolute_receipt_difference_ms','index_change_1m','index_change_3m','index_change_5m','basis_change_1m','basis_change_3m','basis_change_5m','divergence_state','validity_status']].to_dict('records');records=[{k:(None if pd.isna(v) else v) for k,v in r.items()} for r in records];data={'date':d,'start':d+'T09:15:00+05:30','end':d+'T15:30:00+05:30','rows':records,'episodes':de}
  js="""const D=JSON.parse(document.querySelector('#payload').textContent),S=Date.parse(D.start),E=Date.parse(D.end),L=58,R=1150,x=t=>L+(Date.parse(t)-S)/(E-S)*(R-L);let now=S,explain=false;function draw(){let a=D.rows.filter(r=>Date.parse(r.basis_timestamp)<=now),valid=a.filter(r=>Number.isFinite(+r.index_price)&&Number.isFinite(+r.basis_value)),lo=Math.min(...valid.map(r=>+r.index_price))-20,hi=Math.max(...valid.map(r=>+r.index_price))+20,bl=Math.min(...valid.map(r=>+r.basis_value))-5,bh=Math.max(...valid.map(r=>+r.basis_value))+5,yp=v=>20+(hi-v)/(hi-lo)*300,yb=v=>10+(bh-v)/(bh-bl)*110,seg=(state,color)=>{let z=valid.filter(r=>r.divergence_state===state);return z.length>1?`<polyline fill='none' stroke='${color}' stroke-width='3' points='${z.map(r=>x(r.basis_timestamp)+','+yp(r.index_price)).join(' ')}'/>`:''},base=`<polyline fill='none' stroke='#52c8ff' points='${valid.map(r=>x(r.basis_timestamp)+','+yp(r.index_price)).join(' ')}'/>`;if(green.checked)base+=seg('GREEN_CONFIRMED','#5ee6a8');if(red.checked)base+=seg('RED_CONFIRMED','#ff718c');price.innerHTML=base+`<line x1='${x(new Date(now).toISOString())}' x2='${x(new Date(now).toISOString())}' y1='10' y2='330' stroke='#fff'/>`;basis.innerHTML=basisToggle.checked?`<polyline fill='none' stroke='#b7a4ff' points='${valid.map(r=>x(r.basis_timestamp)+','+yb(r.basis_value)).join(' ')}'/><line x1='${x(new Date(now).toISOString())}' x2='${x(new Date(now).toISOString())}' y1='5' y2='125' stroke='#fff'/>`:''}document.querySelectorAll('input').forEach(i=>i.onchange=draw);slider.oninput=e=>{now=S+(E-S)*e.target.value/1000;draw()};draw();"""
  page=f'''<!doctype html><meta charset=utf-8><title>{d} basis divergence</title><style>{css}</style><div class=note>Descriptive basis divergence — not a BUY/SELL signal.</div><h1>{d}</h1><div class=tools><label><input id=basisToggle type=checkbox checked> Basis</label><label><input id=green type=checkbox checked> Green relative strength</label><label><input id=red type=checkbox checked> Red relative weakness</label><label><input id=bands type=checkbox> Divergence background bands</label><label><input id=markers type=checkbox checked> Confirmation markers</label><label><input id=ages type=checkbox checked> Show data-age warnings</label></div><input id=slider type=range min=0 max=1000 value=0 style='width:100%'><svg id=price class=chart viewBox='0 0 1300 350'></svg><svg id=basis class=chart viewBox='0 0 1300 140'></svg><script id=payload type=application/json>{json.dumps(data,separators=(',',':'))}</script><script>{js}</script>''';(ROOT/f'replay_{d}.html').write_text(page);links.append(f'<li><a href="replay_{d}.html">{d}</a></li>')
 (ROOT/'replay_index.html').write_text('<!doctype html><meta charset=utf-8><h1>Basis divergence diagnostic</h1><p>Descriptive only; zero production weight.</p><ul>'+''.join(links)+'</ul>')
def manifest():
 entries=[]
 for p in sorted(ROOT.rglob('*')):
  if p.is_file() and p.name!='sha256_manifest.json':entries.append({'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
 frozen={str(p.relative_to(BASE)):sha(p) for p in [CANON/'sha256_manifest.json',BASE/'forward_validation_v1/sha256_manifest.json',BASE/'visual_replay_v3/sha256_manifest.json',BASE/'inventory_horizon_revision_1/sha256_manifest.json']}
 (ROOT/'sha256_manifest.json').write_text(json.dumps({'diagnostic':'basis_divergence_revision_1','production_weight':0,'outcomes_used':False,'frozen_manifest_hashes':frozen,'entries':entries},indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()
