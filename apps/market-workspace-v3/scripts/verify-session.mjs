#!/usr/bin/env node
// Optional regression check against private recordings; does not save market data.
import assert from 'node:assert/strict';
import { readSession } from './import-session.mjs';
import { normalizePayload, validatePayload } from '../public/payload-adapters.mjs';
import { frameAt } from '../public/market-data.mjs';
const [profileId,file]=process.argv.slice(2);
if(!profileId||!file)throw new Error('Usage: node scripts/verify-session.mjs <workspace-profile> <session.json[.gz]>');
const {payload}=await readSession(file);
validatePayload(payload,profileId,{allowUnidentified:true});payload.workspace_profile=profileId;
const before=JSON.stringify(payload),data=normalizePayload(payload,profileId);
const times=new Set([data.start,data.end,data.analysisStart-1,data.analysisStart,
  ...data.calls.filter((_,i)=>i%40===0).flatMap(row=>[row.x-1,row.x])]);
for(const time of times){
  if(time<data.start||time>data.end)continue;
  const frame=frameAt(data,time);
  for(const field of ['price','oi','cash','options','snapshots','controls','controlHistory','transitions']){
    assert.ok(frame[field].every(row=>row.x<=time),`${field} contains a future row at ${time}`);
  }
  assert.ok(!frame.call||frame.call.x<=time);
  for(const row of frame.snapshots){
    const first=data.options.find(r=>r.symbol===row.symbol&&r.e===row.e);
    if(!row.cumPartial)assert.ok(Math.abs(first.oi+row.cumPositive+row.cumNegative-row.oi)<1e-6,'Cumulative OI failed to reconcile');
  }
}
const sourceCalls=data.profile.version==='2.0.0'?payload.decisions.map(r=>r.baseline_call).filter(Boolean):[];
for(const call of sourceCalls){
  const projected=data.calls.find(r=>r.decision_id? r.decision_id===call.decision_id : r.t===call.t);
  assert.ok(projected);
  for(const [key,value]of Object.entries(call))assert.deepEqual(projected[key],value);
}
assert.equal(JSON.stringify(payload),before,'Source was mutated');
const last=frameAt(data,data.end);
console.log(JSON.stringify({profile:profileId,session:data.session,prices:data.price.length,calls:data.calls.length,
  contexts:data.contexts.length,strikeReceipts:data.options.length,controls:data.controls.length,
  vixAvailable:last.vixRange.high!==null,passed:true}));
