#!/usr/bin/env python3
"""Independently reconcile context, controls and option barriers to the original ZIP.

Uses Python Decimal and raw source rows, without importing the JavaScript detector,
context classifier, or outcome evaluator. No service or GUI access.
"""
import argparse
import bisect
import collections
import csv
from datetime import datetime
from decimal import Decimal as D
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--inputs', type=Path, required=True)
parser.add_argument('--results', type=Path, required=True)
args = parser.parse_args()
load = lambda p: json.loads(p.read_text())
stamp = lambda s: int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() * 1000)
positive = lambda x: isinstance(x, (int, float, D)) and math.isfinite(x) and x > 0
decimal = lambda x: D(str(x))


def close(a, b):
    assert abs(float(a) - float(b)) < 1e-8, (a, b)


def number(s):
    try:
        x = D(s)
        return x if x.is_finite() else None
    except Exception:
        return None


def bar_problem(r):
    p = [number(r[k]) for k in ('ltp_open', 'ltp_high', 'ltp_low', 'ltp_close')]
    if not all(positive(x) for x in p):
        return 'INVALID_OHLC'
    o, h, low, c = p
    if low > min(o, c) or h < max(o, c) or low > h:
        return 'INVALID_OHLC'
    if not positive(number(r['quote_event_count'])):
        return 'NO_QUOTES'
    if number(r['gap_flag']) != 0:
        return 'FEED_GAP'
    if number(r['timestamp_anomaly_count']) != 0:
        return 'TIMESTAMP_ANOMALY'
    return None


def option_result(trade, report, series):
    entry_at = (report['x'] // 60000 + 1) * 60000
    assert entry_at == trade['entryAt']
    strike = (math.floor(report['spot'] / 50) + 1) * 50
    assert strike == trade['strike']
    contracts = [c for c in report['contracts'] if c['side'] == 'CE' and c['strike'] == strike]
    if len(contracts) != 1:
        return 'NO_UNIQUE_CONTRACT'
    assert contracts[0]['symbol'] == trade['symbol']
    expected_expiry = datetime.strptime(report['expiry'], '%d-%m-%Y').date().isoformat()
    assert trade['expiry'] == expected_expiry
    rows = series.get((expected_expiry, trade['symbol']), [])
    times = [r[0] for r in rows]
    at = bisect.bisect_left(times, entry_at)
    if at == len(rows) or rows[at][0] != entry_at:
        return 'NO_ENTRY_BAR'
    first = rows[at][2]
    problem = bar_problem(first)
    if problem or not positive(number(first['minute_volume'])):
        return 'ENTRY_' + (problem or 'NO_VOLUME')
    event_at = stamp(first['first_event_time']) if first['first_event_time'] else None
    if event_at is None or not entry_at <= event_at < entry_at + 60000:
        return 'ENTRY_TIMESTAMP_INVALID'
    entry = D(first['ltp_open'])
    assert entry == decimal(trade['entryPrice'])
    if entry <= 20:
        return 'ENTRY_PREMIUM_NOT_ABOVE_20'
    stop, target = entry - 20, entry + 20
    assert stop == decimal(trade['stopPrice']) and target == decimal(trade['targetPrice'])
    assert rows[at][1] == trade['entrySourceRow']
    previous = entry_at - 60000
    cutoff = stamp(trade['session'] + 'T15:40:00+05:30')
    for t, line, r in rows[at:]:
        if t >= cutoff:
            break
        problem = bar_problem(r)
        if t != previous + 60000 or problem:
            return 'CENSORED_' + (problem or 'MISSING_MINUTE')
        previous = t
        o, high, low = (D(r[k]) for k in ('ltp_open', 'ltp_high', 'ltp_low'))
        gross = None
        if o <= stop:
            status, gross = 'STOP_GAP', o - entry
        elif o >= target:
            status, gross = 'TARGET_GAP', D(20)
        elif low <= stop and high >= target:
            status = 'AMBIGUOUS_BOTH'
        elif low <= stop:
            status, gross = 'STOP', D(-20)
        elif high >= target:
            status, gross = 'TARGET', D(20)
        else:
            continue
        assert t == trade['exitBarAt'] and line == trade['exitSourceRow']
        if gross is not None:
            close(gross, trade['grossPoints'])
        return status
    return 'OPEN_AT_DATA_END'


summary = load(args.results / 'summary.json')
observations = load(args.results / 'observations.json')
greens = load(args.results / 'green-bubbles.json')
matches = load(args.results / 'matched-controls.json')
archive_hash = hashlib.sha256(args.archive.read_bytes()).hexdigest()
checks = collections.Counter()
expected_green_times = set()
expected_episodes = []

with zipfile.ZipFile(args.archive) as archive:
    for day in [d['session'] for d in summary['days']]:
        prepared = load(args.inputs / (day + '-research-inputs.json'))
        assert prepared['source']['archive_sha256'] == archive_hash
        raw_reports = {}
        for name in sorted(n for n in archive.namelist() if n.startswith('oi/' + day + '/') and n.endswith('.jsonl')):
            for line in archive.read(name).splitlines():
                raw = json.loads(line)
                if raw.get('source') != 'option_chain' or raw.get('response', {}).get('code') != 200:
                    continue
                data = raw['response']['data']
                underlying = [c for c in data['optionsChain'] if c['symbol'] == 'NSE:NIFTY50-INDEX']
                if not underlying:
                    continue
                t = stamp(raw['received_at'])
                if not stamp(day + 'T09:15:00+05:30') <= t < stamp(day + 'T15:30:00+05:30'):
                    continue
                raw_reports[t] = dict(x=t, spot=underlying[0]['ltp'], vix=data['indiavixData']['ltp'],
                    expiry=data['expiryData'][0]['date'], contracts=[dict(symbol=c['symbol'], side=c['option_type'],
                    strike=c['strike_price'], oi=c.get('oi') if positive(c.get('oi')) else None)
                    for c in data['optionsChain'] if c.get('option_type') in ('PE', 'CE') and c['symbol'].startswith('NSE:NIFTY')])
        byslot = {r['x'] // 60000: r for r in raw_reports.values()}
        assert len(byslot) == len(raw_reports)
        for r in prepared['option_report_inputs']['reports']:
            raw = raw_reports[r['x']]
            for k in ('spot', 'vix', 'expiry', 'contracts'):
                assert r[k] == raw[k]
            checks['rawReportChecks'] += 1
        series = collections.defaultdict(list)
        member = 'minute/' + day + '/market_1m.csv'
        for line, r in enumerate(csv.DictReader(io.TextIOWrapper(archive.open(member))), 2):
            if r['instrument_class'] == 'call' and r['symbol'].startswith('NSE:NIFTY'):
                series[(r['expiry_date'], r['symbol'])].append((stamp(r['minute']), line, r))
        for rows in series.values():
            rows.sort(key=lambda v: v[0])
        bytime = {r['x']: r for r in observations if r['session'] == day}
        last_episode = None
        for slot, report in sorted(byslot.items()):
            seq = [byslot.get(s) for s in range(slot - 35, slot + 1)]
            valid = all(r and positive(r['spot']) for r in seq) and all(0 < seq[i]['x'] - seq[i-1]['x'] <= 90000 for i in range(1, 36))
            context_label = 'UNKNOWN'
            if valid:
                p = [decimal(r['spot']) for r in seq]
                net = p[30] - p[0]
                travel = sum(abs(p[i] - p[i-1]) for i in range(1, 31))
                efficiency = net / travel if travel else D(0)
                average = sum(p[1:31]) / 30
                context_label = 'BULLISH' if efficiency >= D('.3') and p[30] > average and p[35] > average else 'BEARISH' if efficiency <= D('-.3') and p[30] < average and p[35] < average else 'MIXED'
            vseq = [byslot.get(s) for s in range(slot-5, slot+1)]
            vvalid = all(r and positive(r['vix']) for r in vseq) and all(0 < vseq[i]['x'] - vseq[i-1]['x'] <= 90000 for i in range(1, 6))
            vchange = D(100) * (decimal(vseq[-1]['vix']) - decimal(vseq[0]['vix'])) / decimal(vseq[0]['vix']) if vvalid else None
            first = (math.ceil(report['spot'] / 50) - 1) * 50
            oi_spikes, coverage = [], 0
            prior = [byslot.get(s) for s in range(slot-21, slot+1)]
            history_valid = all(r and r['expiry'] == report['expiry'] for r in prior) and all(0 < prior[i]['x'] - prior[i-1]['x'] <= 90000 for i in range(1, 22))
            if history_valid:
                for strike in (first, first-50, first-100):
                    cs = [c for c in report['contracts'] if c['side'] == 'PE' and c['strike'] == strike]
                    if len(cs) != 1:
                        continue
                    h = [[c for c in r['contracts'] if c['symbol'] == cs[0]['symbol']] for r in prior]
                    if any(len(v) != 1 or not positive(v[0]['oi']) for v in h):
                        continue
                    oi = [decimal(v[0]['oi']) for v in h]
                    changes = [100 * (oi[i-1]-oi[i]) / oi[i-1] for i in range(1, 22)]
                    normal = statistics.median(abs(v) for v in changes[:20])
                    if normal <= 0:
                        continue
                    coverage += 1
                    if changes[-1] >= D('0.9999999999') and changes[-1] / normal >= D('2.9999999999'):
                        oi_spikes.append(strike)
            is_green = bool(report['x'] >= stamp(day + 'T09:45:00+05:30') and oi_spikes and vchange is not None and vchange >= D('0.3999999999'))
            if is_green:
                expected_green_times.add(report['x'])
            if report['x'] not in bytime:
                assert not valid and not is_green, (day, report['x'], valid, is_green)
                continue
            row = bytime[report['x']]
            assert row['greenBubble'] == is_green
            assert row['context']['label'] == context_label
            assert row['putCoverage'] == coverage
            if vchange is None:
                assert row['vixChangePct'] is None
            else:
                close(vchange, row['vixChangePct'])
            if valid:
                for key, value in [('efficiency', efficiency), ('average', average), ('netTrendPoints', net), ('travelledPoints', travel), ('priceChange5m', p[35]-p[30])]:
                    close(value, row['context'][key])
                assert row['context']['trendEndAt'] == seq[30]['x']
            checks['contextAndEligibilityChecks'] += 1
            for outcome in row['horizons']:
                endpoint = byslot.get(slot + outcome['minutes'])
                if outcome['status'] == 'AVAILABLE':
                    assert endpoint['x'] == outcome['at']
                    close(decimal(endpoint['spot']) - decimal(report['spot']), outcome['changePoints'])
                    checks['horizonArithmeticChecks'] += 1
            result = option_result(row['trade'], report, series)
            assert row['trade']['status'] == result, (day, row['ist'], row['trade']['status'], result)
            checks['rawCsvOptionChecks'] += 1
            if is_green and context_label == 'BULLISH' and report['x'] < stamp(day + 'T15:15:00+05:30'):
                if last_episode is None or slot - last_episode >= 15:
                    expected_episodes.append(row['id'])
                    last_episode = slot
        print(json.dumps({'verifiedSession': day, 'observations': len(bytime)}), flush=True)

assert expected_green_times == {r['x'] for r in greens}
assert expected_episodes == [r['id'] for r in greens if r['primaryEpisode']]
byid = {r['id']: r for r in observations}


def match_key(r):
    h = datetime.fromisoformat(r['ist']).hour
    return r['session'], h, (r['context']['priceChange5m'] > 0) - (r['context']['priceChange5m'] < 0)


for comparison in matches:
    pool = [r for r in observations if not r['greenBubble'] and r['context']['label'] == 'BULLISH' and
            r['phase'] == 'CONTINUOUS' and r['putCoverage'] == 3 and r['vixChangePct'] is not None and
            (comparison['name'] != 'BULLISH_VIX_UP_NO_GREEN' or r['vixChangePct'] >= .4 - 1e-10)]
    assert len(pool) == comparison['controlsAvailable']
    for match in comparison['matches']:
        eligible = [r['id'] for r in pool if match_key(r) == match_key(byid[match['caseId']])]
        assert match['controlIds'] == eligible
        checks['matchedControlStrataChecks'] += 1
    for h in comparison['horizons']:
        diffs = []
        for pair in h['pairs']:
            case = byid[pair['caseId']]
            controls = [r for r in pool if match_key(r) == match_key(case)]
            outcomes = [v['changePoints'] for c in controls for v in c['horizons'] if v['minutes'] == h['minutes'] and v['status'] == 'AVAILABLE' and v['phase'] == 'CONTINUOUS']
            control_mean = statistics.mean(outcomes)
            close(control_mean, pair['controlMean'])
            point = next(v['changePoints'] for v in case['horizons'] if v['minutes'] == h['minutes'])
            close(point - control_mean, pair['difference'])
            diffs.append(point - control_mean)
        if diffs:
            close(statistics.mean(diffs), h['meanDifferencePoints'])

result = dict(status='PASS', method='Independent Python Decimal from original ZIP reports and CSV option rows',
              sourceArchiveSha256=archive_hash, greenEligibilityChecks=len(expected_green_times),
              primaryEpisodes=len(expected_episodes), **checks)
(args.results / 'raw-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
