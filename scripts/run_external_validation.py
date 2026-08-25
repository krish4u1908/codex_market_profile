#!/usr/bin/env python3
"""Explicit external-data entrypoint. Never writes beneath data-root."""
import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--data-root",type=Path,required=True)
    p.add_argument("--output-root",type=Path,required=True)
    p.add_argument("--mode",choices=["stream","batch"],required=True)
    a=p.parse_args()
    if a.data_root.resolve()==a.output_root.resolve() or a.data_root.resolve() in a.output_root.resolve().parents:
        raise SystemExit("output-root must be outside the read-only data-root")
    if not a.data_root.is_dir(): raise SystemExit("data-root does not exist")
    raise SystemExit("External full-data adapter is intentionally dormant; authorize a separate runtime revision.")

if __name__ == "__main__": main()

