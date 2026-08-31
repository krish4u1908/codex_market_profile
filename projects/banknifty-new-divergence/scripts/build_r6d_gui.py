#!/usr/bin/env python3
"""Build the offline R6D GUI from sealed R6C2R outputs only."""
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path
from banknifty_profiler.gui.adapter import SESSIONS, build_payload, source_contract, write_payload

def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True)
    args=p.parse_args(); out=args.output_root.resolve()
    if out.exists() and any(out.iterdir()): raise RuntimeError('output root must be new or empty')
    out.mkdir(parents=True,exist_ok=True); (out/'data').mkdir(); (out/'screenshots').mkdir(); (out/'tests').mkdir()
    static=Path(__file__).resolve().parents[1]/'src/banknifty_profiler/gui/static'
    for name in ('app.js','style.css','index.html'):shutil.copyfile(static/name,out/name)
    shutil.copyfile(Path(__file__).resolve().parents[1]/'configs/r6d_gui.json',out/'configuration.json')
    contract=source_contract(args.input_root.resolve())
    (out/'data/gui_input_schema.json').write_text(json.dumps(contract,indent=2,sort_keys=True)+'\n')
    for date in SESSIONS:
        write_payload(build_payload(args.input_root.resolve(),date),out/f'data/session_{date}.json.gz')
        page=(static/'replay.html').read_text().replace('__DATE__',date)
        (out/f'replay_{date}.html').write_text(page)
    # Visual-only degradation fixtures use sealed records with explicit layer
    # removal. They never manufacture controls or analytical states.
    intraday = build_payload(args.input_root.resolve(), "2026-08-13")
    intraday["inventory"]["rows"] = [row for row in intraday["inventory"]["rows"] if row[intraday["inventory"]["fields"].index("horizon")] == "ID"]
    for row in intraday["availability"]:
        if row["horizon"] != "ID":
            row["availability_state"] = "MISSING"
            row["availability_reason"] = "SYNTHETIC_DEGRADATION_FIXTURE"
        row["overall_state"] = "LIVE_INTRADAY_ONLY"
    intraday["fixture"] = "SYNTHETIC_INTRADAY_ONLY_NO_ANALYTICAL_SUBSTITUTION"
    write_payload(intraday, out/'data/session_synthetic_intraday_only.json.gz')
    (out/'replay_synthetic_intraday_only.html').write_text((static/'replay.html').read_text().replace('__DATE__','synthetic_intraday_only'))
    missing = build_payload(args.input_root.resolve(), "2026-08-11")
    missing["fixture"] = "SYNTHETIC_MISSING_3D_2D_FROM_CANONICAL_2026_08_11"
    write_payload(missing, out/'data/session_synthetic_missing_3d_2d.json.gz')
    (out/'replay_synthetic_missing_3d_2d.html').write_text((static/'replay.html').read_text().replace('__DATE__','synthetic_missing_3d_2d'))
    print(json.dumps({'sessions':len(SESSIONS),'output':str(out)},sort_keys=True))
if __name__=='__main__':main()
