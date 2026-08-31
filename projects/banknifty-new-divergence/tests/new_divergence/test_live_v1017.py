from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path

import pytest

from banknifty_profiler.new_divergence.contracts import EventKind, MarketEvent
from banknifty_profiler.new_divergence.live_authority import LiveAuthority
from banknifty_profiler.new_divergence.live_collector import LiveCollectorTail
from banknifty_profiler.new_divergence.live_service import build_live_browser


SESSION = date(2031, 4, 7)
START = datetime(2031, 4, 7, 9, 15, tzinfo=UTC) + timedelta(hours=-5, minutes=-30)


def _event(identifier: str, kind: EventKind, second: int, price: float) -> MarketEvent:
    timestamp = datetime(2031, 4, 7, 3, 45, second, tzinfo=UTC)
    return MarketEvent(
        event_id=identifier,
        session=SESSION,
        kind=kind,
        symbol="NSE:NIFTYBANK-INDEX" if kind == EventKind.INDEX_TICK else "NSE:BANKNIFTY31APRFUT",
        event_timestamp=timestamp,
        receipt_timestamp=timestamp,
        sequence=second,
        values={"price": price},
    )


def test_authority_checkpoint_recovery_and_monotonic_sequence(tmp_path: Path) -> None:
    authority = LiveAuthority(tmp_path, SESSION)
    assert authority.recover()["mode"] == "VERIFIED_JOURNAL_RECONSTRUCTION"
    rows = [_event("i", EventKind.INDEX_TICK, 1, 100), _event("f", EventKind.FUTURES_TICK, 2, 105)]
    authority.stage(reversed(rows), {"raw/events.jsonl": {"offset": 10, "line": 2, "inode": 4}})
    assert authority.commit_ready(flush=True) == 2
    assert [row["sequence"] for row in authority.after(0)] == [1, 2]

    recovered = LiveAuthority(tmp_path, SESSION)
    result = recovered.recover()
    assert result == {"mode": "CHECKPOINT_VERIFIED", "events": 2, "pending": 0, "sequence": 2}
    assert recovered.snapshot()["observations"][0]["basis"] == 5


def test_authority_persists_pending_reorder_buffer(tmp_path: Path) -> None:
    authority = LiveAuthority(tmp_path, SESSION)
    authority.recover()
    future = _event("future", EventKind.INDEX_TICK, 10, 100)
    authority.stage([future], {"raw": {"offset": 1, "line": 1, "inode": 2}})
    assert authority.commit_ready(future.receipt_timestamp - timedelta(seconds=1)) == 0
    recovered = LiveAuthority(tmp_path, SESSION)
    assert recovered.recover()["pending"] == 1
    assert recovered.commit_ready(flush=True) == 1


def test_authority_refuses_event_older_than_committed_watermark(tmp_path: Path) -> None:
    authority = LiveAuthority(tmp_path, SESSION)
    authority.recover()
    authority.stage([_event("new", EventKind.INDEX_TICK, 10, 100)], {})
    authority.commit_ready(flush=True)
    authority.stage([_event("late", EventKind.INDEX_TICK, 9, 99)], {})
    with pytest.raises(ValueError, match="late live event"):
        authority.commit_ready(flush=True)


def test_tail_reads_only_complete_lines_and_resumes(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata"
    raw_root = tmp_path / "raw" / SESSION.isoformat()
    metadata.mkdir(); raw_root.mkdir(parents=True)
    (metadata / "startup_x.json").write_text(json.dumps({
        "started_at": "2031-04-07T03:44:00Z",
        "base_quote_symbols": ["NSE:NIFTYBANK-INDEX"],
        "future_oi_symbols": ["NSE:BANKNIFTY31APRFUT"],
    }))
    row = json.dumps({
        "received_at": "2031-04-07T03:45:01Z", "event_time": "2031-04-07T03:45:01Z",
        "message": {"symbol": "NSE:NIFTYBANK-INDEX", "ltp": 100},
    }).encode()
    source = raw_root / "events_09.jsonl"
    source.write_bytes(row[:-3])
    tail = LiveCollectorTail(tmp_path, SESSION)
    events, offsets = tail.poll()
    assert events == [] and offsets[str(source.relative_to(tmp_path))]["offset"] == 0
    with source.open("ab") as handle:
        handle.write(row[-3:] + b"\n")
    events, offsets = tail.poll()
    assert [event.kind for event in events] == [EventKind.INDEX_TICK]
    assert offsets[str(source.relative_to(tmp_path))]["line"] == 1


def test_live_browser_uses_session_storage_and_maximize(tmp_path: Path) -> None:
    target = build_live_browser(tmp_path / "browser")
    script = (target / "live.js").read_text()
    assert "sessionStorage" in script
    assert "localStorage" not in script
    assert "frame-maximized" in script
    assert 'event.key==="Escape"' in script
    assert "state.overflowed=true" in script
    assert (target / "live.html").is_file()


def test_wheel_contract_includes_every_live_browser_asset() -> None:
    project = Path(__file__).resolve().parents[2]
    pyproject = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert '"static_live/*.html"' in pyproject
    assert '"static_live/*.js"' in pyproject
    assert (project / "src/banknifty_profiler/new_divergence/static_live/live.html").is_file()
    assert (project / "src/banknifty_profiler/new_divergence/static_live/live.js").is_file()
