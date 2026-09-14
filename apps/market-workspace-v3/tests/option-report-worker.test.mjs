import test from 'node:test';
import assert from 'node:assert/strict';
import {Worker} from 'node:worker_threads';
import {once} from 'node:events';
import {entryFixture} from './entry-fixtures.mjs';
function waitFor(w,kind,predicate=()=>true){return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{w.off('message',receive);reject(new Error('Timeout '+kind));},5000);
  function receive(m){if(m.kind===kind&&predicate(m)){clearTimeout(timer);w.off('message',receive);resolve(m);}}
  w.on('message',receive);
});}
test('replay panes work while quotes load; matching feed adds markers without moving cursor',async()=>{
  const f=entryFixture(),feed=f.payload.option_report_inputs;delete f.payload.option_report_inputs;
  const url='/api/replay?profile=nifty-v200&key=recorded-2026-09-11';
  const w=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{
    [url]:{payload:f.payload},'/api/option-report-inputs?profile=nifty-v200&session=2026-09-11':{delay:250,payload:feed}}}});
  try{
    await once(w,'message');const loaded=waitFor(w,'loaded');w.postMessage({id:1,action:'load',profileId:'nifty-v200',url});await loaded;
    const frame=waitFor(w,'frame',m=>m.frame.entryStatus.status==='PENDING');
    const added=waitFor(w,'frame',m=>m.frame.entryStatus.status==='AVAILABLE');
    w.postMessage({id:2,action:'frame',now:f.event});const pending=(await frame).frame;
    assert.equal(pending.entryBubbles.length,0);assert.equal(pending.optionOiFlowStatus.status,'PENDING');assert.equal(pending.optionOiFlow.length,0);
    const complete=await added;assert.equal(complete.id,2);assert.equal(complete.frame.now,f.event);assert.equal(complete.frame.entryBubbles.length,1);
    assert.equal(complete.frame.optionOiFlowStatus.status,'AVAILABLE');assert.ok(complete.frame.optionOiFlow.length>0);
  }finally{await w.terminate();}
});
test('switching sessions cancels a delayed report feed and cannot inject old bubbles',async()=>{
  const f=entryFixture(),feed=f.payload.option_report_inputs;delete f.payload.option_report_inputs;
  const url='/api/replay?profile=nifty-v200&key=recorded-2026-09-11';
  const w=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{
    [url]:{payload:f.payload},'/api/option-report-inputs?profile=nifty-v200&session=2026-09-11':{delay:250,payload:feed},other:{payload:f.payload}}}});
  try{
    await once(w,'message');let loaded=waitFor(w,'loaded');w.postMessage({id:1,action:'load',profileId:'nifty-v200',url});await loaded;
    loaded=waitFor(w,'loaded',m=>m.id===2);w.postMessage({id:2,action:'load',profileId:'nifty-v200',url:'other'});await loaded;
    await new Promise(r=>setTimeout(r,350));const result=waitFor(w,'frame');w.postMessage({id:3,action:'frame',now:f.event});
    const frame=(await result).frame;assert.equal(frame.entryBubbles.length,0);assert.equal(frame.optionOiFlow.length,0);
  }finally{await w.terminate();}
});
