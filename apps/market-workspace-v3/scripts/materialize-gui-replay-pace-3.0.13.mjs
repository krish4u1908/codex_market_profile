import {readFileSync,writeFileSync} from 'node:fs';

const workspacePath=new URL('../components/market-workspace.tsx',import.meta.url);
let workspace=readFileSync(workspacePath,'utf8');
const replacements=[
  ["[speed,setSpeed]=useState('1')","[speed,setSpeed]=useState('15')"],
  ["),1000/Number(speed));","),Number(speed)*1000);"],
  ["<Choice label=\"Playback speed\" value={speed} onChange={setSpeed} choices={['1','2','5'].map(v=>({value:v,label:`${v} min/s`}))}/>","<Choice label=\"Replay pace\" value={speed} onChange={setSpeed} choices={['1','15','30'].map(v=>({value:v,label:`1m / ${v}s`}))}/>"]
];
for(const [from,to] of replacements){
  if(workspace.includes(to))continue;
  if(!workspace.includes(from))throw new Error(`Expected 3.0.12 replay token missing: ${from}`);
  workspace=workspace.replace(from,to);
}
writeFileSync(workspacePath,workspace);

const replaceRelease=(relative)=>{
  const path=new URL(relative,import.meta.url);
  const before=readFileSync(path,'utf8');
  if(before.includes('3.0.13-gui-replay-pace'))return;
  if(!before.includes('3.0.12-gui-oi-flow-layout'))throw new Error(`Expected 3.0.12 release token missing in ${relative}`);
  writeFileSync(path,before.replaceAll('3.0.12-gui-oi-flow-layout','3.0.13-gui-replay-pace'));
};
for(const relative of [
  '../../market-core-v3/deploy/update_data.py',
  '../../market-core-v3/deploy/update_gui.py',
  '../../market-core-v3/indicator-release.json',
  '../../market-core-v3/scripts/build_gui_update.py',
  '../../market-core-v3/DATA_UPDATE.md',
]) replaceRelease(relative);
