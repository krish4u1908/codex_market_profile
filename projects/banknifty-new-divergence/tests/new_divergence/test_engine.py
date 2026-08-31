from dataclasses import replace
from datetime import datetime, timedelta

from banknifty_profiler.new_divergence.adapters import LiveAdapter, ReplayAdapter
from banknifty_profiler.new_divergence.clock import IST
from banknifty_profiler.new_divergence.contracts import BasisState, EngineConfig, EpisodeState, EventKind
from banknifty_profiler.new_divergence.engine import run_replay

from .helpers import event, green_episode_events


def _rows(engine):
    return [transition.to_dict() for transition in engine.transitions]


def test_candidate_confirm_active_resolve_is_published_causally() -> None:
    engine = run_replay(ReplayAdapter(green_episode_events()).stream())
    states = [row.state for row in engine.transitions]
    assert states[:3] == [EpisodeState.CANDIDATE, EpisodeState.CONFIRMED, EpisodeState.ACTIVE]
    assert states[-1] == EpisodeState.RESOLVED
    candidate, confirmation = engine.transitions[:2]
    assert candidate.published_at == candidate.effective_at == candidate.candidate_started_at
    assert confirmation.published_at > candidate.published_at
    assert (confirmation.published_at - candidate.published_at).total_seconds() >= 60
    assert all(row.published_at == row.effective_at for row in engine.transitions)


def test_prefix_invariance_proves_no_future_record_changes_past_output() -> None:
    events = green_episode_events()
    full = run_replay(events)
    cutoff = events[55].receipt_timestamp
    prefix = run_replay(event for event in events if event.receipt_timestamp <= cutoff)
    expected = [row.to_dict() for row in full.transitions if row.published_at <= cutoff]
    assert _rows(prefix) == expected


def test_participation_contradiction_is_descriptive_not_a_gate() -> None:
    events = green_episode_events()
    insertion = next(
        i for i, row in enumerate(events)
        if row.receipt_timestamp.astimezone(IST).hour == 9
        and row.receipt_timestamp.astimezone(IST).minute == 45
    )
    anchor = events[insertion]
    option = event(
        "opposing-option", EventKind.OPTION_PRESSURE,
        anchor.receipt_timestamp.replace(microsecond=0), -1.0,
        max(row.sequence for row in events) + 1,
        symbol="NSE:BANKNIFTY",
    )
    augmented = sorted([*events, option], key=lambda row: row.sort_key)
    baseline = run_replay(events)
    with_participation = run_replay(augmented)
    assert [row.state for row in baseline.transitions] == [row.state for row in with_participation.transitions]
    assert any(
        "OPTION_PRESSURE_OPPOSES_BASIS_STATE" in row.evidence.contradictions
        for row in with_participation.transitions
    )


def test_replay_and_live_adapters_feed_identical_engine() -> None:
    events = green_episode_events()
    replay = run_replay(ReplayAdapter(events).stream())
    live_adapter = LiveAdapter()
    emitted = []
    for row in events:
        assert live_adapter.ingest(row)
        emitted.extend(live_adapter.drain())
    emitted.extend(live_adapter.drain(flush=True))
    live = run_replay(emitted)
    assert _rows(live) == _rows(replay)


def test_out_of_order_event_is_refused_not_backdated() -> None:
    events = green_episode_events()
    engine = run_replay(events[:10])
    late = replace(events[0], event_id="late-copy")
    assert engine.ingest(late) == ()
    assert engine.diagnostics[-1]["reason"] == "OUT_OF_ORDER_RECEIPT_REFUSED"


def test_future_index_receipt_is_never_used_for_matching() -> None:
    timestamp = datetime(2031, 4, 7, 10, 0, tzinfo=IST)
    future = event("future-first", EventKind.FUTURES_TICK, timestamp, 107.0, 1)
    index = event("index-later", EventKind.INDEX_TICK, timestamp + timedelta(milliseconds=1), 100.0, 2)
    engine = run_replay((future, index))
    assert engine.observations == ()
    assert engine.diagnostics == [{
        "event_id": "future-first",
        "receipt_timestamp": "2031-04-07T04:30:00.000000Z",
        "reason": "UNMATCHED_NO_PRIOR_INDEX",
    }]


def test_candidate_discovery_is_closed_outside_configured_window() -> None:
    events = green_episode_events()
    shifted = [
        replace(
            row,
            event_timestamp=row.event_timestamp - timedelta(hours=1),
            receipt_timestamp=row.receipt_timestamp - timedelta(hours=1),
        )
        for row in events
    ]
    assert run_replay(shifted).transitions == ()


def test_premarket_index_cannot_seed_a_session_match() -> None:
    preopen = datetime(2031, 4, 7, 9, 14, 59, 900000, tzinfo=IST)
    rows = (
        event("preopen-index", EventKind.INDEX_TICK, preopen, 100.0, 1),
        event("opening-future", EventKind.FUTURES_TICK, preopen + timedelta(milliseconds=200), 107.0, 2),
    )
    engine = run_replay(rows)
    assert engine.observations == ()
    assert [row["reason"] for row in engine.diagnostics] == [
        "OUTSIDE_MARKET_SESSION_REFUSED", "UNMATCHED_NO_PRIOR_INDEX"
    ]


def test_unmatched_futures_row_remains_a_horizon_gap() -> None:
    first = datetime(2031, 4, 7, 9, 59, tzinfo=IST)
    rows = [
        event("i-1", EventKind.INDEX_TICK, first, 100.0, 1),
        event("f-1", EventKind.FUTURES_TICK, first + timedelta(milliseconds=100), 105.0, 2),
        event("f-gap", EventKind.FUTURES_TICK, first + timedelta(minutes=1), 106.0, 3),
        event("i-2", EventKind.INDEX_TICK, first + timedelta(minutes=2), 88.0, 4),
        event("f-2", EventKind.FUTURES_TICK, first + timedelta(minutes=2, milliseconds=100), 99.0, 5),
    ]
    engine = run_replay(rows, EngineConfig(horizons_minutes=(1,), minimum_supporting_horizons=1))
    assert engine.latest_evidence is not None
    assert engine.latest_evidence.basis_state == BasisState.UNKNOWN_GAP
    assert engine.latest_evidence.horizon_evidence["1m"]["reason"] == "PRIOR_OBSERVATION_UNMATCHED"


def _gap_recovery_events(*, recovery_seconds: int) -> list:
    start = datetime(2031, 4, 7, 9, 39, tzinfo=IST)
    rows = []
    sequence = 0

    for step in range(35):
        timestamp = start + timedelta(seconds=15 * step)
        sequence += 1
        rows.append(event(f"pre-i-{step}", EventKind.INDEX_TICK, timestamp, 100.0, sequence))
        sequence += 1
        rows.append(event(
            f"pre-f-{step}", EventKind.FUTURES_TICK,
            timestamp + timedelta(milliseconds=100), 140.0, sequence,
        ))

    recovery = datetime(2031, 4, 7, 10, 0, tzinfo=IST)
    for step in range(recovery_seconds // 15 + 1):
        timestamp = recovery + timedelta(seconds=15 * step)
        index_price = 200.0 + 4.0 * step
        basis = 30.0 - 2.0 * step
        sequence += 1
        rows.append(event(f"post-i-{step}", EventKind.INDEX_TICK, timestamp, index_price, sequence))
        sequence += 1
        rows.append(event(
            f"post-f-{step}", EventKind.FUTURES_TICK,
            timestamp + timedelta(milliseconds=100), index_price + basis, sequence,
        ))
    return rows


def test_post_gap_red_cannot_reuse_one_stale_row_as_three_horizons() -> None:
    engine = run_replay(_gap_recovery_events(recovery_seconds=60))
    assert engine.latest_evidence is not None
    evidence = engine.latest_evidence
    assert evidence.basis_state == BasisState.UNKNOWN_GAP
    assert evidence.supporting_horizons == 1
    assert evidence.horizon_evidence["1m"]["state"] == BasisState.RED_CANDIDATE.value
    assert evidence.horizon_evidence["3m"]["reason"] == "INSUFFICIENT_CONTINUOUS_HISTORY_AFTER_GAP"
    assert evidence.horizon_evidence["5m"]["reason"] == "INSUFFICIENT_CONTINUOUS_HISTORY_AFTER_GAP"
    assert not any(row.colour == "RED" for row in engine.transitions)


def test_horizons_rejoin_only_after_their_own_continuous_warmup() -> None:
    engine = run_replay(_gap_recovery_events(recovery_seconds=180))
    assert engine.latest_evidence is not None
    evidence = engine.latest_evidence
    assert evidence.basis_state == BasisState.RED_CANDIDATE
    assert evidence.supporting_horizons == 2
    assert evidence.horizon_evidence["1m"]["state"] == BasisState.RED_CANDIDATE.value
    assert evidence.horizon_evidence["3m"]["state"] == BasisState.RED_CANDIDATE.value
    assert evidence.horizon_evidence["5m"]["reason"] == "INSUFFICIENT_CONTINUOUS_HISTORY_AFTER_GAP"
    assert engine.transitions[-1].state == EpisodeState.CANDIDATE
    assert engine.transitions[-1].colour == "RED"
