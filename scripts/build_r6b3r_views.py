#!/usr/bin/env python3
import argparse,csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

def read(path):
 with path.open(newline='') as f:return list(csv.DictReader(f)),next(iter([None]),None)
def read_rows(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def fields(path):
 with path.open(newline='') as f:return next(csv.reader(f))
def write(path,rows,order=None):
 keys=order or list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def norm(v):return (v or '').replace(' ','T')
def dt(v):return datetime.fromisoformat(norm(v))
def max_ts(values):
 valid=[v for v in values if v]
 return max(valid,key=dt) if valid else ''
def min_ts(values):
 valid=[v for v in values if v]
 return min(valid,key=dt) if valid else ''
def did(*parts):return 'R6B3R-'+hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:24].upper()
def sign(v):
 try:x=float(v)
 except:return 'UNKNOWN'
 return 'UP' if x>0 else 'DOWN' if x<0 else 'UNCHANGED'
def futures_state(row,w):return f"PRICE_{sign(row.get(f'price_change_{w}m'))}_OI_{sign(row.get(f'delta_oi_{w}m'))}"
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--anchors',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['stream','batch'],required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 fp=a.input/'futures_participation.csv';op=a.input/'option_participation.csv';bp=a.input.parent.parent/'option_strike_breadth.csv'
 futures=read_rows(fp);options=read_rows(op);breadth=read_rows(bp);anchors=read_rows(a.anchors);amap={r['episode_id']:r for r in anchors}
 opens=[]
 for path in (fp,op,bp,a.anchors):opens.append({'phase':'A_B_CANONICAL_INPUT','path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 # View 1: lossless union. Original fields are untouched; union-only fields are prefixed.
 union_fields=['view_record_kind']+list(dict.fromkeys(fields(fp)+fields(op)))
 dense=[]
 for r in futures:dense.append({'view_record_kind':'FUTURES',**r})
 for r in options:dense.append({'view_record_kind':'OPTION',**r})
 dense.sort(key=lambda r:(norm(r.get('observation_timestamp','')),r['episode_id'],r['view_record_kind'],r.get('symbol',''),r.get('record_id','')))
 write(a.output/'dense_participation_view.csv',dense,union_fields)
 # Group snapshots shared by Views 2-4.
 fut_by=defaultdict(list);opt_by=defaultdict(list);breadth_by=defaultdict(list)
 for r in futures:fut_by[r['episode_id']].append(r)
 for r in options:opt_by[r['episode_id']].append(r)
 for r in breadth:breadth_by[r['episode_id']].append(r)
 for groups in (fut_by,opt_by,breadth_by):
  for rows in groups.values():rows.sort(key=lambda r:norm(r['observation_timestamp']))
 transitions=[];summaries=[];compat=[];clock_audit=[]
 for ep in sorted(amap):
  anchor=amap[ep];confirmation=anchor['confirmation_timestamp'];fr=fut_by[ep];orr=opt_by[ep];br=breadth_by[ep]
  # Material component transitions.
  prior={}
  for r in fr:
   state='|'.join(str(r.get(k,'')) for k in ('price_change_1m','price_change_3m','price_change_5m','delta_oi_1m','delta_oi_3m','delta_oi_5m','volume_spike','stale','volume_status'))
   key=('FUTURES',r.get('symbol',''))
   if prior.get(key)!=state:
    effective=max_ts([r.get('receipt_timestamp'),r.get('observation_timestamp')]);transitions.append({'transition_id':did(ep,*key,effective,state),'episode_id':ep,'dependency_group_id':anchor.get('dependency_group_id',''),'component':'FUTURES','previous_state':prior.get(key,'UNOBSERVED'),'new_state':state,'effective_timestamp':effective,'evidence_receipt_timestamp':r.get('receipt_timestamp',''),'constituent_effective_timestamps':json.dumps({'futures_oi':r.get('receipt_timestamp'),'futures_volume':r.get('observation_timestamp')},sort_keys=True),'calculation_timestamp':r['observation_timestamp'],'reason_code':'MATERIAL_FUTURES_STATE_CHANGE','raw_source_references':f"{r.get('source_file')}:{r.get('source_row')}"});prior[key]=state
  for r in orr:
   state='|'.join(str(r.get(k,'')) for k in ('symbol','strike','expiry','moneyness','inventory_state','semantic_classification','volume_spike','oi_spike','stale'))
   key=(r['option_type'],r['symbol'])
   if prior.get(key)!=state:
    effective=r['receipt_timestamp'];transitions.append({'transition_id':did(ep,*key,effective,state),'episode_id':ep,'dependency_group_id':anchor.get('dependency_group_id',''),'component':r['option_type'],'previous_state':prior.get(key,'UNOBSERVED'),'new_state':state,'effective_timestamp':effective,'evidence_receipt_timestamp':effective,'constituent_effective_timestamps':json.dumps({r['symbol']:effective},sort_keys=True),'calculation_timestamp':r['observation_timestamp'],'reason_code':'MATERIAL_STRIKE_STATE_CHANGE','raw_source_references':f"{r.get('source_file')}:{r.get('source_row')}"});prior[key]=state
  for r in br:
   state='|'.join(str(r.get(k,'')) for k in ('selected_strike_count','supportive_count','contradictory_count','mixed','broad_agreement','ce_pe_agreement'))
   key=('BREADTH','AGGREGATE');const=[x['receipt_timestamp'] for x in orr if norm(x['observation_timestamp'])==norm(r['observation_timestamp'])];effective=max_ts(const)
   if effective and prior.get(key)!=state:
    transitions.append({'transition_id':did(ep,*key,effective,state),'episode_id':ep,'dependency_group_id':anchor.get('dependency_group_id',''),'component':'BREADTH','previous_state':prior.get(key,'UNOBSERVED'),'new_state':state,'effective_timestamp':effective,'evidence_receipt_timestamp':effective,'constituent_effective_timestamps':json.dumps(sorted(set(const))),'calculation_timestamp':r['observation_timestamp'],'reason_code':'MATERIAL_BREADTH_CHANGE','raw_source_references':'R6B3_CANONICAL_STRIKE_ROWS'});prior[key]=state
   option_rows=[x for x in orr if norm(x['observation_timestamp'])==norm(r['observation_timestamp'])];future_rows=[x for x in fr if dt(x['observation_timestamp'])<=dt(r['observation_timestamp'])];frow=future_rows[-1] if future_rows else {};receipts=[x['receipt_timestamp'] for x in option_rows]+([frow.get('receipt_timestamp','')] if frow else []);joint_effective=max_ts(receipts);stale=any(str(x.get('stale')).lower()=='true' for x in option_rows+([frow] if frow else []));types={x['option_type'] for x in option_rows};quality='STALE' if stale else 'PARTIAL' if not frow or types!={'CE','PE'} else 'COMPLETE_MIXED' if r.get('mixed')=='True' else 'COMPLETE_AGREED';joint_state='|'.join((quality,str(r.get('supportive_count')),str(r.get('contradictory_count')),str(frow.get('volume_spike','')),str(frow.get('stale',''))));key=('JOINT','AGGREGATE')
   if joint_effective and prior.get(key)!=joint_state:
    transitions.append({'transition_id':did(ep,*key,joint_effective,joint_state),'episode_id':ep,'dependency_group_id':anchor.get('dependency_group_id',''),'component':'JOINT','previous_state':prior.get(key,'UNOBSERVED'),'new_state':joint_state,'effective_timestamp':joint_effective,'evidence_receipt_timestamp':joint_effective,'constituent_effective_timestamps':json.dumps(sorted(set(x for x in receipts if x))),'calculation_timestamp':r['observation_timestamp'],'reason_code':'MATERIAL_JOINT_OR_EVIDENCE_QUALITY_CHANGE','raw_source_references':'R6B3_CANONICAL_FUTURES_AND_STRIKE_ROWS'});prior[key]=joint_state
  # Episode constituent clocks and first states.
  fconfirm=next((r for r in fr if norm(r['observation_timestamp'])==norm(confirmation)),fr[0] if fr else {})
  ce=sorted([r for r in orr if r['option_type']=='CE'],key=lambda r:dt(r['receipt_timestamp']));pe=sorted([r for r in orr if r['option_type']=='PE'],key=lambda r:dt(r['receipt_timestamp']))
  first_f=fconfirm.get('receipt_timestamp','');first_ce=ce[0]['receipt_timestamp'] if ce else '';first_pe=pe[0]['receipt_timestamp'] if pe else ''
  first_b=min_ts([t['effective_timestamp'] for t in transitions if t['episode_id']==ep and t['component']=='BREADTH']);joint=max_ts([first_f,first_ce,first_pe,first_b])
  semantics=defaultdict(list)
  for r in orr:semantics[r['semantic_classification']].append(r['receipt_timestamp'])
  first_support=min_ts(semantics['SUPPORTIVE']);first_contra=min_ts(semantics['CONTRADICTORY']);first_amb=min_ts(semantics['NEUTRAL_AMBIGUOUS']);mixed=min_ts([t['effective_timestamp'] for t in transitions if t['episode_id']==ep and t['component']=='BREADTH' and '|True|' in '|'+t['new_state']+'|'])
  latest=max_ts([r.get('receipt_timestamp','') for r in fr+orr]);cohort='PRE_EXISTING_AT_CONFIRMATION' if any(dt(x)<=dt(confirmation) for x in (first_ce,first_pe) if x) else 'NEW_AFTER_CONFIRMATION'
  first_ce_row=ce[0] if ce else {};first_pe_row=pe[0] if pe else {};first_br=br[0] if br else {}
  stale=any(str(r.get('stale')).lower()=='true' for r in (fconfirm,first_ce_row,first_pe_row) if r);missing=not all((fconfirm,first_ce_row,first_pe_row,first_br));quality='STALE' if stale else 'PARTIAL' if missing else 'COMPLETE_MIXED' if first_br.get('mixed')=='True' else 'COMPLETE_AGREED'
  summaries.append({'episode_id':ep,'evaluation_date':confirmation[:10],'colour':anchor['colour'],'dependency_group_id':anchor.get('dependency_group_id',''),'confirmation_timestamp':confirmation,'first_futures_qualifying_timestamp':first_f,'first_ce_qualifying_timestamp':first_ce,'first_pe_qualifying_timestamp':first_pe,'first_breadth_timestamp':first_b,'first_joint_participation_timestamp':joint,'first_supportive_timestamp':first_support,'first_contradictory_timestamp':first_contra,'first_mixed_timestamp':mixed,'first_ambiguous_timestamp':first_amb,'latest_eligible_evidence_timestamp':latest,'constituent_receipt_timestamps':json.dumps({'futures':first_f,'ce':first_ce,'pe':first_pe,'breadth':first_b},sort_keys=True),'timing_cohort':cohort,'futures_state_1m':futures_state(fconfirm,1) if fconfirm else 'MISSING','futures_state_3m':futures_state(fconfirm,3) if fconfirm else 'MISSING','futures_state_5m':futures_state(fconfirm,5) if fconfirm else 'MISSING','futures_volume_5m':fconfirm.get('incremental_volume_5m',''),'futures_volume_spike':fconfirm.get('volume_spike',''),'first_ce_symbol':first_ce_row.get('symbol',''),'first_ce_state':first_ce_row.get('semantic_classification',''),'first_ce_strike':first_ce_row.get('strike',''),'first_ce_expiry':first_ce_row.get('expiry',''),'first_ce_moneyness':first_ce_row.get('moneyness',''),'first_pe_symbol':first_pe_row.get('symbol',''),'first_pe_state':first_pe_row.get('semantic_classification',''),'first_pe_strike':first_pe_row.get('strike',''),'first_pe_expiry':first_pe_row.get('expiry',''),'first_pe_moneyness':first_pe_row.get('moneyness',''),'breadth_state':json.dumps(first_br,sort_keys=True),'joint_participation':quality,'conservative_semantic_classification':'MIXED' if first_br.get('mixed')=='True' else 'AGREED_OR_NEUTRAL','evidence_quality_classification':quality,'stale_missing_status':'STALE' if stale else 'MISSING' if missing else 'VALID','summary_reason_code':'FIRST_CAUSAL_CONSTITUENT_CLOCKS_PRESERVED'})
  # Compatibility: independent first qualifying joint option observation.
  observation_times=sorted({r['observation_timestamp'] for r in orr},key=dt);chosen=''
  for t in observation_times:
   rows=[r for r in orr if norm(r['observation_timestamp'])==norm(t)];types={r['option_type'] for r in rows};qual=[r for r in rows if r.get('semantic_classification')!='INSUFFICIENT_EVIDENCE' and (r.get('volume_spike')=='True' or r.get('oi_spike')=='True')]
   if types=={'CE','PE'} and {r['option_type'] for r in qual}=={'CE','PE'}:chosen=t;break
  if not chosen:chosen=observation_times[0] if observation_times else confirmation
  rows=[r for r in orr if norm(r['observation_timestamp'])==norm(chosen)];ce_rows=[r for r in rows if r['option_type']=='CE'];pe_rows=[r for r in rows if r['option_type']=='PE'];effective=max_ts([r['receipt_timestamp'] for r in rows]);brow=next((r for r in br if norm(r['observation_timestamp'])==norm(chosen)),{})
  def agg(rows,field):return sum(float(r[field]) for r in rows if r.get(field) not in ('',None))
  snapshot=max_ts([confirmation,effective]);compat.append({'episode_id':ep,'evaluation_date':confirmation[:10],'compatibility_label':'LEGACY R4/R5 COMPATIBILITY SNAPSHOT — LOSSY, NOT RAW AUTHORITY','snapshot_timestamp':snapshot,'confirmation_time_futures_snapshot':confirmation,'futures_effective_timestamp':fconfirm.get('receipt_timestamp',''),'option_joint_effective_timestamp':effective,'constituent_effective_timestamps':json.dumps({'futures':fconfirm.get('receipt_timestamp',''),'ce':sorted({r['receipt_timestamp'] for r in ce_rows}),'pe':sorted({r['receipt_timestamp'] for r in pe_rows})},sort_keys=True),'futures_volume_5m':fconfirm.get('incremental_volume_5m',''),'futures_delta_oi_5m':fconfirm.get('delta_oi_5m',''),'ce_selected_symbol':ce_rows[0].get('symbol','') if ce_rows else '','ce_eligible_strikes':len(ce_rows),'ce_volume_5m':agg(ce_rows,'incremental_volume_5m'),'ce_delta_oi_5m':agg(ce_rows,'delta_oi_5m'),'ce_premium_change_5m':agg(ce_rows,'premium_change_5m'),'pe_selected_symbol':pe_rows[0].get('symbol','') if pe_rows else '','pe_eligible_strikes':len(pe_rows),'pe_volume_5m':agg(pe_rows,'incremental_volume_5m'),'pe_delta_oi_5m':agg(pe_rows,'delta_oi_5m'),'pe_premium_change_5m':agg(pe_rows,'premium_change_5m'),'breadth_supportive_count':brow.get('supportive_count',''),'breadth_contradictory_count':brow.get('contradictory_count',''),'breadth_mixed':brow.get('mixed',''),'compatibility_reason_code':'INDEPENDENT_FIRST_JOINT_QUALIFYING_SELECTOR'})
  for component,value in [('FUTURES',first_f),('CE',first_ce),('PE',first_pe),('BREADTH',first_b),('JOINT',joint)]:clock_audit.append({'episode_id':ep,'component':component,'confirmation_timestamp':confirmation,'effective_timestamp':value,'backdated':str(bool(value and dt(value)>dt(confirmation) and value==confirmation)),'validity':'PASS' if value else 'MISSING'})
 transitions.sort(key=lambda r:(r['episode_id'],norm(r['effective_timestamp']),r['component'],r['transition_id']))
 write(a.output/'transition_participation_ledger.csv',transitions);write(a.output/'episode_participation_summary.csv',summaries);write(a.output/'legacy_compatibility_snapshot.csv',compat);write(a.output/'constituent_clock_audit.csv',clock_audit);write(a.output/'file_open_audit.csv',opens)
 seal={'mode':a.mode,'dense_rows':len(dense),'transition_rows':len(transitions),'summary_rows':len(summaries),'compatibility_rows':len(compat)}
 for name in ('dense_participation_view.csv','transition_participation_ledger.csv','episode_participation_summary.csv','legacy_compatibility_snapshot.csv','constituent_clock_audit.csv'):seal[name]=hashlib.sha256((a.output/name).read_bytes()).hexdigest()
 seal['prohibited_reference_opens']=sum('clean_combined_profiler_r4' in r['path'] or 'clean_combined_profiler_r5' in r['path'] for r in opens)
 (a.output/'seal.json').write_text(json.dumps(seal,indent=2,sort_keys=True)+'\n');print(json.dumps(seal,sort_keys=True))
if __name__=='__main__':main()
