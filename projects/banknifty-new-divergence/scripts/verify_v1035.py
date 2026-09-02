#!/usr/bin/env python3
"""Dependency-free V1.0.35 release assertions (pytest is optional)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from banknifty_profiler.new_divergence import __version__
from banknifty_profiler.new_divergence.api import ProjectionReadModel
from banknifty_profiler.new_divergence.codex_replay import replay_fact_bundle
from banknifty_profiler.new_divergence.commentary import live_fact_bundle
from banknifty_profiler.new_divergence.contracts import EngineConfig
from banknifty_profiler.new_divergence.output import publish_run
from banknifty_profiler.new_divergence.projection import build_browser
from tests.new_divergence import test_scenario_v1028, test_short_trap_v1035
from tests.new_divergence.helpers import green_episode_events


def _run_module(module) -> int:
    count = 0
    for name in sorted(dir(module)):
        if not name.startswith("test_"):
            continue
        getattr(module, name)()
        count += 1
        print(f"PASS {module.__name__}.{name}")
    return count


def _integration() -> int:
    assert __version__ == "1.0.35"
    events = green_episode_events()
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_root = root / "runs"
        publish_run(
            run_root,
            events[0].session,
            events,
            EngineConfig(),
            source={"kind": "V1035_DEPENDENCY_FREE_ASSERTION"},
        )
        browser = build_browser(run_root, root / "browser")
        model = ProjectionReadModel(browser)
        payload = model.session(events[0].session.isoformat())
        assert "futures_volume" in payload
        cutoff = payload["price"]["rows"][10][0]
        prefix = model.session(events[0].session.isoformat(), as_of=cutoff)
        assert prefix["availability"]["future_futures_volume_returned"] is False
        fields = prefix["futures_volume"]["fields"]
        time_index = fields.index("t")
        assert all(row[time_index] <= cutoff for row in prefix["futures_volume"]["rows"])
        bundle, digest = replay_fact_bundle(model, payload["session"], cutoff)
        assert "recent_futures_volume_minutes" in bundle
        assert len(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()) < 96_000
        assert len(digest) == 64

    snapshot = {
        "session": "2026-08-31",
        "server_time": "2026-08-31T04:30:01Z",
        "observations": [{
            "timestamp": "2026-08-31T04:30:00Z",
            "index_price": 57500,
            "futures_price": 57545,
            "basis": 45,
        }],
        "events": [], "evidence": [], "transitions": [],
        "profile": {
            "option_strike_oi": [], "strike_selection": {}, "futures_oi": [],
            "futures_volume": [{
                "t": "2026-08-31T04:30:00Z", "dv": 10, "vs": "VALID",
            }],
            "visible_intraday_inventory": {},
            "recent_intraday_inventory_shifts": {},
        },
    }
    live = live_fact_bundle(snapshot)
    assert "recent_futures_volume_minutes" in live
    assert len(json.dumps(live, sort_keys=True, separators=(",", ":")).encode()) < 96_000
    print("PASS replay Futures-volume prefix filtering")
    print("PASS replay compact fact bundle under 96 KB")
    print("PASS live compact fact bundle under 96 KB")
    return 3


def main() -> int:
    unit_count = sum(_run_module(module) for module in (
        test_short_trap_v1035,
        test_scenario_v1028,
    ))
    integration_count = _integration()
    print(f"V1.0.35 verification passed: {unit_count} unit/scenario + {integration_count} integration assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
