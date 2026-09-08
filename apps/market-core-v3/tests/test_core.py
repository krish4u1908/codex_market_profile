import concurrent.futures
import gzip
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from market_core.config import Config
from market_core.gui import handler_for as gui_handler
from market_core.server import handler_for as core_handler
from market_core.storage import PublishedStore

ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def test_each_instrument_recovers_and_preserves_native_decisions(self):
        for instrument in ('BANKNIFTY','NIFTY'):
            with self.subTest(instrument=instrument):
                result = subprocess.run([sys.executable, '-m', 'tests.instrument_checks'], cwd=ROOT,
                    env=dict(os.environ,TEST_INSTRUMENT=instrument),text=True,capture_output=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_config_rejects_wrong_instrument_and_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for options in [dict(state_root=root/'collector/state'),dict(host='0.0.0.0'),
                dict(context_root=root/'collector'),dict(futures_symbols_by_session={'2031-04-07':'NSE:NIFTY31APRFUT'})]:
                values=dict(instrument='BANKNIFTY',collector_root=root/'collector',state_root=root/'state',lock_path=root/'lock')
                values.update(options)
                with self.assertRaises(ValueError): Config(**values).validate()

    def serve(self, handler):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, 'http://127.0.0.1:'+str(server.server_port)

    def test_gui_restart_replay_and_parallel_reads_do_not_touch_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'index.html').write_text('independent GUI')
            config=Config('BANKNIFTY',root/'collector',root/'state',root/'lock')
            store=PublishedStore(config)
            profile='banknifty-v200';payload={'session':'2031-04-07','decisions':[{'published_at':'unchanged'}]}
            store.publish(profile,payload,live=True)
            core,base=self.serve(core_handler(store))
            gui,front=self.serve(gui_handler(root,'BANKNIFTY',core.server_port))
            before=store.live(profile)
            def request(_):
                with urlopen(front+'/api/live?profile='+profile,timeout=5) as r: return json.load(r)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                self.assertTrue(all(row==payload for row in pool.map(request,range(24))))
            self.assertEqual(store.live(profile),before)
            for endpoint in ['/api/live?profile=nifty-v200','/api/replay?profile=banknifty-v200&key=../../bad','/../no-such-file']:
                with self.assertRaises(HTTPError) as error: urlopen(front+endpoint,timeout=5)
                self.assertIn(error.exception.code,(400,404))
            with self.assertRaises(HTTPError) as unchanged:
                urlopen(Request(base+'/api/live?profile='+profile,headers={'If-None-Match':before[2]}))
            self.assertEqual(unchanged.exception.code,304)
            with urlopen(Request(front+'/api/live?profile='+profile,headers={'Accept-Encoding':'gzip'})) as response:
                self.assertEqual(json.loads(gzip.decompress(response.read())),payload)
            saved=PublishedStore(config)
            self.assertIsNone(saved.live(profile))
            self.assertEqual(json.loads(gzip.decompress(saved.replay(profile,'recorded-2031-04-07'))),payload)
            # GUI shell still serves when the core is down; state stays intact.
            core.shutdown();core.server_close()
            with urlopen(front+'/') as response: self.assertEqual(response.read(),b'independent GUI')
            with self.assertRaises(HTTPError) as offline: urlopen(front+'/api/health',timeout=6)
            self.assertEqual(offline.exception.code,502)
            self.assertEqual(store.live(profile),before)


if __name__=='__main__': unittest.main(verbosity=2)
