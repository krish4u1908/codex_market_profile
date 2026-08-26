#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,signal,threading,time,uuid
from pathlib import Path
from banknifty_profiler.shadow.api import create_server
from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.shadow.state import ShadowState

def main():
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,required=True);p.add_argument('--state-root',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--bind',required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--mode',required=True);p.add_argument('--activation',type=Path,required=True);a=p.parse_args()
 c=validate_shadow_contract(a.data_root,a.state_root,a.config,a.bind,a.mode);c['raw_run_id']='R6E-'+uuid.uuid4().hex.upper();activation=json.loads(a.activation.read_text());c['minimum_session_date']=activation['activation_day'];ingestor=IncrementalJSONLIngestor(c);orchestrator=LiveAnalyticalOrchestrator(c,ledgers=ingestor.ledgers);ingestor.register_callback(orchestrator);state=ShadowState(ingestor,activation,orchestrator);server=create_server(state,a.bind,a.port);stop=threading.Event()
 def halt(*_):stop.set();server.shutdown()
 signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  while not stop.is_set():
   try:ingestor.poll();state.last_error=''
   except Exception as e:state.last_error=f'INGESTION_ERROR:{e}'
   stop.wait(float(c['config']['poll_interval_seconds']))
 finally:server.server_close();ingestor.close()
if __name__=='__main__':main()
