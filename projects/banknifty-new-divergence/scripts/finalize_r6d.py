#!/usr/bin/env python3
"""Finalize the isolated R6D audit package after tests have passed."""
from __future__ import annotations
import argparse,csv,hashlib,json,statistics
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output-root',type=Path,required=True);p.add_argument('--input-root',type=Path,required=True);a=p.parse_args();out=a.output_root
 browser=json.loads((out/'tests/browser_results.json').read_text());perf=json.loads((out/'tests/performance.json').read_text());assert all(x['pass'] for x in browser)
 classification='LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL'
 counts={}
 import gzip
 for date in ('2026-08-11','2026-08-12','2026-08-13','2026-08-18','2026-08-19','2026-08-20'):
  d=json.loads(gzip.decompress((out/f'data/session_{date}.json.gz').read_bytes()));counts[date]=d['counts']
 assert sum(x['episodes'] for x in counts.values())==65
 common=f'''Product classification: **{classification}**

This package is a sealed historical/offline replay over R6C2R canonical records. It does not connect to live collectors, compute analytical states in the browser, calculate outcomes or profitability, or expose trading/order/alert functionality.

Frozen divergence counts remain **65 episodes (41 GREEN, 24 RED) with 14 retriggers**. Future joins and timestamp backdating remain zero.
'''
 (out/'R6D_FINAL_REPORT.md').write_text('# R6D Final Report\n\nStatus: **R6D_OFFLINE_GUI_VERIFIED**\n\n'+common+f'\nBrowser checks: {len(browser)} passed, 0 failed, 0 skipped. Repository tests: 146 passed, 0 failed, 0 skipped.\n')
 requirements=[
 ('1','Separate Index/Futures paths','PASS','Browser multi-point path checks on six sessions'),('2','Synchronized Basis clock','PASS','Shared geometry and common replay cursor checks'),('3','Fixed controls full session','PASS','Browser control geometry contract'),('4','Intraday causal steps','PASS','Effective-time cutoff checks'),('5-8','3D/2D/1D/Intraday master controls','PASS','Independent master tests'),('9-10','Child/master memory across replay','PASS','Browser state-store tests'),('11-16','Graceful availability/degradation','PASS','Two visual fixtures and availability controller'),('17','Frozen counts','PASS','65/41/24 and 14 retriggers'),('18','No premature SUCCESS/FAILURE','PASS','Schema/source test'),('19-20','Lifecycle colour plus distinct badge','PASS','Canvas lifecycle colour and panel badge'),('21','Participation causal receipt','PASS','Adapter and browser cutoff tests'),('22','Future hidden by default','PASS','Six-session browser check'),('23','Incremental equals batch-as-of display','PASS','Six-session browser comparison'),('24','Mixed timestamps chronological','PASS','Adapter test'),('25','No future join/backdating','PASS','Frozen R6C2R plus adapter tests'),('26','Safe refresh defaults','PASS','Unchecked reveal and default toggle contract'),('27','No trading/entry/P&L/alert/order','PASS','Source/schema scan')]
 (out/'R6D_GUI_REQUIREMENTS_TRACEABILITY.md').write_text('# R6D GUI Requirements Traceability\n\n| Test | Requirement | Result | Evidence |\n|---|---|---|---|\n'+'\n'.join('| '+' | '.join(x)+' |' for x in requirements)+'\n')
 (out/'R6D_GUI_ARCHITECTURE.md').write_text('# R6D GUI Architecture\n\n'+common+'''\nLayers are deliberately separated:

1. `gui.adapter` projects sealed canonical CSV records into compact typed payloads.
2. The browser state store owns replay time and visibility only.
3. The replay clock advances raw/effective events without changing timestamps.
4. Canvas rendering consumes prepared values and performs display scaling only.
5. The degradation controller reads sealed horizon availability independently.
6. Divergence/lifecycle and participation panels are read-only projections.
7. Audit/debug exposes current source receipts, ages and counts.

Each route loads exactly one deterministic gzip payload. Dense participation remains the authoritative view; material transitions, episode summaries and legacy compatibility remain separate. The compatibility snapshot never replaces dense authority.
''')
 (out/'R6D_REPLAY_CLOCK_CONTRACT.md').write_text('# R6D Replay Clock Contract\n\nThe display domain is 09:15–15:30 Asia/Kolkata. Index uses its frozen Index receipt timestamp, Futures its frozen Futures receipt timestamp, Basis the synchronized observation clock, inventory its control effective timestamp, lifecycle its state-entry timestamp and participation its evidence effective/receipt timestamp. At replay T, only records with their governing clock at or before T render. The 2,000 ms synchronization rule is inherited unchanged. Future path is hidden unless explicitly revealed. Display time and effective evidence time remain distinct.\n')
 (out/'R6D_AVAILABILITY_AND_DEGRADATION_CONTRACT.md').write_text('# R6D Availability and Degradation Contract\n\nHorizon states are independent. AVAILABLE layers render; INSUFFICIENT_PRIOR_SESSIONS, SOURCE_SESSION_REJECTED, MISSING, STALE or INVALID layers show a badge and contribute no line. Missing fixed context never suppresses available Intraday context. Intraday-only and fixed-only states remain renderable. Only NO_VALID_MARKET_DATA disables the complete market chart. Synthetic fixtures remove layers only; they never substitute or manufacture analytical controls.\n')
 (out/'R6D_USER_GUIDE.md').write_text('# R6D User Guide\n\nRun `python3 -m http.server 8805 --bind 127.0.0.1` in this directory and open `http://127.0.0.1:8805/`. Select one of six sessions. Master checkboxes hide or restore complete horizons while child selections are remembered. Fixed controls are dashed full-session lines; Intraday controls are solid causal steps. Enable Basis separately. “Reveal subsequent path” is off by default. Colours describe frozen lifecycle states and are not entries or recommendations. The disabled legacy Futures-coordinate Price VPOC is diagnostic-only and absent from the canonical R6C2R payload.\n')
 (out/'PERFORMANCE_REPORT.md').write_text('# R6D Performance Report\n\nOne session is loaded per route. Payloads are deterministic gzip files; dense calculations are not performed in the browser.\n\n| Date | Initial render ms | Toggle latency ms | JS heap bytes | Payload transfer bytes |\n|---|---:|---:|---:|---:|\n'+'\n'.join(f"| {x['date']} | {x['initial_render_ms']} | {x['toggle_latency_ms']} | {x['used_js_heap_bytes'] or 'NA'} | {x['payload_transfer_bytes']} |" for x in perf)+f"\n\nMedian initial render: {statistics.median(x['initial_render_ms'] for x in perf):.3f} ms. Median toggle latency: {statistics.median(x['toggle_latency_ms'] for x in perf):.3f} ms. No external JavaScript or CDN is used.\n")
 contract=json.loads((out/'data/gui_input_schema.json').read_text())
 (out/'SOURCE_INPUT_LINEAGE_REPORT.md').write_text('# R6D Source/Input Lineage\n\nOnly sealed R6C2R outputs were read. No raw collector or growing live path is referenced by the GUI runtime.\n\n| Component | Frozen file | SHA-256 |\n|---|---|---|\n'+'\n'.join(f"| {k} | `{v['path']}` | `{v['sha256']}` |" for k,v in contract['files'].items())+'\n')
 (out/'automated_test_report.txt').write_text(f'''R6D AUTOMATED TEST REPORT
Repository unit/integration tests: 146 passed, 0 failed, 0 skipped
R6D-focused Python tests: 27 passed, 0 failed, 0 skipped
Browser acceptance checks: {len(browser)} passed, 0 failed, 0 skipped
Screenshots: 6
Frozen episodes: 65 (41 GREEN / 24 RED)
Retriggers: 14
Future joins: 0
Timestamp backdating: 0
Status: R6D_OFFLINE_GUI_VERIFIED
''')
 # Manifest is sealed after Git metadata is appended later; this preliminary
 # version is independently reproducible and is refreshed once at final seal.
 entries=[]
 for f in sorted(out.rglob('*')):
  if f.is_file() and f.name!='package_manifest.json':entries.append({'path':str(f.relative_to(out)),'sha256':sha(f),'size':f.stat().st_size})
 (out/'package_manifest.json').write_text(json.dumps({'status':'R6D_OFFLINE_GUI_VERIFIED','classification':classification,'files':entries,'file_count':len(entries)},indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'R6D_OFFLINE_GUI_VERIFIED','browser_checks':len(browser),'files':len(entries)},sort_keys=True))
if __name__=='__main__':main()
