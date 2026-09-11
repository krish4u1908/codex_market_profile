import {validatePreview} from './display-preview.mjs';
let generation=0,timer=null,controller=null;
function stop(){generation++;clearTimeout(timer);controller?.abort();}
self.onmessage=event=>{
  stop();
  const {action,instrument}=event.data;
  if(action!=='start')return;
  const active=generation;
  async function poll(){
    const request=new AbortController();controller=request;
    const timeout=setTimeout(()=>request.abort(),3000);
    try{
      const response=await fetch('/api/display-preview',{cache:'no-store',signal:request.signal});
      if(!response.ok)throw new Error('Preview reader unavailable');
      const candidate=validatePreview(await response.json(),instrument);
      if(!candidate)throw new Error('Waiting for preview data');
      if(active===generation)self.postMessage({kind:'preview',data:candidate});
    }catch(error){
      if(active===generation)self.postMessage({kind:'preview-error',error:'Incoming feed unavailable; confirmed charts remain available.'});
    }finally{
      clearTimeout(timeout);
      if(active===generation)timer=setTimeout(poll,1000);
    }
  }
  void poll();
};
