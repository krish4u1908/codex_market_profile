import {COLORS,clock,fmt,signed,type Row} from './market-types';

export const VIX_MARK_COLORS={red:'rgba(255,118,140,0.48)',green:'rgba(70,216,164,0.48)'};

export function vixRibbonMarks(points:Row[],min:number,max:number):any {
  return {
    id:'vix-5m-ribbon-marks',name:'VIX change · 5m',type:'custom',xAxisIndex:1,yAxisIndex:1,
    dimensions:['time','band'],encode:{x:0,y:1},clip:true,progressive:0,z:20,
    emphasis:{disabled:true},
    renderItem:(params:any,api:any)=>{
      const x=api.coord([api.value(0),.5])[0],area=params.coordSys;
      if(x<area.x||x>area.x+area.width)return null;
      return {type:'group',children:[
        {type:'rect',shape:{x:x-6,y:area.y,width:12,height:area.height},style:{fill:'rgba(0,0,0,0)'}},
        {type:'rect',shape:{x:x-2.5,y:area.y+1,width:5,height:area.height-2,r:1.5},style:{fill:api.visual('color')}},
      ]};
    },
    tooltip:{trigger:'item',formatter:(p:any)=>{
      const row=p.data;
      return `<strong>VIX 5m ${signed(row.changePct)}%</strong><br/>${row.state==='red'?'Rise ≥ +0.4%':'Fall ≤ −0.4%'}`
        +`<br/>VIX ${fmt(row.from,3)} → ${fmt(row.to,3)}`
        +`<br/>Minute closes ${clock(row.baselineEnd)}–${clock(row.minuteEnd)} IST`
        +`<br/>Available ${clock(row.x,true)} IST`;
    }},
    data:points.filter(row=>row.x>=min&&row.x<=max).map(row=>({...row,value:[row.x,.5],
      itemStyle:{color:VIX_MARK_COLORS[row.state as 'red'|'green']}})),
  };
}

export function VixRibbonCaption({latest}:{latest:Row|null}) {
  return <div className="vix-ribbon-caption" aria-label="Five-minute VIX change marks">
    <strong>VIX · 5m marks</strong>
    <span><i style={{background:VIX_MARK_COLORS.red}}/> ≥ +0.4%</span>
    <span><i style={{background:VIX_MARK_COLORS.green}}/> ≤ −0.4%</span>
    <span className="vix-ribbon-reading" style={{color:latest?.state==='red'?COLORS.negative:latest?.state==='green'?COLORS.positive:COLORS.muted}}>
      {latest?.changePct!=null?`${signed(latest.changePct)}%`:'Awaiting complete 5m window'}
    </span>
  </div>;
}
