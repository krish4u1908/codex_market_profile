#!/usr/bin/env python3
"""Headless browser acceptance for the offline R6D package."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright

DATES=("2026-08-11","2026-08-12","2026-08-13","2026-08-18","2026-08-19","2026-08-20")

def check(condition,name,results,detail=""):
    results.append({"name":name,"pass":bool(condition),"detail":detail})

def main():
    p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--output-root',type=Path,required=True);a=p.parse_args();out=a.output_root;shots=out/'screenshots';shots.mkdir(parents=True,exist_ok=True)
    results=[];performance=[];screens=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1600,"height":1000},device_scale_factor=1)
        errors=[];page.on('console',lambda m: errors.append(m.text) if m.type=='error' else None);page.on('pageerror',lambda e:errors.append(str(e)))
        for date in DATES:
            begun=time.perf_counter();page.goto(f"{a.base_url}/replay_{date}.html",wait_until='networkidle');page.wait_for_function('window.R6D && window.R6D.data');load=(time.perf_counter()-begun)*1000
            page.click('[data-time="14:30"]');page.wait_for_timeout(100)
            data=page.evaluate('''()=>{const r=window.R6D,d=r.data,t=r.state.t;const ip=r.segments(d.price,'it','i',t).flat(),fp=r.segments(d.price,'ft','f',t).flat();return {ip:ip.length,fp:fp.length,lastI:ip.at(-1)?.[0],lastF:fp.at(-1)?.[0],t,episodes:d.episodes.length,reveal:r.state.reveal,controls:[...r.controlsAt(t)].map(([k,v])=>[k,v[0][0],v.at(-1)[0]])}}''')
            check(data['ip']>1,f'{date} Index multi-point path',results,str(data['ip']));check(data['fp']>1,f'{date} Futures multi-point path',results,str(data['fp']));check(data['lastI']<=data['t'] and data['lastF']<=data['t'],f'{date} no future price path',results);check(not data['reveal'],f'{date} subsequent path hidden by default',results)
            fixed=[x for x in data['controls'] if not x[0].startswith('ID|')];intraday=[x for x in data['controls'] if x[0].startswith('ID|')]
            check(all(x[1]==page.evaluate('window.R6D.start') and x[2]==page.evaluate('window.R6D.end') for x in fixed),f'{date} fixed controls full session',results)
            check(all(x[2]<=data['t'] for x in intraday),f'{date} Intraday controls causal cutoff',results)
            # Toggle memory and independent master behavior.
            page.uncheck('[data-child="1D|CE_POS_OI_VPOC"]');page.uncheck('[data-master="1D"]');page.check('[data-master="1D"]')
            check(not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]'),f'{date} child memory survives master toggle',results)
            before=page.evaluate('window.R6D.state.toggles.children["1D|FUT_POS_OI_VPOC"]');page.click('[data-step="bar"][data-dir="1"]');after=page.evaluate('window.R6D.state.toggles.children["1D|FUT_POS_OI_VPOC"]');check(before==after,f'{date} replay preserves toggles',results)
            # Batch-as-of and stream-style prefix expose identical last inventory state.
            eq=page.evaluate('''()=>{const r=window.R6D,d=r.data,t=r.state.t;const batch=[...r.controlsAt(t)].map(([k,v])=>[k,v.at(-1)[1]]);const eligible=d.inventory.filter(x=>Date.parse(x.control_effective_timestamp)<=t);const last={};for(const x of eligible)if(r.available(x.horizon).availability_state==='AVAILABLE'&&r.state.toggles.masters[x.horizon]&&r.state.toggles.children[x.horizon+'|'+x.family])last[x.horizon+'|'+x.family]=Number(x.control_value);return JSON.stringify(batch)==JSON.stringify(Object.entries(last))}''')
            check(eq,f'{date} incremental/batch-as-of display identity',results)
            toggle_start=time.perf_counter();page.click('[data-market="basis"]');page.wait_for_timeout(50);toggle=(time.perf_counter()-toggle_start)*1000
            geometry=page.evaluate('''()=>({price:document.querySelector('#price').getBoundingClientRect(),basis:document.querySelector('#basis').getBoundingClientRect(),hidden:document.querySelector('#basisWrap').classList.contains('hidden')})''')
            check(not geometry['hidden'] and abs(geometry['price']['width']-geometry['basis']['width'])<1,f'{date} Basis panel shared width/clock geometry',results,str(geometry))
            memory=page.evaluate('performance.memory ? performance.memory.usedJSHeapSize : null')
            performance.append({'date':date,'initial_render_ms':round(load,3),'toggle_latency_ms':round(toggle,3),'used_js_heap_bytes':memory,'payload_transfer_bytes':page.evaluate('performance.getEntriesByType("resource").filter(x=>x.name.includes("session_")).reduce((a,x)=>a+x.transferSize,0)')})
        # Required visual acceptance frames.
        frames=[('2026-08-13','14:30','aug13_high_frequency.png'),('2026-08-18','13:24','aug18_mixed_context.png'),('2026-08-19','11:30','aug19_abcd.png'),('2026-08-20','13:30','aug20_partial_fixed.png'),('synthetic_intraday_only','12:00','synthetic_intraday_only.png'),('synthetic_missing_3d_2d','12:00','synthetic_missing_3d_2d.png')]
        for route,clock,name in frames:
            page.goto(f'{a.base_url}/replay_{route}.html',wait_until='networkidle');page.wait_for_function('window.R6D && window.R6D.data');page.evaluate(f'''()=>{{window.R6D.state.t=Date.parse(window.R6D.data.date+'T{clock}:00+05:30');window.R6D.render()}}''');page.wait_for_timeout(100);path=shots/name;page.screenshot(path=str(path),full_page=True);screens.append({'file':str(path.relative_to(out)),'route':route,'clock':clock,'bytes':path.stat().st_size})
        page.goto(f'{a.base_url}/replay_synthetic_intraday_only.html',wait_until='networkidle');page.wait_for_function('window.R6D && window.R6D.data');states=page.evaluate('Object.fromEntries(["3D","2D","1D","ID"].map(h=>[h,window.R6D.available(h).availability_state]))');check(states=={'3D':'MISSING','2D':'MISSING','1D':'MISSING','ID':'AVAILABLE'},'Intraday-only degradation state',results,str(states));check(page.evaluate('window.R6D.available("ID").overall_state')=='LIVE_INTRADAY_ONLY','Intraday-only overall state',results)
        page.goto(f'{a.base_url}/replay_synthetic_missing_3d_2d.html',wait_until='networkidle');page.wait_for_function('window.R6D && window.R6D.data');states=page.evaluate('Object.fromEntries(["3D","2D","1D","ID"].map(h=>[h,window.R6D.available(h).availability_state]))');check(states['3D']=='INSUFFICIENT_PRIOR_SESSIONS' and states['2D']=='INSUFFICIENT_PRIOR_SESSIONS' and states['1D']=='AVAILABLE' and states['ID']=='AVAILABLE','Missing 3D/2D degradation state',results,str(states))
        browser.close()
    check(not errors,'Browser console/page errors',results,' | '.join(errors))
    (out/'tests/browser_results.json').write_text(json.dumps(results,indent=2)+'\n');(out/'tests/performance.json').write_text(json.dumps(performance,indent=2)+'\n');(out/'screenshot_inventory.json').write_text(json.dumps(screens,indent=2)+'\n')
    passed=sum(x['pass'] for x in results);failed=len(results)-passed
    (out/'browser_test_report.txt').write_text(f'R6D BROWSER ACCEPTANCE\nPassed: {passed}\nFailed: {failed}\nSkipped: 0\n\n'+"\n".join(f"{'PASS' if x['pass'] else 'FAIL'} {x['name']} {x['detail']}" for x in results)+'\n')
    print(json.dumps({'passed':passed,'failed':failed,'screenshots':len(screens)}));raise SystemExit(1 if failed else 0)
if __name__=='__main__':main()
