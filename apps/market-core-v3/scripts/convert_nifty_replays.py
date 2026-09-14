#!/usr/bin/env python3
"""Build NIFTY V1/V2 historical replays offline from the installed frozen core.

No broker calls, service control, live authorities or writes to collector files.
Each date runs in a separate process; existing recorded replays are preserved.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import date, datetime, timedelta
import fcntl
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

VERSION = '1.0.0'
IST = ZoneInfo('Asia/Kolkata')
DAY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
FUTURE = re.compile(r'^NSE:NIFTY\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)FUT$')
HERE = Path(__file__).resolve().parent


def encode(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':')).encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    from market_core.storage import atomic_write
    atomic_write(path, encode(value) + b'\n')


def checked_day(value):
    if not DAY.fullmatch(value) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Expected YYYY-MM-DD: ' + value)
    return value


def load_config(args):
    root = args.core_root.resolve(strict=True)
    if not (root / 'market_core/config.py').is_file():
        raise ValueError('--core-root must contain market_core and vendor directories')
    sys.path.insert(0, str(root))
    from market_core.config import Config
    config = Config.read(args.config)
    if config.instrument != 'NIFTY':
        raise ValueError('This utility only accepts a NIFTY configuration')
    if args.futures_map:
        overrides = dict(config.futures_symbols_by_session or {})
        overrides.update(json.loads(args.futures_map.read_text()))
        config = replace(config, futures_symbols_by_session=overrides)
        config.validate()
    return config


def relevant_metadata(root, day):
    result = []
    for path in sorted((root / 'metadata').glob('startup_*.json')):
        try:
            row = json.loads(path.read_bytes())
            instant = datetime.fromisoformat(row['started_at'].replace('Z', '+00:00'))
            if instant.tzinfo and instant.astimezone(IST).date().isoformat() == day:
                result.append((path, row))
        except (ValueError, KeyError, TypeError):
            continue
    return result


def inspect_day(config, day):
    checked_day(day)
    root = config.collector_root
    raw = sorted((root / 'raw' / day).glob('events_*.jsonl'))
    oi = sorted((root / 'oi' / day).glob('oi_*.jsonl'))
    minute = root / 'minute' / day / 'market_1m.csv'
    metadata = relevant_metadata(root, day)
    found = {s for _, row in metadata for s in row.get('future_oi_symbols', [])
             if isinstance(s, str) and FUTURE.fullmatch(s)}
    override = (config.futures_symbols_by_session or {}).get(day)
    future = override or (next(iter(found)) if len(found) == 1 else None)
    reasons = []
    if day >= datetime.now(IST).date().isoformat(): reasons.append('NOT_A_COMPLETED_HISTORICAL_DATE')
    if not any(p.stat().st_size for p in raw): reasons.append('MISSING_RAW_TICKS')
    if not any(p.stat().st_size for p in oi): reasons.append('MISSING_OI_REPORTS')
    if override and found and override not in found: reasons.append('FUTURES_OVERRIDE_CONFLICTS_WITH_METADATA')
    if future is None: reasons.append('FUTURES_IDENTITY_MISSING_OR_AMBIGUOUS: provide --futures-map')
    paths = sorted(set(raw + oi + [p for p, _ in metadata] + ([minute] if minute.is_file() else [])))
    return dict(session=day, eligible=not reasons, reasons=reasons, futures_symbol=future,
                raw_files=len(raw), oi_files=len(oi), minute_file=minute.is_file(),
                bytes=sum(p.stat().st_size for p in paths)), paths


def discover(config, args):
    if args.dates:
        days = sorted({checked_day(d) for d in args.dates})
    else:
        days = sorted({p.name for kind in ('raw', 'oi', 'minute')
                       for p in (config.collector_root / kind).glob('*')
                       if p.is_dir() and DAY.fullmatch(p.name)})
    if args.date_from: days = [d for d in days if d >= checked_day(args.date_from)]
    if args.date_to: days = [d for d in days if d <= checked_day(args.date_to)]
    return [inspect_day(config, d)[0] for d in days]


def freeze(root, paths):
    result = {}
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Unsafe source path: ' + str(path))
        before = path.stat()
        digest = sha(path)
        after = path.stat()
        signature = lambda s: (s.st_ino, s.st_size, s.st_mtime_ns)
        if signature(before) != signature(after): raise ValueError('Source changed while reading: ' + str(path))
        if after.st_size and path.suffix in ('.jsonl', '.csv'):
            with path.open('rb') as handle:
                handle.seek(-1, 2)
                if handle.read(1) != b'\n': raise ValueError('Incomplete source line: ' + str(path))
        result[path.relative_to(root).as_posix()] = dict(sha256=digest, size=after.st_size,
                                                       mtime_ns=after.st_mtime_ns, inode=after.st_ino)
    return result


def runtime_hash(core):
    paths = [core / 'VENDOR_MANIFEST.json', *sorted((core / 'market_core').glob('*.py')),
             core / 'vendor/nifty/analyze.py', *sorted((core / 'vendor/nifty/v2_engine').rglob('*.py')),
             HERE / 'convert_nifty_replays.py', HERE / 'replay_v2.py']
    return hashlib.sha256(encode([(str(p.relative_to(core)) if p.is_relative_to(core) else p.name, sha(p))
                                 for p in paths])).hexdigest()


def output_root(args, config):
    if not args.output: raise ValueError('--output is required for this action')
    output = args.output.resolve()
    for protected in (config.collector_root, config.state_root, args.core_root.resolve()):
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError('Build output must be separate from collector, installed core, and live state')
    return output


def historical_indicator_inputs(config, day, stage):
    """Final archived minutes with explicitly simulated, not observed, availability."""
    from market_core.indicator_inputs import IndicatorInputs, instant
    reader = IndicatorInputs(config, day, journal_root=stage / 'indicator-journal')
    feed = reader.poll()
    if feed['status'] != 'AVAILABLE':
        return None, feed.get('error') or 'Cash/VIX source unavailable'
    rows = [dict(r, available_at=r['source_published_at'],
                 origin='HISTORICAL_FINAL_MINUTE_SIMULATION') for r in feed['revisions']]
    completed = (instant(feed['session_end']) + timedelta(seconds=8)).isoformat()
    feed.update(revisions=rows, journal_sha256=None,
                as_of=max([completed, *(r['available_at'] for r in rows)], key=instant),
                historical_reconstruction=True,
                availability_clock='SIMULATED_MINUTE_END_PLUS_FINALIZE_DELAY_OR_LATER_SOURCE_RECEIPT',
                history_note='Final archived minute values; original revisions and first-observed GUI times are unavailable.')
    feed.pop('vix_window_5m', None)
    feed['quality']['session_open'] = False
    feed['quality']['source_age_seconds'] = None
    return feed, None


def verify_session(directory):
    from market_core.migration import validate_import
    from market_core.config import Config
    report = json.loads((directory / 'result.json').read_text())
    day = checked_day(report['session'])
    dummy = Config('NIFTY', Path('/unused-collector'), Path('/unused-state'), Path('/unused-lock'))
    for profile in ('v1062', 'v200'):
        path = directory / (profile + '.json.gz')
        if path.is_symlink() or sha(path) != report['payload_sha256'][profile]:
            raise ValueError('Replay checksum mismatch: ' + str(path))
        payload = json.loads(gzip.decompress(path.read_bytes()))
        validate_import(payload, dummy, profile)
        if payload['session'] != day or not payload.get('historical_reconstruction'):
            raise ValueError('Replay identity or reconstruction label mismatch')
    return report


def build_one(args, config, day):
    from market_core.vendor import load
    from market_core.storage import atomic_write
    from market_core.option_reports import OptionReportReader
    from replay_v2 import build_gui
    plan, paths = inspect_day(config, day)
    if not plan['eligible']: raise ValueError('; '.join(plan['reasons']))
    output = output_root(args, config)
    destination = output / 'sessions' / day
    original = freeze(config.collector_root, paths)
    runtime = runtime_hash(args.core_root.resolve())
    if destination.exists():
        prior = verify_session(destination)
        if prior['source_files'] != original or prior['runtime_sha256'] != runtime:
            raise ValueError('Existing build differs from source/runtime; use a fresh --output directory')
        return dict(prior, status='UNCHANGED')
    vendor = load('NIFTY')
    from v2_engine.new_divergence.contracts import EngineConfig, EventKind
    from v2_engine.new_divergence.cash_samples import generate_session_sample
    analysis = importlib.import_module('analyze')
    predictor = importlib.import_module('v2_engine.new_divergence.directional_prediction')
    parsed = date.fromisoformat(day)
    engine_config = EngineConfig()
    start = vendor.clock.session_instant(parsed, engine_config.session_start)
    end = vendor.clock.session_instant(parsed, engine_config.session_end)
    tail = vendor.LiveCollectorTail(config.collector_root, parsed, futures_symbol=plan['futures_symbol'])
    events, offsets = tail.poll()
    if any(r['offset'] != original[name]['size'] for name, r in offsets.items()):
        raise ValueError('Source files were not fully consumed')
    events = [e for e in events if start <= e.receipt_timestamp <= end]
    counts = Counter(e.kind.value for e in events)
    for kind in (EventKind.INDEX_TICK, EventKind.FUTURES_TICK, EventKind.FUTURES_OI, EventKind.OPTION_PRESSURE):
        if not any(e.kind == kind for e in events): raise ValueError('No eligible ' + kind.value + ' events')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='build-' + day + '-', dir=output) as temporary:
        stage = Path(temporary)
        run = vendor.output.publish_run(stage / 'runs', parsed, events, engine_config,
                    source={'kind':'HISTORICAL_RAW_RECONSTRUCTION', 'files':original,
                            'futures_symbol':plan['futures_symbol']}, finalize_at=end)
        del events
        warnings = []
        if plan['minute_file']:
            try:
                generate_session_sample(config.collector_root, stage / 'runs', parsed)
            except ValueError as exc:
                if str(exc) != 'market_1m.csv contains no cash-constituent symbols': raise
                warnings.append(str(exc))
        else: warnings.append('Minute CSV absent: Cash/VIX and their ribbon remain unavailable')
        baseline = vendor.projection.session_payload(run, {'intraday':[day]}, direction_strategy='corrected')
        v2, coverage = build_gui(baseline, analysis, predictor)
        offline = replace(config, state_root=stage / 'offline-state', lock_path=stage / 'unused.lock')
        quotes = OptionReportReader(offline, day).poll()
        if quotes['quality']['rejected_lines']: raise ValueError('Option-report parser rejected source lines')
        feed, feed_error = historical_indicator_inputs(offline, day, stage) if plan['minute_file'] else (None, None)
        if feed_error: warnings.append(feed_error)
        note = ('Historical reconstruction from raw NIFTY receipts. Reference calls use simulated completed-minute +8s publication; '
                'these are not the originally recorded live calls. Cash/VIX uses final archived minutes with simulated availability. '
                'Prior-day VPOC scopes are not reconstructed.')
        common = dict(instrument='NIFTY', baseline_version='1.0.62', historical_reconstruction=True,
                      option_report_inputs=quotes, provenance={'source':'HISTORICAL_RAW_RECONSTRUCTION', 'history_note':note})
        baseline.update(common, workspace_profile='nifty-v1062')
        v2.update(common, workspace_profile='nifty-v200', chart_inputs=baseline)
        if feed:
            baseline['indicator_inputs'] = feed
            v2['indicator_inputs'] = feed
        # Both profile envelopes share the same raw-derived chart history.
        staged = stage / 'session'; staged.mkdir()
        hashes = {}
        for profile, payload in [('v1062', baseline), ('v200', v2)]:
            data = gzip.compress(encode(payload), compresslevel=6, mtime=0)
            atomic_write(staged / (profile + '.json.gz'), data)
            hashes[profile] = hashlib.sha256(data).hexdigest()
        after_plan, after_paths = inspect_day(config, day)
        if after_plan != plan or after_paths != paths or freeze(config.collector_root, paths) != original:
            raise ValueError('Source changed during conversion; replay was not published')
        if runtime_hash(args.core_root.resolve()) != runtime:
            raise ValueError('Core or converter changed during conversion; replay was not published')
        report = dict(version=VERSION, session=day, status='BUILT', source_files=original,
                      runtime_sha256=runtime, futures_symbol=plan['futures_symbol'], event_counts=dict(counts),
                      coverage=coverage, option_reports=quotes['quality'],
                      indicator_quality=feed['quality'] if feed else None,
                      warnings=warnings + coverage.get('warnings', []), payload_sha256=hashes,
                      publication_clock='HISTORICAL_COMPLETED_MINUTE_PLUS_8_SECONDS_SIMULATION')
        write(staged / 'result.json', report)
        verify_session(staged)
        staged.rename(destination)
    return report


def batch(args, config):
    output = output_root(args, config)
    output.mkdir(parents=True, exist_ok=True)
    rows = discover(config, args)
    report = dict(version=VERSION, source=str(config.collector_root), sessions=[])
    (output / 'logs').mkdir(exist_ok=True)
    with (output / '.build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for row in rows:
            day = row['session']
            if not row['eligible']:
                result = dict(row, status='SKIPPED')
            else:
                print('Converting ' + day + ' [' + str(row['futures_symbol']) + ']', flush=True)
                command = [sys.executable, '-B', str(Path(__file__).resolve()), '_one',
                           '--core-root', str(args.core_root.resolve()), '--config', str(args.config.resolve()),
                           '--output', str(output), '--dates', day]
                if args.futures_map: command += ['--futures-map', str(args.futures_map.resolve())]
                log = output / 'logs' / (day + '.log')
                existed = (output / 'sessions' / day).exists()
                with log.open('w') as handle:
                    completed = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT)
                if completed.returncode:
                    result = dict(row, status='FAILED', log=str(log), error=log.read_text()[-2000:])
                else:
                    built = verify_session(output / 'sessions' / day)
                    result = dict(row, status='UNCHANGED' if existed else 'BUILT', decisions=built['coverage']['decisions'],
                                  complete_decisions=built['coverage']['complete_decisions'],
                                  option_reports=built['option_reports']['reports'], warnings=built['warnings'])
            report['sessions'].append(result)
            report['counts'] = dict(Counter(r['status'] for r in report['sessions']))
            write(output / 'conversion-report.json', report)
            print(day + ': ' + result['status'], flush=True)
    print(json.dumps(dict(report=str(output / 'conversion-report.json'), counts=report.get('counts', {})), indent=2))
    if not rows: write(output / 'conversion-report.json', report)
    return 2 if (any(r['status'] == 'FAILED' for r in report['sessions']) or
                 not any(r['status'] in ('BUILT', 'UNCHANGED') for r in report['sessions'])) else 0


def selected_builds(args, config):
    directories = sorted((output_root(args, config) / 'sessions').glob('????-??-??'))
    if args.dates:
        requested = {checked_day(d) for d in args.dates}
        directories = [p for p in directories if p.name in requested]
        missing = requested - {p.name for p in directories}
        if missing: raise ValueError('Requested sessions have no build: ' + ', '.join(sorted(missing)))
    if args.date_from: directories = [p for p in directories if p.name >= checked_day(args.date_from)]
    if args.date_to: directories = [p for p in directories if p.name <= checked_day(args.date_to)]
    if not directories: raise ValueError('No replay builds match the requested dates')
    return directories


def publish(args, config):
    from market_core.storage import PublishedStore
    output = output_root(args, config)
    directories = selected_builds(args, config)
    reports = [(p, verify_session(p)) for p in directories]
    lock_root = config.state_root / 'replay'; lock_root.mkdir(parents=True, exist_ok=True)
    installed = []
    with (lock_root / '.nifty-import.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = PublishedStore(config)
        for directory, report in reports:
            for profile in ('v1062', 'v200'):
                payload = json.loads(gzip.decompress((directory / (profile + '.json.gz')).read_bytes()))
                name = config.profile(profile)
                # Content-addressed names cannot overwrite a recorded live session.
                key = 'rebuilt-' + report['session'] + '-' + report['payload_sha256'][profile][:12]
                target = lock_root / name / (key + '.json.gz')
                if target.exists():
                    if json.loads(gzip.decompress(target.read_bytes())) != payload:
                        raise ValueError('An existing replay key has different content')
                store.publish(name, payload, source='rebuilt', key=key)
                installed.append(dict(profile=name, key=key, session=report['session']))
        write(output / 'publish-report.json', {'installed':installed, 'service_restarts':[],
              'catalog_refresh':'Restart nifty-core.service once when ready, or use Open session immediately.'})
    print(json.dumps({'installed':len(installed), 'sessions':len(reports),
                      'report':str(output / 'publish-report.json'), 'service_restarts':[],
                      'next':'Existing cores cache the catalog. Restart only nifty-core.service to discover new files.'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'build', 'verify', 'publish', '_one'))
    parser.add_argument('--core-root', type=Path, default=Path('/opt/market-workspace-v3/current/core'))
    parser.add_argument('--config', type=Path, default=Path('/opt/market-workspace-v3/current/config/nifty.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dates', nargs='+')
    parser.add_argument('--date-from')
    parser.add_argument('--date-to')
    parser.add_argument('--futures-map', type=Path, help='Optional JSON mapping YYYY-MM-DD to exact NIFTY futures symbol')
    args = parser.parse_args()
    config = load_config(args)
    if args.action == 'plan':
        rows = discover(config, args)
        print(json.dumps({'source':str(config.collector_root), 'sessions':rows,
                          'eligible':sum(r['eligible'] for r in rows), 'total':len(rows)}, indent=2))
    elif args.action == 'build': return batch(args, config)
    elif args.action == '_one':
        if not args.dates or len(args.dates) != 1: raise ValueError('Internal worker requires one date')
        result = build_one(args, config, args.dates[0])
        print(json.dumps({'session':result['session'], 'status':result['status']}))
    elif args.action == 'verify':
        rows = [verify_session(p) for p in selected_builds(args, config)]
        print(json.dumps({'verified_sessions':len(rows), 'profiles':['nifty-v1062', 'nifty-v200']}))
    else: publish(args, config)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
