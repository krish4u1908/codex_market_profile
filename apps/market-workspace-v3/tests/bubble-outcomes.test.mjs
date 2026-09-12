import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluateLongOption,horizonOutcome,summarizeTrades} from '../research/bubble-outcomes.mjs';
const session='2026-09-10',at=Date.parse(session+'T11:15:55+05:30'),start=Date.parse(session+'T11:16:00+05:30');
const symbol='NSE:NIFTY2691523500CE';
const event={id:'sample',x:at,spot:23460,side:'PE',state:'green',watch:'LONG_WATCH',category:'PE_UP',expiry:'15-09-2026'};
const report={contracts:[{symbol,side:'CE',strike:23500},{symbol:'NSE:NIFTY2691523550CE',side:'CE',strike:23550}]};
const bar=(i,patch={})=>({x:start+i*60000,symbol,expiry:'2026-09-15',open:100,high:110,low:90,close:100,quotes:100,gap:0,anomalies:0,volume:10000,firstEventAt:start+i*60000,sourceRow:i+2,...patch});
const run=bars=>evaluateLongOption(event,'CE',report,bars,session);
test('20 premium-point target/stop use the next minute and lock the signal contract',()=>{
  assert.equal(run([bar(0),bar(1,{high:121})]).status,'TARGET');
  assert.equal(run([bar(0),bar(1,{low:79})]).status,'STOP');
  const result=run([bar(-1,{high:999}),bar(0),bar(1,{symbol:'NSE:NIFTY2691523550CE',high:999}),bar(1)]);
  assert.equal(result.status,'OPEN_AT_DATA_END');assert.equal(result.symbol,symbol);assert.equal(result.entryAt,start);
});
test('touching both barriers is ambiguous, while an opening gap resolves first',()=>{
  assert.equal(run([bar(0,{high:125,low:75})]).status,'AMBIGUOUS_BOTH');
  const stop=run([bar(0),bar(1,{open:70,low:65,high:130})]);assert.equal(stop.status,'STOP_GAP');assert.equal(stop.grossPoints,-30);
  const target=run([bar(0),bar(1,{open:130,high:140,low:70})]);assert.equal(target.status,'TARGET_GAP');assert.equal(target.grossPoints,20);
  const exact=run([bar(0,{open:70.1,low:50.1,high:80,close:70})]);assert.equal(exact.status,'STOP');assert.equal(exact.stopPrice,50.1);
});
test('missing and flagged minutes censor before a later apparent win',()=>{
  assert.equal(run([bar(0),bar(2,{high:130})]).status,'CENSORED_MISSING_MINUTE');
  assert.equal(run([bar(0),bar(1,{high:130,gap:1})]).status,'CENSORED_FEED_GAP');
  assert.equal(run([bar(0),bar(1,{high:130,anomalies:1})]).status,'CENSORED_TIMESTAMP_ANOMALY');
  assert.equal(run([bar(1)]).status,'NO_ENTRY_BAR');
  assert.equal(run([bar(0,{open:19,low:18,high:21,close:20})]).status,'ENTRY_PREMIUM_NOT_ABOVE_20');
  assert.equal(run([bar(0,{expiry:'2026-09-22'})]).status,'NO_ENTRY_BAR');
});
test('horizons use future report slots with explicit gaps, actual elapsed time and direction',()=>{
  const reports=Array.from({length:16},(_,i)=>({x:at+i*60000+(i%2?50:0),spot:23460+i}));
  for(const h of [5,10,15]) {const r=horizonOutcome(event,reports,h,session);assert.equal(r.changePoints,h);assert.equal(r.expectedDirectionPoints,h);}
  assert.equal(horizonOutcome(event,reports.slice(0,6),10,session).status,'NO_FUTURE_REPORT');
  assert.equal(horizonOutcome(event,reports.filter((_,i)=>i!==3),5,session).status,'REPORT_GAP');
});
test('summary excludes ambiguity and unresolved trades from decided win rate',()=>{
  const r=summarizeTrades([run([bar(0,{high:121})]),run([bar(0,{low:79})]),run([bar(0,{low:79,high:121})]),run([bar(0)])]);
  assert.equal(r.decidedWinRate,.5);assert.equal(r.ambiguous,1);assert.equal(r.unresolved,1);
  assert.equal(r.grossWithAmbiguousLower,-20);assert.equal(r.grossWithAmbiguousUpper,20);
});
