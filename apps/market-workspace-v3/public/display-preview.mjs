// Display-only projection. Never passed to normalizePayload, frameAt or a detector.
export const PREVIEW_SCHEMA='READ_ONLY_LIVE_DISPLAY_V1';
const VIX='NSE:INDIAVIX-INDEX';
const finite=Number.isFinite;

/** @param {any} raw @param {string} instrument @param {string|null} [session] */
export function validatePreview(raw,instrument,session=null) {
  if(raw?.schema!==PREVIEW_SCHEMA||raw.instrument!==instrument||(session&&raw.session!==session)
    ||raw.display_only!==true||raw.owns_engine!==false||!finite(raw.server_ms)) return null;
  const expected=instrument==='NIFTY'?'NSE:NIFTY50-INDEX':'NSE:NIFTYBANK-INDEX';
  if(raw.index_symbol!==expected||!Array.isArray(raw.prices)||!Array.isArray(raw.vix)||!Array.isArray(raw.volume_bars))return null;
  const sameDay=ms=>finite(ms)&&new Date(ms+19800000).toISOString().slice(0,10)===raw.session;
  const valid=row=>row&&sameDay(row.received_ms)&&sameDay(row.source_ms)&&finite(row.price)&&row.price>0
    &&row.received_ms<=raw.server_ms+500&&row.source_ms<=row.received_ms+500;
  const latest=Object.fromEntries(Object.entries(raw.latest||{}).filter(([symbol,row])=>row.symbol===symbol&&valid(row)));
  return {...raw,latest,prices:raw.prices.filter(r=>r.symbol===expected&&valid(r)),
    vix:raw.vix.filter(r=>r.symbol===VIX&&valid(r)),volume_bars:raw.volume_bars.filter(r=>sameDay(r.minute_ms)
      &&finite(r.volume)&&r.volume>=0&&finite(r.observations))};
}

export function liveReading(preview,symbol) {
  const row=preview?.latest?.[symbol];
  if(preview?.status!=='LIVE'||!row||preview.server_ms-row.received_ms>5000
    ||preview.server_ms-row.source_ms>15000)return null;
  return row;
}

export function incomingIndex(preview,frame) {
  const row=liveReading(preview,preview?.index_symbol);
  return row&&(!frame||row.received_ms>=(frame.latest?.x??frame.now))?row:null;
}

function displayPoints(rows){
  const result=[];
  for(const row of rows){
    if(result.length&&row.received_ms-result.at(-1)[0]>15000)result.push([result.at(-1)[0]+1,null]);
    result.push([row.received_ms,row.price]);
  }
  return result;
}

export function previewPriceOption(option,frame,preview) {
  const latest=incomingIndex(preview,frame);
  if(!latest||preview.session!==frame.session)return option;
  const last=frame.price.at(-1), after=last?.x??frame.now;
  const incoming=preview.prices.filter(r=>r.received_ms>after);
  if(!incoming.length)return option;
  const close=Date.parse(`${frame.session}T15:30:00+05:30`);
  const max=Math.min(close,Math.max(frame.now,latest.received_ms));
  const axes=Array.isArray(option.xAxis)?option.xAxis:[option.xAxis];
  const xAxis=axes.map(axis=>({...axis,max:Math.max(Number(axis.max)||max,max)}));
  const data=displayPoints(incoming);
  if(last&&incoming[0].received_ms-last.x<=15000)data.unshift([last.x,last.i]);
  return {...option,xAxis:Array.isArray(option.xAxis)?xAxis:xAxis[0],series:[...(option.series||[]),{
    id:'incoming-index-preview',name:'Incoming index · provisional',type:'line',showSymbol:false,
    connectNulls:false,sampling:'none',lineStyle:{color:'#8ae1ff',width:2,type:'dotted'},
    itemStyle:{color:'#8ae1ff'},data,z:6,
  }]};
}

export function previewVixOption(option,frame,preview) {
  const latest=liveReading(preview,VIX);
  if(!latest||preview.session!==frame.session)return option;
  const row=frame.cash.at(-1);
  // The confirmed point is labelled by source-minute start. Its close is one minute later.
  const cutoff=row?(frame.cashVixQuality.sourceTime?Date.parse(row.minute_ist)+60000:row.x):frame.now;
  const incoming=preview.vix.filter(r=>r.received_ms>=cutoff);
  if(!incoming.length)return option;
  return {...option,xAxis:{...option.xAxis,max:Math.max(Number(option.xAxis.max)||frame.now,latest.received_ms)},
    tooltip:{...option.tooltip,formatter:undefined},series:[...(option.series||[]),{
      id:'incoming-vix-preview',name:'Incoming VIX · provisional',type:'line',showSymbol:false,
      connectNulls:false,lineStyle:{color:'#ffd0ae',width:2,type:'dotted'},
      data:displayPoints(incoming),itemStyle:{color:'#ffd0ae'},
    }]};
}

export function observedVolume(preview,selection,side='FUT') {
  if(!preview)return {symbols:[],bars:[],coverage:0,expected:0};
  const symbols=side==='FUT'?[preview.futures_symbol].filter(Boolean)
    :selection?.available?(selection[side]||[]).map(r=>r.symbol):[];
  const buckets=new Map();
  for(const r of preview.volume_bars)if(symbols.includes(r.symbol)){
    const bucket=buckets.get(r.minute_ms)||{x:r.minute_ms,volume:0,partial:false,symbols:new Set()};
    if(r.observations>0){bucket.volume+=r.volume;bucket.symbols.add(r.symbol);}
    bucket.partial||=r.partial;
    buckets.set(r.minute_ms,bucket);
  }
  return {symbols,coverage:symbols.filter(s=>liveReading(preview,s)?.volume!=null).length,expected:symbols.length,
    bars:[...buckets.values()].sort((a,b)=>a.x-b.x).map(r=>({x:r.x,volume:r.symbols.size?r.volume:null,
      partial:r.partial||r.symbols.size<symbols.length,forming:r.x===Math.floor(preview.server_ms/60000)*60000}))};
}
