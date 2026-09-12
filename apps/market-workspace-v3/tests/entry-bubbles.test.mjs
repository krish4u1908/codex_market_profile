import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt,summaryInput} from '../public/market-data.mjs';
import {nearOtmStrikes,oiEntryBubbles} from '../public/oi-entry-bubbles.mjs';
import {entryFixture} from './entry-fixtures.mjs';
const run=f=>normalizePayload(f.payload,f.payload.instrument.toLowerCase()+'-v200');
for(const instrument of ['NIFTY','BANKNIFTY'])for(const side of ['PE','CE'])for(const vixSign of [1,-1]) {
  test(`${instrument} ${side} VIX ${vixSign}: receipt timing, position, colour and replay parity`,()=>{
    const f=entryFixture(instrument,side,{vixSign}),d=run(f),e=d.entryAnalysis.events;
    assert.equal(e.length,1);assert.equal(e[0].spikes.length,3);assert.equal(e[0].x,f.event);
    assert.equal(e[0].placement,side==='PE'?'ABOVE':'BELOW');
    assert.equal(e[0].state,side==='PE'&&vixSign>0?'green':side==='CE'&&vixSign<0?'red':'yellow');
    assert.equal(e[0].watch,side==='PE'&&vixSign>0?'LONG_WATCH':side==='CE'&&vixSign<0?'SHORT_WATCH':'RESEARCH');
    assert.equal(e[0].reason,'');
    assert.equal(frameAt(d,f.event-1).entryBubbles.length,0);assert.equal(frameAt(d,f.event).entryBubbles.length,1);
    assert.deepEqual(frameAt(d,f.event,{live:true}).entryBubbles,frameAt(d,f.event).entryBubbles);
    assert.equal(frameAt(d,f.event-1).entryBubbles.length,0);
    assert.ok(!Object.hasOwn(summaryInput(frameAt(d,f.event)),'entryBubbles'));
    f.payload.option_report_inputs.reports.pop();assert.equal(run(f).entryAnalysis.events.length,0);
  });
}
test('strict OTM selection excludes ATM and ITM for each index',()=>{
  assert.deepEqual(nearOtmStrikes(23500,'PE',50),[23450,23400,23350]);
  assert.deepEqual(nearOtmStrikes(23500,'CE',50),[23550,23600,23650]);
  assert.deepEqual(nearOtmStrikes(57451,'PE',100),[57400,57300,57200]);
  assert.deepEqual(nearOtmStrikes(57451,'CE',100),[57500,57600,57700]);
});
test('completed closes, VPOC, cash, price direction and native calls never gate basic bubbles',()=>{
  const f=entryFixture(),expected=run(f).entryAnalysis.events;
  f.payload.decisions=[];f.payload.chart_inputs.cash_vix=[];f.payload.chart_inputs.option_strike_oi={fields:[],rows:[]};
  for(const row of f.payload.chart_inputs.price){row.i=1;row.f=2;row.b=1;row.age=999999;}
  assert.deepEqual(run(f).entryAnalysis.events,expected);
});
test('OI uses previous 20 absolute percentage updates, excluding current, and inclusive thresholds',()=>{
  for(const [drop,vix,expected] of [[1,.4,1],[.9999,.4,0],[1,.3999,0]]) {
    const f=entryFixture(),r=f.payload.option_report_inputs.reports;
    r.forEach((row,i)=>row.contracts.forEach(c=>c.oi=i===25?100000*Math.pow(.998,24)*(1-drop/100):100000*Math.pow(.998,i)));
    r.at(-1).vix=100+vix;assert.equal(run(f).entryAnalysis.events.length,expected);
  }
  const f=entryFixture(),r=f.payload.option_report_inputs.reports;
  for(let i=0;i<25;i++)for(const c of r[i].contracts)c.oi=100000;
  r.at(-1).contracts.forEach(c=>c.oi=98000);assert.equal(run(f).entryAnalysis.events.length,0);
});
test('missing report, OI reset, expiry switch and absent quote fail closed',()=>{
  for(const mutate of [r=>r.splice(22,1),r=>r[10].contracts.forEach(c=>c.oi=0),r=>r.at(-1).expiry='different',r=>r.at(-1).vix=null]) {
    const f=entryFixture();mutate(f.payload.option_report_inputs.reports);assert.equal(run(f).entryAnalysis.events.length,0);
  }
});
test('report-minute slots tolerate millisecond jitter without using the six-minute quote',()=>{
  const f=entryFixture(),r=f.payload.option_report_inputs.reports;
  r[20].x+=278;r[25].x+=64;r[19].vix=120;
  const e=run(f).entryAnalysis.events;assert.equal(e.length,1);assert.equal(e[0].vixWindow.fromAt,r[20].x);
  assert.equal(e[0].vixWindow.changePct,.5);assert.ok(e[0].vixWindow.elapsedSeconds<300);
});
test('PE and CE at same timestamp and consecutive report matches are retained separately',()=>{
  const f=entryFixture('NIFTY','PE'),ce=entryFixture('NIFTY','CE',{vixSign:1}),r=f.payload.option_report_inputs.reports;
  r.forEach((v,i)=>v.contracts.push(...ce.payload.option_report_inputs.reports[i].contracts));
  const next=structuredClone(r.at(-1));next.x+=60000;next.contracts.forEach(c=>c.oi*=.98);r.push(next);
  const events=run(f).entryAnalysis.events;
  assert.equal(events.length,4);assert.equal(new Set(events.map(e=>e.id)).size,4);
  assert.deepEqual(events.slice(0,2).map(e=>e.side),['PE','CE']);
});
test('missing, cross-session, wrong instrument and unordered inputs have explicit status',()=>{
  for(const mutation of [f=>delete f.payload.option_report_inputs,f=>f.payload.option_report_inputs.session='2026-09-10',f=>f.payload.option_report_inputs.instrument='BANKNIFTY',f=>f.payload.option_report_inputs.reports.reverse()]) {
    const f=entryFixture();mutation(f);const a=run(f).entryAnalysis;assert.equal(a.events.length,0);assert.ok(a.reason);assert.notEqual(a.status,'AVAILABLE');
  }
});
test('every chronological prefix yields exactly the same marker set as full replay',()=>{
  const f=entryFixture(),d=run(f),r=f.payload.option_report_inputs.reports;
  for(let i=0;i<r.length;i++) {
    const limited=oiEntryBubbles(d,{...f.payload.option_report_inputs,reports:r.slice(0,i+1)});
    assert.deepEqual(limited.events,d.entryAnalysis.events.filter(e=>e.x<=r[i].x));
  }
});
