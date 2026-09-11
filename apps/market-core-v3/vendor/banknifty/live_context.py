"""Direct collector v2 runtime; immutable v2 context publications in own SQLite DB."""
import collections
import json
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
import analyze as a


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class LiveContext:
    def __init__(self, state_directory, collector_root, poll_seconds=10, futures_symbols_by_session=None):
        self.root = Path(state_directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.collector_root = collector_root
        self.source = None
        self.futures_symbols_by_session = futures_symbols_by_session
        self.poll_seconds = max(5, poll_seconds)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.error = None
        self.last_success = None
        self._chart_cache = None
        self.db = sqlite3.connect(self.root / 'context.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS inputs(day TEXT, kind TEXT, identity TEXT,
             timestamp REAL, body TEXT, PRIMARY KEY(day,kind,identity));
          CREATE TABLE IF NOT EXISTS decisions(day TEXT, cutoff REAL, body TEXT,
             PRIMARY KEY(day,cutoff));
          CREATE TABLE IF NOT EXISTS selections(day TEXT PRIMARY KEY, body TEXT);
        ''')
        self.db.commit()

    def _store(self, day, kind, rows, now):
        for source in rows:
            row = dict(source)
            t = a.ts(row['t'])
            if t > now or a.ist(t)[:10] != day:
                continue
            identity = encoded([row['t'], row.get('symbol'), row.get('family'), row.get('minute_ist')])
            self.db.execute('INSERT OR IGNORE INTO inputs VALUES(?,?,?,?,?)',
                            (day, kind, identity, t, encoded(row)))

    def _rows(self, day, kind, through):
        return [dict(json.loads(body), _t=t) for t, body in self.db.execute(
            'SELECT timestamp,body FROM inputs WHERE day=? AND kind=? AND timestamp<=? ORDER BY timestamp,identity',
            (day, kind, through))]

    def ingest(self, snapshot, now=None):
        now = time.time() if now is None else now
        day = snapshot['session']
        datetime.strptime(day, '%Y-%m-%d')
        if snapshot.get('runtime_version') != '2.0.0':
            raise ValueError('Expected v2.0.0 internal runtime; received '+str(snapshot.get('runtime_version')))
        if snapshot.get('observations_sampled'):
            raise ValueError('Source returned sampled history; full history is required')
        profile = snapshot['profile']
        prices = [dict(t=r['timestamp'], i=r['index_price'], b=r['basis'])
                  for r in snapshot.get('observations', [])]
        with self.lock, self.db:
            self._store(day, 'price', prices, now)
            for kind, field in [('oi','futures_oi'), ('volume','futures_volume'),
                                ('inventory','inventory_rows'), ('cash','cash_vix'),
                                ('options','option_strike_oi')]:
                self._store(day, kind, profile.get(field, []), now)
            self._store(day, 'options', profile.get('selected_option_flow', []), now)
            selection = profile.get('strike_selection', {})
            if selection.get('available') and a.ts(selection['selected_at']) <= now:
                self.db.execute('INSERT OR IGNORE INTO selections VALUES(?,?)', (day, encoded(selection)))
            # Never replay historical calls as newly published live contexts.
            # Background polls publish only the current completed minute.
            cutoff = int(now // 60) * 60
            if a.ist(now)[:10] != day or not (a.ts(day+'T09:46:00+05:30') <= cutoff <= a.ts(day+'T15:30:00+05:30')):
                self.last_success = now
                self.error = None
                return False
            if self.db.execute('SELECT 1 FROM decisions WHERE day=? AND cutoff=?', (day,cutoff)).fetchone():
                self.last_success = now
                self.error = None
                return False
            # Wait briefly for the source's completed-minute publication.
            if now-cutoff < 5:
                return False
            price = self._rows(day, 'price', cutoff-0.000001)
            if not price or cutoff-price[-1]['_t'] > 15:
                raise ValueError('Price source is stale for the current completed minute')
            states = a.price_states(price, day)
            state = states.get(float(cutoff), {})
            oi = self._rows(day, 'oi', cutoff-0.000001)
            volume = self._rows(day, 'volume', cutoff-0.000001)
            inventory = self._rows(day, 'inventory', cutoff-0.000001)
            cash = self._rows(day, 'cash', now)
            for r in cash:
                r['_minute'] = a.ts(r['minute_ist'])
            cash.sort(key=lambda r:r['_minute'])
            cash = [r for r in cash if r['_minute'] < cutoff]
            cash_features = {}
            if cash and now-a.ts(cash[-1].get('source_published_at',cash[-1]['t'])) <= 120:
                cash_features = a.cash_features(cash,cutoff,now)
            contracts = collections.defaultdict(list)
            for r in self._rows(day, 'options', cutoff-0.000001):
                contracts[r['symbol']].append(r)
            saved = self.db.execute('SELECT body FROM selections WHERE day=?',(day,)).fetchone()
            selection = json.loads(saved[0]) if saved else {}
            vs = a.Series(volume)
            contributions = a.Series([r for r in volume if r.get('vs')=='VALID' and a.finite(r.get('i')) and a.finite(r.get('dv')) and r['dv']>0])
            features = dict(session=day, t=a.isot(now), ist=a.ist(now), input_cutoff=a.isot(cutoff),
                context_published_at=a.isot(now), short_leg=state.get('short',0),
                broader_leg=state.get('broad',0), index=price[-1]['i'],
                corrected_direction='UNAVAILABLE', corrected_score=None,
                baseline_note='No matching locally calculated reference call for this minute.',
                **cash_features,
                **a.option_features({k:a.Series(v) for k,v in contracts.items()},selection,cutoff),
                **a.volume_features(vs,contributions,cutoff,inventory))
            for key, rows, field, age, gap in [('index_change_5m',price,'i',15,60),
                    ('basis_change_5m',price,'b',15,60), ('futures_oi_change_5m',oi,'oi',90,90)]:
                w = a.Series(rows).window(cutoff,5,age,gap)
                features[key] = w[-1][field]-w[0][field] if w and all(a.finite(r.get(field)) for r in w) else None
            required = ['index_change_5m','basis_change_5m','futures_oi_change_5m',
                'cash_raw_change_5m','vix_raw_change_5m','ce_oi_delta_5m','pe_oi_delta_5m',
                'volume_recent_15m_mode']
            features['missing_inputs'] = [k for k in required if not a.finite(features.get(k))]
            features['complete'] = not features['missing_inputs']
            if a.finite(features.get('fixed_atm')):
                features['index_minus_fixed_atm'] = features['index']-features['fixed_atm']
            calls = profile.get('directional_prediction_history', [])
            if profile.get('directional_prediction'):
                calls = calls + [profile['directional_prediction']]
            for call in calls:
                if (call.get('input_cutoff') and a.ts(call['input_cutoff'])==cutoff
                        and a.ts(call.get('published_at') or call['t'])<=now):
                    features.update(corrected_direction=call['direction'],
                        corrected_score=call.get('core_score',call.get('score')),
                        baseline_note='Locally calculated reference call for the same input cutoff.', baseline_call=call)
                    break
            if features['corrected_direction']=='UNAVAILABLE' and now-cutoff<30:
                self.last_success = now
                self.error = None
                return False
            # SQLite commits inputs and publication together. Primary key prohibits revision.
            self.db.execute('INSERT INTO decisions VALUES(?,?,?)',(day,cutoff,encoded(features)))
            self.last_success = now
            self.error = None
            return True

    def status(self, now=None):
        now = time.time() if now is None else now
        day = a.ist(now)[:10]
        with self.lock:
            row = self.db.execute('SELECT max(cutoff) FROM decisions WHERE day=?',(day,)).fetchone()
            last = row[0]
            state = 'unavailable' if self.error else 'waiting'
            if not self.error and self.last_success is not None and now-self.last_success <= 3*self.poll_seconds:
                state = 'fresh' if last is not None and now-last <= 120 else 'stale_or_outside_session'
            return dict(status=state, error=self.error, last_poll_at=a.isot(self.last_success) if self.last_success else None,
                        latest_input_cutoff=a.isot(last) if last else None, session=day)

    def payload(self, day=None):
        day = day or a.ist(time.time())[:10]
        with self.lock:
            rows = [json.loads(r[0]) for r in self.db.execute('SELECT body FROM decisions WHERE day=? ORDER BY cutoff',(day,))]
            prices = self._rows(day,'price',a.ts(rows[-1]['input_cutoff'])-0.000001) if rows else []
            oi = a.Series(self._rows(day,'oi',a.ts(rows[-1]['input_cutoff'])-0.000001)) if rows else a.Series([])
            minutes = {}
            for r in prices:
                boundary = int(r['_t']//60)*60+60
                if boundary-r['_t'] > 15:
                    continue
                j = oi.before(boundary)
                minutes[boundary] = dict(t=a.isot(boundary), index=r['i'],basis=r['b'],
                    futures_oi=oi.rows[j].get('oi') if j>=0 and boundary-oi.t[j]<=90 else None)
            through = a.ts(rows[-1]['input_cutoff']) if rows else None
            chart_rows = []
            if through is not None:
                key = (day, through)
                if self._chart_cache is None or self._chart_cache[0] != key:
                    from chart_history import build_chart_history
                    # Reconstruct display history separately from immutable decisions.
                    inputs = {kind:self._rows(day,kind,through-0.000001)
                              for kind in ('volume','inventory','options')}
                    inputs['cash'] = self._rows(day,'cash',a.ts(rows[-1]['context_published_at']))
                    selected = self.db.execute('SELECT body FROM selections WHERE day=?',(day,)).fetchone()
                    selection = json.loads(selected[0]) if selected else {}
                    self._chart_cache = (key, build_chart_history(day,through,inputs,selection))
                chart_rows = self._chart_cache[1]
            return dict(version='2.0.0', baseline_version='1.0.62',session=day,decisions=rows,
                        price_history=list(minutes.values()), chart_history=chart_rows,
                        chart_history_note='Charts include reconstructed input history from 09:45. Calls retain their actual live publication times. Missing inputs remain gaps.',
                        live_status=self.status())

    def days(self):
        with self.lock:
            return [dict(session=d,decisions=n,recorded_live=True) for d,n in
                    self.db.execute('SELECT day,count(*) FROM decisions GROUP BY day ORDER BY day')]

    def run(self):
        while not self.stop.is_set():
            try:
                if self.source is None:
                    from direct_source import DirectSource
                    self.source = DirectSource(self.collector_root,self.root/'engine', self.futures_symbols_by_session)
                snapshot = self.source.snapshot()
                if self.stop.is_set():
                    return
                self.ingest(snapshot)
            except Exception as exc:
                with self.lock:
                    self.error = type(exc).__name__+': '+str(exc)
            self.stop.wait(self.poll_seconds)

    def start(self):
        self.thread = threading.Thread(target=self.run,name='v200-context',daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=10)
        with self.lock:
            self.db.close()
