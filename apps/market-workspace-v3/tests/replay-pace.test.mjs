import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const workspace=readFileSync(new URL('../components/market-workspace.tsx',import.meta.url),'utf8');
const release=JSON.parse(readFileSync(new URL('../public/gui-release.json',import.meta.url),'utf8'));

test('replay defaults to one recorded minute every 15 real seconds',()=>{
  assert.match(workspace,/\[speed,setSpeed\]=useState\('15'\)/);
  assert.match(workspace,/\),Number\(speed\)\*1000\);/);
});

test('replay pace offers 1s, 15s and 30s per market minute',()=>{
  assert.match(workspace,/Choice label="Replay pace"/);
  assert.match(workspace,/\['1','15','30'\]\.map\(v=>\(\{value:v,label:`1m \/ \$\{v\}s`\}\)\)/);
});

test('manual replay step sizes remain unchanged',()=>{
  assert.match(workspace,/\['1','5','10'\]\.map\(v=>\(\{value:v,label:`\$\{v\}m step`\}\)\)/);
});

test('release identifies the GUI-only replay pace revision',()=>{
  assert.equal(release.version,'3.0.13-gui-replay-pace');
});
