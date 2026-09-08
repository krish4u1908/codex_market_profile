"use client";
import {forwardRef,memo,useCallback,useEffect,useImperativeHandle,useMemo,useRef,useState} from 'react';
import {Activity,ArrowDownRight,ArrowUpRight,BarChart3,CalendarDays,Check,ChevronDown,Clock3,Focus,Layers3,Loader2,MessageSquareText,Pause,Play,Radio,RotateCcw,Settings2,SkipBack,SkipForward,StepBack,StepForward,X} from 'lucide-react';
import type {EChartsOption} from 'echarts';
import {Tabs,TabsList,TabsTrigger,TabsContent} from '@/components/ui/tabs';
import {Select,SelectTrigger,SelectValue,SelectContent,SelectItem} from '@/components/ui/select';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from '@/components/ui/sheet';
import {Checkbox} from '@/components/ui/checkbox';
import {Slider} from '@/components/ui/slider';
import {Table,TableHeader,TableHead,TableBody,TableRow,TableCell} from '@/components/ui/table';
import {ChartPanel,Plot,baseChart,line} from './market-chart';
import {OptionOIProfile,OptionOITotals} from './option-oi-profile';
import {PROFILES,getProfile} from '../public/profiles.mjs';
import {summaryInput} from '../public/market-data.mjs';
import {climaxMarkers,V2VolumePanel} from './volume-climax';
import {V2Context,V2FlowCharts} from './v2-context';
import {COLORS,STRIKES,LEVELS,clock,compact,fmt,signed,words,type Frame,type Row} from './market-types';

type Meta={session:string;start:number;end:number;analysisStart:number;provenance:Row};
type Flags={basis:boolean;oi:boolean;vix:boolean;cash:boolean;flows:boolean;levels:boolean;zones:boolean};
const defaultFlags:Flags={basis:true,oi:true,vix:true,cash:false,flows:true,levels:true,zones:false};
const dateLabel=(date:string)=>new Date(`${date}T12:00:00+05:30`).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'});
const colorFor=(v:any)=>v==null?COLORS.muted:v>=0?COLORS.positive:COLORS.negative;

function Choice({value,choices,onChange,label}:{value:string;choices:{value:string;label:string}[];onChange:(v:string)=>void;label:string}){
  return <Select value={value} onValueChange={onChange}><SelectTrigger className="control-select" aria-label={label}><SelectValue/></SelectTrigger><SelectContent>{choices.map(c=><SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}</SelectContent></Select>;
}

const SummaryPanel=forwardRef<{open:()=>void},{frame:Frame}>(function SummaryPanel({frame},ref){
  const latest=useRef(frame),worker=useRef<Worker|null>(null),generation=useRef(0);
  const [open,setOpen]=useState(false),[busy,setBusy]=useState(false),[result,setResult]=useState<Row|null>(null),[error,setError]=useState('');
  latest.current=frame;
  useEffect(()=>()=>worker.current?.terminate(),[]);
  useEffect(()=>{generation.current++;worker.current?.terminate();worker.current=null;setResult(null);setBusy(false);setError('');},[frame.session]);
  const generate=useCallback(()=>{
    setOpen(true);setBusy(true);setError('');const id=++generation.current;
    requestAnimationFrame(()=>{if(window.innerWidth<=960)document.getElementById('market-summary')?.scrollIntoView({block:'nearest',behavior:'smooth'});});
    worker.current?.terminate();
    const w=new Worker('/summary-worker.js',{type:'module'});worker.current=w;
    const timer=window.setTimeout(()=>{if(id===generation.current){w.terminate();setBusy(false);setError('Summary timed out. Your charts are still available.');}},15000);
    w.onmessage=e=>{if(e.data.id!==generation.current)return;clearTimeout(timer);setBusy(false);if(e.data.error)setError(e.data.error);else setResult(e.data.summary);w.terminate();};
    w.onerror=()=>{clearTimeout(timer);setBusy(false);setError('Summary could not load. Try again.');w.terminate();};
    w.postMessage({id,frame:summaryInput(latest.current)});
  },[]);
  useImperativeHandle(ref,()=>({open:generate}),[generate]);
  return <section id="market-summary" className="insight-card summary-card">
    <div className="side-heading"><h2><MessageSquareText size={16}/> Market summary</h2>{open&&<button className="icon-button" aria-label="Collapse market summary" onClick={()=>setOpen(false)}><X size={16}/></button>}</div>
    {!open?<><p className="muted">Review the current snapshot, call drivers and input quality.</p><button className="secondary-button full-width" onClick={generate}>Show market summary <ArrowUpRight size={15}/></button></>:<>
      <div className="summary-status"><span>{busy?'Reading this snapshot…':result?`As of ${clock(result.asOf,true)} IST`:'Summary unavailable'}</span><button className="text-button" onClick={generate} disabled={busy}>{busy?<Loader2 size={15} className="spin"/>:<RotateCcw size={14}/>} Refresh</button></div>
      {error&&<p role="alert" className="inline-error">{error}</p>}
      {busy&&!result&&<div className="summary-loading" role="status"><Loader2 className="spin" size={18}/><span>Preparing market summary</span></div>}
      {result&&<div className="summary-body"><h3>{result.title}</h3><ul>{result.facts.map((fact:string,i:number)=><li key={i}>{fact}</li>)}</ul><div className="note-block"><span>Reassess when</span><p>{result.invalidation}</p></div><details><summary>Input quality · {words(result.quality)}</summary><ul>{Object.entries(result.issues).map(([k,v])=><li key={k}>{words(k)}: {words(v)}</li>)}</ul><p>Call published {clock(result.publishedAt,true)} IST. {frame.profile.callLabel}.</p></details></div>}
    </>}
  </section>;
});

function CallCard({frame,onSummary}:{frame:Frame;onSummary:()=>void}){
  const c=frame.call,up=c?.direction==='UP',down=c?.direction==='DOWN';
  return <section className={`insight-card call-card ${up?'call-up':down?'call-down':''}`}>
    <div className="side-heading"><h2>{frame.profile.version==='2.0.0'?'Reference call':'Current call'}</h2><span className="mini-label">v{frame.profile.version}</span></div>
    <div className="call-main"><span className="call-direction">{up?<ArrowUpRight size={27}/>:down?<ArrowDownRight size={27}/>:<Clock3 size={25}/>} {c?.direction||'WAIT'}</span><div className="call-score"><strong>{signed(c?.score)}</strong><span>direction score</span></div></div>
    <p className="call-state">{c?.state?words(c.state):c?.source_note||'Awaiting a saved call'}</p>
    <div className="call-meta"><span>{words(c?.confidence)} confidence</span><span>{c?.horizon_minutes?`${c.horizon_minutes} min horizon`:'Horizon not recorded'}</span></div>
    <div className="score-track"><span style={{width:`${Math.min(100,Math.abs(c?.score||0)/10*100)}%`,background:up?COLORS.positive:down?COLORS.negative:COLORS.muted}}/></div>
    <div className="driver-list">{(c?.drivers||[]).slice(0,4).map((s:string,i:number)=><div key={i}><span>{s.replace(/\s[-+]?\d[\d.,]*$/,'')}</span><strong>{s.match(/[-+]?\d[\d.,]*$/)?.[0]||'—'}</strong></div>)}</div>
    <button className="text-button call-details" onClick={onSummary}>Why this call <ArrowUpRight size={14}/></button>
    <p className="footnote">Available {clock(c?.x,true)} IST · {frame.profile.callLabel}</p>
  </section>;
}

function LevelList({frame,scope}:{frame:Frame;scope:string}){
  const levels=scope==='ID'?frame.controls:frame.prior.filter(r=>r.scope===scope&&r.status==='AVAILABLE');
  return <section className="insight-card"><div className="side-heading"><h2><Layers3 size={16}/> Control levels</h2><span className="mini-label">{scope==='ID'?'Intraday':scope}</span></div>
    {levels.length?<div className="levels-list">{levels.map((r,i)=><div key={`${r.family}-${i}`} className="level-row"><span className="level-name"><i style={{background:LEVELS[r.family]?.color||COLORS.price}}/>{LEVELS[r.family]?.label||words(r.family)}</span><strong>{fmt(r.control_value,0)}</strong><small style={{color:colorFor((r.control_value??0)-(frame.latest?.i??0))}}>{signed(r.control_value-(frame.latest?.i??0),0)}</small></div>)}</div>:<p className="empty-copy">No available control levels at this time.</p>}
    <p className="footnote">VPOC · distance from current index in points</p>{frame.provenance.timing_note&&<p className="source-note">{frame.provenance.timing_note}</p>}
  </section>;
}

const MarketCharts=memo(function MarketCharts({frame,flags,scope,windowMinutes,onLevelsChange}:{frame:Frame;flags:Flags;scope:string;windowMinutes:number;onLevelsChange:(show:boolean)=>void}){
  const min=windowMinutes?Math.max(frame.start,frame.now-windowMinutes*60000):frame.start;
  const max=Math.max(min+60000,frame.now);
  const visibleLevels=useMemo(()=>{
    if(!flags.levels)return [];
    const levels=scope==='ID'?frame.controls:frame.prior.filter(r=>r.scope===scope&&r.status==='AVAILABLE');
    const order=Object.keys(LEVELS);
    return levels.filter(r=>r.control_value!=null&&Number.isFinite(Number(r.control_value)))
      .slice().sort((a,b)=>order.indexOf(a.family)-order.indexOf(b.family));
  },[frame,flags.levels,scope]);
  const oiLevels=visibleLevels.filter(r=>r.family.includes('_OI_VPOC'));
  const chartOptions=useMemo(()=>{
    const priceBase=baseChart(min,max);
    const series:any[]=[line(frame.profile.label,frame.price,'i',COLORS.price,{lineStyle:{width:2.3,color:COLORS.price},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'#54cfff1f'},{offset:1,color:'#54cfff00'}]}}})];
    if(flags.levels){
      for(const level of visibleLevels){
        const meta=LEVELS[level.family];if(!meta)continue;
        const rows:Row[]=scope==='ID'?frame.controlHistory.filter(r=>r.family===level.family).map(r=>({...r,control_value:r.status==='AVAILABLE'?r.control_value:null})):[{x:frame.start,control_value:level.control_value}];
        if(rows.length)series.push(line(`${scope} ${meta.label} VPOC`,rows.concat({...rows.at(-1),x:frame.now}),'control_value',meta.color,{id:`vpoc-${scope}-${level.family}`,holdLastValue:true,sampling:'none',step:'end',lineStyle:{width:2,type:scope==='ID'?'solid':'dashed',color:meta.color,opacity:1},z:4}));
      }
      // Coincident families share one tag; the legend lists each family's exact value.
      const grouped=new Map<number,Row[]>();
      for(const level of visibleLevels.filter(r=>r.family.includes('_OI_VPOC'))){
        const value=Number(level.control_value);grouped.set(value,[...(grouped.get(value)||[]),level]);
      }
      series.push({name:'OI-VPOC levels',type:'scatter',symbol:'circle',symbolSize:5,z:12,
        labelLayout:{moveOverlap:'shiftY'},
        data:[...grouped.entries()].map(([value,levels])=>{
          const meta=LEVELS[levels[0].family];
          const caption=levels.length===1?meta.label.replace('Futures','FUT'):`${levels.length} OI-VPOCs`;
          return {name:levels.map(r=>LEVELS[r.family]?.label).join(' / '),value:[frame.now,value],
            itemStyle:{color:meta.color},
            label:{show:true,position:'left',distance:7,formatter:`${caption}  ${fmt(value,0)}`,color:meta.color,fontSize:11,fontWeight:500,backgroundColor:'#0e1b2af2',borderColor:meta.color,borderWidth:.5,borderRadius:3,padding:[3,5]},
          };
        }),
      });
    }
    if(frame.profile.version==='2.0.0')series.push(climaxMarkers(frame.volumeClimaxes.filter(row=>row.x>=min&&row.x<=max),'price'));
    if(flags.zones)series[0].markArea={silent:true,data:frame.zones.map(z=>[{xAxis:Date.parse(z.confirmed_at),itemStyle:{color:z.colour==='GREEN'?'#46d8a412':'#ff768c12'}},{xAxis:z.ended_at?Date.parse(z.ended_at):frame.now}])};
    const basis={...baseChart(min,max),series:[line('Basis',frame.price,'b',COLORS.basis)]};
    const vix={...baseChart(min,max),series:[line('India VIX · value',frame.cash,'vix_close',COLORS.vix,{lineStyle:{color:COLORS.vix,width:1.8,type:'dashed'}})]};
    const cash={...baseChart(min,max),series:[line('Weighted cash · rolling %',frame.cash,'cash_rolling_pct',COLORS.cash)]};
    const oi:any={...baseChart(min,max),yAxis:[{...(baseChart(min,max).yAxis as object),position:'left'},{type:'value',show:false,scale:true}],series:[{name:'Futures ΔOI',type:'bar',yAxisIndex:1,barMaxWidth:5,data:frame.oi.map(r=>({value:[r.x,r.d],itemStyle:{color:r.d>=0?'#46d8a447':'#ff768c47'}}))},line('Futures OI',frame.oi,'oi',COLORS.oi,{z:3})]};
    return {price:{...priceBase,series},basis,vix,cash,oi};
  },[frame,flags,scope,min,max,visibleLevels]);
  return <div className="chart-stack">
    <ChartPanel title={frame.profile.label} subtitle="Index · 1m view" value={fmt(frame.latest?.i)} colour={COLORS.price} className="price-panel">
      <div className="price-level-legend" aria-label="OI-VPOC price overlays"><span className="price-level-caption">OI-VPOC · {scope==='ID'?'Intraday':scope}</span><label className="vpoc-visibility"><Checkbox checked={flags.levels} onCheckedChange={checked=>onLevelsChange(checked===true)}/><span>Show lines</span></label>{flags.levels?<>{oiLevels.map(level=><span className="price-level-chip" key={level.family} title={`${LEVELS[level.family]?.label} VPOC${level.x?' · published '+clock(level.x,true)+' IST':''}`}><i style={{background:LEVELS[level.family]?.color}}/><span>{LEVELS[level.family]?.label}</span><strong>{fmt(level.control_value,0)}</strong></span>)}{!oiLevels.length&&<span className="price-level-empty">{scope==='ID'?'Awaiting published levels':`No ${scope} reference levels available`}</span>}</>:<span className="price-level-empty">VPOC overlays are hidden</span>}</div>
      {frame.profile.version==='2.0.0'&&<div className="climax-legend"><span aria-hidden="true">◆</span> Volume climax &gt;4× <small>Ratio labels · hover or tap for details</small></div>}
      <Plot label={`${frame.profile.label} index with labeled CE, PE and futures positive and negative OI-VPOC levels`} option={chartOptions.price} height={330}/><div className="chart-footer"><span><Focus size={13}/> Shared time cursor</span><span>Ctrl + scroll to zoom · pinch on touch</span><span>{clock(min)} – {clock(max)} IST</span></div>
    </ChartPanel>
    {frame.profile.version==='2.0.0'&&<V2VolumePanel frame={frame} min={min} max={max}/>}
    {flags.vix&&<ChartPanel title="India VIX" subtitle="Actual value · dashed" value={fmt(frame.cash.at(-1)?.vix_close)} colour={COLORS.vix}><Plot option={chartOptions.vix} label="India VIX actual retained values" height={138}/></ChartPanel>}
    {flags.cash&&<ChartPanel title="Weighted cash" subtitle="5m rolling %" value={signed(frame.cash.at(-1)?.cash_rolling_pct)} colour={COLORS.cash}><Plot option={chartOptions.cash} label="Weighted cash rolling percentage" height={138}/></ChartPanel>}
    {flags.basis&&<ChartPanel title="Futures basis" subtitle="Futures − Index · points" value={signed(frame.latest?.b)} colour={COLORS.basis}><Plot option={chartOptions.basis} label="Synchronized futures basis" height={138}/></ChartPanel>}
    {flags.oi&&<ChartPanel title="Futures open interest" subtitle="Yellow line · signed ΔOI bars" value={compact(frame.oi.at(-1)?.oi)} colour={COLORS.oi}><Plot option={chartOptions.oi} label="Futures open interest and signed OI changes" height={160}/></ChartPanel>}
    {flags.flows&&(frame.profile.version==='2.0.0'&&!frame.capabilities.strikeReceipts?<V2FlowCharts frame={frame} min={min} max={max}/>:<><OptionFlow frame={frame} side="CE" metric="d" min={min} max={max}/><OptionFlow frame={frame} side="PE" metric="d" min={min} max={max}/></>)}
  </div>;
});

function OptionFlow({frame,side,metric,min,max}:{frame:Frame;side:'CE'|'PE';metric:'d'|'dv';min:number;max:number}){
  const contracts=frame.selection[side]||[];
  const option=useMemo(()=>({...baseChart(min,max),series:contracts.map((contract:Row,i:number)=>({name:`${fmt(contract.strike,0)} ${side}`,type:'bar',barMaxWidth:4,itemStyle:{color:STRIKES[i]},emphasis:{focus:'series'},data:frame.options.filter(r=>r.symbol===contract.symbol).map(r=>[r.x,r[metric]??null])}))}),[frame,contracts,side,metric,min,max]);
  return <ChartPanel title={`${side} ${metric==='d'?'change in OI':'incremental volume'}`} subtitle="Fixed 09:45 basket" colour={side==='CE'?COLORS.negative:COLORS.positive}><div className="strike-legend">{contracts.map((r:Row,i:number)=><span key={r.symbol}><i style={{background:STRIKES[i]}}/>{fmt(r.strike,0)} {i===0?<small>ATM</small>:null}</span>)}</div>{contracts.length?<Plot option={option as EChartsOption} label={`${side} four fixed strikes ${metric==='d'?'OI changes':'volume changes'}`} height={162}/>:<p className="empty-chart">{frame.capabilities.strikeReceipts?'Option participation becomes available after the retained basket publication.':'Individual strike receipts are not included in this export.'}</p>}</ChartPanel>;
}

function OptionWorkspace({frame,windowMinutes}:{frame:Frame;windowMinutes:number}){
  const [side,setSide]=useState<'CE'|'PE'>('CE');
  const min=windowMinutes?Math.max(frame.start,frame.now-windowMinutes*60000):frame.start,max=Math.max(min+60000,frame.now);
  const contracts=frame.selection[side]||[];
  if(frame.profile.version==='2.0.0'&&!frame.capabilities.strikeReceipts)return <div className="option-workspace"><V2Context frame={frame}/><p className="source-note">{frame.provenance.input_note}</p><V2FlowCharts frame={frame} min={min} max={max}/></div>;
  return <div className="option-workspace"><div className="section-bar"><div><h2>Option participation</h2><p>ATM + 3 OTM · selected at 09:45 · expiry {frame.selection.expiry||'unavailable'}</p></div><Tabs value={side} onValueChange={v=>setSide(v as 'CE'|'PE')}><TabsList><TabsTrigger value="CE">Calls · CE</TabsTrigger><TabsTrigger value="PE">Puts · PE</TabsTrigger></TabsList></Tabs></div>
    <div className="option-price-grid">{contracts.map((c:Row,i:number)=>{
      const rows=frame.options.filter(r=>r.symbol===c.symbol),last=rows.at(-1);
      return <ChartPanel key={c.symbol} title={`${fmt(c.strike,0)} ${side}`} subtitle={i===0?'Fixed ATM':`OTM ${i}`} value={fmt(last?.p)} colour={STRIKES[i]}><Plot sync option={{...baseChart(min,max),series:[line(`${c.strike} ${side} premium`,rows,'p',STRIKES[i])]}} label={`${c.strike} ${side} option premium`} height={180}/><OptionOITotals row={last}/><div className="option-card-footer"><span>Latest ΔOI <b style={{color:colorFor(last?.d)}}>{signed(last?.d,0)}</b></span><span>{clock(last?.x)}</span></div></ChartPanel>;
    })}</div>
    {!contracts.length&&<p className="empty-copy">The fixed option basket has not been published at this replay time.</p>}
    <OptionFlow frame={frame} side="CE" metric="d" min={min} max={max}/><OptionFlow frame={frame} side="PE" metric="d" min={min} max={max}/><OptionFlow frame={frame} side="CE" metric="dv" min={min} max={max}/><OptionFlow frame={frame} side="PE" metric="dv" min={min} max={max}/>
    <StrikeSnapshot frame={frame} side="CE"/><StrikeSnapshot frame={frame} side="PE"/>
  </div>;
}

function StrikeSnapshot({frame,side}:{frame:Frame;side:'CE'|'PE'}){
  const rows=frame.snapshots.filter(r=>r.k===side).sort((a,b)=>Math.abs(a.s-(frame.latest?.i||0))-Math.abs(b.s-(frame.latest?.i||0))).slice(0,11).sort((a,b)=>a.s-b.s);
  return <section className="table-card"><div className="section-bar"><h2>{side} OI snapshot</h2><span className="muted">11 strikes near index · latest available receipts</span></div><Table><TableHeader><TableRow><TableHead>Strike</TableHead><TableHead>Premium</TableHead><TableHead>Total OI</TableHead><TableHead>Cum +OI</TableHead><TableHead>Cum −OI</TableHead><TableHead>ΔOI</TableHead><TableHead>ΔVolume</TableHead><TableHead>Receipt IST</TableHead></TableRow></TableHeader><TableBody>{rows.map(r=><TableRow key={r.symbol}><TableCell className="numeric">{fmt(r.s,0)} {side}</TableCell><TableCell>{fmt(r.p)}</TableCell><TableCell>{compact(r.oi)}</TableCell><TableCell className="oi-added" title={r.cumPartial?"Partial: missing receipt deltas":undefined}>+{compact(r.cumPositive)}</TableCell><TableCell className="oi-removed" title={r.cumPartial?"Partial: missing receipt deltas":undefined}>{r.cumNegative<0?"−":""}{compact(Math.abs(r.cumNegative))}</TableCell><TableCell style={{color:colorFor(r.d)}}>{signed(r.d,0)}</TableCell><TableCell>{compact(r.dv)}</TableCell><TableCell>{clock(r.x,true)}</TableCell></TableRow>)}</TableBody></Table>{!rows.length&&<p className="empty-copy">No option receipts available yet.</p>}</section>;
}

function InventoryWorkspace({frame,scope,onScope}:{frame:Frame;scope:string;onScope:(v:string)=>void}){
  const rows=scope==='ID'?frame.controls:frame.prior.filter(r=>r.scope===scope&&r.status==='AVAILABLE');
  return <section className="table-card"><div className="section-bar"><div><h2>Inventory & reference levels</h2><p>Intraday controls develop at the cursor. Prior scopes are frozen.</p></div><Choice value={scope} onChange={onScope} label="Inventory scope" choices={['ID','1D','2D','3D'].map(v=>({value:v,label:v==='ID'?'Intraday':`${v} prior`}))}/></div><Table><TableHeader><TableRow><TableHead>Family</TableHead><TableHead>VPOC</TableHead><TableHead>VAL</TableHead><TableHead>VAH</TableHead><TableHead>Weight</TableHead><TableHead>Published / source</TableHead></TableRow></TableHeader><TableBody>{rows.map((r,i)=><TableRow key={i}><TableCell><span className="table-family"><i style={{background:LEVELS[r.family]?.color}}/>{LEVELS[r.family]?.label||words(r.family)}</span></TableCell><TableCell>{fmt(r.control_value,0)}</TableCell><TableCell>{fmt(r.value_area_low,0)}</TableCell><TableCell>{fmt(r.value_area_high,0)}</TableCell><TableCell>{compact(r.total_weight)}</TableCell><TableCell>{r.x?clock(r.x,true):r.source_sessions?.join(', ')||'—'}</TableCell></TableRow>)}</TableBody></Table>{!rows.length&&<p className="empty-copy">No available levels for this scope at the current time.</p>}</section>;
}

function EventWorkspace({frame,onSeek,canSeek}:{frame:Frame;onSeek:(n:number)=>void;canSeek:boolean}){
  const [filter,setFilter]=useState('all');
  const shifts=frame.controlHistory.map(r=>({...r,x:Number(r.x),eventType:'VPOC',label:`${LEVELS[r.family]?.label||r.family} → ${fmt(r.control_value,0)}`}));
  const events=[...frame.transitions.map(r=>({...r,x:Number(r.x),eventType:'Divergence',label:`${r.colour} · ${words(r.state)}`})),...shifts].sort((a,b)=>b.x-a.x).filter(r=>filter==='all'||r.eventType===filter).slice(0,100);
  return <section className="table-card"><div className="section-bar"><div><h2>Published events</h2><p>Only events available at {clock(frame.now,true)} IST · latest 100</p></div><Choice label="Event type" value={filter} onChange={setFilter} choices={[{value:'all',label:'All events'},{value:'VPOC',label:'VPOC shifts'},{value:'Divergence',label:'Divergence'}]}/></div><div className="event-list">{events.map((e,i)=><button key={i} className="event-row" disabled={!canSeek} title={canSeek?"Seek to event":"Switch to Replay to seek"} onClick={()=>onSeek(e.x)}><span className="event-time">{clock(e.x,true)}</span><span className={`event-type ${e.eventType==='VPOC'?'vpoc':''}`}>{e.eventType}</span><span>{e.label}</span><ArrowUpRight size={15}/></button>)}{!events.length&&<p className="empty-copy">No events published at this time.</p>}</div></section>;
}

export default function MarketWorkspace({profileId,onProfileChange,workspaceConfig}:{profileId:string;onProfileChange:(id:string)=>void;workspaceConfig:Row}){
  const profile=getProfile(profileId);
  const imported=useRef(false);
  const [mode,setMode]=useState(()=>workspaceConfig.live?(new URLSearchParams(location.search).get('mode')==='replay'?'replay':workspaceConfig.defaultMode):'replay');
  const [liveStatus,setLiveStatus]=useState<Row|null>(null);
  const [catalog,setCatalog]=useState<Row[]>([]),[session,setSession]=useState(''),[meta,setMeta]=useState<Meta|null>(null),[frame,setFrame]=useState<Frame|null>(null);
  const [cursor,setCursor]=useState(0),[playing,setPlaying]=useState(false),[speed,setSpeed]=useState('1'),[step,setStep]=useState('5'),[tab,setTab]=useState('market');
  const [scope,setScope]=useState('ID'),[windowMinutes,setWindowMinutes]=useState('0'),[flags,setFlags]=useState<Flags>(defaultFlags),[settings,setSettings]=useState(false);
  const [loading,setLoading]=useState(true),[error,setError]=useState(''),[seekText,setSeekText]=useState(''),[seekError,setSeekError]=useState('');
  const worker=useRef<Worker|null>(null),request=useRef(0),summary=useRef<{open:()=>void}>(null);
  useEffect(()=>{
    const w=new Worker('/data-worker.js',{type:'module'});worker.current=w;
    w.onmessage=e=>{
      const r=e.data;if(r.id!==request.current)return;
      if(r.kind==='loaded'){setMeta(r.meta);setCursor(Math.min(r.meta.end,Date.parse(`${r.meta.session}T12:15:08+05:30`)));}
      else if(r.kind==='frame'){setFrame(r.frame);setLoading(false);setError('');}
      else if(r.kind==='live-frame'){setFrame(r.frame);setMeta(r.meta);setCursor(r.frame.now);setLiveStatus(r.health);setLoading(false);setError('');}
      else if(r.kind==='live-status'){setLiveStatus(r.health);setLoading(false);}
      else if(r.kind==='live-connected'){setLiveStatus(r.health);setError('');setLoading(false);}
      else if(r.kind==='live-reset'){setFrame(null);setMeta(null);setLiveStatus(r.health);setLoading(false);}
      else if(r.kind==='live-error'){setError(r.error);setLoading(false);}
      else if(r.kind==='seek'){setCursor(r.now);}
      else if(r.kind==='error'){setError(r.error);setLoading(false);setPlaying(false);}
    };
    w.onerror=()=>{setError('The session reader could not start. Reload the page to retry.');setLoading(false);};
    try{const saved=localStorage.getItem(`market-v3-display-${profileId}`);if(saved){const {vpocVisibilityVersion,...preferences}=JSON.parse(saved);setFlags({...defaultFlags,...preferences,levels:vpocVisibilityVersion===1?preferences.levels!==false:true});}}catch{}
    return()=>{w.terminate();};
  },[]);
  useEffect(()=>{
    if(!worker.current)return;
    const abort=new AbortController();
    imported.current=false;setPlaying(false);setFrame(null);setMeta(null);setError('');setLoading(true);setSession('');setCatalog([]);setLiveStatus(null);
    const url=new URL(location.href);url.searchParams.set('mode',mode);history.replaceState(null,'',url);
    if(mode==='live')worker.current.postMessage({id:++request.current,action:'live',profileId,interval:workspaceConfig.pollMilliseconds});
    else{
      worker.current.postMessage({id:++request.current,action:'stop'});
      const catalogUrl=workspaceConfig.live?`/api/catalog?profile=${encodeURIComponent(profileId)}`:profile.catalog;
      fetch(catalogUrl,{signal:abort.signal}).then(r=>{if(r.status===404)return {sessions:[]};if(!r.ok)throw new Error('Session catalog is unavailable.');return r.json();}).then(c=>{
        if(abort.signal.aborted||imported.current)return;
        setCatalog(c.sessions||[]);setSession(c.sessions?.[0]?.id||c.sessions?.[0]?.session||'');if(!c.sessions?.length)setLoading(false);
      }).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setLoading(false);}});
    }
    return()=>{abort.abort();worker.current?.postMessage({id:++request.current,action:'stop'});};
  },[mode]);
  useEffect(()=>{if(mode==='live'||!session||!worker.current)return;const entry=catalog.find(r=>(r.id||r.session)===session);if(!entry)return;setPlaying(false);setLoading(true);setError('');setFrame(null);setMeta(null);worker.current.postMessage({id:++request.current,action:'load',url:entry.payload,profileId});},[session,catalog,mode]);
  useEffect(()=>{if(mode==='live'||!meta||!worker.current)return;worker.current.postMessage({id:++request.current,action:'frame',now:cursor});},[cursor,meta,session,mode]);
  useEffect(()=>{if(!playing||!meta)return;const timer=setInterval(()=>setCursor(prev=>{const next=Math.min(meta.end,prev+60000);if(next>=meta.end)setPlaying(false);return next;}),1000/Number(speed));return()=>clearInterval(timer);},[playing,meta,speed]);
  useEffect(()=>{try{localStorage.setItem(`market-v3-display-${profileId}`,JSON.stringify({...flags,vpocVisibilityVersion:1}));}catch{}},[flags]);
  useEffect(()=>{setSeekText(clock(cursor));},[cursor]);
  const seek=useCallback((value:number)=>{if(meta&&mode==='replay'){setPlaying(false);setCursor(Math.max(meta.start,Math.min(meta.end,value)));}},[meta,mode]);
  const advance=(direction:number)=>seek(cursor+direction*Number(step)*60000);
  const jumpEvent=(direction:number)=>{
    if(!worker.current||!meta)return;setPlaying(false);
    worker.current.postMessage({id:++request.current,action:'seek-event',now:cursor,direction});
  };
  const changeSession=(v:string)=>{imported.current=false;setSession(v);setSeekError('');};
  const openFile=(file:File|undefined)=>{if(!file||!worker.current)return;imported.current=true;setSession('');setMeta(null);setFrame(null);setPlaying(false);setLoading(true);setError('');setSeekError('');worker.current.postMessage({id:++request.current,action:'file',file,profileId});};
  const submitTime=()=>{const value=Date.parse(`${meta?.session||session}T${seekText.length===5?seekText+':00':seekText}+05:30`);if(!meta||!Number.isFinite(value)||value<meta.start||value>meta.end){setSeekError('Enter a time within this recorded session.');return;}setSeekError('');seek(value);};
  const latest=frame?.latest,first=frame?.range.open,change=latest&&first!=null?latest.i-first:null;
  return <div className="market-app">
    <header className="app-header"><a className="brand" href="/" aria-label={`${profile.label} workspace`}><span className="brand-icon"><Activity size={21}/></span><span>{profile.instrument} <b>WORKSPACE</b></span><span className="version-badge">V3</span></a><div className="header-status"><span className="recorded-label"><span/> {mode==='live'?'Live feed':'Recorded session'}</span><span className="header-baseline">v{profile.version} · {workspaceConfig.live?'shared core':'recorded output'}</span><button className="icon-button" aria-label="Display settings" onClick={()=>setSettings(true)}><Settings2 size={18}/></button></div></header>
    <main className="workspace-shell">
      <div className="workspace-toolbar"><div className="toolbar-left"><Choice label="Instrument and engine version" value={profileId} onChange={onProfileChange} choices={workspaceConfig.profiles.map((id:string)=>({value:id,label:PROFILES[id].title}))}/><span className="mode-badge">{mode==='live'?<Radio size={13}/>:<RotateCcw size={13}/>} {mode==='live'?'Live':'Replay'}</span>{workspaceConfig.live&&<Choice label="Live or replay mode" value={mode} onChange={setMode} choices={[{value:'live',label:'Live'},{value:'replay',label:'Replay'}]}/>}<CalendarDays size={15} className="calendar-icon"/>{mode==='replay'&&!imported.current&&catalog.length>0&&<Choice label="Recorded session" value={session} onChange={changeSession} choices={catalog.map(r=>({value:r.id||r.session,label:dateLabel(r.session)+(r.source?` · ${r.source}`:'')}))}/>}</div><div className="toolbar-right">{mode==='replay'&&<label className="secondary-button file-picker">Open session<input type="file" accept=".json,.gz" aria-label={`Open ${profile.title} session file`} onChange={e=>{openFile(e.target.files?.[0]);e.target.value='';}}/></label>}<button className="secondary-button" onClick={()=>summary.current?.open()} disabled={!frame}><MessageSquareText size={15}/> Market summary</button><button className="secondary-button settings-button" onClick={()=>setSettings(true)}><Settings2 size={15}/> Customize</button></div></div>
      {meta&&imported.current&&<p className="session-source">{dateLabel(meta.session)} · local session file</p>}
      {error&&<div role="alert" className="error-banner">{error}<button className="text-button" onClick={()=>location.reload()}>Retry</button></div>}
      {frame?.provenance.history_note&&<p className="session-source">{frame.provenance.history_note}</p>}
      {!loading&&!frame&&!error&&<section className="welcome-card"><h1>{profile.title}</h1><p>{mode==='live'?(liveStatus?.error||'Waiting for synchronized live price receipts from the shared core.'):'Open a prepared session JSON or JSON.gz file to start replay.'}</p><p className="muted">{mode==='live'?'The core runs continuously, including when this page is closed.':'Replay reads saved publications. Playback does not change the live engine.'}</p></section>}
      <section className="ticker-strip" aria-label={mode==='live'?'Latest market values':'Market values at the replay cursor'}><div className="ticker-primary"><span className="ticker-label">{profile.label.toUpperCase()} INDEX</span><div><strong>{fmt(latest?.i)}</strong><span style={{color:colorFor(change)}}>{change!=null&&<>{change>=0?<ArrowUpRight size={17}/>:<ArrowDownRight size={17}/>} {signed(change)} <small>({signed(first?change/first*100:0)}%)</small></>}</span></div><span className="ticker-note">Change from first session receipt</span>{frame?.provenance.price_note&&<span className="ticker-note">{frame.provenance.price_note}</span>}<dl className="ticker-session-range"><div><dt>High so far</dt><dd>{fmt(frame?.range.high)}</dd></div><div><dt>Low so far</dt><dd>{fmt(frame?.range.low)}</dd></div></dl></div><div className="ticker-item"><span>Futures basis</span><strong style={{color:COLORS.basis}}>{signed(latest?.b)} <small>pts</small></strong><span>Futures {fmt(latest?.f)}</span><dl className="ticker-session-range ticker-compact-range" aria-label="Futures basis high and low so far in points"><div><dt>High</dt><dd>{signed(frame?.basisRange.high)}</dd></div><div><dt>Low</dt><dd>{signed(frame?.basisRange.low)}</dd></div></dl></div><div className="ticker-item"><span>India VIX</span><strong style={{color:COLORS.vix}}>{fmt(frame?.cash.at(-1)?.vix_close)}</strong><span>Receipt {clock(frame?.cash.at(-1)?.x)}</span><dl className="ticker-session-range ticker-compact-range" aria-label="Recorded VIX high and low at the replay time"><div><dt>High</dt><dd>{fmt(frame?.vixRange.high)}</dd></div><div><dt>Low</dt><dd>{fmt(frame?.vixRange.low)}</dd></div></dl><span className="vix-range-source">{frame?.vixRange.from?`1m closes from ${clock(frame.vixRange.from)}`:"Awaiting VIX readings"}</span></div><div className="ticker-item"><span>Futures OI</span><strong style={{color:COLORS.oi}}>{compact(frame?.oi.at(-1)?.oi)}</strong><span>Δ {signed(frame?.oi.at(-1)?.d,0)}</span></div><div className="ticker-item ticker-call"><span>Current call</span><strong style={{color:frame?.call?.direction==='UP'?COLORS.positive:frame?.call?.direction==='DOWN'?COLORS.negative:COLORS.muted}}>{frame?.call?.direction||'WAIT'} <small>{signed(frame?.call?.score)}</small></strong><span>{words(frame?.call?.confidence)} confidence</span></div></section>
      <Tabs value={tab} onValueChange={setTab} className="workspace-tabs"><div className="tab-toolbar"><TabsList variant="line" className="main-tab-list"><TabsTrigger value="market"><Activity size={15}/> Market</TabsTrigger><TabsTrigger value="options"><BarChart3 size={15}/> Options</TabsTrigger><TabsTrigger value="inventory"><Layers3 size={15}/> Inventory</TabsTrigger><TabsTrigger value="events"><Clock3 size={15}/> Events</TabsTrigger></TabsList><div className="range-controls"><Choice value={scope} onChange={setScope} label="Chart control scope" choices={[{value:'ID',label:'Intraday VPOC'},{value:'1D',label:'1D prior VPOC'},{value:'2D',label:'2D prior VPOC'},{value:'3D',label:'3D prior VPOC'}]}/><div className="range-buttons" aria-label="Visible time range">{[{v:'30',l:'30m'},{v:'60',l:'1h'},{v:'0',l:'Session'}].map(r=><button key={r.v} aria-pressed={windowMinutes===r.v} className={windowMinutes===r.v?'active':''} onClick={()=>setWindowMinutes(r.v)}>{r.l}</button>)}</div></div></div>
        {loading&&!frame?<div className="workspace-loading" role="status"><Loader2 className="spin" size={25}/><h2>{mode==='live'?'Connecting to the shared core':'Loading recorded market data'}</h2><p>Preparing price, OI and saved calls.</p></div>:frame?<div className="workspace-grid"><div className="main-column"><TabsContent value="market"><MarketCharts frame={frame} flags={flags} scope={scope} windowMinutes={Number(windowMinutes)} onLevelsChange={levels=>setFlags(previous=>({...previous,levels}))}/></TabsContent><TabsContent value="options"><OptionWorkspace frame={frame} windowMinutes={Number(windowMinutes)}/></TabsContent><TabsContent value="inventory"><InventoryWorkspace frame={frame} scope={scope} onScope={setScope}/></TabsContent><TabsContent value="events"><EventWorkspace frame={frame} onSeek={seek} canSeek={mode==='replay'}/></TabsContent></div><aside className="insights-column">{profile.version==='2.0.0'&&<V2Context frame={frame}/>}<CallCard frame={frame} onSummary={()=>summary.current?.open()}/><SummaryPanel ref={summary} frame={frame}/><LevelList frame={frame} scope={scope}/><OptionOIProfile frame={frame}/></aside></div>:null}
      </Tabs>
      <footer className="workspace-footnote"><span>{mode==='live'?'Live market data':'Recorded market data'} · {profile.callLabel}</span><span>IST (UTC +05:30) · Experimental analysis</span></footer>
    </main>
    {mode==='replay'?<section className="replay-dock" aria-label="Replay controls"><div className="playback-buttons"><button className="icon-button" title="Previous published event" aria-label="Previous published event" disabled={!meta} onClick={()=>jumpEvent(-1)}><SkipBack size={16}/></button><button className="icon-button" title={`Back ${step} minutes`} aria-label={`Back ${step} minutes`} disabled={!meta} onClick={()=>advance(-1)}><StepBack size={18}/></button><button className="play-button" disabled={!meta||loading} aria-label={playing?'Pause replay':'Play replay'} onClick={()=>{if(meta&&cursor>=meta.end)setCursor(meta.start);setPlaying(!playing);}}>{playing?<Pause size={19}/>:<Play size={19}/>}</button><button className="icon-button" title={`Forward ${step} minutes`} aria-label={`Forward ${step} minutes`} disabled={!meta} onClick={()=>advance(1)}><StepForward size={18}/></button><button className="icon-button" title="Next published event" aria-label="Next published event" disabled={!meta} onClick={()=>jumpEvent(1)}><SkipForward size={16}/></button></div><div className="replay-time"><strong>{clock(frame?.now||cursor,true)}</strong><span>IST · {playing?'Playing':meta&&cursor>=meta.end?'Session complete':'Paused'}</span></div><div className="timeline"><Slider min={meta?.start||0} max={meta?.end||1} step={1000} value={[cursor||0]} disabled={!meta} onValueChange={v=>seek(v[0])} aria-label="Replay time"/><div><span>{clock(meta?.start)}</span><span>VPOC shifts continue playback</span><span>{clock(meta?.end)}</span></div></div><div className="playback-selectors"><Choice label="Playback speed" value={speed} onChange={setSpeed} choices={['1','2','5'].map(v=>({value:v,label:`${v} min/s`}))}/><Choice label="Step size" value={step} onChange={setStep} choices={['1','5','10'].map(v=>({value:v,label:`${v}m step`}))}/><form className="jump-form" onSubmit={e=>{e.preventDefault();submitTime();}}><input aria-label="Jump to IST time" type="text" inputMode="numeric" value={seekText} onChange={e=>setSeekText(e.target.value)} placeholder="HH:MM"/><button type="submit" title="Jump to time" aria-label="Jump to time"><ArrowUpRight size={16}/></button></form></div>{seekError&&<p role="alert" className="seek-error">{seekError}</p>}</section>:<section className="replay-dock live-dock" aria-label="Live feed status"><Radio size={20}/><div className="replay-time"><strong>{clock(frame?.now,true)}</strong><span>View as of · IST</span></div><div className="live-feed-state"><strong>{error?'Disconnected · retrying':liveStatus?.status==='ready'?(liveStatus.market_open?'Live · connected':'Connected · outside market hours'):words(liveStatus?.status||'connecting')}</strong><span>{liveStatus?.error||liveStatus?.v2_context_error||'The core continues processing when this GUI is closed.'}</span></div><button className="secondary-button" onClick={()=>setMode('replay')}><RotateCcw size={15}/> Open replay</button></section>}
    <Sheet open={settings} onOpenChange={setSettings}><SheetContent className="display-sheet"><SheetHeader><SheetTitle>Display settings</SheetTitle><SheetDescription>Choose the panes and reference overlays in your workspace.</SheetDescription></SheetHeader><div className="settings-body"><h3>Market panes</h3>{([{key:'vix',label:'India VIX',note:'Actual value, dashed line'},{key:'basis',label:'Futures basis',note:'Futures minus index'},{key:'oi',label:'Futures OI',note:'OI line and signed change bars'},{key:'flows',label:'CE / PE OI flows',note:'Four fixed strikes per side'},{key:'cash',label:'Weighted cash',note:'Optional five-minute rolling view'}] as {key:keyof Flags;label:string;note:string}[]).map(r=><label key={r.key} className="setting-row"><span><strong>{r.label}</strong><small>{r.note}</small></span><Checkbox checked={flags[r.key]} onCheckedChange={v=>setFlags(f=>({...f,[r.key]:v===true}))}/></label>)}<h3>Chart overlays</h3><label className="setting-row"><span><strong>VPOC control lines</strong><small>Intraday or selected prior scope</small></span><Checkbox checked={flags.levels} onCheckedChange={v=>setFlags(f=>({...f,levels:v===true}))}/></label><label className="setting-row"><span><strong>Confirmed divergence zones</strong><small>Shown only after publication</small></span><Checkbox checked={flags.zones} onCheckedChange={v=>setFlags(f=>({...f,zones:v===true}))}/></label><button className="secondary-button full-width" onClick={()=>setFlags(defaultFlags)}><RotateCcw size={15}/> Reset display</button></div></SheetContent></Sheet>
  </div>;
}
