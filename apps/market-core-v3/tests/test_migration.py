import gzip
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from market_core.config import Config
from market_core.migration import copy_state, import_prepared, migrate, sha256
from market_core.storage import PublishedStore


def old_state(root,instrument='BANKNIFTY'):
    root.mkdir(parents=True)
    (root/'engine/2031-04-07').mkdir(parents=True)
    (root/'engine/2031-04-07/event_journal.jsonl').write_text('{"receipt":"retained"}\n')
    with sqlite3.connect(root/'context.sqlite3') as db:
        db.executescript('CREATE TABLE inputs(day TEXT,kind TEXT,identity TEXT,timestamp REAL,body TEXT); CREATE TABLE decisions(day TEXT,cutoff REAL,body TEXT); CREATE TABLE selections(day TEXT,body TEXT);')
        db.execute('INSERT INTO inputs VALUES(?,?,?,?,?)',('2031-04-07','price','1',1,json.dumps({'t':'2031-04-07T09:45:59+05:30','i':24000 if instrument=='NIFTY' else 57000,'b':10})))
        db.execute('INSERT INTO decisions VALUES(?,?,?)',('2031-04-07',2,json.dumps({'t':'2031-04-07T09:46:35+05:30','context_published_at':'2031-04-07T09:46:35+05:30','input_cutoff':'2031-04-07T09:46:00+05:30','corrected_direction':'UP','corrected_score':3.5})))


class MigrationTests(unittest.TestCase):
    def test_copy_and_sqlite_export_keep_recorded_publications(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';old_state(old)
            original={p:sha256(p) for p in old.rglob('*') if p.is_file()}
            config=Config('BANKNIFTY',root/'collector',root/'new',root/'lock')
            report=migrate(config,old,{})
            self.assertEqual(report['retained_v2']['imported'],1)
            for path,value in original.items(): self.assertEqual(sha256(path),value)
            store=PublishedStore(config)
            payload=json.loads(gzip.decompress(store.replay('banknifty-v200','migrated-2031-04-07')))
            with sqlite3.connect(old/'context.sqlite3') as db: expected=json.loads(db.execute('SELECT body FROM decisions').fetchone()[0])
            self.assertEqual(payload['decisions'],[expected])
            self.assertEqual(payload['chart_inputs']['price'][0]['b'],10)
            with self.assertRaises(FileExistsError): migrate(config,old,{})

    def test_sqlite_backup_includes_wal_and_refuses_links_and_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';old_state(old)
            with sqlite3.connect(old/'context.sqlite3') as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('INSERT INTO selections VALUES(?,?)',('2031-04-07','{"available":true}'));db.commit()
                copy_state(old,root/'new')
                with sqlite3.connect(root/'new/context.sqlite3') as new:
                    self.assertEqual(new.execute('SELECT count(*) FROM selections').fetchone()[0],1)
            (old/'outside').symlink_to(root/'unrelated')
            with self.assertRaises(ValueError): copy_state(old,root/'other')
            with self.assertRaises(FileExistsError): copy_state(old,root/'new')

    def test_imports_keep_distinct_sessions_and_reject_other_index_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);prepared=root/'prepared';prepared.mkdir()
            config=Config('BANKNIFTY',root/'collector',root/'new',root/'lock')
            good={'schema':'NEW_DIVERGENCE_BROWSER_PAYLOAD_V1','session':'2031-04-07','price':[{'t':'2031-04-07T09:15:00+05:30','i':57000,'b':10}],'directional_prediction':[{'published_at':'actual'}]}
            (prepared/'2031-04-07.json').write_text(json.dumps(good))
            (prepared/'2031-04-08.json').write_text(json.dumps(dict(good,session='2031-04-08',instrument='NIFTY')))
            report=import_prepared(config,prepared,'v1062')
            self.assertEqual(report['imported'],1);self.assertEqual(len(report['skipped']),1)
            store=PublishedStore(config);entry=store.catalog('banknifty-v1062')['sessions'][0]
            imported=json.loads(gzip.decompress(store.replay('banknifty-v1062',entry['id'])))
            self.assertEqual(imported['directional_prediction'],good['directional_prediction'])
            (prepared/'catalog.json').write_text(json.dumps({'sessions':[{'payload':'../outside.json'}]}))
            with self.assertRaisesRegex(ValueError,'escapes'): import_prepared(config,prepared,'v1062')


if __name__=='__main__': unittest.main(verbosity=2)
