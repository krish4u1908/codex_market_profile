import {Checkbox} from './ui/checkbox';
import {clock,compact,fmt,type Row} from './market-types';
import {OPTION_CLIMAX_TYPES} from '../public/v2-option-climax.mjs';
import {FUTURES_CLIMAX_MARKER_COLOR,volumeRatioLabel} from '../public/v2-volume.mjs';

export type ClimaxVisibility=Record<string,boolean>;
export const defaultClimaxVisibility:ClimaxVisibility={futures:true,...Object.fromEntries(OPTION_CLIMAX_TYPES.map(t=>[t.key,true]))};
const meta=(key:string)=>OPTION_CLIMAX_TYPES.find(t=>t.key===key)!;

export function optionClimaxMarkers(points:Row[]):any {
  const groups=new Map<string,Row>();
  for(const point of points) {
    if(!Number.isFinite(point.price))continue;
    const id=`${point.x}:${point.price}`;
    if(!groups.has(id))groups.set(id,{value:[point.x,point.price],events:[]});
    groups.get(id)!.events.push(point);
  }
  return {id:'v2-option-climaxes',name:'CE/PE climax candidates',type:'scatter',z:21,clip:true,
    symbolSize:11,
    label:{show:true,position:'top',distance:8,fontSize:10,fontWeight:600,lineHeight:15,
      backgroundColor:'#16202ef2',borderRadius:3,padding:[2,4],
      formatter:(p:any)=>p.data.events.map((e:Row)=>`${meta(e.key).short} ${volumeRatioLabel(e.ratio)}`).join('\n')},
    labelLayout:{moveOverlap:'shiftY',hideOverlap:true},
    tooltip:{trigger:'item',formatter:(p:any)=>{
      const row=p.data;
      return `<strong>CE/PE climax · trial thresholds</strong><br/>Available ${clock(row.value[0],true)} IST<br/>Index ${fmt(row.value[1])}`
        +row.events.map((e:Row)=>`<div style="margin-top:8px"><b>${meta(e.key).label} · ${volumeRatioLabel(e.ratio)}</b><br/>5m ${compact(e.amount)} · baseline ${compact(e.baseline)}${e.metric==='volume'?'':`<br/>${fmt(e.oiPercent)}% of starting basket OI`}<br/>Input cutoff ${clock(e.input_cutoff,true)} IST</div>`).join('');
    }},
    data:[...groups.values()].map(row=>{
      const types=row.events.map((e:Row)=>meta(e.key)),single=types.length===1;
      const color=types.every((t:Row)=>t.side===types[0].side)?types[0].color:'#e4edf7';
      return {...row,symbol:single?types[0].symbol:'roundRect',symbolRotate:single?(types[0].rotate||0):0,
        symbolSize:single?11:13,itemStyle:{color,borderColor:'#16202e',borderWidth:1},label:{color}};
    }),
  };
}

export function ClimaxControls({visible,onChange,allPoints,onAllPoints}:{visible:ClimaxVisibility;onChange:(key:string)=>void;allPoints:boolean;onAllPoints:(show:boolean)=>void}) {
  const items=[{key:'futures',label:'Futures >4×',color:FUTURES_CLIMAX_MARKER_COLOR,glyph:'◆'},...OPTION_CLIMAX_TYPES];
  return <div className="climax-toolbar" aria-label="Price chart climax markers">
    <span className="climax-caption">Climaxes</span>
    {items.map(item=><button key={item.key} type="button" className={`climax-toggle ${visible[item.key]?'':'is-hidden'}`} aria-pressed={visible[item.key]} onClick={()=>onChange(item.key)} title={`Show or hide ${item.label} markers`}>
      <span aria-hidden="true" style={{color:item.color}}>{item.glyph}</span>{item.label}
    </button>)}
    <label className="climax-all"><Checkbox checked={allPoints} onCheckedChange={checked=>onAllPoints(checked===true)}/><span>Every CE/PE point</span></label>
  </div>;
}

export function OptionClimaxDetails({points,allPoints}:{points:Row[];allPoints:boolean}) {
  return <details className="climax-details option-climax-details"><summary>{points.length} CE/PE {allPoints?'qualifying points':'burst markers'} in this view · trial thresholds</summary>
    <p>Volume ≥2.5×. OI additions/reductions ≥3× and ≥0.5% of starting basket OI. Each ratio uses the median of the prior four 5m windows. {allPoints?'Every qualifying publication is shown.':'The first qualifying publication marks each burst; overlapping 5m windows share a burst.'}</p>
    <p>Triangles show OI additions or reductions. They describe OI flow, not price direction. Hover or tap for values; controls above the chart isolate each type.</p>
    {points.length?<div className="climax-event-table"><table><thead><tr><th>Available IST</th><th>Basket / metric</th><th>Ratio</th><th>OI size</th></tr></thead><tbody>{points.map(point=><tr key={point.id}><td>{clock(point.x,true)}</td><td style={{color:meta(point.key).color}}>{meta(point.key).label}</td><td>{volumeRatioLabel(point.ratio)}</td><td>{point.metric==='volume'?'—':`${fmt(point.oiPercent)}%`}</td></tr>)}</tbody></table></div>
      :<p>Markers need complete prior windows and qualifying activity. Earlier missing basket values remain unavailable.</p>}
  </details>;
}
