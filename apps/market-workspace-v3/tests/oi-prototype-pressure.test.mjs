import test from 'node:test';
import assert from 'node:assert/strict';
import {fixedPressure,fixedRawBalance} from '../public/oi-fixed-pressure.mjs';
import {researchStep} from '../public/oi-research-replay.mjs';
const start=Date.parse('2026-09-15T09:45:55+05:30');
const data={profile:{instrument:'NIFTY',version:'2.0.0'},session:'2026-09-15',selection:{selected_at:new Date(start).toISOString(),reference_close:{status:'VALID_0945_NIFTY_CLOSE'},CE:[0,1,2,3].map(i=>({symbol:`C${i}`})),PE:[0,1,2,3].map(i=>({symbol:`P${i}`}))}};
const makeFeed=()=>({schema:'OPTION_REPORT_INPUTS_V1',instrument:'NIFTY',session:data.session,status:'AVAILABLE',source:'OPTION_CHAIN_REPORT_QUOTES',reports:Array.from({length:16},(_,i)=>({x:start+i*60000,contracts:[...data.selection.CE,...data.selection.PE].map(({symbol})=>({symbol,oi:1000+(symbol[0]==='C'?-i:i)*10}))}))});

test('raw pressure preserves prototype signs and distinguishes no flow from missing data',()=>{
 assert.deepEqual(fixedRawBalance({plus:0,minus:40},{plus:40,minus:0}),{v:100,state:'BULL FLOW'});
 assert.deepEqual(fixedRawBalance({plus:40,minus:0},{plus:0,minus:40}),{v:-100,state:'BEAR FLOW'});
 assert.deepEqual(fixedRawBalance({plus:40,minus:0},{plus:40,minus:0}),{v:0,state:'MIXED LEGS'});
 assert.deepEqual(fixedRawBalance({plus:0,minus:0},{plus:0,minus:0}),{v:0,state:'NO FLOW'});
 assert.equal(fixedRawBalance(null,{plus:1,minus:0}).v,null);
});
test('five-minute pressure sums gross reversals and starts only with five complete minutes',()=>{
 const feed=makeFeed();for(let i=0;i<feed.reports.length;i++)feed.reports[i].contracts.forEach(c=>c.oi=1000+(i%2?10:0));
 const points=fixedPressure(data,feed).points;
 assert.equal(points[0].raw5,null);assert.equal(points[3].raw5,null);
 assert.equal(points[4].raw5.ce_plus,120);assert.equal(points[4].raw5.ce_minus,80);
 assert.equal(points[4].raw5.pe_plus,120);assert.equal(points[4].raw5.pe_minus,80);
});
test('missing minute and missing individual OI create gaps, including every affected 5m window',()=>{
 const feed=makeFeed();feed.reports.splice(4,1);
 const result=fixedPressure(data,feed);assert.equal(result.points.find(p=>p.x===start+5*60000).raw1,null);
 assert.equal(result.points.find(p=>p.x===start+8*60000).raw5,null);
 assert.ok(result.points.find(p=>p.x===start+10*60000).raw5);
 const fresh=makeFeed();delete fresh.reports[5].contracts[0].oi;
 assert.equal(fixedPressure(data,fresh).points[4].raw1,null);
});
test('first receipt is stable when later same-minute reports arrive',()=>{
 const feed=makeFeed(),initial=fixedPressure(data,feed).points;
 const later=structuredClone(feed.reports[1]);later.x+=1000;later.contracts[0].oi=999999;
 feed.reports.splice(2,0,later);assert.deepEqual(fixedPressure(data,feed).points,initial);
});
test('live prefixes and replay prefixes match; prior activity baseline excludes current observation',()=>{
 const feed=makeFeed(),full=fixedPressure(data,feed).points;
 for(let i=1;i<feed.reports.length;i++)assert.deepEqual(fixedPressure(data,{...feed,reports:feed.reports.slice(0,i+1)}).points,full.slice(0,i));
 assert.equal(full[9].raw1.activity_ratio,null);assert.equal(full[10].raw1.activity_ratio,1);
 const original=structuredClone(full[10]);feed.reports[12].contracts.forEach(c=>c.oi*=20);
 assert.deepEqual(fixedPressure(data,feed).points[10],original);
});
test('unverified basket, wrong instrument and missing report feed cannot become a signal',()=>{
 assert.equal(fixedPressure({...data,selection:{}},makeFeed()).status,'UNAVAILABLE');
 assert.equal(fixedPressure(data,{...makeFeed(),instrument:'BANKNIFTY'}).status,'INVALID');
 assert.equal(fixedPressure(data,null).points.length,0);
 assert.equal(fixedPressure({...data,profile:{instrument:'BANKNIFTY',version:'2.0.0'}},makeFeed()).status,'NOT_APPLICABLE');
});
test('replay pauses at the first score publication crossed, including transitions to neutral',()=>{
 const rows=[0,35,0,-35].map((score,i)=>({score,x:start+i*60000,source_x:start+i*60000}));
 assert.deepEqual(researchStep(rows,start+30000,start+10*60000,true),{now:start+60000,paused:true});
 assert.deepEqual(researchStep(rows,start+60000,start+10*60000,true),{now:start+120000,paused:true});
 assert.deepEqual(researchStep(rows,start+30000,start+10*60000,false),{now:start+90000,paused:false});
 assert.equal(researchStep([{...rows[0]},{...rows[3]}],start+150000,start+10*60000,true).paused,false);
});
