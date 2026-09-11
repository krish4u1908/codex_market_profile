from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy import update_data as update


class DataUpdateTests(unittest.TestCase):
    def fixture(self,tmp):
        root=Path(tmp)/'install';release=root/'releases/old';bundle=Path(tmp)/'bundle'
        for base in (release,bundle):
            (base/'core').mkdir(parents=True);(base/'gui').mkdir();(base/'config').mkdir()
            (base/'core/requirements.txt').write_text('')
            (base/'core/VENDOR_MANIFEST.json').write_text('{"files":[]}')
            (base/'core/marker').write_text('old' if base==release else 'new')
            (base/'gui/index.html').write_text('old' if base==release else 'new')
        for name in ('banknifty','nifty'):(release/'config'/f'{name}.json').write_text('{"config":"retained"}')
        (root/'current').symlink_to(release,target_is_directory=True)
        (bundle/'core/indicator-release.json').write_text(json.dumps({'version':update.CORE_VERSION,'schema':update.SCHEMA,'gui':update.GUI_VERSION}))
        (bundle/'gui/gui-release.json').write_text(json.dumps({'version':update.GUI_VERSION}))
        entries=[{'path':p.relative_to(bundle).as_posix(),'sha256':update.gui.digest(p)} for p in bundle.rglob('*') if p.is_file()]
        (bundle/'BUNDLE-MANIFEST.json').write_text(json.dumps({'files':entries}))
        sentinel=root/'state/recorded-calls';sentinel.parent.mkdir();sentinel.write_text('original calls and prices')
        return root,release,bundle,sentinel

    def mock_services(self,stack,root):
        running={unit:True for unit in update.UNITS};calls=[]
        def control(action,units=update.UNITS):
            calls.append((action,*units))
            for unit in units:running[unit]=action=='start'
        def state(unit):
            name=unit.split('-')[0];port,core=update.gui.PORTS[name.upper()]
            command=(f'-m market_core.server --config {root}/current/config/{name}.json' if unit in update.gui.CORE_UNITS else
                f'-m market_core.gui --instrument {name.upper()} --root {root}/current/gui --core-port {core} --port {port}')
            return {'LoadState':'loaded','ActiveState':'active' if running[unit] else 'inactive','MainPID':'123' if running[unit] else '0','ExecStart':command}
        stack.enter_context(patch.object(update,'control',control))
        stack.enter_context(patch.object(update.gui,'unit_status',state))
        stack.enter_context(patch.object(update.DataUpdater,'healthy_data',lambda *args:None))
        return calls

    def test_apply_and_rollback_keep_config_calls_and_current_release(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,sentinel=self.fixture(tmp);calls=self.mock_services(stack,root)
            configs={p:p.read_bytes() for p in (release/'config').glob('*.json')}
            before=(root/'current').readlink(); instance=update.DataUpdater(root)
            record=instance.apply(bundle)
            self.assertEqual((release/'core/marker').read_text(),'new')
            self.assertEqual((release/'gui/index.html').read_text(),'new')
            instance.rollback(record['record'])
            self.assertEqual((release/'core/marker').read_text(),'old')
            self.assertEqual((release/'gui/index.html').read_text(),'old')
            self.assertEqual(configs,{p:p.read_bytes() for p in configs})
            self.assertEqual(sentinel.read_text(),'original calls and prices')
            self.assertEqual((root/'current').readlink(),before)
            self.assertTrue(all(set(call[1:])<=set(update.UNITS) for call in calls))

    def test_bad_bundle_fails_before_service_stop(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,_=self.fixture(tmp);calls=self.mock_services(stack,root)
            (bundle/'core/marker').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'checksum'):update.DataUpdater(root).apply(bundle)
            self.assertEqual(calls,[])

    def test_health_failure_restores_both_code_slots(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,_=self.fixture(tmp);self.mock_services(stack,root)
            stack.enter_context(patch.object(update.DataUpdater,'healthy_data',side_effect=[RuntimeError('bad health'),None]))
            with self.assertRaisesRegex(RuntimeError,'Data update failed'):update.DataUpdater(root).apply(bundle)
            self.assertEqual((release/'core/marker').read_text(),'old');self.assertEqual((release/'gui/index.html').read_text(),'old')
            record=json.loads(next((root/'data-update-records').glob('*.json')).read_text())
            self.assertEqual(record['phase'],'failed-restored')

    def test_stale_rollback_is_rejected_before_stopping_services(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,_=self.fixture(tmp);calls=self.mock_services(stack,root)
            instance=update.DataUpdater(root);first=instance.apply(bundle);second=instance.apply(bundle)
            before=list(calls)
            with self.assertRaisesRegex(RuntimeError,'stale rollback'):instance.rollback(first['record'])
            self.assertEqual(calls,before)
            instance.rollback(second['record']);instance.rollback(first['record'])
            self.assertEqual((release/'core/marker').read_text(),'old')

    def test_dependency_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,_=self.fixture(tmp);calls=self.mock_services(stack,root)
            (release/'core/requirements.txt').write_text('unexpected-dependency')
            with self.assertRaisesRegex(RuntimeError,'unchanged dependencies'):update.DataUpdater(root).apply(bundle)
            self.assertEqual(calls,[])

    def test_interruption_between_rename_and_link_can_be_rolled_back(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root,release,bundle,sentinel=self.fixture(tmp);self.mock_services(stack,root)
            instance=update.DataUpdater(root)
            with patch.object(Path,'symlink_to',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):instance.apply(bundle)
            record_path=next((root/'data-update-records').glob('*.json'))
            self.assertEqual(json.loads(record_path.read_text())['phase'],'prepared')
            self.assertFalse((release/'core').exists())
            instance.rollback(record_path)
            self.assertEqual((release/'core/marker').read_text(),'old')
            self.assertEqual((release/'gui/index.html').read_text(),'old')
            self.assertEqual(sentinel.read_text(),'original calls and prices')


if __name__=='__main__':unittest.main()
