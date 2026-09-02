from pathlib import Path
import json
import threading

from banknifty_profiler.new_divergence.commentary import (
    CommentaryStore,
    ReplayCommentaryQueue,
    compact_commentary,
    detect_inventory_shifts,
    live_fact_bundle,
    market_profile_analysis,
)


def facts():
    return {
        "causal_as_of": "2026-08-25T04:30:00+00:00",
        "verified_prefix_sha256": "a" * 64,
        "latest_market": {"i": 57485.0, "f": 57530.0, "b": 45.0},
        "latest_option_summary": {
            "CE": {"delta_oi_total": 60_000},
            "PE": {"delta_oi_total": 100_000},
        },
        "visible_intraday_inventory": {
            "PE_POS_OI_VPOC": {"control_value": 57400},
            "CE_POS_OI_VPOC": {"control_value": 57600},
        },
        "recent_intraday_inventory_shifts": {
            "CE_POS_OI_VPOC": [
                {"control_value": 57500, "receipt": "2026-08-25T04:29:00+00:00"},
                {"control_value": 57600, "receipt": "2026-08-25T04:30:00+00:00"},
            ]
        },
    }


def test_shift_identity_is_deterministic_and_exact():
    assert detect_inventory_shifts(facts()) == [{
        "family": "CE_POS_OI_VPOC", "from": 57500, "to": 57600,
        "delta": 100.0, "receipt": "2026-08-25T04:30:00+00:00",
    }]


def test_textbook_analysis_is_separate_and_cautious():
    result = market_profile_analysis(facts(), detect_inventory_shifts(facts()))
    assert result["method"] == "TRANSPARENT_RULE_BASED_MARKET_PROFILE"
    assert result["support"] == [57400.0]
    assert result["resistance"] == [57600.0]
    assert any("not proven" in row for row in result["observations"])
    assert any("not automatically" in row for row in result["cautions"])


def test_no_unvalidated_probability_is_fabricated():
    result = compact_commentary(
        facts(), {"headline": "Context", "summary": "Visible inventory changed."},
        detect_inventory_shifts(facts()),
    )
    assert result["bias"] == "NO_EDGE"
    assert result["probability"] is None
    assert result["classification"] == "EXPERIMENTAL_NOT_VALIDATED"
    assert result["generation_revision"] == 5
    assert "market_profile_analysis" in result
    assert result["backend_scenario"]["scenario"] == "NO_EDGE"


def test_store_is_shared_and_immutable(tmp_path: Path):
    store = CommentaryStore(tmp_path / "commentary.sqlite3")
    payload = compact_commentary(
        facts(), {"headline": "Context", "summary": "Stored once."},
        detect_inventory_shifts(facts()),
    )
    first = store.put("2026-08-25", payload)
    second = store.put("2026-08-25", {**payload, "summary": "must not overwrite"})
    assert first["event_id"] == second["event_id"]
    assert second["summary"] == "Stored once."
    assert store.current("2026-08-25", payload["causal_as_of"])["event_id"] == first["event_id"]


def test_live_bundle_is_prefix_only_and_hashed():
    snapshot = {
        "session": "2026-08-31", "server_time": "2026-08-31T04:30:01+00:00",
        "observations": [{
            "timestamp": "2026-08-31T04:30:00+00:00", "index_price": 57500,
            "futures_price": 57545, "basis": 45,
        }],
        "events": [], "evidence": [], "transitions": [],
        "profile": {
            "option_strike_oi": [
                {"k": "CE", "oi": 1000, "d": 100, "symbol": "CE1"},
                {"k": "PE", "oi": 1200, "d": 200, "symbol": "PE1"},
            ],
            "strike_selection": {
                "CE": [{"symbol": "CE1"}], "PE": [{"symbol": "PE1"}],
            },
            "visible_intraday_inventory": {
                "CE_POS_OI_VPOC": {"control_value": 57525},
            },
            "recent_intraday_inventory_shifts": {
                "CE_POS_OI_VPOC": [
                    {"control_value": 57500, "receipt": "2026-08-31T04:29:00Z"},
                    {"control_value": 57525, "receipt": "2026-08-31T04:30:00Z"},
                ],
            },
            "futures_oi": [
                {"t": "2026-08-31T04:25:00Z", "p": 57510, "oi": 1000},
                {"t": "2026-08-31T04:30:00Z", "p": 57545, "oi": 1100},
            ],
            "futures_volume": [
                {"t": "2026-08-31T04:30:00Z", "dv": 100, "vs": "VALID"},
            ],
        },
    }
    bundle = live_fact_bundle(snapshot)
    assert bundle["availability"] == "LIVE_PREFIX_ONLY"
    assert bundle["latest_option_summary"]["PE"]["delta_oi_total"] == 200
    assert bundle["visible_intraday_inventory"]["CE_POS_OI_VPOC"]["control_value"] == 57525
    assert len(bundle["recent_intraday_inventory_shifts"]["CE_POS_OI_VPOC"]) == 2
    assert len(bundle["recent_futures_oi"]) == 2
    assert len(bundle["recent_futures_volume_minutes"]) == 1
    assert len(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()) < 96_000
    assert len(bundle["verified_prefix_sha256"]) == 64


def test_central_queue_deduplicates_pending_work(tmp_path: Path):
    called = []
    finished = threading.Event()

    class Coordinator:
        store = CommentaryStore(tmp_path / "queue.sqlite3")

        def generate(self, session, as_of):
            called.append((session, as_of))
            finished.set()

    queue = ReplayCommentaryQueue(Coordinator())
    queue.start()
    try:
        assert queue.request("2026-08-27", "2026-08-27T04:30:00Z") == "PENDING"
        assert finished.wait(2)
        assert called == [("2026-08-27", "2026-08-27T04:30:00Z")]
    finally:
        queue.stop()
