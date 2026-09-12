#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {parseArgs} from 'node:util';
import {oiEntryBubbles} from '../public/oi-entry-bubbles.mjs';
import {OUTCOME_POLICY,horizonOutcome,evaluateLongOption,summarizeTrades,isoIST} from '../research/bubble-outcomes.mjs';
const {values}=parseArgs({options:{inputs:{type:'string'},output:{type:'string'}}});
if(!values.inputs||!values.output)throw Error('Use --inputs PREPARED_DIRECTORY --output RESULTS_DIRECTORY');
fs.mkdirSync(values.output,{recursive:true});
const days=[],events=[],trades=[];
const write=(name,value)=>fs.writeFileSync(path.join(values.output,name),JSON.stringify(value,null,2)+'\n');
for(const filename of fs.readdirSync(values.inputs).filter(n=>n.endsWith('-research-inputs.json')).sort()) {
  const input=JSON.parse(fs.readFileSync(path.join(values.inputs,filename)));
  assert.equal(input.schema,'BUBBLE_RESEARCH_INPUTS_V1');assert.equal(input.instrument,'NIFTY');
  const feed=input.option_report_inputs,data={session:input.session,profile:{instrument:'NIFTY',version:'2.0.0'}};
  const analysis=oiEntryBubbles(data,feed);assert.equal(analysis.status,'AVAILABLE');
  let prefixChecks=0;
  for(const e of analysis.events)for(const at of [e.x-1,e.x]) {
    assert.deepEqual(oiEntryBubbles(data,{...feed,reports:feed.reports.filter(r=>r.x<=at)}).events,analysis.events.filter(r=>r.x<=at));prefixChecks++;
  }
  const reports=new Map(feed.reports.map(r=>[r.x,r])),dayTrades=[];
  for(const e of analysis.events) {
    const outcomes=OUTCOME_POLICY.horizons.map(h=>horizonOutcome(e,feed.reports,h,input.session));
    const record={...e,session:input.session,ist:isoIST(e.x),horizons:outcomes};events.push(record);
    const sides=e.watch==='LONG_WATCH'?['CE']:e.watch==='SHORT_WATCH'?['PE']:['CE','PE'];
    for(const side of sides)dayTrades.push(evaluateLongOption(e,side,reports.get(e.x),input.optionBars,input.session));
  }
  trades.push(...dayTrades);
  const day={session:input.session,source:input.source,events:analysis.events.length,prefixChecks,
    colors:Object.fromEntries(['green','red','yellow'].map(c=>[c,analysis.events.filter(r=>r.state===c).length])),
    categories:Object.fromEntries(['PE_UP','PE_DOWN','CE_UP','CE_DOWN'].map(c=>[c,analysis.events.filter(r=>r.category===c).length])),
    trades:summarizeTrades(dayTrades)};days.push(day);
  write(input.session+'-replay-audit.json',{...analysis,causalReplay:'PASS',prefixChecks});
  console.log(JSON.stringify({session:day.session,colors:day.colors,optionOutcomes:day.trades.statusCounts}));
}
const mean=rows=>rows.length?rows.reduce((a,v)=>a+v,0)/rows.length:null;
const groups=[];
for(const category of ['PE_UP','CE_DOWN','PE_DOWN','CE_UP']) {
  const selected=events.filter(e=>e.category===category),sample=selected[0];
  groups.push({category,color:sample?.state,eventCount:selected.length,horizons:OUTCOME_POLICY.horizons.map(h=>{
    const rows=selected.map(e=>e.horizons.find(x=>x.minutes===h)),valid=rows.filter(r=>r.status==='AVAILABLE');
    return {minutes:h,available:valid.length,unavailable:rows.length-valid.length,
      meanIndexPoints:mean(valid.map(r=>r.changePoints)),up:valid.filter(r=>r.changePoints>0).length,
      down:valid.filter(r=>r.changePoints<0).length,flat:valid.filter(r=>r.changePoints===0).length,
      meanExpectedDirectionPoints:mean(valid.map(r=>r.expectedDirectionPoints).filter(x=>x!==null))};
  }),optionTests:['CE','PE'].map(side=>({buy:side,...summarizeTrades(trades.filter(t=>t.category===category&&t.side===side))})).filter(t=>t.observations)});
}
const splits=[];
for(const group of ['DIRECTIONAL','YELLOW'])for(const phase of ['CONTINUOUS','CAS_PERIOD'])for(const expiryDay of [false,true]) {
  const rows=trades.filter(t=>(group==='YELLOW'?(t.color==='yellow'):(t.color!=='yellow'))&&t.phase===phase&&t.expiryDay===expiryDay);
  if(rows.length)splits.push({group,phase,expiryDay,...summarizeTrades(rows)});
}
write('events.json',events);write('option-trades.json',trades);
write('summary.json',{policy:OUTCOME_POLICY,status:'PASS',sessions:days.length,events:events.length,
  prefixChecks:days.reduce((a,d)=>a+d.prefixChecks,0),days,groups,splits,
  directional:summarizeTrades(trades.filter(t=>t.color!=='yellow')),yellow:summarizeTrades(trades.filter(t=>t.color==='yellow'))});
const csv=(rows,fields)=>[fields.join(','),...rows.map(row=>fields.map(f=>JSON.stringify(row[f]??'')).join(','))].join('\n')+'\n';
fs.writeFileSync(path.join(values.output,'option-trades.csv'),csv(trades.map(t=>({...t,signalIST:isoIST(t.signalAt),entryIST:isoIST(t.entryAt),exitBarIST:t.exitBarAt?isoIST(t.exitBarAt):''})),
  ['session','signalIST','category','color','side','symbol','strike','expiry','expiryDay','phase','entryIST','entryPrice','stopPrice','targetPrice','status','exitBarIST','exitPrice','grossPoints','grossLower','grossUpper','unrealizedPoints','entrySourceRow','exitSourceRow']));
fs.writeFileSync(path.join(values.output,'horizon-outcomes.csv'),csv(events.flatMap(e=>e.horizons.map(h=>({...h,session:e.session,signalIST:e.ist,category:e.category,color:e.state,toIST:h.at?isoIST(h.at):''}))),
  ['session','signalIST','category','color','minutes','status','from','to','toIST','elapsedSeconds','changePoints','changePct','expectedDirectionPoints','sampledMaxUp','sampledMaxDown','phase']));
