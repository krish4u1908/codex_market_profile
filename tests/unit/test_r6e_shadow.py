from __future__ import annotations
import json,threading,urllib.error,urllib.request
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pytest
from banknifty_profiler.shadow.api import create_server
from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.state import ShadowState

IST=ZoneInfo('Asia/Kolkata')
def ts(delta=0,exact=False):
 d=datetime.now(IST)+timedelta(seconds=delta)
 return d.replace(microsecond=0).isoformat() if exact else d.isoformat(timespec='microseconds')
def config():return {'timezone':'Asia/Kolkata','synchronization_tolerance_ms':2000,'selected_futures_by_session':{'2099-01-01':'NSE:BANKNIFTY26AUGFUT'},'poll_interval_seconds':.01,'max_read_bytes_per_file_per_poll':1048576,'max_buffer_bytes_per_file':1024,'freshness_seconds':{'index':10,'futures':10,'futures_oi':180,'ce':180,'pe':180},'allowed_bind':'127.0.0.1','classification':'LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL','analytical_threshold_overrides':None}
def setup(tmp_path):
 data=tmp_path/'collector';(data/'raw/2099-01-01').mkdir(parents=True);(data/'oi/2099-01-01').mkdir(parents=True);cfg=tmp_path/'config.json';cfg.write_text(json.dumps(config()));state=tmp_path/'state';c=validate_shadow_contract(data,state,cfg,'127.0.0.1','shadow');c['raw_run_id']='TEST';return data,state,c
def market(receipt,symbol='NSE:NIFTYBANK-INDEX'):return json.dumps({'received_at':receipt,'event_time':receipt,'message':{'symbol':symbol,'ltp':57000,'vol_traded_today':100}})
def oi(receipt,source='future_depth'):return json.dumps({'received_at':receipt,'request_time':receipt,'source':source,'response':{'d':{}} if source=='future_depth' else {'data':{'optionsChain':[]}}})

def test_contract_accepts_valid(tmp_path):
 _,_,c=setup(tmp_path);assert c['config']['timezone']=='Asia/Kolkata'
def test_contract_uses_captured_config_bytes_not_later_path_contents(tmp_path):
 data=tmp_path/'collector';(data/'raw/2099-01-01').mkdir(parents=True);(data/'oi/2099-01-01').mkdir(parents=True);cfg=tmp_path/'config.json';cfg.write_text(json.dumps(config()));captured=cfg.read_bytes();cfg.write_text('{mutated-after-capture')
 c=validate_shadow_contract(data,tmp_path/'state',cfg,'127.0.0.1','shadow',authenticated_config_payload=captured);assert c['config']['timezone']=='Asia/Kolkata'
@pytest.mark.parametrize('bind,mode',[('0.0.0.0','shadow'),('127.0.0.1','live')])
def test_contract_refuses_public_or_wrong_mode(tmp_path,bind,mode):
 data,state,_=setup(tmp_path);cfg=tmp_path/'config.json'
 with pytest.raises(ValueError):validate_shadow_contract(data,state/'x',cfg,bind,mode)
def test_contract_refuses_state_under_data(tmp_path):
 data,_,_=setup(tmp_path)
 with pytest.raises(ValueError):validate_shadow_contract(data,data/'state',tmp_path/'config.json','127.0.0.1','shadow')
@pytest.mark.parametrize('tz,tolerance',[('UTC',2000),('IST',2000),('Asia/Kolkata',1999),('Asia/Kolkata',2001),('Asia/Kolkata','2000')])
def test_frozen_runtime_invariants(tmp_path,tz,tolerance):
 data,state,_=setup(tmp_path);v=config();v['timezone']=tz;v['synchronization_tolerance_ms']=tolerance;(tmp_path/'bad.json').write_text(json.dumps(v))
 with pytest.raises(ValueError):validate_shadow_contract(data,state/'bad',tmp_path/'bad.json','127.0.0.1','shadow')
def test_threshold_override_refused(tmp_path):
 data,state,_=setup(tmp_path);v=config();v['analytical_threshold_overrides']={'x':1};(tmp_path/'bad.json').write_text(json.dumps(v))
 with pytest.raises(ValueError):validate_shadow_contract(data,state/'bad',tmp_path/'bad.json','127.0.0.1','shadow')
def test_complete_line_commits(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts())+'\n');i=IncrementalJSONLIngestor(c);assert len(i.poll())==1;assert i.checkpoints[str(p.relative_to(data))]['offset']==p.stat().st_size;i.close()
def test_incomplete_line_deferred_and_retried(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';text=market(ts());p.write_text(text);i=IncrementalJSONLIngestor(c);assert i.poll()==[];assert str(p.relative_to(data)) not in i.checkpoints
 with p.open('a') as h:h.write('\n')
 assert len(i.poll())==1;i.close()
def test_malformed_line_refused_but_checkpointed(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text('{bad}\n');i=IncrementalJSONLIngestor(c);assert i.poll()==[];assert i.metrics['malformed']==1;assert i.checkpoints[str(p.relative_to(data))]['offset']==p.stat().st_size;i.close()
def test_duplicate_prevented_after_checkpoint_rewind(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts())+'\n');i=IncrementalJSONLIngestor(c);i.poll();i.checkpoints[str(p.relative_to(data))]['offset']=0;i.checkpoints[str(p.relative_to(data))]['row']=0;assert i.poll()==[];assert i.metrics['duplicates']==1;i.close()
def test_restart_is_idempotent(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts())+'\n');i=IncrementalJSONLIngestor(c);i.poll();i.close();j=IncrementalJSONLIngestor(c);assert j.poll()==[];assert len(j.ledgers['normalized_raw_events'].rows())==1;j.close()
def test_checkpoint_corruption_refused(tmp_path):
 data,state,c=setup(tmp_path);state.mkdir();(state/'checkpoints.json').write_text('{bad')
 with pytest.raises(ValueError,match='checkpoint state corrupt'):IncrementalJSONLIngestor(c)
def test_file_truncation_refused(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts())+'\n');i=IncrementalJSONLIngestor(c);i.poll();p.write_text('');i.poll();assert i.ledgers['refusals_data_quality'].rows()[-1]['reason']=='FILE_TRUNCATED';i.close()
def test_hourly_rotation_discovered(tmp_path):
 data,state,c=setup(tmp_path);a=data/'raw/2099-01-01/events_09.jsonl';b=data/'raw/2099-01-01/events_10.jsonl';a.write_text(market(ts(-0.2))+'\n');b.write_text(market(ts(-0.1),'NSE:BANKNIFTY26AUGFUT')+'\n');i=IncrementalJSONLIngestor(c);assert len(i.poll())==2;assert len(i.checkpoints)==2;i.close()
def test_exact_and_fractional_timestamps(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts(exact=True))+'\n'+market(ts(), 'NSE:BANKNIFTY26AUGFUT')+'\n');i=IncrementalJSONLIngestor(c);assert len(i.poll())==2;i.close()
def test_naive_timestamp_refused(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market('2026-08-26T10:00:00')+'\n');i=IncrementalJSONLIngestor(c);assert i.poll()==[];assert i.ledgers['refusals_data_quality'].rows()[-1]['reason']=='TIMESTAMP_REFUSED';i.close()
def test_future_timestamp_refused(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts(10))+'\n');i=IncrementalJSONLIngestor(c);assert i.poll()==[];assert i.ledgers['refusals_data_quality'].rows()[-1]['reason']=='TIMESTAMP_REFUSED';i.close()
def test_out_of_order_is_visible_not_backdated(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text(market(ts())+'\n');i=IncrementalJSONLIngestor(c);i.poll();with_time=ts(-1)
 with p.open('a') as h:h.write(market(with_time)+'\n')
 i.poll();assert any(x['reason']=='OUT_OF_ORDER_RECEIPT' for x in i.ledgers['refusals_data_quality'].rows());assert i.latest['INDEX']!=with_time;i.close()
def test_oi_streams_classified(tmp_path):
 data,state,c=setup(tmp_path);p=data/'oi/2099-01-01/oi_09.jsonl';future=oi(ts());option=oi(ts(),'option_chain');p.write_text(future+'\n'+option+'\n');i=IncrementalJSONLIngestor(c);assert i.poll()==[]
 audit=i.unknown_symbol_audit();by_symbol={x['source_symbol']:x for x in audit};assert set(by_symbol)=={'<FUTURE_DEPTH_EMPTY>','<OPTION_CHAIN_EMPTY>'};assert all(x['reason']=='EMPTY_SOURCE_CONTAINER' and x['observation_count']==1 for x in audit);assert by_symbol['<FUTURE_DEPTH_EMPTY>']['first_byte_offset']==0;assert by_symbol['<OPTION_CHAIN_EMPTY>']['first_byte_offset']==len((future+'\n').encode());i.close()
def test_stale_market_suspends_divergence(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);i.latest={'INDEX':ts(-30),'FUTURES':ts(-30)};s=ShadowState(i,{});a=s.availability();assert a['Divergence']=='STALE_DATA' and a['overall_state']=='STALE_PARTIAL';i.close()
def test_fresh_market_allows_intraday_without_fixed(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);i.latest={'INDEX':ts(),'FUTURES':ts()};s=ShadowState(i,{});a=s.availability();assert a['overall_state']=='LIVE_INTRADAY_ONLY' and a['3D']=='INSUFFICIENT_PRIOR_SESSIONS';i.close()
def test_missing_options_do_not_block_market_readiness(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);i.latest={'INDEX':ts(),'FUTURES':ts()};s=ShadowState(i,{});assert s.readiness()['ready'];assert s.availability()['CEParticipation']=='STALE';i.close()
def test_readiness_fails_without_market(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);s=ShadowState(i,{});assert not s.readiness()['ready'];i.close()
def test_api_refuses_public_bind(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);s=ShadowState(i,{})
 with pytest.raises(ValueError):create_server(s,'0.0.0.0',0)
 i.close()
def test_api_endpoints(tmp_path):
 data,state,c=setup(tmp_path);i=IncrementalJSONLIngestor(c);i.latest={'INDEX':ts(),'FUTURES':ts()};s=ShadowState(i,{});server=create_server(s,'127.0.0.1',0);thread=threading.Thread(target=server.serve_forever);thread.start();base=f'http://127.0.0.1:{server.server_address[1]}'
 try:
  for path in ('health','readiness','status','session','chart','inventory','divergence','lifecycle','participation','transitions','availability','audit'):
   with urllib.request.urlopen(base+'/api/'+path) as r:assert r.status==200;assert json.loads(r.read()) is not None
 finally:server.shutdown();thread.join();server.server_close();i.close()
def test_event_ids_unique(tmp_path):
 data,state,c=setup(tmp_path);p=data/'raw/2099-01-01/events_09.jsonl';p.write_text('\n'.join(market(ts(i/10),'NSE:BANKNIFTY-INDEX' if i%2==0 else 'NSE:BANKNIFTY26AUGFUT') for i in range(10))+'\n');i=IncrementalJSONLIngestor(c);i.poll();ids=[x['event_id'] for x in i.ledgers['normalized_raw_events'].rows()];assert len(ids)==len(set(ids));i.close()
