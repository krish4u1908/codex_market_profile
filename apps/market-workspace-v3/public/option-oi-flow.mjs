// Display-only, causal minute flow derived from successive option OI reports.
// It does not change calls, bubbles, VPOCs, or the shared core's calculations.
export const OPTION_OI_FLOW_POLICY=Object.freeze({
  id:'NEAR_OTM_OPTION_OI_FLOW_1M_V1',
  source:'OPTION_CHAIN_REPORT_QUOTES',
  inputSchema:'OPTION_REPORT_INPUTS_V1',
  strikesPerSide:3,
  maxReceiptGapMs:90000,
  minuteMs:60000,
});

const finite=value=>typeof value==='number'&&Number.isFinite(value);
const positive=value=>finite(value)&&value>0;

export function nearOtmFlowStrikes(spot,side,step) {
  if(!positive(spot)||!positive(step)||!['PE','CE'].includes(side))return [];
  const first=side==='PE'?Math.ceil(spot/step)-1:Math.floor(spot/step)+1;
  return Array.from({length:OPTION_OI_FLOW_POLICY.strikesPerSide},(_,index)=>
    step*(first+(side==='PE'?-index:index)));
}

function blankResult(status='UNAVAILABLE',reason='Raw option-report quotes are unavailable.') {
  return {policy:OPTION_OI_FLOW_POLICY,status,reason,points:[],reportCount:0,lastReportAt:null};
}

function dominance(positiveOi,negativeOi) {
  if(positiveOi===0&&negativeOi===0)return {dominant:'FLAT',ratio:0};
  if(positiveOi===negativeOi)return {dominant:'BALANCED',ratio:1};
  const high=Math.max(positiveOi,negativeOi),low=Math.min(positiveOi,negativeOi);
  return {dominant:positiveOi>negativeOi?'POSITIVE':'NEGATIVE',ratio:low>0?high/low:null};
}

export function optionOiMinuteFlows(data,feed) {
  if(data.profile.version!=='2.0.0')return blankResult('NOT_APPLICABLE','');
  if(!feed)return blankResult();
  if(feed.schema!==OPTION_OI_FLOW_POLICY.inputSchema||feed.instrument!==data.profile.instrument||feed.session!==data.session)
    return blankResult('INVALID','Option-report instrument, session or schema does not match this workspace.');
  if(feed.status!=='AVAILABLE')return blankResult(feed.status||'UNAVAILABLE',feed.status==='PENDING'?'Loading option-report quotes…':feed.error||'Raw option reports are unavailable for this session.');
  if(feed.source!==OPTION_OI_FLOW_POLICY.source||!Array.isArray(feed.reports))
    return blankResult('INVALID','Verified option-report quotes are required.');

  const open=Date.parse(`${data.session}T09:15:00+05:30`);
  const close=Date.parse(`${data.session}T15:30:00+05:30`);
  const step=data.profile.instrument==='NIFTY'?50:100;
  const previous=new Map();
  const minutes=new Map();
  let priorTime=-Infinity;

  for(const report of feed.reports) {
    if(!finite(report.x)||report.x<=priorTime||report.x<open||report.x>=close||!Array.isArray(report.contracts))
      return blankResult('INVALID','Option reports must have unique, ordered receipt times within this session.');
    priorTime=report.x;
    const current=new Map();
    for(const contract of report.contracts) {
      if(typeof contract.symbol!=='string'||!['PE','CE'].includes(contract.side)||!positive(contract.strike))continue;
      const key=`${report.expiry||''}|${contract.symbol}`;
      if(current.has(key))return blankResult('INVALID','Duplicate option contract in a report.');
      current.set(key,contract);
    }

    const minute=Math.floor(report.x/OPTION_OI_FLOW_POLICY.minuteMs)*OPTION_OI_FLOW_POLICY.minuteMs;
    for(const side of ['PE','CE']) {
      const strikes=new Set(nearOtmFlowStrikes(report.spot,side,step));
      let positiveOi=0,negativeOi=0,validContracts=0;
      const changes=[];
      for(const [key,contract] of current) {
        if(contract.side!==side||!strikes.has(contract.strike)||!positive(contract.oi))continue;
        const prior=previous.get(key);
        if(!prior||!positive(prior.oi)||report.x<=prior.x||report.x-prior.x>OPTION_OI_FLOW_POLICY.maxReceiptGapMs)continue;
        const delta=contract.oi-prior.oi;
        if(delta>=0)positiveOi+=delta;else negativeOi+=Math.abs(delta);
        validContracts++;
        changes.push({symbol:contract.symbol,strike:contract.strike,delta,oiFrom:prior.oi,oiTo:contract.oi});
      }
      if(validContracts) {
        const key=`${minute}|${side}`;
        const row=minutes.get(key)||{x:report.x,minute,side,positive:0,negative:0,net:0,
          validContracts:0,expectedContracts:OPTION_OI_FLOW_POLICY.strikesPerSide,receipts:0,changes:[],fromAt:report.x,toAt:report.x};
        row.x=report.x;
        row.toAt=report.x;
        row.fromAt=Math.min(row.fromAt,...changes.map(change=>previous.get(`${report.expiry||''}|${change.symbol}`)?.x??report.x));
        row.positive+=positiveOi;
        row.negative+=negativeOi;
        row.net=row.positive-row.negative;
        row.validContracts=Math.max(row.validContracts,validContracts);
        row.receipts++;
        row.changes.push(...changes);
        Object.assign(row,dominance(row.positive,row.negative));
        minutes.set(key,row);
      }
    }
    for(const [key,contract] of current)if(positive(contract.oi))previous.set(key,{x:report.x,oi:contract.oi});
  }

  return {policy:OPTION_OI_FLOW_POLICY,status:'AVAILABLE',reason:'',
    points:[...minutes.values()].sort((a,b)=>a.x-b.x||a.side.localeCompare(b.side)),
    reportCount:feed.reports.length,lastReportAt:priorTime};
}
