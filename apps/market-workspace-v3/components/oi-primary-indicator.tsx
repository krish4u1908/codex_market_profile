"use client";
// Additive V3 Market-tab display. Uses exactly the existing ChartPanel/Plot/ECharts
// implementation so crosshair, zoom, tooltips and time scales match the price chart.
// No core, published call, confirmation, option-report source or model is mutated.
import {useMemo,useState} from 'react';
import type {EChartsOption} from 'echarts';
import {ChartPanel,Plot,baseChart,line} from './market-chart';
import {COLORS,clock,compact,fmt,type Frame} from './market-types';
import {useStudy,layerNames,scoreLabel,persistence,priceDisagreement,relation,type RecordRow,type RawWindow} from './oi-pressure-research';
import {nativePressureSeries} from '../public/oi-native-pressure.mjs';

type Point={x:number;v:number|null};
type Flow={plus:number;minus:number;lastAt?:number};
type NativeRow={x:number;minute:number;ce:Flow|null;pe:Flow|null;score:number|null;state:string;window:number};
type Side='CE'|'PE';
type Window=1|5;
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);
const availableAt=(row:Record<string,any>,now:number)=>{
  if(row.available_at==null)return true;
  const at=typeof row.available_at==='number'?row.available_at:Date.parse(row.available_at);
  return Number.isFinite(at)&&at<=now;
};
const small=(n:number|null|undefined)=>n==null?'—':compact(n);
const scoreText=(v:number|null|undefined)=>v==null?'—':`${v>0?'+':''}${v.toFixed(1)}`;
const asPoint=(x:number,v:number|null):Point=>({x,v});
const actual=(list:Point[],now:number,min:number,max:number)=>list.filter(p=>p.x<=now&&p.x>=min&&p.x<=max&&finite(p.v));
const mostRecent=<T,>(list:T[]):T|null=>list.length?list[list.length-1]:null;

// Feed missing observations into the series as null (not zero), including every
// missing minute in a 5-minute window. No straight line may bridge them.
function pointsWithGaps(points:Point[]):Point[]{
  const sorted=points.slice().sort((a,b)=>a.x-b.x),out:Point[]=[];
  let prior:Point|null=null;
  for(const row of sorted){
    if(prior&&row.x-prior.x>90000)out.push({x:prior.x+60000,v:null});
    out.push(row);
    prior=row;
  }
  return out;
}
function chartOption(min:number,max:number,series:{name:string;rows:Point[];color:string;dashed?:boolean}[],axis:'value'|'score'|'oi') : EChartsOption{
  const base=baseChart(min,max);
  const data=series.flatMap(s=>actual(s.rows,max,min,max).map(row=>Math.abs(row.v||0)));
  const extent=axis==='oi'?Math.max(1,...data)*1.12:undefined;
  return {...base,
    yAxis:axis==='score'?{type:'value',min:-100,max:100,splitNumber:4,axisLabel:{color:'#98a9bf'},splitLine:{lineStyle:{color:'#26394a'}}}
      :axis==='oi'?{type:'value',min:-extent!,max:extent!,splitNumber:4,axisLabel:{color:'#98a9bf',formatter:(v:number)=>compact(v)},splitLine:{lineStyle:{color:'#26394a'}}}
        :base.yAxis,
    series:series.map(s=>line(s.name,pointsWithGaps(s.rows),'v',s.color,{
      sampling:'none',lineStyle:{color:s.color,width:2,type:s.dashed?'dashed':'solid'},showSymbol:false,
      ...(axis==='score'?{markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#607589',width:1,type:'dotted'},data:[{yAxis:0}]}}:{})
    }))
  };
}
function Lane({title,subtitle,series,unit,min,max,axis='value',empty}:{title:string;subtitle:string;series:{name:string;rows:Point[];color:string;dashed?:boolean}[];unit:string;min:number;max:number;axis?:'value'|'score'|'oi';empty?:string}){
  const option=useMemo(()=>chartOption(min,max,series,axis),[min,max,series,axis]);
  const any=series.some(s=>actual(s.rows,max,min,max).length>0);
  return <ChartPanel title={title} subtitle={subtitle} colour={series[0]?.color||COLORS.muted} className="oi-primary-lane">
    <div className="oi-primary-legend">{series.map(s=><span key={s.name}><i style={{background:s.color}}/>{s.name}</span>)}<span className="oi-primary-unit">{unit}</span></div>
    {any?<Plot option={option} height={185} label={`${title} actual data on existing synchronized market time cursor; no future observations`}/>
      :<p className="oi-primary-empty">{empty||'No complete, available source readings at this replay cursor. Nothing has been estimated.'}</p>}
  </ChartPanel>;
}

export function OiPrimaryIndicator({frame,eligible,min,max,showVix=true,showBasis=true}:{frame:Frame;eligible:boolean;min:number;max:number;showVix?:boolean;showBasis?:boolean}){
  const study=useStudy(frame,eligible);
  const [window,setWindow]=useState<Window>(5);
  const [basket,setBasket]=useState<'study4'|'native3'>('study4');
  const isNifty=frame.profile.instrument==='NIFTY'&&frame.profile.version==='2.0.0';
  const now=frame.now;
  const price=frame.price;
  const vix=useMemo(()=>frame.cash.filter(row=>finite(row.x)&&row.x<=now&&finite(row.vix_close)&&availableAt(row,now))
    .map(row=>asPoint(row.x,row.vix_close)),[frame.cash,now]);
  const basis=useMemo(()=>price.filter(row=>finite(row.x)&&row.x<=now&&finite(row.b))
    .map(row=>asPoint(row.x,row.b)),[price,now]);
  const native1=useMemo(()=>nativePressureSeries(frame.optionOiFlow,now,1) as NativeRow[],[frame.optionOiFlow,now]);
  const native5=useMemo(()=>nativePressureSeries(frame.optionOiFlow,now,5) as NativeRow[],[frame.optionOiFlow,now]);
  if(!isNifty)return null;
  // A frozen score is shown only for the previously whitelisted recorded session.
  // Basket selection is explicit; unavailable fixed-four readings never fall back to native three.
  const studyRows=study.active&&study.series?study.series.rows.filter(r=>r.x<=now&&r.source_x<=now):null;
  const useFixed=basket==='study4';
  const native=window===1?native1:native5;
  const fixedRows=(frame.fixedOiPressure||[]).filter(r=>r.x<=now);
  const currentFixed=mostRecent(fixedRows);
  const freshFixed=currentFixed&&now-currentFixed.x<=90000?currentFixed:null;
  const frozen=fixedRows.map(r=>({x:r.x,w:window===1?r.raw1:r.raw5}));
  const side=(key:'ce'|'pe',field:'plus'|'minus'):Point[]=> {
    const property=`${key}_${field}` as 'ce_plus'|'ce_minus'|'pe_plus'|'pe_minus';
    return useFixed?frozen.map(r=>asPoint(r.x,r.w?.[property]??null))
      :native.map(r=>asPoint(r.x,r[key]?.[field]??null));
  };
  // Removal is drawn below zero on the y-axis; cards always show unsigned gross.
  const cePlus=side('ce','plus'),ceMinus=side('ce','minus').map(p=>asPoint(p.x,p.v==null?null:-p.v));
  const pePlus=side('pe','plus'),peMinus=side('pe','minus').map(p=>asPoint(p.x,p.v==null?null:-p.v));
  const latestNative=mostRecent(native);
  const studyCurrent=study.row;
  const currentRaw:RawWindow|null=useFixed?(window===1?freshFixed?.raw1:freshFixed?.raw5)||null:null;
  const latestFlow=(key:Side):Flow|null=>{
    if(!useFixed)return latestNative?.[key.toLowerCase() as 'ce'|'pe']||null;
    const plus=key==='CE'?currentRaw?.ce_plus:currentRaw?.pe_plus;
    const minus=key==='CE'?currentRaw?.ce_minus:currentRaw?.pe_minus;
    return finite(plus)&&finite(minus)?{plus,minus}:null;
  };
  const flowFresh=(key:Side):Flow|null=>{
    const row=latestFlow(key);
    if(!row)return null;
    if(useFixed)return row;
    return latestNative&&now-latestNative.x<=90000?row:null;
  };
  const ce=flowFresh('CE'),pe=flowFresh('PE');
  const previousScores=studyRows||[];
  const confirmedSeries:Point[]=previousScores.map((r:RecordRow)=>asPoint(r.x,r.score));
  const raw1Series:Point[]=useFixed?fixedRows.map(r=>asPoint(r.x,r.raw1?.v??null))
    :native1.map(r=>asPoint(r.x,r.score));
  const raw5Series:Point[]=useFixed?fixedRows.map(r=>asPoint(r.x,r.raw5?.v??null))
    :native5.map(r=>asPoint(r.x,r.score));
  const latestVix=mostRecent(vix),latestBasis=mostRecent(basis);
  const rawScore=useFixed?(window===1?freshFixed?.raw1?.v:freshFixed?.raw5?.v):latestNative?.score;
  const sourceLabel=useFixed?'FIXED 4 · 09:45 · PROTOTYPE':'NATIVE NEAR-OTM 3 · MOVING';
  return <section className="oi-primary" aria-label="NIFTY primary VIX basis and option OI research indicator">
    <div className="oi-primary-head"><div><span className="oi-primary-eyebrow">PRIMARY INDICATOR · NIFTY V2 · DISPLAY ONLY</span><h2>CE / PE delta-OI pressure</h2><p>CE and PE gross OI changes with separate 1m and 5m pressure. Select a basket to inspect its own readings.</p></div>
      <div className="oi-primary-actions"><div className="oi-primary-segment" role="group" aria-label="Gross OI aggregation"><span>Gross OI</span><button type="button" aria-pressed={window===1} onClick={()=>setWindow(1)}>1m</button><button type="button" aria-pressed={window===5} onClick={()=>setWindow(5)}>5m</button></div>
        {<div className="oi-primary-segment" role="group" aria-label="Select OI basket"><span>Basket</span><button type="button" aria-pressed={basket==='study4'} onClick={()=>setBasket('study4')}>Fixed 4</button><button type="button" aria-pressed={basket==='native3'} onClick={()=>setBasket('native3')}>Native 3</button></div>}</div></div>
    <div className="oi-primary-source"><strong>{sourceLabel}</strong><span>Cursor {clock(now,true)} IST</span><span>OI receipt {clock(useFixed?currentFixed?.x:latestNative?.x,true)} IST</span><span>5m = five 1m gross flows · missing receipts remain gaps</span></div>
    {useFixed&&<div className="oi-primary-basket" aria-label="Fixed four-strike basket"><span>CE: {(frame.selection.CE||[]).map((c:any)=>fmt(c.strike,0)).join(' · ')||'Awaiting 09:45 selection'}</span><span>PE: {(frame.selection.PE||[]).map((c:any)=>fmt(c.strike,0)).join(' · ')||'Awaiting 09:45 selection'}</span></div>}
    <div className="oi-primary-metrics" aria-label="Current primary indicator readings">
      <div><span>India VIX</span><strong>{latestVix&&now-latestVix.x<=90000?fmt(latestVix.v):'—'}</strong><small>Published actual value</small></div>
      <div><span>Futures basis</span><strong>{latestBasis&&now-latestBasis.x<=90000?`${fmt(latestBasis.v)} pts`:'—'}</strong><small>Futures minus index</small></div>
      <div><span>CE gross +OI / −OI</span><strong>{ce?`${small(ce.plus)} / ${small(ce.minus)}`:'—'}</strong><small>{window}m · {sourceLabel}</small></div>
      <div><span>PE gross +OI / −OI</span><strong>{pe?`${small(pe.plus)} / ${small(pe.minus)}`:'—'}</strong><small>{window}m · {sourceLabel}</small></div>
      <div><span>Research score / raw</span><strong>{useFixed?`${scoreText(studyCurrent?.score)} / ${scoreText(rawScore)}`:`— / ${latestNative&&now-latestNative.x<=90000?scoreText(rawScore):'—'}`}</strong><small>{useFixed?'Historical score / independent raw':'Native raw only; no confirmed research score'}</small></div>
    </div>
    {useFixed&&studyCurrent?<div className="oi-primary-context" aria-label="Prototype score and layer tags">
      <strong className={studyCurrent.score>0?'bull':studyCurrent.score<0?'bear':'neutral'}>{scoreLabel(studyCurrent.score)} · {scoreText(studyCurrent.score)} <small>Historical prototype score</small></strong>
      <div className="oi-lens-tags">{studyCurrent.layers.length?studyCurrent.layers.map(key=><span key={key}>{layerNames[key]||key}</span>):<span>No confirmed layer</span>}</div>
      <span>Score persistence: {persistence(study.series!.rows,study.index)}</span><span>{priceDisagreement(studyCurrent)}</span><span>{relation(studyCurrent)}</span>
    </div>:useFixed?<p role="status" className="oi-lens-caption">{study.error|| (study.loading?'Loading the historical prototype reference…':'No historical confirmation score at this cursor. Fixed-four raw pressure below uses current report receipts.')}</p>:<p className="oi-lens-caption">Moving three-strike raw pressure · historical prototype score and layers do not apply to this basket.</p>}
    {useFixed&&<div className="oi-primary-raw-summary">{([1,5] as const).map(w=>{const raw=freshFixed?.[`raw${w}`] as RawWindow|undefined;return <div key={w}><span>RAW {w}M</span><strong>{scoreText(raw?.v)} · {raw?.state||'UNAVAILABLE'}</strong><small>{raw?.activity_quality||'Awaiting complete receipts'}{raw?.activity_ratio!=null?` · ${raw.activity_ratio.toFixed(2)}× prior activity`:''}</small></div>;})}</div>}
    <div className="oi-primary-stack">
      <div className="oi-primary-flow-pair">
      <Lane title={`CE +OI / −OI · ${window}m`} subtitle={`${sourceLabel} · additions above zero, removals below zero`} min={min} max={max} axis="oi" unit="Reported OI units" series={[{name:'CE +OI',rows:cePlus,color:'#f4b069'},{name:'CE −OI',rows:ceMinus,color:'#ed8dc4'}]} empty={(useFixed?frame.fixedOiPressureStatus?.reason:frame.optionOiFlowStatus?.reason)||'The selected basket has no complete verified CE flow at this timestamp.'}/>
      <Lane title={`PE +OI / −OI · ${window}m`} subtitle={`${sourceLabel} · additions above zero, removals below zero`} min={min} max={max} axis="oi" unit="Reported OI units" series={[{name:'PE +OI',rows:pePlus,color:'#46d8a4'},{name:'PE −OI',rows:peMinus,color:'#a1b7ff'}]} empty={(useFixed?frame.fixedOiPressureStatus?.reason:frame.optionOiFlowStatus?.reason)||'The selected basket has no complete verified PE flow at this timestamp.'}/>
      </div>
      <Lane title={useFixed?'Raw pressure · 1m and 5m':'Native raw OI balance · observations only'} subtitle={useFixed?'Prototype fixed-four calculation · live and replay use the same rule':'Moving three-strike observations; no live/fixed-four score is inferred'} min={min} max={max} axis="score" unit="Pressure −100 to +100 · not probability" series={useFixed?[...(studyRows?.length?[{name:'Historical confirmed score',rows:confirmedSeries,color:'#bb9cff'}]:[]),{name:'Fixed-4 raw 1m',rows:raw1Series,color:'#54d5df',dashed:true},{name:'Fixed-4 raw 5m',rows:raw5Series,color:'#f6cc6b'}]:[{name:'Native raw 1m',rows:raw1Series,color:'#54d5df',dashed:true},{name:'Native raw 5m',rows:raw5Series,color:'#f6cc6b'}]} empty="Awaiting full, causal CE and PE option report receipts. No raw score is estimated."/>
    </div>
    <div className="oi-primary-flow-pair">      {showVix&&<Lane title="India VIX" subtitle="Actual retained values · dashed · original source timing" min={min} max={max} unit="VIX points" series={[{name:'VIX',rows:vix,color:COLORS.vix,dashed:true}]}/>}

      {showBasis&&<Lane title="Futures basis" subtitle="Futures − NIFTY index · actual points" min={min} max={max} unit="Points" series={[{name:'Basis',rows:basis,color:COLORS.basis}]}/>}

</div>
    <div className="oi-primary-footer"><strong>Source separation:</strong> Fixed 4 uses the prototype’s fixed 09:45 basket and first receipt in each minute in both live and replay. Native 3 uses the existing moving three-near-OTM receipt stream; its 5m value is the sum of five complete 1m gross flows, never endpoint net ΔOI. Do not compare basket scores as if identical. Scores are imbalance measures, not forecast confidence. Confirmation scores and layer tags are available only for matching historical references. Raw pressure does not identify option buyers versus writers or change the V2 call.</div>
  </section>;
}
