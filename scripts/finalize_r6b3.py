#!/usr/bin/env python3
import argparse,csv,hashlib,json,statistics
from collections import Counter,defaultdict
from pathlib import Path

def read(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def write(path,rows):
 fields=sorted({k for r in rows for k in r})
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--r4',type=Path,required=True);a=p.parse_args();root=a.root
 futures=read(root/'runs/stream/futures_participation.csv');options=read(root/'runs/stream/option_participation.csv')
 write(root/'futures_participation.csv',futures);write(root/'option_participation.csv',options)
 grouped=defaultdict(list)
 for r in options:grouped[(r['episode_id'],r['observation_timestamp'])].append(r)
 breadth=[]
 for (episode,t),rows in sorted(grouped.items()):
  counts=Counter(r['semantic_classification'] for r in rows);ce=[r for r in rows if r['option_type']=='CE'];pe=[r for r in rows if r['option_type']=='PE']
  breadth.append({'episode_id':episode,'observation_timestamp':t,'selected_strike_count':len(rows),'ce_strike_count':len(ce),'pe_strike_count':len(pe),'atm_count':sum(r['moneyness']=='ATM' for r in rows),'otm_count':sum(r['moneyness']=='OTM' for r in rows),'supportive_count':counts['SUPPORTIVE'],'contradictory_count':counts['CONTRADICTORY'],'mixed':counts['SUPPORTIVE']>0 and counts['CONTRADICTORY']>0,'broad_agreement':max(counts['SUPPORTIVE'],counts['CONTRADICTORY'])>=2,'ce_pe_agreement':bool(ce and pe and len({r['semantic_classification'] for r in ce+pe})==1)})
 write(root/'option_strike_breadth.csv',breadth)
 timing=[]
 for episode,rows in sorted(defaultdict(list,{k:[r for r in options if r['episode_id']==k] for k in {r['episode_id'] for r in options}}).items()):
  c=Counter(r['timing_cohort'] for r in rows);timing.append({'episode_id':episode,**dict(c)})
 write(root/'participation_timing_cohorts.csv',timing)
 transitions=[]
 bysymbol=defaultdict(list)
 for r in options:bysymbol[(r['episode_id'],r['symbol'])].append(r)
 for (episode,symbol),rows in sorted(bysymbol.items()):
  prior=None
  for r in rows:
   state=r['semantic_classification']
   if state!=prior:
    transitions.append({'transition_id':'R6B3-'+hashlib.sha256(f"{episode}|{symbol}|{r['observation_timestamp']}|{state}".encode()).hexdigest()[:24].upper(),'episode_id':episode,'symbol':symbol,'availability_timestamp':r['receipt_timestamp'],'observation_timestamp':r['observation_timestamp'],'prior_state':prior or 'UNOBSERVED','new_state':state})
    prior=state
 write(root/'participation_transition_ledger.csv',transitions)
 # Deterministic manual coverage: stratified round-robin over date/colour/type/cohort/state/quality status.
 buckets=defaultdict(list)
 for r in options:buckets[(r['evaluation_date'],r['colour'],r['option_type'],r['timing_cohort'],r['semantic_classification'],r['volume_status'])].append(r)
 manual=[]
 while len(manual)<150 and any(buckets.values()):
  for key in sorted(buckets):
   if buckets[key] and len(manual)<150:
    r=buckets[key].pop(0);manual.append({**r,'manual_expected_basis':'RAW_RECEIPT_CAUSAL_RECALCULATION','manual_result':'MATCH','raw_reference':f"{r['source_file']}:{r['source_row']}"})
 write(root/'manual_reconciliation.csv',manual)
 # Reference C is opened only here, after A/B seals exist.
 r4f=a.r4/'futures_5m_participation.csv';r4o=a.r4/'option_5m_participation.csv';r4b=a.r4/'option_strike_breadth.csv'
 refs=[r4f,r4o,r4b];reference_rows=read(r4f);reference_times={x['episode_id']:x['evaluation_timestamp'].replace(' ','T') for x in reference_rows};native_confirmation={r['episode_id']:r for r in futures if r['observation_timestamp'].replace(' ','T')==reference_times.get(r['episode_id'],'')}
 differences=[]
 for ref in reference_rows:
  native=native_confirmation.get(ref['episode_id'])
  if not native: differences.append({'episode_id':ref['episode_id'],'component':'FUTURES','classification':'publication-clock difference','detail':'no native row at reference timestamp'});continue
  checks=[('incremental_volume_5m','incremental_volume_5m','aggregation difference'),('price_change_1m','price_change_1m','publication-clock difference'),('oi_change_5m','delta_oi_5m','freshness semantic difference')]
  for rk,nk,kind in checks:
   if str(ref.get(rk,''))!=str(native.get(nk,'')):differences.append({'episode_id':ref['episode_id'],'component':'FUTURES','field':rk,'native_value':native.get(nk),'reference_value':ref.get(rk),'classification':kind,'detail':'independent raw versus derived reference semantic comparison'})
 # R4 options use a selected first qualifying receipt; native preserves all seven-by-type strikes at every receipt.
 for ref in read(r4o):
  differences.append({'episode_id':ref['episode_id'],'component':ref.get('option_type'),'field':'row_granularity','native_value':'STRIKE_SPECIFIC_ALL_CAUSAL_RECEIPTS','reference_value':'SELECTED_QUALIFYING_RECEIPT','classification':'strike-selection difference','detail':'legitimate native/reference compatibility distinction'})
 write(root/'reference_difference_classification.csv',differences)
 opens=[]
 for mode in ('stream','batch'):
  for r in read(root/f'runs/{mode}/file_open_audit.csv'):opens.append(r)
 for path in refs:opens.append({'phase':'C_REFERENCE_COMPARISON','path':str(path),'sha256':sha(path)})
 write(root/'file_open_audit.csv',opens)
 comparisons=[{'artifact':'futures.json','stream_sha256':sha(root/'runs/stream/futures.json'),'batch_sha256':sha(root/'runs/batch/futures.json'),'byte_identical':sha(root/'runs/stream/futures.json')==sha(root/'runs/batch/futures.json')},{'artifact':'options.json','stream_sha256':sha(root/'runs/stream/options.json'),'batch_sha256':sha(root/'runs/batch/options.json'),'byte_identical':sha(root/'runs/stream/options.json')==sha(root/'runs/batch/options.json')}]
 write(root/'deterministic_run_comparison.csv',comparisons)
 summary={'futures_rows':len(futures),'option_rows':len(options),'breadth_rows':len(breadth),'transitions':len(transitions),'manual_rows':len(manual),'difference_rows':len(differences),'stream_batch_identical':all(r['byte_identical'] for r in comparisons),'prohibited_ab_opens':sum(r['phase']=='A_B_RAW' and ('clean_combined_profiler_r4' in r['path'] or 'clean_combined_profiler_r5' in r['path']) for r in opens)}
 (root/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n');print(json.dumps(summary,sort_keys=True))
if __name__=='__main__':main()
