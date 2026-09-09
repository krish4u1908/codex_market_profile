import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt} from '../public/market-data.mjs';
import {optionClimaxPoints} from '../public/v2-option-climax.mjs';
import {v1,v2,day,ms} from './fixtures.mjs';

const cutoff=i=>ms('10:00:00')+i*60000;
const iso=x=>new Date(x).toISOString();
function payload(instrument='BANKNIFTY') {
  const p=v2(instrument),base=p.decisions[0];
  p.decisions=Array.from({length:41},(_,i)=>({...base,index:instrument==='NIFTY'?24000+i:57400+i,
    t:iso(cutoff(i)+20000),context_published_at:iso(cutoff(i)+20000),input_cutoff:iso(cutoff(i)),
    ce_volume_5m:100,pe_volume_5m:100,ce_oi:120000,pe_oi:120000,
    ce_oi_additions_5m:200,ce_oi_reductions_5m:200,ce_oi_delta_5m:0,
    pe_oi_additions_5m:200,pe_oi_reductions_5m:200,pe_oi_delta_5m:0}));
  return p;
}
function peak(p,i=20){for(const side of ['ce','pe'])Object.assign(p.decisions[i],{
  [side+'_volume_5m']:250,[side+'_oi_additions_5m']:600,[side+'_oi_reductions_5m']:600});return p;}
const points=p=>normalizePayload(p,`${p.instrument.toLowerCase()}-v200`).optionClimaxes;

for(const instrument of ['BANKNIFTY','NIFTY'])test(`${instrument}: inclusive CE/PE thresholds, native price, availability and rewind`,()=>{
  const p=peak(payload(instrument)),original=JSON.stringify(p),data=normalizePayload(p,`${instrument.toLowerCase()}-v200`);
  const when=cutoff(20)+20000;
  assert.equal(frameAt(data,when-1).optionClimaxes.length,0);
  const first=frameAt(data,when).optionClimaxes;
  assert.equal(first.length,6);assert.ok(first.every(r=>r.isEpisodeStart&&r.x===when));
  assert.deepEqual(first.map(r=>r.ratio),[2.5,2.5,3,3,3,3]);
  assert.ok(first.filter(r=>r.metric!=='volume').every(r=>r.oiPercent===.5));
  assert.ok(first.every(r=>r.price===(instrument==='NIFTY'?24020:57420)));
  assert.equal(frameAt(data,when-1).optionClimaxes.length,0);
  assert.equal(JSON.stringify(p),original);
});

test('baseline uses the four exact previous five-minute cutoffs, excluding current and intervening minutes',()=>{
  const p=peak(payload());
  for(const i of [16,17,18,19])p.decisions[i].ce_volume_5m=10000;
  assert.equal(points(p).find(r=>r.key==='ce-volume'&&r.x===cutoff(20)+20000).ratio,2.5);
});

test('an OI ratio spike below the inventory size floor does not mark a climax',()=>{
  const p=peak(payload());
  p.decisions[20].ce_oi=120001;
  assert.ok(!points(p).some(r=>r.side==='CE'&&r.metric!=='volume'));
  assert.equal(points(p).filter(r=>r.side==='PE').length,3);
});

test('missing, zero or not-yet-published baselines do not create annotations',()=>{
  const missing=peak(payload());delete missing.decisions[5].ce_volume_5m;
  assert.ok(!points(missing).some(r=>r.key==='ce-volume'&&r.x===cutoff(20)+20000));
  const zero=peak(payload());for(const i of [0,5,10,15])zero.decisions[i].ce_volume_5m=0;
  assert.ok(!points(zero).some(r=>r.key==='ce-volume'&&r.x===cutoff(20)+20000));
  const late=peak(payload());late.decisions[5].context_published_at=iso(cutoff(21));
  assert.ok(!points(late).some(r=>r.x===cutoff(20)+20000));
});

test('coverage, OI reconciliation, basket changes and cross-session rows are checked independently',()=>{
  const p=peak(payload());p.decisions[20].ce_coverage=3;
  assert.ok(!points(p).some(r=>r.side==='CE'));
  const invalid=peak(payload());invalid.decisions[20].ce_oi_delta_5m=42;
  assert.ok(!points(invalid).some(r=>r.side==='CE'&&r.metric!=='volume'));
  const shifted=peak(payload());shifted.decisions[15].fixed_atm+=100;
  assert.equal(points(shifted).length,0);
  const different=peak(payload());different.decisions[5].session='2026-09-04';
  assert.ok(!points(different).some(r=>r.x===cutoff(20)+20000));
});

test('duplicates and reconstructed chart history cannot create extra or earlier events',()=>{
  const p=peak(payload());p.decisions.push({...p.decisions[20],context_published_at:iso(cutoff(20)+30000)});
  p.chart_history=Array.from({length:30},(_,i)=>({...p.decisions[20],t:iso(cutoff(i)),history_origin:'RECONSTRUCTED_INPUT_HISTORY'}));
  assert.equal(points(p).length,6);
  const reconstructed=peak(payload());reconstructed.decisions[20].history_origin='RECONSTRUCTED_INPUT_HISTORY';
  assert.equal(points(reconstructed).length,0);
});

test('burst starts remain immutable when later qualifying windows or higher peaks arrive',()=>{
  const p=payload();for(const i of [20,21,26,32])p.decisions[i].ce_volume_5m=250;
  const all=points(p).filter(r=>r.key==='ce-volume');
  assert.deepEqual(all.map(r=>r.isEpisodeStart),[true,false,false,true]);
  const truncated={...p,decisions:p.decisions.slice(0,22)};
  assert.deepEqual(points(truncated).filter(r=>r.key==='ce-volume'),all.slice(0,2));
  p.decisions[21].ce_volume_5m=9999;
  assert.deepEqual(points(p).find(r=>r.key==='ce-volume'),all[0]);
});

test('selection warm-up, missing price and v1.0.62 are handled without invented chart points',()=>{
  const p=peak(payload()),contexts=p.decisions.map(r=>({...r,x:Date.parse(r.context_published_at)}));
  assert.equal(optionClimaxPoints(contexts,[],day,{selected_at:iso(cutoff(0))}).length,0);
  for(const r of contexts)delete r.index;
  assert.ok(optionClimaxPoints(contexts,[],day).every(r=>r.price===null));
  assert.equal(frameAt(normalizePayload(v1(),'banknifty-v1062'),ms('10:00:00')).optionClimaxes.length,0);
});
