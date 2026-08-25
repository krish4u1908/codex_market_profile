#!/usr/bin/env python3
import argparse,csv,hashlib,json
from pathlib import Path
from banknifty_profiler.participation.raw_engine import load_raw,read_episode_anchors,participation_at,canonical_json_bytes

def write_csv(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 fields=sorted({k for r in rows for k in r})
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['stream','batch'],required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--anchors',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 cfg=json.loads(a.config.read_text());anchors=read_episode_anchors(a.anchors);futures=[];options=[];opened=[]
 bydate={}
 for e in anchors:bydate.setdefault(e['confirmation'].date().isoformat(),[]).append(e)
 for date,episodes in sorted(bydate.items()):
  store=load_raw(date,Path(cfg['raw_market_root']),Path(cfg['raw_oi_root']),a.mode);opened.extend(store.opened)
  for e in episodes:
   times=[e['confirmation']]
   # Every causal option receipt through the frozen lifecycle end.
   times+=sorted({r['receipt'] for rows in store.oi.values() for r in rows if e['confirmation']<r['receipt']<=e['end']})
   for at in times:
    f,o=participation_at(store,e,at,cfg);futures.append(f);options.extend(o)
 a.output.mkdir(parents=True,exist_ok=True)
 (a.output/'futures.json').write_bytes(canonical_json_bytes(futures));(a.output/'options.json').write_bytes(canonical_json_bytes(options))
 write_csv(a.output/'futures_participation.csv',futures);write_csv(a.output/'option_participation.csv',options);write_csv(a.output/'file_open_audit.csv',opened)
 seal={'mode':a.mode,'futures_rows':len(futures),'option_rows':len(options),'futures_sha256':hashlib.sha256((a.output/'futures.json').read_bytes()).hexdigest(),'options_sha256':hashlib.sha256((a.output/'options.json').read_bytes()).hexdigest(),'prohibited_reference_opens':sum('/clean_combined_profiler_r4/' in r['path'] or '/clean_combined_profiler_r5_rc1/' in r['path'] for r in opened)}
 (a.output/'seal.json').write_text(json.dumps(seal,indent=2,sort_keys=True)+'\n')
 print(json.dumps(seal,sort_keys=True))
if __name__=='__main__':main()
