import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError

from market_core.config import Config
from market_core.option_reports import OptionReportReader, OptionReportCache, parse_report
from market_core.server import handler_for
from market_core.storage import PublishedStore

DAY='2026-09-10'
def report(instrument='NIFTY', at='10:00:55.113', oi=100000):
    index='NSE:NIFTY50-INDEX' if instrument=='NIFTY' else 'NSE:NIFTYBANK-INDEX'
    return {'source':'option_chain','received_at':DAY+'T'+at+'+05:30','response':{'code':200,'data':{
        'expiryData':[{'date':'15-09-2026'}], 'indiavixData':{'symbol':'NSE:INDIAVIX-INDEX','ltp':12.4},
        'optionsChain':[{'symbol':index,'ltp':23520 if instrument=='NIFTY' else 57520},
                        {'symbol':'NSE:'+instrument+'2691523500PE','option_type':'PE','strike_price':23500,'oi':oi,'prev_oi':999999,'oich':-999}]}}}

class OptionReportTests(unittest.TestCase):
    def config(self,root,instrument='NIFTY'):
        return Config(instrument,root/'collector',root/'state',root/'lock')

    def test_identity_and_report_totals_for_both_instruments(self):
        for instrument in ('NIFTY','BANKNIFTY'):
            r=parse_report(report(instrument),instrument,DAY)
            self.assertEqual(r['contracts'][0]['oi'],100000)
            self.assertEqual(r['vix'],12.4)
            other='BANKNIFTY' if instrument=='NIFTY' else 'NIFTY'
            self.assertIsNone(parse_report(report(instrument),other,DAY))
        bad=report();bad['response']['data']['indiavixData']['symbol']='OTHER'
        self.assertIsNone(parse_report(bad,'NIFTY',DAY)['vix'])

    def test_tail_waits_for_newline_deduplicates_and_rebuilds_replaced_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=self.config(Path(tmp));p=config.collector_root/'oi'/DAY/'oi_10.jsonl';p.parent.mkdir(parents=True)
            a=json.dumps(report()).encode();b=json.dumps(report(at='10:01:55.278',oi=98000)).encode()
            p.write_bytes(a+b'\n'+b[:50]);reader=OptionReportReader(config,DAY)
            self.assertEqual(reader.poll()['quality']['reports'],1)
            with p.open('ab') as f:f.write(b[50:]+b'\n'+a+b'\n')
            feed=reader.poll();self.assertEqual(feed['quality']['reports'],2)
            self.assertEqual(feed['reports'][1]['contracts'][0]['oi'],98000)
            p.unlink();p.write_bytes(a+b'\n');self.assertEqual(reader.poll()['quality']['reports'],1)

    def test_missing_archive_and_conflicting_receipts_are_not_silent_zero_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=self.config(Path(tmp));reader=OptionReportReader(config,DAY)
            self.assertEqual(reader.poll()['status'],'MISSING')
            p=config.collector_root/'oi'/DAY/'oi_10.jsonl';p.parent.mkdir(parents=True)
            p.write_text(json.dumps(report())+'\n'+json.dumps(report(oi=99999))+'\n')
            with self.assertRaisesRegex(ValueError,'Conflicting'):reader.poll()

    def test_slow_archive_does_not_block_live_health_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=self.config(Path(tmp));store=PublishedStore(config);cache=OptionReportCache(config);store.option_reports=cache
            store.publish('nifty-v200',{'session':DAY,'decisions':[]},live=True)
            entered,release=threading.Event(),threading.Event()
            def slow(_):
                entered.set();release.wait(5)
                return dict(schema='OPTION_REPORT_INPUTS_V1',instrument='NIFTY',session=DAY,status='MISSING',reports=[])
            with patch.object(OptionReportReader,'poll',slow):
                cache.start();server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(store))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base='http://127.0.0.1:'+str(server.server_port)
                try:
                    with urlopen(base+'/api/option-report-inputs?profile=nifty-v200&session='+DAY,timeout=1) as response:
                        self.assertEqual(response.status,202)
                    self.assertTrue(entered.wait(1))
                    for path in ['/health','/api/live?profile=nifty-v200','/api/replay?profile=nifty-v200&key=recorded-'+DAY]:
                        with urlopen(base+path,timeout=1) as response:self.assertEqual(response.status,200)
                    for path in ['/api/option-report-inputs?profile=banknifty-v200&session='+DAY,
                                 '/api/option-report-inputs?profile=nifty-v200&session=../../etc']:
                        with self.assertRaises(HTTPError) as e:urlopen(base+path,timeout=1)
                        self.assertEqual(e.exception.code,400)
                finally:
                    release.set();cache.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
