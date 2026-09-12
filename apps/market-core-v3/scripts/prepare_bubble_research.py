#!/usr/bin/env python3
"""Prepare read-only research inputs from a collector minute/OI ZIP.

No extraction into collector directories and no running-service access.
The production parser determines report identity, expiry, OI and VIX quotes.
"""
import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_core.option_reports import parse_report


def number(value):
    try:
        result = float(value)
        return result if abs(result) < float('inf') else None
    except (TypeError, ValueError):
        return None


def stamp(value):
    return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000) if value else None


def prepare(archive, output):
    output.mkdir(parents=True, exist_ok=True)
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        dates = sorted(re.fullmatch(r'minute/(\d{4}-\d{2}-\d{2})/market_1m.csv', n).group(1)
                       for n in names if re.fullmatch(r'minute/(\d{4}-\d{2}-\d{2})/market_1m.csv', n))
        for day in dates:
            reports, hashes = {}, {}
            for name in sorted(n for n in names if n.startswith('oi/' + day + '/') and n.endswith('.jsonl')):
                content = source.read(name)
                hashes[name] = hashlib.sha256(content).hexdigest()
                for line in content.splitlines():
                    raw = json.loads(line)
                    row = parse_report(raw, 'NIFTY', day)
                    if row:
                        if row['x'] in reports and reports[row['x']] != row:
                            raise ValueError('Conflicting report at ' + row['t'])
                        reports[row['x']] = row
            name = 'minute/' + day + '/market_1m.csv'
            content = source.read(name)
            hashes[name] = hashlib.sha256(content).hexdigest()
            bars, seen = [], set()
            for line, row in enumerate(csv.DictReader(io.StringIO(content.decode())), 2):
                if row['instrument_class'] not in ('call', 'put'):
                    continue
                if not re.fullmatch(r'NSE:NIFTY\d\S*(CE|PE)', row['symbol']):
                    continue
                x = stamp(row['minute'])
                key = (row['symbol'], x)
                if key in seen:
                    raise ValueError('Duplicate minute candle ' + str(key))
                seen.add(key)
                bars.append(dict(x=x, symbol=row['symbol'], expiry=row['expiry_date'],
                    open=number(row['ltp_open']), high=number(row['ltp_high']),
                    low=number(row['ltp_low']), close=number(row['ltp_close']),
                    quotes=number(row['quote_event_count']), gap=number(row['gap_flag']),
                    anomalies=number(row['timestamp_anomaly_count']),
                    volume=number(row['minute_volume']),
                    firstEventAt=stamp(row['first_event_time']),
                    firstReceivedAt=stamp(row['first_received_time']),
                    lastReceivedAt=stamp(row['last_received_time']), sourceRow=line))
            feed = dict(schema='OPTION_REPORT_INPUTS_V1', instrument='NIFTY', session=day,
                source='OPTION_CHAIN_REPORT_QUOTES', clock='COLLECTOR_RECEIPT_TIME',
                status='AVAILABLE' if reports else 'MISSING', reports=[v for _, v in sorted(reports.items())])
            result = dict(schema='BUBBLE_RESEARCH_INPUTS_V1', instrument='NIFTY', session=day,
                source=dict(archive=archive.name, archive_sha256=archive_hash, members=hashes),
                option_report_inputs=feed, optionBars=sorted(bars, key=lambda b: (b['x'], b['symbol'])))
            target = output / (day + '-research-inputs.json')
            target.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
            print(json.dumps(dict(day=day, reports=len(reports), optionBars=len(bars), file=str(target))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.archive, args.output)
