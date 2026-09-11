import test from 'node:test';
import assert from 'node:assert/strict';
import {cashVixAt,validateIndicatorInputs,INDICATOR_INPUT_SCHEMA} from '../public/indicator-inputs.mjs';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt} from '../public/market-data.mjs';
import {v2,ms,day} from './fixtures.mjs';

function feed(instrument='NIFTY'){
  const revisions=Array.from({length:5},(_,i)=>({minute_ist:new Date(ms('09:15:00')+i*60000).toISOString(),
    minute_end:new Date(ms('09:16:00')+i*60000).toISOString(),available_at:new Date(ms('09:16:10')+i*60000).toISOString(),
    revision:1,vix_close:i===2?null:12+i/100,vix_valid:i!==2,cash_weighted_pct:i===2?null:i/10,cash_valid:i!==2}));
  return {schema:INDICATOR_INPUT_SCHEMA,instrument,session:day,status:'AVAILABLE',error:null,
    session_start:new Date(ms('09:15:00')).toISOString(),session_end:new Date(ms('15:30:00')).toISOString(),
    as_of:new Date(ms('09:20:30')).toISOString(),finalize_delay_seconds:8,
    revisions:[...revisions,{...revisions[2],available_at:new Date(ms('09:20:30')).toISOString(),revision:2,vix_close:12.02,vix_valid:true,cash_weighted_pct:.2,cash_valid:true}]};
}

test('late VIX data stays unavailable before arrival and rewinds without a future value',()=>{
  const f=feed(),source=JSON.stringify(f);
  const before=cashVixAt(f,ms('09:20:20')),after=cashVixAt(f,ms('09:20:30'));
  assert.equal(before.rows[2].vix_close,null);assert.equal(before.quality.missing,1);
  assert.equal(after.rows[2].vix_close,12.02);assert.equal(after.quality.missing,0);
  assert.equal(after.rows[2].x,ms('09:18:00'));
  assert.equal(after.rows.at(-1).cash_rolling_pct,.2);
  assert.equal(cashVixAt(f,ms('09:20:20')).rows[2].vix_close,null);
  assert.equal(JSON.stringify(f),source);
});

test('live knowledge can include a later repair; replay keeps the original availability clock',()=>{
  for(const instrument of ['NIFTY','BANKNIFTY']){
    const input=v2(instrument);input.indicator_inputs=feed(instrument);
    input.live={server_time:new Date(ms('09:20:30')).toISOString()};
    const data=normalizePayload(input,instrument.toLowerCase()+'-v200');
    assert.equal(frameAt(data,ms('09:20:20')).cash[2].vix_close,null);
    assert.equal(frameAt(data,ms('09:20:20'),{live:true}).cash[2].vix_close,12.02);
    assert.deepEqual(data.calls,normalizePayload({...input,indicator_inputs:undefined},instrument.toLowerCase()+'-v200').calls);
  }
});

test('missing source minutes remain explicit gaps; invalid VIX never becomes zero',()=>{
  const f=feed();f.revisions=f.revisions.filter(r=>r.minute_ist!==new Date(ms('09:16:00')).toISOString());
  f.revisions[0].vix_close=0;
  const view=cashVixAt(f,ms('09:20:30'));
  assert.equal(view.rows.length,5);assert.equal(view.rows[0].vix_close,null);assert.equal(view.rows[1].vix_close,null);
  assert.equal(view.rows.at(-1).cash_rolling_pct,null);
});

test('input identity errors and unavailable source quality remain visible',()=>{
  const f=feed();assert.throws(()=>validateIndicatorInputs(f,{instrument:'BANKNIFTY'},day),/identity/);
  f.status='SOURCE_UNAVAILABLE';f.error='retry';
  assert.equal(cashVixAt(f,ms('09:20:30')).quality.status,'SOURCE_UNAVAILABLE');
  assert.equal(cashVixAt(f,ms('09:20:20')).quality.status,'AS_OF_REPLAY');
});
