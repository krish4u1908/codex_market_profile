"""Load a frozen instrument package once in a dedicated core process."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
_loaded = None


def load(instrument):
    global _loaded
    if instrument not in {"BANKNIFTY", "NIFTY"}:
        raise ValueError("Unknown instrument")
    if _loaded is not None:
        if _loaded.instrument != instrument:
            raise RuntimeError("BANKNIFTY and NIFTY require separate core processes")
        return _loaded
    package_root = ROOT / "vendor" / instrument.lower()
    prefix = "vendor/" + instrument.lower() + "/"
    for item in json.loads((ROOT / "VENDOR_MANIFEST.json").read_text())["files"]:
        if item["path"].startswith(prefix) and hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("Frozen source verification failed: " + item["path"])
    if "v2_engine" in sys.modules or "analyze" in sys.modules or "live_context" in sys.modules:
        raise RuntimeError("Another calculation package is already loaded in this process")
    sys.path.insert(0, str(package_root))
    authority = importlib.import_module("v2_engine.new_divergence.live_authority")
    collector = importlib.import_module("v2_engine.new_divergence.live_collector")
    cash = importlib.import_module("v2_engine.new_divergence.live_cash_vix")
    _loaded = SimpleNamespace(instrument=instrument, LiveAuthority=authority.LiveAuthority,
        LiveCollectorTail=collector.LiveCollectorTail, LiveCashVixSource=cash.LiveCashVixSource,
        LiveContext=importlib.import_module("live_context").LiveContext,
        projection=importlib.import_module("v2_engine.new_divergence.projection"),
        output=importlib.import_module("v2_engine.new_divergence.output"),
        clock=importlib.import_module("v2_engine.new_divergence.clock"))
    return _loaded
