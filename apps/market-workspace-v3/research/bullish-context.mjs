// Research-only causal price context. Does not alter or import GUI state.
const MINUTE = 60000;
const positive = x => Number.isFinite(x) && x > 0;
const median = values => {
  const a = [...values].sort((x, y) => x - y), n = a.length;
  return n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2;
};

export function indexReports(reports) {
  const index = new Map();
  let previous = -Infinity;
  for (const r of reports) {
    const slot = Math.floor(r.x / MINUTE);
    if (!Number.isFinite(r.x) || r.x <= previous || index.has(slot))
      throw Error('Require ordered reports with exactly one receipt per minute slot');
    previous = r.x;
    index.set(slot, r);
  }
  return index;
}

function consecutive(index, slot, count, field) {
  const rows = Array.from({length: count}, (_, i) => index.get(slot - count + 1 + i));
  if (rows.some(r => !r || !positive(r[field])) ||
      rows.slice(1).some((r, i) => r.x <= rows[i].x || r.x - rows[i].x > 90000)) return null;
  return rows;
}

export function priceContext(index, x, threshold = 0.3) {
  if (!(threshold > 0 && threshold <= 1)) throw Error('Efficiency threshold must be in (0, 1]');
  const slot = Math.floor(x / MINUTE), rows = consecutive(index, slot, 36, 'spot');
  if (!rows || rows.at(-1).x !== x) return {status: 'UNKNOWN', label: 'UNKNOWN', reason: 'Missing, invalid or noncausal price window'};
  // rows[0..30] spans the 30 increments BEFORE the five-minute event window.
  const trend = rows.slice(0, 31), before = trend.at(-1), now = rows.at(-1);
  const net = before.spot - trend[0].spot;
  const travel = trend.slice(1).reduce((sum, r, i) => sum + Math.abs(r.spot - trend[i].spot), 0);
  const efficiency = travel === 0 ? 0 : net / travel;
  const average = trend.slice(1).reduce((sum, r) => sum + r.spot, 0) / 30;
  const label = efficiency >= threshold && before.spot > average && now.spot > average ? 'BULLISH' :
    efficiency <= -threshold && before.spot < average && now.spot < average ? 'BEARISH' : 'MIXED';
  const priceChange5m = now.spot - before.spot;
  return {status: 'AVAILABLE', label, threshold, efficiency, average,
    trendStartAt: trend[0].x, trendEndAt: before.x, signalAt: now.x,
    trendStartPrice: trend[0].spot, beforePrice: before.spot, signalPrice: now.spot,
    netTrendPoints: net, travelledPoints: travel, priceChange5m,
    response: priceChange5m > 0 ? 'PRICE_UP_WITH_VIX' : priceChange5m < 0 ? 'PULLBACK_WITH_VIX' : 'FLAT_WITH_VIX'};
}

export function vixChange5m(index, x) {
  const rows = consecutive(index, Math.floor(x / MINUTE), 6, 'vix');
  if (!rows || rows.at(-1).x !== x) return null;
  return 100 * (rows.at(-1).vix - rows[0].vix) / rows[0].vix;
}

// Controls must represent a valid absence of a PE spike, rather than missing OI history.
export function nearPutCoverage(index, x) {
  const current = index.get(Math.floor(x / MINUTE));
  if (!current || !positive(current.spot) || current.x !== x) return 0;
  const first = (Math.ceil(current.spot / 50) - 1) * 50;
  const rows = Array.from({length: 22}, (_, i) => index.get(Math.floor(x / MINUTE) - 21 + i));
  if (rows.some(r => !r || r.expiry !== current.expiry) ||
      rows.slice(1).some((r, i) => r.x <= rows[i].x || r.x - rows[i].x > 90000)) return 0;
  return [first, first - 50, first - 100].filter(strike => {
    const selected = current.contracts.filter(c => c.side === 'PE' && c.strike === strike);
    if (selected.length !== 1) return false;
    const h = rows.map(r => r.contracts.filter(c => c.symbol === selected[0].symbol));
    if (h.some(a => a.length !== 1 || !positive(a[0].oi))) return false;
    const changes = h.slice(1, -1).map((a, i) => 100 * Math.abs(a[0].oi - h[i][0].oi) / h[i][0].oi);
    return median(changes) > 0;
  }).length;
}

export function selectEpisodes(rows, cooldownMinutes = 15) {
  const last = new Map(), selected = [];
  for (const r of [...rows].sort((a, b) => a.x - b.x)) {
    const slot = Math.floor(r.x / MINUTE);
    if (!last.has(r.session) || slot - last.get(r.session) >= cooldownMinutes) {
      selected.push(r); last.set(r.session, slot);
    }
  }
  return selected;
}

export function matchKey(row) {
  const hour = new Date(row.x + 19800000).getUTCHours();
  return `${row.session}|${hour}|${Math.sign(row.context.priceChange5m)}`;
}
