"""Canonical raw-only BN-reference multi-horizon inventory engine."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from banknifty_profiler.raw_io.reader import load_market,load_oi,select_contracts,backward_join,moneyness

FAMILIES=("BN_REF_FUT_VOLUME_VPOC","FUT_POS_OI_VPOC","FUT_NEG_OI_VPOC","CE_POS_OI_VPOC","CE_NEG_OI_VPOC","PE_POS_OI_VPOC","PE_NEG_OI_VPOC")
def iso(x):return "" if pd.isna(x) else pd.Timestamp(x).isoformat()
def sha(path):
 d=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""):d.update(block)
 return d.hexdigest()
def write(path,rows):
 rows=list(rows);fields=list(dict.fromkeys(k for row in rows for k in row))
 with path.open("w",newline="") as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator="\n");w.writeheader();w.writerows(rows)
def choose(weights,mean,prior=np.nan):
 maximum=max(weights.values());tied=sorted(k for k,v in weights.items() if v==maximum);rule="NO_TIE"
 if len(tied)>1:
  rule="TIE_WEIGHTED_MEAN";distance=min(abs(x-mean) for x in tied);tied=[x for x in tied if abs(x-mean)==distance]
  if len(tied)>1 and np.isfinite(prior):rule="TIE_PREVIOUS_VPOC";distance=min(abs(x-prior) for x in tied);tied=[x for x in tied if abs(x-prior)==distance]
  if len(tied)>1:rule="TIE_LOWER_BIN"
 return min(tied),rule
def profile(frame,bin_points,prior=np.nan):
 q=frame[pd.to_numeric(frame.px,errors="coerce").notna()&pd.to_numeric(frame.w,errors="coerce").gt(0)].copy()
 if q.empty:return None
 weights=defaultdict(float);total=weighted=0.0
 for _,row in q.iterrows():price_bin=float(round(float(row.px)/bin_points)*bin_points);weight=float(row.w);weights[price_bin]+=weight;total+=weight;weighted+=float(row.px)*weight
 winner,rule=choose(weights,weighted/total,prior);nodes=sorted(weights,key=lambda x:(-weights[x],x))
 return {"control_value":winner,"total_weight":total,"winning_bin_weight":weights[winner],"runner_up_bin":nodes[1] if len(nodes)>1 else "","runner_up_weight":weights[nodes[1]] if len(nodes)>1 else "","tie_break_reason":rule,"count":len(q)}
def price_events(market,date,futures,index_symbol,tolerance):
 start=pd.Timestamp(date+"T09:15:00+05:30");end=pd.Timestamp(date+"T15:30:00+05:30")
 values=market[(market.symbol==futures)&market.receipt_timestamp.between(start,end,inclusive="left")].sort_values(["receipt_timestamp","source_file","source_row"]).dropna(subset=["receipt_timestamp","cumulative_volume"]).copy();values["previous_valid"]=values.cumulative_volume.shift();values["w"]=values.cumulative_volume-values.previous_valid;values["reject"]="";values.loc[values.previous_valid.isna(),"reject"]="FIRST_VALID_COUNTER";values.loc[values.w.lt(0),"reject"]="COUNTER_RESET";values.loc[values.w.eq(0),"reject"]="UNCHANGED_COUNTER";values.loc[values.reject!="","w"]=np.nan
 index=market[(market.symbol==index_symbol)&market.receipt_timestamp.between(start,end,inclusive="left")&market.last_price.notna()].sort_values(["receipt_timestamp","source_file","source_row"])[["receipt_timestamp","last_price","source_file","source_row"]].rename(columns={"receipt_timestamp":"index_timestamp","last_price":"px","source_file":"index_source_file","source_row":"index_source_row"});values=pd.merge_asof(values.sort_values("receipt_timestamp"),index,left_on="receipt_timestamp",right_on="index_timestamp",direction="backward");values["join_age_seconds"]=(values.receipt_timestamp-values.index_timestamp).dt.total_seconds();invalid=values.join_age_seconds.gt(tolerance)|values.join_age_seconds.lt(0)|values.px.isna();values.loc[invalid,"reject"]="NO_CAUSAL_INDEX_WITHIN_TOLERANCE";values.loc[invalid,"w"]=np.nan;values["session_date"]=date;return values
def oi_events(oi,market,date,futures,option_expiry,index_symbol,tolerance):
 start=pd.Timestamp(date+"T09:15:00+05:30");end=pd.Timestamp(date+"T15:30:00+05:30");joined=moneyness(backward_join(oi,market[(market.symbol==index_symbol)&market.receipt_timestamp.between(start,end,inclusive="left")],tolerance_seconds=tolerance));joined=joined[joined.availability_timestamp.between(start,end,inclusive="left")&~joined.duplicate_record.fillna(False)].copy();joined["family"]="";joined.loc[(joined.instrument_class=="future")&(joined.symbol==futures)&joined.delta_oi.gt(0),"family"]="FUT_POS_OI_VPOC";joined.loc[(joined.instrument_class=="future")&(joined.symbol==futures)&joined.delta_oi.lt(0),"family"]="FUT_NEG_OI_VPOC";selected=joined.expiry_date.astype(str).eq(str(option_expiry))&joined.moneyness.isin(["ATM","NEAR_OTM"])
 for instrument,prefix in (("call","CE"),("put","PE")):
  joined.loc[selected&(joined.instrument_class==instrument)&joined.delta_oi.gt(0),"family"]=prefix+"_POS_OI_VPOC";joined.loc[selected&(joined.instrument_class==instrument)&joined.delta_oi.lt(0),"family"]=prefix+"_NEG_OI_VPOC"
 joined=joined[joined.family!=""].copy();joined["px"]=joined.matched_underlying_price;joined["w"]=joined.delta_oi.abs();joined["receipt_timestamp"]=joined.availability_timestamp;joined["join_age_seconds"]=(joined.availability_timestamp-joined.matched_price_timestamp).dt.total_seconds();return joined[joined.px.notna()&joined.w.gt(0)&joined.join_age_seconds.between(0,tolerance)]
def discover_sessions(data_root,config):
 raw=data_root/"raw";oi_root=data_root/"oi";common=sorted({p.name for p in raw.iterdir() if p.is_dir()}&{p.name for p in oi_root.iterdir() if p.is_dir()});rows=[];accepted=[];start=pd.Timestamp(config["discovery_start"]).date();end=pd.Timestamp(config["discovery_end"]).date()
 for date in [d for d in common if start<=pd.Timestamp(d).date()<=end]:
  market=load_market(raw,date,{config["index_symbol"],config["futures_symbol"]});oi=load_oi(oi_root,date);reasons=[];symbols=set(market.symbol) if len(market) else set();classes=set(oi.instrument_class) if len(oi) else set()
  if config["index_symbol"] not in symbols:reasons.append("MISSING_INDEX")
  if config["futures_symbol"] not in symbols:reasons.append("MISSING_FUTURES")
  for required,code in (("future","MISSING_FUTURES_OI"),("call","MISSING_CE_OI"),("put","MISSING_PE_OI")):
   if required not in classes:reasons.append(code)
  minute_coverage=set(pd.to_datetime(oi.availability_timestamp).dt.floor("min")) if len(oi) else set();session_minutes=pd.date_range(date+" 09:15",date+" 15:29",freq="min",tz="Asia/Kolkata");missing=sum(t not in minute_coverage for t in session_minutes)
  if missing>config["maximum_missing_oi_minutes"]:reasons.append("MATERIAL_CONTINUITY_OUTAGE")
  futures,fe,oe=select_contracts(oi,date) if len(oi) else ("",None,None)
  if futures!=config["futures_symbol"]:reasons.append("INCOMPATIBLE_FUTURES")
  status="ACCEPTED" if not reasons else "REJECTED"
  if status=="ACCEPTED":accepted.append(date)
  rows.append({"date":date,"status":status,"reason":"|".join(reasons) if reasons else "RAW_CONTINUITY_VERIFIED","missing_oi_minutes":missing,"futures_symbol":futures,"futures_expiry":fe,"option_expiry":oe})
 return rows,accepted
def record(date,horizon,family,value,sources,effective,latest,contract,expiry,count,weight,runner,runner_weight,tie):
 return {"evaluation_date":date,"horizon":horizon,"family":family,"sign":"POSITIVE" if "_POS_" in family else "NEGATIVE" if "_NEG_" in family else "VOLUME","control_value":value,"source_sessions":sources,"control_effective_timestamp":effective,"winner_change_timestamp":latest,"snapshot_timestamp":"","freshness_receipt_timestamp":latest,"last_contributing_change_timestamp":latest,"contract":contract,"expiry":expiry,"eligible_observation_count":count,"excluded_observation_count":0,"winning_bin_weight":weight,"runner_up_bin":runner,"runner_up_weight":runner_weight,"tie_break_reason":tie,"methodology_version":"INVENTORY_V2_BN_REF_RAW_CAUSAL","raw_input_hashes":"RECORDED_IN_FILE_OPEN_AUDIT","authority_basis":"RAW_CAUSAL_BANKNIFTY_REFERENCE","canonical_control_name":family,"user_facing_label":"BN-REF FUT VOL-VPOC" if family=="BN_REF_FUT_VOLUME_VPOC" else family,"canonical_revision":"INVENTORY_CANONICAL_REVISION_2_BN_REFERENCE_RAW_CAUSAL"}
def transitions(frame,family,date,contract,expiry,bin_points):
 q=frame[pd.to_numeric(frame.px,errors="coerce").notna()&pd.to_numeric(frame.w,errors="coerce").gt(0)&frame.receipt_timestamp.notna()].copy();rows=[];weights=defaultdict(float);total=weighted=0.;prior=np.nan;last=None;seen=0
 for timestamp,group in q.sort_values(["receipt_timestamp","source_file","source_row"]).groupby("receipt_timestamp",sort=True):
  for _,row in group.iterrows():price_bin=float(round(float(row.px)/bin_points)*bin_points);weight=float(row.w);weights[price_bin]+=weight;total+=weight;weighted+=float(row.px)*weight;seen+=1
  winner,rule=choose(weights,weighted/total,prior)
  if winner!=last:
   nodes=sorted(weights,key=lambda x:(-weights[x],x));rows.append(record(date,"ID",family,winner,date,iso(timestamp),iso(timestamp),contract,expiry,seen,weights[winner],nodes[1] if len(nodes)>1 else "",weights[nodes[1]] if len(nodes)>1 else "",rule));last=winner;prior=winner
 return rows
def generate(mode,data_root,output_root,config):
 eligibility,accepted=discover_sessions(data_root,config);evaluations=[d for d in accepted if config["evaluation_start"]<=d<=config["evaluation_end"] and len([x for x in accepted if x<d])>=3];chains={d:[x for x in accepted if x<d][-3:] for d in evaluations};needed=sorted(set(evaluations+sum(chains.values(),[])));frames={};contracts={};audit=[]
 for date in needed:
  oi=load_oi(data_root/"oi",date);futures,fe,oe=select_contracts(oi,date);market=load_market(data_root/"raw",date,{config["index_symbol"],futures});contracts[date]=(futures,fe,oe);frames[date]={"price":price_events(market,date,futures,config["index_symbol"],config["join_tolerance_seconds"]),"oi":oi_events(oi,market,date,futures,oe,config["index_symbol"],config["join_tolerance_seconds"])}
  for path in sorted((data_root/"raw"/date).glob("events_*.jsonl"))+sorted((data_root/"oi"/date).glob("oi_*.jsonl")):audit.append({"stage":"RAW_CALCULATION","path":str(path),"sha256":sha(path),"classification":"PERMITTED"})
 output=[]
 for date in evaluations:
  futures,fe,oe=contracts[date]
  for horizon,count in (("1D",1),("2D",2),("3D",3)):
   sources=chains[date][-count:]
   for family in FAMILIES:
    q=pd.concat([frames[d]["price"] if family=="BN_REF_FUT_VOLUME_VPOC" else frames[d]["oi"][frames[d]["oi"].family==family] for d in sources],ignore_index=True);result=profile(q,config["bin_points"])
    if result:
     latest=iso(q.receipt_timestamp.max())
     output.append(record(date,horizon,family,result["control_value"],"|".join(sources),date+"T09:15:00+05:30",latest,futures,fe if family.startswith(("BN_","FUT_")) else oe,result["count"],result["winning_bin_weight"],result["runner_up_bin"],result["runner_up_weight"],result["tie_break_reason"]))
  for family in FAMILIES:
   q=frames[date]["price"] if family=="BN_REF_FUT_VOLUME_VPOC" else frames[date]["oi"][frames[date]["oi"].family==family];output+=transitions(q,family,date,futures,fe if family.startswith(("BN_","FUT_")) else oe,config["bin_points"])
 output_root.mkdir(parents=True,exist_ok=False);write(output_root/"canonical_inventory.csv",output);write(output_root/"raw_session_eligibility.csv",eligibility);write(output_root/"discovered_source_chains.csv",[{"evaluation_date":d,"source_sessions":"|".join(c),"current_session_excluded":d not in c} for d,c in chains.items()]);write(output_root/"file_open_audit.csv",audit);summary={"mode":mode,"canonical_rows":len(output),"future_joins":sum(int((frames[d]["price"].join_age_seconds<0).sum()) for d in needed),"current_session_leakage":sum(d in c for d,c in chains.items()),"august_17_accepted":"2026-08-17" in accepted,"prohibited_opens":0};(output_root/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n");return summary
def main():
 parser=argparse.ArgumentParser();parser.add_argument("--mode",choices=("stream","batch"),required=True);parser.add_argument("--data-root",type=Path,required=True);parser.add_argument("--output-root",type=Path,required=True);parser.add_argument("--config",type=Path,required=True);args=parser.parse_args();data=args.data_root.resolve();output=args.output_root.resolve()
 if not data.is_dir():raise SystemExit("data root missing")
 if "research" in data.parts:raise SystemExit("derived analytical input root refused")
 if output.exists():raise SystemExit("output root must not exist")
 if Path(__file__).resolve().parents[3] in output.parents:raise SystemExit("output inside repository refused")
 if not args.config.is_file():raise SystemExit("configuration missing")
 print(json.dumps(generate(args.mode,data,output,json.loads(args.config.read_text())),sort_keys=True))
if __name__=="__main__":main()
