import type { EChartsOption } from 'echarts';
import { ChartPanel, Plot, baseChart, line } from './market-chart';
import { clock, compact, fmt, type Frame, type Row } from './market-types';
import { VOLUME_CLIMAX_COLOR, FUTURES_CLIMAX_MARKER_COLOR, volumeRatioLabel } from '../public/v2-volume.mjs';

export function climaxMarkers(points:Row[], coordinate:'price'|'ratio'):any {
  return {
    id:`v2-volume-climax-${coordinate}`, name:'Volume climax >4×', type:'scatter',
    symbol:'diamond', symbolSize:11, z:20, clip:true,
    itemStyle:{color:FUTURES_CLIMAX_MARKER_COLOR,borderColor:'#401d2a',borderWidth:1},
    label:{show:true,position:'top',distance:7,fontSize:11,fontWeight:600,
      color:FUTURES_CLIMAX_MARKER_COLOR,backgroundColor:'#16202ef2',borderRadius:3,padding:[2,4],
      formatter:(p:any)=>volumeRatioLabel(p.data.volumeRatio)},
    labelLayout:{moveOverlap:'shiftY',hideOverlap:true},
    tooltip:{trigger:'item',formatter:(p:any)=>{
      const r=p.data;
      return `<strong>Volume climax · ${volumeRatioLabel(r.volumeRatio)}</strong><br/>Available ${clock(r.value[0],true)} IST<br/>Input cutoff ${clock(r.inputCutoff,true)} IST<br/>Index ${fmt(r.indexPrice)}<br/>Futures volume · 5m ${compact(r.volume)}`;
    }},
    data:points.filter(row=>Number.isFinite(row[coordinate])).map(row=>({
      value:[row.x,row[coordinate]],volumeRatio:row.ratio,indexPrice:row.price,
      inputCutoff:row.input_cutoff,volume:row.volume,
    })),
  };
}

export function V2VolumePanel({frame,min,max}:{frame:Frame;min:number;max:number}) {
  const points=frame.volumeClimaxes.filter(row=>row.x>=min&&row.x<=max);
  const available=frame.volumeHistory.some(row=>Number.isFinite(row.futures_volume_ratio));
  const ratioLine:any=line('Futures volume ratio',frame.volumeHistory,'futures_volume_ratio',VOLUME_CLIMAX_COLOR);
  ratioLine.markLine={symbol:'none',silent:true,lineStyle:{color:'#ffb35780',type:'dashed'},
    label:{formatter:'4× threshold',position:'insideStartTop',color:'#b3a38e'},data:[{yAxis:4}]};
  const options:EChartsOption={...baseChart(min,max),series:[ratioLine,climaxMarkers(points,'ratio')]};
  return <ChartPanel title="Futures volume ratio" subtitle="Confirmed · completed-minute cutoff · >4×" colour={VOLUME_CLIMAX_COLOR}
    value={volumeRatioLabel(frame.context?.futures_volume_ratio)}>
    {available?<Plot option={options} label={`${frame.profile.label} futures volume ratio with marked climax points strictly above four`} height={190}/>
      :<p className="empty-chart">The source has no available volume-ratio readings at this replay time.</p>}
    <p className="chart-source-note">Recorded 5m futures volume ÷ median of the previous four 5m windows. Red diamonds mark ratios strictly greater than 4; markers appear at the V2 publication time.</p>
    <details className="climax-details"><summary>{points.length} volume-climax {points.length===1?'point':'points'} in this view</summary>
      <div className="climax-list">{points.map((row,index)=><span key={`${row.x}-${index}`}><time>{clock(row.x,true)}</time><strong>{volumeRatioLabel(row.ratio)}</strong></span>)}</div>
    </details>
  </ChartPanel>;
}
