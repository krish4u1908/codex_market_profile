// Research overlay only. Native calls, strategy state and orders are untouched.
import {atOrBefore} from './series.mjs';

export const OI_ENTRY_POLICY=Object.freeze({
  id:'NEAR_OTM_OI_ENTRY_V2',version:'research-2',strikesPerSide:3,
  minimumDropPct:1,spikeMultiple:3,baselineUpdates:20,
  setupLookbackMs:180000,premiumWindowMs:300000,maxOiGapMs:90000,
  maxPriceAgeMs:15000,maxContextAgeMs:90000,maxCashAgeMs:120000,
  vixThresholdPct:.4,longVix:'rise',shortVix:'either',
  vixSource:'CAUSAL_COMPLETED_MINUTE_CLOSES',vpoc:'MANUAL_REVIEW_ONLY',
});
const finite=Number.isFinite,positive=n=>finite(n)&&n>0;
const time=value=>typeof value==='number'?value:Date.parse(value);
const contract=row=>JSON.stringify([row.e,row.symbol,row.k,row.s]);
const median=values=>{const v=[...values].sort((a,b)=>a-b),n=v.length;return n%2?v[(n-1)/2]:(v[n/2-1]+v[n/2])/2;};

export function nearOtmStrikes(spot,step,side,count=3) {
  if(!positive(spot)||!positive(step)||!['PE','CE'].includes(side))return [];
  const first=side==='PE'?Math.ceil(spot/step)-1:Math.floor(spot/step)+1;
  return Array.from({length:count},(_,i)=>(first+(side==='PE'?-i:i))*step).filter(positive);
}

function historiesOf(options,start,end) {
  const histories=new Map();
  for(const raw of options) {
    const row={...raw,x:Math.max(time(raw.t),finite(raw.x)?raw.x:-Infinity,
      finite(time(raw.available_at))?time(raw.available_at):-Infinity)};
    if(!finite(row.x)||row.x<start||row.x>end||!row.symbol||!row.e||!['PE','CE'].includes(row.k)||!positive(row.s))continue;
    const key=contract(row);if(!histories.has(key))histories.set(key,[]);
    histories.get(key).push(row);
  }
  const batches=new Map();
  for(const [key,rows] of histories) {
    rows.sort((a,b)=>a.x-b.x);
    const clean=[],seen=new Set();
    for(const row of rows) {
      const id=row.event_id||String(row.x);
      if(seen.has(id))continue;seen.add(id);
      const previous=clean.at(-1);
      if(previous?.x===row.x) {
        if(previous.oi!==row.oi||previous.p!==row.p){previous.oi=null;previous.p=null;previous.d=null;}
        continue;
      }
      clean.push(row);
    }
    histories.set(key,clean);
    clean.forEach((row,index)=>{
      if(!batches.has(row.x))batches.set(row.x,[]);
      batches.get(row.x).push({row,index,history:clean});
    });
  }
  return [...batches].sort((a,b)=>a[0]-b[0]);
}

function oiDrop(history,index,policy) {
  if(index<policy.baselineUpdates+1)return null;
  const window=history.slice(index-policy.baselineUpdates-1,index+1),changes=[];
  for(let i=1;i<window.length;i++) {
    const previous=window[i-1],row=window[i];
    if(!positive(previous.oi)||!positive(row.oi)||!finite(row.d)||row.x<=previous.x||row.x-previous.x>policy.maxOiGapMs)return null;
    // Null/gap-flagged deltas are never replaced by a reconstructed spike.
    const actual=row.oi-previous.oi;
    if(Math.abs(actual-row.d)>Math.max(1e-7,Math.abs(actual)*1e-9))return null;
    changes.push(100*(previous.oi-row.oi)/previous.oi);
  }
  const dropPct=changes.at(-1),normalPct=median(changes.slice(0,-1).map(Math.abs));
  if(!(normalPct>0)||dropPct<policy.minimumDropPct-1e-10||dropPct/normalPct<policy.spikeMultiple-1e-10)return null;
  return {dropPct,normalPct,multiple:dropPct/normalPct,oiFrom:window.at(-2).oi,oiTo:window.at(-1).oi,
    previousOiAt:window.at(-2).x,baselineFrom:window[0].x,baselineTo:window.at(-2).x};
}

function premiumAt(history,at,policy) {
  const current=atOrBefore(history,at),baseline=atOrBefore(history,at-policy.premiumWindowMs);
  if(!current||!baseline||!positive(current.p)||!positive(baseline.p)||
    at-current.x>policy.maxOiGapMs||at-policy.premiumWindowMs-baseline.x>policy.maxOiGapMs)return null;
  // A missing premium receipt inside the five-minute window invalidates it.
  let previous=baseline;
  for(const row of history) {
    if(row.x<=baseline.x)continue;if(row.x>current.x)break;
    if(!positive(row.p)||row.x-previous.x>policy.maxOiGapMs)return null;
    previous=row;
  }
  return {changePct:100*(current.p-baseline.p)/baseline.p,from:baseline.p,to:current.p,
    fromAt:baseline.x,toAt:current.x};
}

function cashAt(data,feed,at,policy) {
  const rows=feed?.revisions||data.cash||[];let selected=null;
  for(const row of rows) {
    const available=time(row.available_at||row.first_observed_at||row.t);
    const end=time(row.minute_end)||time(row.minute_ist)+60000;
    if(!finite(available)||!finite(end)||available>at||end>at)continue;
    const revision=row.revision??available;
    if(!selected||end>selected.end||(end===selected.end&&revision>selected.revision))selected={row,end,available,revision};
  }
  if(!selected||at-selected.end>policy.maxCashAgeMs)return null;
  const row=selected.row;
  const complete=feed?row.cash_valid===true:row.expected_constituent_count>0&&row.cash_names===row.expected_constituent_count;
  if(!complete||!finite(row.cash_weighted_pct))return null;
  return {value:row.cash_weighted_pct,at:selected.available,minuteEnd:selected.end,
    names:row.cash_names,expected:row.expected_constituent_count};
}

function contextAt(data,feed,at,price,side,policy) {
  const c=atOrBefore(data.contexts,at),cash=cashAt(data,feed,at,policy),reasons=[];
  const direction=side==='PE'?1:-1;
  const current=c&&at-c.x<=policy.maxContextAgeMs&&finite(time(c.input_cutoff))&&at-time(c.input_cutoff)<=policy.maxCashAgeMs;
  if(!current)reasons.push('Fresh published V2 context unavailable');
  else if(c.broader_leg!==direction)reasons.push(side==='PE'?'Broader price trend is not UP':'Broader price trend is not DOWN');
  const vpoc=current&&positive(c.volume_cumulative_mode_canonical)?c.volume_cumulative_mode_canonical:null;
  // Retain the available VPOC for manual review; it never gates a bubble.
  if(!cash)reasons.push('Complete recent cash basket unavailable');
  else if(direction*cash.value<=0)reasons.push(side==='PE'?'Cash basket is not above its open':'Cash basket is not below its open');
  return {reasons,contextAt:c?.x??null,broaderLeg:current?c.broader_leg:null,vpoc,
    index:price.i,priceAt:price.x,cashPct:cash?.value??null,cashAt:cash?.at??null,cashNames:cash?.names??null};
}

function setupAt(history,vix,at,side,policy) {
  for(let i=vix.length-1;i>=0;i--) {
    const point=vix[i];if(point.x>at)continue;if(point.x<at-policy.setupLookbackMs)break;
    const change=point.changePct;
    if(!finite(change)||!finite(point.minuteEnd)||point.minuteEnd>point.x||point.x-point.minuteEnd>policy.maxCashAgeMs)continue;
    const rule=side==='PE'?policy.longVix:policy.shortVix;
    const accepted=rule==='rise'?change>=policy.vixThresholdPct-1e-10:
      rule==='fall'?change<=-policy.vixThresholdPct+1e-10:Math.abs(change)>=policy.vixThresholdPct-1e-10;
    if(!accepted)continue;
    const premium=premiumAt(history,point.x,policy);
    if(premium&&premium.changePct>0)return {at:point.x,vixChangePct:change,vixFrom:point.from,vixTo:point.to,
      vixMinuteEnd:point.minuteEnd,vixBaselineEnd:point.baselineEnd,premium};
  }
  return null;
}

export function oiEntryBubbles(data,options,vix,feed=null) {
  const policy=OI_ENTRY_POLICY,events=[],assessments=[];
  if(data.profile.version!=='2.0.0')return {events,assessments,policy};
  const start=time(`${data.session}T09:15:00+05:30`),end=time(`${data.session}T15:30:00+05:30`);
  const selectedAt=time(data.selection?.selected_at),expiry=data.selection?.expiry;
  if(!expiry||!finite(selectedAt)||data.selection?.available!==true)return {events,assessments,policy};
  for(const [at,batch] of historiesOf(options,start,end)) {
    if(at<Math.max(selectedAt,data.analysisStart))continue;
    const price=atOrBefore(data.price,at);
    if(!price||!positive(price.i)||at-price.x>policy.maxPriceAgeMs||
      (finite(price.age)&&price.age+at-price.x>policy.maxPriceAgeMs))continue;
    for(const side of ['PE','CE']) {
      const nearest=nearOtmStrikes(price.i,data.profile.strikeStep,side,policy.strikesPerSide);
      const spikes=[];
      for(const {row,index,history} of batch) {
        if(row.e!==expiry||row.k!==side||!nearest.includes(row.s))continue;
        const drop=oiDrop(history,index,policy);if(!drop)continue;
        const context=contextAt(data,feed,at,price,side,policy),setup=setupAt(history,vix,at,side,policy);
        const reasons=[...context.reasons];
        if(!setup)reasons.push(side==='PE'?'No recent VIX rise ≥0.4% with a PE premium rebound':
          'No recent VIX move ≥0.4% with a CE premium rebound');
        spikes.push({symbol:row.symbol,strike:row.s,expiry:row.e,side,...drop,...context,setup,reasons,
          eligible:reasons.length===0,reportId:row.event_id||String(at)});
      }
      if(!spikes.length)continue;
      const matches=spikes.filter(r=>r.eligible).sort((a,b)=>b.multiple-a.multiple),direction=side==='PE'?'LONG':'SHORT';
      const assessment={id:`${data.profile.instrument}:${data.session}:${direction}:${at}`,x:at,direction,side,
        status:matches.length?'ENTRY':'FILTERED',nearest,spikes,policy:policy.id};
      assessments.push(assessment);
      if(matches.length)events.push({...assessment,spikes:matches,state:direction==='LONG'?'green':'red',
        multiple:matches[0].multiple,dropPct:matches[0].dropPct,strike:matches[0].strike});
    }
  }
  return {events,assessments,policy};
}
