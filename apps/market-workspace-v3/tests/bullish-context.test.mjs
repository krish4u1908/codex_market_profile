import test from 'node:test';
import assert from 'node:assert/strict';
import {indexReports, priceContext, selectEpisodes, nearPutCoverage} from '../research/bullish-context.mjs';

const start = Date.parse('2026-09-10T09:15:55+05:30');
const series = prices => prices.map((spot, i) => ({x: start + i * 60000, spot}));

test('trend is measured before the event window; a pullback can remain bullish', () => {
  const rows = series([...Array.from({length: 31}, (_, i) => 100 + i), 129, 128, 127, 126, 125]);
  const c = priceContext(indexReports(rows), rows.at(-1).x);
  assert.equal(c.label, 'BULLISH'); assert.equal(c.efficiency, 1);
  assert.equal(c.average, 115.5); assert.equal(c.netTrendPoints, 30);
  assert.equal(c.priceChange5m, -5); assert.equal(c.response, 'PULLBACK_WITH_VIX');
  rows[35].spot = 115;
  assert.equal(priceContext(indexReports(rows), rows.at(-1).x).label, 'MIXED');
});

test('bearish is signed; flat or a last-five-minute rally alone is not bullish', () => {
  let rows = series(Array.from({length: 36}, (_, i) => 200 - i));
  assert.equal(priceContext(indexReports(rows), rows.at(-1).x).label, 'BEARISH');
  rows = series([...Array(31).fill(100), 101, 102, 103, 104, 105]);
  assert.equal(priceContext(indexReports(rows), rows.at(-1).x).label, 'MIXED');
  assert.equal(priceContext(indexReports(rows), rows.at(-1).x).efficiency, 0);
});

test('missing slots, bad prices and duplicate slots cannot silently become valid context', () => {
  const rows = series(Array.from({length: 36}, (_, i) => 100 + i));
  assert.equal(priceContext(indexReports(rows.slice(1)), rows.at(-1).x).status, 'UNKNOWN');
  const copy = structuredClone(rows); copy[10].spot = null;
  assert.equal(priceContext(indexReports(copy), rows.at(-1).x).status, 'UNKNOWN');
  assert.throws(() => indexReports([rows[0], {...rows[0], x: rows[0].x + 1}]));
  assert.equal(priceContext(indexReports(rows), rows.at(-1).x - 1).status, 'UNKNOWN');
});

test('adding future prices cannot change a past classification', () => {
  const rows = series(Array.from({length: 80}, (_, i) => i < 36 ? 100 + i : 1));
  assert.deepEqual(priceContext(indexReports(rows), rows[35].x), priceContext(indexReports(rows.slice(0, 36)), rows[35].x));
});

test('episodes use minute slots and reset each session', () => {
  const rows = [0, 1, 14, 15, 16, 30].map(i => ({x: start + i * 60000 - (i === 15 ? 10 : 0), session: '2026-09-10'}));
  rows.push({x: start + 86400000, session: '2026-09-11'});
  assert.deepEqual(selectEpisodes(rows).map(r => r.x), [rows[0].x, rows[3].x, rows[5].x, rows[6].x]);
});

test('a non-event control needs computable OI for all three puts', () => {
  const rows = series(Array(22).fill(23500)).map((r, i) => ({...r, expiry: '15-09-2026',
    contracts: [23450, 23400, 23350].map(strike => ({side: 'PE', strike, symbol: `P${strike}`, oi: 100000 + i * 100}))}));
  assert.equal(nearPutCoverage(indexReports(rows), rows.at(-1).x), 3);
  rows[5].contracts.pop();
  assert.equal(nearPutCoverage(indexReports(rows), rows.at(-1).x), 2);
});
