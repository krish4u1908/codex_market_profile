import test from 'node:test';
import assert from 'node:assert/strict';
import {Worker} from 'node:worker_threads';
import {once} from 'node:events';
import {v2,ms,day} from './fixtures.mjs';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt} from '../public/market-data.mjs';
import {validatePreview,incomingIndex,previewPriceOption,previewVixOption,observedVolume} from '../public/display-preview.mjs';

function feed(instrument='BANKNIFTY'){
  const symbol=instrument==='NIFTY'?'NSE:NIFTY50-INDEX':'NSE:NIFTYBANK-INDEX';
  const price={symbol,price:instrument==='NIFTY'?24100:57500,received_ms:ms('10:00:02'),source_ms:ms('10:00:02')};
  return {schema:'READ_ONLY_LIVE_DISPLAY_V1',version:'3.1.0-preview.1',instrument,session:day,
    status:'LIVE',display_only:true,owns_engine:false,server_ms:ms('10:00:03'),generation:'a',
    index_symbol:symbol,latest:{[symbol]:price},prices:[price],vix:[],volume_bars:[]};
}

test('fast price updates preserve confirmed futures/CE/PE climaxes, calls, ribbons and input history',()=>{
  for(const instrument of ['NIFTY','BANKNIFTY']){
    const payload=v2(instrument,{receipts:true});
    payload.decisions[0].futures_volume_ratio=4.17;
    payload.decisions[0].futures_valid_volume_5m=12345;
    const normalized=normalizePayload(payload,`${instrument.toLowerCase()}-v200`);
    const frame=frameAt(normalized,ms('10:00:00'),{live:true});
    const before=JSON.stringify({payload,normalized,frame});
    const confirmed={name:'Confirmed climax',type:'scatter',data:frame.volumeClimaxes.map(r=>[r.x,r.price])};
    const option={xAxis:[{max:frame.now},{max:frame.now}],series:[{name:'Price',data:frame.price.map(r=>[r.x,r.i])},confirmed]};
    const saved=structuredClone(option);
    const projected=previewPriceOption(option,frame,validatePreview(feed(instrument),instrument,day));
    assert.equal(projected.series.length,3);
    assert.equal(projected.series[1],confirmed);
    assert.deepEqual(projected.series[1],saved.series[1]);
    assert.deepEqual(option,saved);
    assert.equal(projected.series[2].data.at(-1)[0],ms('10:00:02'));
    assert.equal(JSON.stringify({payload,normalized,frame}),before);
    assert.equal(frame.volumeClimaxes[0].ratio,4.17);
  }
});

test('wrong instrument/day and stale or catching-up readings cannot extend a chart',()=>{
  const raw=feed(),frame=frameAt(normalizePayload(v2('BANKNIFTY',{receipts:true}),'banknifty-v200'),ms('10:00:00'));
  assert.equal(validatePreview(raw,'NIFTY'),null);
  assert.equal(validatePreview(raw,'BANKNIFTY','2026-09-04'),null);
  const option={series:[],xAxis:{max:frame.now}};
  assert.equal(previewPriceOption(option,frame,{...raw,status:'CATCHING_UP'}),option);
  assert.equal(previewPriceOption(option,frame,{...raw,server_ms:ms('10:00:15')}),option);
  assert.equal(previewPriceOption(option,frame,null),option);
  assert.equal(incomingIndex(raw,{latest:{x:ms('10:00:04')}}),null);
});

test('forming volume uses only the selected basket and exposes incomplete coverage',()=>{
  const raw=feed();raw.futures_symbol='NSE:BANKNIFTY26SEPFUT';
  raw.volume_bars=[{symbol:'selectedCE',minute_ms:ms('10:00:00'),volume:25,observations:1,partial:false},
    {symbol:'unselectedCE',minute_ms:ms('10:00:00'),volume:99999,observations:5,partial:false}];
  const selection={available:true,CE:[{symbol:'selectedCE'},{symbol:'missingCE'}],PE:[]};
  const result=observedVolume(raw,selection,'CE');
  assert.equal(result.bars[0].volume,25);
  assert.equal(result.bars[0].partial,true);
  assert.equal(result.bars[0].forming,true);
  assert.equal(result.expected,2);
  assert.deepEqual(observedVolume(raw,{available:false},'CE').bars,[]);
});

test('preview worker cancels pending updates when leaving live mode',async()=>{
  const worker=new Worker(new URL('./worker-harness.mjs',import.meta.url),{workerData:{module:'preview',sources:{
    '/api/display-preview':{delay:100,payload:feed()}}}});
  const messages=[];
  try{
    await once(worker,'message');worker.on('message',m=>messages.push(m));
    worker.postMessage({action:'start',instrument:'BANKNIFTY'});
    await new Promise(r=>setTimeout(r,20));worker.postMessage({action:'stop'});
    await new Promise(r=>setTimeout(r,150));
    assert.ok(!messages.some(m=>m.kind==='preview'));
  }finally{await worker.terminate();}
});
