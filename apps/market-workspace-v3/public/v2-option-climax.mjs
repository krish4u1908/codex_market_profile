// Separately named display research policy. Never changes a native V2 call.
import {atOrBefore} from './series.mjs';

export const OPTION_CLIMAX_POLICY = Object.freeze({
  id:'CE_PE_CLIMAX_DISPLAY_V1', volumeThreshold:2.5, oiThreshold:3,
  minimumOiPercent:0.5, windowMilliseconds:300000, baselineWindows:4,
});
export const OPTION_CLIMAX_TYPES = Object.freeze([
  {key:'ce-volume',side:'CE',metric:'volume',label:'CE volume',short:'CE VOL',color:'#ffb357',glyph:'●',symbol:'circle'},
  {key:'pe-volume',side:'PE',metric:'volume',label:'PE volume',short:'PE VOL',color:'#b7a1ff',glyph:'●',symbol:'circle'},
  {key:'ce-additions',side:'CE',metric:'additions',label:'CE +OI',short:'CE +OI',color:'#ffb357',glyph:'▲',symbol:'triangle'},
  {key:'ce-reductions',side:'CE',metric:'reductions',label:'CE −OI',short:'CE −OI',color:'#ffb357',glyph:'▼',symbol:'triangle',rotate:180},
  {key:'pe-additions',side:'PE',metric:'additions',label:'PE +OI',short:'PE +OI',color:'#b7a1ff',glyph:'▲',symbol:'triangle'},
  {key:'pe-reductions',side:'PE',metric:'reductions',label:'PE −OI',short:'PE −OI',color:'#b7a1ff',glyph:'▼',symbol:'triangle',rotate:180},
]);
const finite=Number.isFinite;
const nonnegative=n=>finite(n)&&n>=0;
const median=values=>{const sorted=values.slice().sort((a,b)=>a-b);return (sorted[1]+sorted[2])/2;};

function valueFor(row,type) {
  const side=type.side.toLowerCase();
  if(row[side+'_coverage']!==4 || !finite(row.fixed_atm))return null;
  if(type.metric==='volume') {
    const amount=row[side+'_volume_5m'];
    return nonnegative(amount)?{amount,oiPercent:null}:null;
  }
  const additions=row[side+'_oi_additions_5m'],reductions=row[side+'_oi_reductions_5m'];
  const net=row[side+'_oi_delta_5m'],oi=row[side+'_oi'];
  if(!nonnegative(additions)||!nonnegative(reductions)||!finite(net)||!finite(oi)||oi<=0)return null;
  if(Math.abs(additions-reductions-net)>1e-7*Math.max(1,additions,reductions))return null;
  const startingOi=oi-net;
  if(startingOi<=0)return null;
  const amount=type.metric==='additions'?additions:reductions;
  return {amount,oiPercent:amount/startingOi*100,startingOi,net};
}

export function optionClimaxPoints(contexts,prices,session,selection={}) {
  const points=[],published=new Map(),lastHit=new Map();
  const open=Date.parse(`${session}T09:45:00+05:30`),close=Date.parse(`${session}T15:30:00+05:30`);
  const selectionAt=Date.parse(selection.selected_at);
  for(const row of contexts.slice().sort((a,b)=>a.x-b.x)) {
    const cutoff=Date.parse(row.input_cutoff);
    if(row.history_origin==='RECONSTRUCTED_INPUT_HISTORY' || row.session!==session || !finite(row.x)
      || !finite(cutoff) || cutoff<open || cutoff>close || cutoff>row.x || published.has(cutoff))continue;
    // First native publication for a cutoff is immutable. A late dependency
    // never retroactively creates an annotation at an earlier publication.
    const prior=Array.from({length:OPTION_CLIMAX_POLICY.baselineWindows},(_,i)=>published.get(cutoff-(i+1)*OPTION_CLIMAX_POLICY.windowMilliseconds));
    if(prior.every(r=>r&&r.x<=row.x&&r.fixed_atm===row.fixed_atm)
      && (!finite(selectionAt)||cutoff-25*60000>=selectionAt)) {
      for(const type of OPTION_CLIMAX_TYPES) {
        const current=valueFor(row,type),history=prior.map(r=>valueFor(r,type));
        if(!current||history.some(r=>!r))continue;
        const baseline=median(history.map(r=>r.amount));
        if(baseline<=0)continue;
        const ratio=current.amount/baseline;
        const threshold=type.metric==='volume'?OPTION_CLIMAX_POLICY.volumeThreshold:OPTION_CLIMAX_POLICY.oiThreshold;
        if(!finite(ratio)||ratio<threshold||(type.metric!=='volume'&&current.oiPercent<OPTION_CLIMAX_POLICY.minimumOiPercent))continue;
        const last=lastHit.get(type.key);
        const isEpisodeStart=last===undefined||cutoff<last||cutoff-last>OPTION_CLIMAX_POLICY.windowMilliseconds;
        lastHit.set(type.key,Math.max(cutoff,last??cutoff));
        points.push({...current,id:`${session}:${type.key}:${cutoff}`,key:type.key,side:type.side,metric:type.metric,
          ratio,baseline,threshold,policy:OPTION_CLIMAX_POLICY.id,isEpisodeStart,
          x:row.x,t:row.context_published_at||row.t,input_cutoff:row.input_cutoff,
          price:finite(row.index)?row.index:atOrBefore(prices,row.x)?.i??null});
      }
    }
    published.set(cutoff,row);
  }
  return points;
}
