"use client";
import {memo,useEffect,useRef,useState} from 'react';
import {Maximize2,Minimize2} from 'lucide-react';
import type {ECharts,EChartsOption,LineSeriesOption} from 'echarts';
import {clock,compact,fmt} from './market-types';
import {chartPoints} from '../public/market-data.mjs';

export function baseChart(min:number,max:number):EChartsOption {
  return {
    backgroundColor:'transparent',animation:false,useUTC:true,
    textStyle:{fontFamily:'Inter, ui-sans-serif, system-ui, sans-serif',color:'#8fa0b7',fontSize:12},
    grid:{left:66,right:22,top:16,bottom:28,containLabel:false},
    tooltip:{trigger:'axis',confine:true,backgroundColor:'#162334',borderColor:'#34475f',textStyle:{color:'#e7eef8',fontSize:13},axisPointer:{type:'line',lineStyle:{color:'#829bb8',type:'dashed'}},formatter:(raw:any)=>{
      const items=Array.isArray(raw)?raw:[raw];
      const escape=(s:any)=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
      return `<strong>${clock(items[0]?.axisValue,true)} IST</strong>`+items.map((p:any)=>`<div>${p.marker||''} ${escape(p.seriesName)} <b>${fmt(Array.isArray(p.value)?p.value[1]:p.value)}</b></div>`).join('');
    }},
    axisPointer:{link:[{xAxisIndex:'all'}],label:{backgroundColor:'#26374b'}},
    xAxis:{type:'time',min,max,splitNumber:6,axisLine:{lineStyle:{color:'#233247'}},axisTick:{show:false},axisLabel:{color:'#8fa0b7',formatter:(v:number)=>clock(v),hideOverlap:true},splitLine:{show:true,lineStyle:{color:'#1a293b',type:'dashed'}}},
    yAxis:{type:'value',scale:true,splitNumber:3,axisLabel:{color:'#98a9bf',formatter:(v:number)=>Math.abs(v)>=100000?compact(v):fmt(v,Math.abs(v)<100?2:0)},splitLine:{lineStyle:{color:'#1c2a3d'}},axisLine:{show:false}},
    dataZoom:[{type:'inside',xAxisIndex:0,filterMode:'none',zoomOnMouseWheel:'ctrl',moveOnMouseWheel:false,preventDefaultMouseMove:false}],
  };
}
export function line(name:string,rows:any[],field:string,color:string,extra:Record<string,any>={}):LineSeriesOption {
  const {holdLastValue=false,...chartStyle}=extra;
  return {name,type:'line',showSymbol:false,connectNulls:false,sampling:'lttb',emphasis:{disabled:true},data:chartPoints(rows,field,holdLastValue),lineStyle:{width:1.8,color},itemStyle:{color},...chartStyle};
}
export const Plot=memo(function Plot({option,height=160,sync=true,label}:{option:EChartsOption;height?:number;sync?:boolean;label:string}){
  const el=useRef<HTMLDivElement>(null),chart=useRef<ECharts|null>(null),latest=useRef(option);
  const [ready,setReady]=useState(false),[visible,setVisible]=useState(false),[error,setError]=useState('');
  latest.current=option;
  useEffect(()=>{
    if(!el.current)return;
    const observer=new IntersectionObserver(entries=>setVisible(entries.some(entry=>entry.isIntersecting)),{rootMargin:'100px'});
    observer.observe(el.current);return()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    if(!visible||chart.current||!el.current)return;
    let disposed=false,observer:ResizeObserver|undefined;
    import('echarts').then(echarts=>{
      if(disposed||!el.current)return;
      const c=echarts.init(el.current,undefined,{renderer:'canvas'});chart.current=c;
      if(sync){c.group='market-v3-time';echarts.connect('market-v3-time');}
      c.setOption(latest.current);setReady(true);
      observer=new ResizeObserver(()=>{if(!c.isDisposed())c.resize();});observer.observe(el.current);
    }).catch(()=>setError('Chart could not load. Refresh this page to retry.'));
    return()=>{disposed=true;observer?.disconnect();chart.current?.dispose();chart.current=null;setReady(false);};
  },[visible,sync]);
  useEffect(()=>{if(ready&&visible)chart.current?.setOption(option,{replaceMerge:['series'],lazyUpdate:true});},[option,ready,visible]);
  return <div className="plot" style={{height}} role="img" aria-label={label}><div ref={el} className="plot-canvas"/>{error&&<p className="chart-message">{error}</p>}</div>;
});
export function ChartPanel({title,subtitle,value,colour,children,tools,className=''}:{title:string;subtitle?:string;value?:React.ReactNode;colour?:string;children:React.ReactNode;tools?:React.ReactNode;className?:string}){
  const ref=useRef<HTMLElement>(null);const [full,setFull]=useState(false),[expanded,setExpanded]=useState(false);
  useEffect(()=>{const handler=()=>setFull(document.fullscreenElement===ref.current);document.addEventListener('fullscreenchange',handler);return()=>document.removeEventListener('fullscreenchange',handler);},[]);
  return <section ref={ref} className={`chart-card ${expanded?'chart-expanded':''} ${className}`}>
    <div className="chart-heading"><div className="chart-title"><span className="series-marker" style={{background:colour||'#54cfff'}}/><h2>{title}</h2>{subtitle&&<span className="chart-subtitle">{subtitle}</span>}</div><div className="chart-actions">{value&&<strong style={{color:colour}}>{value}</strong>}{tools}<button type="button" className="icon-button maximize" title={full||expanded?'Restore chart':'Expand chart'} aria-label={`${full||expanded?'Restore':'Expand'} ${title}`} aria-pressed={full||expanded} onClick={()=>{if(full)void document.exitFullscreen();else if(expanded)setExpanded(false);else if(typeof ref.current?.requestFullscreen==='function')void ref.current.requestFullscreen().catch(()=>setExpanded(true));else setExpanded(true);}}>{full||expanded?<Minimize2 size={15}/>:<Maximize2 size={15}/>}</button></div></div>
    {children}
  </section>;
}
