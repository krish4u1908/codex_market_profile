import json
from pathlib import Path
import numpy as np,pandas as pd
root=Path(__file__).resolve().parent
df=pd.read_json(root/'evaluation_rows.jsonl.gz',lines=True)
result=[];rng=np.random.default_rng(20260917)
for period,d in [('all15',df),('first5',df[df.session<'2026-09-01']),('later10',df[df.session>='2026-09-01']),('normal',df[df.regime=='normal']),('expiry',df[df.regime=='expiry'])]:
 for rule in ['raw5','quantity5','quantityAgreement','candidate']:
  active=d[d[rule]!=0].copy()
  for sample,a in [('all_minutes',active),('spaced10',None)]:
   if a is None:
    ids=[]
    for _,g in active.groupby('session'):
     last=-np.inf
     for i,r in g.sort_values('t').iterrows():
      if r.t-last>=600:ids.append(i);last=r.t
    a=active.loc[ids]
   for horizon in ['past5','future5','future10']:
    a1=a[a[horizon].notna()].copy();hits=a1[rule]*a1[horizon]>0
    daily=[]
    for day,g in a1.groupby('session'):daily.append([len(g),int(sum(g[rule]*g[horizon]>0))])
    agg=np.array(daily);sums=agg[rng.integers(0,len(agg),(2000,len(agg)))].sum(axis=1)
    result.append(dict(period=period,rule=rule,sample=sample,target=horizon,n=len(a1),sessions=len(daily),coveragePct=100*len(active)/len(d),directionHitPct=100*float(hits.mean()),meanDirectionalPoints=float((a1[rule]*a1[horizon]).mean()),sessionBootstrap95=(100*np.quantile(sums[:,1]/sums[:,0],[.025,.975])).tolist()))
(root/'results.json').write_text(json.dumps({'rows':len(df),'sessions':int(df.session.nunique()),'estimates':result},indent=2))
for r in result:
 if r['period']=='all15' and (r['target']=='future10' or (r['rule']=='candidate' and r['sample']=='all_minutes')):print(r)
