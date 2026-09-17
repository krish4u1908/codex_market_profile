import test from 'node:test';import assert from 'node:assert/strict';
import {Worker} from 'node:worker_threads';import {once} from 'node:events';import {gzipSync} from 'node:zlib';
import {pressureDirection,pressureQuantities,pressureReportVix} from '../public/pressure-direction.mjs';
import {normalizePayload} from '../public/payload-adapters.mjs';import {frameAt} from '../public/market-data.mjs';
const day='2026-08-24',start=Date.parse(day+'T09:50:05+05:30'),q=(cp,cm,pp,pm)=>({ce_plus:cp,ce_minus:cm,pe_plus:pp,pe_minus:pm});
const bull=q(0,40,60,0),bear=q(60,0,0,40),mixed=q(60,0,80,0),none=q(0,0,0,0);
const point=(i,raw5,raw1=raw5)=>({x:start+i*60000,raw1,raw5});
const run=rows=>pressureDirection(rows,day,start+20*60000).rows;
test('aligned 5m pressure needs 1m quantity agreement; neutral is distinct from missing',()=>{
 const rows=run([point(0,bull),point(1,bear),point(2,bull,bear),point(3,none),point(4,null)]);
 assert.deepEqual(rows.map(r=>r.direction),[1,-1,0,0,null]);assert.equal(rows[3].state,'NO FLOW');
 assert.equal(pressureQuantities(q(-1,0,0,0)),null);assert.equal(pressureQuantities({}),null);
});
test('bull-origin mixed episode needs negative 1m and falling 5m balance for a down reversal candidate',()=>{
 const rows=run([point(0,bull),point(1,mixed,bear),point(2,q(40,0,80,0),bear),point(3,mixed,bear),point(4,mixed,bull)]);
 assert.deepEqual(rows.map(r=>r.direction),[1,-1,0,-1,0]);assert.equal(rows[1].kind,'REVERSAL_CANDIDATE');assert.equal(rows[3].mixedOrigin,'BULL');
});
test('bear-origin mixed can flag up immediately; mixed without observed origin stays neutral',()=>{
 const rows=run([point(0,mixed,bull),point(1,bear),point(2,q(0,80,0,60),bull)]);
 assert.deepEqual(rows.map(r=>r.direction),[0,-1,1]);assert.equal(rows[2].mixedOrigin,'BEAR');
});
test('receipt gaps, incomplete windows and no-flow clear mixed-state memory',()=>{
 assert.equal(run([point(0,bull),point(2,mixed,bear)])[1].direction,0);
 assert.equal(run([point(0,bull),point(1,null),point(2,mixed,bear)])[2].direction,0);
 assert.equal(run([point(0,bull),point(1,none),point(2,mixed,bear)])[2].direction,0);
});
test('same current quantities can have a different direction depending on the preceding state',()=>{
 assert.equal(run([point(0,bull),point(1,mixed,bear)])[1].direction,-1);
 assert.equal(run([point(0,bear),point(1,mixed,bear)])[1].direction,0);
});
test('live prefixes and replay clock cutoffs produce identical past rows without future influence',()=>{
 const rows=[point(0,bull),point(1,mixed,bear),point(2,bear),point(3,mixed,bull)];
 for(let n=1;n<=rows.length;n++){
  const now=rows[n-1].x,full=pressureDirection(rows,day,now),prefix=pressureDirection(rows.slice(0,n),day,now);assert.deepEqual(full,prefix);assert.equal(full.rows.length,n);
 }
});
test('before 09:50, after 15:00 and stale receipts never display a current directional hypothesis',()=>{
 const rows=[point(0,bull)];assert.equal(pressureDirection(rows,day,start-1).rows.length,0);
 assert.equal(pressureDirection(rows,day,start).latest.label,'UP');assert.equal(pressureDirection(rows,day,start+90001).latest,null);
 const end=Date.parse(day+'T15:00:00+05:30');assert.equal(pressureDirection([...rows,{...point(0,bull),x:end}],day,end).rows.length,1);
});
function fixture(){
 const ms=t=>Date.parse(`${day}T${t}+05:30`),symbols=['C0','C1','C2','C3','P0','P1','P2','P3'];
 const selection={selected_at:new Date(ms('09:45:00')).toISOString(),expiry:'25-08-2026',reference_close:{status:'VALID_0945_NIFTY_CLOSE'},CE:symbols.slice(0,4).map(symbol=>({symbol,strike:23000})),PE:symbols.slice(4).map(symbol=>({symbol,strike:23000}))};
 const reports=Array.from({length:36},(_,i)=>({x:ms('09:30:05')+i*60000,vix:13+i/100,contracts:symbols.map((symbol,k)=>({symbol,oi:100000+(k<4?-1:1)*i*100}))}));
 const price=Array.from({length:1801},(_,i)=>({x:ms('09:35:00')+i*1000,i:23000+i/100,b:30,f:23030+i/100}));
 const feed={schema:'OPTION_REPORT_INPUTS_V1',source:'OPTION_CHAIN_REPORT_QUOTES',instrument:'NIFTY',session:day,status:'AVAILABLE',reports};
 const payload={version:'2.0.0',baseline_version:'1.0.62',instrument:'NIFTY',session:day,decisions:[],chart_inputs:{price,option_strike_oi:{fields:[],rows:[],strike_selection:selection}},option_report_inputs:feed};
 return {payload,feed,ms,data:normalizePayload(payload,'nifty-v200')};
}
test('earliest old study sessions support direction without any trained model; frame respects knowledge time',()=>{
 const {data,ms}=fixture();const frame=frameAt(data,ms('10:00:30'));assert.equal(frame.pressureDirection.latest.label,'UP');assert.ok(!('oiQuantityModel' in frame));
 data.liveKnowledgeAt=ms('09:55:30');const live=frameAt(data,ms('10:00:30'),{live:true});assert.ok(live.pressureDirection.rows.every(r=>r.x<=data.liveKnowledgeAt));
 assert.ok(live.oiDirectionVix.every(r=>r.x<=data.liveKnowledgeAt));assert.equal(live.pressureDirection.latest.label,'UP');
});
test('direction is independent of price, VIX and model probabilities',()=>{
 const {payload,ms}=fixture();const a=frameAt(normalizePayload(payload,'nifty-v200'),ms('10:00:30')).pressureDirection;
 payload.chart_inputs.price.forEach(r=>{r.i=9999;r.f=10000;r.b=1;});payload.option_report_inputs.reports.forEach(r=>r.vix=90);
 const b=frameAt(normalizePayload(payload,'nifty-v200'),ms('10:00:30')).pressureDirection;assert.deepEqual(a,b);
});
test('archived VIX source identity is checked independently',()=>{
 const {data,feed}=fixture();assert.ok(pressureReportVix(data,feed).length>0);assert.equal(pressureReportVix(data,{...feed,session:'2026-08-25'}).length,0);
});
function waitFor(w,kind,predicate=()=>true){return new Promise((resolve,reject)=>{const t=setTimeout(()=>{w.off('message',receive);reject(new Error('Timeout '+kind));},5000);function receive(m){if(m.kind===kind&&predicate(m)){clearTimeout(t);w.off('message',receive);resolve(m);}}w.on('message',receive);});}
test('old catalog replay archive enrichment adds independent direction without moving the replay cursor',async()=>{
 const {payload,feed,ms}=fixture();delete payload.option_report_inputs;const url='/api/replay?profile=nifty-v200&key=recorded-2026-08-24';
 const w=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{[url]:{payload},'/api/option-report-inputs?profile=nifty-v200&session=2026-08-24':{delay:150,payload:feed}}}});
 try{await once(w,'message');const loaded=waitFor(w,'loaded');w.postMessage({id:1,action:'load',profileId:'nifty-v200',url});await loaded;
 const result=waitFor(w,'frame',m=>m.frame.pressureDirection.latest);w.postMessage({id:2,action:'frame',now:ms('10:00:30')});const {frame}=await result;assert.equal(frame.now,ms('10:00:30'));assert.equal(frame.pressureDirection.latest.label,'UP');
 }finally{await w.terminate();}
});
test('old JSON.gz imports support direction without a model or server archive',async()=>{
 const {payload,ms}=fixture();const w=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{}}});
 try{await once(w,'message');const loaded=waitFor(w,'loaded');w.postMessage({id:1,action:'file',profileId:'nifty-v200',file:new Blob([gzipSync(JSON.stringify(payload))])});await loaded;
 const result=waitFor(w,'frame');w.postMessage({id:2,action:'frame',now:ms('10:00:30')});const {frame}=await result;assert.equal(frame.pressureDirection.latest.label,'UP');assert.ok(!('oiQuantityModel' in frame));
 }finally{await w.terminate();}
});
