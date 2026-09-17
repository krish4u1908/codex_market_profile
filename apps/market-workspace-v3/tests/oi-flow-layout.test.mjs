import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const workspace=readFileSync(new URL('../components/market-workspace.tsx',import.meta.url),'utf8');
const ribbon=readFileSync(new URL('../components/option-oi-flow-ribbon.tsx',import.meta.url),'utf8');
const css=readFileSync(new URL('../app/globals.css',import.meta.url),'utf8');
const release=JSON.parse(readFileSync(new URL('../public/gui-release.json',import.meta.url),'utf8'));

test('3.0.12 keeps the OI histogram in the existing price-frame order',()=>{
  const basis=workspace.indexOf('<PriceBasisRibbonCaption frame={frame}/>');
  const flow=workspace.indexOf('<OptionOiFlowRibbon frame={frame} min={min} max={max}/>');
  const bubbles=workspace.indexOf('<EntryBubbleReview frame={frame}');
  assert.ok(basis>=0&&flow>basis&&bubbles>flow);
});

test('3.0.12 gives PE/CE lanes more height and horizontal plot width',()=>{
  assert.match(ribbon,/barMaxWidth:7/);
  assert.match(ribbon,/grid:\[\{left:36,right:10,top:4,height:46\},\{left:36,right:10,top:58,height:46\}\]/);
  assert.match(ribbon,/height=\{108\}/);
  assert.match(css,/\.option-oi-flow-ribbon \.plot\{height:108px!important;min-height:108px!important\}/);
});

test('responsive price sizing targets only the main price plot',()=>{
  assert.doesNotMatch(css,/\.price-panel \.plot\{height:(?:390|300)px!important\}/);
  assert.match(css,/\.price-panel > \.plot\{height:390px!important\}/);
  assert.match(css,/\.price-panel > \.plot\{height:300px!important\}/);
  assert.match(css,/\.chart-card\.chart-expanded > \.plot\{height:75dvh!important/);
});

test('3.0.12 OI-flow layout remains present in the newer GUI release',()=>{
  assert.equal(release.optionOiFlowPolicy,'NEAR_OTM_OPTION_OI_FLOW_1M_V1');
  assert.match(release.version,/^3\.0\.18-/);
});
