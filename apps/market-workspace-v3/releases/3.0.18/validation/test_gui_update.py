from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import importlib.util
_spec = importlib.util.spec_from_file_location("update_gui", Path(__file__).resolve().parents[1] / "update_gui.py")
updater = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(updater)


class GuiUpdateTests(unittest.TestCase):
    def setup_install(self, tmp):
        root = Path(tmp) / 'install'
        release = root / 'releases/original'
        gui = release / 'gui'
        gui.mkdir(parents=True)
        (gui / 'index.html').write_text('original GUI')
        (release / 'core').mkdir()
        (release / 'core/unchanged.txt').write_text('core/config sentinel')
        (root / 'current').symlink_to(release, target_is_directory=True)
        bundle = Path(tmp) / 'bundle'
        (bundle / 'gui').mkdir(parents=True)
        (bundle / 'gui/index.html').write_text('new GUI')
        (bundle / 'gui/gui-release.json').write_text(json.dumps({'version': updater.RELEASE}))
        self.manifest(bundle)
        return root, release, bundle

    def manifest(self, bundle):
        entries = [{'path': p.relative_to(bundle).as_posix(), 'sha256': updater.digest(p)}
                   for p in bundle.rglob('*') if p.is_file() and p.name != updater.MANIFEST]
        (bundle / updater.MANIFEST).write_text(json.dumps({'release': updater.RELEASE, 'files': entries}))

    def mocks(self, stack, root):
        calls = []
        def status(unit):
            instrument = unit.split('-')[0].upper()
            gui, core = updater.PORTS[instrument]
            return {'LoadState': 'loaded', 'ActiveState': 'active', 'MainPID': '101' if instrument == 'BANKNIFTY' else '102',
                    'ExecStart': f'-m market_core.gui --instrument {instrument} --root {root}/current/gui --port {gui} --core-port {core}'}
        stack.enter_context(patch.object(updater, 'unit_status', status))
        stack.enter_context(patch.object(updater, 'systemctl', lambda *args: calls.append(args)))
        stack.enter_context(patch.object(updater.GuiUpdater, 'healthy', lambda *args: None))
        return calls

    def test_apply_and_rollback_preserve_core_files_pids_and_original_gui(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            instance = updater.GuiUpdater(root)
            before = (root / 'current').readlink()
            result = instance.apply(bundle)
            self.assertEqual(result['core_pids_before'], result['core_pids_after'])
            self.assertEqual((release / 'gui/index.html').read_text(), 'new GUI')
            self.assertTrue((release / 'gui').is_symlink())
            instance.rollback(result['record'])
            self.assertEqual((release / 'gui/index.html').read_text(), 'original GUI')
            self.assertFalse((release / 'gui').is_symlink())
            self.assertEqual((release / 'core/unchanged.txt').read_text(), 'core/config sentinel')
            self.assertEqual((root / 'current').readlink(), before)
            self.assertEqual(calls, [(action, *updater.GUI_UNITS) for action in ('stop', 'start', 'stop', 'start')])

    def test_report_quote_gui_rejects_old_core_before_stopping_services(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            (bundle/'gui/gui-release.json').write_text(json.dumps({'version':updater.RELEASE,'minimumCoreVersion':'3.0.2'}))
            self.manifest(bundle)
            stack.enter_context(patch.object(updater,'read_json',return_value={'version':'3.0.1','instrument':'BANKNIFTY'}))
            with self.assertRaisesRegex(RuntimeError,'full bundle'):
                updater.GuiUpdater(root).apply(bundle)
            self.assertEqual(calls,[])

    def test_bad_package_or_missing_core_fails_before_service_changes(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            (bundle / 'gui/index.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                updater.GuiUpdater(root).apply(bundle)
            self.assertEqual(calls, [])
            self.assertFalse((root / 'gui-releases').exists())
            self.manifest(bundle)
            stack.enter_context(patch.object(updater, 'unit_status', return_value={'LoadState': 'loaded', 'ActiveState': 'inactive', 'MainPID': '0'}))
            with self.assertRaisesRegex(RuntimeError, 'not running'):
                updater.GuiUpdater(root).apply(bundle)
            self.assertEqual(calls, [])

    def test_failed_health_check_restores_gui_and_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            stack.enter_context(patch.object(updater.GuiUpdater, 'healthy', side_effect=[RuntimeError('not healthy'), None]))
            with self.assertRaisesRegex(RuntimeError, 'GUI update failed'):
                updater.GuiUpdater(root).apply(bundle)
            self.assertEqual((release / 'gui/index.html').read_text(), 'original GUI')
            record = json.loads(next((root / 'gui-update-records').glob('*.json')).read_text())
            self.assertEqual(record['phase'], 'failed-restored')
            self.assertEqual(calls, [(action, *updater.GUI_UNITS) for action in ('stop', 'start', 'stop', 'start')])

    def test_core_pid_change_is_detected_without_attempting_core_restart(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            stack.enter_context(patch.object(updater.GuiUpdater, 'assert_core_pids', side_effect=RuntimeError('core PID changed')))
            with self.assertRaisesRegex(RuntimeError, 'GUI update failed'):
                updater.GuiUpdater(root).apply(bundle)
            self.assertEqual((release / 'gui/index.html').read_text(), 'original GUI')
            self.assertTrue(all(call[1:] == updater.GUI_UNITS for call in calls))

    def test_stale_rollback_cannot_replace_a_later_gui_and_symlink_backups_work(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root, release, bundle = self.setup_install(tmp)
            calls = self.mocks(stack, root)
            instance = updater.GuiUpdater(root)
            first = instance.apply(bundle)
            second = instance.apply(bundle)
            old_calls = list(calls)
            with self.assertRaisesRegex(RuntimeError, 'stale rollback'):
                instance.rollback(first['record'])
            self.assertEqual(calls, old_calls)
            instance.rollback(second['record'])
            self.assertEqual((release / 'gui').resolve(), Path(first['assets']))
            instance.rollback(first['record'])
            self.assertEqual((release / 'gui/index.html').read_text(), 'original GUI')

    def test_unlisted_files_symlinks_and_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, bundle = self.setup_install(tmp)
            extra = bundle / 'extra'
            extra.write_text('unlisted')
            with self.assertRaisesRegex(ValueError, 'unlisted'):
                updater.verify_package(bundle)
            extra.unlink()
            extra.symlink_to(bundle / 'gui/index.html')
            with self.assertRaisesRegex(ValueError, 'symbolic'):
                updater.verify_package(bundle)
            extra.unlink()
            (bundle / updater.MANIFEST).write_text(json.dumps({'release': updater.RELEASE, 'files': [{'path': '../escape', 'sha256': 'x'}]}))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                updater.verify_package(bundle)


if __name__ == '__main__':
    unittest.main()
