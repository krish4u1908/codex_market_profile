import test from 'node:test';
import assert from 'node:assert/strict';
import {optionOiMinuteFlows} from '../public/option-oi-flow.mjs';

const session='2026-09-11';
const at=time=>Date.parse(`${session}T${time}+05:30`);
const symbol=(strike,side)=>`NSE:NIFTY26SEP${strike}${side}`;
const contracts=(values={})=>[
  ...[23300,23250,23200].map((strike,index)=>({symbol:symbol(strike,'PE'),side:'PE',strike,oi:(values.PE||[1000,2000,3000])[index]})),
  ...[23350,23400,23450].map((strike,index)=>({symbol:symbol(strike,'CE'),side:'CE',strike,oi:(values.CE||[4000,5000,6000])[index]})),
];
const feed=reports=>({schema:'OPTION_REPORT_INPUTS_V1',source:'OPTION_CHAIN_REPORT_QUOTES',instrument:'NIFTY',session,status:'AVAILABLE',reports});
const data={session,profile:{instrument:'NIFTY',version:'2.0.0'}};
const report=(time,values)=>({x:at(time),expiry:'2026-09-29',spot:23325,vix:12,contracts:contracts(values)});

test('separates fresh positive and negative OI for PE and CE each minute',()=>{
  const result=optionOiMinuteFlows(data,feed([
    report('09:15:55'),
    report('09:16:55',{PE:[1100,1950,3000],CE:[3900,5200,6000]}),
  ]));
  assert.equal(result.status,'AVAILABLE');
  assert.equal(result.points.length,2);
  const pe=result.points.find(row=>row.side==='PE'),ce=result.points.find(row=>row.side==='CE');
  assert.deepEqual({positive:pe.positive,negative:pe.negative,net:pe.net,dominant:pe.dominant},{positive:100,negative:50,net:50,dominant:'POSITIVE'});
  assert.deepEqual({positive:ce.positive,negative:ce.negative,net:ce.net,dominant:ce.dominant},{positive:200,negative:100,net:100,dominant:'POSITIVE'});
});

test('aggregates multiple receipts in one minute without using a rolling window',()=>{
  const result=optionOiMinuteFlows(data,feed([
    report('09:15:55'),
    report('09:16:10',{PE:[1010,2000,3000],CE:[4000,5000,6000]}),
    report('09:16:55',{PE:[1005,2020,3000],CE:[4000,4990,6000]}),
  ]));
  const pe=result.points.find(row=>row.side==='PE');
  assert.equal(pe.receipts,2);
  assert.equal(pe.positive,30);
  assert.equal(pe.negative,5);
  assert.equal(pe.x,at('09:16:55'));
});

test('leaves a gap when the previous receipt is too old',()=>{
  const result=optionOiMinuteFlows(data,feed([
    report('09:15:55'),
    report('09:17:55',{PE:[1100,2000,3000],CE:[4000,5000,6000]}),
  ]));
  assert.deepEqual(result.points,[]);
});

test('prefix results are causal and unchanged by later reports',()=>{
  const reports=[report('09:15:55'),report('09:16:55',{PE:[1100,2000,3000],CE:[4000,5000,6000]}),report('09:17:55',{PE:[900,2000,3000],CE:[4000,5100,6000]})];
  const prefix=optionOiMinuteFlows(data,feed(reports.slice(0,2))).points;
  const complete=optionOiMinuteFlows(data,feed(reports)).points.filter(row=>row.x<=at('09:16:55'));
  assert.deepEqual(complete,prefix);
});

test('rejects mismatched inputs and does not apply to v1',()=>{
  assert.equal(optionOiMinuteFlows(data,{...feed([]),instrument:'BANKNIFTY'}).status,'INVALID');
  assert.equal(optionOiMinuteFlows({...data,profile:{...data.profile,version:'1.0.62'}},feed([])).status,'NOT_APPLICABLE');
});
