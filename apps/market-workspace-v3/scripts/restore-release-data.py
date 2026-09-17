#!/usr/bin/env python3
"""Restore optional research data from the exact, locally supplied release ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'scripts/release-data-3.0.18.json').read_text())
    digest = hashlib.sha256()
    with args.package.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != manifest['sha256']:
        parser.error('Package SHA256 does not match the delivered 3.0.18 release.')
    pending = []
    with zipfile.ZipFile(args.package) as archive:
        for entry in manifest['files']:
            target = (root / entry['path']).resolve()
            if not target.is_relative_to(root):
                parser.error('Manifest target is outside the source directory.')
            data = archive.read(manifest['prefix'] + entry['path'])
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                parser.error('Research data verification failed: ' + entry['path'])
            pending.append((target, data))
    # Verify all entries before writing any data. Extract only the manifest allowlist.
    for target, data in pending:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print('Restored ' + str(target.relative_to(root)))


if __name__ == '__main__':
    main()
