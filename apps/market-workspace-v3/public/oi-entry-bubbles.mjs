// Generic report-by-report display screen; no date/strike/timestamp calibration.
export const OI_ENTRY_POLICY=Object.freeze({id:'BASIC_OTM_OI_VIX_V2',strikesPerSide:3,
  minimumDropPct:1,spikeMultiple:3,baselineUpdates:20,maxOiGapMs:90000,vixThresholdPct:.4,
  vixSource:'OPTION_CHAIN_REPORT_QUOTES',vixWindow:'FIVE_MINUTE_SLOTS',analysisStart:'09:45',
  pePlacement:'ABOVE',cePlacement:'BELOW',
  colors:Object.freeze({PE_UP:'green',PE_DOWN:'yellow',CE_UP:'yellow',CE_DOWN:'red'})});
export const bubbleWatch=category=>category==='PE_UP'?'LONG_WATCH':category==='CE_DOWN'?'SHORT_WATCH':'RESEARCH';
const finite=n=>typeof n==='number'&&Number.isFinite(n),positive=n=>finite(n)&&n>0;
const median=values=>{const s=[...values].sort((a,b)=>a-b),m=s.length/2;return (s[m-1]+s[m])/2;};
export function nearOtmStrikes(spot,side,step) {
  if(!positive(spot)||!positive(step)||!['PE','CE'].includes(side))return [];
  const first=side==='PE'?Math.ceil(spot/step)-1:Math.floor(spot/step)+1;
  return Array.from({length:3},(_,i)=>step*(first+(side==='PE'?-i:i)));
}
export function oiEntryBubbles(data,feed) {
  const result={policy:OI_ENTRY_POLICY,status:'UNAVAILABLE',reason:'Raw option-report quotes unavailable. Update the core or import a replay with option_report_inputs.',events:[],assessments:[]};
  if(data.profile.version!=='2.0.0')return {...result,status:'NOT_APPLICABLE',reason:''};
  if(!feed)return result;
  if(feed.schema!=='OPTION_REPORT_INPUTS_V1'||feed.instrument!==data.profile.instrument||feed.session!==data.session)
    return {...result,status:'INVALID',reason:'Option-report instrument, session or schema does not match this replay.'};
  if(feed.status!=='AVAILABLE')return {...result,status:feed.status||'UNAVAILABLE',reason:feed.status==='PENDING'?'Loading option-report quotes…':feed.error||'Raw option reports are unavailable for this session.'};
  if(feed.source!=='OPTION_CHAIN_REPORT_QUOTES'||!Array.isArray(feed.reports))
    return {...result,status:'INVALID',reason:'Verified option-report quotes are required.'};
  const open=Date.parse(`${data.session}T09:15:00+05:30`),close=Date.parse(`${data.session}T15:30:00+05:30`),start=Date.parse(`${data.session}T09:45:00+05:30`);
  const step=data.profile.instrument==='NIFTY'?50:100,histories=new Map(),slots=new Map();
  let priorTime=-Infinity;
  for(const r of feed.reports) {
    if(!finite(r.x)||r.x<=priorTime||r.x<open||r.x>=close||!Array.isArray(r.contracts))
      return {...result,status:'INVALID',reason:'Option reports must have unique, ordered receipt times within this session.',events:[],assessments:[]};
    priorTime=r.x;
    const slot=Math.floor(r.x/60000);
    slots.set(slot,r);
    const seq=Array.from({length:6},(_,i)=>slots.get(slot-5+i));
    const validVix=seq.every(v=>v&&positive(v.vix))&&seq.slice(1).every((v,i)=>v.x>seq[i].x&&v.x-seq[i].x<=90000);
    const vixWindow=validVix?{fromAt:seq[0].x,from:seq[0].vix,to:r.vix,
      elapsedSeconds:(r.x-seq[0].x)/1000,changePct:100*(r.vix-seq[0].vix)/seq[0].vix}:null;
    const grouped={PE:[],CE:[]},seen=new Set();
    for(const c of r.contracts) {
      if(seen.has(c.symbol))return {...result,status:'INVALID',reason:'Duplicate option contract in a report.',events:[],assessments:[]};
      seen.add(c.symbol);
      if(!['PE','CE'].includes(c.side)||!positive(c.strike)||typeof c.symbol!=='string'||
         !new RegExp(`^NSE:${data.profile.instrument}\\d\\S*${c.side}$`).test(c.symbol))continue;
      const key=`${r.expiry}|${c.symbol}`,h=histories.get(key)||[];
      h.push({x:r.x,oi:c.oi});if(h.length>22)h.shift();histories.set(key,h);
      if(r.x<start||!nearOtmStrikes(r.spot,c.side,step).includes(c.strike)||h.length<22)continue;
      if(!h.every(v=>positive(v.oi))||h.slice(1).some((v,i)=>v.x<=h[i].x||v.x-h[i].x>90000))continue;
      const changes=h.slice(1).map((v,i)=>100*(h[i].oi-v.oi)/h[i].oi);
      const dropPct=changes.at(-1),normalPct=median(changes.slice(0,-1).map(Math.abs));
      if(dropPct<1-1e-10||normalPct<=0||dropPct/normalPct<3-1e-10)continue;
      grouped[c.side].push({side:c.side,symbol:c.symbol,strike:c.strike,oiFrom:h.at(-2).oi,oiTo:c.oi,
        dropPct,normalPct,multiple:dropPct/normalPct,index:r.spot});
    }
    for(const side of ['PE','CE'])if(grouped[side].length) {
      const eligible=vixWindow!==null&&Math.abs(vixWindow.changePct)>=.4-1e-10;
      const direction=vixWindow?(vixWindow.changePct>=0?'UP':'DOWN'):null;
      const category=direction?`${side}_${direction}`:null;
      const row={id:`${OI_ENTRY_POLICY.id}:${data.session}:${r.x}:${side}`,x:r.x,side,spikes:grouped[side],
        status:eligible?'MATCH':'OI_ONLY',category,spot:r.spot,expiry:r.expiry,
        vixDirection:direction,vixWindow,state:OI_ENTRY_POLICY.colors[category]||'yellow',
        watch:bubbleWatch(category),placement:side==='PE'?'ABOVE':'BELOW',
        reason:eligible?'':validVix?'VIX five-minute change below 0.4%':'Incomplete five-minute report-quote window'};
      result.assessments.push(row);if(eligible)result.events.push(row);
    }
  }
  return {...result,status:'AVAILABLE',reason:'',reportCount:feed.reports.length,lastReportAt:priorTime};
}
