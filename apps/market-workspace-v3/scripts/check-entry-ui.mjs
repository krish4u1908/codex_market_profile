// Browser smoke test against built assets and synthetic fixtures only.
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {entryFixture} from '../tests/entry-fixtures.mjs';
const {chromium}=await import(process.env.ENTRY_PLAYWRIGHT_MODULE?pathToFileURL(process.env.ENTRY_PLAYWRIGHT_MODULE).href:'playwright');
const root=fileURLToPath(new URL('../dist/',import.meta.url));
const output=process.env.ENTRY_UI_OUTPUT||'/tmp/entry-ui';fs.mkdirSync(output,{recursive:true});
const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://localhost').pathname,filename=path.resolve(root,'.'+(name==='/'?'/index.html':name));
  if(!filename.startsWith(root)||!fs.existsSync(filename)||!fs.statSync(filename).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.mjs':'application/javascript','.json':'application/json','.css':'text/css'})[path.extname(filename)]||'application/octet-stream');
  res.end(fs.readFileSync(filename));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,...(process.env.ENTRY_CHROME?{executablePath:process.env.ENTRY_CHROME}:{})});
const checks=[];
try {
  for(const instrument of ['NIFTY','BANKNIFTY'])for(const side of ['PE','CE']) {
    const f=entryFixture(instrument,side),label=side==='PE'?'Long':'Short',page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
    f.payload.provenance={history_note:'Synthetic browser test fixture — not market data.'};
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/?workspace=${instrument.toLowerCase()}-v200`);
    await page.locator('input[type=file]').setInputFiles({name:`synthetic-${instrument}-${side}.json`,mimeType:'application/json',buffer:Buffer.from(JSON.stringify(f.payload))});
    await page.locator('.entry-bubble-caption').waitFor({timeout:20000});
    const seek=async t=>{const input=page.getByRole('textbox',{name:'Jump to IST time'});await input.fill(t);await input.press('Enter');
      await page.waitForFunction(t=>document.querySelector('.replay-time strong')?.textContent===t,t);};
    await seek('10:00:54');assert.match(await page.locator('.entry-bubble-caption').innerText(),new RegExp(label+' 0'));
    await seek('10:00:56');assert.match(await page.locator('.entry-bubble-caption').innerText(),new RegExp(label+' 1'));
    await seek('10:00:54');assert.match(await page.locator('.entry-bubble-caption').innerText(),new RegExp(label+' 0'));
    await seek('10:04:00');await page.locator('.price-panel').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>!!document.querySelector('.price-panel canvas'));
    const box=await page.locator('.price-panel .plot').boundingBox();
    const fraction=(25*60+55)/(29*60);
    await page.mouse.move(box.x+66+fraction*(box.width-88),box.y+318);
    await page.getByText(`${label} entry setup · research`,{exact:true}).waitFor({timeout:5000});
    await page.mouse.move(1,1);
    await page.locator('.price-panel').screenshot({path:path.join(output,`${instrument}-${side}-desktop.png`)});
    await page.locator('.entry-audit summary').click();assert.match(await page.locator('.entry-audit').innerText(),new RegExp(label+' bubble'));
    await page.locator('.entry-audit summary').click();
    await page.setViewportSize({width:390,height:1000});await page.waitForTimeout(200);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
    await page.locator('.price-panel').screenshot({path:path.join(output,`${instrument}-${side}-mobile.png`)});
    assert.deepEqual(errors,[]);checks.push({instrument,side,availability:'PASS',rewind:'PASS',tooltip:'PASS',mobile:'PASS',browserErrors:errors});
    await page.close();
  }
  fs.writeFileSync(path.join(output,'checks.json'),JSON.stringify(checks,null,2)+'\n');
  console.log(JSON.stringify(checks,null,2));
} finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
