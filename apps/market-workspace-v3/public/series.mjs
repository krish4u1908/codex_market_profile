// Shared presentation helpers. No decision or engine rules are calculated here.
export const stamp = row => Number(row?.x ?? Date.parse(row?.published_at ?? row?.t ?? row?.timestamp));
export function unpack(block) {
  if (Array.isArray(block)) return block.map(row => ({ ...row, x: stamp(row) })).filter(row => Number.isFinite(row.x)).sort((a,b)=>a.x-b.x);
  return (block?.rows || []).map(row => {
    const out = Object.fromEntries(block.fields.map((field, i) => [field, row[i]]));
    return { ...out, x: stamp(out) };
  }).filter(row => Number.isFinite(row.x)).sort((a, b) => a.x - b.x);
}
export function atOrBefore(rows, now) {
  let lo = 0, hi = rows.length - 1, found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    if (rows[mid].x <= now) { found = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return found < 0 ? null : rows[found];
}
export function minuteClose(rows) {
  const buckets = new Map();
  for (const row of rows) buckets.set(Math.floor(row.x / 60000), row);
  return [...buckets.values()].sort((a, b) => a.x - b.x);
}
// Reference levels persist between publications. Tick series retain their gap breaks.
export function chartPoints(rows, field, holdLastValue = false) {
  const points = [];
  for (let i = 0; i < rows.length; i++) {
    if (!holdLastValue && i && rows[i].x - rows[i - 1].x > 180000) {
      points.push([rows[i - 1].x + 1, null]);
    }
    points.push([rows[i].x, rows[i][field] ?? null]);
  }
  return points;
}
// Sum option/futures gap-safe receipt deltas once, in the data worker. Gross
// additions/removals are separate from the latest outstanding (total) OI.
export function withCumulativeOI(rows, analysisStart) {
  const contracts = new Map();
  return rows.filter(row => row.x >= analysisStart).map(row => {
    const key = JSON.stringify([row.e, row.symbol, row.k, row.s]);
    const previous = contracts.get(key);
    const state = previous ? { ...previous } : { positive: 0, negative: 0, partial: false, from: row.x };
    if (previous) {
      if (Number.isFinite(row.d)) {
        state.positive += Math.max(0, row.d);
        state.negative += Math.min(0, row.d);
      } else state.partial = true;
    }
    contracts.set(key, state);
    return { ...row, cumPositive: state.positive, cumNegative: state.negative, cumPartial: state.partial, cumFrom: state.from };
  });
}

export function optionOIProfile(snapshots, spot, expiry, now, count = 7) {
  const byStrike = new Map();
  if (Number.isFinite(spot) && expiry) for (const row of snapshots) {
    if (row.e !== expiry || row.x > now || !Number.isFinite(row.s) || !['CE', 'PE'].includes(row.k)) continue;
    const entry = byStrike.get(row.s) || { strike: row.s, CE: null, PE: null };
    if (!entry[row.k] || row.x > entry[row.k].x) entry[row.k] = row;
    byStrike.set(row.s, entry);
  }
  const rows = [...byStrike.values()].sort((a, b) => Math.abs(a.strike - spot) - Math.abs(b.strike - spot) || a.strike - b.strike)
    .slice(0, count).sort((a, b) => b.strike - a.strike);
  const strongest = (side, eligible) => rows.filter(row => eligible(row.strike) && Number.isFinite(row[side]?.oi) && row[side].oi > 0)
    .sort((a, b) => b[side].oi - a[side].oi || Math.abs(a.strike - spot) - Math.abs(b.strike - spot))[0]?.strike ?? null;
  const receipts = rows.flatMap(row => [row.CE, row.PE]).filter(Boolean);
  const scale = Math.max(1, ...receipts.flatMap(row => [row.oi, row.cumPositive, Math.abs(row.cumNegative)]).filter(Number.isFinite));
  return {
    rows, scale, support: strongest('PE', strike => strike < spot), resistance: strongest('CE', strike => strike > spot),
    oldestReceipt: receipts.length ? Math.min(...receipts.map(row => row.x)) : null,
    newestReceipt: receipts.length ? Math.max(...receipts.map(row => row.x)) : null,
    partial: receipts.some(row => row.cumPartial), expiry: expiry || null,
  };
}
