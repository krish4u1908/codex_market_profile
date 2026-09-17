// Port of prototype v0.1.3 build_raw_flow.py. Same causal computation for live
// snapshots and replay. These observations never alter the core reference call.
const MINUTE=60000;
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const empty=(reason,status='UNAVAILABLE')=>({status,reason,points:[],lastReportAt:null});
const median=values=>{const s=[...values].sort((a,b)=>a-b),i=s.length>>1;return s.length%2?s[i]:(s[i-1]+s[i])/2;};
// Python round uses ties-to-even on the exact binary float. Preserve it so
// activity ratios and pressure values match the supplied prototype CSV.
function round(v,n){
  const bits=new DataView(new ArrayBuffer(8));bits.setFloat64(0,Math.abs(v));
  const raw=bits.getBigUint64(0),exponent=Number((raw>>52n)&2047n);
  const mantissa=(raw&((1n<<52n)-1n))+(exponent?1n<<52n:0n);
  const shift=exponent?exponent-1023-52:-1074;
  let numerator=mantissa*10n**BigInt(n),denominator=1n;
  if(shift>=0)numerator<<=BigInt(shift);else denominator<<=BigInt(-shift);
  let quotient=numerator/denominator;const twice=2n*(numerator%denominator);
  if(twice>denominator||(twice===denominator&&quotient%2n))quotient++;
  return Math.sign(v)*Number(quotient)/10**n;
}

export function fixedRawBalance(ce,pe){
  if(!ce||!pe)return {v:null,state:'UNAVAILABLE'};
  const ct=ce.plus+ce.minus,pt=pe.plus+pe.minus;
  if(!ct||!pt)return {v:0,state:ct||pt?'ONE-SIDED / NO FLOW':'NO FLOW'};
  const cb=(ce.minus-ce.plus)/ct,pb=(pe.plus-pe.minus)/pt;
  if(cb>0&&pb>0)return {v:round(100*Math.min(cb,pb),2),state:'BULL FLOW'};
  if(cb<0&&pb<0)return {v:round(-100*Math.min(-cb,-pb),2),state:'BEAR FLOW'};
  return {v:0,state:cb===0||pb===0?'ONE LEG BALANCED':'MIXED LEGS'};
}

export function fixedPressure(data,feed){
  if(data.profile.instrument!=='NIFTY'||data.profile.version!=='2.0.0')return empty('', 'NOT_APPLICABLE');
  const selection=data.selection||{},ce=(selection.CE||[]).map(c=>c.symbol),pe=(selection.PE||[]).map(c=>c.symbol);
  if(ce.length!==4||pe.length!==4||new Set([...ce,...pe]).size!==8||selection.reference_close?.status!=='VALID_0945_NIFTY_CLOSE')
    return empty('Awaiting the verified 09:45 fixed four-strike basket.');
  if(!feed||feed.status!=='AVAILABLE')return empty(feed?.error||'Raw option-report receipts are unavailable.',feed?.status||'UNAVAILABLE');
  if(feed.schema!=='OPTION_REPORT_INPUTS_V1'||feed.instrument!=='NIFTY'||feed.session!==data.session||feed.source!=='OPTION_CHAIN_REPORT_QUOTES'||!Array.isArray(feed.reports))
    return empty('Option-report source, instrument or session does not match.', 'INVALID');
  const open=Date.parse(`${data.session}T09:15:00+05:30`),start=Date.parse(`${data.session}T09:46:00+05:30`),fiveStart=start+4*MINUTE,close=Date.parse(`${data.session}T15:30:00+05:30`);
  const selectedAt=Date.parse(selection.selected_at);
  if(!finite(selectedAt))return empty('The basket publication time is missing.');
  const minutes=new Map(),symbols=new Set([...ce,...pe]);
  let prior=-Infinity;
  for(const report of feed.reports){
    const x=report.x;
    if(!finite(x)||x<=prior||x<open||x>=close||!Array.isArray(report.contracts))return empty('Option reports must have ordered session receipt times.', 'INVALID');
    prior=x;
    const minute=Math.floor(x/MINUTE)*MINUTE;
    if(minutes.has(minute))continue; // Prototype takes the first receipt of each minute.
    const contracts=new Map();
    for(const c of report.contracts){
      if(!symbols.has(c.symbol))continue;
      if(contracts.has(c.symbol))return empty('Duplicate contract in an OI receipt.', 'INVALID');
      contracts.set(c.symbol,c.oi);
    }
    minutes.set(minute,{x,contracts});
  }
  function gross(minute,window,side){
    let plus=0,minus=0;
    for(let back=0;back<window;back++){
      const current=minutes.get(minute-back*MINUTE),prev=minutes.get(minute-(back+1)*MINUTE);
      if(!current||!prev)return null;
      for(const symbol of side){
        const a=current.contracts.get(symbol),b=prev.contracts.get(symbol);
        if(!finite(a)||!finite(b)||a<0||b<0)return null;
        const delta=a-b;plus+=Math.max(delta,0);minus+=Math.max(-delta,0);
      }
    }
    return {plus,minus};
  }
  const history={1:[],5:[]},points=[];
  for(const [minute,receipt] of minutes){
    if(receipt.x<start||receipt.x<selectedAt)continue;
    const row={x:receipt.x,source_x:receipt.x,raw1:null,raw5:null};
    for(const window of [1,5]){
      if(window===5&&receipt.x<fiveStart)continue;
      const c=gross(minute,window,ce),p=gross(minute,window,pe);
      if(!c||!p)continue;
      const activity=c.plus+c.minus+p.plus+p.minus,prior=history[window];
      const base=prior.length>=10?median(prior):null;
      const ratio=base>0?round(activity/base,3):null;
      row[`raw${window}`]={...fixedRawBalance(c,p),ce_plus:c.plus,ce_minus:c.minus,pe_plus:p.plus,pe_minus:p.minus,activity,
        activity_ratio:ratio,activity_quality:ratio==null?'BASELINE WARMING':ratio<.5?'THIN':ratio>=1.5?'ELEVATED':'TYPICAL'};
      prior.push(activity);if(prior.length>30)prior.shift();
    }
    points.push(row);
  }
  return {status:'AVAILABLE',reason:'',points,lastReportAt:prior===-Infinity?null:prior};
}
