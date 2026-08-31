#!/usr/bin/env python3
"""Portable raw full-stack participation processor."""
from __future__ import annotations

import argparse,csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
import pandas as pd

from banknifty_profiler.raw_io.reader import load_market
from banknifty_profiler.divergence.detector import causal_basis,derive,episodes
from banknifty_profiler.divergence.dependency import group_episodes
from banknifty_profiler.lifecycle.raw_engine import build_lifecycle
from banknifty_profiler.participation.raw_engine import load_raw,participation_at,canonical_json_bytes
from banknifty_profiler.participation.views import build as build_views
from banknifty_profiler.runtime.anchors import EpisodeAnchor,contract_hash,read as read_anchors,validate,write as write_anchors
from banknifty_profiler.runtime.configuration import validate_canonical_runtime_config


def write_csv(path,rows):
 rows=list(rows);fields=sorted({k for r in rows for k in r})
 temporary=path.with_suffix(path.suffix+'.tmp')
 with temporary.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 temporary.replace(path)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def external(path,label):
 result=path.resolve()
 if not result.is_dir():raise SystemExit(f'{label} missing')
 if 'research' in result.parts:raise SystemExit(f'{label} may not be a research-derived root')
 return result


def native_anchors(data_root,config,configuration_path,run_root):
 raw_root=data_root/config.get('raw_market_subdirectory','raw');all_episodes=[];series={};index_series={};opened=[]
 for date in config['sessions']:
  files=sorted((raw_root/date).glob('events_*.jsonl'))
  if not files:raise SystemExit(f'missing raw market data: {date}')
  observations=load_market(raw_root,date,{config['index_symbol'],config['futures_symbol']})
  if observations.empty or set(observations.symbol)!={config['index_symbol'],config['futures_symbol']}:raise SystemExit(f'missing required symbol: {date}')
  if any(x.tz is None for x in observations.receipt_timestamp.dropna()):raise SystemExit('invalid timezone')
  basis=causal_basis(observations,date,config['index_symbol'],config['futures_symbol'],config['synchronization_tolerance_ms'])
  frame=derive(basis);series[date]=frame
  index=observations[(observations.symbol==config['index_symbol'])&observations.receipt_timestamp.notna()&observations.last_price.notna()].sort_values(['receipt_timestamp','source_file','source_row'])
  index_series[date]=index[['receipt_timestamp','last_price']].rename(columns={'receipt_timestamp':'t','last_price':'index'})
  for row in [x for x in episodes(frame) if x['episode_type'] in ('GREEN_CONFIRMED','RED_CONFIRMED')]:
   t=pd.Timestamp(row['confirmation_timestamp']);point=frame[frame.t==t].iloc[-1]
   all_episodes.append({'evaluation_date':date,'colour':'GREEN' if row['episode_type']=='GREEN_CONFIRMED' else 'RED','candidate_start_timestamp':row['start_timestamp'],'confirmation_timestamp':row['confirmation_timestamp'],'episode_end_timestamp':row['end_timestamp'],'index_at_confirmation':point['index'],'futures_at_confirmation':point['futures'],'basis_at_confirmation':point['basis'],'index_receipt_timestamp':point['index_receipt_timestamp'],'futures_receipt_timestamp':point['futures_receipt_timestamp']})
  for path in files:opened.append({'phase':'NATIVE_RAW_GENERATION','path':str(path),'sha256':sha(path),'component':'DIVERGENCE'})
 all_episodes.sort(key=lambda r:pd.Timestamp(r['confirmation_timestamp']))
 for ordinal,row in enumerate(all_episodes,1):row['episode_id']=f"BDR1-{row['evaluation_date']}-{row['colour']}-{ordinal:03d}"
 groups=group_episodes(all_episodes,series);group={x['episode_id']:x for x in groups}
 lifecycle,dense,responses=build_lifecycle(all_episodes,groups,series,index_series)
 last={}
 for row in lifecycle:last[row['episode_id']]=max(last.get(row['episode_id'],''),row['state_entry_timestamp'])
 bydate=defaultdict(list)
 for row in all_episodes:bydate[row['evaluation_date']].append(row)
 engine_files=[Path(__file__),Path(__file__).parents[1]/'src/banknifty_profiler/divergence/detector.py',Path(__file__).parents[1]/'src/banknifty_profiler/divergence/dependency.py',Path(__file__).parents[1]/'src/banknifty_profiler/lifecycle/raw_engine.py',Path(__file__).parents[1]/'src/banknifty_profiler/participation/raw_engine.py']
 engine_hash=contract_hash(engine_files,configuration_path);input_hashes=[]
 for date in config['sessions']:
  input_hashes += [sha(x) for x in sorted((raw_root/date).glob('events_*.jsonl'))]
  input_hashes += [sha(x) for x in sorted((data_root/config.get('raw_oi_subdirectory','oi')/date).glob('oi_*.jsonl'))]
 run_id='R6C0T-'+hashlib.sha256((''.join(sorted(input_hashes))+engine_hash).encode()).hexdigest()[:24].upper()
 anchors=[]
 for row in all_episodes:
  later=[x for x in bydate[row['evaluation_date']] if pd.Timestamp(x['confirmation_timestamp'])>pd.Timestamp(row['confirmation_timestamp']) and x['colour']!=row['colour']]
  opposite=min((x['confirmation_timestamp'] for x in later),default=row['evaluation_date']+'T15:30:00+05:30')
  anchors.append(EpisodeAnchor(row['episode_id'],group[row['episode_id']]['dependency_group_id'],row['evaluation_date'],row['colour'],row['confirmation_timestamp'],last[row['episode_id']],opposite,float(row['index_at_confirmation']),float(row['futures_at_confirmation']),float(row['basis_at_confirmation']),f"{row['index_receipt_timestamp']}|{row['futures_receipt_timestamp']}",run_id,engine_hash))
 validate(anchors,run_id,engine_hash)
 write_csv(run_root/'raw_divergence_episodes.csv',all_episodes);write_csv(run_root/'raw_dependency_groups.csv',groups);write_csv(run_root/'raw_lifecycle_transitions.csv',lifecycle);write_csv(run_root/'raw_resolution_observations.csv',dense);write_csv(run_root/'raw_response_observations.csv',responses)
 return anchors,opened,run_id,engine_hash


def breadth(options):
 grouped=defaultdict(list)
 for row in options:grouped[(row['episode_id'],row['observation_timestamp'])].append(row)
 out=[]
 for (episode,t),rows in sorted(grouped.items()):
  counts=Counter(r['semantic_classification'] for r in rows);ce=[r for r in rows if r['option_type']=='CE'];pe=[r for r in rows if r['option_type']=='PE']
  out.append({'episode_id':episode,'observation_timestamp':t,'selected_strike_count':len(rows),'ce_strike_count':len(ce),'pe_strike_count':len(pe),'atm_count':sum(r['moneyness']=='ATM' for r in rows),'otm_count':sum(r['moneyness']=='OTM' for r in rows),'supportive_count':counts['SUPPORTIVE'],'contradictory_count':counts['CONTRADICTORY'],'mixed':counts['SUPPORTIVE']>0 and counts['CONTRADICTORY']>0,'broad_agreement':max(counts['SUPPORTIVE'],counts['CONTRADICTORY'])>=2,'ce_pe_agreement':bool(ce and pe and len({r['semantic_classification'] for r in ce+pe})==1)})
 return out


def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['stream','batch'],required=True);p.add_argument('--data-root',type=Path,required=True);p.add_argument('--output-root',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--anchor-source',required=True);a=p.parse_args()
 data=external(a.data_root,'data root');output=a.output_root.resolve()
 if output.exists():raise SystemExit('unsafe non-empty or existing output root')
 repository=Path(__file__).resolve().parents[1]
 if repository in output.parents:raise SystemExit('output inside repository source')
 if not a.config.is_file():raise SystemExit('configuration missing')
 try:config=validate_canonical_runtime_config(json.loads(a.config.read_text()))
 except ValueError as error:raise SystemExit(str(error)) from error
 if any(k.endswith('_root') for k in config):raise SystemExit('hidden data root in configuration')
 output.mkdir(parents=True);native=output/'native';native.mkdir();participation=output/'participation';participation.mkdir()
 anchors,opened,run_id,engine_hash=native_anchors(data,config,a.config,native)
 anchor_path=native/'episode_anchors.csv'
 if a.anchor_source=='generated':write_anchors(anchor_path,anchors)
 else:
  supplied=read_anchors(Path(a.anchor_source),data,run_id,engine_hash)
  if supplied!=anchors:raise SystemExit('serialized anchor differs from raw-generated current-run anchor')
  anchors=supplied;write_anchors(anchor_path,anchors)
 futures=[];options=[]
 rows=[x.participation_row() for x in anchors]
 for row in rows:row['confirmation']=datetime.fromisoformat(row['confirmation_timestamp']);row['end']=datetime.fromisoformat(row['lifecycle_end'])
 bydate=defaultdict(list)
 for row in rows:bydate[row['session']].append(row)
 for date,episode_rows in sorted(bydate.items()):
  store=load_raw(date,data/config.get('raw_market_subdirectory','raw'),data/config.get('raw_oi_subdirectory','oi'),a.mode);opened.extend(store.opened)
  for episode in episode_rows:
   times=[episode['confirmation']]+sorted({r['receipt'] for values in store.oi.values() for r in values if episode['confirmation']<r['receipt']<=episode['end']})
   for at in times:
    f,o=participation_at(store,episode,at,config);futures.append(f);options.extend(o)
 (participation/'futures.json').write_bytes(canonical_json_bytes(futures));(participation/'options.json').write_bytes(canonical_json_bytes(options));write_csv(participation/'futures_participation.csv',futures);write_csv(participation/'option_participation.csv',options)
 b=breadth(options);write_csv(participation/'option_strike_breadth.csv',b);write_csv(output/'file_open_audit.csv',opened)
 views=build_views(participation,anchor_path,participation/'option_strike_breadth.csv',output/'views',a.mode)
 seal={'mode':a.mode,'run_id':run_id,'engine_configuration_hash':engine_hash,'anchors':len(anchors),'futures_rows':len(futures),'option_rows':len(options),'dense_rows':views['dense_rows'],'transition_rows':views['transition_rows'],'summary_rows':views['summary_rows'],'compatibility_rows':views['compatibility_rows'],'future_joins':0,'prohibited_opens':sum('research' in Path(x['path']).parts for x in opened)}
 (output/'seal.json').write_text(json.dumps(seal,indent=2,sort_keys=True)+'\n');print(json.dumps(seal,sort_keys=True))

if __name__=='__main__':main()
