from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from zoneinfo import ZoneInfo

import pytest

from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.contracts import engine_hash, engine_source_inventory
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.observation import TypedObservation
from banknifty_profiler.shadow.symbols import (
    CANONICAL_INDEX_SYMBOL,
    InstrumentClass,
    SymbolRegistry,
    classify_symbol,
)


IST = ZoneInfo("Asia/Kolkata")


def _timestamp(seconds: float = 0) -> str:
    return (datetime.now(IST) + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


def _contract(tmp_path):
    data = tmp_path / "collector"
    (data / "raw/2099-01-01").mkdir(parents=True)
    (data / "oi/2099-01-01").mkdir(parents=True)
    config = {
        "timezone": "Asia/Kolkata",
        "synchronization_tolerance_ms": 2000,
        "selected_futures_by_session": {"2099-01-01": "NSE:BANKNIFTY26AUGFUT"},
        "poll_interval_seconds": 0.01,
        "max_read_bytes_per_file_per_poll": 1_048_576,
        "max_buffer_bytes_per_file": 1_048_576,
        "freshness_seconds": {"index": 10, "futures": 10, "futures_oi": 180, "ce": 180, "pe": 180},
        "allowed_bind": "127.0.0.1",
        "classification": "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL",
        "analytical_threshold_overrides": None,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    contract = validate_shadow_contract(data, tmp_path / "state", config_path, "127.0.0.1", "shadow")
    contract["raw_run_id"] = "R6E1R-TEST"
    return data, contract


def _market(receipt: str, symbol: str, price: float, volume: int) -> str:
    return json.dumps({
        "received_at": receipt,
        "event_time": receipt,
        "secret": "must-not-project",
        "message": {
            "symbol": symbol,
            "ltp": price,
            "vol_traded_today": volume,
            "last_traded_qty": 30,
            "access_token": "must-not-project",
        },
    })


def test_registry_requires_exact_index_and_refuses_unsafe_suffix():
    index = classify_symbol(CANONICAL_INDEX_SYMBOL)
    unsafe = classify_symbol("NSE:BANKNIFTY-INDEX")
    unrelated = classify_symbol("NSE:NOTNIFTYBANK-INDEX")
    assert index.instrument_class is InstrumentClass.INDEX
    assert index.canonical_symbol == CANONICAL_INDEX_SYMBOL
    assert unsafe.instrument_class is InstrumentClass.UNKNOWN_SYMBOL
    assert unrelated.instrument_class is InstrumentClass.UNKNOWN_SYMBOL
    assert classify_symbol(
        "NSE:BANKNIFTY26AUGFUT", expiry="2026-09-29"
    ).instrument_class is InstrumentClass.UNKNOWN_SYMBOL
    assert classify_symbol(
        "NSE:BANKNIFTY26AUG57100CE", strike=57_200, option_type="CE", expiry="2026-08-25"
    ).instrument_class is InstrumentClass.UNKNOWN_SYMBOL


def test_market_envelope_is_lossless_and_files_merge_by_receipt(tmp_path):
    data, contract = _contract(tmp_path)
    earlier = _timestamp(-0.5)
    later = _timestamp(-0.1)
    (data / "raw/2099-01-01/events_09.jsonl").write_text(
        _market(later, "NSE:BANKNIFTY26AUGFUT", 57_125.2, 1_230) + "\n"
    )
    (data / "raw/2099-01-01/events_10.jsonl").write_text(
        _market(earlier, CANONICAL_INDEX_SYMBOL, 57_100.45, 98_765) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    rows = ingestor.poll()
    assert all(isinstance(row, TypedObservation) for row in rows)
    assert [row.instrument_class for row in rows] == ["INDEX", "FUTURES"]
    assert rows[0].receipt_timestamp == earlier
    assert rows[0].event_timestamp == earlier
    assert rows[0].price == 57_100.45
    assert rows[0].cumulative_volume == 98_765
    assert rows[0].source_stream == "raw"
    assert rows[1].price == 57_125.2
    assert rows[1].cumulative_volume == 1_230
    assert "access_token" not in rows[1].canonical_payload
    assert "secret" not in rows[1].canonical_payload
    assert rows[0]["observation_id"] == rows[0].event_id
    ingestor.close()


def test_projection_padding_advances_physical_row_without_refusal(tmp_path):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    valid = (_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100.45, 98_765) + "\n").encode()
    malformed = b'{"received_at":\n'
    payload = b"\n \t\r\n" + valid + malformed
    path.write_bytes(payload)

    ingestor = IncrementalJSONLIngestor(contract)
    rows = ingestor.poll()

    assert len(rows) == 1
    assert rows[0].source_row_number == 3
    assert ingestor.metrics["projection_padding_lines"] == 2
    assert ingestor.metrics["malformed"] == 1
    refusals = ingestor.ledgers["refusals_data_quality"].rows()
    assert [row["reason"] for row in refusals] == ["MALFORMED_JSONL"]
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    checkpoint = ingestor.checkpoints[str(path.relative_to(data))]
    assert checkpoint["offset"] == len(payload)
    assert checkpoint["row"] == 4
    assert ingestor.db.execute("select count(*) from observation_outbox").fetchone()[0] == 1
    ingestor.close()


def test_same_inode_same_size_rewrite_is_refused_replayably(tmp_path):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.2)
    path = data / "raw/2099-01-01/events_09.jsonl"
    original = (_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n").encode()
    replacement = (_market(receipt, CANONICAL_INDEX_SYMBOL, 57_101, 100) + "\n").encode()
    assert len(original) == len(replacement)
    path.write_bytes(original)

    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll()) == 1
    checkpoint = dict(ingestor.checkpoints[str(path.relative_to(data))])
    inode = path.stat().st_ino
    with path.open("r+b") as handle:
        handle.write(replacement)
        handle.flush()
        os.fsync(handle.fileno())
    if path.stat().st_mtime_ns == checkpoint["mtime_ns_at_commit"]:
        os.utime(
            path,
            ns=(path.stat().st_atime_ns, checkpoint["mtime_ns_at_commit"] + 1),
        )
    assert path.stat().st_ino == inode
    assert path.stat().st_size == checkpoint["offset"]

    assert ingestor.poll(source_paths=[path]) == []
    assert ingestor.checkpoints[str(path.relative_to(data))]["offset"] == checkpoint["offset"]
    assert any(
        row["reason"] == "FILE_REPLACED_IN_PLACE"
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[path]) == []
    assert len(restarted.ledgers["normalized_raw_events"].rows()) == 1
    restarted.close()


def test_same_inode_committed_prefix_rewrite_with_growth_is_refused(tmp_path):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.3)
    path = data / "raw/2099-01-01/events_09.jsonl"
    original = (_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n").encode()
    replacement = (_market(receipt, CANONICAL_INDEX_SYMBOL, 57_101, 100) + "\n").encode()
    appended = (
        _market(_timestamp(-0.1), "NSE:BANKNIFTY26AUGFUT", 57_125, 200) + "\n"
    ).encode()
    assert len(original) == len(replacement)
    path.write_bytes(original)

    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    checkpoint = dict(ingestor.checkpoints[str(path.relative_to(data))])
    inode = path.stat().st_ino
    with path.open("r+b") as handle:
        handle.seek(0)
        handle.write(replacement)
        handle.seek(0, os.SEEK_END)
        handle.write(appended)
        handle.flush()
        os.fsync(handle.fileno())
    assert path.stat().st_ino == inode
    assert path.stat().st_size > checkpoint["offset"]

    assert ingestor.poll(source_paths=[path]) == []
    assert ingestor.checkpoints[str(path.relative_to(data))]["offset"] == checkpoint["offset"]
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    assert any(
        row["reason"] == "FILE_REPLACED_IN_PLACE"
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[path]) == []
    assert len(restarted.ledgers["normalized_raw_events"].rows()) == 1
    restarted.close()


def test_future_receipt_is_strictly_refused_and_publication_never_backdates(tmp_path):
    data, contract = _contract(tmp_path)
    future_path = data / "raw/2099-01-01/events_09.jsonl"
    future_path.write_text(
        _market(_timestamp(1.0), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)

    assert ingestor.poll(source_paths=[future_path]) == []
    assert not ingestor.ledgers["normalized_raw_events"].rows()
    assert any(
        row["reason"] == "TIMESTAMP_REFUSED"
        and "future live receipt timestamp" in row["detail"]
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )

    accepted_path = data / "raw/2099-01-01/events_10.jsonl"
    accepted_path.write_text(
        _market(_timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 101) + "\n"
    )
    rows = ingestor.poll(source_paths=[accepted_path])
    assert len(rows) == 1
    assert datetime.fromisoformat(rows[0].publication_timestamp) >= datetime.fromisoformat(
        rows[0].receipt_timestamp
    )
    ingestor.close()


def test_oi_rows_expand_to_futures_ce_and_pe_without_field_loss(tmp_path):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.1)
    future = {
        "source": "future_depth",
        "request_time": receipt,
        "received_at": receipt,
        "requested_symbol": "NSE:BANKNIFTY26AUGFUT",
        "response": {"d": {"NSE:BANKNIFTY26AUGFUT": {
            "ltp": 57_130.2, "v": 12_345, "oi": 1_984_800,
            "pdoi": 1_986_030, "expiry": "2026-08-25",
            "bids": [{"price": 57_129.8, "volume": 30}],
            "ask": [{"price": 57_130.4, "volume": 30}],
        }}},
    }
    option = {
        "source": "option_chain",
        "request_time": receipt,
        "received_at": receipt,
        "response": {"data": {
            "expiryData": [{"date": "25-08-2026"}],
            "optionsChain": [
                {"symbol": CANONICAL_INDEX_SYMBOL, "ltp": 57_100.0, "fp": 57_130.2, "strike_price": -1},
                {"symbol": "NSE:BANKNIFTY26AUG57100CE", "option_type": "CE", "strike_price": 57_100,
                 "ltp": 520.5, "volume": 3_000, "oi": 20_000, "prev_oi": 19_500, "oich": 500},
                {"symbol": "NSE:BANKNIFTY26AUG57100PE", "option_type": "PE", "strike_price": 57_100,
                 "ltp": 480.25, "volume": 2_700, "oi": 22_000, "prev_oi": 22_300, "oich": -300},
            ],
        }},
    }
    (data / "oi/2099-01-01/oi_09.jsonl").write_text(
        json.dumps(future) + "\n" + json.dumps(option) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    rows = ingestor.poll()
    by_class = {row.instrument_class: row for row in rows}
    assert set(by_class) == {"FUTURES_OI", "CE", "PE"}
    futures = by_class["FUTURES_OI"]
    assert (futures.price, futures.cumulative_volume, futures.open_interest) == (57_130.2, 12_345, 1_984_800)
    assert futures.previous_open_interest == 1_986_030
    assert futures.open_interest_change == -1_230
    assert futures.expiry == "2026-08-25"
    assert futures.source_stream == "oi"
    assert (futures.bid_price, futures.ask_price) == (57_129.8, 57_130.4)
    ce = by_class["CE"]
    pe = by_class["PE"]
    assert (ce.price, ce.cumulative_volume, ce.oi, ce.delta_oi) == (520.5, 3_000, 20_000, 500)
    assert (pe.price, pe.cumulative_volume, pe.oi, pe.delta_oi) == (480.25, 2_700, 22_000, -300)
    assert ce.strike == pe.strike == 57_100
    assert ce.expiry == pe.expiry == "2026-08-25"
    assert ce.underlying_price == pe.underlying_price == 57_100
    assert ce.forward_price == pe.forward_price == 57_130.2
    underlying_audit = [
        row for row in ingestor.unknown_symbol_audit()
        if row["reason"] == "IGNORED_OPTION_CHAIN_UNDERLYING_REFERENCE"
    ]
    assert len(underlying_audit) == 1
    assert underlying_audit[0]["observation_count"] == 1
    ingestor.close()


def test_unknown_is_auditable_and_callback_restart_is_exactly_once(tmp_path):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(
        _market(receipt, "NSE:BANKNIFTY-INDEX", 57_100, 100) + "\n"
        + _market(receipt, CANONICAL_INDEX_SYMBOL, 57_101, 101) + "\n"
    )
    received = []
    first = IncrementalJSONLIngestor(contract, received.append)
    rows = first.poll()
    assert received == rows
    by_class = {row.instrument_class: row for row in rows}
    assert set(by_class) == {"INDEX"}
    audit = first.unknown_symbol_audit()
    assert len(audit) == 1
    assert audit[0]["source_symbol"] == "NSE:BANKNIFTY-INDEX"
    assert audit[0]["reason"] == "UNKNOWN_SYMBOL"
    assert audit[0]["observation_count"] == 1
    assert audit[0]["first_byte_offset"] == 0
    assert audit[0]["last_byte_offset"] == 0
    first.close()

    replayed = []
    restarted = IncrementalJSONLIngestor(contract, replayed.append)
    assert restarted.poll() == []
    assert replayed == []
    assert len(restarted.ledgers["normalized_raw_events"].rows()) == 1
    assert sum(row["observation_count"] for row in restarted.unknown_symbol_audit()) == 1
    restarted.close()


def test_callback_failure_keeps_multirow_outbox_and_does_not_advance_high_water(tmp_path):
    data, contract = _contract(tmp_path)
    first_receipt = _timestamp(-0.5)
    second_receipt = _timestamp(-0.4)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(
        _market(first_receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
        + _market(second_receipt, CANONICAL_INDEX_SYMBOL, 57_101, 101) + "\n"
    )

    calls = []

    def fail_first(observation):
        calls.append(observation.observation_id)
        raise RuntimeError("synthetic callback crash")

    failed = IncrementalJSONLIngestor(contract, fail_first)
    with pytest.raises(RuntimeError, match="synthetic callback crash"):
        failed.poll()
    assert len(calls) == 1
    assert failed.checkpoints[str(path.relative_to(data))]["offset"] == path.stat().st_size
    assert failed.db.execute("select count(*) from observation_outbox").fetchone()[0] == 2
    assert failed.db.execute(
        "select value from runtime_meta where key='causal_high_water'"
    ).fetchone() is None
    failed.close()

    replayed = []
    recovered = IncrementalJSONLIngestor(contract, replayed.append)
    rows = recovered.poll()
    assert [row.observation_id for row in rows] == [row.observation_id for row in replayed]
    assert len(rows) == 2
    assert all(not row.out_of_order for row in rows)
    assert recovered.db.execute("select count(*) from observation_outbox").fetchone()[0] == 0
    recovered.close()

    final = IncrementalJSONLIngestor(contract, replayed.append)
    assert final.poll() == []
    assert len(replayed) == 2
    final.close()


def test_batch_callback_receives_one_causal_poll_and_is_acked_only_after_success(tmp_path):
    data, contract = _contract(tmp_path)
    base = datetime.now(IST) - timedelta(seconds=1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text("".join(
        _market(
            (base + timedelta(milliseconds=ordinal)).isoformat(timespec="microseconds"),
            CANONICAL_INDEX_SYMBOL,
            57_100 + ordinal,
            ordinal,
        ) + "\n"
        for ordinal in range(3)
    ))

    class BatchSink:
        def __init__(self):
            self.batches = []

        def process_observations(self, observations):
            self.batches.append(list(observations))

    sink = BatchSink()
    ingestor = IncrementalJSONLIngestor(contract, sink)
    rows = ingestor.poll()
    assert sink.batches == [rows]
    assert [row.price for row in rows] == [57_100, 57_101, 57_102]
    assert ingestor.db.execute("select count(*) from observation_outbox").fetchone()[0] == 0
    ingestor.close()
    restarted = IncrementalJSONLIngestor(contract, sink)
    assert restarted.poll() == []
    assert len(sink.batches) == 1
    restarted.close()


def test_poll_crash_before_clean_close_replays_but_clean_close_acknowledges(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(_market(_timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n")
    crashed = IncrementalJSONLIngestor(contract)
    original = crashed.poll()
    assert len(original) == 1
    assert crashed.db.execute("select count(*) from observation_outbox").fetchone()[0] == 1
    crashed.db.close()  # Simulate process death: do not call the clean-close acknowledgement.

    recovered = IncrementalJSONLIngestor(contract)
    replay = recovered.poll()
    assert [row.observation_id for row in replay] == [row.observation_id for row in original]
    assert all(not row.out_of_order for row in replay)
    recovered.close()
    final = IncrementalJSONLIngestor(contract)
    assert final.poll() == []
    final.close()


def test_normalized_writes_are_batched_and_checkpoint_prevents_reread(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    base = datetime.now(IST) - timedelta(seconds=1)
    path.write_text("".join(
        _market(
            (base + timedelta(microseconds=ordinal)).isoformat(timespec="microseconds"),
            CANONICAL_INDEX_SYMBOL,
            57_100 + ordinal / 100,
            ordinal,
        ) + "\n"
        for ordinal in range(100)
    ))
    ingestor = IncrementalJSONLIngestor(contract)
    batches = []
    original_append_many = ingestor.ledgers["normalized_raw_events"].append_many

    def record_batch(rows):
        rows = list(rows)
        batches.append(len(rows))
        original_append_many(rows)

    ingestor.ledgers["normalized_raw_events"].append_many = record_batch
    assert len(ingestor.poll()) == 100
    assert batches == [100]
    assert ingestor.db.execute("select count(*) from seen").fetchone()[0] == 0
    assert ingestor.db.execute("select count(*) from file_checkpoint").fetchone()[0] == 1
    bytes_after_first = ingestor.metrics["bytes"]
    assert ingestor.poll() == []
    assert ingestor.metrics["bytes"] == bytes_after_first
    ingestor.close()


def test_unknown_reconciliation_aggregates_cash_and_noncanonical_option_source(tmp_path):
    data, contract = _contract(tmp_path)
    receipts = [_timestamp(-0.5), _timestamp(-0.4), _timestamp(-0.3), _timestamp(-0.2)]
    lines = [
        _market(receipts[0], "NSE:SBIN-EQ", 900, 1),
        _market(receipts[1], "NSE:SBIN-EQ", 901, 2),
        _market(receipts[2], "NSE:BANKNIFTY26AUG57100CE", 500, 3),
        _market(receipts[3], CANONICAL_INDEX_SYMBOL, 57_100, 4),
    ]
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text("".join(line + "\n" for line in lines))
    callback_rows = []
    ingestor = IncrementalJSONLIngestor(contract, callback_rows.append)
    rows = ingestor.poll()
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert callback_rows == rows
    audit = {(row["source_symbol"], row["reason"]): row for row in ingestor.unknown_symbol_audit()}
    cash = audit[("NSE:SBIN-EQ", "UNKNOWN_SYMBOL")]
    assert cash["observation_count"] == 2
    assert cash["first_receipt"] == receipts[0]
    assert cash["last_receipt"] == receipts[1]
    assert cash["first_byte_offset"] == 0
    assert cash["last_byte_offset"] == len((lines[0] + "\n").encode())
    option = audit[(
        "NSE:BANKNIFTY26AUG57100CE",
        "IGNORED_NONCANONICAL_OPTION_PREMIUM_SOURCE",
    )]
    assert option["observation_count"] == 1
    assert sum(row["observation_count"] for row in audit.values()) + len(rows) == len(lines)
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    ingestor.close()


def test_k_way_watermark_does_not_backdate_second_older_chunk(tmp_path):
    data, contract = _contract(tmp_path)
    base = datetime.now(IST) - timedelta(seconds=2)
    a0 = _market(base.isoformat(timespec="microseconds"), CANONICAL_INDEX_SYMBOL, 57_100, 1)
    a1 = _market((base + timedelta(milliseconds=100)).isoformat(timespec="microseconds"), CANONICAL_INDEX_SYMBOL, 57_101, 2)
    b0 = _market((base + timedelta(milliseconds=200)).isoformat(timespec="microseconds"), CANONICAL_INDEX_SYMBOL, 57_102, 3)
    first = data / "raw/2099-01-01/events_09.jsonl"
    later = data / "raw/2099-01-01/events_10.jsonl"
    first.write_text(a0 + "\n" + a1 + "\n")
    later.write_text(b0 + "\n")
    contract["config"]["max_read_bytes_per_file_per_poll"] = max(
        len((a0 + "\n").encode()), len((b0 + "\n").encode())
    ) + 1
    ingestor = IncrementalJSONLIngestor(contract)
    cycle_one = ingestor.poll()
    assert [row.price for row in cycle_one] == [57_100]
    cycle_two = ingestor.poll()
    assert [row.price for row in cycle_two] == [57_101, 57_102]
    assert all(not row.out_of_order for row in cycle_one + cycle_two)
    assert not any(
        row["reason"] == "OUT_OF_ORDER_RECEIPT"
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    ingestor.close()


def test_empty_growing_stream_blocks_later_receipt_until_first_frontier(tmp_path):
    data, contract = _contract(tmp_path)
    base = datetime.now(IST) - timedelta(seconds=2)
    earlier_receipt = (base + timedelta(milliseconds=100)).isoformat(timespec="microseconds")
    later_receipt = (base + timedelta(milliseconds=200)).isoformat(timespec="microseconds")
    first = data / "raw/2099-01-01/events_09.jsonl"
    growing = data / "raw/2099-01-01/events_10.jsonl"
    first.write_text(
        _market(later_receipt, CANONICAL_INDEX_SYMBOL, 57_102, 2) + "\n"
    )
    growing.write_text("")

    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll() == []

    with growing.open("a") as handle:
        handle.write(
            _market(earlier_receipt, CANONICAL_INDEX_SYMBOL, 57_101, 1) + "\n"
        )
    rows = ingestor.poll()
    assert [row.price for row in rows] == [57_101, 57_102]
    assert [row.receipt_timestamp for row in rows] == [earlier_receipt, later_receipt]
    assert all(not row.out_of_order for row in rows)
    assert not any(
        row["reason"] == "OUT_OF_ORDER_RECEIPT"
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    ingestor.close()


def test_session_selection_defers_raw_future_until_verified_depth_arrives(tmp_path):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    raw_receipt = f"{session}T09:15:00.100000+05:30"
    oi_receipt = f"{session}T09:15:01.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(raw_receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll() == []
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 1
    assert ingestor.checkpoints[str(raw_path.relative_to(data))]["offset"] == raw_path.stat().st_size

    depth = {
        "source": "future_depth",
        "request_time": oi_receipt,
        "received_at": oi_receipt,
        "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    (data / f"oi/{session}/oi_09.jsonl").write_text(json.dumps(depth) + "\n")
    rows = ingestor.poll()
    assert [row.instrument_class for row in rows] == ["FUTURES", "FUTURES_OI"]
    assert rows[0].price == 58_130.2
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 0
    assert not any(
        row["reason"] == "FUTURES_SELECTION_PENDING"
        for row in ingestor.unknown_symbol_audit()
    )
    ingestor.close()


def test_registry_selects_nearest_unexpired_then_oi_and_refuses_unselected():
    registry = SymbolRegistry()
    selected = registry.select_session_futures(
        "2026-08-20",
        [
            ("NSE:BANKNIFTY26SEPFUT", "2026-09-29", 3_000_000),
            ("NSE:BANKNIFTY26AUGFUT", "2026-08-25", 1_000_000),
        ],
        as_of_date="2026-08-20",
    )
    assert selected == "NSE:BANKNIFTY26AUGFUT"
    assert registry.classify(
        selected, source_kind="future_depth", expiry="2026-08-25",
        session_date="2026-08-20",
    ).instrument_class is InstrumentClass.FUTURES_OI
    refused = registry.classify(
        "NSE:BANKNIFTY26SEPFUT", source_kind="future_depth",
        expiry="2026-09-29", session_date="2026-08-20",
    )
    assert refused.instrument_class is InstrumentClass.UNKNOWN_SYMBOL
    assert refused.reason == "UNSELECTED_FUTURES_CONTRACT"

    activation = SymbolRegistry()
    assert activation.select_session_futures(
        "2026-08-26",
        [
            ("NSE:BANKNIFTY26AUGFUT", "2026-08-25", 9_000_000),
            ("NSE:BANKNIFTY26SEPFUT", "2026-09-29", 2_000_000),
        ],
        as_of_date="2026-08-26",
    ) == "NSE:BANKNIFTY26SEPFUT"


def test_session_futures_selection_is_immutable_after_first_canonical_choice():
    registry = SymbolRegistry()
    assert registry.select_session_futures(
        "2026-08-20",
        [("NSE:BANKNIFTY26AUGFUT", "2026-08-25", 1_000_000)],
    ) == "NSE:BANKNIFTY26AUGFUT"
    assert registry.select_session_futures(
        "2026-08-20",
        [("NSE:BANKNIFTY26SEPFUT", "2026-09-29", 9_000_000)],
    ) == "NSE:BANKNIFTY26AUGFUT"


def test_raw_run_identity_survives_process_restart(tmp_path):
    _, contract = _contract(tmp_path)
    first = IncrementalJSONLIngestor(contract)
    assert first.c["raw_run_id"] == "R6E1R-TEST"
    first.close()

    restarted_contract = dict(contract)
    restarted_contract["raw_run_id"] = "SHOULD-NOT-REPLACE-DURABLE-RUN"
    restarted = IncrementalJSONLIngestor(restarted_contract)
    assert restarted.c["raw_run_id"] == "R6E1R-TEST"
    restarted.close()


def test_current_engine_hash_is_allowlisted_deterministic_and_content_sensitive(tmp_path):
    (tmp_path / "a.py").write_text("A\n")
    (tmp_path / "b.py").write_text("B\n")
    allowlist = ("b.py", "a.py")
    first = engine_hash(tmp_path, allowlist)
    assert first == engine_hash(tmp_path, reversed(allowlist))
    assert [row["path"] for row in engine_source_inventory(tmp_path, allowlist)] == [
        "a.py", "b.py",
    ]
    (tmp_path / "b.py").write_text("CHANGED\n")
    assert engine_hash(tmp_path, allowlist) != first
    with pytest.raises(ValueError, match="unsafe engine source"):
        engine_hash(tmp_path, ("../outside.py",))


def test_validated_changed_path_hint_uses_same_checkpoint_path(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(
        _market(_timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    rows = ingestor.poll(source_paths=[path])
    assert len(rows) == 1
    assert ingestor.checkpoints[str(path.relative_to(data))]["offset"] == path.stat().st_size
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n")
    with pytest.raises(ValueError, match="outside raw data root"):
        ingestor.poll(source_paths=[outside])
    ingestor.close()
