import fs from 'node:fs';import zlib from 'node:zlib';
import {fixedPressure} from '../../public/oi-fixed-pressure.mjs';
import {pressureDirection} from '../../public/pressure-direction.mjs';
const directory=process.argv[2];if(!directory)throw new Error('Usage: node evaluate.mjs EXTRACTED_SESSION_JSON_DIRECTORY');
const obs=zlib.gunzipSync(fs.readFileSync(new URL('./observations.jsonl.gz',import.meta.url))).toString().trim().split('\n').map(JSON.parse);
const rows=[];
for(const file of fs.readdirSync(directory).sort()){
 const p=JSON.parse(fs.readFileSync(directory+'/'+file)),data={profile:{instrument:'NIFTY',version:'2.0.0'},session:p.session,selection:p.chart_inputs.option_strike_oi.strike_selection};
 const pressure=fixedPressure(data,p.option_report_inputs),result=pressureDirection(pressure.points,p.session,Infinity,pressure),byMinute=new Map(result.rows.map(r=>[Math.floor(r.x/60000),r]));
 for(const o of obs.filter(r=>r.session===p.session)){
  const r=byMinute.get(Math.floor(o.t/60));if(!r||r.direction===null)throw new Error('Missing eligible candidate row '+p.session+' '+o.t);
  rows.push({...o,candidate:r.direction,candidateKind:r.kind,candidateReason:r.reason,mixedOrigin:r.mixedOrigin,raw5:Math.sign(o.strict_5),quantity5:Math.sign(o.quantity_5),quantityAgreement:Math.sign(o.quantity_1)===Math.sign(o.quantity_5)?Math.sign(o.quantity_5):0});
 }
}
fs.writeFileSync(new URL('./evaluation_rows.jsonl.gz',import.meta.url),zlib.gzipSync(rows.map(JSON.stringify).join('\n')+'\n'));console.log('Compared',rows.length,'eligible historical rows across',new Set(rows.map(r=>r.session)).size,'sessions');
