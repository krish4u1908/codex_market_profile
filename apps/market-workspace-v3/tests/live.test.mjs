import test from 'node:test';
import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';
import { once } from 'node:events';
import { v1, ms } from './fixtures.mjs';
import { normalizePayload } from '../public/payload-adapters.mjs';
import { frameAt } from '../public/market-data.mjs';
import { validateWorkspaceConfig } from '../public/workspace-config.mjs';

function waitFor(worker,kind){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{worker.off('message',receive);reject(new Error('Timed out waiting for '+kind));},6000);
    function receive(m){if(m.kind===kind){clearTimeout(timer);worker.off('message',receive);resolve(m);}}
    worker.on('message',receive);
  });
}

test('live retries, conditional requests and new-day reset retain the correct frame',async()=>{
  const payload=v1();payload.live={server_time:'2026-09-03T10:01:00+05:30'};
  const worker=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{
    '/api/health':[
      {payload:{session:payload.session,status:'ready'}},{payload:{session:payload.session,status:'ready'}},
      {payload:{session:payload.session,status:'ready'}},{payload:{session:'2026-09-04',status:'waiting'}}],
    '/api/live?profile=banknifty-v1062':[
      {payload,headers:{ETag:'"snapshot-1"'}},{error:'temporary disconnect'},
      {status:304,expectedEtag:'"snapshot-1"'}, {status:503,payload:{waiting:true}}],
  }}});
  try{
    await once(worker,'message');
    const first=waitFor(worker,'live-frame');worker.postMessage({id:1,action:'live',profileId:'banknifty-v1062',interval:1000});
    const result=await first;assert.equal(result.frame.now,ms('10:01:00'));
    assert.match((await waitFor(worker,'live-error')).error,/disconnect/);
    assert.equal((await waitFor(worker,'live-connected')).health.session,payload.session);
    assert.equal((await waitFor(worker,'live-reset')).health.session,'2026-09-04');
  }finally{await worker.terminate();}
});

test('switching from a pending live request to replay cancels its result',async()=>{
  const worker=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{
    '/api/health':{payload:{session:'2026-09-03',status:'ready'}},
    '/api/live?profile=banknifty-v1062':{delay:200,payload:v1()},
    replay:{payload:v1()},
  }}});
  try{
    await once(worker,'message');const messages=[];worker.on('message',m=>messages.push(m));
    const status=waitFor(worker,'live-status');worker.postMessage({id:1,action:'live',profileId:'banknifty-v1062'});await status;
    const loaded=waitFor(worker,'loaded');worker.postMessage({id:2,action:'load',url:'replay',profileId:'banknifty-v1062'});
    assert.equal((await loaded).id,2);await new Promise(r=>setTimeout(r,250));
    assert.ok(!messages.some(m=>m.kind==='live-frame'));
    const frame=waitFor(worker,'frame');worker.postMessage({id:3,action:'frame',now:ms('09:47:00')});
    assert.equal((await frame).frame.now,ms('09:47:00'));
  }finally{await worker.terminate();}
});

test('instrument GUI configurations and late prior-context availability are enforced',()=>{
  assert.throws(()=>validateWorkspaceConfig({instrument:'NIFTY',profiles:['banknifty-v200'],defaultProfile:'banknifty-v200'}),/mixes instruments/);
  const payload=v1();payload.inventory_context={controls:[{family:'FUT_POS_OI_VPOC',scope:'PD',control_value:57400,status:'AVAILABLE',available_at:'2026-09-03T10:00:00+05:30'}]};
  const data=normalizePayload(payload,'banknifty-v1062');
  assert.equal(frameAt(data,ms('09:59:59')).prior.length,0);
  assert.equal(frameAt(data,ms('10:00:00')).prior.length,1);
});
