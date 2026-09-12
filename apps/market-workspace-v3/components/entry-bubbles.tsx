import {memo} from 'react';
import {Checkbox} from './ui/checkbox';
import {fmt,signed,type Frame,type Row} from './market-types';

export const ENTRY_BUBBLE_COLORS={green:{fill:'rgba(70,216,164,0.26)',stroke:'rgba(70,216,164,0.85)'},
  red:{fill:'rgba(255,118,140,0.26)',stroke:'rgba(255,118,140,0.85)'},
  yellow:{fill:'rgba(250,204,85,0.26)',stroke:'rgba(250,204,85,0.9)'}};
const escape=(value:unknown)=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const receiptClock=(x:number)=>new Date(x+19800000).toISOString().slice(11,23);
const category=(r:Row)=>`${r.side} OI fall · VIX ${r.vixDirection==='UP'?'↑':'↓'}`;
const watchLabel=(r:Row)=>r.watch==='LONG_WATCH'?'Long watch':r.watch==='SHORT_WATCH'?'Short watch':'Research';
export function entryBubbleTooltip(row:Row) {
  const v=row.vixWindow;
  return `<strong>${escape(category(row))}</strong><br/>OI report ${receiptClock(row.x)} IST`
    +`<br/>${watchLabel(row)} · ${escape(row.state)} bubble`
    +`<br/>VIX ${fmt(v.from,3)} → ${fmt(v.to,3)} · ${signed(v.changePct)}%`
    +`<br/>Report quotes ${receiptClock(v.fromAt)}–${receiptClock(row.x)} IST (${fmt(v.elapsedSeconds,1)}s)`
    +`<br/>${row.side==='PE'?'Above':'Below'} ribbon · three nearest OTM strikes`
    +'<br/>'+row.spikes.map((s:Row)=>`<b>${fmt(s.strike,0)} ${escape(s.side)}</b> · OI −${fmt(s.dropPct)}% · ${fmt(s.multiple)}× normal`
      +`<br/>OI ${fmt(s.oiFrom,0)} → ${fmt(s.oiTo,0)}`).join('<br/>');
}
export function entryBubbleMarks(points:Row[],min:number,max:number):any {
  const visible=points.filter(row=>row.x>=min&&row.x<=max);
  return {id:'near-otm-oi-entry-bubbles',name:'OI / VIX conditions',type:'custom',xAxisIndex:1,yAxisIndex:1,
    dimensions:['time','band'],encode:{x:0,y:1},clip:true,progressive:0,z:30,emphasis:{disabled:true},
    renderItem:(params:any,api:any)=>{
      const x=api.coord([api.value(0),.5])[0],area=params.coordSys,row=visible[params.dataIndex];
      if(x<area.x||x>area.x+area.width)return null;
      const color=ENTRY_BUBBLE_COLORS[row.state as keyof typeof ENTRY_BUBBLE_COLORS];
      const y=row.side==='PE'?area.y+9:area.y+area.height-9;
      return {type:'group',children:[
        {type:'circle',shape:{cx:x,cy:y,r:9},style:{fill:'rgba(0,0,0,0)'}},
        {type:'circle',shape:{cx:x,cy:y,r:7},style:{fill:color.fill,stroke:color.stroke,lineWidth:1.4}},
      ]};
    },
    tooltip:{trigger:'item',formatter:(p:any)=>entryBubbleTooltip(p.data)},
    data:visible.map(row=>({...row,value:[row.x,row.side==='PE'?.85:.15]})),
  };
}
export const EntryBubbleReview=memo(function EntryBubbleReview({frame,min,show,onShow,onSeek,canSeek}:{
  frame:Frame;min:number;show:boolean;onShow:(value:boolean)=>void;onSeek:(value:number)=>void;canSeek:boolean;
}) {
  if(frame.profile.version!=='2.0.0')return null;
  const events=frame.entryBubbles.filter(r=>r.x>=min),assessments=frame.entryAssessments.filter(r=>r.x>=min);
  return <div className="entry-bubble-review">
    <div className="entry-bubble-caption">
      <label><Checkbox checked={show} onCheckedChange={v=>onShow(v===true)}/><strong>OI / VIX bubbles</strong></label>
      {['PE','CE'].map(side=><span key={side}><b>{side} {side==='PE'?'above':'below'}</b> · <i className={`entry-dot ${side==='PE'?'green':'red'}`}/> {side==='PE'?'Long':'Short'} {events.filter(r=>r.side===side&&r.state===(side==='PE'?'green':'red')).length} · <i className="entry-dot yellow"/> Research {events.filter(r=>r.side===side&&r.state==='yellow').length}</span>)}
      <span className="entry-policy-note">OI fall ≥1% · ≥3× normal · VIX ±0.4% / 5m</span>
    </div>
    {frame.entryStatus?.status!=='AVAILABLE'&&<p role="status">{frame.entryStatus?.reason||'Option-report quotes unavailable for this session.'}</p>}
    <details className="entry-audit"><summary>Review {events.length} matches / {assessments.length} OI-spike reports in view</summary>
      <p>Green above: PE OI fall with VIX rise ≥0.4% (long watch). Red below: CE OI fall with VIX fall ≥0.4% (short watch). Yellow: PE OI fall with VIX fall, or CE OI fall with VIX rise, for research.</p>
      <p>Three nearest strict OTM strikes at each report. OI fall is compared with the previous report and the median absolute percentage change of the previous 20 updates. Colours identify watch conditions; subsequent price movement is evaluated separately.</p>
      <p>VIX uses the quote in the OI report versus the report five minute slots earlier. The VIX line and vertical ribbon marks continue to use completed-minute closes. Bubbles use collector receipt times; live display follows receipt processing.</p>
      <p>Screening starts at 09:45 with history from 09:15. Trend, price, premium, cash, VPOC and day-high filters are not applied.</p>
      {!assessments.length&&frame.entryStatus?.status==='AVAILABLE'&&<p>No qualifying OI spikes at this replay time.</p>}
      <div className="entry-audit-list">{[...assessments].reverse().map(row=><div key={row.id} className="entry-audit-row">
        <button disabled={!canSeek} onClick={()=>onSeek(row.x)} title={canSeek?'Replay from this OI report':'Open replay to seek'}>{receiptClock(row.x)}</button>
        <div><strong className={row.status==='MATCH'?`entry-${row.state}`:''}>{row.status==='MATCH'?`${category(row)} · ${watchLabel(row)}`:`${row.side} OI spike · ${row.reason}`}</strong>
          {row.vixWindow&&<p>VIX {signed(row.vixWindow.changePct)}% / 5m</p>}
          {row.spikes.map((s:Row)=><p key={s.symbol}>{fmt(s.strike,0)} {s.side} · OI −{fmt(s.dropPct)}% · {fmt(s.multiple)}×</p>)}
        </div>
      </div>)}</div>
    </details>
  </div>;
});
