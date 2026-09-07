"use client";
import {Fragment,memo} from 'react';
import {BarChart3} from 'lucide-react';
import {COLORS,clock,compact,fmt,signed,words,type Frame,type Row} from './market-types';

function OIBars({row,side,scale}:{row:Row|null;side:'CE'|'PE';scale:number}) {
  const metrics=[
    {key:'oi',label:'Total OI',value:row?.oi,color:side==='PE'?COLORS.positive:COLORS.negative},
    {key:'cumPositive',label:'Cumulative +OI added',value:row?.cumPositive,color:COLORS.positive},
    {key:'cumNegative',label:'Cumulative −OI removed',value:row?.cumNegative,color:COLORS.negative},
  ];
  return <div className={`oi-bar-group oi-bar-${side.toLowerCase()}`}>
    {metrics.map(({key,label,value,color})=>{
      const valid=Number.isFinite(value);
      const text=!valid?'—':`${key==='cumPositive'?'+':key==='cumNegative'&&value<0?'−':''}${compact(Math.abs(value))}`;
      return <div key={key} className={`oi-bar-metric ${key==='oi'?'oi-bar-total':'oi-bar-cumulative'}`} title={`${label}: ${valid?fmt(value,0):'Unavailable'}${row?` · receipt ${clock(row.x,true)} IST`:''}`}>
        <span className="oi-bar-track" aria-hidden="true"><i style={{width:valid?`${Math.abs(value)/scale*100}%`:'0%',background:color}}/></span>
        <span className="oi-bar-value" style={{color:key==='oi'?'#e1ecf8':color}}><span className="sr-only">{side} {label}: </span>{text}</span>
      </div>;
    })}
  </div>;
}

export function OptionOITotals({row}:{row:Row|undefined}) {
  return <div className="option-oi-totals" title={`Cumulative changes since ${clock(row?.cumFrom,true)} IST${row?.cumPartial?' · partial: missing receipt deltas':''}`}>
    <div><span>Total OI</span><strong>{compact(row?.oi)}</strong></div>
    <div className="oi-added"><span>Cum +OI</span><strong>{row?`+${compact(row.cumPositive)}`:'—'}</strong></div>
    <div className="oi-removed"><span>Cum −OI</span><strong>{row?`${row.cumNegative<0?'−':''}${compact(Math.abs(row.cumNegative))}`:'—'}</strong></div>
    {row?.cumPartial&&<small>Partial cumulative data</small>}
  </div>;
}

function FuturesOIDeltas({frame}:{frame:Frame}) {
  const row=frame.oi.at(-1);
  const scale=Math.max(1,row?.oi||0,row?.cumPositive||0,Math.abs(row?.cumNegative||0));
  const metrics=[
    {label:'Total OI',value:row?.oi,color:COLORS.oi,total:true},
    {label:'Cum +OI',value:row?.cumPositive,color:COLORS.positive,total:false},
    {label:'Cum −OI',value:row?.cumNegative,color:COLORS.negative,total:false},
  ];
  return <div className="futures-oi-deltas" aria-label={`${frame.profile.label} futures OI and cumulative deltas`}>
    <div className="futures-oi-heading"><h3>{frame.profile.shortLabel} futures · OI</h3><span>Latest Δ <strong style={{color:row?.d==null?COLORS.muted:row.d>=0?COLORS.positive:COLORS.negative}}>{signed(row?.d,0)}</strong></span></div>
    {row?<>
      {metrics.map(({label,value,color,total})=><div className={`futures-oi-metric ${total?'futures-oi-total':''}`} key={label} title={`${label}: ${fmt(value,0)}`}>
        <span>{label}</span><i aria-hidden="true"><b style={{width:Number.isFinite(value)?`${Math.abs(value)/scale*100}%`:'0%',background:color}}/></i>
        <strong style={{color}}>{!Number.isFinite(value)?'—':total?compact(value):`${value>0?'+':value<0?'−':''}${compact(Math.abs(value))}`}</strong>
      </div>)}
      <p className="oi-profile-caption">Receipt {clock(row.x,true)} IST{frame.capabilities.cumulativeFutures?` · cumulative from ${clock(row.cumFrom)}`:' · minute snapshot; receipt deltas unavailable'}{row.cumPartial?<><br/>Partial cumulative data: missing receipt deltas.</>:null}</p>
    </>:<p className="oi-profile-caption">Futures deltas appear after 09:45 IST.</p>}
  </div>;
}

export const OptionOIProfile=memo(function OptionOIProfile({frame}:{frame:Frame}) {
  const profile=frame.optionProfile,spot=frame.latest?.i;
  const spotLine=<div className="oi-profile-spot"><span>INDEX</span><strong>{fmt(spot)}</strong><i/></div>;
  return <section className="insight-card option-profile-card" aria-label="Option OI, potential support and resistance">
    <div className="side-heading"><h2><BarChart3 size={16}/> Options · support / resistance</h2></div>
    <div className="oi-profile-candidates">
      <div className="oi-support"><span>Potential support</span><strong>{fmt(profile.support,0)}</strong><small>{profile.support==null?'No level below price':`${signed(profile.support-spot,0)} pts · PE OI`}</small></div>
      <div className="oi-resistance"><span>Potential resistance</span><strong>{fmt(profile.resistance,0)}</strong><small>{profile.resistance==null?'No level above price':`${signed(profile.resistance-spot,0)} pts · CE OI`}</small></div>
    </div>
    {profile.rows.length?<>
      <div className="oi-profile-legend"><b>Total OI</b><span className="oi-added">+ cumulative</span><span className="oi-removed">− cumulative</span></div>
      <div className="oi-profile-columns"><span>PE / puts</span><span>Strike</span><span>CE / calls</span></div>
      <div className="oi-profile-ladder" role="list" aria-label="Open interest at seven nearby strikes">
        {spot>profile.rows[0].strike&&spotLine}
        {profile.rows.map((row,index)=><Fragment key={row.strike}>
          <div role="listitem" className={`oi-profile-row ${row.strike===profile.support?'oi-support-row':''} ${row.strike===profile.resistance?'oi-resistance-row':''}`}>
            <OIBars row={row.PE} side="PE" scale={profile.scale}/>
            <div className="oi-strike"><strong>{fmt(row.strike,0)}</strong>{row.strike===profile.support?<small>Support</small>:row.strike===profile.resistance?<small>Resistance</small>:null}</div>
            <OIBars row={row.CE} side="CE" scale={profile.scale}/>
          </div>
          {spot<=row.strike&&(index===profile.rows.length-1||spot>profile.rows[index+1].strike)&&spotLine}
        </Fragment>)}
      </div>
      <p className="oi-profile-caption">{profile.rows.length} nearby strikes · expiry {profile.expiry}<br/>OI receipt {clock(profile.oldestReceipt,true)}{profile.oldestReceipt!==profile.newestReceipt?`–${clock(profile.newestReceipt,true)}`:''} IST</p>
    </>:<p className="empty-copy">{frame.capabilities.strikeReceipts?'Option OI appears after the retained basket publication.':frame.provenance.input_note||'No strike receipts were retained for this session.'}</p>}
    <FuturesOIDeltas frame={frame}/>
    <details className="oi-profile-details"><summary>How to read these bars</summary>
      <p>Thick bars show total outstanding OI. Thin bars show cumulative additions (+) and removals (−) from the first available receipt after 09:45 to the replay time. Option bars share one scale; futures bars share a separate scale. Removals are shown by magnitude.</p>
      <p>Potential levels mark the highest PE OI below the index and CE OI above it among the displayed strikes. These are OI concentrations; price confirmation is still needed. <a href="https://zerodha.com/z-connect/sensibull/historical-open-interest-oi-on-kite" target="_blank" rel="noreferrer">About OI levels ↗</a></p>
      <p>Positive and negative cumulative changes are separate gross flows; total OI is the current outstanding balance.</p>
      <dl><div><dt>Price receipt</dt><dd>{clock(frame.latest?.x,true)} IST</dd></div><div><dt>Price / futures age</dt><dd>{fmt(frame.latest?.age,0)} ms</dd></div><div><dt>Call input quality</dt><dd>{words(frame.call?.quality?.status||'Not recorded')}</dd></div></dl>
    </details>
    {profile.partial&&<p className="oi-profile-caption">Cumulative figures are partial where receipt deltas are missing.</p>}
  </section>;
});
