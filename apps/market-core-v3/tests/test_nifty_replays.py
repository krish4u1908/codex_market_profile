"""Offline integration tests using synthetic collector receipts, never market data."""
import csv
from datetime import datetime, timedelta
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parents[1]
SCRIPT = CORE / 'scripts/convert_nifty_replays.py'


def fixture(root, day, future, minutes=75):
    collector = root / 'collector'
    for kind in ('raw', 'oi', 'minute'):
        (collector / kind / day).mkdir(parents=True, exist_ok=True)
    (collector / 'metadata').mkdir(exist_ok=True)
    (collector / 'metadata' / ('startup_' + day + '.json')).write_text(json.dumps({
        'started_at': day + 'T09:00:00+05:30', 'future_oi_symbols': [future],
        'base_quote_symbols': ['NSE:NIFTY50-INDEX'], 'constituent_weights': {'A': 100},
        'finalize_delay': 8}))
    first = datetime.fromisoformat(day + 'T09:15:00+05:30')
    raw, oi, minute_rows = [], [], []
    for n in range(minutes):
        minute = first + timedelta(minutes=n)
        for second in (9, 19, 29, 39, 49, 59):
            at = (minute + timedelta(seconds=second)).isoformat()
            for symbol, price in [('NSE:NIFTY50-INDEX', 23500+n/5), (future, 23580+n/4)]:
                raw.append({'received_at': at, 'event_time': at, 'message': {
                    'symbol': symbol, 'ltp': price, 'vol_traded_today': 10000+n*600+second*10}})
        at = (minute + timedelta(seconds=55)).isoformat()
        oi.append({'source': 'future_depth', 'received_at': at, 'request_time': at,
                   'requested_symbol': future, 'response': {'d': {future: {'oi': 100000+n*100,
                   'pdoi': 95000, 'ltp': 23580+n/4, 'v': 10000+n*600}}}})
        contracts = [{'symbol': 'NSE:NIFTY50-INDEX', 'ltp': 23500+n/5}]
        for side in ('CE', 'PE'):
            for strike in range(23200, 23901, 50):
                contracts.append({'symbol': f'NSE:NIFTY26SEP{strike}{side}', 'option_type': side,
                    'strike_price': strike, 'oi': 100000+n*200, 'oich': n*200,
                    'ltp': 100+n/10, 'volume': 10000+n*500})
        oi.append({'source': 'option_chain', 'received_at': at, 'request_time': at,
            'response': {'code': 200, 'data': {'expiryData': [{'date': '29-09-2026'}],
            'indiavixData': {'symbol': 'NSE:INDIAVIX-INDEX', 'ltp': 12+n/100},
            'optionsChain': contracts}}})
        for symbol, kind, opening, close in [('NSE:A-EQ','cash',100,100+n/100),
                                            ('NSE:INDIAVIX-INDEX','vix',12,12+n/100)]:
            minute_rows.append([minute.isoformat(),symbol,kind,opening,close,100,at])
    for kind, name, rows in [('raw','events_09.jsonl',raw),('oi','oi_09.jsonl',oi)]:
        (collector/kind/day/name).write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with (collector/'minute'/day/'market_1m.csv').open('w',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['minute','symbol','instrument_class','ltp_open','ltp_close','minute_volume','last_received_time'])
        writer.writerows(minute_rows)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        cls.days=['2026-08-27','2026-09-10']
        for day, future in zip(cls.days, ['NSE:NIFTY26AUGFUT','NSE:NIFTY26SEPFUT']):
            fixture(cls.root,day,future)
        cls.config=cls.root/'config.json'
        cls.config.write_text(json.dumps(dict(version='3.0.0',instrument='NIFTY',
            collector_root=str(cls.root/'collector'),state_root=str(cls.root/'state'),
            lock_path=str(cls.root/'core.lock'),port=8923)))
        cls.output=cls.root/'output'
        result=cls.run_tool('build')
        if result.returncode: raise AssertionError(result.stdout)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    @classmethod
    def run_tool(cls, action, *extra):
        return subprocess.run([sys.executable,'-B',str(SCRIPT),action,'--core-root',str(CORE),
            '--config',str(cls.config),'--output',str(cls.output),*extra],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)

    def payload(self, day, profile='v200'):
        return json.loads(gzip.decompress((self.output/'sessions'/day/(profile+'.json.gz')).read_bytes()))

    def test_two_contracts_both_profiles_and_indicator_clocks(self):
        self.assertEqual(self.run_tool('verify').returncode,0)
        for day, future in zip(self.days,['NSE:NIFTY26AUGFUT','NSE:NIFTY26SEPFUT']):
            p=self.payload(day)
            self.assertEqual(p['futures_symbol'],future)
            self.assertEqual(p['workspace_profile'],'nifty-v200')
            self.assertTrue(p['historical_reconstruction'])
            self.assertTrue(p['decisions'])
            self.assertTrue(p['chart_inputs']['price']['rows'])
            self.assertTrue(p['chart_inputs']['option_strike_oi']['rows'])
            self.assertTrue(p['chart_inputs']['futures_volume']['rows'])
            self.assertEqual(p['option_report_inputs']['quality']['reports'],75)
            self.assertTrue(all(r['available_at']==r['source_published_at'] for r in p['indicator_inputs']['revisions']))
            self.assertTrue(all(r['origin']=='HISTORICAL_FINAL_MINUTE_SIMULATION' for r in p['indicator_inputs']['revisions']))
            self.assertEqual(self.payload(day,'v1062')['workspace_profile'],'nifty-v1062')

    def test_resume_keeps_verified_bytes(self):
        original=(self.output/'sessions'/self.days[0]/'v200.json.gz').read_bytes()
        self.assertEqual(self.run_tool('build','--dates',*self.days).returncode,0)
        self.assertEqual(original,(self.output/'sessions'/self.days[0]/'v200.json.gz').read_bytes())
        report=json.loads((self.output/'conversion-report.json').read_text())
        self.assertEqual(report['counts'],{'UNCHANGED':2})

    def test_publish_repeatable_preserves_recorded_sessions(self):
        sys.path.insert(0,str(CORE))
        from market_core.storage import PublishedStore
        from market_core.config import Config
        config=Config.read(self.config)
        store=PublishedStore(config)
        existing=self.payload(self.days[1]);existing['provenance']={'history_note':'Original recorded fixture'}
        store.publish('nifty-v200',existing,source='recorded',key='recorded-'+self.days[1])
        recorded=config.state_root/'replay/nifty-v200'/('recorded-'+self.days[1]+'.json.gz')
        original=recorded.read_bytes()
        for _ in range(2):
            result=self.run_tool('publish')
            self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(recorded.read_bytes(),original)
        self.assertEqual(len(list((config.state_root/'replay/nifty-v200').glob('rebuilt-*.json.gz'))),2)
        self.assertEqual(len(PublishedStore(config).catalog('nifty-v200')['sessions']),3)

    def test_tampered_payload_fails_before_any_publish(self):
        target=self.output/'sessions'/self.days[1]/'v200.json.gz';original=target.read_bytes()
        try:
            target.write_bytes(b'broken')
            result=self.run_tool('publish')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('checksum mismatch',result.stdout)
        finally: target.write_bytes(original)

    def test_source_change_and_incomplete_line_fail_without_overwrite(self):
        source=self.root/'collector/raw'/self.days[0]/'events_09.jsonl'
        original=source.read_bytes();stat=source.stat()
        try:
            source.write_bytes(original+b'{')
            result=self.run_tool('build','--dates',self.days[0])
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Incomplete source line', (self.output/'logs'/(self.days[0]+'.log')).read_text())
        finally:
            import os
            source.write_bytes(original);os.utime(source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertEqual(self.run_tool('verify').returncode,0)

    def test_missing_raw_and_invalid_output_are_reported(self):
        day='2026-09-09';(self.root/'collector/minute'/day).mkdir(parents=True,exist_ok=True)
        result=self.run_tool('plan','--dates',day)
        self.assertIn('MISSING_RAW_TICKS',result.stdout)
        self.assertNotEqual(self.run_tool('build','--dates',day).returncode,0)
        result=self.run_tool('build','--output',str(self.root/'collector/generated'))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('separate',result.stdout)

    def test_date_selection_does_not_silently_ignore_missing_builds(self):
        self.assertNotEqual(self.run_tool('publish','--dates','2026-09-09').returncode,0)
        result=self.run_tool('verify','--date-from','2026-09-01')
        self.assertEqual(json.loads(result.stdout)['verified_sessions'],1)


if __name__=='__main__':unittest.main(verbosity=2)
