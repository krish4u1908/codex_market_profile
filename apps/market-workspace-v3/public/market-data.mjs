import {volumeClimaxPoints} from './v2-volume.mjs';
import {atOrBefore,minuteClose,optionOIProfile} from './series.mjs';
import {latestBasisRibbon,sampleBasisRibbon} from './price-basis-ribbon.mjs';
export * from './series.mjs';
export {normalizePayload} from './payload-adapters.mjs';
export function frameAt(data, now) {
  now = Math.min(Math.max(now, data.start), data.end);
  const pricePrefix = data.price.filter(row => row.x <= now);
  const price = minuteClose(pricePrefix);
  const latest = pricePrefix.at(-1) || null;
  const call = atOrBefore(data.calls, now);
  const controls = new Map();
  for (const row of data.controls) if (row.x <= now) controls.set(row.family, row);
  const options = data.options.filter(row => row.x <= now);
  const snapshots = new Map();
  for (const row of options) snapshots.set(row.symbol, row);
  const selectedAt = Number.isFinite(Date.parse(data.selection.selected_at)) ? Date.parse(data.selection.selected_at) : data.analysisStart;
  const selection = now >= Math.max(data.analysisStart, selectedAt) ? data.selection : {available:false,CE:[],PE:[]};
  const symbols = new Set([...(selection.CE || []), ...(selection.PE || [])].map(c => c.symbol));
  const oi = data.oi.filter(row => row.x >= data.analysisStart && row.x <= now);
  const cash = data.cash.filter(row => row.x <= now);
  const vix = cash.filter(row => Number.isFinite(row.vix_close));
  const values = pricePrefix.map(row => row.i).filter(Number.isFinite);
  const basisValues = pricePrefix.map(row => row.b).filter(Number.isFinite);
  const basisRibbon = sampleBasisRibbon((data.basisRibbon||[]).filter(row=>row.x<=now));
  return {
    volumeHistory:data.contexts.filter(row=>row.x<=now),
    volumeClimaxes:data.profile.version==='2.0.0'?volumeClimaxPoints(data.contexts,data.price,now):[],
    optionClimaxes:data.profile.version==='2.0.0'?(data.optionClimaxes||[]).filter(row=>row.x<=now):[],
    profile:data.profile, capabilities:data.capabilities, context:atOrBefore(data.contexts,now), contextHistory:data.contextHistory.filter(row=>row.x<=now),
    session:data.session, now, start:data.start, end:data.end, analysisStart:data.analysisStart,
    price, latest, oi, cash, call, state:atOrBefore(data.states,now), selection,
    basisRibbon, basisRibbonLatest:latestBasisRibbon(basisRibbon,now),
    controls:[...controls.values()].filter(row => row.status === "AVAILABLE"),
    controlHistory:data.controls.filter(row => row.x <= now), prior:data.prior.filter(row=>!Number.isFinite(Date.parse(row.available_at))||Date.parse(row.available_at)<=now),
    options:options.filter(row => symbols.has(row.symbol)), snapshots:[...snapshots.values()],
    optionProfile:optionOIProfile([...snapshots.values()],latest?.i,selection.expiry,now),
    transitions:data.transitions.filter(row => row.x <= now),
    zones:data.zones.filter(row=>Date.parse(row.confirmed_at)<=now).map(row=>({...row,ended_at:row.ended_at&&Date.parse(row.ended_at)<=now?row.ended_at:null})),
    range:{high:values.length?values.reduce((a,b)=>Math.max(a,b),-Infinity):null,low:values.length?values.reduce((a,b)=>Math.min(a,b),Infinity):null,open:pricePrefix[0]?.i??null},
    vixRange:{high:vix.length?vix.reduce((high,row)=>Math.max(high,row.vix_close),-Infinity):null,low:vix.length?vix.reduce((low,row)=>Math.min(low,row.vix_close),Infinity):null,from:vix.length?(Date.parse(vix[0].minute_ist)||vix[0].x):null},
    basisRange:{high:basisValues.length?basisValues.reduce((a,b)=>Math.max(a,b),-Infinity):null,low:basisValues.length?basisValues.reduce((a,b)=>Math.min(a,b),Infinity):null},
    provenance:data.provenance,
  };
}
export function snapshotSummary(frame) {
  const fmt=(n,d=2)=>n==null||!Number.isFinite(Number(n))?"Unavailable":Number(n).toLocaleString("en-IN",{maximumFractionDigits:d,minimumFractionDigits:d});
  const call=frame.call;
  return {
    asOf:frame.now,publishedAt:call?.published_at||call?.t||null,
    title:call?`${call.direction}${call.state?" · "+String(call.state).replaceAll("_"," ").toLowerCase():""}`:"Awaiting a published call",
    facts:[`${frame.profile.label} ${fmt(frame.latest?.i)}; futures ${fmt(frame.latest?.f)}; basis ${fmt(frame.latest?.b)} points.`,`Futures OI ${fmt(frame.oi.at(-1)?.oi,0)}. India VIX ${fmt(frame.cash.at(-1)?.vix_close)}.`,...(call?.drivers||[])],
    invalidation:call?.invalidation||"No invalidation statement has been published.",
    quality:call?.quality?.status||"Not recorded",issues:call?.quality?.issues||{},
    components:call?.components||{},context:call?.context||{},decisionId:call?.decision_id||null,
  };
}

// Keep summary messages small so structured cloning never copies chart history.
export function summaryInput(frame) {
  return {profile:frame.profile, now:frame.now, latest:frame.latest,
    oi:frame.oi.slice(-1), cash:frame.cash.slice(-1), call:frame.call};
}
