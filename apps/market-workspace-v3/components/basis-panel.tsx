import {memo,useMemo} from 'react';
import type {EChartsOption} from 'echarts';
import {ChartPanel,Plot,baseChart,line} from './market-chart';
import {COLORS,clock,signed,type Frame,type Row} from './market-types';
import {basisRibbonIntervals} from '../public/price-basis-ribbon.mjs';

const states:Record<string,{color:string;label:string}>={
  green:{color:COLORS.positive,label:'Price ↓ · basis ↑'},
  red:{color:COLORS.negative,label:'Price ↑ · basis ↓'},
  neutral:{color:'#718298',label:'Other / flat'},
  unavailable:{color:COLORS.muted,label:'Unavailable'},
};

export function basisChartOptions(frame:Frame,min:number,max:number):EChartsOption {
  const base=baseChart(min,max);
  const intervals=basisRibbonIntervals(frame.basisRibbon,min,Math.min(max,frame.now));
  const ribbon:any={
    id:'price-basis-3m-ribbon',name:'Price / basis · 3m',type:'custom',xAxisIndex:1,yAxisIndex:1,
    dimensions:['start','end','band'],encode:{x:[0,1],y:2},clip:true,progressive:0,
    emphasis:{disabled:true},
    renderItem:(params:any,api:any)=>{
      const first=api.coord([api.value(0),0]),last=api.coord([api.value(1),1]);
      const area=params.coordSys,left=Math.max(first[0],area.x),right=Math.min(last[0],area.x+area.width);
      if(right<=left)return null;
      return {type:'rect',shape:{x:left,y:area.y,width:right-left,height:area.height},
        style:{fill:api.visual('color')}};
    },
    tooltip:{trigger:'item',formatter:(p:any)=>{
      const row=p.data;
      return `<strong>3m · ${states[row.state].label}</strong><br/>As of ${clock(row.x,true)} IST`
        +`<br/>Δ price ${signed(row.priceChange)} pts<br/>Δ basis ${signed(row.basisChange)} pts`
        +`<br/>3m cutoff ${clock(row.cutoff,true)} IST<br/>Baseline receipt ${clock(row.baselineAt,true)} IST`;
    }},
    data:intervals.map((row:Row)=>({...row,value:[row.start,row.end,.5],itemStyle:{color:states[row.state].color}})),
  };
  return {...base,
    grid:[{...(base.grid as object),bottom:64},{left:66,right:22,bottom:28,height:12,show:true,backgroundColor:'#172536',borderWidth:0}],
    xAxis:[{...(base.xAxis as object),gridIndex:0,axisLabel:{show:false}},
      {...(base.xAxis as object),gridIndex:1,splitLine:{show:false},axisLine:{show:false}}],
    yAxis:[base.yAxis as any,{type:'value',gridIndex:1,min:0,max:1,show:false}],
    dataZoom:[{...(base.dataZoom as any[])[0],xAxisIndex:[0,1]}],
    series:[line('Basis',frame.price,'b',COLORS.basis),ribbon],
  };
}

export const BasisPanel=memo(function BasisPanel({frame,min,max}:{frame:Frame;min:number;max:number}) {
  const options=useMemo(()=>basisChartOptions(frame,min,max),[frame,min,max]);
  const latest=frame.basisRibbonLatest,state=latest?.state||'unavailable';
  return <ChartPanel title="Futures basis" subtitle="Futures − Index · points" value={signed(frame.latest?.b)} colour={COLORS.basis} className="basis-panel">
    <div className="basis-ribbon-legend" aria-label="Three-minute price and basis ribbon legend">
      <strong>3m ribbon</strong>{['green','red','neutral'].map(key=><span key={key}><i style={{background:states[key].color}}/>{states[key].label}</span>)}
    </div>
    <Plot option={options} label={`${frame.profile.label} basis line with a three-minute price/basis ribbon: green for falling price and rising basis, red for rising price and falling basis`} height={182}/>
    <div className="basis-ribbon-reading" aria-label="Latest three-minute price and basis change">
      <span className="basis-ribbon-state" data-state={state} style={{color:states[state].color}}>{state==='unavailable'?(latest?.reason||'Waiting for price/basis history'):states[state].label}</span>
      {state!=='unavailable'&&<span>Δ price <b>{signed(latest?.priceChange)}</b> · Δ basis <b>{signed(latest?.basisChange)}</b> pts</span>}
    </div>
    <p className="basis-ribbon-note">Net change over 3m · blank during warm-up or gaps · hover or tap the ribbon for values</p>
  </ChartPanel>;
});
