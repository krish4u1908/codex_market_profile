import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { gunzipSync } from 'node:zlib';
import { importSession } from '../scripts/import-session.mjs';
import { normalizePayload } from '../public/payload-adapters.mjs';
import { v1, v2, day } from './fixtures.mjs';

test('V2 importer adds matching chart receipts without copying v1 calls or inventory controls',async()=>{
  const root=await mkdtemp(join(tmpdir(),'market-import-'));
  try{
    const source=v2('NIFTY'),input=v1('NIFTY');
    input.directional_prediction[0].score=999;input.intraday_inventory[0].control_value=999;
    await writeFile(join(root,'native.json'),JSON.stringify(source));await writeFile(join(root,'input.json'),JSON.stringify(input));
    const result=await importSession({profileId:'nifty-v200',file:join(root,'native.json'),chartInputs:join(root,'input.json'),output:join(root,'out')});
    const saved=JSON.parse(gunzipSync(await readFile(result.file)));
    assert.deepEqual(saved.decisions,source.decisions);
    assert.equal(saved.chart_inputs.intraday_inventory,undefined);assert.equal(saved.chart_inputs.directional_prediction,undefined);
    assert.equal(normalizePayload(saved,'nifty-v200').options.length,24);
    const catalog=JSON.parse(await readFile(join(root,'out/nifty-v200/catalog.json')));
    assert.equal(catalog.sessions[0].payload,`/data/nifty-v200/${day}.json.gz`);
    input.instrument='BANKNIFTY';await writeFile(join(root,'input.json'),JSON.stringify(input));
    await assert.rejects(()=>importSession({profileId:'nifty-v200',file:join(root,'native.json'),chartInputs:join(root,'input.json'),output:join(root,'out')}),/Instrument mismatch/);
    const unchanged=JSON.parse(gunzipSync(await readFile(result.file)));assert.deepEqual(saved,unchanged);
  }finally{await rm(root,{recursive:true,force:true});}
});

test('SQLite export reads one engine database and preserves decisions and source bytes',async()=>{
  const root=await mkdtemp(join(tmpdir(),'market-export-'));
  try{
    const input=v1('NIFTY'),source=v2('NIFTY'),data={price:input.price,oi:input.futures_oi,
      inventory:input.intraday_inventory,cash:input.cash_vix,options:[]};
    await writeFile(join(root,'fixture.json'),JSON.stringify({data,source,selection:input.option_strike_oi.strike_selection}));
    execFileSync('python',['-c',`
import sqlite3,json,sys
from datetime import datetime
from pathlib import Path
r=Path(sys.argv[1]);f=json.loads((r/'fixture.json').read_text());db=sqlite3.connect(r/'context.sqlite3')
db.executescript('CREATE TABLE inputs(day,kind,identity,timestamp,body); CREATE TABLE decisions(day,cutoff,body); CREATE TABLE selections(day,body);')
for kind,rows in f['data'].items():
 for i,row in enumerate(rows):db.execute('INSERT INTO inputs VALUES(?,?,?,?,?)',('${day}',kind,str(i),datetime.fromisoformat(row['t']).timestamp(),json.dumps(row)))
for row in f['source']['decisions']:db.execute('INSERT INTO decisions VALUES(?,?,?)',('${day}',datetime.fromisoformat(row['input_cutoff']).timestamp(),json.dumps(row)))
db.execute('INSERT INTO selections VALUES(?,?)',('${day}',json.dumps(f['selection'])));db.commit();db.close()
`,root]);
    const before=await readFile(join(root,'context.sqlite3'));
    execFileSync('python',['scripts/export-v2-inputs.py','--database',join(root,'context.sqlite3'),'--profile','nifty-v200','--session',day,'--output',join(root,'out.json')]);
    const result=JSON.parse(await readFile(join(root,'out.json')));
    assert.deepEqual(result.decisions,source.decisions);assert.deepEqual(result.chart_inputs.futures_oi,input.futures_oi);
    assert.deepEqual(await readFile(join(root,'context.sqlite3')),before);
    assert.equal(normalizePayload(result,'nifty-v200').calls[0].score,3.5);
  }finally{await rm(root,{recursive:true,force:true});}
});
