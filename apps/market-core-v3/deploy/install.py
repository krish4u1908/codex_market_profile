#!/usr/bin/env python3
"""First-install migration for the captured VPS; read-only check is the default.

No collector/auth/cron/user-manager changes. No old state is removed. Four new
units only. A failed activation stops them; explicit rollback does the same.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CORE))
from market_core.config import Config
from market_core.migration import migrate, sha256
from market_core.storage import atomic_write, encode

UNITS=('banknifty-core.service','nifty-core.service','banknifty-gui.service','nifty-gui.service')
OLD_PORTS=(8792,8794,8798,8803,8804,8896,8897,8899,8911,8912,8913,8914)
UNIT_ROOT=Path('/etc/systemd/system')


def run(argv, *, check=True):
    result=subprocess.run([str(x) for x in argv],text=True,capture_output=True,
        env=dict(os.environ,LC_ALL='C',SYSTEMD_PAGER='cat',SYSTEMD_COLORS='0'))
    if check and result.returncode:
        raise RuntimeError('Command failed: '+' '.join(map(str,argv))+'\n'+result.stderr[-2000:])
    return result


def prefix(scope):
    if scope=='system': return ['systemctl']
    if scope!='user:codexuser': raise ValueError('Unknown systemd scope')
    account=pwd.getpwnam('codexuser')
    runtime='/run/user/'+str(account.pw_uid)
    if not Path(runtime,'bus').exists():
        raise RuntimeError('Cannot verify codexuser units: its existing user bus is unavailable')
    return ['runuser','-u','codexuser','--','env','XDG_RUNTIME_DIR='+runtime,
        'DBUS_SESSION_BUS_ADDRESS=unix:path='+runtime+'/bus','systemctl','--user']


def unit_state(scope, name):
    output=run(prefix(scope)+['show',name,'--no-pager','--property=LoadState,ActiveState,SubState,UnitFileState,MainPID'])
    return dict(line.split('=',1) for line in output.stdout.splitlines() if '=' in line)


def retired_problem(row):
    if row.get('ActiveState') not in {'inactive','failed'}:
        return 'still active or unverifiable'
    if row.get('UnitFileState') in {'enabled','enabled-runtime','linked','linked-runtime','alias'}:
        return 'still enabled or linked'
    return None


def old_state_report():
    report=[]
    for unit in json.loads((CORE/'deploy/old-units.json').read_text()):
        state=unit_state(unit['scope'],unit['name'])
        report.append(dict(unit,**state,problem=retired_problem(state)))
    return report


def occupied_ports():
    output=run(['ss','-H','-ltn']).stdout
    ports=set()
    for line in output.splitlines():
        fields=line.split()
        if len(fields)>3:
            try: ports.add(int(fields[3].rsplit(':',1)[1]))
            except (ValueError,IndexError): pass
    return ports


def leftover_processes():
    """Find captured legacy entrypoints even when started outside systemd."""
    roots=['/home/bankadmin/divergence/releases/',
        '/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v']
    found=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid(): continue
        try:
            argv=(entry/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (OSError,PermissionError): continue
        if any(any(arg.startswith(root) for root in roots) for arg in argv[:3]):
            if any(Path(arg).name.startswith(('python','banknifty','nifty','streamlit')) for arg in argv[:2]):
                found.append({'pid':int(entry.name),'entrypoint':argv[:2]})
    return found


def read_deployment():
    cfg=json.loads((CORE/'deploy/deployment.json').read_text())
    # This installer is deliberately tied to the reviewed four-service layout.
    if set(cfg['instruments'])!={'BANKNIFTY','NIFTY'}: raise ValueError('Expected exactly two instruments')
    for field in ('service_user','service_group','collector_group'):
        if not re.fullmatch(r'[a-z_][a-z0-9_-]*',cfg[field]): raise ValueError('Invalid account')
    for field in ('install_root','state_root'):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+',cfg[field]): raise ValueError('Invalid installation path')
    return cfg


def core_config(cfg, instrument):
    item=cfg['instruments'][instrument];name=instrument.lower()
    return {'version':'3.0.0','instrument':instrument,'collector_root':item['collector_root'],
        'state_root':str(Path(cfg['state_root'])/name),'lock_path':'/run/market-core-'+name+'/core.lock',
        'host':'127.0.0.1','port':item['core_port'],'poll_seconds':10,
        'futures_symbols_by_session':item.get('futures_symbols_by_session',{})}


def config_object(raw):
    return Config(raw['instrument'],Path(raw['collector_root']).resolve(),Path(raw['state_root']).resolve(),
        Path(raw['lock_path']).resolve(),raw['host'],raw['port'],raw['poll_seconds'],raw['futures_symbols_by_session'])


def preflight(cfg, bundle):
    problems=[]
    if os.geteuid()!=0: problems.append('Run with sudo to inspect both system and user services')
    if socket.gethostname()!=cfg['expected_host']: problems.append('Expected host '+cfg['expected_host'])
    if sys.version_info<(3,11): problems.append('Python 3.11 or newer is required (captured VPS uses 3.12)')
    for kind,name in [('user',cfg['service_user']),('group',cfg['service_group']),('group',cfg['collector_group'])]:
        try: (pwd.getpwnam if kind=='user' else grp.getgrnam)(name)
        except KeyError: problems.append('Missing '+kind+' '+name)
    old=[]
    try:
        old=old_state_report()
        problems.extend(row['scope']+' '+row['name']+': '+row['problem'] for row in old if row['problem'])
        ports=occupied_ports()
        desired=[v[k] for v in cfg['instruments'].values() for k in ('core_port','gui_port')]
        problems.extend('Port still listening: '+str(p) for p in sorted(ports & set(OLD_PORTS+tuple(desired))))
        problems.extend('Legacy process still running: PID '+str(row['pid']) for row in leftover_processes())
    except (OSError,RuntimeError) as exc: problems.append(str(exc))
    if not (bundle/'gui/index.html').is_file(): problems.append('Built GUI missing; use the deployment ZIP or build_bundle.py')
    if not (bundle/'BUNDLE-MANIFEST.json').is_file(): problems.append('Bundle checksum manifest is missing')
    else:
        manifest=json.loads((bundle/'BUNDLE-MANIFEST.json').read_text())
        for row in manifest['files']:
            path=(bundle/row['path']).resolve()
            if bundle not in path.parents or not path.is_file() or sha256(path)!=row['sha256']:
                problems.append('Bundle verification failed: '+row['path'])
    for instrument,item in cfg['instruments'].items():
        config_object(core_config(cfg,instrument)).validate()
        collector=Path(item['collector_root'])
        state=Path(item['old_state'])
        if not collector.is_dir(): problems.append('Missing collector directory: '+str(collector))
        if not (state/'context.sqlite3').is_file(): problems.append('Existing V2 context.sqlite3 not found: '+str(state))
        if not (state/'engine').is_dir(): problems.append('Existing V2 engine journal directory not found: '+str(state))
        destination=Path(cfg['state_root'])/instrument.lower()
        if destination.exists(): problems.append('New state already exists; refusing overwrite: '+str(destination))
        if collector.is_dir():
            access=run(['runuser','-u',cfg['service_user'],'-g',cfg['service_group'],'-G',cfg['collector_group'],'--',
                sys.executable,'-c','from pathlib import Path; import sys; p=Path(sys.argv[1]); list(p.iterdir())',collector],check=False)
            if access.returncode: problems.append('Service account cannot read collector directory: '+str(collector))
    for unit in UNITS:
        if (UNIT_ROOT/unit).exists() or (UNIT_ROOT/unit).is_symlink(): problems.append('New unit name is already in use: '+unit)
    current=Path(cfg['install_root'])/'current'
    if current.exists() or current.is_symlink(): problems.append('An installed current release already exists; this is a first-install migration')
    return {'host':socket.gethostname(),'problems':problems,'old_units':old,
        'services':list(UNITS),'state_root':cfg['state_root'],'collector_changes':False}


def unit_text(cfg,instrument,role):
    name=instrument.lower();item=cfg['instruments'][instrument]
    current=Path(cfg['install_root'])/'current'
    python=current/'.venv/bin/python';core=current/'core'
    common=f'''[Unit]
Description={instrument} V3 {role}
After=network.target

[Service]
Type=simple
User={cfg['service_user']}
Group={cfg['service_group']}
WorkingDirectory={core}
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
UMask=0027
'''
    if role=='core':
        common+=f'''SupplementaryGroups={cfg['collector_group']}
RuntimeDirectory=market-core-{name}
ReadOnlyPaths={item['collector_root']}
ReadWritePaths={Path(cfg['state_root'])/name}
ExecStart={python} -m market_core.server --config {current}/config/{name}.json
TimeoutStopSec=180
'''
    else:
        common+=f'''ExecStart={python} -m market_core.gui --instrument {instrument} --root {current}/gui --core-port {item['core_port']} --port {item['gui_port']} --host 0.0.0.0
TimeoutStopSec=15
'''
    return common+'\n[Install]\nWantedBy=multi-user.target\n'


def stop_new(units=UNITS):
    errors=[]
    if any(unit not in UNITS for unit in units): raise ValueError('Unknown replacement unit')
    for unit in reversed(units):
        result=run(['systemctl','disable','--now',unit],check=False)
        if result.returncode: errors.append(unit+': '+result.stderr.strip())
    return errors


def status(cfg):
    report={'units':{},'endpoints':{}}
    for unit in UNITS: report['units'][unit]=unit_state('system',unit)
    for instrument,item in cfg['instruments'].items():
        for role,port in [('core',item['core_port']),('gui',item['gui_port'])]:
            try:
                with urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as response:
                    report['endpoints'][instrument+' '+role]=json.load(response)
            except Exception as exc: report['endpoints'][instrument+' '+role]={'error':str(exc)}
    return report


def install(cfg,bundle,cleanup_record):
    checked=preflight(cfg,bundle)
    if checked['problems']:
        print(json.dumps(checked,indent=2));raise RuntimeError('Preflight failed; no installation changes made')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    root=Path(cfg['install_root']);release=root/'releases'/('3.0.0-'+stamp)
    record=root/'install-records'/(stamp+'.json')
    report={'started_at':stamp,'phase':'preparing','release':str(release),
        'cleanup_record':str(Path(cleanup_record).resolve()) if cleanup_record else None,
        'created_units':[],'new_state_roots':[],'current_link_created':False}
    atomic_write(record,encode(report))
    print('Installation record: '+str(record),flush=True)
    activated=False
    try:
        release.mkdir(parents=True)
        for directory in ('core','gui'): shutil.copytree(bundle/directory,release/directory)
        print('Preparing the isolated Python environment…',flush=True)
        run([sys.executable,'-m','venv',release/'.venv'])
        python=release/'.venv/bin/python'
        run([python,'-m','pip','install','--disable-pip-version-check','-r',release/'core/requirements.txt'])
        # Verify dependencies and frozen imports before copying state or enabling units.
        for instrument in cfg['instruments']:
            run([python,'-c','import sys; sys.path.insert(0,sys.argv[1]); from market_core.vendor import load; load(sys.argv[2])',release/'core',instrument])
        release.joinpath('config').mkdir()
        uid=pwd.getpwnam(cfg['service_user']).pw_uid;gid=grp.getgrnam(cfg['service_group']).gr_gid
        Path(cfg['state_root']).mkdir(parents=True,exist_ok=True)
        # Check again after dependency installation, immediately before copying.
        blockers=[row for row in old_state_report() if row['problem']]
        if blockers or leftover_processes(): raise RuntimeError('An old service restarted before migration')
        for instrument,item in cfg['instruments'].items():
            raw=core_config(cfg,instrument);config=config_object(raw)
            config_file=release/'config'/(instrument.lower()+'.json')
            atomic_write(config_file,encode(raw))
            config_file.chmod(0o644)  # Paths/ports only; readable by the service account.
            print('Copying and verifying '+instrument+' state…',flush=True)
            report['new_state_roots'].append(str(config.state_root));atomic_write(record,encode(report))
            migration=migrate(config,item['old_state'],item['prepared'],item.get('prior'))
            for path in [config.state_root,*config.state_root.rglob('*')]:
                os.chown(path,uid,gid)
                path.chmod(0o750 if path.is_dir() else 0o640)
            print(instrument+': '+str(migration['retained_v2']['imported'])+' retained V2 sessions; '+
                str(sum(r['imported'] for r in migration['prepared']))+' prepared replays',flush=True)
            skipped=[row for group in migration['prepared'] for row in group['skipped']]
            if skipped: print('Review skipped replay imports in '+str(config.state_root/'migration.json'),flush=True)
        report['phase']='state-copied';atomic_write(record,encode(report))
        current=root/'current'
        current.symlink_to(release)
        report['current_link_created']=True;atomic_write(record,encode(report))
        for instrument in cfg['instruments']:
            for role in ('core','gui'):
                unit=instrument.lower()+'-'+role+'.service'
                path=UNIT_ROOT/unit
                # Exclusive creation: do not overwrite an unrelated existing unit.
                with path.open('x') as handle: handle.write(unit_text(cfg,instrument,role))
                report['created_units'].append(unit);atomic_write(record,encode(report))
        run(['systemctl','daemon-reload'])
        activated=True
        for unit in UNITS: run(['systemctl','enable','--now',unit])
        report['phase']='verifying';atomic_write(record,encode(report))
        deadline=time.monotonic()+45
        while True:
            result=status(cfg)
            connected=all(value.get('instrument') for value in result['endpoints'].values())
            active=all(value.get('ActiveState')=='active' for value in result['units'].values())
            if connected and active:
                failures={name:value['error'] for name,value in result['endpoints'].items() if value.get('error')}
                if failures: raise RuntimeError('Core initialization failed: '+json.dumps(failures))
                break
            if time.monotonic()>deadline: raise RuntimeError('New services did not become reachable within 45 seconds')
            time.sleep(1)
        report.update(phase='installed',verification=result)
        atomic_write(record,encode(report))
        print(json.dumps(result,indent=2))
        print('Installed. Keep the old source and state until a live market session has been verified.')
    except BaseException as exc:
        report.update(phase='failed',error=type(exc).__name__+': '+str(exc))
        if activated: report['stop_errors']=stop_new()
        atomic_write(record,encode(report))
        print('Installation stopped. Existing source/state are intact. Recovery record: '+str(record),file=sys.stderr)
        raise


def rollback(cfg,record_path):
    record_path=Path(record_path).resolve(strict=True)
    report=json.loads(record_path.read_text())
    root=Path(cfg['install_root']).resolve()
    release=Path(report['release']).resolve()
    if release.parent!=root/'releases' or record_path.parent!=root/'install-records':
        raise ValueError('This is not an installation record from this layout')
    if os.geteuid()!=0 or socket.gethostname()!=cfg['expected_host']:
        raise RuntimeError('Rollback must run as root on '+cfg['expected_host'])
    errors=stop_new(report['created_units']) if report.get('created_units') else []
    if errors: raise RuntimeError('Could not stop every new unit: '+json.dumps(errors))
    # Keep all state, release and unit files as evidence; only disable services.
    report['phase']='rolled-back';report['rolled_back_at']=datetime.now(timezone.utc).isoformat()
    atomic_write(record_path,encode(report))
    print('The four replacement services are stopped and disabled. All state is retained.')
    if report.get('cleanup_record'):
        print('To restore the former GUI services, run:')
        import shlex
        print('sudo python3 '+shlex.quote(str(CORE/'deploy/market_cleanup.py'))+' restore '+shlex.quote(report['cleanup_record']))
    else:
        print('Use the original market_cleanup.py restore command and its saved restore.json if you want the former services back.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',nargs='?',default='check',choices=['check','install','status','rollback'])
    parser.add_argument('--bundle',type=Path,default=CORE.parent)
    parser.add_argument('--cleanup-record',help='Original cleanup restore.json; retained for rollback instructions')
    parser.add_argument('--record',help='Installation record printed by install; required for rollback')
    args=parser.parse_args();cfg=read_deployment()
    if args.action=='check':
        result=preflight(cfg,args.bundle.resolve());print(json.dumps(result,indent=2));return 1 if result['problems'] else 0
    if args.action=='install': install(cfg,args.bundle.resolve(),args.cleanup_record)
    if args.action=='status': print(json.dumps(status(cfg),indent=2))
    if args.action=='rollback':
        if not args.record: parser.error('rollback requires --record')
        rollback(cfg,args.record)
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,RuntimeError) as exc: sys.exit(str(exc))
