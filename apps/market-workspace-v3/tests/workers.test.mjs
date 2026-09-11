import test from 'node:test';
import assert from 'node:assert/strict';
import { Worker } from 'node:worker_threads';
import { once } from 'node:events';
import { normalizePayload, frameAt, summaryInput } from '../public/market-data.mjs';
import { v1, ms } from './fixtures.mjs';

test('a delayed summary worker leaves replay free to advance and returns the original snapshot',async()=>{
  const worker=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'summary',delay:200}});
  try{
    await once(worker,'message');
    const data=normalizePayload(v1(),'banknifty-v1062'),frame=frameAt(data,ms('09:47:00'));
    const response=once(worker,'message');worker.postMessage({id:7,frame:summaryInput(frame)});
    let ticks=0;
    for(let i=0;i<3;i++){
      await new Promise(resolve=>setTimeout(resolve,10));
      assert.ok(frameAt(data,frame.now+(i+1)*60000).now>frame.now);ticks++;
    }
    assert.equal(ticks,3);const [result]=await response;assert.equal(result.summary.asOf,frame.now);
  }finally{await worker.terminate();}
});

test('a slow previous instrument load cannot replace a newer workspace load',async()=>{
  const worker=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'data',sources:{
    bank:{delay:150,payload:v1()},nifty:{payload:v1('NIFTY')},
  }}});
  try{
    await once(worker,'message');const messages=[];worker.on('message',m=>messages.push(m));
    const loaded=once(worker,'message');
    worker.postMessage({id:1,action:'load',url:'bank',profileId:'banknifty-v1062'});
    worker.postMessage({id:2,action:'load',url:'nifty',profileId:'nifty-v1062'});
    const [r]=await loaded;assert.equal(r.id,2);assert.equal(r.kind,'loaded');
    await new Promise(resolve=>setTimeout(resolve,200));
    const response=once(worker,'message');worker.postMessage({id:3,action:'frame',now:ms('10:00:00')});
    const [frame]=await response;assert.equal(frame.frame.profile.instrument,'NIFTY');
    assert.ok(!messages.some(m=>m.id===1&&m.kind==='loaded'));
  }finally{await worker.terminate();}
});
