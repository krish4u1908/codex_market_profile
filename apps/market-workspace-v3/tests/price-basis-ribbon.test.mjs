import test from 'node:test';
import assert from 'node:assert/strict';
import {priceBasisRibbon,latestBasisRibbon,basisRibbonIntervals,sampleBasisRibbon} from '../public/price-basis-ribbon.mjs';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt,summaryInput} from '../public/market-data.mjs';
import {v1,v2,day,ms} from './fixtures.mjs';

const start=ms('10:00:00');
const row=(seconds,i,b)=>({x:start+seconds*1000,t:new Date(start+seconds*1000).toISOString(),i,b,f:i+b});
const trend=(priceStep=-10,basisStep=1)=>Array.from({length:8},(_,m)=>row(m*60,24000+m*priceStep,10+m*basisStep));

test('three-minute endpoint changes produce the requested green/red and neutral states',()=>{
  for(const [price,basis,state] of [[-10,1,'green'],[10,-1,'red'],[10,1,'neutral'],[-10,-1,'neutral'],[0,1,'neutral'],[-10,0,'neutral'],[0,0,'neutral']]) {
    const result=priceBasisRibbon(trend(price,basis),day);
    assert.ok(result.slice(0,3).every(p=>p.state==='unavailable'));
    assert.ok(result.slice(3).every(p=>p.state===state));
    assert.equal(result[3].priceChange,price*3);
    assert.equal(result[3].basisChange,basis*3);
    assert.equal(result[3].baselineAt,start);
  }
});

test('uses net changes over elapsed time, not three receipt rows or a monotonic path',()=>{
  const rows=[row(0,100,10),row(45,115,8),row(90,80,9),row(135,110,8),row(180,95,12)];
  const point=priceBasisRibbon(rows,day).at(-1);
  assert.equal(point.state,'green');assert.equal(point.priceChange,-5);assert.equal(point.basisChange,2);
});

test('baseline is at or before the three-minute cutoff and never a later receipt',()=>{
  const rows=[row(0,100,10),row(5,90,15),row(65,95,12),row(125,95,12),row(183,95,12)];
  const point=priceBasisRibbon(rows,day).at(-1);
  assert.equal(point.baselineAt,start);assert.equal(point.cutoff,start+3000);assert.equal(point.state,'green');
});

test('missing inputs and receipt gaps require fresh three-minute history; stale anchors are rejected',()=>{
  const missing=trend();missing[2].b=null;
  assert.ok(priceBasisRibbon(missing,day).slice(2,6).every(p=>p.state==='unavailable'));
  assert.equal(priceBasisRibbon(missing,day)[6].state,'green');
  const gap=trend().filter((_,i)=>i!==2);
  assert.ok(priceBasisRibbon(gap,day).filter(p=>p.x>=start+180000&&p.x<start+360000).every(p=>p.state==='unavailable'));
  assert.equal(priceBasisRibbon(gap,day).find(p=>p.x===start+360000).state,'green');
  const coarse=[row(0,100,10),row(90,99,11),row(180,98,12),row(260,97,13)];
  assert.equal(priceBasisRibbon(coarse,day).at(-1).state,'unavailable');
});

test('intraminute state changes survive display sampling and do not move to a later close',()=>{
  const points=[{x:start,state:'green'},{x:start+10000,state:'red'},{x:start+20000,state:'red'},
    {x:start+30000,state:'unavailable'},{x:start+45000,state:'unavailable'},{x:start+55000,state:'unavailable'}];
  const sampled=sampleBasisRibbon(points);
  assert.deepEqual(sampled.map(p=>p.x-start),[0,10000,30000,55000]);
  const spans=basisRibbonIntervals(sampled,start,start+60000);
  assert.deepEqual(spans.map(p=>[p.state,p.start-start,p.end-start]),[['green',0,10000],['red',10000,30000]]);
});

test('ribbon never extends into the future or across stale receipt time',()=>{
  const point=priceBasisRibbon(trend(),day).at(-1);
  const now=point.x+30000;
  assert.deepEqual(basisRibbonIntervals([point],point.x-1000,now).map(p=>[p.start,p.end]),[[point.x,now]]);
  assert.equal(basisRibbonIntervals([point],point.x,point.x).length,0);
  assert.equal(basisRibbonIntervals([point],point.x,point.x+300000)[0].end,point.x+90000);
  assert.equal(latestBasisRibbon([point],point.x+90001).state,'unavailable');
  assert.equal(latestBasisRibbon([point],now).state,'green');
});

for(const instrument of ['NIFTY','BANKNIFTY'])for(const version of ['v1062','v200'])test(`${instrument} ${version}: causal frame, rewind, no source mutation or summary payload growth`,()=>{
  const input=version==='v200'?v2(instrument):v1(instrument);
  const prices=trend().map(p=>({...p,i:p.i+(instrument==='BANKNIFTY'?33000:0)}));
  if(version==='v200')input.price_history=prices.map(p=>({t:p.t,index:p.i,basis:p.b}));
  else input.price=prices;
  const original=JSON.stringify(input),data=normalizePayload(input,`${instrument.toLowerCase()}-${version}`);
  assert.equal(frameAt(data,start+179999).basisRibbonLatest.state,'unavailable');
  const green=frameAt(data,start+180000);
  assert.equal(green.basisRibbonLatest.state,'green');
  assert.ok(green.basisRibbon.every(p=>p.x<=green.now));
  assert.ok(!Object.hasOwn(summaryInput(green),'basisRibbon'));
  assert.equal(frameAt(data,start+60000).basisRibbonLatest.state,'unavailable');
  const truncated={...input};
  if(version==='v200')truncated.price_history=input.price_history.slice(0,4);
  else truncated.price=input.price.slice(0,4);
  assert.deepEqual(frameAt(normalizePayload(truncated,`${instrument.toLowerCase()}-${version}`),start+180000).basisRibbon,green.basisRibbon);
  assert.equal(JSON.stringify(input),original);
});

test('another session and missing prices cannot provide the warm-up baseline',()=>{
  const previous={...row(0,100,10),x:ms('09:59:00')-86400000};
  const rows=[previous,...trend().slice(0,3)];
  assert.ok(priceBasisRibbon(rows,day).every(p=>p.state==='unavailable'&&p.x>=start));
  assert.deepEqual(priceBasisRibbon([],day),[]);
  assert.equal(latestBasisRibbon([],start),null);
});
