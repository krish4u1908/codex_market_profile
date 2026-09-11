import concurrent.futures
from datetime import datetime, timedelta
import gzip
import hashlib
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from realtime_preview import DisplayTail, INDEX, VIX, encoded, handler_for, instant
from install_preview import unit_text, verify_bundle
import install_preview as installer
import build_preview as packager

DAY = '2026-09-11'


def stamp(time_string):
    return f'{DAY}T{time_string}+05:30'


def row(symbol, when, price=24000, volume=None, **extra):
    message = dict(symbol=symbol, ltp=price, type='sf')
    if volume is not None:
        message['vol_traded_today'] = volume
    return dict(received_at=stamp(when), event_time=stamp(when), message=message,
                aggregation_status='aggregated', **extra)


class PreviewTests(unittest.TestCase):
    def setup_reader(self, root, instrument='NIFTY'):
        future = f'NSE:{instrument}26SEPFUT'
        metadata = root / 'metadata'
        metadata.mkdir(exist_ok=True)
        (metadata / 'startup_test.json').write_bytes(encoded(dict(started_at=stamp('09:00:00'),
            future_symbol=future, future_oi_symbols=[future], base_quote_symbols=[INDEX[instrument], VIX])))
        raw = root / 'raw' / DAY / 'events_10.jsonl'
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.touch()
        return DisplayTail(root, instrument), raw, future

    def append(self, path, *rows):
        with path.open('ab') as handle:
            for r in rows:
                handle.write(encoded(r) + b'\n')

    def test_complete_line_retry_and_no_source_writes_for_both_instruments(self):
        for instrument in INDEX:
            with self.subTest(instrument=instrument), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                reader, raw, future = self.setup_reader(root, instrument)
                self.append(raw, row(INDEX[instrument], '10:00:00'), row(future, '10:00:00', volume=100))
                fragment = encoded(row(future, '10:00:01', volume=125))
                with raw.open('ab') as handle:
                    handle.write(fragment[:25])
                before = raw.read_bytes()
                first = reader.poll(instant(stamp('10:00:02')))
                self.assertEqual(first['latest'][future]['volume'], 100)
                self.assertEqual(raw.read_bytes(), before)
                with raw.open('ab') as handle:
                    handle.write(fragment[25:] + b'\n')
                before = raw.read_bytes()
                second = reader.poll(instant(stamp('10:00:03')))
                self.assertEqual(second['latest'][future]['volume'], 125)
                self.assertEqual(second['volume_bars'][0]['volume'], 25)
                self.assertTrue(second['volume_bars'][0]['partial'])
                self.assertEqual(raw.read_bytes(), before)
                self.assertFalse(second['owns_engine'])
                self.assertTrue(second['display_only'])

    def test_counter_reset_gap_duplicates_and_unrelated_options_do_not_create_spikes(self):
        with tempfile.TemporaryDirectory() as temporary:
            reader, raw, future = self.setup_reader(Path(temporary))
            self.append(raw, row(future, '10:00:00', volume=100), row(future, '10:00:01', volume=125),
                row(future, '10:00:01', volume=200), row(future, '10:00:02', volume=2),
                row(future, '10:00:03', volume=5), row(future, '10:00:40', volume=2000),
                row('NSE:BANKNIFTY26SEP56000CE', '10:00:40', volume=99999),
                row(VIX, '10:00:40', price=12.3, timestamp_anomaly=True))
            result = reader.poll(instant(stamp('10:00:41')))
            self.assertEqual(result['volume_bars'][0]['volume'], 28)
            self.assertEqual(set(result['latest']), {future})
            self.assertTrue(result['volume_bars'][0]['partial'])
            self.assertEqual(result['rejected'], 1)

    def test_truncation_and_next_day_reset_the_display_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            reader, raw, future = self.setup_reader(Path(temporary))
            self.append(raw, row(future, '10:00:00', volume=9000), row(future, '10:00:01', volume=9020))
            first = reader.poll(instant(stamp('10:00:02')))
            raw.write_bytes(encoded(row(future, '10:00:03', volume=700)) + b'\n')
            second = reader.poll(instant(stamp('10:00:04')))
            self.assertNotEqual(second['generation'], first['generation'])
            self.assertEqual(second['volume_bars'][0]['volume'], 0)
            third = reader.poll(instant('2026-09-12T09:15:01+05:30'))
            self.assertNotEqual(third['generation'], second['generation'])
            self.assertEqual(third['latest'], {})
            self.assertEqual(third['volume_bars'], [])

    def test_recent_tail_does_not_scan_old_session_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            reader, raw, future = self.setup_reader(Path(temporary))
            old = raw.with_name('events_09.jsonl')
            old.write_bytes(b'x' * (3 * 1024 * 1024) + b'\n')
            self.append(raw, row(future, '10:00:00', volume=100))
            # Three hourly files: the oldest is skipped entirely.
            older = raw.with_name('events_08.jsonl')
            older.write_bytes(b'old recording without a newline')
            result = reader.poll(instant(stamp('10:00:01')))
            self.assertEqual(reader.offsets[str(older)][1], older.stat().st_size)
            self.assertEqual(result['latest'][future]['volume'], 100)

    def serve(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_confirmed_payload_bytes_etag_and_gzip_are_forwarded_without_recalculation(self):
        body = gzip.compress(encoded({'decisions': [{'ratio': 4.17, 'context_published_at': 'retained'}]}))
        class Core(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                if self.headers.get('If-None-Match') == '"original"':
                    self.send_response(304); self.send_header('ETag', '"original"'); self.end_headers(); return
                self.send_response(200)
                self.send_header('ETag', '"original"')
                self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
        core = self.serve(Core)
        for instrument in INDEX:
            with self.subTest(instrument=instrument), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); (root / 'index.html').write_text('preview')
                tail = DisplayTail(root, instrument)
                front = self.serve(handler_for(root, instrument, core.server_port, tail))
                url = f'http://127.0.0.1:{front.server_port}/api/live?profile={instrument.lower()}-v200'
                with urlopen(Request(url, headers={'Accept-Encoding': 'gzip'})) as response:
                    self.assertEqual(response.read(), body)
                    self.assertEqual(response.headers['ETag'], '"original"')
                    self.assertEqual(response.headers['Content-Encoding'], 'gzip')
                with self.assertRaises(HTTPError) as result:
                    urlopen(Request(url, headers={'If-None-Match': '"original"'}))
                self.assertEqual(result.exception.code, 304)
                with self.assertRaises(HTTPError) as result:
                    urlopen(url.replace(instrument.lower()+'-v200', 'other-v200'))
                self.assertEqual(result.exception.code, 400)

    def test_slow_core_request_does_not_block_display_endpoint(self):
        entered, release = threading.Event(), threading.Event()
        class SlowCore(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                entered.set(); release.wait(3)
                self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
        core = self.serve(SlowCore)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); tail = DisplayTail(root, 'NIFTY')
            tail.body = b'{"independent":true}'
            front = self.serve(handler_for(root, 'NIFTY', core.server_port, tail))
            base = f'http://127.0.0.1:{front.server_port}'
            with concurrent.futures.ThreadPoolExecutor() as pool:
                pending = pool.submit(lambda: urlopen(base + '/api/live?profile=nifty-v200').read())
                try:
                    self.assertTrue(entered.wait(2))
                    with urlopen(base + '/api/display-preview', timeout=1) as response:
                        self.assertEqual(json.load(response), {'independent': True})
                    self.assertFalse(pending.done())
                finally:
                    release.set()
                pending.result(timeout=2)

    def test_service_has_no_authority_and_read_only_filesystem(self):
        text = unit_text('NIFTY', 'bankadmin', Path('/opt/preview'), Path('/opt/existing/config.json'),
                         Path('/opt/collector'), 8931, '127.0.0.1')
        self.assertIn('ProtectSystem=strict', text)
        self.assertIn('ProtectHome=read-only', text)
        self.assertIn('CPUQuota=20%', text)
        self.assertNotIn('market_core.server', text)
        self.assertNotIn('ReadWritePaths', text)
        self.assertNotIn('Requires=', text)
        with self.assertRaises(ValueError):
            unit_text('NIFTY', 'root', Path('/a'), Path('/b'), Path('/c'), 8931, '127.0.0.1')

    def test_package_checks_detect_extra_files_and_changed_gui(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'gui').mkdir()
            release = root / 'gui/gui-release.json'
            release.write_bytes(b'{"version":"3.1.0-preview.1"}')
            manifest = {'version': '3.1.0-preview.1', 'files': [{'path': 'gui/gui-release.json',
                'sha256': hashlib.sha256(release.read_bytes()).hexdigest()}]}
            (root / 'PREVIEW-MANIFEST.json').write_bytes(encoded(manifest))
            self.assertEqual(verify_bundle(root), root)
            (root / 'extra.zip').write_text('wrapper copied into package')
            with self.assertRaisesRegex(ValueError, 'empty directory'):
                verify_bundle(root)
            (root / 'extra.zip').unlink()
            release.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify_bundle(root)

    def test_package_excludes_local_imported_recordings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); gui=root/'gui-source'; (gui/'dist/data/nifty-v200').mkdir(parents=True)
            (gui/'dist/index.html').write_text('preview')
            (gui/'dist/gui-release.json').write_text('{"version":"3.1.0-preview.1"}')
            (gui/'dist/data/nifty-v200/catalog.json').write_text('{"private":true}')
            (gui/'dist/data/nifty-v200/session.json.gz').write_bytes(b'private recording')
            output=root/'preview.zip'
            with patch.object(packager, 'GUI', gui):
                packager.build(output)
            with zipfile.ZipFile(output) as archive:
                self.assertFalse(any('/data/' in name or name.endswith('.gz') for name in archive.namelist()))
                archive.extractall(root/'extracted')
            verify_bundle(root/'extracted/market-workspace-realtime-preview')

    def install_fixture(self, root):
        package = root / 'bundle'; package.mkdir()
        (package / 'test.txt').write_text('new preview files')
        units = root / 'units'; units.mkdir()
        states = {u: {'MainPID': str(i+1), 'ActiveState': 'active'} for i,u in enumerate(installer.ORIGINAL)}
        checked = dict(destination=str(root / 'preview' / installer.VERSION), package=str(package),
            preview_units={name: 'new preview unit' for name in installer.PREVIEW},
            configs={'NIFTY': {'port':8931}, 'BANKNIFTY': {'port':8930}},
            existing_units=states, config_hashes={})
        return checked, units, states

    def test_install_starts_only_preview_services_and_preserves_existing_pids(self):
        with tempfile.TemporaryDirectory() as temporary:
            checked, units, states = self.install_fixture(Path(temporary))
            def health(url, **_):
                return io.BytesIO(encoded(dict(version=installer.VERSION, owns_engine=False,
                    instrument='NIFTY' if ':8931/' in url else 'BANKNIFTY')))
            with patch.object(installer, 'UNIT_DIRECTORY', units), patch.object(installer, 'check', return_value=checked), \
                 patch.object(installer.os, 'geteuid', return_value=0), patch.object(installer, 'systemctl') as calls, \
                 patch.object(installer, 'unit_state', side_effect=lambda name: states.get(name, {'ActiveState':'active'})), \
                 patch.object(installer, 'urlopen', side_effect=health):
                result = installer.apply(None)
                self.assertEqual(result['original_pids'], {u:s['MainPID'] for u,s in states.items()})
                self.assertEqual([c.args for c in calls.call_args_list], [('daemon-reload',), ('enable','--now',*installer.PREVIEW)])
                self.assertEqual(set(p.name for p in units.iterdir()), set(installer.PREVIEW))

    def test_failed_install_rolls_back_only_owned_preview_paths_and_units(self):
        with tempfile.TemporaryDirectory() as temporary:
            checked, units, states = self.install_fixture(Path(temporary))
            with patch.object(installer, 'UNIT_DIRECTORY', units), patch.object(installer, 'check', return_value=checked), \
                 patch.object(installer.os, 'geteuid', return_value=0), patch.object(installer, 'systemctl'), \
                 patch.object(installer, 'unit_state', return_value={'ActiveState':'failed'}), \
                 patch.object(installer.subprocess, 'run') as rollback:
                with self.assertRaisesRegex(ValueError, 'did not start'):
                    installer.apply(None)
                self.assertFalse(Path(checked['destination']).exists())
                self.assertEqual(list(units.iterdir()), [])
                for call in rollback.call_args_list:
                    self.assertFalse(set(call.args[0]) & set(installer.ORIGINAL))
                # A destination created by another process after check is never removed.
                target = Path(checked['destination']); target.mkdir()
                (target/'keep.txt').write_text('another installation')
                with self.assertRaises(FileExistsError):
                    installer.apply(None)
                self.assertTrue((target/'keep.txt').exists())


if __name__ == '__main__':
    unittest.main()
