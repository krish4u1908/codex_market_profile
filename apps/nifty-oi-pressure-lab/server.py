#!/usr/bin/env python3
import argparse, csv, json, math, os
from collections import defaultdict
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, 'static')
DATA = os.path.join(ROOT, 'data')

FILES = {
    'expiry': os.path.join(DATA, 'expiry_oi_pressure_timeline.csv'),
    'normal': os.path.join(DATA, 'normal_oi_pressure_timeline.csv'),
}

def _num(v):
    if v in (None, '', 'nan', 'NaN'):
        return None
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return int(f) if f.is_integer() else f
    except Exception:
        return v

def _bool(v):
    if isinstance(v, bool): return v
    return str(v).lower() in ('true','1','yes')

def load_rows(path):
    out = []
    with open(path, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rr = {}
            for k,v in r.items():
                if k in ('MICRO_FIXED4_1M','NEAR_DYN4_5M','BROAD_FULL_10M',
                         'BULL_FIXED4_FAST','BULL_DYN4_NEAR','BULL_FULL_BROAD',
                         'BEAR_FIXED2_FAST','BEAR_DYN4_REGIME','BEAR_FULL_ACTIVITY'):
                    rr[k] = _bool(v)
                elif k in ('session','kind','time'):
                    rr[k] = v
                else:
                    rr[k] = _num(v)
            out.append(rr)
    return out

CACHE = {k: load_rows(p) for k,p in FILES.items()}
BY_SESSION = {}
for regime, rows in CACHE.items():
    d = defaultdict(list)
    for r in rows: d[r['session']].append(r)
    for s in d: d[s].sort(key=lambda x:x['time'])
    BY_SESSION[regime] = dict(d)


def score_of(regime, r):
    if regime == 'expiry':
        return float(r.get('expiry_bear_score') or 0)
    return float(r.get('normal_oi_score') or 0)


def directional_hit(score, ret):
    if ret is None or score == 0: return None
    return (ret > 0) if score > 0 else (ret < 0)


def session_summary(regime, rows):
    # Independent episodes = trigger start after at least 2 neutral/opposite minutes.
    episodes=[]
    last_trigger=-99
    for i,r in enumerate(rows):
        s=score_of(regime,r)
        if abs(s) < 35: continue
        if i-last_trigger <= 2: continue
        episodes.append(r); last_trigger=i
    strong=[r for r in episodes if abs(score_of(regime,r)) >= 70]
    def stats(items):
        vals=[]; hits=[]
        for r in items:
            v=r.get('fut_ret_10m')
            if v is None: continue
            vals.append(v if score_of(regime,r)>0 else -v)
            h=directional_hit(score_of(regime,r),v)
            if h is not None: hits.append(h)
        return {
            'n': len(items),
            'n_with_10m': len(vals),
            'hit10': round(sum(hits)/len(hits)*100,1) if hits else None,
            'avg_dir_move10': round(sum(vals)/len(vals),2) if vals else None,
        }
    return {'episodes': stats(episodes), 'strong': stats(strong)}

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Static files only.
        parsed=urlparse(path)
        p=parsed.path
        if p == '/': p='/index.html'
        return os.path.join(STATIC, p.lstrip('/'))

    def log_message(self, fmt, *args):
        print('[gui]', fmt % args)

    def send_json(self, obj, status=200):
        data=json.dumps(obj, separators=(',',':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        u=urlparse(self.path)
        q=parse_qs(u.query)
        if u.path == '/api/sessions':
            regime=q.get('regime',['expiry'])[0]
            if regime not in BY_SESSION: return self.send_json({'error':'bad regime'},400)
            ss=sorted(BY_SESSION[regime])
            return self.send_json({'regime':regime,'sessions':ss})
        if u.path == '/api/timeline':
            regime=q.get('regime',['expiry'])[0]
            session=q.get('session',[''])[0]
            rows=BY_SESSION.get(regime,{}).get(session)
            if rows is None: return self.send_json({'error':'session not found'},404)
            return self.send_json({'regime':regime,'session':session,'rows':rows,'summary':session_summary(regime,rows)})
        if u.path == '/api/global-summary':
            out={}
            for regime,sessions in BY_SESSION.items():
                allrows=[]
                for r in sessions.values(): allrows.extend(r)
                out[regime]={'sessions':len(sessions),'rows':len(allrows)}
            # Frozen research facts from the accompanying report; labelled observed.
            out['frozen_research']={
                'expiry_watch_10m':'90.0% prior expiries; 87.5% Sep 15',
                'expiry_high_10m':'10/10 observed across 4 expiry sessions',
                'normal_bear_2plus_10m':'83.3% observed, 6 episodes',
                'normal_bull_2plus_10m':'64.3% observed, 14 episodes; unstable magnitude',
                'caution':'Historical observed results, not guaranteed probabilities. Fresh forward sessions are required.'
            }
            return self.send_json(out)
        return super().do_GET()

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description='NIFTY OI Pressure research GUI prototype')
    ap.add_argument('--host',default='127.0.0.1')
    ap.add_argument('--port',type=int,default=8920)
    args=ap.parse_args()
    os.chdir(STATIC)
    httpd=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'NIFTY OI Pressure prototype: http://{args.host}:{args.port}')
    print('Research-only prototype. No production services are modified.')
    try: httpd.serve_forever()
    except KeyboardInterrupt: pass
