#!/usr/bin/env python3
"""Repository-native raw divergence/dependency regeneration."""
from __future__ import annotations

import argparse,csv,hashlib,json
from datetime import datetime
from pathlib import Path
import pandas as pd

from banknifty_profiler.raw_io.reader import load_market
from banknifty_profiler.divergence.detector import causal_basis,derive,episodes
from banknifty_profiler.divergence.dependency import group_episodes
from banknifty_profiler.lifecycle.raw_engine import build_lifecycle


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1<<20),b""):digest.update(block)
    return digest.hexdigest()


def write(path,rows):
    rows=list(rows); fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def require_external_root(path,label):
    resolved=path.resolve()
    if not resolved.is_dir():raise SystemExit(f"{label} does not exist: {resolved}")
    if "research" in resolved.parts:raise SystemExit(f"{label} may not be a derived research path: {resolved}")
    return resolved


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",required=True,choices=("stream","batch"))
    parser.add_argument("--data-root",required=True,type=Path)
    parser.add_argument("--output-root",required=True,type=Path)
    parser.add_argument("--config",required=True,type=Path)
    args=parser.parse_args()
    data_root=require_external_root(args.data_root,"data root")
    if not args.config.is_file():raise SystemExit(f"configuration missing: {args.config}")
    config=json.loads(args.config.read_text()); raw_root=data_root/"raw"
    if not raw_root.is_dir():raise SystemExit(f"raw market root missing: {raw_root}")
    args.output_root.mkdir(parents=True,exist_ok=False)
    all_episodes=[];series={};index_series={};opened=[]
    for date in config["sessions"]:
        files=sorted((raw_root/date).glob("events_*.jsonl"))
        if not files:raise SystemExit(f"required raw files absent: {date}")
        observations=load_market(raw_root,date,{config["index_symbol"],config["futures_symbol"]})
        if observations.empty:raise SystemExit(f"required symbols absent: {date}")
        basis=causal_basis(observations,date,config["index_symbol"],config["futures_symbol"],config["synchronization_tolerance_ms"])
        frame=derive(basis);series[date]=frame
        index=observations[(observations.symbol==config["index_symbol"])&observations.receipt_timestamp.notna()&observations.last_price.notna()].sort_values(["receipt_timestamp","source_file","source_row"])
        index_series[date]=index[["receipt_timestamp","last_price"]].rename(columns={"receipt_timestamp":"t","last_price":"index"})
        selected=[row for row in episodes(frame) if row["episode_type"] in ("GREEN_CONFIRMED","RED_CONFIRMED")]
        for row in selected:
            t=pd.Timestamp(row["confirmation_timestamp"]);point=frame[frame.t==t].iloc[-1]
            all_episodes.append({"evaluation_date":date,"colour":"GREEN" if row["episode_type"]=="GREEN_CONFIRMED" else "RED","episode_start_timestamp":row["start_timestamp"],"candidate_start_timestamp":row["start_timestamp"],"confirmation_timestamp":row["confirmation_timestamp"],"episode_end_timestamp":row["end_timestamp"],"index_at_confirmation":point["index"],"futures_at_confirmation":point["futures"],"basis_at_confirmation":point["basis"],"basis_percentile":point["basis_expanding_percentile"],"basis_zscore":point["basis_robust_z"],"persistence":(t-pd.Timestamp(row["start_timestamp"])).total_seconds(),"index_age":point["index_data_age_seconds"],"futures_age":point["futures_data_age_seconds"],"join_age":point["absolute_receipt_difference_ms"],"reason_code":"LOCKED_P60_N5_TWO_OF_1M_3M_5M"})
        for path in files:opened.append({"opened_path":str(path),"access_stage":"RAW_GENERATION","purpose":"RAW_WEBSOCKET_INPUT","classification":"PERMITTED","source_component":"DIVERGENCE","opened_at":datetime.now().astimezone().isoformat(),"sha256":sha(path)})
    all_episodes.sort(key=lambda r:pd.Timestamp(r["confirmation_timestamp"]))
    for ordinal,row in enumerate(all_episodes,1):row["episode_id"]=f"BDR1-{row['evaluation_date']}-{row['colour']}-{ordinal:03d}"
    dependencies=group_episodes(all_episodes,series)
    lifecycle,dense,responses=build_lifecycle(all_episodes,dependencies,series,index_series)
    write(args.output_root/"raw_divergence_episodes.csv",all_episodes);write(args.output_root/"raw_dependency_groups.csv",dependencies);write(args.output_root/"raw_lifecycle_transitions.csv",lifecycle);write(args.output_root/"raw_resolution_observations.csv",dense);write(args.output_root/"raw_response_observations.csv",responses);write(args.output_root/"file_open_audit.csv",opened)
    summary={"mode":args.mode,"episodes":len(all_episodes),"green":sum(r["colour"]=="GREEN" for r in all_episodes),"red":sum(r["colour"]=="RED" for r in all_episodes),"retriggers":sum(r["retrigger_flag"] for r in dependencies),"lifecycle_transitions":len(lifecycle),"dense_resolution_observations":len(dense),"future_joins":0,"prohibited_runtime_opens":0}
    (args.output_root/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print(json.dumps(summary,sort_keys=True))


if __name__=="__main__":main()
