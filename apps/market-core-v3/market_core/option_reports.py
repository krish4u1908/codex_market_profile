"""Read-only option-chain report quotes, separate from frozen engine decisions.

One bounded background reader in each existing core. HTTP handlers only enqueue
work and return cached bytes; raw archive scans never run in a request or tick.
"""
from collections import OrderedDict
from datetime import datetime, timezone
import gzip
import math
import re
import threading
import time
from zoneinfo import ZoneInfo
import json

from .config import INSTRUMENTS, session_date
from .storage import encode

SCHEMA = 'OPTION_REPORT_INPUTS_V1'
IST = ZoneInfo('Asia/Kolkata')


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def parse_report(raw, instrument, day):
    if raw.get('source') != 'option_chain' or raw.get('response', {}).get('code') != 200:
        return None
    received = datetime.fromisoformat(raw['received_at'].replace('Z', '+00:00'))
    if received.tzinfo is None:
        return None
    local = received.astimezone(IST)
    if local.date().isoformat() != day or not (9, 15) <= (local.hour, local.minute) < (15, 30):
        return None
    data = raw['response']['data']
    chain = data.get('optionsChain', [])
    index = next((r for r in chain if r.get('symbol') == INSTRUMENTS[instrument]), None)
    if index is None:  # Never mix NIFTY and BANKNIFTY archives.
        return None
    vix = data.get('indiavixData') or {}
    expiries = data.get('expiryData') or []
    expiry = str(expiries[0].get('date') or expiries[0].get('expiry') or '') if expiries else ''
    contracts = []
    seen = set()
    for row in chain:
        symbol, side, strike = row.get('symbol'), row.get('option_type'), row.get('strike_price')
        if side not in ('CE', 'PE') or not positive(strike) or not isinstance(symbol, str):
            continue
        if not re.fullmatch(r'NSE:' + instrument + r'\d[^\s]*' + side, symbol):
            continue
        if symbol in seen:
            raise ValueError('Duplicate option contract in a report')
        seen.add(symbol)
        contracts.append(dict(symbol=symbol, side=side, strike=strike, oi=row.get('oi') if positive(row.get('oi')) else None))
    return dict(x=int(received.timestamp() * 1000), t=raw['received_at'], expiry=expiry,
                spot=index.get('ltp') if positive(index.get('ltp')) else None,
                vix=vix.get('ltp') if vix.get('symbol') == 'NSE:INDIAVIX-INDEX' and positive(vix.get('ltp')) else None,
                contracts=contracts)


class OptionReportReader:
    def __init__(self, config, day):
        self.config, self.day = config, session_date(day)
        self.offsets, self.reports = {}, {}
        self.rejected = 0

    def poll(self):
        files = sorted((self.config.collector_root / 'oi' / self.day).glob('oi_*.jsonl'))
        # A replaced/truncated source is rebuilt, never appended to old totals.
        if any(path in self.offsets and (path.stat().st_ino != self.offsets[path][0] or
               path.stat().st_size < self.offsets[path][1]) for path in files):
            self.offsets, self.reports, self.rejected = {}, {}, 0
        for path in files:
            inode = path.stat().st_ino
            offset = self.offsets.get(path, (inode, 0))[1]
            with path.open('rb') as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline()
                    if not line or not line.endswith(b'\n'):
                        break  # Do not consume a live collector's partial line.
                    offset = handle.tell()
                    try:
                        row = parse_report(json.loads(line), self.config.instrument, self.day)
                    except (KeyError, TypeError, ValueError):
                        self.rejected += 1
                        continue
                    if row is None:
                        continue
                    old = self.reports.get(row['x'])
                    if old is not None and old != row:
                        raise ValueError('Conflicting option reports at the same receipt time')
                    self.reports[row['x']] = row
            self.offsets[path] = inode, offset
        now = datetime.now(timezone.utc)
        rows = [r for _, r in sorted(self.reports.items()) if r['x'] <= int(now.timestamp() * 1000)]
        return dict(schema=SCHEMA, instrument=self.config.instrument, session=self.day,
                    source='OPTION_CHAIN_REPORT_QUOTES', clock='COLLECTOR_RECEIPT_TIME',
                    status='AVAILABLE' if rows else 'MISSING', as_of=now.isoformat(),
                    strike_step=50 if self.config.instrument == 'NIFTY' else 100,
                    quality=dict(reports=len(rows), rejected_lines=self.rejected,
                                 vix_valid=sum(r['vix'] is not None for r in rows)), reports=rows)


class OptionReportCache:
    """At most four sessions retained and eight pending reads per core."""
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.wake, self.stop = threading.Event(), threading.Event()
        self.pending, self.entries, self.readers = OrderedDict(), OrderedDict(), OrderedDict()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name='option-report-reader', daemon=True)
        self.thread.start()

    def request(self, day):
        day = session_date(day)
        with self.lock:
            entry = self.entries.get(day)
            if entry:
                self.entries.move_to_end(day)
            if (entry is None or time.monotonic() - entry['checked'] >= 5) and len(self.pending) < 8:
                self.pending.setdefault(day, None)
                self.wake.set()
            if entry:
                return entry
        feed = dict(schema=SCHEMA, instrument=self.config.instrument, session=day, status='PENDING', reports=[])
        body = encode(feed)
        return dict(feed=feed, body=body, compressed=gzip.compress(body), code=202)

    def _run(self):
        while not self.stop.is_set():
            self.wake.wait(1)
            with self.lock:
                if not self.pending:
                    self.wake.clear()
                    continue
                day, _ = self.pending.popitem(last=False)
            try:
                reader = self.readers.setdefault(day, OptionReportReader(self.config, day))
                self.readers.move_to_end(day)
                while len(self.readers) > 4:
                    self.readers.popitem(last=False)
                feed = reader.poll()
            except Exception:
                feed = dict(schema=SCHEMA, instrument=self.config.instrument, session=day,
                            status='ERROR', error='Option-report archive could not be verified', reports=[])
            body = encode(feed)
            entry = dict(feed=feed, body=body, compressed=gzip.compress(body, compresslevel=1, mtime=0),
                         code=200, checked=time.monotonic())
            with self.lock:
                self.entries[day] = entry
                while len(self.entries) > 4:
                    self.entries.popitem(last=False)

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join()
