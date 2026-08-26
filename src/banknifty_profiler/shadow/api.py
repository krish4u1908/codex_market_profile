from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs

ENDPOINT_COMPONENT={'/api/divergence':'episodes','/api/lifecycle':'lifecycle','/api/inventory':'inventory','/api/participation':'participation_dense','/api/transitions':'cross_layer_transitions'}

def handler_for(state):
 class Handler(BaseHTTPRequestHandler):
  def _send(self,obj,status=200):
   data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
  def do_GET(self):
   path=urlparse(self.path).path
   if path=='/api/health':return self._send(state.health())
   if path=='/api/readiness':
    value=state.readiness();return self._send(value,200 if value['ready'] else 503)
   if path=='/api/status':return self._send(state.status())
   if path=='/api/availability':return self._send(state.availability())
   if path=='/api/session':
    snapshot=state.analytical_snapshot();return self._send(snapshot or {'session_date':max((x.get('session_date','') for x in state.ingestor.ledgers['normalized_raw_events'].rows()),default=''),'status':state.status()})
   if path=='/api/chart':
    snapshot=state.analytical_snapshot();return self._send(snapshot.get('gui_payload') or {'latest_receipts':state.ingestor.latest,'future_path_control':False,'classification':state.ingestor.c['config']['classification']})
   if path in ENDPOINT_COMPONENT:
    snapshot=state.analytical_snapshot();rows=snapshot.get(ENDPOINT_COMPONENT[path],[]);return self._send({'rows':rows[-1000:],'count':len(rows),'session_date':snapshot.get('session_date','')})
   if path=='/api/audit':
    rows=state.ingestor.ledgers['refusals_data_quality'].rows();return self._send({'rows':rows[-1000:],'count':len(rows)})
   self._send({'error':'NOT_FOUND'},404)
  def log_message(self,*args):pass
 return Handler

def create_server(state,bind,port):
 if bind!='127.0.0.1':raise ValueError('public bind prohibited')
 return ThreadingHTTPServer((bind,port),handler_for(state))
