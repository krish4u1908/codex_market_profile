#!/usr/bin/env python3
"""Export one existing V2 SQLite snapshot; never start or mutate an engine."""
import argparse
import json
import sqlite3
from datetime import date
from pathlib import Path


def export_session(database, session, profile):
    date.fromisoformat(session)
    if profile not in ('banknifty-v200', 'nifty-v200'):
        raise ValueError('Select a V2 workspace profile')
    path = Path(database).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')  # One coherent read, including the existing WAL.
        decisions = [json.loads(body) for (body,) in db.execute(
            'SELECT body FROM decisions WHERE day=? ORDER BY cutoff', (session,))]
        inputs = {}
        for kind, field in [('price', 'price'), ('oi', 'futures_oi'),
                            ('cash', 'cash_vix'), ('options', 'option_strike_oi'),
                            ('inventory', 'intraday_inventory')]:
            inputs[field] = [json.loads(body) for (body,) in db.execute(
                'SELECT body FROM inputs WHERE day=? AND kind=? ORDER BY timestamp,identity',
                (session, kind))]
        selected = db.execute('SELECT body FROM selections WHERE day=?', (session,)).fetchone()
        inputs['strike_selection'] = json.loads(selected[0]) if selected else {}
    if not inputs['price']:
        raise ValueError('No retained prices for this session')
    instrument = 'NIFTY' if profile == 'nifty-v200' else 'BANKNIFTY'
    inputs.update(session=session, instrument=instrument, provenance={
        'note': 'Original receipt inputs read from the existing V2 context database. Decisions are unchanged.'})
    return dict(version='2.0.0', baseline_version='1.0.62', session=session,
                instrument=instrument, workspace_profile=profile,
                decisions=decisions, price_history=[], chart_inputs=inputs,
                provenance={'source': 'READ_ONLY_V2_CONTEXT_DATABASE'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='Existing V2 context.sqlite3')
    parser.add_argument('--session', required=True, help='YYYY-MM-DD')
    parser.add_argument('--profile', required=True, choices=['banknifty-v200', 'nifty-v200'])
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = export_session(args.database, args.session, args.profile)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, allow_nan=False) + '\n')
    print(f'Exported {len(result["decisions"])} unchanged decisions to {target}')


if __name__ == '__main__':
    main()
