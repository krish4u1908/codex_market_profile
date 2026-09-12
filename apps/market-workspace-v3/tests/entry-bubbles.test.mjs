import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt,summaryInput} from '../public/market-data.mjs';
import {nearOtmStrikes} from '../public/oi-entry-bubbles.mjs';
import {entryFixture} from './entry-fixtures.mjs';

function run(f){return normalizePayload(f.payload,`${f.payload.instrument.toLowerCase()}-v200`);}
function editOptions(f,edit){const rows=f.options.map(r=>({...r}));edit(rows);f.options=rows;
  f.payload.chart_inputs.option_strike_oi={...f.payload.chart_inputs.option_strike_oi,fields:Object.keys(rows[0]),rows:rows.map(Object.values)};}

test('strict near-OTM universe excludes exact ATM, ITM and the fourth OTM strike',()=>{
  assert.deepEqual(nearOtmStrikes(23300,50,'PE'),[23250,23200,23150]);
  assert.deepEqual(nearOtmStrikes(23300,50,'CE'),[23350,23400,23450]);
  assert.deepEqual(nearOtmStrikes(23331.8,50,'PE'),[23300,23250,23200]);
  assert.deepEqual(nearOtmStrikes(57450,100,'CE'),[57500,57600,57700]);
});

for(const instrument of ['NIFTY','BANKNIFTY'])for(const side of ['PE','CE'])test(`${instrument} ${side}: one bubble per report; exact availability, backward seek, unchanged calls`,()=>{
  const f=entryFixture(instrument,side),before=JSON.stringify(f.payload),data=run(f);
  assert.equal(data.entryAnalysis.events.length,1);
  const bubble=data.entryAnalysis.events[0];assert.equal(bubble.x,f.event);assert.equal(bubble.spikes.length,3);
  assert.equal(bubble.state,side==='PE'?'green':'red');assert.equal(bubble.direction,side==='PE'?'LONG':'SHORT');
  assert.equal(frameAt(data,f.event-1).entryBubbles.length,0);
  assert.equal(frameAt(data,f.event).entryBubbles.length,1);
  assert.equal(frameAt(data,f.event-1).entryBubbles.length,0);
  assert.deepEqual(frameAt(data,f.event,{live:true}).entryBubbles,frameAt(data,f.event).entryBubbles);
  assert.equal(JSON.stringify(f.payload),before);assert.equal(data.calls[0].direction,f.payload.decisions[0].corrected_direction);
  assert.ok(!Object.hasOwn(summaryInput(frameAt(data,f.event)),'entryBubbles'));
  assert.equal(data.options[0].x>=data.analysisStart,true); // UI flow warm-up unchanged.
  const prefix={...f,payload:structuredClone(f.payload)};prefix.payload.chart_inputs.option_strike_oi.rows=prefix.payload.chart_inputs.option_strike_oi.rows.filter(r=>Date.parse(r[0])<f.event);
  assert.equal(run(prefix).entryAnalysis.events.length,0);
});

test('short research policy accepts either VIX sign; long requires the rise',()=>{
  assert.equal(run(entryFixture('NIFTY','CE',{vixSign:1})).entryAnalysis.events.length,1);
  assert.equal(run(entryFixture('NIFTY','PE',{vixSign:-1})).entryAnalysis.events.length,0);
});

test('baseline excludes current spike, exact 1% threshold is included, smaller fall fails',()=>{
  for(const [fraction,expected] of [[.01,1],[.0099,0]]) {
    const f=entryFixture();editOptions(f,rows=>{for(const r of rows)if(Date.parse(r.t)===f.event){const prev=r.oi-r.d;r.oi=prev*(1-fraction);r.d=r.oi-prev;}});
    assert.equal(run(f).entryAnalysis.events.length,expected);
    if(expected)assert.ok(run(f).entryAnalysis.events[0].spikes[0].normalPct<.11);
  }
});

test('relative-size threshold rejects a 1% fall amid normal 0.5% changes',()=>{
  const f=entryFixture();editOptions(f,rows=>{
    const previous=new Map();for(const r of rows){const p=previous.get(r.symbol);r.oi=p?p*(Date.parse(r.t)===f.event?.99:1.005):100000;r.d=p?r.oi-p:null;previous.set(r.symbol,r.oi);}
  });assert.equal(run(f).entryAnalysis.events.length,0);
});

test('a spike on only the fourth OTM strike or another expiry cannot qualify',()=>{
  for(const change of ['far','expiry']) {
    const f=entryFixture();editOptions(f,rows=>{for(const r of rows){if(change==='far')r.s-=10*f.step;else r.e='2026-10-27';}});
    assert.equal(run(f).entryAnalysis.assessments.length,0);
  }
});

test('missing, null-delta, inconsistent and zero baselines do not manufacture spikes',()=>{
  for(const change of ['gap','null','inconsistent','zero']) {
    const f=entryFixture();editOptions(f,rows=>{
      if(change==='gap'){rows.splice(0,rows.length,...rows.filter(r=>!r.t.includes('04:21:55')));return;}
      for(const r of rows) {
        if(change==='null'&&Date.parse(r.t)===f.event)r.d=null;
        if(change==='inconsistent'&&Date.parse(r.t)===f.event)r.d=-1;
        if(change==='zero'){r.oi=Date.parse(r.t)===f.event?98000:100000;r.d=Date.parse(r.t)===f.event?-2000:0;}
      }
    });assert.equal(run(f).entryAnalysis.events.length,0,change);
  }
});

test('duplicate OI reports are counted once; price-refresh rows cannot generate extra entries',()=>{
  const f=entryFixture(),expected=run(f).entryAnalysis.events;
  editOptions(f,rows=>rows.push(...rows.map(r=>({...r}))));
  assert.deepEqual(run(f).entryAnalysis.events,expected);
});

test('a missing VIX minute and late VIX repair never backdate an entry',()=>{
  const missing=entryFixture();missing.payload.chart_inputs.cash_vix.splice(2,1);
  assert.equal(run(missing).entryAnalysis.events.length,0);
  const late=entryFixture();late.payload.chart_inputs.cash_vix.at(-1).t=late.iso(late.ms('10:05:08'));
  assert.equal(run(late).entryAnalysis.events.length,0);
});

test('premium rebound must be known at the VIX setup, not learned afterwards',()=>{
  const f=entryFixture();editOptions(f,rows=>{for(const r of rows)r.p=Date.parse(r.t)===f.event?200:100;});
  assert.equal(run(f).entryAnalysis.events.length,0);
});

test('context and cash must be available, fresh, and on the required side',()=>{
  for(const change of ['late','stale','trend','cash','cashPartial','priceStale']) {
    const f=entryFixture(),c=f.payload.decisions[0];
    if(change==='late')c.t=c.context_published_at=f.iso(f.event+1000);
    if(change==='stale')c.t=c.context_published_at=f.iso(f.event-120001);
    if(change==='trend')c.broader_leg=0;
    if(change==='cash')f.payload.chart_inputs.cash_vix.at(-1).cash_weighted_pct=-.2;
    if(change==='cashPartial')f.payload.chart_inputs.cash_vix.at(-1).cash_names=9;
    if(change==='priceStale')f.payload.chart_inputs.price=f.payload.chart_inputs.price.filter(r=>Date.parse(r.t)<f.event-15000);
    assert.equal(run(f).entryAnalysis.events.length,0,change);
  }
});

for(const instrument of ['NIFTY','BANKNIFTY'])for(const side of ['PE','CE'])test(`${instrument} ${side}: VPOC is manual context at any price relation or when unavailable`,()=>{
  for(const relation of ['below','equal','above','missing']) {
    const f=entryFixture(instrument,side),c=f.payload.decisions[0];
    c.volume_cumulative_mode_canonical=relation==='missing'?null:
      f.spot+(relation==='below'?-f.step:relation==='above'?f.step:0);
    const data=run(f);
    assert.equal(data.entryAnalysis.policy.id,'NEAR_OTM_OI_ENTRY_V2');
    assert.equal(data.entryAnalysis.policy.vpoc,'MANUAL_REVIEW_ONLY');
    assert.equal(data.entryAnalysis.events.length,1,relation);
    assert.equal(data.entryAnalysis.events[0].state,side==='PE'?'green':'red');
    for(const spike of data.entryAnalysis.events[0].spikes) {
      assert.equal(spike.vpoc,c.volume_cumulative_mode_canonical);
      assert.deepEqual(spike.reasons,[]);
    }
    assert.equal(frameAt(data,f.event-1).entryBubbles.length,0);
    assert.equal(frameAt(data,f.event).entryBubbles.length,1);
  }
});

test('future data does not change a past bubble or move it to an earlier VIX timestamp',()=>{
  const f=entryFixture(),expected=run(f).entryAnalysis.events;
  f.payload.decisions.push({...f.payload.decisions[0],t:f.iso(f.event+3000),context_published_at:f.iso(f.event+3000),broader_leg:-1});
  assert.deepEqual(run(f).entryAnalysis.events,expected);
  assert.ok(expected[0].spikes.every(s=>s.setup.at<expected[0].x));
});
