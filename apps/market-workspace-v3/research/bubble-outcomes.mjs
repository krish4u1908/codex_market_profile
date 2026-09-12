// Retrospective outcome evaluation. Never imported by a live/replay detector.
import {nearOtmStrikes} from '../public/oi-entry-bubbles.mjs';
export const OUTCOME_POLICY=Object.freeze({id:'OI_VIX_OUTCOMES_V1',horizons:[5,10,15],
  contract:'NEAREST_STRICT_OTM_AT_SIGNAL_SAME_EXPIRY',entry:'NEXT_MINUTE_LTP_OPEN',
  position:'BUY',targetPoints:20,stopPoints:20,ambiguous:'RETAIN_BOTH_POSSIBILITIES',
  unresolved:'CENSOR_AT_DATA_END',costs:'EXCLUDED',observations:'INDEPENDENT_OVERLAPPING_EVENTS'});
const minute=60000,good=n=>typeof n==='number'&&Number.isFinite(n),pos=n=>good(n)&&n>0;
const price2=n=>Math.round((n+Number.EPSILON)*100)/100;
export const isoIST=x=>new Date(x+19800000).toISOString().replace('Z','+05:30');
export function expiryISO(expiry) {
  if(/^\d{4}-\d{2}-\d{2}$/.test(expiry))return expiry;
  const m=/^(\d{2})-(\d{2})-(\d{4})$/.exec(expiry||'');
  return m?`${m[3]}-${m[2]}-${m[1]}`:null;
}
export function phaseAt(x,session) {
  return x<Date.parse(`${session}T15:15:00+05:30`)?'CONTINUOUS':'CAS_PERIOD';
}
export function horizonOutcome(event,reports,horizon,session) {
  const slot=Math.floor(event.x/minute),bySlot=new Map();
  for(const r of reports)bySlot.set(Math.floor(r.x/minute),r);
  const seq=[{x:event.x,spot:event.spot},...Array.from({length:horizon},(_,i)=>bySlot.get(slot+i+1))];
  const targetAt=(slot+horizon)*minute,base={minutes:horizon,targetSlotAt:targetAt};
  if(!seq.at(-1))return {...base,status:'NO_FUTURE_REPORT'};
  if(seq.some(r=>!r||!pos(r.spot))||seq.slice(1).some((r,i)=>r.x-seq[i].x>90000))
    return {...base,status:'REPORT_GAP'};
  const to=seq.at(-1),changes=seq.map(r=>r.spot-event.spot),change=to.spot-event.spot;
  return {...base,status:'AVAILABLE',from:event.spot,to:to.spot,at:to.x,
    elapsedSeconds:(to.x-event.x)/1000,changePoints:change,changePct:100*change/event.spot,
    expectedDirectionPoints:event.watch==='LONG_WATCH'?change:event.watch==='SHORT_WATCH'?-change:null,
    sampledMaxUp:Math.max(...changes),sampledMaxDown:Math.min(...changes),
    phase:phaseAt(event.x,session)===phaseAt(to.x,session)?phaseAt(to.x,session):'CROSSES_CAS'};
}
export function candleProblem(b) {
  if(!b||![b.open,b.high,b.low,b.close].every(pos)||b.low>Math.min(b.open,b.close)||b.high<Math.max(b.open,b.close)||b.low>b.high)return 'INVALID_OHLC';
  if(!(b.quotes>0))return 'NO_QUOTES';
  if(b.gap!==0)return 'FEED_GAP';
  if(b.anomalies!==0)return 'TIMESTAMP_ANOMALY';
  return null;
}
export function evaluateLongOption(event,side,report,allBars,session) {
  const firstMinute=(Math.floor(event.x/minute)+1)*minute,expiry=expiryISO(event.expiry);
  const strike=nearOtmStrikes(event.spot,side,50)[0];
  const contracts=(report?.contracts||[]).filter(c=>c.side===side&&c.strike===strike);
  const base={eventId:event.id,category:event.category,color:event.state,watch:event.watch,signalAt:event.x,
    session,side,strike,expiry,phase:phaseAt(event.x,session),expiryDay:expiry===session,
    entryAt:firstMinute,position:'BUY',targetPoints:20,stopPoints:20};
  if(contracts.length!==1||!expiry)return {...base,status:'NO_UNIQUE_CONTRACT'};
  const symbol=contracts[0].symbol,closeAt=Date.parse(`${session}T15:40:00+05:30`);
  const bars=allBars.filter(b=>b.symbol===symbol&&b.expiry===expiry&&b.x>=firstMinute&&b.x<closeAt).sort((a,b)=>a.x-b.x);
  if(!bars.length||bars[0].x!==firstMinute)return {...base,symbol,status:'NO_ENTRY_BAR'};
  const first=bars[0],problem=candleProblem(first);
  if(problem||!(first.volume>0))return {...base,symbol,status:'ENTRY_'+(problem||'NO_VOLUME'),entrySourceRow:first.sourceRow};
  if(!good(first.firstEventAt)||first.firstEventAt<firstMinute||first.firstEventAt>=firstMinute+minute)
    return {...base,symbol,status:'ENTRY_TIMESTAMP_INVALID'};
  const entry=first.open,stop=price2(entry-20),target=price2(entry+20);
  if(stop<=0)return {...base,symbol,entryPrice:entry,status:'ENTRY_PREMIUM_NOT_ABOVE_20'};
  const started={...base,symbol,entryPrice:entry,stopPrice:stop,targetPrice:target,
    entrySourceRow:first.sourceRow,entryFirstEventAt:first.firstEventAt};
  let previous=firstMinute-minute,lastClose=entry,lastAt=firstMinute;
  for(const b of bars) {
    const problem=candleProblem(b);
    if(b.x!==previous+minute||problem)return {...started,status:'CENSORED_'+(problem||'MISSING_MINUTE'),
      censoredAt:b.x,lastAt,lastPrice:lastClose,unrealizedPoints:price2(lastClose-entry)};
    previous=b.x;
    const ended={...started,exitBarAt:b.x,exitSourceRow:b.sourceRow,
      minHoldingMinutes:(b.x-firstMinute)/minute,maxHoldingMinutes:(b.x-firstMinute)/minute+1};
    // The open precedes the bar's extrema, so a gap resolves before intrabar ambiguity.
    if(b.open<=stop)return {...ended,status:'STOP_GAP',exitPrice:b.open,grossPoints:price2(b.open-entry)};
    if(b.open>=target)return {...ended,status:'TARGET_GAP',exitPrice:target,grossPoints:20};
    if(b.low<=stop&&b.high>=target)return {...ended,status:'AMBIGUOUS_BOTH',grossLower:-20,grossUpper:20};
    if(b.low<=stop)return {...ended,status:'STOP',exitPrice:stop,grossPoints:-20};
    if(b.high>=target)return {...ended,status:'TARGET',exitPrice:target,grossPoints:20};
    lastClose=b.close;lastAt=b.x;
  }
  return {...started,status:'OPEN_AT_DATA_END',lastAt,lastPrice:lastClose,unrealizedPoints:price2(lastClose-entry)};
}
export function summarizeTrades(rows) {
  const statusCounts=Object.fromEntries([...new Set(rows.map(r=>r.status))].sort().map(s=>[s,rows.filter(r=>r.status===s).length]));
  const wins=rows.filter(r=>r.status==='TARGET'||r.status==='TARGET_GAP').length;
  const losses=rows.filter(r=>r.status==='STOP'||r.status==='STOP_GAP').length;
  const ambiguous=rows.filter(r=>r.status==='AMBIGUOUS_BOTH').length;
  const resolved=rows.filter(r=>good(r.grossPoints)),gross=resolved.reduce((a,r)=>a+r.grossPoints,0);
  return {observations:rows.length,entered:rows.filter(r=>pos(r.stopPrice)).length,wins,losses,ambiguous,
    unresolved:rows.filter(r=>r.status==='OPEN_AT_DATA_END'||r.status.startsWith('CENSORED_')).length,
    notEntered:rows.filter(r=>!pos(r.stopPrice)).length,
    decidedWinRate:wins+losses?wins/(wins+losses):null,grossResolvedPoints:gross,
    grossWithAmbiguousLower:gross-20*ambiguous,grossWithAmbiguousUpper:gross+20*ambiguous,statusCounts};
}
