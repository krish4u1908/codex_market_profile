import {memo} from 'react';
import {Checkbox} from './ui/checkbox';
import {clock,fmt,signed,type Frame,type Row} from './market-types';

export const ENTRY_BUBBLE_COLORS={green:{fill:'rgba(70,216,164,0.22)',stroke:'rgba(70,216,164,0.72)'},
  red:{fill:'rgba(255,118,140,0.22)',stroke:'rgba(255,118,140,0.72)'}};
const escape=(value:unknown)=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');

export function entryBubbleTooltip(row:Row) {
  const lines=(row.spikes||[]).map((s:Row)=>`<b>${fmt(s.strike,0)} ${escape(s.side)}</b> · OI −${fmt(s.dropPct)}% · ${fmt(s.multiple)}× normal`
    +`<br/>OI ${fmt(s.oiFrom,0)} → ${fmt(s.oiTo,0)}`
    +`<br/>VIX ${signed(s.setup?.vixChangePct)}% / 5m · premium ${signed(s.setup?.premium?.changePct)}%`
    +`<br/>Setup available ${clock(s.setup?.at,true)} IST`
    +`<br/>Index ${fmt(s.index)} · cash ${signed(s.cashPct)}%`
    +`<br/>Volume VPOC ${fmt(s.vpoc,0)} · manual review only`);
  return `<strong>${row.direction==='LONG'?'Long':'Short'} entry setup · research</strong>`
    +`<br/>OI report received ${clock(row.x,true)} IST<br/>${lines.join('<br/><br/>')}`;
}

export function entryBubbleMarks(points:Row[],min:number,max:number):any {
  const visible=points.filter(row=>row.x>=min&&row.x<=max);
  return {id:'near-otm-oi-entry-bubbles',name:'OI entry setups',type:'custom',xAxisIndex:1,yAxisIndex:1,
    dimensions:['time','band'],encode:{x:0,y:1},clip:true,progressive:0,z:30,emphasis:{disabled:true},
    renderItem:(params:any,api:any)=>{
      const x=api.coord([api.value(0),.5])[0],area=params.coordSys;
      if(x<area.x||x>area.x+area.width)return null;
      const color=ENTRY_BUBBLE_COLORS[visible[params.dataIndex]?.state as 'green'|'red']||ENTRY_BUBBLE_COLORS.green;
      return {type:'group',children:[
        {type:'circle',shape:{cx:x,cy:area.y+8,r:10},style:{fill:'rgba(0,0,0,0)'}},
        {type:'circle',shape:{cx:x,cy:area.y+8,r:6.5},style:{fill:color.fill,stroke:color.stroke,lineWidth:1.3}},
      ]};
    },
    tooltip:{trigger:'item',formatter:(p:any)=>entryBubbleTooltip(p.data)},
    data:visible.map(row=>({...row,value:[row.x,.5]})),
  };
}

export const EntryBubbleReview=memo(function EntryBubbleReview({frame,min,show,onShow,onSeek,canSeek}:{
  frame:Frame;min:number;show:boolean;onShow:(value:boolean)=>void;onSeek:(value:number)=>void;canSeek:boolean;
}) {
  if(frame.profile.version!=='2.0.0')return null;
  const events=frame.entryBubbles.filter(r=>r.x>=min),assessments=frame.entryAssessments.filter(r=>r.x>=min);
  const longs=events.filter(r=>r.direction==='LONG').length,shorts=events.filter(r=>r.direction==='SHORT').length;
  return <div className="entry-bubble-review">
    <div className="entry-bubble-caption">
      <label><Checkbox checked={show} onCheckedChange={v=>onShow(v===true)}/><strong>Entry bubbles</strong><span className="mini-label">Research</span></label>
      <span><i className="entry-dot green"/> Long {longs}</span><span><i className="entry-dot red"/> Short {shorts}</span>
      <span className="entry-policy-note">Near OTM · OI fall ≥1% · ≥3× normal · VPOC: manual</span>
    </div>
    <details className="entry-audit"><summary>Review {assessments.length} OI-spike reports in view</summary>
      <p>Three nearest OTM strikes. Long: VIX rise ≥0.4%. Short: either VIX move ≥0.4%. Premium rebound within the preceding 3 minutes; VIX uses completed-minute closes.</p>
      <p>Market filters: published broader trend and cash basket above/below its open. VPOC is for manual review only. Bubbles appear at OI receipt time.</p>
      {!assessments.length&&<p>No eligible near-OTM OI spikes with complete input history in this view.</p>}
      <div className="entry-audit-list">{[...assessments].reverse().map(row=><div key={row.id} className="entry-audit-row">
        <button disabled={!canSeek} onClick={()=>onSeek(row.x)} title={canSeek?'Replay from this OI report':'Open replay to seek'}>{clock(row.x,true)}</button>
        <div><strong className={row.status==='ENTRY'?(row.direction==='LONG'?'entry-green':'entry-red'):''}>{row.status==='ENTRY'?`${row.direction==='LONG'?'Long':'Short'} bubble`:`${row.side} spike · filtered`}</strong>
          {row.spikes.map((s:Row)=><p key={s.symbol}>{fmt(s.strike,0)} {s.side} · OI −{fmt(s.dropPct)}% · {fmt(s.multiple)}×
            {s.eligible?<span> · VIX {signed(s.setup.vixChangePct)}% · premium {signed(s.setup.premium.changePct)}%</span>:<span> · {s.reasons.join('; ')}</span>}</p>)}
        </div>
      </div>)}</div>
    </details>
  </div>;
});
