import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizePayload, validatePayload } from '../public/payload-adapters.mjs';
import { frameAt, chartPoints, withCumulativeOI, optionOIProfile, summaryInput, snapshotSummary } from '../public/market-data.mjs';
import { PROFILES } from '../public/profiles.mjs';
import { v1, v2, t, ms } from './fixtures.mjs';

for (const profile of Object.values(PROFILES)) test(`${profile.title}: causal frames, own instrument and immutable source calls`,()=>{
  const source=profile.version==='2.0.0'?v2(profile.instrument,{receipts:true}):v1(profile.instrument);
  const original=JSON.stringify(source),data=normalizePayload(source,profile.id);
  for(const now of [ms('09:44:59'),ms('09:46:07'),ms('09:47:00'),ms('09:48:08'),ms('09:48:09'),data.end]){
    const frame=frameAt(data,now);
    assert.equal(frame.profile.instrument,profile.instrument);
    for(const field of ['price','oi','cash','options','snapshots','controls','controlHistory','transitions']) {
      assert.ok(frame[field].every(row=>row.x<=now),field+' exposed a future row');
    }
    assert.ok(!frame.call||frame.call.x<=now);
    assert.ok(!frame.context||frame.context.x<=now);
  }
  const before=frameAt(data,ms('09:44:59'));
  assert.equal(before.call,null);assert.equal(before.selection.available,false);assert.equal(before.optionProfile.rows.length,0);
  const frame=frameAt(data,data.end);
  for(const [key,value] of Object.entries(source.directional_prediction?.[0]||source.decisions[0].baseline_call)){
    assert.deepEqual(frame.call[key],value,'Changed call field '+key);
  }
  assert.equal(frame.selection.CE[1].strike-frame.selection.CE[0].strike,profile.strikeStep);
  assert.equal(frame.range.high,profile.instrument==='NIFTY'?24040:57440);
  assert.equal(frame.basisRange.low,-4);assert.equal(frame.basisRange.high,7);
  assert.equal(JSON.stringify(source),original,'Adapter mutated the source');
});

test('V2 uses its enclosing publication time, preserves its native context and never synthesizes early calls',()=>{
  const payload=v2(),data=normalizePayload(payload,'banknifty-v200');
  assert.equal(frameAt(data,ms('09:48:08')).call,null);
  assert.equal(frameAt(data,ms('09:47:00')).context,null);
  assert.equal(frameAt(data,ms('09:47:00')).controls.length,0);
  const frame=frameAt(data,ms('09:48:09'));
  assert.equal(frame.call.x,ms('09:48:09'));assert.equal(frame.call.published_at,t('09:46:08'));
  assert.equal(frame.context.ce_oi_additions_5m,30);assert.equal(frame.controls.length,7);
  assert.equal(frame.snapshots.length,0);assert.equal(frame.capabilities.strikeReceipts,false);
  assert.equal(frame.oi.at(-1).cumPositive,null);assert.equal(frame.oi.at(-1).d,null);
});

test('missing or late VIX is never filled from the other index or a reconstructed source minute',()=>{
  const nifty=normalizePayload(v2('NIFTY'),'nifty-v200');
  assert.equal(frameAt(nifty,nifty.end).vixRange.high,null);
  const bank=normalizePayload(v2(),'banknifty-v200');
  assert.equal(frameAt(bank,ms('09:48:30')).vixRange.high,null);
  assert.equal(frameAt(bank,ms('09:49:00')).vixRange.high,11.2);
});

test('instrument, version and fixed strike grids are validated before loading',()=>{
  assert.throws(()=>normalizePayload(v1('BANKNIFTY'),'nifty-v1062'),/Instrument mismatch/);
  assert.throws(()=>normalizePayload(v2('NIFTY'),'banknifty-v200'),/Instrument mismatch/);
  assert.throws(()=>normalizePayload(v1(),'banknifty-v200'),/native version/);
  const disguised=v1();disguised.workspace_profile='nifty-v1062';
  assert.throws(()=>normalizePayload(disguised,'nifty-v1062'),/Instrument mismatch/);
  const wrongGrid=v1('NIFTY');wrongGrid.option_strike_oi.strike_selection.CE[1].strike+=25;
  assert.throws(()=>normalizePayload(wrongGrid,'nifty-v1062'),/strike grid/);
  const unknown=v2();delete unknown.instrument;
  assert.throws(()=>normalizePayload(unknown,'banknifty-v200'),/instrument identity/);
  assert.doesNotThrow(()=>validatePayload(unknown,'banknifty-v200',{allowUnidentified:true}));
});

test('receipt cumulative OI reconciles, excludes the initial balance and rewinds correctly',()=>{
  const data=normalizePayload(v1(),'banknifty-v1062'),early=frameAt(data,ms('09:46:59')),late=frameAt(data,data.end);
  for(const last of late.snapshots){
    assert.equal(last.cumPositive,30);assert.equal(last.cumNegative,-10);assert.equal(last.oi,100+30-10);
  }
  const future=late.oi.at(-1);
  assert.equal(future.oi,1000+future.cumPositive+future.cumNegative);
  assert.equal(future.d,-40);
  assert.deepEqual(frameAt(data,early.now).snapshots,early.snapshots);
  const rows=withCumulativeOI([{x:1,e:'A',symbol:'same',oi:100,d:null},{x:2,e:'A',symbol:'same',oi:150,d:null},
    {x:3,e:'B',symbol:'same',oi:500,d:350},{x:4,e:'B',symbol:'same',oi:510,d:10}],1);
  assert.equal(rows[1].cumPartial,true);assert.equal(rows[2].cumPositive,0);assert.equal(rows[3].cumPositive,10);
});

test('support and resistance use their own expiry, price side and available receipts',()=>{
  const row={e:'A',s:57400,k:'PE',x:1,oi:100,cumPositive:0,cumNegative:0};
  const p=optionOIProfile([row,{...row,s:57500,k:'CE',oi:200},{...row,s:57700,k:'PE',oi:99999},
    {...row,s:57600,k:'CE',x:3,oi:999999},{...row,s:57600,k:'CE',e:'B',oi:99999}],57450,'A',2);
  assert.equal(p.support,57400);assert.equal(p.resistance,57500);
});

test('VPOC persists between publications, while explicit missing levels and tick gaps remain gaps',()=>{
  assert.deepEqual(chartPoints([{x:1,v:100},{x:600001,v:100}],'v',true),[[1,100],[600001,100]]);
  assert.ok(chartPoints([{x:1,v:100},{x:600001,v:102}],'v').some(p=>p[1]===null));
  assert.deepEqual(chartPoints([{x:1,v:100},{x:600001,v:null}],'v',true).at(-1),[600001,null]);
  const data=normalizePayload(v1(),'banknifty-v1062');
  assert.equal(frameAt(data,ms('09:55:54')).controls[0].control_value,57400);
  assert.equal(frameAt(data,ms('09:55:55')).controls[0].control_value,57375);
});

test('summary messages exclude chart history and keep NIFTY identity and the saved explanation',()=>{
  const data=normalizePayload(v1('NIFTY'),'nifty-v1062'),frame=frameAt(data,data.end),before=JSON.stringify(frame);
  const input=summaryInput(frame),summary=snapshotSummary(input);
  assert.ok(!('options' in input));assert.ok(!('price' in input));assert.ok(!('controlHistory' in input));
  assert.equal(summary.invalidation,frame.call.invalidation);assert.ok(summary.facts[0].startsWith('Nifty 50'));
  assert.equal(JSON.stringify(frame),before);
});

test('V2 volume-climax markers use strictly >4, native publication time and the recorded ratio',async()=>{
  const {volumeRatioLabel}=await import('../public/v2-volume.mjs');
  const payload=v2();
  const base=payload.decisions[0];
  payload.decisions=[4,4.0001,5.25,null,-7,Number.NaN,Number.POSITIVE_INFINITY].map((ratio,index)=>({...base,
    t:t(`09:5${index}:09`),context_published_at:t(`09:5${index}:09`),index:57400+index,
    futures_volume_ratio:ratio}));
  payload.chart_history.push({t:t('09:47:00'),futures_volume_ratio:99,history_origin:'RECONSTRUCTED_INPUT_HISTORY'});
  const data=normalizePayload(payload,'banknifty-v200');
  assert.equal(frameAt(data,ms('09:51:08')).volumeClimaxes.length,0);
  const first=frameAt(data,ms('09:51:09')).volumeClimaxes;
  assert.equal(first.length,1);assert.equal(first[0].ratio,4.0001);assert.equal(first[0].x,ms('09:51:09'));assert.equal(first[0].price,57401);
  assert.equal(volumeRatioLabel(first[0].ratio),'4.0001×');
  const final=frameAt(data,data.end).volumeClimaxes;
  assert.deepEqual(final.map(r=>r.ratio),[4.0001,5.25]);
  assert.equal(frameAt(normalizePayload(v1(),'banknifty-v1062'),ms('10:00:00')).volumeClimaxes.length,0);
});
