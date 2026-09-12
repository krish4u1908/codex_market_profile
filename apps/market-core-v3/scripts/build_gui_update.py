#!/usr/bin/env python3
"""Build a small GUI-only update from the verified full deployment bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

CORE = Path(__file__).resolve().parents[1]
RELEASE = '3.0.7-gui-oi-entry-manual-vpoc'


def build(deployment_bundle, output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'market-workspace-v3-gui-update'
        root.mkdir()
        with zipfile.ZipFile(deployment_bundle) as source:
            prefix = 'market-workspace-v3/'
            manifest = json.loads(source.read(prefix + 'BUNDLE-MANIFEST.json'))
            for entry in manifest['files']:
                name = entry['path']
                if not (name.startswith('gui/') or name == 'THIRD_PARTY_LICENSES.txt'):
                    continue
                path = root / name
                if not path.resolve().is_relative_to(root):
                    raise ValueError('Invalid deployment bundle path')
                content = source.read(prefix + name)
                if hashlib.sha256(content).hexdigest() != entry['sha256']:
                    raise ValueError('Deployment bundle checksum failed: ' + name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        for source, name in [(CORE / 'deploy/update_gui.py', 'update_gui.py'),
                             (CORE / 'GUI_UPDATE.md', 'GUI_UPDATE.md'),
                             (CORE.parent / 'market-workspace-v3/OI_ENTRY_REPLAY.md', 'OI_ENTRY_REPLAY.md')]:
            (root / name).write_bytes(source.read_bytes())
        files = [{'path': p.relative_to(root).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(root.rglob('*')) if p.is_file()]
        (root / 'GUI-UPDATE-MANIFEST.json').write_text(json.dumps({'release': RELEASE, 'files': files}, indent=2) + '\n')
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(root.parent))
    return {'path': str(output), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.deployment_bundle, args.output), indent=2))
