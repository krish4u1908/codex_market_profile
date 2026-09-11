// Source-minute coordinates and availability clocks are deliberately separate.
export const INDICATOR_INPUT_SCHEMA='CASH_VIX_INDICATOR_INPUTS_V1';

export function validateIndicatorInputs(feed,profile,session){
  if(!feed)return null;
  if(feed.schema!==INDICATOR_INPUT_SCHEMA||feed.instrument!==profile.instrument||feed.session!==session)
    throw new Error('Cash/VIX input identity or schema mismatch.');
  const revisions=feed.revisions||[];
  for(const row of revisions){
    const minute=Date.parse(row.minute_ist),end=Date.parse(row.minute_end),available=Date.parse(row.available_at);
    if(!Number.isFinite(minute)||!Number.isFinite(end)||!Number.isFinite(available)||end!==minute+60000||
      new Date(minute+19800000).toISOString().slice(0,10)!==session||available<end||available>Date.parse(feed.as_of)||
      !Number.isInteger(row.revision)||row.revision<1)
      throw new Error('Invalid Cash/VIX input clocks or revision.');
  }
  return {...feed,revisions};
}

export function cashVixAt(feed,cutoff,knowledgeAt=cutoff){
  const selected=new Map();
  for(const row of feed.revisions){
    if(Date.parse(row.available_at)>knowledgeAt||Date.parse(row.minute_end)>cutoff)continue;
    const old=selected.get(row.minute_ist);
    if(!old||row.revision>old.revision)selected.set(row.minute_ist,row);
  }
  const rows=[...selected.values()].sort((a,b)=>Date.parse(a.minute_ist)-Date.parse(b.minute_ist)).map(row=>({
    ...row,x:Date.parse(row.minute_end),t:row.available_at,
    vix_close:row.vix_valid&&Number.isFinite(row.vix_close)&&row.vix_close>0?row.vix_close:null,
    cash_weighted_pct:row.cash_valid&&Number.isFinite(row.cash_weighted_pct)?row.cash_weighted_pct:null,
    cash_rolling_pct:null,
  }));
  // Explicit placeholders prevent short absent windows from being bridged.
  const byMinute=new Map(rows.map(row=>[row.x,row]));
  const completeUntil=Math.min(cutoff,knowledgeAt-(feed.finalize_delay_seconds??8)*1000,Date.parse(feed.session_end));
  const result=[];
  for(let end=Date.parse(feed.session_start)+60000;end<=completeUntil;end+=60000)
    result.push(byMinute.get(end)||{x:end,minute_ist:new Date(end-60000).toISOString(),vix_close:null,cash_weighted_pct:null,cash_rolling_pct:null,unavailable:true});
  for(let i=4;i<result.length;i++){
    const window=result.slice(i-4,i+1);
    if(window.every(r=>Number.isFinite(r.cash_weighted_pct)))
      result[i].cash_rolling_pct=window.reduce((sum,r)=>sum+r.cash_weighted_pct,0)/5;
  }
  const valid=result.filter(r=>Number.isFinite(r.vix_close)).length;
  const current=knowledgeAt>=Date.parse(feed.as_of||0);
  return {rows:result,quality:{verified:true,total:result.length,valid,missing:result.length-valid,
    status:current?feed.status:'AS_OF_REPLAY',error:current?feed.error:null,
    asOf:knowledgeAt,sourceTime:true}};
}
