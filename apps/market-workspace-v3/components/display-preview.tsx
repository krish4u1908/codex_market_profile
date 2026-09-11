import {useEffect,useMemo,useState} from 'react';
import type {EChartsOption} from 'echarts';
import {ChartPanel,Plot,baseChart} from './market-chart';
import {clock,compact,fmt,type Frame,type Row} from './market-types';
import {liveReading,observedVolume,previewPriceOption,previewVixOption,validatePreview} from '../public/display-preview.mjs';

export function useDisplayPreview(enabled:boolean,instrument:string,session?:string){
  const [data,setData]=useState<Row|null>(null),[error,setError]=useState('');
  useEffect(()=>{
    setData(null);setError('');if(!enabled)return;
    const worker=new Worker('/display-preview-worker.js',{type:'module'});
    worker.onmessage=e=>{if(e.data.kind==='preview'){setData(e.data.data);setError('');}
      else{setData(null);setError(e.data.error);}};
    worker.onerror=()=>{setData(null);setError('Incoming feed unavailable; confirmed charts remain available.');};
    worker.postMessage({action:'start',instrument});
    return()=>worker.terminate();
  },[enabled,instrument]);
  return {data:enabled&&data?validatePreview(data,instrument,session):null,error};
}

export function PreviewStatus({data,error}:{data:Row|null;error:string}){
  const index=liveReading(data,data?.index_symbol),vix=liveReading(data,'NSE:INDIAVIX-INDEX');
  const age=index?Math.max(0,(data!.server_ms-index.received_ms)/1000):null;
  return <section className="preview-status" aria-label="Near real-time preview status">
    <div><strong>Preview 3.1.0 · incoming readings</strong><span>{error||(index?`Index ${fmt(index.price)} · receipt age ${age!.toFixed(1)}s`:
      data?.status==='CATCHING_UP'?'Reader catching up':data?.status==='ERROR'?'Reader unavailable':'Waiting for fresh readings')}{vix?` · VIX ${fmt(vix.price)}`:''}</span></div>
    <p>Dotted lines are provisional. Climax diamonds, OI and ribbon signals remain confirmed by the existing core.</p>
  </section>;
}

export function PreviewPricePlot({option,frame,data,label}:{option:EChartsOption;frame:Frame;data:Row|null;label:string}){
  const projected=useMemo(()=>previewPriceOption(option,frame,data),[option,frame,data]);
  return <Plot option={projected} height={380} label={label}/>;
}

export function PreviewVixPlot({option,frame,data}:{option:EChartsOption;frame:Frame;data:Row|null}){
  const projected=useMemo(()=>previewVixOption(option,frame,data),[option,frame,data]);
  return <Plot option={projected} height={138} label="India VIX confirmed minute closes with provisional incoming readings"/>;
}

export function IncomingVolume({data,frame}:{data:Row|null;frame:Frame}){
  const [side,setSide]=useState('FUT');
  const values=useMemo(()=>observedVolume(data,frame.selection,side),[data,frame.selection,side]);
  const now=data?.server_ms??frame.now,max=Math.ceil(now/60000)*60000;
  const options:EChartsOption={...baseChart(max-600000,max),series:[{
    name:'Observed volume · provisional',type:'bar',barMaxWidth:22,
    data:values.bars.map((r:Row)=>({value:[r.x,r.volume],itemStyle:{
      color:r.partial?'#9aa8be66':r.forming?'#54cfff77':'#54cfff',
      borderColor:r.forming?'#8ae1ff':'transparent',borderWidth:r.forming?1:0}})),
  }],tooltip:{...baseChart(max-600000,max).tooltip as object,formatter:(raw:any)=>{
    const p=Array.isArray(raw)?raw[0]:raw,r=values.bars.find((b:Row)=>b.x===p?.value?.[0]);
    return `${clock(r?.x)} IST<br/>Observed volume ${compact(r?.volume)}<br/>${r?.forming?'Forming minute':'Observed minute'}${r?.partial?' · partial coverage':''}`;
  }}};
  const last=values.bars.at(-1);
  return <ChartPanel title="Incoming volume" subtitle="Observed 1m bars · preview" colour="#54cfff"
    value={last?compact(last.volume):'—'} tools={<div className="preview-volume-tabs" aria-label="Incoming volume instrument">
      {['FUT','CE','PE'].map(s=><button type="button" key={s} aria-pressed={side===s} onClick={()=>setSide(s)}>{s==='FUT'?'Futures':s}</button>)}
    </div>}>
    <Plot option={options} height={130} label={`${side} incoming volume by receipt minute, forming and partial bars distinguished`}/>
    <p className="chart-source-note">{values.coverage}/{values.expected} contracts fresh · {side==='FUT'?'Active futures contract':'Fixed 09:45 basket'}.
      {' '}Observed counter increases only; outlined bar is forming, grey bars have partial coverage. These bars do not calculate climax signals.</p>
  </ChartPanel>;
}
