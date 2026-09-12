#!/usr/bin/env node
// Read-only replay audit. No broker, server, database or order operations.
import fs from 'node:fs';
import zlib from 'node:zlib';
import assert from 'node:assert/strict';
import {parseArgs} from 'node:util';
import {normalizePayload} from '../public/payload-adapters.mjs';
import {frameAt} from '../public/market-data.mjs';
import {unpack} from '../public/series.mjs';

const {values}=parseArgs({options:{input:{type:'string'},profile:{type:'string'},'indicator-inputs':{type:'string'},'option-reports':{type:'string'},output:{type:'string'}}});
if(!values.input||!values.profile)throw new Error('Use --input SESSION.json[.gz] --profile nifty-v200|banknifty-v200 [--indicator-inputs FEED.json] [--output AUDIT.json]');
const read=path=>{const bytes=fs.readFileSync(path);return JSON.parse((bytes[0]===31&&bytes[1]===139?zlib.gunzipSync(bytes):bytes).toString());};
const payload=read(values.input);
if(values['indicator-inputs'])payload.indicator_inputs=read(values['indicator-inputs']);
if(values['option-reports'])payload.option_report_inputs=read(values['option-reports']);
const data=normalizePayload(payload,values.profile);
const available=row=>Math.max(...[row.x,row.t,row.context_published_at,row.published_at,row.available_at,row.first_observed_at]
  .map(v=>typeof v==='number'?v:Date.parse(v)).filter(Number.isFinite));
function prefix(at) {
  const p=structuredClone(payload);
  p.decisions=p.decisions.filter(row=>available(row)<=at);
  if(p.price_history)p.price_history=p.price_history.filter(row=>available(row)<=at);
  if(p.chart_history)p.chart_history=unpack(p.chart_history).filter(row=>available(row)<=at);
  if(p.chart_inputs)for(const key of ['price','futures_oi','futures_volume','cash_vix','option_strike_oi','intraday_inventory']) {
    const block=p.chart_inputs[key];if(!block)continue;
    const rows=unpack(block).filter(row=>available(row)<=at);
    if(key==='option_strike_oi'&&block.strike_selection)p.chart_inputs[key]={...block,fields:rows.length?Object.keys(rows[0]):block.fields,rows:rows.map(Object.values)};
    else p.chart_inputs[key]=rows;
  }
  if(p.indicator_inputs){p.indicator_inputs.revisions=p.indicator_inputs.revisions.filter(row=>available(row)<=at);p.indicator_inputs.as_of=new Date(at).toISOString();}
  if(p.option_report_inputs)p.option_report_inputs.reports=p.option_report_inputs.reports.filter(r=>r.x<=at);
  if(p.live)p.live.server_time=new Date(at).toISOString();
  return normalizePayload(p,values.profile);
}
const checkpoints=[...new Set([data.analysisStart,...data.entryAnalysis.events.flatMap(row=>[row.x-1,row.x]),data.end])].sort((a,b)=>a-b);
for(const at of checkpoints) {
  const full=frameAt(data,at).entryBubbles,limited=frameAt(prefix(at),at).entryBubbles;
  assert.deepEqual(limited,full,`Prefix replay differs at ${new Date(at).toISOString()}`);
  assert.deepEqual(frameAt(data,at,{live:true}).entryBubbles,full,`Live/replay differs at ${new Date(at).toISOString()}`);
  assert.ok(full.every(row=>row.x<=at));
}
for(const at of [...checkpoints].reverse())assert.ok(frameAt(data,at).entryBubbles.every(row=>row.x<=at));
const isoIST=at=>new Date(at+19800000).toISOString().replace('Z','+05:30');
const report={policy:data.entryAnalysis.policy,profile:values.profile,session:data.session,
  prefixChecks:checkpoints.length,causalReplay:'PASS',liveReplayParity:'PASS',
  counts:{...Object.fromEntries(['PE_UP','PE_DOWN','CE_UP','CE_DOWN'].map(k=>[k,data.entryAnalysis.events.filter(r=>r.category===k).length])),spikeReports:data.entryAnalysis.assessments.length},
  events:data.entryAnalysis.events.map(row=>({...row,ist:isoIST(row.x)})),
  assessments:data.entryAnalysis.assessments.map(row=>({...row,ist:isoIST(row.x)}))};
if(values.output)fs.writeFileSync(values.output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({profile:report.profile,session:report.session,counts:report.counts,
  prefixChecks:report.prefixChecks,causalReplay:report.causalReplay,
  events:report.events.map(row=>({ist:row.ist,category:row.category,strikes:row.spikes.map(s=>s.strike)}))},null,2));
