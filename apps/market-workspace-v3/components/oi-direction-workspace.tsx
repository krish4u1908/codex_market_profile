import {useMemo,useState,type ReactNode} from 'react';
import type {EChartsOption} from 'echarts';
import {Tabs,TabsList,TabsTrigger,TabsContent} from './ui/tabs';
import {Checkbox} from './ui/checkbox';
import {ChartPanel,Plot,baseChart,line} from './market-chart';
import {COLORS,clock,fmt,signed,type Frame,type Row} from './market-types';
const frameLabels={price:'Main price chart',pressure:'Raw pressure · 1m and 5m',direction:'Independent pressure direction',vix:'India VIX',basis:'Futures basis'};
type Visibility=Record<keyof typeof frameLabels,boolean>;
const defaults:Visibility={price:true,pressure:true,direction:true,vix:true,basis:true};
const storageKey='nifty-oi-direction-display-v1';
function readVisibility():Visibility{try{const stored=JSON.parse(localStorage.getItem(storageKey)||localStorage.getItem('nifty-oi-model-display-v1')||'{}');return Object.fromEntries(Object.keys(defaults).map(k=>[k,typeof stored?.[k]==='boolean'?stored[k]:true])) as Visibility;}catch{return {...defaults};}}
export function OiDirectionWorkspace({frame,windowMinutes,priceChart}:{frame:Frame;windowMinutes:number;priceChart:ReactNode}){
 const [visible,setVisible]=useState<Visibility>(readVisibility),[saved,setSaved]=useState(true);
 function update(next:Visibility){setVisible(next);try{localStorage.setItem(storageKey,JSON.stringify(next));setSaved(true);}catch{setSaved(false);}}
 return <Tabs defaultValue="charts" className="oi-direction-workspace">
  <TabsList aria-label="OI Direction view"><TabsTrigger value="charts">Charts</TabsTrigger><TabsTrigger value="custom-display">Custom display</TabsTrigger></TabsList>
  <TabsContent value="custom-display"><section className="insight-card"><h2>Choose chart frames</h2><p className="muted">Applies to OI Direction in live and replay. {saved?'Remembered in this browser.':'Browser storage unavailable; choices apply until this view is closed.'}</p>
   {(Object.keys(frameLabels) as (keyof Visibility)[]).map(key=><label className="setting-row" key={key}><span><strong>{frameLabels[key]}</strong></span><Checkbox aria-label={`Show ${frameLabels[key]}`} checked={visible[key]} onCheckedChange={checked=>update({...visible,[key]:checked===true})}/></label>)}
   <button className="secondary-button" onClick={()=>update({...defaults})}>Show all frames</button>
  </section></TabsContent>
  <TabsContent value="charts"><div className="chart-stack">
   {visible.price&&priceChart}
   {Object.values(visible).some(Boolean)?<DirectionCharts frame={frame} windowMinutes={windowMinutes} visible={visible}/>:<section className="insight-card"><p>All chart frames are hidden. Open Custom display to enable a frame.</p><button className="secondary-button" onClick={()=>update({...defaults})}>Show all frames</button></section>}
  </div></TabsContent>
 </Tabs>;
}
function DirectionCharts({frame,windowMinutes,visible}:{frame:Frame;windowMinutes:number;visible:Visibility}){
 const min=windowMinutes?Math.max(frame.start,frame.now-windowMinutes*60000):frame.start,max=Math.max(min+60000,frame.now);
 const direction=frame.pressureDirection||{rows:[],latest:null,reason:'Awaiting OI receipts.'},rows:Row[]=direction.rows,latest=direction.latest;
 const useReportVix=!frame.cash.some(r=>Number.isFinite(r.vix_close))&&!!frame.oiDirectionVix?.some(r=>Number.isFinite(r.vix_close));
 const vixRows=useReportVix?frame.oiDirectionVix:frame.cash;
 const options=useMemo(()=>{
  const base=()=>baseChart(min,max),zero={silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#72839b',type:'dashed'},data:[{yAxis:0}]};
  const raw=frame.fixedOiPressure.map(r=>({x:r.x,raw1:r.raw1?.v??null,raw5:r.raw5?.v??null}));
  const pressure={...base(),legend:{top:0,textStyle:{color:'#b9c9dc'},data:['Fixed-4 raw 1m','Fixed-4 raw 5m']},grid:{left:66,right:22,top:35,bottom:28},yAxis:{...(base().yAxis as object),min:-100,max:100,interval:50},series:[line('Fixed-4 raw 1m',raw,'raw1','#51d3dc',{lineStyle:{color:'#51d3dc',type:'dashed',width:1.6},markLine:zero}),line('Fixed-4 raw 5m',raw,'raw5','#f6cc6b')]};
  const state={...base(),grid:{left:80,right:22,top:20,bottom:28},yAxis:{...(base().yAxis as object),min:-1,max:1,interval:1,axisLabel:{color:'#98a9bf',formatter:(v:number)=>v===1?'UP':v===-1?'DOWN':v===0?'NEUTRAL':''}},
   series:[line('Pressure direction',rows,'direction',COLORS.muted,{sampling:'none',step:'end',lineStyle:{color:'#8294ab',width:1.2},data:rows.map(r=>({value:[r.x,r.direction],itemStyle:{color:r.direction===1?COLORS.positive:r.direction===-1?COLORS.negative:COLORS.muted}})),showSymbol:true,symbol:'circle',symbolSize:5,clip:true,markLine:zero})],
   tooltip:{...(base().tooltip as object),formatter:(raw:any)=>{
    const point=Array.isArray(raw)?raw[0]:raw,r=rows.find(r=>r.x===point?.value?.[0]);if(!r)return '';
    return `<strong>${clock(r.x,true)} IST · ${r.label}</strong><br/>${r.reason}<br/>1m quantity: ${signed(r.quantity1,1)}<br/>5m quantity: ${signed(r.quantity5,1)}<br/>5m balance change: ${signed(r.quantityChange5,1)}<br/>Previous 5m state: ${r.previousState||'Unknown'}${r.mixedOrigin?'<br/>Mixed episode came from: '+r.mixedOrigin:''}`;
   }}};
  return {pressure,state,vix:{...base(),series:[line('India VIX',vixRows,'vix_close',COLORS.vix,{lineStyle:{color:COLORS.vix,type:'dashed',width:1.8}})]},basis:{...base(),series:[line('Futures − index · points',frame.price,'b',COLORS.basis,{markLine:zero})]}};
 },[frame,rows,vixRows,min,max]);
 return <div className="chart-stack oi-direction-stack">
  <p className="source-note">OI Direction · {frame.session} · Shared time cursor and replay clock.</p>
  {visible.pressure&&<ChartPanel title="Raw pressure · 1m and 5m" subtitle="Fixed 09:45 four CE / four PE basket · −100 to +100" colour="#51d3dc">
   <Plot option={options.pressure as EChartsOption} label="Fixed-four raw 1-minute and 5-minute pressure, not probability" height={210}/>
   <p className="chart-source-note">Pressure is not probability. {frame.fixedOiPressureStatus.reason||'Live and replay use the same receipt calculation.'}</p>
  </ChartPanel>}
  {visible.direction&&<ChartPanel title="Independent pressure direction" subtitle="Rule candidate · available at each OI receipt" colour={latest?.direction===1?COLORS.positive:latest?.direction===-1?COLORS.negative:COLORS.muted} value={latest?.label||'UNAVAILABLE'}>
   <Plot option={options.state as EChartsOption} label="Independent pressure direction: up, down or neutral, calculated immediately from past and current OI receipts" height={170}/>
   <p className="chart-source-note"><strong>{latest?.reason||direction.reason}</strong>{latest?` · Receipt ${clock(latest.x,true)} IST · 1m quantity ${signed(latest.quantity1,1)} · 5m quantity ${signed(latest.quantity5,1)}`:''}</p>
   <p className="chart-source-note">Aligned 5m pressure needs 1m quantity agreement. After alignment becomes mixed, an opposing 1m quantity and a changing 5m balance can flag a reversal. Otherwise: neutral. No 10-minute wait.</p>
   <p className="chart-source-note">Experimental directional hypothesis, not a probability or a validated trading signal. NEUTRAL means no agreed direction, not a flat-price forecast.</p>
  </ChartPanel>}
  {visible.vix&&<ChartPanel title="India VIX" subtitle="Actual retained values · dashed" colour={COLORS.vix} value={fmt(vixRows.at(-1)?.vix_close)}>
   <Plot option={options.vix} label="India VIX actual retained values" height={150}/>
   <p className="chart-source-note">{useReportVix?'Archived option-report VIX · original receipt timing.':frame.cashVixQuality.sourceTime?'Source-minute time; values appear only after arrival.':'Original retained receipt timing.'} Missing values stay blank.</p>
  </ChartPanel>}
  {visible.basis&&<ChartPanel title="Futures basis" subtitle="Futures − NIFTY index · points" colour={COLORS.basis} value={signed(frame.latest?.b)}><Plot option={options.basis as EChartsOption} label="Futures minus NIFTY index in points" height={150}/></ChartPanel>}
 </div>;
}
