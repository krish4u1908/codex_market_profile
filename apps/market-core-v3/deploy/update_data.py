#!/usr/bin/env python3
"""Install the report-quote data and bubble revision on the existing four-service workspace."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import time

sys.dont_write_bytecode = True
try:
    from . import update_gui as gui
except ImportError:
    import update_gui as gui

CORE_VERSION = '3.0.2'
GUI_VERSION = '3.0.11-gui-minute-oi-flow'
SCHEMA = 'CASH_VIX_INDICATOR_INPUTS_V1'
UNITS = gui.CORE_UNITS + gui.GUI_UNITS


def verify_bundle(root):
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root/'BUNDLE-MANIFEST.json').read_text())
    expected = {'BUNDLE-MANIFEST.json'}
    for item in manifest['files']:
        name = item['path']; relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or name in expected:
            raise ValueError('Unsafe or duplicate bundle path')
        path = root/relative; expected.add(name)
        if path.is_symlink() or not path.is_file() or gui.digest(path) != item['sha256']:
            raise ValueError('Bundle checksum failed: '+name)
    paths = list(root.rglob('*'))
    if any(p.is_symlink() for p in paths) or {p.relative_to(root).as_posix() for p in paths if p.is_file()} != expected:
        raise ValueError('Bundle contains missing or unlisted files')
    release = json.loads((root/'core/indicator-release.json').read_text())
    if release != {'version':CORE_VERSION,'schema':SCHEMA,'gui':GUI_VERSION}:
        raise ValueError('Wrong data update release')
    if json.loads((root/'gui/gui-release.json').read_text())['version'] != GUI_VERSION:
        raise ValueError('Wrong GUI release')
    return root


def control(action, units=UNITS):
    if action not in ('stop','start') or any(unit not in UNITS for unit in units):
        raise ValueError('Unexpected service action')
    subprocess.run(['systemctl',action,*units],check=True,text=True,capture_output=True,timeout=240)


class DataUpdater(gui.GuiUpdater):
    def inspect_data(self, allow_stopped=False):
        release = self.installed_release()
        states = {unit:gui.unit_status(unit) for unit in UNITS}
        for unit,state in states.items():
            if state.get('LoadState') != 'loaded': raise RuntimeError('Required service missing: '+unit)
            if not allow_stopped and (state.get('ActiveState') != 'active' or int(state.get('MainPID','0')) <= 0):
                raise RuntimeError('Required service not running: '+unit)
            name=unit.split('-')[0]; command=state.get('ExecStart','')
            if unit in gui.CORE_UNITS:
                expected=['-m market_core.server', '--config '+str(self.root/'current/config'/f'{name}.json')]
            else:
                port,core=gui.PORTS[name.upper()]
                expected=['-m market_core.gui','--instrument '+name.upper(),'--root '+str(self.root/'current/gui'),
                          '--core-port '+str(core),'--port '+str(port)]
            if any(not re.search(r'(?<!\S)'+re.escape(s)+r'(?=\s|;|$)',command) for s in expected):
                raise RuntimeError('Service command does not match this installation: '+unit)
        return release,states

    def check(self,bundle):
        bundle=verify_bundle(bundle)
        release,states=self.inspect_data()
        for role in ('core','gui'):
            if not (release/role).is_dir() or not (release/role).resolve().is_relative_to(self.root):
                raise RuntimeError('Installed '+role+' path is outside the installation')
        for name in ('requirements.txt','VENDOR_MANIFEST.json'):
            if (release/'core'/name).read_bytes() != (bundle/'core'/name).read_bytes():
                raise RuntimeError('This update requires unchanged dependencies and frozen vendor sources')
        for entry in json.loads((release/'core/VENDOR_MANIFEST.json').read_text())['files']:
            if gui.digest(release/'core'/entry['path']) != entry['sha256']:
                raise RuntimeError('Installed frozen source verification failed')
        configs={str(release/'config'/f'{name}.json'):gui.digest(release/'config'/f'{name}.json') for name in ('banknifty','nifty')}
        return dict(release=str(release),package=str(bundle),new_core_version=CORE_VERSION,new_gui_version=GUI_VERSION,
                    restart_services=list(UNITS),units=states,config_hashes=configs)

    def healthy_data(self,expected=True):
        deadline=time.monotonic()+90
        while True:
            try:
                for instrument,(_,port) in gui.PORTS.items():
                    health=gui.read_json(f'http://127.0.0.1:{port}/health')
                    if health.get('instrument') != instrument or health.get('error') or health.get('authority_instances',0)>1:
                        raise RuntimeError('Core identity or health check failed')
                    if expected and (health.get('version') != CORE_VERSION or health.get('indicator_inputs',{}).get('schema') != SCHEMA or health.get('option_report_inputs',{}).get('schema') != 'OPTION_REPORT_INPUTS_V1'):
                        raise RuntimeError('Core data revision not active')
                self.healthy(GUI_VERSION if expected else None)
                return
            except Exception:
                if time.monotonic()>=deadline:raise
                time.sleep(.5)

    def _start(self):
        control('start',gui.CORE_UNITS)
        control('start',gui.GUI_UNITS)

    def _restore(self,record):
        for role in ('core','gui'):
            item=record['paths'][role]
            self.restore(Path(item['slot']),Path(item['backup']),Path(item['assets']))

    def apply(self,bundle):
        with self.locked():
            checked=self.check(bundle);bundle=Path(checked['package']);release=Path(checked['release'])
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            stage=self.root/'data-releases'/('cash-vix-'+stamp)
            paths={}
            for role in ('core','gui'):
                assets=stage/role;shutil.copytree(bundle/role,assets)
                for p in [stage.parent,stage,assets,*assets.rglob('*')]:p.chmod(0o755 if p.is_dir() else 0o644)
                paths[role]=dict(slot=str(release/role),backup=str(release/(role+'-before-data-'+stamp)),assets=str(assets),original_target=str((release/role).resolve()))
            for entry in json.loads((bundle/'BUNDLE-MANIFEST.json').read_text())['files']:
                if entry['path'].startswith(('core/','gui/')) and gui.digest(stage/entry['path']) != entry['sha256']:
                    raise RuntimeError('Staged data update checksum failed')
            record=dict(phase='prepared',release=str(release),created_at=stamp,paths=paths,
                        config_hashes=checked['config_hashes'],new_core_version=CORE_VERSION,new_gui_version=GUI_VERSION)
            records=self.root/'data-update-records';records.mkdir(mode=0o700,exist_ok=True)
            record_path=records/(stamp+'.json');gui.write_record(record_path,record)
            try:
                control('stop')
                for unit in UNITS:
                    state=gui.unit_status(unit)
                    if state.get('ActiveState')=='active' or int(state.get('MainPID','0')):
                        raise RuntimeError('Service did not stop cleanly: '+unit)
                for item in paths.values():
                    slot=Path(item['slot']);slot.rename(item['backup']);slot.symlink_to(item['assets'],target_is_directory=True)
                self._start();self.healthy_data()
                if any(gui.digest(Path(p))!=sha for p,sha in checked['config_hashes'].items()):
                    raise RuntimeError('Installed configuration changed during update')
                record['phase']='installed';gui.write_record(record_path,record)
            except Exception as error:
                record.update(phase='failed',error=str(error))
                try:
                    control('stop');self._restore(record);self._start();self.healthy_data(False)
                    record['phase']='failed-restored'
                except Exception as recovery:record['recovery_error']=str(recovery)
                gui.write_record(record_path,record)
                raise RuntimeError('Data update failed; see '+str(record_path)) from error
            return dict(record=str(record_path),**record)

    def rollback(self,record_path):
        with self.locked():
            record_path=Path(record_path).resolve(strict=True)
            if record_path.parent != self.root/'data-update-records':raise ValueError('Use this installation data update record')
            record=json.loads(record_path.read_text());release,_=self.inspect_data(allow_stopped=True)
            stamp=record['created_at']
            if not re.fullmatch(r'\d{8}T\d{12}Z',stamp) or record['release']!=str(release):
                raise RuntimeError('Rollback record does not match this installation')
            for role,item in record['paths'].items():
                if role not in ('core','gui'):raise ValueError('Unknown rollback path')
                slot,backup,assets=(Path(item[k]) for k in ('slot','backup','assets'))
                if (slot!=release/role or backup!=release/(role+'-before-data-'+stamp)
                    or assets!=self.root/'data-releases'/('cash-vix-'+stamp)/role):
                    raise RuntimeError('Invalid rollback paths')
                if backup.exists() or backup.is_symlink():
                    if (slot.exists() or slot.is_symlink()) and (not slot.is_symlink() or slot.resolve()!=assets):
                        raise RuntimeError('A later update is active; refusing stale rollback')
                elif record['phase']!='prepared':raise RuntimeError('Rollback backup missing')
                elif slot.resolve()!=Path(item['original_target']):raise RuntimeError('Unmoved installation path changed after preparation')
            if set(record['paths'])!={'core','gui'}:raise ValueError('Rollback record is incomplete')
            control('stop');self._restore(record);self._start();self.healthy_data(False)
            record['phase']='rolled-back';gui.write_record(record_path,record)
            return dict(record=str(record_path),**record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('check','apply','rollback'))
    parser.add_argument('--bundle',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--record',type=Path)
    args=parser.parse_args()
    if os.geteuid()!=0:parser.error('Run with sudo to inspect services and apply this data update')
    if socket.gethostname().split('.')[0]!=gui.EXPECTED_HOST:parser.error('Unexpected installation host')
    updater=DataUpdater(gui.INSTALL_ROOT)
    if args.action=='rollback':
        if not args.record:parser.error('rollback requires --record')
        result=updater.rollback(args.record)
    else:result=getattr(updater,args.action)(args.bundle)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
