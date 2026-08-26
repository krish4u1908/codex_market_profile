from __future__ import annotations
import hashlib,json
from pathlib import Path
from banknifty_profiler.runtime.configuration import canonical_configuration_sha256,validate_canonical_runtime_config
from banknifty_profiler.shadow.symbols import CANONICAL_INDEX_SYMBOL,SymbolRegistry

CLASSIFICATION="LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"

def validate_shadow_contract(data_root:Path,state_root:Path,config_path:Path,bind:str,mode:str)->dict:
 data=data_root.resolve();state=state_root.resolve();config_file=config_path.resolve()
 if mode!='shadow':raise ValueError('mode must be exactly shadow')
 if bind!='127.0.0.1':raise ValueError('shadow API must bind exactly 127.0.0.1')
 if not data.is_absolute() or not state.is_absolute() or not config_file.is_absolute():raise ValueError('all runtime paths must be absolute')
 if not data.is_dir():raise ValueError(f'raw data root missing: {data}')
 if 'research' in data.parts:raise ValueError('research-derived analytical input is prohibited')
 if not (data/'raw').is_dir() or not (data/'oi').is_dir():raise ValueError('data root must contain physical raw and oi directories')
 repo=Path(__file__).resolve().parents[3]
 if state==data or data in state.parents:raise ValueError('state root must be outside read-only collector root')
 if state==repo or repo in state.parents:raise ValueError('state root must be outside source tree')
 if not config_file.is_file():raise ValueError('configuration missing')
 raw_config=json.loads(config_file.read_text())
 raw_config.setdefault('index_symbol',CANONICAL_INDEX_SYMBOL)
 raw_config.setdefault('futures_selection_mode','SESSION_NEAREST_UNEXPIRED_HIGHEST_OI')
 raw_config.setdefault('selected_futures_by_session',{})
 config=validate_canonical_runtime_config(raw_config)
 if config.get('index_symbol')!=CANONICAL_INDEX_SYMBOL:raise ValueError(f'index_symbol must be exactly {CANONICAL_INDEX_SYMBOL}')
 if config.get('futures_selection_mode')!='SESSION_NEAREST_UNEXPIRED_HIGHEST_OI':raise ValueError('invalid futures_selection_mode')
 if not isinstance(config.get('selected_futures_by_session'),dict):raise ValueError('selected_futures_by_session must be an object')
 SymbolRegistry(selected_by_session=config['selected_futures_by_session'])
 if config.get('allowed_bind')!='127.0.0.1':raise ValueError('configuration allowed_bind must be exactly 127.0.0.1')
 if config.get('analytical_threshold_overrides') is not None:raise ValueError('runtime analytical threshold overrides are prohibited')
 for key,value in config.get('freshness_seconds',{}).items():
  if type(value) not in (int,float) or value<=0:raise ValueError(f'invalid freshness threshold: {key}')
 return {'data_root':data,'state_root':state,'config_path':config_file,'config':config,'configuration_hash':canonical_configuration_sha256(config),'engine_hash':engine_hash(repo)}

def engine_hash(repo:Path)->str:
 manifest=repo/'manifests/repository_source_manifest.json'
 if not manifest.is_file():raise ValueError('repository manifest missing')
 return hashlib.sha256(manifest.read_bytes()).hexdigest()
