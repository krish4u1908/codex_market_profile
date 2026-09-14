// Regression: changing dates must not send a frame while the new session is loading.
// All source data below is synthetic. No production API is contacted.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {v1,v2,day} from '../tests/fixtures.mjs';
const {chromium}=await import(process.env.ENTRY_PLAYWRIGHT_MODULE?pathToFileURL(process.env.ENTRY_PLAYWRIGHT_MODULE).href:'playwright');
const root=fileURLToPath(new URL('../dist/',import.meta.url));
const output=process.env.ENTRY_UI_OUTPUT||'/tmp/replay-switch-ui';fs.mkdirSync(output,{recursive:true});
const dates=['2026-09-09','2026-09-10','2026-09-11'];
const profiles=['nifty-v1062','nifty-v200','banknifty-v1062','banknifty-v200'];
function payload(profile,date){
  const instrument=profile.startsWith('nifty-')?'NIFTY':'BANKNIFTY';
  const source=profile.endsWith('v200')?v2(instrument,{receipts:true}):v1(instrument);
  source.provenance={history_note:'Synthetic replay-switch test '+date};
  return JSON.stringify(source).replaceAll(day,date);
}
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),name=url.pathname;
  const json=(body,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
  if(name==='/workspace-config.json')return json({live:true,profiles,defaultProfile:'nifty-v200',defaultMode:'replay',pollMilliseconds:5000});
  if(name==='/api/catalog')return json({sessions:dates.map(session=>({id:session,session,source:'synthetic',payload:'/fixture/'+url.searchParams.get('profile')+'/'+session}))});
  if(name==='/api/health')return json({status:'waiting',market_open:false});
  if(name==='/api/live')return json({error:'Synthetic live mode has no session'},503);
  if(name.startsWith('/fixture/')){
    const [, ,profile,date]=name.split('/');
    return setTimeout(()=>{res.writeHead(200,{'Content-Type':'application/json'});res.end(payload(profile,date));},450);
  }
  const filename=path.resolve(root,'.'+(name==='/'?'/index.html':name));
  if(!filename.startsWith(root)||!fs.existsSync(filename)||!fs.statSync(filename).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.mjs':'application/javascript','.json':'application/json','.css':'text/css'})[path.extname(filename)]||'application/octet-stream');
  res.end(fs.readFileSync(filename));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,...(process.env.ENTRY_CHROME?{executablePath:process.env.ENTRY_CHROME}:{})});
const checks=[];
try{
  for(const profile of profiles){
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/?workspace=${profile}&mode=replay`);
    const loaded=async date=>{
      await page.getByText('Synthetic replay-switch test '+date,{exact:true}).waitFor({timeout:15000});
      await page.getByRole('button',{name:'Play replay',exact:true}).waitFor();
      assert.equal(await page.getByRole('button',{name:'Play replay',exact:true}).isEnabled(),true);
      assert.equal(await page.getByRole('alert').count(),0);
    };
    const select=async date=>{
      await page.getByRole('combobox',{name:'Recorded session'}).click();
      await page.getByRole('option',{name:new RegExp(date.slice(-2)+' Sept')}).click();
    };
    await loaded(dates[0]);
    for(const date of [dates[1],dates[2],dates[0]]){await select(date);await loaded(date);}
    // A second switch while the previous fetch is delayed must cancel the old load.
    await select(dates[1]);await select(dates[2]);await loaded(dates[2]);
    const input=page.getByRole('textbox',{name:'Jump to IST time'});
    await input.fill('09:46');await input.press('Enter');
    await page.waitForFunction(()=>document.querySelector('.replay-time strong')?.textContent==='09:46:00');
    await page.locator('input[type=file]').setInputFiles({name:'synthetic.json',mimeType:'application/json',buffer:Buffer.from(payload(profile,dates[1]))});
    await loaded(dates[1]);
    await page.getByRole('combobox',{name:'Live or replay mode'}).click();
    await page.getByRole('option',{name:'Live',exact:true}).click();
    await page.getByRole('button',{name:'Open replay',exact:true}).click();
    await loaded(dates[0]);
    if(profile==='nifty-v200')await page.screenshot({path:path.join(output,'replay-switch-nifty.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    checks.push({profile,sequentialDateSwitch:'PASS',rapidDateSwitch:'PASS',seek:'PASS',fileImport:'PASS',liveToReplay:'PASS'});
    await page.close();
  }
  fs.writeFileSync(path.join(output,'replay-switch-checks.json'),JSON.stringify(checks,null,2)+'\n');
  console.log(JSON.stringify(checks,null,2));
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
