"use client";

// Additive display-only integration of the frozen v0.1.3 research timelines.
// Neither this module nor its fixture modifies V1/V2 calls, scores, or core state.
import {useEffect,useMemo,useState} from 'react';
import type {Frame} from './market-types';

const FIXTURE_URL='/oi-pressure-reference-v1.json';
export const layerNames:Record<string,string>={
  MICRO_FIXED4_1M:'Fixed 4 · 1m transition',
  NEAR_DYN4_5M:'Dynamic ATM · 5m',
  BROAD_FULL_10M:'Full chain · 10m',
  BULL_FIXED4_FAST:'Bull · fixed 4 fast',
  BULL_DYN4_NEAR:'Bull · dynamic ATM',
  BULL_FULL_BROAD:'Bull · full chain',
  BEAR_FIXED2_FAST:'Bear · fixed 2 fast',
  BEAR_DYN4_REGIME:'Bear · dynamic ATM',
  BEAR_FULL_ACTIVITY:'Bear · activity',
};
export type RawWindow={v:number|null;state:string;ce_plus:number|null;ce_minus:number|null;pe_plus:number|null;pe_minus:number|null;activity_ratio:number|null;activity_quality:string|null};
export type RecordRow={x:number;source_x:number;score:number;prior_3m:number|null;layers:string[];raw1:RawWindow|null;raw5:RawWindow|null};
type SessionRows={kind:'normal'|'expiry';rows:RecordRow[]};
type Reference={schema:string;scope:string;outcome_fields_included:boolean;sessions:Record<string,SessionRows>};
let sharedRequest:Promise<Reference>|null=null;
function retrieve():Promise<Reference>{
  if(!sharedRequest)sharedRequest=fetch(FIXTURE_URL,{cache:'no-store'}).then(async res=>{
    if(!res.ok)throw new Error(`Research reference HTTP ${res.status}`);
    const data=await res.json() as Reference;
    if(data.schema!=='NIFTY_V3_OI_RESEARCH_REFERENCE_V1'||data.outcome_fields_included!==false||!data.sessions)
      throw new Error('Unexpected research reference schema');
    return data;
  });
  return sharedRequest;
}
const time=(x:number)=>new Date(x).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit',hour12:false});
const signed=(v:number|null|undefined,d=1)=>v==null?'—':`${v>0?'+':''}${v.toFixed(d)}`;
const lakh=(v:number|null)=>v==null?'—':`${(v/100000).toFixed(2)}L`;
const tone=(score:number)=>score>0?'bull':score<0?'bear':'neutral';
export const scoreLabel=(s:number)=>Math.abs(s)<35?'NEUTRAL':`${Math.abs(s)<70?'WATCH':Math.abs(s)<100?'HIGH':'VERY HIGH'} ${s>0?'BULL':'BEAR'}`;
function strength(raw:RawWindow|null){
  if(!raw||raw.v==null)return 'Unavailable';
  if(!['BULL FLOW','BEAR FLOW'].includes(raw.state))return 'Mixed / no joint direction';
  return `${Math.abs(raw.v)>=50?'Strong':Math.abs(raw.v)>=20?'Moderate':'Weak'} OI imbalance`;
}
function recentRow(rows:RecordRow[],cursor:number){
  let lo=0,hi=rows.length;
  while(lo<hi){const mid=(lo+hi)>>1;if(rows[mid].x<=cursor)lo=mid+1;else hi=mid;}
  const index=lo-1;
  if(index<0||cursor-rows[index].x>90000||rows[index].source_x>cursor)return {row:null,index:-1};
  return {row:rows[index],index};
}
export function persistence(rows:RecordRow[],index:number):string{
  if(index<0)return 'UNAVAILABLE';
  const s=rows[index].score;
  if(Math.abs(s)<35){
    for(let j=Math.max(0,index-4);j<index;j++)if(Math.abs(rows[j].score)>=70)return 'RESETTING';
    return 'NO REGIME';
  }
  let count=0;
  for(let j=index;j>=0&&j>=index-5;j--){
    if(Math.abs(rows[j].score)>=35&&Math.sign(rows[j].score)===Math.sign(s))count++;
    else break;
  }
  if(count>=3)return 'LOCKED';
  if(count>=2)return 'PERSISTING';
  if(index>0&&Math.abs(rows[index-1].score)>=35&&Math.sign(rows[index-1].score)===-Math.sign(s))return 'REVERSED';
  return 'DEVELOPING';
}
export function priceDisagreement(r:RecordRow){
  if(r.prior_3m==null)return 'PRIOR PRICE UNAVAILABLE';
  if(r.score<=-35&&r.prior_3m>0)return 'Bearish OI / price bouncing';
  if(r.score>=35&&r.prior_3m<0)return 'Bullish OI / price dipping';
  return 'No confirmed disagreement';
}
export function relation(r:RecordRow){
  const a=r.raw1?.v??0,b=r.raw5?.v??0;
  if(a*b<0)return 'Raw 1m / 5m disagree';
  const d=Math.sign(b||a);
  if(!d)return 'No joint raw direction';
  if(r.score===0)return `Raw ${d>0?'bull':'bear'} / unconfirmed`;
  return Math.sign(r.score)===d?'Raw and confirmed agree':'Raw and confirmed differ';
}
export function useStudy(frame:Frame|null,eligible:boolean){
  const [reference,setReference]=useState<Reference|null>(null);
  const [error,setError]=useState('');
  const active=eligible&&frame?.profile.instrument==='NIFTY'&&frame?.profile.version==='2.0.0';
  useEffect(()=>{
    if(!active)return;
    let stopped=false;
    retrieve().then(data=>{if(!stopped)setReference(data);}).catch(e=>{if(!stopped)setError(String(e.message||e));});
    return()=>{stopped=true;};
  },[active]);
  const series=active?reference?.sessions[frame!.session]:undefined;
  const matched=series?recentRow(series.rows,frame!.now):{row:null,index:-1};
  return {active,series,row:matched.row,index:matched.index,error,loading:active&&!reference&&!error};
}
export function RawCard({name,raw}:{name:string;raw:RawWindow|null}){
  const value=raw?.v;
  const t=value==null?'neutral':tone(value);
  return <article className={`oi-lens-card oi-lens-raw ${t}`}>
    <span className="oi-lens-overline">{name} · observational only</span>
    <strong className="oi-lens-value">{value==null?'—':signed(value,1)}</strong>
    <span className="oi-lens-emphasis">{raw?.state?.replaceAll('_',' ')||'UNAVAILABLE'}</span>
    <span className="oi-lens-caption">{strength(raw)} · not a confirmation vote</span>
    <div className="oi-lens-flows"><span>CE + {lakh(raw?.ce_plus??null)} · − {lakh(raw?.ce_minus??null)}</span><span>PE + {lakh(raw?.pe_plus??null)} · − {lakh(raw?.pe_minus??null)}</span></div>
    <small>{raw?.activity_quality?.replaceAll('_',' ')||'Activity baseline warming'} · {raw?.activity_ratio==null?'baseline warming / unavailable':`${raw.activity_ratio.toFixed(2)}× prior median`}</small>
  </article>;
}
function Chart({rows,now,frame}:{rows:RecordRow[];now:number;frame:Frame}){
  const visible=useMemo(()=>rows.filter(r=>r.x<=now),[rows,now]);
  const prices=useMemo(()=>frame.price.filter(r=>r.x<=now&&typeof r.i==='number'&&Number.isFinite(r.i)),[frame.price,now]);
  const start=rows[0]?.x??now,end=Date.parse(`${frame.session}T15:30:00+05:30`);
  const x=(t:number)=>44+Math.max(0,Math.min(1,(t-start)/Math.max(1,end-start)))*936;
  function path(points:{x:number;y:number|null}[],low:number,high:number,top=12,height=116){
    let d='',previous=false;
    for(const p of points){if(p.y==null||!Number.isFinite(p.y)){previous=false;continue;}
      const py=top+(1-(p.y-low)/(high-low||1))*height;
      d+=`${previous?'L':'M'}${x(p.x).toFixed(1)},${py.toFixed(1)} `;previous=true;
    }
    return d;
  }
  const values=prices.map(p=>p.i as number),min=values.length?Math.min(...values)-1:0,max=values.length?Math.max(...values)+1:1;
  const price=path(prices.map(p=>({x:p.x,y:p.i as number})),min,max);
  const model=path(visible.map(r=>({x:r.x,y:r.score})),-100,100);
  const raw1=path(visible.map(r=>({x:r.x,y:r.raw1?.v??null})),-100,100);
  const raw5=path(visible.map(r=>({x:r.x,y:r.raw5?.v??null})),-100,100);
  const cursor=x(now);
  return <div className="oi-lens-charts" aria-label="Observed price and OI research history, truncated at replay cursor">
    <div className="oi-lens-chart-head">NIFTY price <span>Actual replay data · no future observations</span></div>
    <svg role="img" aria-label="Observed NIFTY price up to current cursor" viewBox="0 0 1000 150" preserveAspectRatio="none"><path d="M44 70H980" className="oi-lens-gridline"/><path d={price} className="oi-lens-price-line"/><line x1={cursor} y1="4" x2={cursor} y2="130" className="oi-lens-cursor"/><text x="3" y="18" className="oi-lens-axis">{max.toFixed(0)}</text><text x="3" y="126" className="oi-lens-axis">{min.toFixed(0)}</text><text x="44" y="145" className="oi-lens-axis">09:46</text><text x="895" y="145" className="oi-lens-axis">15:30</text></svg>
    <div className="oi-lens-chart-head">OI structure <span>Frozen confirmed / raw 1m / raw 5m</span></div>
    <svg role="img" aria-label="Confirmed OI score and independent raw scores up to current cursor" viewBox="0 0 1000 150" preserveAspectRatio="none">
      {[0,35,70,-35,-70].map(y=><line key={y} x1="44" y1={12+(1-(y+100)/200)*116} x2="980" y2={12+(1-(y+100)/200)*116} className="oi-lens-gridline"/>)}
      <path d={model} className="oi-lens-model-line"/><path d={raw1} className="oi-lens-raw1-line"/><path d={raw5} className="oi-lens-raw5-line"/><line x1={cursor} y1="4" x2={cursor} y2="130" className="oi-lens-cursor"/><text x="3" y="18" className="oi-lens-axis">+100</text><text x="15" y="73" className="oi-lens-axis">0</text><text x="3" y="126" className="oi-lens-axis">−100</text><text x="44" y="145" className="oi-lens-axis">09:46</text><text x="895" y="145" className="oi-lens-axis">15:30</text>
    </svg><div className="oi-lens-legend"><span className="model">Confirmed model</span><span className="raw1">Raw 1m</span><span className="raw5">Raw 5m</span></div>
  </div>;
}

export function OiPressureStrip({frame,eligible,onOpen}:{frame:Frame;eligible:boolean;onOpen:()=>void}){
  const data=useStudy(frame,eligible);
  if(frame.profile.instrument!=='NIFTY'||frame.profile.version!=='2.0.0')return null;
  const r=data.row;
  return <section className="oi-lens-strip" aria-label="Independent OI research summary">
    <div className="oi-lens-strip-label"><strong>OI RESEARCH LENS</strong><small>Not the V2 reference call · raw adds zero votes</small></div>
    {r?<><div className={`oi-lens-strip-metric ${tone(r.score)}`}><span>CONFIRMED</span><b>{signed(r.score,0)} · {scoreLabel(r.score)}</b><small>{r.layers.length} active layer{r.layers.length===1?'':'s'}</small><div className="oi-lens-tags">{r.layers.map(layer=><span key={layer}>{layerNames[layer]||layer}</span>)}</div></div><div className="oi-lens-strip-metric"><span>RAW 1M</span><b>{signed(r.raw1?.v)} · {r.raw1?.state?.replaceAll('_',' ')||'Unavailable'}</b></div><div className="oi-lens-strip-metric"><span>RAW 5M</span><b>{signed(r.raw5?.v)} · {r.raw5?.state?.replaceAll('_',' ')||'Unavailable'}</b></div></>
      :<div className="oi-lens-strip-wait">{(frame.fixedOiPressure?.at(-1)&&frame.now-frame.fixedOiPressure.at(-1)!.x<=90000)?`Fixed 4 · raw 1m ${signed(frame.fixedOiPressure.at(-1)?.raw1?.v)} / raw 5m ${signed(frame.fixedOiPressure.at(-1)?.raw5?.v)} · historical confirmation unavailable`:data.error?`Reference unavailable: ${data.error}`:!data.active?'Historical reference only; no live OI research model':data.loading?'Loading frozen research…':!data.series?'No frozen reference for this session':'Awaiting matching OI publication'}</div>}
    <button className="oi-lens-open" onClick={onOpen} type="button">Open OI research →</button>
  </section>;
}

export function OiPressureResearch({frame,eligible}:{frame:Frame;eligible:boolean}){
  const data=useStudy(frame,eligible);
  const latest=frame.fixedOiPressure?.at(-1);
  const fresh=latest&&frame.now-latest.x<=90000?latest:null;
  if(!data.row||!data.series)return <section className="oi-lens-main"><h2>OI Pressure · NIFTY V2</h2><div className="oi-lens-cards"><RawCard name="RAW 1 MINUTE" raw={fresh?.raw1||null}/><RawCard name="RAW 5 MINUTES" raw={fresh?.raw5||null}/></div><p>{data.error||(!data.active?'Raw fixed-four pressure uses current receipts in both live and replay. Confirmation scores and layer tags require a matching historical prototype reference; a live confirmation engine was not supplied.':data.loading?'Loading the historical research reference…':!data.series?'No verified historical research reference for this session.':'No OI publication available at this replay timestamp.')}</p><p className="oi-lens-caution">The original reference call and core calculations are unchanged.</p></section>;
  const r=data.row,series=data.series,s=r.score,active=r.layers,per=persistence(series.rows,data.index),dis=priceDisagreement(r),rel=relation(r);
  const allLayers=series.kind==='expiry'?['MICRO_FIXED4_1M','NEAR_DYN4_5M','BROAD_FULL_10M']:['BULL_FIXED4_FAST','BULL_DYN4_NEAR','BULL_FULL_BROAD','BEAR_FIXED2_FAST','BEAR_DYN4_REGIME','BEAR_FULL_ACTIVITY'];
  const history=series.rows.slice(Math.max(0,data.index-5),data.index+1);
  return <section className="oi-lens-main" aria-label="NIFTY V2 OI pressure research display">
    <div className="oi-lens-top"><div><span className="oi-lens-overline">NIFTY V2 · HISTORICAL RESEARCH VIEW</span><h2>Price vs positioning · OI Pressure Lens</h2><p>Frozen prototype v0.1.3; synchronized to this workspace replay cursor.</p></div><span className="oi-lens-stamp">OI receipt {time(r.source_x)} IST · replay {time(frame.now)} IST</span></div>
    <div className="oi-lens-cards"><article className={`oi-lens-card confirmed ${tone(s)}`}><span className="oi-lens-overline">CONFIRMED · ORIGINAL FROZEN MODEL</span><strong className="oi-lens-value">{signed(s,0)}</strong><span className="oi-lens-emphasis">{scoreLabel(s)}</span><span className="oi-lens-caption">{active.length} confirming layer{active.length===1?'':'s'} · raw scores do not contribute</span><div className="oi-lens-tags">{active.length?active.map(layer=><span key={layer}>{layerNames[layer]||layer}</span>):<span>No active confirmation</span>}</div></article><RawCard name="RAW 1 MINUTE" raw={r.raw1}/><RawCard name="RAW 5 MINUTES" raw={r.raw5}/></div>
    <div className="oi-lens-statebar"><div><small>SCORE PERSISTENCE</small><strong>{per}</strong></div><div><small>PRICE / OI DISAGREEMENT</small><strong>{dis}</strong></div><div><small>RAW vs CONFIRMED</small><strong>{rel}</strong></div><div><small>PREVIOUS 3M NIFTY</small><strong>{signed(r.prior_3m,2)} pts</strong></div></div>
    <div className="oi-lens-layer-grid" aria-label="Prototype confirmation layers">{allLayers.map(key=><div key={key} className={active.includes(key)?'active':''}><span>{layerNames[key]}</span><b>{active.includes(key)?'ACTIVE':'off'}</b></div>)}</div>
    <p className="oi-lens-caption">{series.kind==='expiry'?'Expiry':'Normal-session'} layer set · LOCKED means three consecutive same-direction score observations; it is not a forecast.</p>
    <Chart rows={series.rows} now={frame.now} frame={frame}/>
    <div className="oi-lens-history"><table aria-label="Recent OI observations"><thead><tr><th>IST</th><th>Prior 3m price</th><th>Frozen score</th><th>Raw 1m</th><th>Raw 5m</th><th>Active layers</th></tr></thead><tbody>{history.map(row=><tr key={row.x}><td>{time(row.x)}</td><td>{signed(row.prior_3m,2)}</td><td>{signed(row.score,0)}</td><td>{signed(row.raw1?.v)}</td><td>{signed(row.raw5?.v)}</td><td>{row.layers.length}</td></tr>)}</tbody></table></div>
    <p className="oi-lens-caution"><strong>Data boundary:</strong> Frozen historical rebuilt-session reference, matched by session/date and causal receipt time. Do not compare against a different replay import. No future returns, simulated probability or trade recommendation is used here. The independent raw four-strike basket is not the native near-OTM three-strike ribbon.</p>
  </section>;
}
