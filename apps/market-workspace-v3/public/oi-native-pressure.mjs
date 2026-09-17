// Read-only presentation of the EXISTING V3 NEAR_OTM_OPTION_OI_FLOW_1M_V1
// report rows. No core, published calls, confirmations or research reference
// are modified. This basket moves with spot; it is NOT the fixed-4 study.
const minuteMs = 60000;
const finite = n => typeof n === 'number' && Number.isFinite(n);
const valid = row => row && finite(row.positive) && row.positive >= 0 &&
  finite(row.negative) && row.negative >= 0 &&
  Number.isInteger(row.validContracts) &&
  Number.isInteger(row.expectedContracts) && row.expectedContracts > 0 &&
  row.validContracts === row.expectedContracts;

function sideAt(map, minute, windowMinutes) {
  let positive = 0, negative = 0, latestAt = -Infinity;
  for (let back = windowMinutes - 1; back >= 0; back--) {
    const row = map.get(minute - back * minuteMs);
    // An incomplete receipt or missing minute is a gap, NEVER zero OI.
    if (!valid(row)) return null;
    positive += row.positive;
    negative += row.negative;
    latestAt = Math.max(latestAt, row.x);
  }
  return {plus:positive,minus:negative,lastAt:latestAt};
}

export function rawNativeBalance(ce, pe) {
  if (!ce || !pe) return {score:null,state:'INCOMPLETE RECEIPTS'};
  const ceActivity = ce.plus + ce.minus, peActivity = pe.plus + pe.minus;
  if (!ceActivity || !peActivity) return {score:null,state:'ONE-SIDED / NO FLOW'};
  const ceBull = (ce.minus - ce.plus) / ceActivity;
  const peBull = (pe.plus - pe.minus) / peActivity;
  if (ceBull > 0 && peBull > 0)
    return {score:100 * Math.min(ceBull,peBull),state:'BULL FLOW'};
  if (ceBull < 0 && peBull < 0)
    return {score:-100 * Math.min(-ceBull,-peBull),state:'BEAR FLOW'};
  return {score:0,state:'MIXED LEGS'};
}

export function nativePressureSeries(rows, now, windowMinutes=1) {
  if (windowMinutes !== 1 && windowMinutes !== 5) throw new RangeError('Only gross 1m/5m windows are supported');
  const bySide = {CE:new Map(),PE:new Map()};
  for (const row of rows || []) {
    if (!row || !['CE','PE'].includes(row.side) || !finite(row.x) || row.x > now) continue;
    const minute = finite(row.minute) ? row.minute : Math.floor(row.x / minuteMs) * minuteMs;
    if (!finite(minute) || minute > now) continue;
    const prev = bySide[row.side].get(minute);
    if (!prev || row.x > prev.x) bySide[row.side].set(minute,row);
  }
  const minutes=[...new Set([...bySide.CE.keys(),...bySide.PE.keys()])].sort((a,b)=>a-b);
  return minutes.map(minute=>{
    const ce = sideAt(bySide.CE,minute,windowMinutes);
    const pe = sideAt(bySide.PE,minute,windowMinutes);
    const endX=Math.max(bySide.CE.get(minute)?.x??minute,bySide.PE.get(minute)?.x??minute);
    const balance=rawNativeBalance(ce,pe);
    return {x:endX,minute,ce,pe,...balance,window:windowMinutes};
  }).filter(row=>row.x<=now);
}
