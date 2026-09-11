#!/usr/bin/env python3
"""Compare retained receipts with collector data; optionally export as-of revisions.

Uses a temporary journal. Never modifies collector files or production journals.
Recovered values become available at this audit's time, not in past decisions.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_core.config import Config
from market_core.indicator_inputs import IndicatorInputs, latest_minutes
from market_core.storage import atomic_write, encode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--session',required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();config=Config.read(args.config)
    if args.output:
        path=args.output.resolve()
        if any(path==root or root in path.parents for root in (config.collector_root,config.state_root)):
            parser.error('Export outside collector and production state directories')
        if path.exists():parser.error('Choose a new output file; existing exports are retained')
    with tempfile.TemporaryDirectory() as temp:
        reader=IndicatorInputs(config,args.session,Path(temp));feed=reader.poll()
        latest=latest_minutes(feed['revisions'],feed['as_of'])
        legacy={r['minute_ist']:r for r in feed['revisions'] if r['origin']=='RETAINED_LEGACY_RECEIPT'}
        recovered=[r['minute_ist'] for r in latest if r['vix_valid'] and r['minute_ist'] in legacy and not legacy[r['minute_ist']]['vix_valid']]
        report={k:feed[k] for k in ('schema','instrument','session','as_of','status','error','quality')}
        report['recovered_vix_minutes']=recovered
        report['still_missing_vix_minutes']=[r['minute_ist'] for r in latest if not r['vix_valid']]
        if args.output:
            if feed['status']!='AVAILABLE':raise RuntimeError('Source unavailable; no export written')
            atomic_write(args.output,encode(feed));report['export']=str(args.output)
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
