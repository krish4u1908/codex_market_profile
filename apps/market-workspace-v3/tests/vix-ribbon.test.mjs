import test from 'node:test';
import assert from 'node:assert/strict';
import {vixRibbonPoints,latestVixRibbon} from '../public/vix-ribbon.mjs';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt,summaryInput} from '../public/market-data.mjs';
import {day,ms,v1,v2} from './fixtures.mjs';

const iso=x=>new Date(x).toISOString();
const rows=(values=[12,12.01,12.02,12.03,12.04,12.048])=>values.map((vix_close,i)=>({
  minute_ist:iso(ms('09:15:00')+i*60000),minute_end:iso(ms('09:16:00')+i*60000),
  available_at:iso(ms('09:16:08')+i*60000),revision:1,vix_close,vix_valid:vix_close!==null,
  cash_valid:false,cash_weighted_pct:null,
}));
const feed=(revisions,instrument)=>({schema:'CASH_VIX_INDICATOR_INPUTS_V1',instrument,session:day,
  session_start:iso(ms('09:15:00')),session_end:iso(ms('15:30:00')),
  as_of:iso(ms('20:00:00')),finalize_delay_seconds:8,status:'AVAILABLE',revisions});

test('five elapsed minutes use six closes and include exact +0.4% red and -0.4% green boundaries',()=>{
  for(const [close,state] of [[12.048,'red'],[11.952,'green'],[12.04799,'neutral'],[11.95201,'neutral'],[12,'neutral']]) {
    const points=vixRibbonPoints(rows([12,12,12,12,12,close]),day);
    assert.ok(points.slice(0,5).every(r=>r.state==='unavailable'));
    const p=points.at(-1);assert.equal(p.state,state);assert.equal(p.minuteEnd-p.baselineEnd,300000);
    assert.ok(Math.abs(p.changePct-100*(close-12)/12)<1e-10);
    assert.equal(p.x,ms('09:21:08'));assert.equal(p.from,12);assert.equal(p.to,close);
  }
});

test('missing minutes, nulls, invalid values and other-session baselines suppress marks; cash is independent',()=>{
  for(const missing of [null,0,NaN,Infinity,-1]) {
    const source=rows();source[2].vix_close=missing;
    assert.equal(vixRibbonPoints(source,day).at(-1).state,'unavailable');
  }
  assert.equal(vixRibbonPoints(rows().filter((_,i)=>i!==2),day).at(-1).state,'unavailable');
  const source=rows();source[2].vix_valid=false;
  assert.equal(vixRibbonPoints(source,day).at(-1).state,'unavailable');
  source[2]=rows()[2];source[0].minute_ist=iso(ms('09:15:00')-86400000);
  assert.equal(vixRibbonPoints(source,day).at(-1).state,'unavailable');
  assert.equal(vixRibbonPoints(rows(),day).at(-1).state,'red');
});

test('late repairs become marks at arrival and never fill earlier replay marks',()=>{
  const source=rows();source[2].vix_close=null;source[2].vix_valid=false;
  const repair={...rows()[2],available_at:iso(ms('09:21:30')),revision:2};
  const all=vixRibbonPoints([...source,repair],day);
  assert.equal(all.at(-2).state,'unavailable');assert.equal(all.at(-1).state,'red');
  assert.equal(all.at(-1).x,ms('09:21:30'));
  assert.deepEqual(all.filter(r=>r.x<ms('09:21:30')),vixRibbonPoints(source,day));
  assert.equal(vixRibbonPoints([...source,{...repair,available_at:iso(ms('19:00:00'))}],day).at(-1).state,'unavailable');
});

test('later corrections preserve earlier marks; cash-only revisions and repeats do not duplicate them',()=>{
  const source=rows(),original=JSON.stringify(source);
  const cashRepair={...source[5],available_at:iso(ms('09:21:20')),revision:2,cash_valid:true};
  const vixRepair={...source[5],available_at:iso(ms('09:21:30')),revision:3,vix_close:11.952};
  const all=vixRibbonPoints([...source,cashRepair,vixRepair],day);
  assert.equal(all.filter(r=>r.state==='red').length,1);assert.equal(all.at(-1).state,'green');
  assert.deepEqual(vixRibbonPoints([...source].reverse(),day),vixRibbonPoints(source,day));
  assert.deepEqual(vixRibbonPoints([...source,cashRepair,vixRepair],day,{asOf:ms('09:21:10')}),vixRibbonPoints(source,day));
  assert.equal(JSON.stringify(source),original);
  assert.equal(latestVixRibbon(all,ms('09:23:01')).state,'unavailable');
});

test('a batch yields one assessment, and stale windows are not presented as current',()=>{
  const batch=rows().map(r=>({...r,available_at:iso(ms('09:21:10'))}));
  assert.equal(vixRibbonPoints(batch,day).length,1);
  assert.equal(vixRibbonPoints(batch,day)[0].state,'red');
  assert.equal(vixRibbonPoints(rows().map(r=>({...r,available_at:iso(ms('09:23:10'))})),day)[0].state,'unavailable');
  assert.deepEqual(vixRibbonPoints(rows().map(r=>({...r,available_at:iso(ms('09:14:00'))})),day),[]);
});

for(const instrument of ['NIFTY','BANKNIFTY'])for(const version of ['v1062','v200'])test(`${instrument} ${version}: live/replay timing, native calls, legacy timestamps and compact summary`,()=>{
  const input=version==='v200'?v2(instrument):v1(instrument),profile=instrument.toLowerCase()+'-'+version;
  const before=JSON.stringify(input),originalCalls=normalizePayload(input,profile).calls;
  input.indicator_inputs=feed(rows(),instrument);input.live={server_time:iso(ms('09:21:30'))};
  const data=normalizePayload(input,profile);
  assert.equal(frameAt(data,ms('09:21:07')).vixRibbon.length,0);
  assert.equal(frameAt(data,ms('09:21:08')).vixRibbon.length,1);
  assert.deepEqual(frameAt(data,ms('09:21:08'),{live:true}).vixRibbon,frameAt(data,ms('09:21:08')).vixRibbon);
  assert.deepEqual(data.calls,originalCalls);assert.equal(frameAt(data,ms('09:21:07')).vixRibbon.length,0);
  assert.ok(!Object.hasOwn(summaryInput(frameAt(data,ms('09:21:08'))),'vixRibbon'));
  const legacy=JSON.parse(before),cash=rows().map(({available_at,revision,...r})=>({...r,t:available_at}));
  if(version==='v200')legacy.chart_inputs={cash_vix:cash};else legacy.cash_vix=cash;
  assert.equal(frameAt(normalizePayload(legacy,profile),ms('09:21:08')).vixRibbon[0].state,'red');
});
