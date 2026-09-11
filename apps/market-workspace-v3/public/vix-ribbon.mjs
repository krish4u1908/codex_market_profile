// Display-only policy. Process observations in arrival order, including repairs.
export const VIX_RIBBON_POLICY=Object.freeze({
  id:'VIX_RIBBON_5M_PCT_V1',windowMs:300000,thresholdPct:.4,maxAgeMs:90000,
});
const finite=Number.isFinite,minuteMs=60000;

export function vixRibbonPoints(rows,session,{finalizeDelaySeconds=8,asOf=Infinity}={}) {
  const start=Date.parse(`${session}T09:15:00+05:30`),end=Date.parse(`${session}T15:30:00+05:30`);
  const delay=finite(finalizeDelaySeconds)&&finalizeDelaySeconds>=0?finalizeDelaySeconds*1000:8000;
  const events=rows.map(row=>{
    const minute=Date.parse(row.minute_ist),close=Date.parse(row.minute_end)||minute+minuteMs;
    const at=Math.max(Date.parse(row.available_at||row.first_observed_at||row.t),finite(row.x)?row.x:-Infinity);
    return {minute,close,at,revision:Number.isInteger(row.revision)?row.revision:at,
      vix:row.vix_valid!==false&&finite(row.vix_close)&&row.vix_close>0?row.vix_close:null};
  }).filter(r=>finite(r.minute)&&finite(r.at)&&r.minute>=start&&r.minute<end&&r.minute%minuteMs===0
    &&r.close===r.minute+minuteMs&&r.at>=r.close&&r.at<=asOf)
    .sort((a,b)=>a.at-b.at||a.close-b.close||a.revision-b.revision);
  const latest=new Map(),points=[];let previousKey='';
  for(let i=0;i<events.length;) {
    const at=events[i].at;
    // A batch is one observation: do not emit intermediate partial-batch marks.
    while(i<events.length&&events[i].at===at) {
      const row=events[i++],old=latest.get(row.close);
      if(!old||row.revision>old.revision)latest.set(row.close,row);
    }
    const close=Math.floor((at-delay)/minuteMs)*minuteMs;
    // Late historical repairs never become earlier intraday marks.
    if(close<=start||close>end)continue;
    const baseline=close-VIX_RIBBON_POLICY.windowMs;
    const window=Array.from({length:6},(_,n)=>latest.get(baseline+n*minuteMs));
    const key=JSON.stringify([close,...window.map(r=>r?.vix??null)]);
    if(key===previousKey)continue;previousKey=key;
    const point={x:at,minuteEnd:close,baselineEnd:baseline,from:null,to:null,changePct:null,
      state:'unavailable',reason:'Needs six consecutive one-minute VIX closes'};
    if(window.every(r=>r&&finite(r.vix))) {
      point.from=window[0].vix;point.to=window[5].vix;
      point.changePct=100*(point.to-point.from)/point.from;
      // Tolerance only covers binary rounding at the exact ±0.4% boundary.
      point.state=point.changePct>=VIX_RIBBON_POLICY.thresholdPct-1e-10?'red'
        :point.changePct<=-VIX_RIBBON_POLICY.thresholdPct+1e-10?'green':'neutral';
      point.reason='';
    }
    points.push(point);
  }
  return points;
}

export function latestVixRibbon(points,now) {
  const last=points.at(-1);
  return !last?null:now-last.x>VIX_RIBBON_POLICY.maxAgeMs
    ?{...last,state:'unavailable',changePct:null,reason:'No recent complete VIX window'}:last;
}
