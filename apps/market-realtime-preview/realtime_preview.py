"""Read-only display preview. No imports of an authority, strategy or broker client."""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
from pathlib import Path
import re
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit
import uuid
from zoneinfo import ZoneInfo

VERSION = '3.1.0-preview.1'
SCHEMA = 'READ_ONLY_LIVE_DISPLAY_V1'
IST = ZoneInfo('Asia/Kolkata')
INDEX = {'NIFTY': 'NSE:NIFTY50-INDEX', 'BANKNIFTY': 'NSE:NIFTYBANK-INDEX'}
VIX = 'NSE:INDIAVIX-INDEX'


def instant(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include its time zone')
    return parsed.timestamp()


def finite(value, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and (value > 0 if positive else value >= 0) else None
    except OverflowError:
        return None


def encoded(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


class DisplayTail:
    """Bounded recent history; input files are opened only in rb mode.

    Startup reads at most the last 2 MiB of each of the latest two hourly files.
    No backtest, candle finalization, OI reconstruction or signal calculation.
    """
    def __init__(self, collector_root, instrument, overrides=None):
        if instrument not in INDEX:
            raise ValueError('Unknown instrument')
        self.root, self.instrument = Path(collector_root).resolve(), instrument
        self.overrides = overrides or {}
        self.day = None
        self.futures = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.body = encoded({'schema': SCHEMA, 'version': VERSION, 'status': 'WAITING'})

    def reset(self, day, now):
        self.day, self.generation = day, uuid.uuid4().hex
        self.attached_at, self.cutoff = now, now - 90
        self.offsets, self.latest, self.bars = {}, {}, {}
        self.points = {INDEX[self.instrument]: deque(maxlen=180), VIX: deque(maxlen=180)}
        self.futures, self.metadata_checked = None, 0
        self.rejected, self.backlog = 0, False

    def metadata(self, now):
        if now - self.metadata_checked < 5:
            return
        self.metadata_checked = now
        selected, newest = None, -math.inf
        for path in self.root.glob('metadata/startup_*.json'):
            try:
                if path.stat().st_size > 1024 * 1024:
                    continue
                row = json.loads(path.read_bytes())
                started = instant(row['started_at'])
                if datetime.fromtimestamp(started, IST).date().isoformat() != self.day or started > now or started <= newest:
                    continue
                if INDEX[self.instrument] not in row.get('base_quote_symbols', []):
                    continue
                choices = [s for s in row.get('future_oi_symbols', [])
                           if re.fullmatch(r'NSE:' + self.instrument + r'\d{2}[A-Z]{3}FUT', s)]
                selected = row.get('future_symbol') or (choices[0] if len(choices) == 1 else None)
                if selected and not re.fullmatch(r'NSE:' + self.instrument + r'\d{2}[A-Z]{3}FUT', selected):
                    selected = None
                newest = started
            except (OSError, ValueError, KeyError, TypeError):
                continue
        override = self.overrides.get(self.day)
        if override and selected and override != selected:
            raise ValueError('Futures override conflicts with collector metadata')
        active = override or selected
        if self.futures and active and self.futures != active:
            self.reset(self.day, now)
        self.futures = active

    def accept(self, row, now):
        message = row.get('message')
        if not isinstance(message, dict) or message.get('type') == 'dp':
            return
        symbol = str(message.get('symbol', '')).upper()
        option = bool(re.fullmatch(r'NSE:' + self.instrument + r'\d{2}[A-Z0-9]+\d+(CE|PE)', symbol))
        if symbol not in {INDEX[self.instrument], VIX, self.futures} and not option:
            return
        received, source = instant(row['received_at']), instant(row['event_time'])
        if (row.get('timestamp_anomaly') or row.get('aggregation_status') not in (None, '', 'aggregated')
                or source > received + .5 or received > now + .5 or received < self.cutoff
                or datetime.fromtimestamp(received, IST).date().isoformat() != self.day
                or datetime.fromtimestamp(source, IST).date().isoformat() != self.day):
            self.rejected += 1
            return
        local = datetime.fromtimestamp(received, IST)
        if not (9, 15) <= (local.hour, local.minute) < (15, 30):
            return
        price = finite(message.get('ltp', message.get('last_price')), positive=True)
        if price is None:
            return
        previous = self.latest.get(symbol)
        if previous and received <= previous['received_ms'] / 1000:
            return  # Late/duplicate receipts cannot rewrite already displayed volume.
        counter = finite(message.get('vol_traded_today', message.get('volume')))
        current = dict(symbol=symbol, price=price, volume=counter,
                       received_ms=received * 1000, source_ms=source * 1000)
        self.latest[symbol] = current
        if symbol in self.points:
            points = self.points[symbol]
            if points and int(points[-1]['received_ms'] / 1000) == int(received):
                points[-1] = current  # Coalesce display points only; never a strategy input.
            else:
                points.append(current)
        if counter is not None and (symbol == self.futures or option):
            minute = int(received // 60) * 60000
            bucket = self.bars.setdefault((symbol, minute),
                dict(symbol=symbol, minute_ms=minute, volume=0, partial=False, observations=0))
            prior_counter = previous.get('volume') if previous else None
            gap = received - previous['received_ms'] / 1000 if previous else math.inf
            if prior_counter is None or counter < prior_counter or gap > 15:
                bucket['partial'] = True
            else:
                bucket['volume'] += counter - prior_counter
                bucket['observations'] += 1

    def poll(self, now=None):
        now = time.time() if now is None else now
        day = datetime.fromtimestamp(now, IST).date().isoformat()
        if self.day != day:
            self.reset(day, now)
        error = None
        try:
            self.metadata(now)
            paths = sorted((self.root / 'raw' / day).glob('events_*.jsonl'))
            # Reset all display counters on rotation/truncation; never bridge the gap.
            for path in paths:
                stat, old = path.stat(), self.offsets.get(str(path))
                if old and (old[0] != stat.st_ino or stat.st_size < old[1]):
                    self.reset(day, now)
                    self.metadata(now)
                    break
            rows, budget, self.backlog = [], 2 * 1024 * 1024, False
            for path in paths:
                stat = path.stat()
                saved = self.offsets.get(str(path))
                if saved is None:
                    start = max(0, stat.st_size - 2 * 1024 * 1024) if path in paths[-2:] else stat.st_size
                else:
                    start = saved[1]
                with path.open('rb') as handle:
                    handle.seek(start)
                    if saved is None and 0 < start < stat.st_size:
                        handle.readline()  # Startup can begin in the middle of a record.
                    offset = handle.tell()
                    while budget > 0:
                        beginning = handle.tell()
                        line = handle.readline(256 * 1024 + 1)
                        if len(line) > 256 * 1024:
                            raise ValueError('Oversized raw record')
                        if not line or not line.endswith(b'\n'):
                            offset = beginning
                            break
                        budget -= len(line)
                        offset = handle.tell()
                        try:
                            row = json.loads(line)
                            if isinstance(row, dict):
                                rows.append((instant(row['received_at']), row))
                        except (ValueError, KeyError, TypeError):
                            self.rejected += 1
                    self.offsets[str(path)] = (stat.st_ino, offset)
                    if budget <= 0 and offset < stat.st_size:
                        self.backlog = True
                if budget <= 0:
                    self.backlog = True
                    break
            for _, row in sorted(rows, key=lambda r: r[0]):
                try:
                    self.accept(row, now)
                except (ValueError, TypeError, KeyError):
                    self.rejected += 1
            self.bars = {key: value for key, value in self.bars.items() if key[1] >= (now - 600) * 1000}
            self.latest = {key: value for key, value in self.latest.items() if value['received_ms'] >= (now - 600) * 1000}
            for points in self.points.values():
                while points and points[0]['received_ms'] < (now - 120) * 1000:
                    points.popleft()
        except (OSError, ValueError) as exc:
            error = str(exc)
        payload = dict(schema=SCHEMA, version=VERSION, instrument=self.instrument, session=day,
            generation=self.generation, server_ms=now * 1000, attached_ms=self.attached_at * 1000,
            status='ERROR' if error else 'CATCHING_UP' if self.backlog else 'LIVE' if self.latest else 'WAITING',
            error=error, rejected=self.rejected, index_symbol=INDEX[self.instrument], futures_symbol=self.futures,
            latest=self.latest, prices=list(self.points[INDEX[self.instrument]]), vix=list(self.points[VIX]),
            volume_bars=list(self.bars.values()), display_only=True, owns_engine=False)
        body = encoded(payload)
        with self.lock:
            self.body = body
        return payload

    def run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(.25)


def handler_for(root, instrument, core_port, tail):
    root = Path(root).resolve()
    prefix = instrument.lower() + '-'
    profiles = [prefix + 'v1062', prefix + 'v200']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, body, status=200, content_type='application/json', headers=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            try:
                if url.path == '/workspace-config.json':
                    return self.send(encoded(dict(instrument=instrument, profiles=profiles,
                        defaultProfile=prefix + 'v200', live=True, defaultMode='live',
                        pollMilliseconds=5000, realtimePreview=True, previewVersion=VERSION)))
                if url.path == '/health':
                    return self.send(encoded(dict(status='ok', role='read-only-preview',
                        instrument=instrument, version=VERSION, owns_engine=False)))
                if url.path == '/api/display-preview':
                    with tail.lock:
                        body = tail.body
                    return self.send(body)
                if url.path.startswith('/api/'):
                    if url.path not in {'/api/health', '/api/live', '/api/catalog', '/api/replay', '/api/indicator-inputs'}:
                        return self.send(b'{"error":"Not found"}', 404)
                    if url.path != '/api/health' and parse_qs(url.query).get('profile', [''])[0] not in profiles:
                        return self.send(b'{"error":"Wrong instrument"}', 400)
                    connection = http.client.HTTPConnection('127.0.0.1', core_port, timeout=5)
                    try:
                        headers = {k: self.headers[k] for k in ('Accept-Encoding', 'If-None-Match') if self.headers.get(k)}
                        connection.request('GET', self.path, headers=headers)
                        response = connection.getresponse()
                        body = response.read()
                        headers = {k: response.getheader(k) for k in ('ETag', 'Content-Encoding') if response.getheader(k)}
                        return self.send(body, response.status, headers=headers)
                    finally:
                        connection.close()
                target = (root / (unquote(url.path).lstrip('/') or 'index.html')).resolve()
                if root not in target.parents or not target.is_file():
                    return self.send(b'{"error":"Not found"}', 404)
                return self.send(target.read_bytes(), content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
            except (BrokenPipeError, ConnectionResetError):
                pass
            except (OSError, http.client.HTTPException):
                self.send(b'{"error":"Existing core unavailable"}', 502)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    config = json.loads(args.config.read_bytes())
    if config.get('instrument') not in INDEX or not 1024 <= args.port <= 65535:
        raise ValueError('Invalid instrument or preview port')
    if args.port in {8920, 8921, 8922, 8923, int(config['port'])}:
        raise ValueError('Preview must use a separate port')
    tail = DisplayTail(config['collector_root'], config['instrument'], config.get('futures_symbols_by_session'))
    server = ThreadingHTTPServer((args.host, args.port), handler_for(args.root, config['instrument'], int(config['port']), tail))
    thread = threading.Thread(target=tail.run, daemon=True, name='display-reader')
    thread.start()
    try:
        server.serve_forever()
    finally:
        tail.stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
