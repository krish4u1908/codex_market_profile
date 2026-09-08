#!/usr/bin/env python3
"""Package source + built GUI; recordings, databases and environments excluded."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

CORE=Path(__file__).resolve().parents[1]
GUI=CORE.parent/'market-workspace-v3'
EXCLUDED={'__pycache__','.venv','node_modules','dist','build','.git','data'}


def build(output):
    if not (GUI/'dist/index.html').is_file(): raise ValueError('Build the frontend first: npm run build')
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'market-workspace-v3';root.mkdir()
        for source,label in [(CORE,'core'),(GUI/'dist','gui')]:
            for path in sorted(source.rglob('*')):
                relative=path.relative_to(source)
                if any(part in EXCLUDED or part.startswith('.') for part in relative.parts): continue
                if not path.is_file() or path.is_symlink() or path.suffix in {'.pyc','.zip','.gz','.sqlite','.sqlite3','.db'}: continue
                dest=root/label/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        shutil.copyfile(CORE/'DEPLOYMENT.md',root/'INSTALL.md')
        notices=[]
        npm_lock=GUI/'node_modules/.package-lock.json'
        packages=json.loads(npm_lock.read_text()).get('packages',{}) if npm_lock.is_file() else {}
        for package in sorted(packages):
            directory=GUI/package
            for path in sorted(directory.glob('*')):
                if path.is_file() and path.name.lower().startswith(('license','licence','copying')):
                    try: notices.append(package+' / '+path.name+'\n'+path.read_text())
                    except UnicodeDecodeError: continue
        for path in sorted((GUI/'vendor').glob('*.LICENSE.md')):
            notices.append(str(path.relative_to(GUI))+'\n'+path.read_text())
        (root/'THIRD_PARTY_LICENSES.txt').write_text('\n\n'.join(notices))
        files=[]
        for path in sorted(root.rglob('*')):
            if path.is_file(): files.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        (root/'BUNDLE-MANIFEST.json').write_text(json.dumps({'version':'3.0.0','created_at':datetime.now(timezone.utc).isoformat(),'files':files},indent=2)+'\n')
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file(): archive.write(path,str(path.relative_to(root.parent)))
    return {'path':str(output),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(files)+1}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output),indent=2))
