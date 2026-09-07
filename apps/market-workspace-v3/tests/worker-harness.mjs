import { parentPort, workerData } from 'node:worker_threads';
globalThis.self={postMessage:message=>parentPort.postMessage(message)};
if (workerData.module==='data') {
  globalThis.fetch=async url=>{
    const source=workerData.sources[url];
    if(!source) throw new Error('Unknown test source');
    await new Promise(resolve=>setTimeout(resolve,source.delay||0));
    return new Response(JSON.stringify(source.payload));
  };
}
await import(workerData.module==='data'?'../public/data-worker.js':'../public/summary-worker.js');
parentPort.on('message',async message=>{
  if(workerData.delay) await new Promise(resolve=>setTimeout(resolve,workerData.delay));
  self.onmessage({data:message});
});
parentPort.postMessage({ready:true});
