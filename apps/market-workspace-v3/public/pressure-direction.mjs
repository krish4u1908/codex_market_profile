// PRESSURE_DIRECTION_RULE_V1: explicit, unfitted research rule. No probability,
// price or outcome inputs. Null means unavailable; zero is an observed neutral.
const MINUTE=60000;
export function pressureQuantities(raw){
 if(!raw)return null;
 const values=['ce_plus','ce_minus','pe_plus','pe_minus'].map(k=>raw[k]);
 if(!values.every(v=>typeof v==='number'&&Number.isFinite(v)&&v>=0))return null;
 const [cp,cm,pp,pm]=values,ceNet=cp-cm,peNet=pp-pm,total=cp+cm+pp+pm;
 const state=!total?'NO FLOW':ceNet<0&&peNet>0?'BULL':ceNet>0&&peNet<0?'BEAR':'MIXED';
 return {ceNet,peNet,total,quantity:total?100*(peNet-ceNet)/total:0,state};
}
export function pressureDirection(points,session,now,sourceStatus={}){
 const start=Date.parse(`${session}T09:50:00+05:30`),end=Date.parse(`${session}T15:00:00+05:30`);
 const rows=[];let previous=null,origin=null,mixedSince=null;
 for(const raw of points){
  if(raw.x>now)break;
  if(raw.x<start||raw.x>=end)continue;
  const one=pressureQuantities(raw.raw1),five=pressureQuantities(raw.raw5);
  const contiguous=previous&&raw.x-previous.x>0&&raw.x-previous.x<=90000;
  if(!contiguous){previous=null;origin=null;mixedSince=null;}
  if(!one||!five){rows.push({x:raw.x,direction:null,label:'UNAVAILABLE',reason:'Incomplete 1m / 5m OI windows.'});previous=null;origin=null;mixedSince=null;continue;}
  const previousState=previous?.state||null,change=previous?five.quantity-previous.quantity:null;
  if(five.state==='MIXED'){
   if(previousState!=='MIXED'){origin=['BULL','BEAR'].includes(previousState)?previousState:null;mixedSince=raw.x;}
  }else{origin=null;mixedSince=null;}
  let direction=0,reason='No agreement between the 1m flow and the 5m state.';
  if(!one.total||!five.total)reason='No flow in at least one window.';
  else if(five.state==='BULL'&&one.quantity>0){direction=1;reason='5m CE net removal + PE net addition; 1m quantity agrees.';}
  else if(five.state==='BEAR'&&one.quantity<0){direction=-1;reason='5m CE net addition + PE net removal; 1m quantity agrees.';}
  else if(five.state==='MIXED'&&origin==='BULL'&&one.quantity<0&&change!==null&&change<0){direction=-1;reason='Bull → mixed; 1m quantity is negative and 5m quantity balance is falling.';}
  else if(five.state==='MIXED'&&origin==='BEAR'&&one.quantity>0&&change!==null&&change>0){direction=1;reason='Bear → mixed; 1m quantity is positive and 5m quantity balance is rising.';}
  else if(five.state==='MIXED')reason=origin?`${origin==='BULL'?'Bull':'Bear'} → mixed; reversal conditions do not agree.`:'Mixed pressure without an observed preceding aligned state.';
  rows.push({x:raw.x,direction,label:direction>0?'UP':direction<0?'DOWN':'NEUTRAL',reason,
   state:five.state,previousState,mixedOrigin:origin,mixedSince,quantity1:one.quantity,quantity5:five.quantity,quantityChange5:change,
   ceNet5:five.ceNet,peNet5:five.peNet,activity5:five.total,kind:direction===0?'NEUTRAL':five.state==='MIXED'?'REVERSAL_CANDIDATE':'ALIGNED'});
  previous={x:raw.x,state:five.state,quantity:five.quantity};
 }
 const last=rows.at(-1),latest=last&&last.direction!==null&&now-last.x<=90000&&now<end?last:null;
 const reason=latest?'':now>=end?'Direction window ended at 15:00 IST.':last?last.direction===null?last.reason:'Latest OI receipt is stale.':sourceStatus.reason||'Awaiting complete OI windows after 09:50 IST.';
 return {policy:'PRESSURE_DIRECTION_RULE_V1',rows,latest,reason};
}

// Actual archived VIX at option-report receipt time, for sessions predating the
// separate VIX reader. These observations are display context, never model inputs.
export function pressureReportVix(data,feed){
  if(data.profile.instrument!=='NIFTY'||feed?.status!=='AVAILABLE'||feed.schema!=='OPTION_REPORT_INPUTS_V1'||feed.source!=='OPTION_CHAIN_REPORT_QUOTES'||feed.instrument!=='NIFTY'||feed.session!==data.session||!Array.isArray(feed.reports))return [];
  const open=Date.parse(`${data.session}T09:15:00+05:30`),close=Date.parse(`${data.session}T15:30:00+05:30`);let last=-Infinity;const rows=[];
  for(const r of feed.reports){if(!Number.isFinite(r.x)||r.x<=last||r.x<open||r.x>=close)return [];last=r.x;rows.push({x:r.x,vix_close:Number.isFinite(r.vix)&&r.vix>0?r.vix:null});}
  return rows;
}
