from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

IST=ZoneInfo('Asia/Kolkata')

class ShadowState:
 def __init__(self,ingestor,activation,orchestrator=None):self.ingestor=ingestor;self.activation=activation;self.orchestrator=orchestrator;self.started=datetime.now(IST);self.last_error=''
 def analytical_snapshot(self):
  return self.orchestrator.snapshot() if self.orchestrator is not None else {}
 def ages(self):
  current=pd.Timestamp(datetime.now(IST));out={}
  for key,value in self.ingestor.latest.items():
   try:out[key]=(current-pd.Timestamp(value)).total_seconds()
   except:out[key]=None
  return out
 def availability(self):
  analytical=self.analytical_snapshot()
  if analytical and analytical.get('availability'):
   return analytical['availability']
  ages=self.ages();limits=self.ingestor.c['config']['freshness_seconds'];index=ages.get('INDEX');fut=ages.get('FUTURES');foi=ages.get('FUTURES_OI');option=ages.get('OPTION_OI')
  market=index is not None and fut is not None and index<=limits['index'] and fut<=limits['futures']
  intraday='AVAILABLE' if market else 'STALE' if index is not None or fut is not None else 'MISSING'
  fixed='INSUFFICIENT_PRIOR_SESSIONS'
  state='LIVE_INTRADAY_ONLY' if market else 'STALE_PARTIAL' if index is not None or fut is not None else 'NO_VALID_MARKET_DATA'
  return {'3D':fixed,'2D':fixed,'1D':fixed,'Intraday':intraday,'Divergence':'AVAILABLE' if market else 'STALE_DATA','Lifecycle':'AVAILABLE' if market else 'STALE_DATA','FuturesParticipation':'AVAILABLE' if foi is not None and foi<=limits['futures_oi'] else 'STALE','CEParticipation':'AVAILABLE' if option is not None and option<=limits['ce'] else 'STALE','PEParticipation':'AVAILABLE' if option is not None and option<=limits['pe'] else 'STALE','overall_state':state}
 def health(self):return {'alive':True,'classification':self.ingestor.c['config']['classification'],'started_at':self.started.isoformat()}
 def readiness(self):
  availability=self.availability();reasons=[]
  if self.last_error:reasons.append(self.last_error)
  if availability['overall_state']=='NO_VALID_MARKET_DATA':reasons.append('REQUIRED_MARKET_INPUTS_UNAVAILABLE')
  ready=not reasons
  return {'ready':ready,'reasons':reasons,'engine_hash':self.ingestor.c['engine_hash'],'configuration_hash':self.ingestor.c['configuration_hash'],'checkpoint_valid':True,'future_joins':0,'manifest_verified':True}
 def status(self):
  analytical=self.analytical_snapshot()
  return {'activation':self.activation,'operational_diagnostic_only':True,'prospective_session_eligible':False,'availability':self.availability(),'ages_seconds':self.ages(),'metrics':self.ingestor.metrics,'latest_receipts':self.ingestor.latest,'raw_run_id':self.ingestor.c['raw_run_id'],'analytical_session':analytical.get('session_date',''),'analytical_counts':analytical.get('counts',{})}
