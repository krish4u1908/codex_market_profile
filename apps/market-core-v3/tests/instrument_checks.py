"""Run each frozen namespace in its own process, as in production."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from market_core.config import Config, INSTRUMENTS
from market_core.projection import baseline_payload, chart_inputs, v2_payload
from market_core.runtime import Runtime
from market_core.source import SharedSource
from market_core.vendor import load

INSTRUMENT = os.environ['TEST_INSTRUMENT']
NOW = datetime(2031, 4, 7, 4, 16, 35, tzinfo=timezone.utc)


class InstrumentChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = Config(INSTRUMENT, self.root/'collector', self.root/'state', self.root/'lock')
        self.vendor = load(INSTRUMENT)
        self.future = 'NSE:' + INSTRUMENT + '31APRFUT'
        self.config.collector_root.mkdir()

    def metadata(self, day='2031-04-07', future=None):
        root = self.config.collector_root/'metadata'
        root.mkdir(exist_ok=True)
        (root/('startup_'+day+'.json')).write_text(json.dumps(dict(started_at=day+'T03:44:00Z',
            base_quote_symbols=[INSTRUMENTS[INSTRUMENT]], future_oi_symbols=[future or self.future])))

    def receipts(self):
        self.metadata()
        root = self.config.collector_root/'raw'/'2031-04-07'
        root.mkdir(parents=True)
        rows = []
        for clock, price in [('03:45:01', 24000 if INSTRUMENT=='NIFTY' else 57500), ('04:15:58', 24010 if INSTRUMENT=='NIFTY' else 57510)]:
            instant = datetime.fromisoformat('2031-04-07T'+clock+'+00:00')
            for offset, symbol, value in [(0, INSTRUMENTS[INSTRUMENT], price), (1, self.future, price+10)]:
                t = (instant+timedelta(seconds=offset)).isoformat()
                rows.append(dict(received_at=t,event_time=t,message=dict(symbol=symbol,ltp=value)))
        path = root/'events_09.jsonl'
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return path

    def test_ingestion_recovery_partial_receipt_and_rollover(self):
        path = self.receipts()
        original = path.read_bytes()
        source = SharedSource(self.config, self.vendor)
        with patch('socket.socket', side_effect=AssertionError('Collector must be read from disk')):
            first = source.snapshot(NOW)
            self.assertEqual(first['observations'][-1]['basis'], 10)
            self.assertEqual(first['observations'][-1]['synchronization_age_ms'], 1000)
            path.write_bytes(original+b'{"received_at":')
            second = source.snapshot(NOW)
            self.assertEqual(first['observations'], second['observations'])
            path.write_bytes(original)
            recovered = SharedSource(self.config, self.vendor).snapshot(NOW)
            self.assertEqual(recovered['observations'], first['observations'])
            self.assertTrue((self.config.state_root/'runtime/engine/2031-04-07/checkpoint.json').exists())
            self.metadata('2031-04-08')
            rolled = source.snapshot(NOW+timedelta(days=1))
            self.assertEqual(rolled['session'], '2031-04-08')
            self.assertEqual(rolled['observations'], [])
        self.assertEqual(original, path.read_bytes())

    def test_metadata_waits_then_retries_and_failures_latch(self):
        source = SharedSource(self.config, self.vendor)
        with self.assertRaisesRegex(ValueError, 'metadata'):
            source.snapshot(NOW)
        self.receipts()
        source.snapshot(NOW)
        with patch.object(source.tail, 'poll', side_effect=ValueError('bad receipt')) as poll:
            with self.assertRaises(ValueError): source.snapshot(NOW)
            with self.assertRaisesRegex(RuntimeError, 'recovery required'): source.snapshot(NOW)
            self.assertEqual(poll.call_count, 1)

    def test_single_authority_native_v2_equivalence_and_state_lock(self):
        self.receipts()
        before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.config.collector_root.rglob('*') if p.is_file()}
        runtime = Runtime(self.config)
        self.addCleanup(runtime.close)
        with self.assertRaisesRegex(RuntimeError, 'Another core'):
            Runtime(self.config)
        with patch('live_context.time.time', return_value=NOW.timestamp()):
            runtime.tick(NOW)
            self.assertIsNone(runtime.error)
            self.assertIsNone(runtime.context_error)
            snapshot = runtime.source.authority.browser_snapshot(observation_limit=None)
            native = self.vendor.LiveContext(self.root/'native-comparison', str(self.config.collector_root))
            try:
                native.ingest(snapshot)
                expected = list(native.db.execute('SELECT day,cutoff,body FROM decisions'))
                actual = list(runtime.context.db.execute('SELECT day,cutoff,body FROM decisions'))
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), 1)
            finally:
                native.close()
        self.assertIsNone(runtime.context.source)
        self.assertIsNone(runtime.context.thread)
        v1 = json.loads(runtime.store.live(self.config.profile('v1062'))[0])
        v2 = json.loads(runtime.store.live(self.config.profile('v200'))[0])
        self.assertEqual(v1['price'], v2['chart_inputs']['price'])
        self.assertEqual(v1['intraday_inventory'], v2['chart_inputs']['intraday_inventory'])
        self.assertEqual(v2['decisions'], [json.loads(actual[0][2])])
        self.assertEqual(v1['price']['rows'][-1][v1['price']['fields'].index('age')], 1000)
        self.assertEqual(before, {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})
        # Display envelopes keep supplied direction publications byte-for-value.
        call = {'decision_id':'retained-call','published_at':'2031-04-07T04:16:09Z','input_cutoff':'2031-04-07T04:16:00Z','direction':'UP'}
        runtime.source.authority.direction_history.append(call)
        inputs = chart_inputs(runtime.source,snapshot,self.config)
        projected = baseline_payload(runtime.source,snapshot,self.config,inputs)['directional_prediction']
        self.assertEqual(dict(zip(projected['fields'],projected['rows'][-1])),call)
        self.assertTrue(runtime.store.catalog(self.config.profile('v200'))['sessions'])
        # A new day waiting for metadata must not retain yesterday as live.
        runtime.tick(NOW+timedelta(days=1))
        self.assertIsNone(runtime.store.live(self.config.profile('v1062')))


if __name__=='__main__': unittest.main(verbosity=2)
