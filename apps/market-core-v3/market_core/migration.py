"""Offline copies and replay imports; never start a calculation authority."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

from .config import session_date
from .storage import atomic_write, encode, PublishedStore


def sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def copy_state(source, target):
    """Caller must verify old producers stopped. Refuse overwrites and links."""
    source, target = Path(source).resolve(strict=True), Path(target).resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Source and target state must not overlap')
    if target.exists():
        raise FileExistsError('Target state already exists: '+str(target))
    files = sorted(source.rglob('*'))
    if any(p.is_symlink() or not (p.is_dir() or p.is_file()) for p in files):
        raise ValueError('State contains a link or special file; inspect it before migration')
    target.mkdir(parents=True)
    result = []
    databases = {p for p in files if p.is_file() and p.suffix in {'.sqlite3','.sqlite','.db'}}
    companions = {Path(str(p)+suffix) for p in databases for suffix in ('-wal','-shm','-journal')}
    for path in files:
        if not path.is_file() or path in companions:
            continue
        relative = path.relative_to(source)
        output = target/relative
        output.parent.mkdir(parents=True,exist_ok=True)
        original = sha256(path)
        if path in databases:
            # Include committed WAL pages in one SQLite read transaction.
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(output) as dst:
                src.execute('PRAGMA query_only=ON')
                src.backup(dst)
                if dst.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('SQLite integrity failure: '+str(relative))
        else:
            shutil.copy2(path,output)
        if sha256(path) != original:
            raise RuntimeError('Old state changed during copy: '+str(relative))
        copied = sha256(output)
        if path not in databases and copied != original:
            raise RuntimeError('State copy verification failed: '+str(relative))
        result.append(dict(path=str(relative),source_sha256=original,destination_sha256=copied,
            method='sqlite-backup' if path in databases else 'byte-copy'))
    return result


def unpack(value):
    if isinstance(value,list): return value
    return [dict(zip(value.get('fields',[]),row)) for row in value.get('rows',[])] if isinstance(value,dict) else []


def validate_import(payload, config, version):
    session_date(payload.get('session',''))
    profile = config.profile(version)
    if payload.get('workspace_profile') not in {None,profile}:
        raise ValueError('Replay workspace does not match destination')
    if payload.get('baseline_version') not in {None,'1.0.62'}:
        raise ValueError('Replay declares another reference version')
    if version=='v1062' and payload.get('schema')!='NEW_DIVERGENCE_BROWSER_PAYLOAD_V1':
        raise ValueError('Expected a prepared v1.0.62 browser payload')
    if version=='v200' and (payload.get('version')!='2.0.0' or not isinstance(payload.get('decisions'),list)):
        raise ValueError('Expected a native V2 session')
    inputs = payload.get('chart_inputs',payload)
    if inputs.get('session',payload['session'])!=payload['session']:
        raise ValueError('Mixed session inputs')
    identities=[payload.get('instrument'),inputs.get('instrument'),payload.get('index_symbol'),payload.get('futures_symbol')]
    for field in ('futures_oi','option_strike_oi'):
        identities.extend(row.get('symbol') for row in unpack(inputs.get(field)))
    for identity in identities:
        if not identity: continue
        symbol=str(identity).upper()
        recognized = 'BANKNIFTY' if 'BANKNIFTY' in symbol or 'NIFTYBANK' in symbol else 'NIFTY' if 'NIFTY' in symbol else None
        if recognized and recognized != config.instrument:
            raise ValueError('Replay contains the other instrument')
    if version=='v1062' and not unpack(inputs.get('price')):
        raise ValueError('Replay has no synchronized price history')
    if version=='v200' and not (unpack(inputs.get('price')) or payload.get('price_history')):
        raise ValueError('Replay has no retained price history')
    return dict(payload,workspace_profile=profile,instrument=config.instrument)


def import_prepared(config, root, version):
    root=Path(root).resolve()
    if not root.is_dir(): return dict(root=str(root),imported=0,skipped=[],note='Directory absent')
    candidates=set()
    excluded=set()
    catalog=root/'catalog.json'
    if catalog.is_file():
        raw=json.loads(catalog.read_text())
        entries=raw if isinstance(raw,list) else raw.get('sessions',[])
        for row in entries:
            filename=row.get('payload') or row.get('file') or (str(row.get('session',''))+'.json')
            path=(root/filename).resolve()
            if root not in path.parents:
                raise ValueError('Prepared catalog path escapes its directory')
            if row.get('eligible') is False:
                excluded.add(path)
                continue
            if path.is_file(): candidates.add(path)
    for directory in (root,root/'sessions'):
        for path in directory.glob('????-??-??.json*'):
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json(\.gz)?',path.name): candidates.add(path)
    store=PublishedStore(config)
    report=dict(root=str(root),imported=0,skipped=[])
    for path in sorted(candidates-excluded):
        try:
            if path.is_symlink(): raise ValueError('Linked payload is not an offline copy')
            body=path.read_bytes()
            payload=json.loads(gzip.decompress(body) if body[:2]==b'\x1f\x8b' else body)
            bound=validate_import(payload,config,version)
            key='import-'+bound['session']+'-'+hashlib.sha256(encode(bound)).hexdigest()[:12]
            store.publish(config.profile(version),bound,source='imported',key=key)
            report['imported']+=1
        except (ValueError,KeyError,OSError,TypeError) as exc:
            report['skipped'].append(dict(file=str(path),reason=str(exc)))
    return report


def export_retained_v2(config):
    path=config.state_root/'runtime/context.sqlite3'
    if not path.is_file(): return {'imported':0,'note':'No retained context database'}
    store=PublishedStore(config)
    count=0
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        days=[row[0] for row in db.execute('SELECT DISTINCT day FROM inputs WHERE kind=? ORDER BY day',('price',))]
        for day in days:
            session_date(day)
            inputs={'session':day,'instrument':config.instrument}
            for kind,field in [('price','price'),('oi','futures_oi'),('volume','futures_volume'),('cash','cash_vix'),('inventory','intraday_inventory'),('options','option_strike_oi')]:
                inputs[field]=[json.loads(row[0]) for row in db.execute('SELECT body FROM inputs WHERE day=? AND kind=? ORDER BY timestamp,identity',(day,kind))]
            selection=db.execute('SELECT body FROM selections WHERE day=?',(day,)).fetchone()
            inputs['strike_selection']=json.loads(selection[0]) if selection else {}
            decisions=[json.loads(row[0]) for row in db.execute('SELECT body FROM decisions WHERE day=? ORDER BY cutoff',(day,))]
            payload=dict(version='2.0.0',baseline_version='1.0.62',instrument=config.instrument,
                workspace_profile=config.profile('v200'),session=day,decisions=decisions,
                price_history=[],chart_inputs=inputs,provenance={'source':'MIGRATED_RECORDED_V2_CONTEXT',
                    'history_note':'Original live publications retained. Missing strike receipts remain unavailable.'})
            store.publish(config.profile('v200'),payload,source='migrated',key='migrated-'+day)
            count+=1
    return {'imported':count}


def migrate(config, old_state, prepared, prior=None):
    if config.state_root.exists(): raise FileExistsError('New state root already exists: '+str(config.state_root))
    report={'instrument':config.instrument,'old_state':str(old_state),'new_state':str(config.state_root)}
    report['runtime_files']=copy_state(old_state,config.state_root/'runtime')
    if prior and Path(prior).is_dir():
        report['prior_files']=copy_state(prior,config.state_root/'prior-context')
    report['retained_v2']=export_retained_v2(config)
    report['prepared']=[import_prepared(config,path,version) for version,path in prepared.items()]
    atomic_write(config.state_root/'migration.json',encode(report))
    return report
