import {memo,useMemo} from 'react';
import type {EChartsOption} from 'echarts';
import {Plot} from './market-chart';
import {COLORS,clock,compact,type Frame,type Row} from './market-types';

const escape=(value:unknown)=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const sideName=(side:string)=>side==='PE'?'PE / puts':'CE / calls';
const dominantLabel=(row:Row|null)=>!row?'Awaiting receipt':row.dominant==='POSITIVE'?'+OI increasing':row.dominant==='NEGATIVE'?'−OI increasing':row.dominant==='BALANCED'?'Balanced':'No OI change';
const dominantColor=(row:Row|null)=>row?.dominant==='POSITIVE'?COLORS.positive:row?.dominant==='NEGATIVE'?COLORS.negative:COLORS.muted;

function tooltip(rows:Row[],raw:any) {
  const params=Array.isArray(raw)?raw:[raw];
  const x=Number(params[0]?.axisValue??params[0]?.value?.[0]);
  if(!Number.isFinite(x))return '';
  const minute=Math.floor(x/60000)*60000;
  const visible=rows.filter(row=>row.minute===minute);
  if(!visible.length)return '';
  return `<strong>${clock(visible[0].x,true)} IST · one-minute OI receipt</strong>`+visible.map(row=>{
    const ratio=row.ratio==null?'one side only':`${Number(row.ratio).toFixed(2)}×`;
    const quality=row.validContracts<row.expectedContracts?` · ${row.validContracts}/${row.expectedContracts} contracts`:'';
    return `<div style="margin-top:6px"><b>${escape(sideName(row.side))}</b>`
      +`<br/><span style="color:${COLORS.positive}">+OI ${compact(row.positive)}</span>`
      +` · <span style="color:${COLORS.negative}">−OI ${compact(row.negative)}</span>`
      +`<br/>${escape(dominantLabel(row))} · ${ratio}${quality}</div>`;
  }).join('');
}

function seriesFor(rows:Row[],side:'PE'|'CE',field:'positive'|'negative',axis:number,zero=false):any {
  const positive=field==='positive';
  return {id:`option-oi-flow-${side}-${field}`,name:`${side} ${positive?'+OI':'−OI'}`,type:'bar',
    xAxisIndex:axis,yAxisIndex:axis,stack:`${side}-flow`,barMaxWidth:7,barMinHeight:0,
    emphasis:{disabled:true},animation:false,progressive:0,itemStyle:{color:positive?'rgba(70,216,164,.68)':'rgba(255,118,140,.68)'},
    data:rows.filter(row=>row.side===side).map(row=>[row.x,positive?row.positive:-row.negative]),
    ...(zero?{markLine:{silent:true,symbol:'none',label:{show:false},lineStyle:{color:'#53657a',width:.7,opacity:.7},data:[{yAxis:0}]}}:{}),
  };
}

export const OptionOiFlowRibbon=memo(function OptionOiFlowRibbon({frame,min,max}:{frame:Frame;min:number;max:number}) {
  const rows=frame.optionOiFlow.filter(row=>row.x>=min&&row.x<=max);
  const latest=(side:'PE'|'CE')=>[...rows].reverse().find(row=>row.side===side)||null;
  const latestPe=latest('PE'),latestCe=latest('CE');
  const option=useMemo<EChartsOption>(()=>{
    const scale=(side:string)=>Math.max(1,...rows.filter(row=>row.side===side).flatMap(row=>[row.positive,row.negative]));
    const peScale=scale('PE'),ceScale=scale('CE');
    const xAxis=(gridIndex:number)=>({type:'time' as const,gridIndex,min,max,show:false,axisPointer:{show:true}});
    const yAxis=(gridIndex:number,extent:number)=>({type:'value' as const,gridIndex,min:-extent,max:extent,show:false,splitLine:{show:false}});
    return {backgroundColor:'transparent',animation:false,useUTC:true,
      grid:[{left:36,right:10,top:4,height:46},{left:36,right:10,top:58,height:46}],
      xAxis:[xAxis(0),xAxis(1)],yAxis:[yAxis(0,peScale),yAxis(1,ceScale)],
      axisPointer:{link:[{xAxisIndex:'all'}],lineStyle:{color:'#829bb8',type:'dashed'}},
      dataZoom:[{type:'inside',xAxisIndex:[0,1],filterMode:'none',zoomOnMouseWheel:'ctrl',moveOnMouseWheel:false,preventDefaultMouseMove:false}],
      tooltip:{trigger:'axis',confine:true,backgroundColor:'#162334',borderColor:'#34475f',textStyle:{color:'#e7eef8',fontSize:12},formatter:(raw:any)=>tooltip(rows,raw)},
      series:[seriesFor(rows,'PE','positive',0,true),seriesFor(rows,'PE','negative',0),seriesFor(rows,'CE','positive',1,true),seriesFor(rows,'CE','negative',1)],
    };
  },[rows,min,max]);
  if(frame.profile.version!=='2.0.0')return null;
  return <section className="option-oi-flow-ribbon" aria-label="Near OTM PE and CE one-minute positive and negative open-interest changes">
    <div className="option-oi-flow-caption">
      <div><strong>Near-OTM ΔOI · 1m receipts</strong><span><i className="oi-flow-positive"/> +OI added</span><span><i className="oi-flow-negative"/> −OI removed</span></div>
      <div className="option-oi-flow-latest"><span style={{color:dominantColor(latestPe)}}>PE {dominantLabel(latestPe)}{latestPe?` · +${compact(latestPe.positive)} / −${compact(latestPe.negative)}`:''}</span><span style={{color:dominantColor(latestCe)}}>CE {dominantLabel(latestCe)}{latestCe?` · +${compact(latestCe.positive)} / −${compact(latestCe.negative)}`:''}</span></div>
    </div>
    {frame.optionOiFlowStatus?.status==='AVAILABLE'?<div className="option-oi-flow-plot"><div className="option-oi-flow-labels"><span>PE</span><span>CE</span></div><Plot option={option} height={108} label="Near OTM PE and CE one-minute OI additions above zero and removals below zero"/></div>
      :<p className="option-oi-flow-status">{frame.optionOiFlowStatus?.reason||'Option-report quotes unavailable for this session.'}</p>}
  </section>;
});
