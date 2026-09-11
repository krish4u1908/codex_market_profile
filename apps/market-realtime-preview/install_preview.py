#!/usr/bin/env python3
"""Install separate preview web services. Never replace or restart production services."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import time
from urllib.request import urlopen

VERSION = '3.1.0-preview.1'
ORIGINAL = ('banknifty-core.service', 'nifty-core.service', 'banknifty-gui.service', 'nifty-gui.service')
PREVIEW = ('banknifty-display-preview.service', 'nifty-display-preview.service')
UNIT_DIRECTORY = Path('/etc/systemd/system')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_bundle(bundle):
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle / 'PREVIEW-MANIFEST.json').read_bytes())
    if manifest.get('version') != VERSION:
        raise ValueError('Wrong preview package version')
    expected = {entry['path']: entry['sha256'] for entry in manifest['files']}
    if len(expected) != len(manifest['files']):
        raise ValueError('Duplicate package entry')
    if any(p.is_symlink() for p in bundle.rglob('*')):
        raise ValueError('Package must not contain symbolic links')
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob('*')
              if p.is_file() and p != bundle / 'PREVIEW-MANIFEST.json'}
    if actual != set(expected):
        raise ValueError('Extract the preview into a new empty directory; package contains missing or extra files')
    for relative, wanted in expected.items():
        path = bundle / relative
        if path.is_symlink() or not path.resolve().is_relative_to(bundle) or digest(path) != wanted:
            raise ValueError('Package checksum/path verification failed: ' + relative)
    if json.loads((bundle / 'gui/gui-release.json').read_bytes()).get('version') != VERSION:
        raise ValueError('Preview GUI version mismatch')
    return bundle


def systemctl(*args):
    return subprocess.check_output(['systemctl', *args], text=True).strip()


def unit_state(unit):
    text = systemctl('show', unit, '--property=MainPID,User,ActiveState,ExecStart')
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def missing_unit(unit):
    # systemd versions can return a nonzero status for an absent unit. Accept
    # only the explicit property value; other query failures must still stop check.
    result = subprocess.run(['systemctl', 'show', unit, '--property=LoadState', '--value'],
                            text=True, capture_output=True, check=False)
    value = result.stdout.strip()
    if value == 'not-found':
        return True
    if result.returncode:
        raise ValueError('Cannot inspect preview service: ' + unit)
    return False


def quote(value):
    return json.dumps(str(value)).replace('%', '%%')


def unit_text(instrument, user, root, config, collector, port, host):
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', user) or user == 'root':
        raise ValueError('Preview requires the non-root account used by the existing core')
    command = ' '.join(quote(v) for v in ['/usr/bin/python3', '-B', root / 'realtime_preview.py',
        '--config', config, '--root', root / 'gui', '--port', port, '--host', host])
    return f'''[Unit]
Description={instrument} read-only near real-time display preview {VERSION}
After=network.target {instrument.lower()}-core.service

[Service]
Type=simple
User={user}
ExecStart={command}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadOnlyPaths={quote(config)} {quote(collector)} {quote(root)}
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
RestrictSUIDSGID=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
MemoryMax=256M
CPUQuota=20%
Nice=10
IOSchedulingClass=idle
UMask=0077

[Install]
WantedBy=multi-user.target
'''


def check(args):
    bundle = verify_bundle(args.bundle)
    base = args.base.resolve(strict=True)
    target = args.prefix.resolve() / VERSION
    if target.exists():
        raise ValueError('This preview version is already installed: ' + str(target))
    states = {unit: unit_state(unit) for unit in ORIGINAL}
    configs, units, hashes = {}, {}, {}
    ports = [args.banknifty_port, args.nifty_port]
    if len(set(ports)) != 2 or any(p in {8920, 8921, 8922, 8923} or not 1024 <= p <= 65535 for p in ports):
        raise ValueError('Two separate, non-production preview ports are required')
    if args.host not in {'127.0.0.1', '0.0.0.0'}:
        raise ValueError('Host must be 127.0.0.1 or 0.0.0.0')
    for unit, state in states.items():
        if state.get('ActiveState') != 'active' or int(state.get('MainPID', '0')) <= 0:
            raise ValueError('Existing service must be healthy before adding a preview: ' + unit)
    for instrument, port, name in zip(('BANKNIFTY', 'NIFTY'), ports, PREVIEW):
        if (UNIT_DIRECTORY / name).exists() or not missing_unit(name):
            raise ValueError('Preview service name already exists: ' + name)
        config_path = base / 'config' / (instrument.lower() + '.json')
        config = json.loads(config_path.read_bytes())
        if config.get('instrument') != instrument or config.get('host', '127.0.0.1') != '127.0.0.1':
            raise ValueError('Core identity or loopback configuration mismatch')
        if int(config['port']) in ports:
            raise ValueError('Preview port overlaps an existing core port')
        state = states[instrument.lower() + '-core.service']
        if 'market_core.server' not in state.get('ExecStart', ''):
            raise ValueError('Unexpected existing core command')
        user = state.get('User', '')
        account = pwd.getpwnam(user)
        with urlopen('http://127.0.0.1:' + str(config['port']) + '/api/health', timeout=5) as response:
            health = json.load(response)
        if health.get('instrument') != instrument or health.get('version') != '3.0.1' or health.get('error'):
            raise ValueError('Expected a healthy existing 3.0.1 core')
        collector = Path(config['collector_root']).resolve(strict=True)
        for protected in (base, collector, Path(config['state_root']).resolve()):
            if target == protected or target.is_relative_to(protected) or protected.is_relative_to(args.prefix.resolve()):
                raise ValueError('Preview installation must be outside the existing code/data directories')
        with socket.socket() as sock:
            sock.bind((args.host, port))
        units[name] = unit_text(instrument, user, target, config_path, collector, port, args.host)
        configs[instrument] = dict(path=str(config_path), collector=str(collector), user=account.pw_name, port=port)
        hashes[str(config_path)] = digest(config_path)
    return dict(version=VERSION, package=str(bundle), destination=str(target), configs=configs,
                config_hashes=hashes, existing_units=states, preview_units=units,
                restarts_existing_services=False, adds_engines=False)


def apply(args):
    if os.geteuid() != 0:
        raise PermissionError('Run apply with sudo')
    checked = check(args)
    target = Path(checked['destination'])
    created_units = []
    owned_target = False
    try:
        target.mkdir(parents=True, exist_ok=False)
        owned_target = True
        shutil.copytree(checked['package'], target, dirs_exist_ok=True)
        for path in [target, *target.rglob('*')]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        for name, text in checked['preview_units'].items():
            path = UNIT_DIRECTORY / name
            with path.open('x') as handle:
                handle.write(text)
            created_units.append(name)
        systemctl('daemon-reload')
        systemctl('enable', '--now', *PREVIEW)
        for name in PREVIEW:
            if unit_state(name).get('ActiveState') != 'active':
                raise ValueError('Preview service did not start: ' + name)
        for instrument, config in checked['configs'].items():
            ready = False
            for attempt in range(20):
                try:
                    with urlopen('http://127.0.0.1:' + str(config['port']) + '/health', timeout=1) as response:
                        health = json.load(response)
                    ready = health.get('version') == VERSION and health.get('instrument') == instrument and health.get('owns_engine') is False
                    if ready:
                        break
                except OSError:
                    pass
                time.sleep(.2)
            if not ready:
                raise ValueError('Preview endpoint did not become ready: ' + instrument)
        after = {unit: unit_state(unit) for unit in ORIGINAL}
        if any(after[u].get('MainPID') != checked['existing_units'][u].get('MainPID') for u in ORIGINAL):
            raise ValueError('An existing process changed during installation; inspect it before continuing')
        if any(digest(path) != wanted for path, wanted in checked['config_hashes'].items()):
            raise ValueError('An existing config changed during installation')
        record = dict(version=VERSION, installed_at=datetime.now(timezone.utc).isoformat(),
            destination=str(target), original_pids={u: after[u]['MainPID'] for u in ORIGINAL},
            preview_ports={key: value['port'] for key, value in checked['configs'].items()},
            config_hashes=checked['config_hashes'])
        (target.parent / ('install-' + VERSION + '.json')).write_text(json.dumps(record, indent=2) + '\n')
        return record
    except Exception:
        for name in created_units:
            subprocess.run(['systemctl', 'disable', '--now', name], check=False, capture_output=True)
            (UNIT_DIRECTORY / name).unlink(missing_ok=True)
        if created_units:
            subprocess.run(['systemctl', 'daemon-reload'], check=False, capture_output=True)
        if owned_target and target.exists():
            shutil.rmtree(target)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'apply'))
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--base', type=Path, default=Path('/opt/market-workspace-v3/current'))
    parser.add_argument('--prefix', type=Path, default=Path('/opt/market-workspace-preview'))
    parser.add_argument('--banknifty-port', type=int, default=8930)
    parser.add_argument('--nifty-port', type=int, default=8931)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    print(json.dumps(check(args) if args.action == 'check' else apply(args), indent=2))
