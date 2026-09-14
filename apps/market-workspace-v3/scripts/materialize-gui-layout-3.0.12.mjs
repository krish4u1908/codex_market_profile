import {readFileSync,writeFileSync} from 'node:fs';

const workspacePath=new URL('../components/market-workspace.tsx',import.meta.url);
let workspace=readFileSync(workspacePath,'utf8');
const importAnchor="import {EntryBubbleReview} from './entry-bubbles';\n";
const importLine="import {OptionOiFlowRibbon} from './option-oi-flow-ribbon';\n";
if(!workspace.includes(importLine)){
  if(!workspace.includes(importAnchor))throw new Error('Market workspace import anchor missing');
  workspace=workspace.replace(importAnchor,importAnchor+importLine);
}
const placementAnchor='      <PriceBasisRibbonCaption frame={frame}/>\n';
const placementLine='      <OptionOiFlowRibbon frame={frame} min={min} max={max}/>\n';
if(!workspace.includes(placementLine)){
  if(!workspace.includes(placementAnchor))throw new Error('Price ribbon placement anchor missing');
  workspace=workspace.replace(placementAnchor,placementAnchor+placementLine);
}
writeFileSync(workspacePath,workspace);

const cssPath=new URL('../app/globals.css',import.meta.url);
let css=readFileSync(cssPath,'utf8');
for(const token of [
  '.price-panel .plot{height:390px!important}',
  '.price-panel .plot{height:300px!important}',
  '.chart-card.chart-expanded .plot{height:75dvh!important;min-height:360px}',
]) if(!css.includes(token))throw new Error(`Expected base CSS token missing: ${token}`);

css=css
  .replace('.chart-card:fullscreen .plot{height:calc(100dvh - 110px)!important}', '.chart-card:fullscreen > .plot{height:calc(100dvh - 110px)!important}')
  .replace('.price-panel .plot{height:390px!important}', '.price-panel > .plot{height:390px!important}')
  .replace('.price-panel .plot{height:300px!important}', '.price-panel > .plot{height:300px!important}')
  .replace('.chart-card.chart-expanded .plot{height:75dvh!important;min-height:360px}', '.chart-card.chart-expanded > .plot{height:75dvh!important;min-height:360px}')
  .replaceAll('.price-panel:fullscreen .plot{', '.price-panel:fullscreen > .plot{');

const finalOiCss='.option-oi-flow-ribbon{padding:0 0 6px;border-top:1px solid #1b2b3f}.option-oi-flow-caption{display:flex;align-items:center;justify-content:space-between;gap:5px 16px;padding:6px 15px 2px;color:#aebfd4;font-size:.68rem;line-height:1.4}.option-oi-flow-caption>div{display:flex;align-items:center;gap:6px 12px;flex-wrap:wrap}.option-oi-flow-caption strong{font-weight:500;color:#dce7f6;white-space:nowrap}.option-oi-flow-caption span{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-variant-numeric:tabular-nums}.option-oi-flow-caption i{display:inline-block;width:11px;height:5px;border-radius:1px}.oi-flow-positive{background:rgba(70,216,164,.68)}.oi-flow-negative{background:rgba(255,118,140,.68)}.option-oi-flow-latest{justify-content:flex-end}.option-oi-flow-plot{position:relative}.option-oi-flow-ribbon .plot{height:108px!important;min-height:108px!important}.option-oi-flow-labels{position:absolute;z-index:2;pointer-events:none;left:10px;top:0;height:108px;width:22px;display:grid;grid-template-rows:1fr 1fr;align-items:center;color:#8da5c1;font-size:.66rem;font-weight:500}.option-oi-flow-labels span{display:flex;align-items:center;height:100%}.option-oi-flow-status{padding:8px 15px 4px;color:#859bb7;font-size:.7rem}.price-panel:fullscreen > .plot{height:calc(100dvh - 383px)!important}.price-panel:fullscreen .option-oi-flow-ribbon .plot{height:108px!important;min-height:108px!important}@media(max-width:640px){.option-oi-flow-caption{padding:6px 10px 2px;align-items:flex-start;flex-direction:column;gap:4px}.option-oi-flow-latest{justify-content:flex-start!important}.option-oi-flow-labels{left:8px}.option-oi-flow-status{padding-left:10px}.price-panel:fullscreen > .plot{height:calc(100dvh - 478px)!important}.price-panel:fullscreen .option-oi-flow-ribbon .plot{height:108px!important;min-height:108px!important}}';
const lines=css.split('\n');
const existing=lines.findIndex(line=>line.startsWith('.option-oi-flow-ribbon{'));
if(existing>=0)lines[existing]=finalOiCss;
else {
  const vix=lines.findIndex(line=>line.startsWith('.vix-ribbon-caption{'));
  if(vix<0)throw new Error('VIX ribbon CSS anchor missing');
  lines.splice(vix+1,0,finalOiCss);
}
writeFileSync(cssPath,lines.join('\n'));

const replaceIn=(relative,from,to)=>{
  const path=new URL(relative,import.meta.url);
  const before=readFileSync(path,'utf8');
  if(before.includes(to))return;
  if(!before.includes(from))throw new Error(`Expected release token missing in ${relative}: ${from}`);
  writeFileSync(path,before.replaceAll(from,to));
};
const oldRelease='3.0.11-gui-minute-oi-flow';
const newRelease='3.0.12-gui-oi-flow-layout';
for(const relative of [
  '../../market-core-v3/deploy/update_data.py',
  '../../market-core-v3/deploy/update_gui.py',
  '../../market-core-v3/indicator-release.json',
  '../../market-core-v3/scripts/build_gui_update.py',
  '../../market-core-v3/DATA_UPDATE.md',
]) replaceIn(relative,oldRelease,newRelease);
replaceIn('../../market-core-v3/NIFTY_REPLAY_RECOVERY.md','GUI 3.0.11 package','GUI 3.0.12 package');
