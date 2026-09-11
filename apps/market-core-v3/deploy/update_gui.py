#!/usr/bin/env python3
"""Update the two installed GUIs, preserving both core processes and their state."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen

INSTALL_ROOT = Path('/opt/market-workspace-v3')
EXPECTED_HOST = 'srv1913330'
GUI_UNITS = ('banknifty-gui.service', 'nifty-gui.service')
CORE_UNITS = ('banknifty-core.service', 'nifty-core.service')
PORTS = {'BANKNIFTY': (8920, 8922), 'NIFTY': (8921, 8923)}
RELEASE = '3.0.4-cash-vix-data'
MANIFEST = 'GUI-UPDATE-MANIFEST.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_package(bundle):
    bundle = Path(bundle).resolve(strict=True)
    manifest = json.loads((bundle / MANIFEST).read_text())
    if manifest.get('release') != RELEASE:
        raise ValueError('GUI package release does not match this updater')
    entries = manifest.get('files', [])
    expected = {MANIFEST}
    for entry in entries:
        relative = PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or str(relative) in expected:
            raise ValueError('Unsafe or duplicate GUI manifest path')
        expected.add(str(relative))
        path = bundle / relative
        if not path.is_file() or path.is_symlink() or digest(path) != entry['sha256']:
            raise ValueError('GUI package checksum failed: ' + str(relative))
    actual = set()
    for path in bundle.rglob('*'):
        if path.is_symlink():
            raise ValueError('GUI package must not contain symbolic links')
        if path.is_file():
            actual.add(path.relative_to(bundle).as_posix())
    if actual != expected or not (bundle / 'gui/index.html').is_file():
        raise ValueError('GUI package contains missing or unlisted files')
    if json.loads((bundle / 'gui/gui-release.json').read_text()).get('version') != RELEASE:
        raise ValueError('Built GUI release does not match this updater')
    return bundle


def systemctl(*args):
    return subprocess.run(['systemctl', *args], check=True, text=True,
                          capture_output=True, timeout=45).stdout


def unit_status(unit):
    output = systemctl('show', unit, '--property=LoadState,ActiveState,MainPID,ExecStart')
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def read_json(url):
    with urlopen(url, timeout=2) as response:
        return json.load(response)


def write_record(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.chmod(0o600)
    os.replace(temporary, path)


class GuiUpdater:
    def __init__(self, root=INSTALL_ROOT):
        self.root = Path(root).resolve(strict=True)

    def installed_release(self):
        current = self.root / 'current'
        if not current.is_symlink():
            raise RuntimeError('Expected an existing shared-core installation with current symlink')
        release = current.resolve(strict=True)
        if not release.is_relative_to(self.root / 'releases'):
            raise RuntimeError('Installed release is outside the reviewed releases directory')
        return release

    def inspect(self, allow_stopped_gui=False):
        release = self.installed_release()
        units = {unit: unit_status(unit) for unit in CORE_UNITS + GUI_UNITS}
        for unit, state in units.items():
            if state.get('LoadState') != 'loaded':
                raise RuntimeError('Required unit is not loaded: ' + unit)
            if (unit in CORE_UNITS or not allow_stopped_gui) and (
                state.get('ActiveState') != 'active' or int(state.get('MainPID', '0')) <= 0
            ):
                raise RuntimeError('Required service is not running: ' + unit)
        for instrument, (gui_port, core_port) in PORTS.items():
            command = units[instrument.lower() + '-gui.service'].get('ExecStart', '')
            for fragment in ('-m market_core.gui', '--instrument ' + instrument,
                             '--root ' + str(self.root / 'current/gui'),
                             '--port ' + str(gui_port), '--core-port ' + str(core_port)):
                if not re.search(r'(?<!\S)' + re.escape(fragment) + r'(?=\s|;|$)', command):
                    raise RuntimeError('GUI unit does not match the reviewed shared-core layout')
        return {'release': str(release), 'units': units,
                'core_pids': {unit: units[unit]['MainPID'] for unit in CORE_UNITS}}

    def check(self, bundle):
        bundle = verify_package(bundle)
        state = self.inspect()
        gui = Path(state['release']) / 'gui'
        if not gui.is_dir() or not gui.resolve().is_relative_to(self.root):
            raise RuntimeError('Installed GUI path is missing or outside the installation')
        return {**state, 'new_gui_release': RELEASE, 'package': str(bundle),
                'restart_only': list(GUI_UNITS)}

    @contextmanager
    def locked(self):
        with (self.root / 'gui-update.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def control_guis(self, action):
        if action not in ('stop', 'start'):
            raise ValueError('Only GUI stop/start is permitted')
        systemctl(action, *GUI_UNITS)

    def healthy(self, expected_release=None):
        deadline = time.monotonic() + 15
        while True:
            try:
                for instrument, (port, _) in PORTS.items():
                    base = 'http://127.0.0.1:' + str(port)
                    health = read_json(base + '/health')
                    if (health.get('status'), health.get('role'), health.get('instrument'), health.get('owns_engine')) != ('ok', 'gui', instrument, False):
                        raise RuntimeError('GUI health identity mismatch: ' + instrument)
                    if expected_release and read_json(base + '/gui-release.json').get('version') != expected_release:
                        raise RuntimeError('GUI is not serving the requested release: ' + instrument)
                return
            except Exception:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)

    def assert_core_pids(self, previous):
        current = {unit: unit_status(unit) for unit in CORE_UNITS}
        if any(current[unit].get('ActiveState') != 'active' or current[unit].get('MainPID') != pid
               for unit, pid in previous.items()):
            raise RuntimeError('A core PID changed during the GUI update; inspect core status separately')

    def restore(self, slot, backup, assets):
        if backup.exists() or backup.is_symlink():
            if slot.is_symlink() and slot.resolve() == assets:
                slot.unlink()
            elif slot.exists() or slot.is_symlink():
                raise RuntimeError('GUI slot changed unexpectedly; retained backup: ' + str(backup))
            backup.rename(slot)

    def apply(self, bundle):
        with self.locked():
            checked = self.check(bundle)
            bundle = Path(checked['package'])
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            release = Path(checked['release'])
            slot, backup = release / 'gui', release / ('gui-before-' + stamp)
            assets = self.root / 'gui-releases' / (RELEASE + '-' + stamp)
            assets.parent.mkdir(mode=0o755, exist_ok=True)
            assets.parent.chmod(0o755)
            shutil.copytree(bundle / 'gui', assets)
            for path in [assets, *assets.rglob('*')]:
                path.chmod(0o755 if path.is_dir() else 0o644)
            # Recheck copied bytes before any service is stopped.
            for entry in json.loads((bundle / MANIFEST).read_text())['files']:
                if entry['path'].startswith('gui/') and digest(assets / entry['path'][4:]) != entry['sha256']:
                    raise RuntimeError('Staged GUI checksum failed')
            records = self.root / 'gui-update-records'
            records.mkdir(mode=0o700, exist_ok=True)
            record_path = records / (stamp + '.json')
            record = {'phase': 'prepared', 'release': str(release), 'slot': str(slot),
                      'backup': str(backup), 'assets': str(assets), 'gui_version': RELEASE,
                      'core_pids_before': checked['core_pids'], 'created_at': stamp}
            write_record(record_path, record)
            try:
                self.control_guis('stop')
                slot.rename(backup)
                slot.symlink_to(assets, target_is_directory=True)
                self.control_guis('start')
                self.healthy(RELEASE)
                self.assert_core_pids(checked['core_pids'])
                record.update(phase='installed', core_pids_after=checked['core_pids'])
                write_record(record_path, record)
            except Exception as error:
                record.update(phase='failed', error=str(error))
                try:
                    self.control_guis('stop')
                    self.restore(slot, backup, assets)
                    self.control_guis('start')
                    self.healthy()
                    record['phase'] = 'failed-restored'
                except Exception as recovery:
                    record['recovery_error'] = str(recovery)
                write_record(record_path, record)
                raise RuntimeError('GUI update failed; see ' + str(record_path)) from error
            return {'record': str(record_path), **record}

    def rollback(self, record_path):
        with self.locked():
            record_path = Path(record_path).resolve(strict=True)
            if record_path.parent != self.root / 'gui-update-records':
                raise ValueError('Use a record from this installation gui-update-records directory')
            record = json.loads(record_path.read_text())
            release = self.installed_release()
            slot, backup, assets = (Path(record[key]) for key in ('slot', 'backup', 'assets'))
            if (record['release'] != str(release) or slot != release / 'gui'
                or backup != release / ('gui-before-' + record['created_at'])
                or assets != self.root / 'gui-releases' / (record['gui_version'] + '-' + record['created_at'])
                or not (backup.exists() or backup.is_symlink())):
                raise RuntimeError('Rollback record does not match the current installation or backup')
            if slot.exists() or slot.is_symlink():
                if not slot.is_symlink() or slot.resolve() != assets:
                    raise RuntimeError('A different GUI release is active; refusing a stale rollback')
            before = self.inspect(allow_stopped_gui=True)
            self.control_guis('stop')
            self.restore(slot, backup, assets)
            self.control_guis('start')
            self.healthy()
            self.assert_core_pids(before['core_pids'])
            record.update(phase='rolled-back', rollback_core_pids=before['core_pids'])
            write_record(record_path, record)
            return {'record': str(record_path), **record}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'apply', 'rollback'))
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--record', type=Path)
    args = parser.parse_args()
    if socket.gethostname().split('.')[0] != EXPECTED_HOST:
        parser.error('This updater targets the reviewed srv1913330 shared-core installation')
    if os.geteuid() != 0:
        parser.error('Run with sudo to inspect installed paths and restart the GUI units')
    updater = GuiUpdater()
    if args.action == 'rollback':
        if not args.record:
            parser.error('rollback requires --record from the completed update output')
        result = updater.rollback(args.record)
    else:
        result = getattr(updater, args.action)(args.bundle)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
