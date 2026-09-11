import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from market_core.config import Config
from market_core.indicator_inputs import IndicatorInputs, indicator_window, latest_minutes, instant

DAY = '2031-04-07'


class InputTests(unittest.TestCase):
    def setup_source(self, root, instrument='NIFTY'):
        config = Config(instrument, root/'collector', root/'state', root/'lock')
        (config.collector_root/'metadata').mkdir(parents=True)
        metadata = {'started_at':DAY+'T09:00:00+05:30', 'constituent_weights':{'A':60,'B':40},
                    'base_quote_symbols':['NSE:NIFTY50-INDEX' if instrument=='NIFTY' else 'NSE:NIFTYBANK-INDEX']}
        (config.collector_root/'metadata/startup_test.json').write_text(json.dumps(metadata))
        source = config.collector_root/'minute'/DAY/'market_1m.csv'
        source.parent.mkdir(parents=True)
        return config, source

    def write(self, source, omit=(), partial=(), vix_override=None, start='09:45:00', count=5):
        rows=[]; first=instant(DAY+'T'+start+'+05:30')
        for i in range(count):
            if i in omit: continue
            minute=first+timedelta(minutes=i)
            for symbol, kind, opening, close in [('NSE:A-EQ','cash',100,100+i),
                ('NSE:B-EQ','cash',200,200+i),('NSE:INDIAVIX-INDEX','vix',12,(vix_override or {}).get(i,12+i/100))]:
                if i in partial and symbol=='NSE:B-EQ':continue
                rows.append([minute.isoformat(),symbol,kind,opening,close,0,(minute+timedelta(seconds=59)).isoformat()])
        with source.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['minute','symbol','instrument_class','ltp_open','ltp_close','minute_volume','last_received_time']);writer.writerows(rows)

    def test_late_empty_minute_recovers_but_is_not_known_early_for_both_instruments(self):
        for instrument in ('NIFTY','BANKNIFTY'):
            with self.subTest(instrument=instrument), tempfile.TemporaryDirectory() as tmp:
                config, source=self.setup_source(Path(tmp),instrument)
                self.write(source,omit=(2,)); reader=IndicatorInputs(config,DAY)
                first=reader.poll(DAY+'T09:50:08.100000+05:30')
                self.assertFalse(indicator_window(first,DAY+'T09:50:09+05:30')['ready'])
                before={p:p.read_bytes() for p in reader.root.glob('batch-*.json')}
                self.write(source)
                fixed=reader.poll(DAY+'T09:50:20+05:30')
                self.assertFalse(indicator_window(fixed,DAY+'T09:50:09+05:30')['ready'])
                self.assertTrue(indicator_window(fixed,DAY+'T09:50:20+05:30')['ready'])
                old=next(r for r in latest_minutes(fixed['revisions'],DAY+'T09:50:09+05:30') if '09:47:00' in r['minute_ist'])
                new=next(r for r in latest_minutes(fixed['revisions'],DAY+'T09:50:20+05:30') if '09:47:00' in r['minute_ist'])
                self.assertIsNone(old['vix_close']); self.assertEqual(new['vix_close'],12.02)
                self.assertEqual(new['revision'],2)
                self.assertEqual(new['available_at'],'2031-04-07T04:20:20.000000+00:00')
                self.assertEqual(before,{p:p.read_bytes() for p in before})
                recovered=IndicatorInputs(config,DAY)
                self.assertEqual(reader.revisions,recovered.revisions)
                again=recovered.poll(DAY+'T09:50:25+05:30')
                self.assertEqual(again['revisions'],fixed['revisions'])

    def test_unchanged_csv_is_revisited_after_finalization_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source,count=1)
            reader=IndicatorInputs(config,DAY)
            early=reader.poll(DAY+'T09:46:07+05:30')
            self.assertFalse(indicator_window(early,DAY+'T09:46:07+05:30',1)['ready'])
            later=reader.poll(DAY+'T09:46:09+05:30')
            self.assertTrue(indicator_window(later,DAY+'T09:46:09+05:30',1)['ready'])

    def test_partial_cash_does_not_make_valid_vix_unusable(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source,partial=(4,))
            feed=IndicatorInputs(config,DAY).poll(DAY+'T09:50:10+05:30')
            self.assertTrue(indicator_window(feed,DAY+'T09:50:10+05:30',1)['ready'])
            self.assertFalse(indicator_window(feed,DAY+'T09:50:10+05:30',1,'cash_weighted_pct')['ready'])

    def test_full_session_is_independent_of_old_cash_analysis_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source,start='09:15:00',count=375)
            feed=IndicatorInputs(config,DAY).poll(DAY+'T15:30:10+05:30')
            self.assertEqual(feed['quality']['minutes'],375)
            self.assertEqual(feed['quality']['vix_valid'],375)
            self.assertEqual(feed['revisions'][0]['minute_ist'],DAY+'T09:15:00+05:30')
            self.assertEqual(feed['revisions'][-1]['minute_ist'],DAY+'T15:29:00+05:30')
            self.assertTrue(indicator_window(feed,DAY+'T15:30:10+05:30',375)['ready'])
            self.assertFalse(indicator_window(feed,DAY+'T10:00:00+05:30')['ready'])

    def test_changed_valid_value_and_partial_write_preserve_previous_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source)
            reader=IndicatorInputs(config,DAY);first=reader.poll(DAY+'T09:50:10+05:30')
            self.write(source,vix_override={4:12.5})
            second=reader.poll(DAY+'T09:50:20+05:30')
            self.assertEqual(indicator_window(second,DAY+'T09:50:10+05:30',1)['rows'][0]['vix_close'],12.04)
            self.assertEqual(indicator_window(second,DAY+'T09:50:20+05:30',1)['rows'][0]['vix_close'],12.5)
            source.write_bytes(source.read_bytes()+b'incomplete,')
            blocked=reader.poll(DAY+'T09:50:25+05:30')
            self.assertEqual(blocked['revisions'],second['revisions'])
            self.assertIn('SOURCE_UNAVAILABLE',indicator_window(blocked,DAY+'T09:50:25+05:30')['reasons'])

    def test_legacy_missing_row_remains_missing_at_its_original_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source)
            legacy=config.state_root/'runtime/engine'/DAY/'cash_vix_first_observed_v2.jsonl'
            legacy.parent.mkdir(parents=True)
            old={'minute_ist':DAY+'T09:49:00+05:30','t':DAY+'T09:50:08+05:30','vix_close':None,'cash_names':0,'expected_constituent_count':2}
            legacy.write_text(json.dumps(old)+'\n');original=legacy.read_bytes()
            feed=IndicatorInputs(config,DAY).poll(DAY+'T09:50:30+05:30')
            self.assertFalse(indicator_window(feed,DAY+'T09:50:09+05:30',1)['ready'])
            self.assertTrue(indicator_window(feed,DAY+'T09:50:30+05:30',1)['ready'])
            self.assertEqual(legacy.read_bytes(),original)

    def test_wrong_instrument_duplicate_and_bad_numeric_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source,vix_override={4:'NaN'})
            reader=IndicatorInputs(config,DAY);feed=reader.poll(DAY+'T09:50:10+05:30')
            self.assertFalse(indicator_window(feed,DAY+'T09:50:10+05:30',1)['ready'])
            m=config.collector_root/'metadata/startup_test.json'
            raw=json.loads(m.read_text());raw['base_quote_symbols']=['NSE:NIFTYBANK-INDEX'];m.write_text(json.dumps(raw))
            bad=reader.poll(DAY+'T09:50:20+05:30');self.assertEqual(bad['status'],'SOURCE_UNAVAILABLE')
            self.assertEqual(bad['revisions'],feed['revisions'])
            raw['base_quote_symbols']=['NSE:NIFTY50-INDEX'];m.write_text(json.dumps(raw))
            source.write_text(source.read_text()+DAY+'T09:45:00+05:30,NSE:INDIAVIX-INDEX,vix,12,15,0,'+DAY+'T09:45:59+05:30\n')
            duplicate=reader.poll(DAY+'T09:50:25+05:30')
            self.assertIn('duplicate',duplicate['error'])
            self.assertEqual(duplicate['revisions'],feed['revisions'])

    def test_future_receipt_is_not_available_until_its_clock_and_missing_metadata_keeps_cash_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            config,source=self.setup_source(Path(tmp));self.write(source,count=1)
            body=source.read_text().replace(DAY+'T09:45:59+05:30',DAY+'T09:46:30+05:30')
            source.write_text(body)
            (config.collector_root/'metadata/startup_test.json').unlink()
            reader=IndicatorInputs(config,DAY)
            early=reader.poll(DAY+'T09:46:10+05:30')
            self.assertFalse(indicator_window(early,DAY+'T09:46:10+05:30',1)['ready'])
            later=reader.poll(DAY+'T09:46:31+05:30')
            self.assertTrue(indicator_window(later,DAY+'T09:46:31+05:30',1)['ready'])
            self.assertFalse(indicator_window(later,DAY+'T09:46:31+05:30',1,'cash_weighted_pct')['ready'])

    def test_invalid_indicator_window_is_rejected(self):
        for value in (0,-1,376,1.5,True):
            with self.assertRaises(ValueError): indicator_window({},datetime.now().astimezone(),value)


if __name__=='__main__':unittest.main()
