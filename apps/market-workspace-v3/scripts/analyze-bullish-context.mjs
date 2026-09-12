#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {oiEntryBubbles, nearOtmStrikes} from '../public/oi-entry-bubbles.mjs';
import {horizonOutcome, evaluateLongOption, summarizeTrades, isoIST, expiryISO} from '../research/bubble-outcomes.mjs';
import {indexReports, priceContext, vixChange5m, nearPutCoverage, selectEpisodes, matchKey} from '../research/bullish-context.mjs';

const {values} = parseArgs({options: {inputs: {type: 'string'}, output: {type: 'string'}}});
if (!values.inputs || !values.output) throw Error('Use --inputs PREPARED_DIRECTORY --output RESULTS_DIRECTORY');
const protocolPath = fileURLToPath(new URL('../research/bullish-context-protocol.json', import.meta.url));
const protocolBytes = fs.readFileSync(protocolPath), protocol = JSON.parse(protocolBytes);
const protocolSha256 = crypto.createHash('sha256').update(protocolBytes).digest('hex');
fs.mkdirSync(values.output, {recursive: true});
const write = (name, value) => fs.writeFileSync(path.join(values.output, name), JSON.stringify(value, null, 2) + '\n');
write('protocol.json', protocol);
const mean = a => a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const countBy = (a, key) => Object.fromEntries([...new Set(a.map(key))].sort().map(k => [k, a.filter(r => key(r) === k).length]));
const continuous = r => r.phase === 'CONTINUOUS';
const validHorizon = (r, h) => { const v = r.horizons.find(v => v.minutes === h); return v.status === 'AVAILABLE' && v.phase === 'CONTINUOUS' ? v : null; };
const bullish = (r, threshold = .3) => r.context.status === 'AVAILABLE' && r.context.efficiency >= threshold && r.context.beforePrice > r.context.average && r.spot > r.context.average;
const green = r => r.greenBubble;
const usableControl = r => !r.greenBubble && r.putCoverage === 3 && r.vixChangePct !== null;
const days = [], observations = [];
let contextPrefixChecks = 0;

for (const filename of fs.readdirSync(values.inputs).filter(n => n.endsWith('-research-inputs.json')).sort()) {
  const inputBytes = fs.readFileSync(path.join(values.inputs, filename)), input = JSON.parse(inputBytes);
  assert.equal(input.schema, 'BUBBLE_RESEARCH_INPUTS_V1'); assert.equal(input.instrument, 'NIFTY');
  const feed = input.option_report_inputs, reports = feed.reports, index = indexReports(reports);
  const detected = oiEntryBubbles({session: input.session, profile: {instrument: 'NIFTY', version: '2.0.0'}}, feed);
  assert.equal(detected.status, 'AVAILABLE');
  const greenByTime = new Map(detected.events.filter(e => e.category === 'PE_UP').map(e => [e.x, e]));
  const bars = new Map();
  for (const b of input.optionBars) { const key = `${b.expiry}|${b.symbol}`; if (!bars.has(key)) bars.set(key, []); bars.get(key).push(b); }
  const dayRows = [];
  for (const r of reports) {
    const event = greenByTime.get(r.x), context = priceContext(index, r.x);
    // Recheck against a feed truncated at the current receipt, not just a full-day map.
    assert.deepEqual(context, priceContext(indexReports(reports.filter(p => p.x <= r.x)), r.x));
    contextPrefixChecks++;
    if (!event && context.status !== 'AVAILABLE') continue;
    const observation = event || {id: `CONTEXT_CONTROL:${input.session}:${r.x}`, x: r.x, spot: r.spot, expiry: r.expiry,
      watch: 'LONG_WATCH', category: 'CONTROL', state: 'none'};
    const strike = nearOtmStrikes(r.spot, 'CE', 50)[0];
    const contract = r.contracts.find(c => c.side === 'CE' && c.strike === strike);
    const optionBars = bars.get(`${expiryISO(r.expiry)}|${contract?.symbol}`) || [];
    const phase = r.x < Date.parse(`${input.session}T15:15:00+05:30`) ? 'CONTINUOUS' : 'CAS_PERIOD';
    const row = {id: observation.id, session: input.session, x: r.x, ist: isoIST(r.x), spot: r.spot, expiry: r.expiry,
      phase, greenBubble: Boolean(event), context, vixChangePct: vixChange5m(index, r.x),
      putCoverage: nearPutCoverage(index, r.x), spikes: event?.spikes || [],
      horizons: [5, 10, 15].map(h => horizonOutcome(observation, reports, h, input.session)),
      trade: evaluateLongOption(observation, 'CE', r, optionBars, input.session)};
    dayRows.push(row);
  }
  observations.push(...dayRows);
  days.push({session: input.session, source: input.source, inputFile: filename,
    inputSha256: crypto.createHash('sha256').update(inputBytes).digest('hex'),
    reports: reports.length, greens: greenByTime.size, contextAvailable: dayRows.filter(r => r.context.status === 'AVAILABLE').length});
  console.log(JSON.stringify({session: input.session, reports: reports.length, greens: greenByTime.size}));
}

function summarize(rows) {
  return {observations: rows.length, sessions: new Set(rows.map(r => r.session)).size,
    responseCounts: countBy(rows, r => r.context.response || 'UNKNOWN'),
    horizons: [5, 10, 15].map(h => {
      const available = rows.map(r => validHorizon(r, h)).filter(Boolean), changes = available.map(v => v.changePoints);
      return {minutes: h, available: changes.length, excluded: rows.length - changes.length,
        meanIndexPoints: mean(changes), medianIndexPoints: median(changes),
        up: changes.filter(x => x > 0).length, down: changes.filter(x => x < 0).length, flat: changes.filter(x => x === 0).length,
        upFraction: changes.length ? changes.filter(x => x > 0).length / changes.length : null};
    }), option: summarizeTrades(rows.map(r => r.trade)),
    optionResolvedAfter1515: rows.filter(r => r.trade.exitBarAt >= Date.parse(`${r.session}T15:15:00+05:30`)).length};
}

// Resample dates as clusters; the weighted statistic still gives each matched case equal weight.
function clusterInterval(pairs) {
  if (!pairs.length) return null;
  const sessions = days.map(d => d.session), perDay = new Map(sessions.map(d => [d, pairs.filter(p => p.session === d).map(p => p.difference)]));
  let state = 20260912;
  const random = () => { state = (1664525 * state + 1013904223) >>> 0; return state / 4294967296; };
  const samples = [];
  for (let i = 0; i < 2000; i++) {
    const sample = Array.from({length: sessions.length}, () => perDay.get(sessions[Math.floor(random() * sessions.length)])).flat();
    if (sample.length) samples.push(mean(sample));
  }
  samples.sort((a, b) => a - b);
  const q = p => { const n = (samples.length - 1) * p, j = Math.floor(n); return samples[j] + (samples[Math.ceil(n)] - samples[j]) * (n - j); };
  return {lower: q(.025), upper: q(.975), repetitions: samples.length, clustersWithCases: new Set(pairs.map(p => p.session)).size};
}

function matchedComparison(cases, controls, name) {
  const strata = new Map();
  for (const r of controls) { const key = matchKey(r); if (!strata.has(key)) strata.set(key, []); strata.get(key).push(r); }
  const matches = cases.map(c => ({caseId: c.id, session: c.session, ist: c.ist, key: matchKey(c), controlIds: (strata.get(matchKey(c)) || []).map(r => r.id)}));
  const byId = new Map(controls.map(c => [c.id, c]));
  const horizons = [5, 10, 15].map(h => {
    const pairs = [];
    for (const c of cases) {
      const caseOutcome = validHorizon(c, h); if (!caseOutcome) continue;
      const pool = (strata.get(matchKey(c)) || []).map(r => validHorizon(r, h)).filter(Boolean);
      if (!pool.length) continue;
      const controlMean = mean(pool.map(p => p.changePoints));
      pairs.push({caseId: c.id, session: c.session, casePoints: caseOutcome.changePoints, controlMean, difference: caseOutcome.changePoints - controlMean, controls: pool.length});
    }
    return {minutes: h, matchedCases: pairs.length, unmatchedOrUnavailable: cases.length - pairs.length,
      meanCasePoints: mean(pairs.map(p => p.casePoints)), meanControlPoints: mean(pairs.map(p => p.controlMean)),
      meanDifferencePoints: mean(pairs.map(p => p.difference)), difference95Interval: clusterInterval(pairs), pairs};
  });
  // Each case's entire control stratum receives total weight one, retaining unresolved/skipped observations.
  const weightedStatuses = {}, matchedCases = [];
  for (const m of matches) if (m.controlIds.length) {
    matchedCases.push(cases.find(c => c.id === m.caseId));
    for (const id of m.controlIds) { const status = byId.get(id).trade.status; weightedStatuses[status] = (weightedStatuses[status] || 0) + 1 / m.controlIds.length; }
  }
  const targetWeight = (weightedStatuses.TARGET || 0) + (weightedStatuses.TARGET_GAP || 0);
  const stopWeight = (weightedStatuses.STOP || 0) + (weightedStatuses.STOP_GAP || 0);
  return {name, controlsAvailable: controls.length, caseCount: cases.length,
    matched: matches.filter(m => m.controlIds.length).length, unmatched: matches.filter(m => !m.controlIds.length).length,
    distinctControlsUsed: new Set(matches.flatMap(m => m.controlIds)).size, horizons,
    option: {caseSummary: summarizeTrades(matchedCases.map(r => r.trade)),
      weightedControlStatuses: weightedStatuses, weightedControlTargetFractionAll: matchedCases.length ? targetWeight / matchedCases.length : null,
      weightedControlDecidedWinRate: targetWeight + stopWeight ? targetWeight / (targetWeight + stopWeight) : null}, matches};
}

const allGreen = observations.filter(green), primaryEligible = observations.filter(continuous);
const rawGreen = primaryEligible.filter(green), bullishGreen = rawGreen.filter(r => bullish(r));
const episodeCases = selectEpisodes(bullishGreen), episodeIds = new Set(episodeCases.map(r => r.id));
const generalControls = primaryEligible.filter(r => bullish(r) && usableControl(r));
const sameVixControls = generalControls.filter(r => r.vixChangePct >= .4 - 1e-10);
const comparisons = [matchedComparison(episodeCases, generalControls, 'BULLISH_NO_GREEN'),
  matchedComparison(episodeCases, sameVixControls, 'BULLISH_VIX_UP_NO_GREEN')];
const sensitivity = [.2, .3, .4].map(threshold => {
  const cases = selectEpisodes(rawGreen.filter(r => bullish(r, threshold)));
  const controls = primaryEligible.filter(r => bullish(r, threshold) && usableControl(r) && r.vixChangePct >= .4 - 1e-10);
  const comparison = matchedComparison(cases, controls, 'BULLISH_VIX_UP_NO_GREEN');
  return {threshold, ...summarize(cases), sameVixMatched: {...comparison, matches: undefined,
    horizons: comparison.horizons.map(({pairs, ...h}) => h)}};
});
const firstTen = new Set(days.slice(0, 10).map(d => d.session));
const summary = {protocol, protocolSha256, status: 'PASS', sessions: days.length, contextPrefixChecks,
  exclusions: {allGreen: allGreen.length, lateSignal: allGreen.length - rawGreen.length,
    greenContextUnknown: rawGreen.filter(r => r.context.status === 'UNKNOWN').length,
    greenKnownNotBullish: rawGreen.filter(r => r.context.status === 'AVAILABLE' && !bullish(r)).length,
    bullishGreens: bullishGreen.length, repeatGreens: bullishGreen.length - episodeCases.length,
    primaryEpisodes: episodeCases.length, episodePutCoverage: countBy(episodeCases, r => r.putCoverage)},
  groups: {unfilteredGreenContinuous: summarize(rawGreen), unfilteredGreenEpisodes: summarize(selectEpisodes(rawGreen)),
    bullishGreenAll: summarize(bullishGreen), bullishGreenEpisodes: summarize(episodeCases),
    bullishGreenPriceUp: summarize(episodeCases.filter(r => r.context.response === 'PRICE_UP_WITH_VIX')),
    bullishGreenPullback: summarize(episodeCases.filter(r => r.context.response === 'PULLBACK_WITH_VIX')),
    bullishNoGreen: summarize(generalControls), bullishVixUpNoGreen: summarize(sameVixControls)},
  comparisons: comparisons.map(({matches, ...c}) => ({...c, horizons: c.horizons.map(({pairs, ...h}) => h)})),
  sensitivity,
  chronology: {firstTen: summarize(episodeCases.filter(r => firstTen.has(r.session))), lastFive: summarize(episodeCases.filter(r => !firstTen.has(r.session)))},
  days: days.map(d => ({...d, episodes: summarize(episodeCases.filter(r => r.session === d.session)),
    greenContexts: countBy(allGreen.filter(r => r.session === d.session), r => r.context.label)}))};
write('summary.json', summary);
write('observations.json', observations);
write('green-bubbles.json', allGreen.map(r => ({...r, primaryEpisode: episodeIds.has(r.id)})));
write('matched-controls.json', comparisons);
const csv = (rows, fields) => [fields.join(','), ...rows.map(r => fields.map(f => {
  const s = String(r[f] ?? ''); return /[",\r\n]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s;
}).join(','))].join('\n') + '\n';
const ledger = rows => rows.map(r => ({session: r.session, signalIST: r.ist, green: r.greenBubble, episode: episodeIds.has(r.id),
  phase: r.phase, context: r.context.label, efficiency: r.context.efficiency, average: r.context.average,
  trendEndIST: r.context.trendEndAt ? isoIST(r.context.trendEndAt) : '', spot: r.spot, priceChange5m: r.context.priceChange5m,
  subgroup: r.context.response, vixChangePct: r.vixChangePct, putCoverage: r.putCoverage,
  oiSpikes: r.spikes.map(s => `${s.strike}PE fall ${s.dropPct.toFixed(4)}% / ${s.multiple.toFixed(4)}x`).join('; '),
  ...Object.fromEntries([5, 10, 15].flatMap(h => {
    const v = r.horizons.find(v => v.minutes === h); return [[`index${h}m`, validHorizon(r, h)?.changePoints ?? ''], [`index${h}mStatus`, v.status === 'AVAILABLE' ? v.phase : v.status]];
  })), symbol: r.trade.symbol, optionEntryIST: isoIST(r.trade.entryAt), optionEntry: r.trade.entryPrice,
  optionStatus: r.trade.status, optionExitBarIST: r.trade.exitBarAt ? isoIST(r.trade.exitBarAt) : '',
  optionGrossPoints: r.trade.grossPoints, unrealizedPoints: r.trade.unrealizedPoints}));
const allLedger = ledger(observations), fields = Object.keys(allLedger[0]);
fs.writeFileSync(path.join(values.output, 'all-observations.csv'), csv(allLedger, fields));
fs.writeFileSync(path.join(values.output, 'green-bubble-timestamps.csv'), csv(ledger(allGreen), fields));
fs.writeFileSync(path.join(values.output, 'primary-episode-timestamps.csv'), csv(ledger(episodeCases), fields));
write('verification.json', {status: 'PASS', contextPrefixChecks, protocolSha256,
  detector: 'Original production module imported unchanged', outcomeEvaluator: 'Original OI_VIX_OUTCOMES_V1 imported unchanged'});
console.log(JSON.stringify({status: summary.status, exclusions: summary.exclusions, primary: summary.groups.bullishGreenEpisodes}));
