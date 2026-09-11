#!/usr/bin/env python3
"""Build the isolated trial package; intentionally excludes the core and its installers."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
GUI = ROOT.parent / 'market-workspace-v3'
VERSION = '3.1.0-preview.1'


def build(output):
    if not (GUI / 'dist/index.html').is_file():
        raise ValueError('Build the GUI first')
    if json.loads((GUI / 'dist/gui-release.json').read_bytes())['version'] != VERSION:
        raise ValueError('Build the preview branch, not the stable GUI')
    with tempfile.TemporaryDirectory() as temporary:
        package = Path(temporary) / 'market-workspace-realtime-preview'
        # Local imported recordings can exist in an otherwise clean developer build.
        # This live preview obtains confirmed history from the existing core only.
        shutil.copytree(GUI / 'dist', package / 'gui',
                        ignore=shutil.ignore_patterns('data', '*.gz', '*.zip', '*.sqlite*', '*.db'))
        for name in ('realtime_preview.py', 'install_preview.py', 'README.md'):
            shutil.copyfile(ROOT / name, package / name)
        notices = []
        lock = GUI / 'node_modules/.package-lock.json'
        packages = json.loads(lock.read_bytes()).get('packages', {}) if lock.exists() else {}
        for relative in sorted(packages):
            for path in (GUI / relative).glob('*'):
                if path.is_file() and path.name.lower().startswith(('license', 'licence', 'copying')):
                    try:
                        notices.append(relative + '/' + path.name + '\n' + path.read_text())
                    except UnicodeDecodeError:
                        pass
        (package / 'THIRD_PARTY_LICENSES.txt').write_text('\n\n'.join(notices))
        files = [{'path': p.relative_to(package).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in sorted(package.rglob('*')) if p.is_file()]
        (package / 'PREVIEW-MANIFEST.json').write_text(json.dumps({'version': VERSION, 'files': files}, indent=2) + '\n')
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(package.parent))
    return dict(path=str(output), bytes=output.stat().st_size, sha256=hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
