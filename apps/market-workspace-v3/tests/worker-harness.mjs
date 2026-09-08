import { parentPort, workerData } from 'node:worker_threads';
globalThis.self={postMessage:message=>parentPort.postMessage(message)};
if (workerData.module==='data') {
  const calls={};
  globalThis.fetch=async (url,options={})=>{
    const entries=workerData.sources[url];
    const n=calls[url]||0;calls[url]=n+1;
    const source=Array.isArray(entries)?entries[Math.min(n,entries.length-1)]:entries;
    if(!source) throw new Error('Unknown test source');
    await new Promise(resolve=>setTimeout(resolve,source.delay||0));
    if(source.error) throw new Error(source.error);
    if(source.expectedEtag && options.headers?.['If-None-Match']!==source.expectedEtag) throw new Error('Missing conditional request');
    return new Response([304,204].includes(source.status)?null:JSON.stringify(source.payload),{status:source.status||200,headers:source.headers});
  };
}
await import(workerData.module==='data'?'../public/data-worker.js':'../public/summary-worker.js');
parentPort.on('message',async message=>{
  if(workerData.delay) await new Promise(resolve=>setTimeout(resolve,workerData.delay));
  self.onmessage({data:message});
});
parentPort.postMessage({ready:true});
