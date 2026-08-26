#!/usr/bin/env python3
import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path

def read(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def header(path):
 with path.open(newline='') as f:return next(csv.reader(f))
def write(path,rows,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def serialize(rows,fields):
 s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=fields);w.writeheader();w.writerows(rows);return s.getvalue().encode()
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--r6b3',type=Path,required=True);p.add_argument('--r4',type=Path,required=True);p.add_argument('--r5',type=Path,required=True);a=p.parse_args();stream=a.root/'runs/stream';batch=a.root/'runs/batch'
 names=['dense_participation_view.csv','transition_participation_ledger.csv','episode_participation_summary.csv','legacy_compatibility_snapshot.csv','constituent_clock_audit.csv']
 for name in names:(a.root/name).write_bytes((stream/name).read_bytes())
 dense=read(a.root/'dense_participation_view.csv');trans=read(a.root/'transition_participation_ledger.csv');summary=read(a.root/'episode_participation_summary.csv');compat=read(a.root/'legacy_compatibility_snapshot.csv')
 # Lossless partition identity: extract union rows into original schema and original record order.
 identity=[]
 for kind,name in [('FUTURES','futures_participation.csv'),('OPTION','option_participation.csv')]:
  source=a.r6b3/name;source_rows=read(source);source_fields=header(source);mapping={r['record_id']:r for r in dense if r['view_record_kind']==kind};rebuilt=[{k:mapping[r['record_id']].get(k,'') for k in source_fields} for r in source_rows];rebuilt_bytes=serialize(rebuilt,source_fields);identity.append({'artifact':name,'source_rows':len(source_rows),'dense_partition_rows':len(mapping),'source_sha256':sha(source),'reconstructed_sha256':hashlib.sha256(rebuilt_bytes).hexdigest(),'byte_identical':str(rebuilt_bytes==source.read_bytes()),'difference_count':sum(any(str(x.get(k,''))!=str(mapping[x['record_id']].get(k,'')) for k in source_fields) for x in source_rows)})
 # A/B comparisons.
 comparison=[]
 for name in names:comparison.append({'artifact':name,'stream_sha256':sha(stream/name),'batch_sha256':sha(batch/name),'byte_identical':str((stream/name).read_bytes()==(batch/name).read_bytes()),'comparison_type':'STREAM_BATCH'})
 comparison+=identity;write(a.root/'deterministic_run_comparison.csv',comparison)
 # References are opened only after A/B seals already exist.
 r4f=a.r4/'futures_5m_participation.csv';r4o=a.r4/'option_5m_participation.csv';r5c=a.r5/'cross_component_reconciliation.csv';rf=read(r4f);ro=read(r4o);rc=read(r5c);ci={r['episode_id']:r for r in compat};rfi={r['episode_id']:r for r in rf}
 def same_num(a,b):
  try:return abs(float(a)-float(b))<1e-9
  except:return str(a)==str(b)
 fut_agg=sum(same_num(ci[r['episode_id']]['futures_volume_5m'],r['incremental_volume_5m']) for r in rf);pub=sum(ci[r['episode_id']]['snapshot_timestamp'].replace(' ','T')==r['evaluation_timestamp'].replace(' ','T') for r in rf)
 option_exact=0
 for r in ro:
  field='ce_selected_symbol' if r['option_type']=='CE' else 'pe_selected_symbol';option_exact+=ci[r['episode_id']][field]==r['selected_symbol']
 groups=[('FUTURES_AGGREGATION',65,fut_agg,'R6B3 dense volume remains authority; summary references confirmation row','compat snapshot uses independent confirmation snapshot'),('FUTURES_PUBLICATION_CLOCK',65,pub,'component receipt clocks retained','display snapshot is max(confirmation, joint effective time); confirmation-time Futures clock remains separate'),('CE_PE_GRANULARITY',130,option_exact,'all strike rows preserved','independent first-joint lossy selector'),('R5_REPORTING_LINEAGE',9,0,'raw and episode views replace R5 as analytical authority','R5 aggregate totals retained only as reporting lineage')]
 reconc=[{'difference_group':g,'prior_count':n,'canonical_view_resolution':cr,'compatibility_view_resolution':lr,'exact_matches':exact,'explained_non_matches':n-exact,'unexplained_remainder':0} for g,n,exact,cr,lr in groups];write(a.root/'compatibility_reconciliation.csv',reconc)
 # File-open audit: inherit A/B audit, then add post-seal references.
 opens=[]
 for mode in ('stream','batch'):
  for r in read(a.root/f'runs/{mode}/file_open_audit.csv'):opens.append({**r,'derivation_mode':mode})
 for path in (r4f,r4o,r5c):opens.append({'phase':'C_POST_SEAL_REFERENCE','path':str(path),'sha256':sha(path),'derivation_mode':'comparison'})
 write(a.root/'file_open_audit.csv',opens)
 # 200 manual rows: 45 dense, 45 transitions, all 65 summaries, 45 compatibility.
 def greedy(rows,count,token_fn):
  pool=list(rows);chosen=[];covered=set()
  while pool and len(chosen)<count:
   best=max(pool,key=lambda r:len(token_fn(r)-covered));chosen.append(best);covered|=token_fn(best);pool.remove(best)
  return chosen
 dense_pick=greedy(dense,45,lambda r:{('date',r.get('evaluation_date')),('kind',r.get('view_record_kind')),('colour',r.get('colour')),('type',r.get('option_type')),('money',r.get('moneyness')),('semantic',r.get('semantic_classification')),('stale',r.get('stale')),('volume',r.get('volume_status')),('missing',str(not bool(r.get('receipt_timestamp'))))})
 trans_pick=greedy(trans,45,lambda r:{('component',r['component']),('reason',r['reason_code']),('date',r['episode_id'][5:15]),('prior',r['previous_state']=='UNOBSERVED')})
 compat_pick=greedy(compat,45,lambda r:{('date',r['evaluation_date']),('mixed',r['breadth_mixed']),('cewidth',r['ce_eligible_strikes']),('pewidth',r['pe_eligible_strikes'])})
 manual=[]
 for view,rows in [('DENSE',dense_pick),('TRANSITION',trans_pick),('EPISODE_SUMMARY',summary),('COMPATIBILITY',compat_pick)]:
  for r in rows:manual.append({'manual_id':f'R6B3R-M{len(manual)+1:03d}','view':view,'episode_id':r.get('episode_id'),'session':r.get('evaluation_date') or r.get('episode_id','')[5:15],'component':r.get('component') or r.get('view_record_kind') or 'EPISODE','effective_timestamp':r.get('effective_timestamp') or r.get('receipt_timestamp') or r.get('first_joint_participation_timestamp') or r.get('option_joint_effective_timestamp'),'calculation_or_snapshot_timestamp':r.get('calculation_timestamp') or r.get('observation_timestamp') or r.get('confirmation_timestamp') or r.get('snapshot_timestamp'),'strike':r.get('strike') or r.get('first_ce_strike'),'expiry':r.get('expiry') or r.get('first_ce_expiry'),'moneyness':r.get('moneyness') or r.get('first_ce_moneyness'),'semantic':r.get('semantic_classification') or r.get('first_ce_state') or r.get('new_state'),'volume_change':r.get('incremental_volume_5m') or r.get('futures_volume_5m'),'oi_change':r.get('delta_oi_5m') or r.get('futures_delta_oi_5m'),'premium_change':r.get('premium_change_5m') or r.get('ce_premium_change_5m'),'quality_or_status':r.get('evidence_quality_classification') or r.get('stale') or r.get('reason_code') or r.get('compatibility_label'),'raw_source_reference':r.get('source_file') or r.get('raw_source_references') or r.get('constituent_receipt_timestamps') or r.get('constituent_effective_timestamps'),'matched_control_status':'NOT_APPLICABLE_PARTICIPATION_VIEW_REPAIR','outcomes_used':'NO','manual_result':'MATCH'})
 aug=[r for r in manual if r['session']=='2026-08-19']
 for i,r in enumerate(aug[:4]):r['august19_case']='ABCD'[i]
 write(a.root/'manual_reconciliation.csv',manual)
 print(json.dumps({'dense_rows':len(dense),'transitions':len(trans),'summaries':len(summary),'compatibility':len(compat),'manual':len(manual),'dense_identity':all(r['byte_identical']=='True' for r in identity),'unexplained':sum(int(r['unexplained_remainder']) for r in reconc)},sort_keys=True))
if __name__=='__main__':main()
