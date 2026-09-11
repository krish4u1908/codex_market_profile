import {snapshotSummary} from './market-data.mjs';
self.onmessage=event=>{
  const {id,frame}=event.data;
  try{self.postMessage({id,summary:snapshotSummary(frame)});}
  catch(error){self.postMessage({id,error:error.message||String(error)});}
};
