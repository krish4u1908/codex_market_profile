"""Versioned, as-observed Cash/VIX inputs; frozen calls keep their own inputs.

Each completed source minute can have several immutable revisions. A correction
is usable only from its availability timestamp, never from the old minute time.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from .storage import atomic_write, encode

SCHEMA = 'CASH_VIX_INDICATOR_INPUTS_V1'
IST = ZoneInfo('Asia/Kolkata')
VIX_SYMBOL = 'NSE:INDIAVIX-INDEX'


def instant(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Input timestamp must include a timezone')
    return result


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def positive(value):
    if isinstance(value, bool): return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def digest(body):
    return hashlib.sha256(body).hexdigest()


def latest_minutes(revisions, as_of):
    as_of = instant(as_of) if isinstance(as_of, str) else as_of
    selected = {}
    for row in revisions:
        if instant(row['available_at']) <= as_of and instant(row['minute_end']) <= as_of:
            old = selected.get(row['minute_ist'])
            if old is None or row['revision'] > old['revision']:
                selected[row['minute_ist']] = row
    return [selected[key] for key in sorted(selected)]


def indicator_window(feed, as_of, minutes=5, field='vix_close'):
    """Require exact consecutive minutes and known, valid data. No filling."""
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 375:
        raise ValueError('minutes must be an integer between 1 and 375')
    if field not in ('vix_close', 'cash_weighted_pct'):
        raise ValueError('Unsupported indicator input')
    now = instant(as_of) if isinstance(as_of, str) else as_of
    end = min(now - timedelta(seconds=feed.get('finalize_delay_seconds', 8)),
              instant(feed['session_end'])).replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes)
    by_minute = {instant(r['minute_ist']): r for r in latest_minutes(feed['revisions'], now)}
    selected = [by_minute.get(start + timedelta(minutes=i)) for i in range(minutes)]
    valid_key = 'vix_valid' if field == 'vix_close' else 'cash_valid'
    missing = [iso(start + timedelta(minutes=i)) for i, r in enumerate(selected) if not r or not r[valid_key]]
    reasons = []
    if start < instant(feed['session_start']): reasons.append('WARMUP')
    if missing: reasons.append('INCOMPLETE_WINDOW')
    # A historical as-of query is independent of a later transport failure.
    if now >= instant(feed['as_of']) and feed['status'] != 'AVAILABLE': reasons.append('SOURCE_UNAVAILABLE')
    return dict(ready=not reasons, field=field, minutes=minutes, as_of=iso(now),
                reasons=reasons, missing_minutes=missing, rows=selected)


class IndicatorInputs:
    def __init__(self, config, session, journal_root=None):
        self.config = config
        self.session = date.fromisoformat(str(session))
        self.start = datetime.combine(self.session, time(9, 15), IST)
        self.end = datetime.combine(self.session, time(15, 30), IST)
        self.root = Path(journal_root) if journal_root else config.state_root/'indicator-inputs'/str(self.session)
        self.revisions, self.latest = [], {}
        self.sequence, self.chain = 0, None
        self.delay, self.status, self.error = 8, 'WAITING', None
        self.signature, self.source_rows, self.metadata = None, {}, {}
        self.source_hash = None
        for path in sorted(self.root.glob('batch-*.json')):
            raw = path.read_bytes(); batch = json.loads(raw)
            if (batch['schema'] != SCHEMA or batch['instrument'] != config.instrument
                or batch['session'] != str(self.session) or batch['sequence'] != self.sequence + 1
                or batch['previous_sha256'] != self.chain):
                raise ValueError('Indicator input journal chain mismatch')
            for row in batch['records']: self._accept(row)
            self.sequence, self.chain = batch['sequence'], digest(raw)

    def _accept(self, row):
        previous = self.latest.get(row['minute_ist'])
        if row['revision'] != (previous['revision'] + 1 if previous else 1):
            raise ValueError('Indicator input revision sequence mismatch')
        if previous and instant(row['available_at']) < instant(previous['available_at']):
            raise ValueError('Indicator availability moved backwards')
        self.revisions.append(row); self.latest[row['minute_ist']] = row

    def _append(self, records, observed):
        if not records: return
        staged = dict(self.latest)
        for row in records:
            previous = staged.get(row['minute_ist'])
            minute, available = instant(row['minute_ist']), instant(row['available_at'])
            if (not self.start <= minute < self.end or instant(row['minute_end']) != minute+timedelta(minutes=1)
                or available < instant(row['minute_end']) or available > observed
                or row['revision'] != (previous['revision']+1 if previous else 1)
                or (previous and available < instant(previous['available_at']))):
                raise ValueError('Invalid indicator observation or revision clock')
            staged[row['minute_ist']] = row
        batch = dict(schema=SCHEMA, instrument=self.config.instrument, session=str(self.session),
                     sequence=self.sequence + 1, previous_sha256=self.chain, recorded_at=iso(observed), records=records)
        raw = encode(batch); path = self.root/f'batch-{self.sequence+1:06d}.json'
        if path.exists(): raise ValueError('Refusing to overwrite an input journal batch')
        atomic_write(path, raw)
        for row in records: self._accept(row)
        self.sequence += 1; self.chain = digest(raw)

    def _record(self, minute, values, available, origin):
        key = minute.isoformat(timespec='seconds')
        previous = self.latest.get(key)
        if previous and previous['values_sha256'] == digest(encode(values)): return None
        return dict(minute_ist=key, minute_end=iso(minute + timedelta(minutes=1)),
                    available_at=iso(available), revision=previous['revision']+1 if previous else 1,
                    origin=origin, source_sha256=self.source_hash, values_sha256=digest(encode(values)),
                    **values)

    def _seed(self, now):
        if self.sequence: return
        old = self.config.state_root/'runtime/engine'/str(self.session)/'cash_vix_first_observed_v2.jsonl'
        if not old.is_file(): return
        records = []
        for line in old.read_text().splitlines():
            r = json.loads(line); minute = instant(r['minute_ist']).astimezone(IST)
            available = instant(r['t'])
            if minute.date() != self.session or available > now: continue
            if r.get('schema') and not r['schema'].startswith(self.config.instrument+'_CASH_VIX_'):
                raise ValueError('Legacy receipt instrument mismatch')
            vix = positive(r.get('vix_close'))
            cash = r.get('cash_weighted_pct')
            cash = cash if isinstance(cash, (int, float)) and math.isfinite(cash) else None
            count, expected = r.get('cash_names', 0), r.get('expected_constituent_count', 0)
            values = dict(vix_close=vix, vix_valid=vix is not None, vix_received_at=None,
                          cash_weighted_pct=cash, cash_valid=cash is not None and expected > 0 and count == expected,
                          cash_names=count, expected_constituent_count=expected,
                          available_weight=r.get('available_weight', 0), source_published_at=r.get('source_published_at', r['t']))
            record = self._record(minute, values, available, 'RETAINED_LEGACY_RECEIPT')
            if record: records.append(record)
        self._append(records, now)

    def _read(self, as_of):
        path = self.config.collector_root/'minute'/str(self.session)/'market_1m.csv'
        before = path.stat()
        metadata_candidates = []
        for p in (self.config.collector_root/'metadata').glob('startup_*.json'):
            r = json.loads(p.read_bytes())
            if instant(r['started_at']).astimezone(IST).date() == self.session and instant(r['started_at']) <= as_of:
                metadata_candidates.append((instant(r['started_at']), r))
        metadata = max(metadata_candidates, key=lambda x:x[0])[1] if metadata_candidates else {}
        signature = (before.st_ino, before.st_size, before.st_mtime_ns, digest(encode(metadata)))
        if signature == self.signature: return
        body = path.read_bytes(); after = path.stat()
        if ((before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns)
            or not body.endswith(b'\n')):
            raise ValueError('Minute file is being written; retrying')
        reader = csv.DictReader(io.StringIO(body.decode('utf-8')))
        required = {'minute', 'symbol', 'instrument_class', 'ltp_open', 'ltp_close', 'last_received_time'}
        if not required <= set(reader.fieldnames or []): raise ValueError('Required minute columns missing')
        rows = {}
        for r in reader:
            if None in r or any(r.get(key) is None for key in required): raise ValueError('Incomplete minute CSV row')
            symbol = r['symbol'].strip().upper()
            if r['instrument_class'].strip().lower() != 'cash' and symbol != VIX_SYMBOL: continue
            minute = instant(r['minute']).astimezone(IST)
            if minute.date() != self.session or minute.second or minute.microsecond:
                raise ValueError('Invalid source minute or mixed session')
            receipt = instant(r['last_received_time']) if r['last_received_time'] else None
            item = dict(open=positive(r['ltp_open']), close=positive(r['ltp_close']), received=receipt)
            key = (minute, symbol)
            if key in rows:
                if rows[key] != item: raise ValueError('Conflicting duplicate minute/symbol')
            rows[key] = item
        delay = int(metadata.get('finalize_delay', 8))
        if not 0 <= delay <= 300: raise ValueError('Invalid finalization delay')
        identities = metadata.get('base_quote_symbols', [])
        own = 'NSE:NIFTY50-INDEX' if self.config.instrument == 'NIFTY' else 'NSE:NIFTYBANK-INDEX'
        if identities and own not in identities: raise ValueError('Collector instrument identity mismatch')
        if not self.source_rows.keys() <= rows.keys(): raise ValueError('Minute file lost previously observed records; retrying')
        self.source_rows, self.metadata, self.delay = rows, metadata, delay
        self.signature, self.source_hash = signature, digest(body)

    def poll(self, as_of=None):
        explicit = instant(as_of) if isinstance(as_of, str) else as_of
        now = explicit or datetime.now(timezone.utc)
        try:
            self._seed(now)
            self._read(now)
            # The wall clock is captured after the file read, not before it.
            now = explicit or datetime.now(timezone.utc)
            raw_weights = self.metadata.get('constituent_weights') or {}
            if not isinstance(raw_weights, dict): raise ValueError('Invalid cash constituent weights')
            weights = {f'NSE:{str(k).upper()}-EQ': positive(v) for k,v in raw_weights.items()}
            weights = {k:v for k,v in weights.items() if v is not None}
            opens = {}
            for (minute, symbol), r in sorted(self.source_rows.items()):
                if (symbol in weights and self.start <= minute < self.end and r['open'] and symbol not in opens
                    and r['received'] and r['received'] <= now):
                    opens[symbol] = (minute, r['open'])
            records = []; minute = self.start
            while minute < self.end and minute + timedelta(minutes=1, seconds=self.delay) <= now:
                v = self.source_rows.get((minute, VIX_SYMBOL), {})
                receipt = v.get('received')
                vix = v.get('close') if receipt and minute <= receipt <= now else None
                values, receipts = [], []
                for symbol, weight in weights.items():
                    r = self.source_rows.get((minute, symbol), {})
                    if r.get('received') and minute <= r['received'] <= now and r.get('close') and symbol in opens and opens[symbol][0] <= minute:
                        values.append((100*(r['close']/opens[symbol][1]-1), weight)); receipts.append(r['received'])
                if receipt and receipt <= now: receipts.append(receipt)
                total = sum(w for _,w in values)
                cash = sum(x*w for x,w in values)/total if total else None
                value = dict(vix_close=vix, vix_valid=vix is not None, vix_received_at=iso(receipt) if receipt and receipt <= now else None,
                             cash_weighted_pct=round(cash, 6) if cash is not None else None,
                             cash_valid=bool(raw_weights) and len(values)==len(raw_weights), cash_names=len(values),
                             expected_constituent_count=len(raw_weights), available_weight=round(total, 6),
                             source_published_at=iso(max([minute+timedelta(minutes=1, seconds=self.delay), *receipts])))
                record = self._record(minute, value, now, 'COLLECTOR_OBSERVATION')
                if record: records.append(record)
                minute += timedelta(minutes=1)
            self._append(records, now)
            self.status, self.error = 'AVAILABLE', None
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.status, self.error = 'SOURCE_UNAVAILABLE', str(error)
        return self.snapshot(now)

    def snapshot(self, as_of):
        rows = latest_minutes(self.revisions, as_of)
        valid = [r for r in rows if r['vix_valid']]
        feed = dict(schema=SCHEMA, instrument=self.config.instrument, session=str(self.session), as_of=iso(as_of),
                    session_start=iso(self.start), session_end=iso(self.end), finalize_delay_seconds=self.delay,
                    status=self.status, error=self.error, journal_sha256=self.chain, revisions=list(self.revisions),
                    quality=dict(minutes=len(rows), vix_valid=len(valid),
                                 cash_valid=sum(r['cash_valid'] for r in rows), revisions=len(self.revisions),
                                 session_open=self.start <= as_of < self.end,
                                 last_vix_minute=valid[-1]['minute_ist'] if valid else None,
                                 source_age_seconds=(as_of-instant(valid[-1]['minute_end'])).total_seconds() if valid else None,
                                 full_session_complete=len(rows)==375 and len(valid)==375))
        feed['vix_window_5m'] = indicator_window(feed, as_of)
        return feed
