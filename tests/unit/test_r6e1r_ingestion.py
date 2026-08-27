from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

import banknifty_profiler.shadow.ledger as ledger_module
from banknifty_profiler.runtime.timestamps import parse_timestamp
from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.contracts import engine_hash, engine_source_inventory
from banknifty_profiler.shadow.api import _AuditReadCache
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.ledger import AppendOnlyLedger
from banknifty_profiler.shadow.observation import TypedObservation
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.shadow.state import ShadowState
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


def _direct_contract(tmp_path):
    """Build an unsealed unit contract for durable-state corruption tests."""
    data = tmp_path / "collector"
    (data / "raw/2099-01-01").mkdir(parents=True)
    (data / "oi/2099-01-01").mkdir(parents=True)
    return data, {
        "data_root": data,
        "state_root": tmp_path / "state",
        "raw_run_id": "R6E1R-DIRECT-TEST",
        "engine_hash": "ENGINE",
        "configuration_hash": "CONFIG",
        "config": {
            "max_read_bytes_per_file_per_poll": 1_048_576,
            "max_buffer_bytes_per_file": 1_048_576,
            "selected_futures_by_session": {
                "2099-01-01": "NSE:BANKNIFTY26AUGFUT"
            },
        },
    }


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


def _seed_checkpoint_authority(ingestor, data: Path, source: Path) -> None:
    """Give synthetic ledger-only tests the authority production persists first."""
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file() or source.stat().st_size == 0:
        source.write_bytes(b"\n")
    stat = source.stat()
    payload = source.read_bytes()
    relative = str(source.relative_to(data))
    with ingestor.db:
        ingestor.db.execute(
            "insert into file_checkpoint("
            "source_file,offset,row_number,identity,size_at_commit,updated_at,"
            "frontier,prefix_fingerprint,mtime_ns_at_commit) "
            "values (?,?,?,?,?,?,?,?,?)",
            (
                relative,
                len(payload),
                payload.count(b"\n"),
                f"{stat.st_dev}:{stat.st_ino}",
                len(payload),
                _timestamp(-0.5),
                None,
                hashlib.sha256(payload).hexdigest(),
                stat.st_mtime_ns,
            ),
        )


@pytest.mark.parametrize("database_mode", ("missing", "empty"))
def test_nonempty_checkpoint_mirror_cannot_create_sqlite_authority(
    tmp_path, database_mode,
):
    data, runtime = _direct_contract(tmp_path)
    receipt = _timestamp(-0.1)
    source = data / "raw/2099-01-01/events_09.jsonl"
    source.write_text(
        _market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )
    source_stat = source.stat()
    relative = str(source.relative_to(data))
    state = runtime["state_root"]
    state.mkdir()
    (state / "checkpoints.json").write_text(json.dumps({
        relative: {
            "offset": source_stat.st_size,
            "row": 1,
            "identity": f"{source_stat.st_dev}:{source_stat.st_ino}",
            "size_at_commit": source_stat.st_size,
            "updated_at": receipt,
            "prefix_fingerprint": "",
            "mtime_ns_at_commit": source_stat.st_mtime_ns,
        },
    }))
    if database_mode == "empty":
        sqlite3.connect(state / "dedup.sqlite3").close()

    with pytest.raises(
        ValueError,
        match=(
            "prior ingestion evidence lacks durable SQLite authority; "
            "clean rebuild required"
        ),
    ):
        IncrementalJSONLIngestor(runtime)

    assert not (state / "ledgers/raw_file_checkpoints.jsonl").exists()
    assert not (state / "ledgers/normalized_raw_events.jsonl").exists()


@pytest.mark.parametrize("mirror_mode", ("absent", "empty"))
@pytest.mark.parametrize("database_mode", ("missing", "empty"))
def test_durable_checkpoint_ledger_requires_sqlite_authority_without_mirror(
    tmp_path, mirror_mode, database_mode,
):
    data, runtime = _direct_contract(tmp_path)
    receipt = _timestamp(-0.1)
    source = data / "raw/2099-01-01/events_09.jsonl"
    source.write_text(
        _market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )

    bootstrap = IncrementalJSONLIngestor(runtime)
    assert len(bootstrap.poll(source_paths=[source])) == 1
    bootstrap.close()

    state = runtime["state_root"]
    checkpoint_ledger = state / "ledgers/raw_file_checkpoints.jsonl"
    normalized_ledger = state / "ledgers/normalized_raw_events.jsonl"
    checkpoint_before = checkpoint_ledger.read_bytes()
    normalized_before = normalized_ledger.read_bytes()
    (state / "dedup.sqlite3").unlink()
    if database_mode == "empty":
        sqlite3.connect(state / "dedup.sqlite3").close()
    (state / "checkpoints.json").unlink()
    if mirror_mode == "empty":
        (state / "checkpoints.json").write_text("{}\n")

    with pytest.raises(
        ValueError,
        match=(
            "prior ingestion evidence lacks durable SQLite authority; "
            "clean rebuild required"
        ),
    ):
        IncrementalJSONLIngestor(runtime)

    assert checkpoint_ledger.read_bytes() == checkpoint_before
    assert normalized_ledger.read_bytes() == normalized_before


def test_clean_new_state_builds_sqlite_authority_from_raw_bytes(tmp_path):
    data, runtime = _direct_contract(tmp_path)
    receipt = _timestamp(-0.1)
    source = data / "raw/2099-01-01/events_09.jsonl"
    source.write_text(
        _market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )

    ingestor = IncrementalJSONLIngestor(runtime)
    rows = ingestor.poll()

    assert len(rows) == 1
    assert rows[0].instrument_class == InstrumentClass.INDEX.value
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    assert len(ingestor.ledgers["raw_file_checkpoints"].rows()) == 1
    assert ingestor.checkpoint_health()["valid"] is True
    ingestor.close()


def test_normalized_ledger_cannot_hide_deleted_sqlite_checkpoint_authority(
    tmp_path,
):
    data, runtime = _direct_contract(tmp_path)
    source = data / "raw/2099-01-01/events_09.jsonl"
    source.write_text(
        _market(
            _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_100, 100,
        ) + "\n"
    )
    bootstrap = IncrementalJSONLIngestor(runtime)
    assert len(bootstrap.poll(source_paths=[source])) == 1
    bootstrap.close()

    state = runtime["state_root"]
    normalized = state / "ledgers/normalized_raw_events.jsonl"
    normalized_before = normalized.read_bytes()
    with sqlite3.connect(state / "dedup.sqlite3") as database:
        database.execute("delete from file_checkpoint")
    (state / "checkpoints.json").unlink()
    (state / "ledgers/raw_file_checkpoints.jsonl").unlink()

    with pytest.raises(
        ValueError,
        match=(
            "prior ingestion evidence lacks durable SQLite authority; "
            "clean rebuild required"
        ),
    ):
        IncrementalJSONLIngestor(runtime)

    assert normalized.read_bytes() == normalized_before


def test_trusted_sources_cannot_hide_partial_sqlite_checkpoint_rollback(
    tmp_path,
):
    data, runtime = _direct_contract(tmp_path)
    first = data / "raw/2099-01-01/events_09.jsonl"
    second = data / "raw/2099-01-01/events_10.jsonl"
    first.write_text(
        _market(
            _timestamp(-0.2), CANONICAL_INDEX_SYMBOL, 57_100, 100,
        ) + "\n"
    )
    second.write_text(
        _market(
            _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_200, 200,
        ) + "\n"
    )
    bootstrap = IncrementalJSONLIngestor(runtime)
    assert len(bootstrap.poll(source_paths=[first, second])) == 2
    bootstrap.close()

    state = runtime["state_root"]
    mirror_before = (state / "checkpoints.json").read_bytes()
    checkpoint_ledger = state / "ledgers/raw_file_checkpoints.jsonl"
    checkpoint_before = checkpoint_ledger.read_bytes()
    normalized_ledger = state / "ledgers/normalized_raw_events.jsonl"
    normalized_before = normalized_ledger.read_bytes()
    first_relative = str(first.relative_to(data))
    with sqlite3.connect(state / "dedup.sqlite3") as database:
        database.execute(
            "delete from file_checkpoint where source_file=?",
            (first_relative,),
        )

    with pytest.raises(
        ValueError,
        match=(
            "prior ingestion evidence lacks durable SQLite authority; "
            "clean rebuild required"
        ),
    ):
        IncrementalJSONLIngestor(runtime)

    assert (state / "checkpoints.json").read_bytes() == mirror_before
    assert checkpoint_ledger.read_bytes() == checkpoint_before
    assert normalized_ledger.read_bytes() == normalized_before


def test_trusted_rows_cannot_hide_same_source_checkpoint_rollback(tmp_path):
    data, runtime = _direct_contract(tmp_path)
    source = data / "raw/2099-01-01/events_09.jsonl"
    first_line = _market(
        _timestamp(-0.2), CANONICAL_INDEX_SYMBOL, 57_100, 100,
    ) + "\n"
    second_line = _market(
        _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_200, 200,
    ) + "\n"
    source.write_text(first_line)
    ingestor = IncrementalJSONLIngestor(runtime)
    assert len(ingestor.poll(source_paths=[source])) == 1
    relative = str(source.relative_to(data))
    first_checkpoint = ingestor.db.execute(
        "select offset,row_number,identity,size_at_commit,updated_at,frontier,"
        "prefix_fingerprint,mtime_ns_at_commit from file_checkpoint "
        "where source_file=?",
        (relative,),
    ).fetchone()
    assert first_checkpoint is not None
    with source.open("a") as handle:
        handle.write(second_line)
    assert len(ingestor.poll(source_paths=[source])) == 1
    ingestor.close()

    state = runtime["state_root"]
    mirror_before = (state / "checkpoints.json").read_bytes()
    with sqlite3.connect(state / "dedup.sqlite3") as database:
        database.execute(
            "update file_checkpoint set offset=?,row_number=?,identity=?,"
            "size_at_commit=?,updated_at=?,frontier=?,prefix_fingerprint=?,"
            "mtime_ns_at_commit=? where source_file=?",
            (*first_checkpoint, relative),
        )

    with pytest.raises(
        ValueError,
        match=(
            "prior ingestion evidence lacks durable SQLite authority; "
            "clean rebuild required"
        ),
    ):
        IncrementalJSONLIngestor(runtime)

    assert (state / "checkpoints.json").read_bytes() == mirror_before


def test_sqlite_authority_ignores_and_rewrites_forged_extra_mirror_row(
    tmp_path,
):
    data, runtime = _direct_contract(tmp_path)
    first_receipt = _timestamp(-0.2)
    first_source = data / "raw/2099-01-01/events_09.jsonl"
    first_source.write_text(
        _market(first_receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )
    bootstrap = IncrementalJSONLIngestor(runtime)
    assert len(bootstrap.poll(source_paths=[first_source])) == 1
    bootstrap.close()

    state = runtime["state_root"]
    authoritative = json.loads((state / "checkpoints.json").read_text())
    second_receipt = _timestamp(-0.1)
    second_source = data / "raw/2099-01-01/events_10.jsonl"
    second_source.write_text(
        _market(second_receipt, CANONICAL_INDEX_SYMBOL, 57_200, 200) + "\n"
    )
    second_stat = second_source.stat()
    second_relative = str(second_source.relative_to(data))
    forged_mirror = dict(authoritative)
    forged_mirror[second_relative] = {
        "offset": second_stat.st_size,
        "row": 1,
        "identity": f"{second_stat.st_dev}:{second_stat.st_ino}",
        "size_at_commit": second_stat.st_size,
        "updated_at": second_receipt,
        "prefix_fingerprint": hashlib.sha256(
            second_source.read_bytes()
        ).hexdigest(),
        "mtime_ns_at_commit": second_stat.st_mtime_ns,
    }
    (state / "checkpoints.json").write_text(json.dumps(forged_mirror))

    recovered = IncrementalJSONLIngestor(runtime)

    assert recovered.checkpoints == authoritative
    assert json.loads(recovered.checkpoint_path.read_text()) == authoritative
    rows = recovered.poll(source_paths=[second_source])
    assert len(rows) == 1
    assert rows[0].source_file == second_relative
    assert rows[0].instrument_class == InstrumentClass.INDEX.value
    assert recovered.db.execute(
        "select count(*) from file_checkpoint"
    ).fetchone()[0] == 2
    assert set(json.loads(recovered.checkpoint_path.read_text())) == {
        *authoritative,
        second_relative,
    }
    recovered.close()


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


@pytest.mark.parametrize(
    "ledger_name",
    (
        "normalized_raw_events",
        "raw_file_checkpoints",
        "refusals_data_quality",
    ),
)
def test_ingestion_startup_refuses_schema_empty_unique_event(
    tmp_path, ledger_name,
):
    _data, runtime = _direct_contract(tmp_path)
    ledger = AppendOnlyLedger(
        runtime["state_root"] / "ledgers" / f"{ledger_name}.jsonl"
    )
    ledger.append({"event_id": "MALFORMED-BUT-UNIQUE"})

    with pytest.raises(ValueError, match=f"{ledger_name} ledger row 1"):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("index_from_oi", "invalid Index identity"),
        ("wrong_index_symbol", "invalid Index identity"),
        ("futures_from_oi", "invalid Futures identity"),
        ("option_shape", "invalid option identity"),
        ("filtered_candidate", "invalid status"),
    ),
)
def test_normalized_startup_refuses_class_inconsistent_identity(
    tmp_path, mutation, message,
):
    data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    row = ingestor._normalize_record(
        data / "raw/2099-01-01/events_09.jsonl",
        json.loads(_market(
            receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100,
        )),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id=f"RAW-{mutation}",
    )[0].to_dict()

    if mutation == "index_from_oi":
        row["source_stream"] = "oi"
        row["source_file"] = "oi/2099-01-01/oi_09.jsonl"
    elif mutation == "wrong_index_symbol":
        row["canonical_symbol"] = "NSE:BANKNIFTY-INDEX"
        row["source_symbol"] = "NSE:BANKNIFTY-INDEX"
    elif mutation == "futures_from_oi":
        row["instrument_class"] = "FUTURES"
        row["canonical_symbol"] = "NSE:BANKNIFTY26AUGFUT"
        row["source_symbol"] = "NSE:BANKNIFTY26AUGFUT"
        row["source_stream"] = "oi"
        row["source_file"] = "oi/2099-01-01/oi_09.jsonl"
    elif mutation == "option_shape":
        row["instrument_class"] = "CE"
        row["canonical_symbol"] = "NSE:BANKNIFTY26AUG57100CE"
        row["source_symbol"] = "NSE:BANKNIFTY26AUG57100CE"
        row["source_stream"] = "oi"
        row["source_file"] = "oi/2099-01-01/oi_09.jsonl"
        row["option_type"] = None
        row["strike"] = None
        row["expiry"] = None
        row["expiry_date"] = None
    else:
        row["instrument_class"] = "UNKNOWN_SYMBOL"
        row["canonical_symbol"] = None
        row["source_symbol"] = "NSE:BANKNIFTY26AUGFUT"
        row["status"] = "FILTERED"
        row["classification_reason"] = "FUTURES_SELECTION_PENDING"
    row["source_receipt_identifiers"]["file"] = row["source_file"]
    row["source_receipt_identifiers"]["source_stream"] = row[
        "source_stream"
    ]
    ingestor.ledgers["normalized_raw_events"].append(row)
    ingestor.close()

    with pytest.raises(ValueError, match=message):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize("provenance", (None, "UNKNOWN"))
def test_refusal_startup_requires_exact_timestamp_provenance(
    tmp_path, provenance,
):
    _data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    ingestor._quality(
        "MALFORMED_JSONL",
        "raw/2099-01-01/events_09.jsonl",
        1,
        0,
        f"RAW-PROVENANCE-{provenance}",
        detail="bad payload",
    )
    row = dict(ingestor._quality_pending[0])
    if provenance is None:
        row.pop("effective_timestamp_provenance")
    else:
        row["effective_timestamp_provenance"] = provenance
    ingestor.ledgers["refusals_data_quality"].append(row)
    ingestor._quality_pending = []
    ingestor._quality_pending_ids = set()
    ingestor._quality_pending_content = {}
    ingestor.close()

    with pytest.raises(
        ValueError, match="invalid effective_timestamp_provenance"
    ):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize(
    ("field", "value"),
    (("file", None), ("byte_offset", True), ("source_row", -1)),
)
def test_ingestion_refusal_startup_requires_source_coordinates(
    tmp_path, field, value,
):
    _data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    ingestor._quality(
        "MALFORMED_JSONL",
        "raw/2099-01-01/events_09.jsonl",
        1,
        0,
        f"RAW-COORDINATES-{field}",
        detail="bad payload",
    )
    row = dict(ingestor._quality_pending[0])
    if value is None:
        row["source_receipt_identifiers"].pop(field)
    else:
        row["source_receipt_identifiers"][field] = value
    ingestor.ledgers["refusals_data_quality"].append(row)
    ingestor._quality_pending = []
    ingestor._quality_pending_ids = set()
    ingestor._quality_pending_content = {}
    ingestor.close()

    with pytest.raises(ValueError, match=f"identifiers.{field}"):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("sqlite_key", "mismatched payload identity"),
        ("payload", "payload digest mismatch"),
    ),
)
def test_observation_outbox_startup_authenticates_key_and_payload(
    tmp_path, corruption, message,
):
    data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    observation = ingestor._normalize_record(
        data / "raw/2099-01-01/events_09.jsonl",
        json.loads(_market(
            receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100,
        )),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id="RAW-OUTBOX-AUTHORITY",
    )[0]
    row = observation.to_dict()
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode()).hexdigest()
    sqlite_key = (
        "OBS-MISMATCHED-SQLITE-KEY"
        if corruption == "sqlite_key" else observation.observation_id
    )
    ingestor.db.execute(
        "insert into observation_outbox(id,payload,content_sha256) "
        "values (?,?,?)",
        (sqlite_key, payload, digest),
    )
    if corruption == "payload":
        row["price"] = 1.0
        ingestor.db.execute(
            "update observation_outbox set payload=? where id=?",
            (
                json.dumps(row, sort_keys=True, separators=(",", ":")),
                sqlite_key,
            ),
        )
    ingestor.db.commit()
    ingestor.close()

    with pytest.raises(ValueError, match=message):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize(
    ("table", "schema", "values", "message"),
    (
        (
            "observation_outbox",
            "id text primary key,payload text not null",
            ("OBS-LEGACY", "{}"),
            "legacy observation_outbox.*clean rebuild required",
        ),
        (
            "futures_candidate_outbox",
            (
                "id text primary key,session_date text not null,"
                "receipt_timestamp text,payload text not null"
            ),
            ("OBS-LEGACY", "2099-01-01", None, "{}"),
            "legacy futures_candidate_outbox.*clean rebuild required",
        ),
    ),
)
def test_nonempty_legacy_outbox_requires_clean_rebuild(
    tmp_path, table, schema, values, message,
):
    _data, runtime = _direct_contract(tmp_path)
    runtime["state_root"].mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(runtime["state_root"] / "dedup.sqlite3")
    database.execute(f"create table {table}({schema})")
    placeholders = ",".join("?" for _value in values)
    database.execute(
        f"insert into {table} values ({placeholders})", values
    )
    database.commit()
    database.close()

    with pytest.raises(ValueError, match=message):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    (
        ("id", "OBS-MISMATCHED-CANDIDATE", "mismatched payload identity"),
        ("session_date", "2099-01-02", "mismatched session_date column"),
        (
            "receipt_timestamp",
            "2099-01-01T09:15:00+05:30",
            "mismatched receipt_timestamp column",
        ),
    ),
)
def test_futures_candidate_outbox_startup_authenticates_columns(
    tmp_path, column, value, message,
):
    data, runtime = _direct_contract(tmp_path)
    runtime["config"]["selected_futures_by_session"] = {}
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    candidate = ingestor._normalize_record(
        data / "raw/2099-01-01/events_09.jsonl",
        json.loads(_market(
            receipt, "NSE:BANKNIFTY26AUGFUT", 57_120, 100,
        )),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id="RAW-CANDIDATE-AUTHORITY",
    )[0]
    assert candidate.classification_reason == "FUTURES_SELECTION_PENDING"
    payload = json.dumps(
        candidate.to_dict(), sort_keys=True, separators=(",", ":")
    )
    values = {
        "id": candidate.observation_id,
        "session_date": candidate.session_date,
        "receipt_timestamp": candidate.receipt_timestamp,
    }
    values[column] = value
    ingestor.db.execute(
        "insert into futures_candidate_outbox("
        "id,session_date,receipt_timestamp,payload,content_sha256) "
        "values (?,?,?,?,?)",
        (
            values["id"], values["session_date"],
            values["receipt_timestamp"], payload,
            hashlib.sha256(payload.encode()).hexdigest(),
        ),
    )
    ingestor.db.commit()
    ingestor.close()

    with pytest.raises(ValueError, match=message):
        IncrementalJSONLIngestor(runtime)


@pytest.mark.parametrize("changed", ("price", "receipt"))
def test_normalized_same_id_changed_content_is_not_hidden_by_seen_set(
    tmp_path, changed,
):
    data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    canonical = ingestor._normalize_record(
        path,
        json.loads(_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100)),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id="RAW-CONTENT-AUTHORITY",
    )[0]
    _seed_checkpoint_authority(ingestor, data, path)
    malicious = canonical.to_dict()
    if changed == "price":
        malicious["price"] = 1.0
    elif changed == "receipt":
        malicious["receipt_timestamp"] = _timestamp(-2)
        malicious["effective_timestamp"] = malicious["receipt_timestamp"]
    ingestor.ledgers["normalized_raw_events"].append(malicious)
    ingestor.close()

    restarted = IncrementalJSONLIngestor(runtime)
    with pytest.raises(ValueError, match="different immutable content"):
        restarted._ledger_observations([canonical])
    assert restarted.ledgers["normalized_raw_events"].rows() == [malicious]
    restarted.close()


def test_normalized_startup_recomputes_and_refuses_tampered_order_flag(
    tmp_path,
):
    data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    canonical = ingestor._normalize_record(
        path,
        json.loads(_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100)),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id="RAW-ORDER-AUTHORITY",
    )[0]
    _seed_checkpoint_authority(ingestor, data, path)
    tampered = canonical.to_dict()
    tampered["out_of_order"] = True
    ingestor.ledgers["normalized_raw_events"].append(tampered)
    ingestor.close()

    with pytest.raises(ValueError, match="invalid derived out_of_order"):
        IncrementalJSONLIngestor(runtime)


def test_normalized_same_evidence_allows_new_transport_raw_run_id(tmp_path):
    data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    receipt = _timestamp(-1)
    path = data / "raw/2099-01-01/events_09.jsonl"
    canonical = ingestor._normalize_record(
        path,
        json.loads(_market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100)),
        rel="raw/2099-01-01/events_09.jsonl",
        row_number=1,
        byte_offset=0,
        raw_record_id="RAW-RUN-TRANSPORT",
    )[0]
    _seed_checkpoint_authority(ingestor, data, path)
    ingestor.ledgers["normalized_raw_events"].append(canonical.to_dict())
    ingestor.close()

    restarted = IncrementalJSONLIngestor(runtime)
    replay = TypedObservation(**{
        **canonical.to_dict(), "raw_run_id": "DIFFERENT-TRANSPORT-RUN",
    })
    restarted._ledger_observations([replay])
    assert restarted.ledgers["normalized_raw_events"].rows() == [
        canonical.to_dict()
    ]
    restarted.close()


def test_sqlite_checkpoint_candidate_authenticates_same_id_ledger_row(tmp_path):
    _data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    rel = "raw/2099-01-01/events_09.jsonl"
    checkpoint = {
        "offset": 128,
        "row": 2,
        "identity": "1:2",
        "size_at_commit": 128,
        "updated_at": _timestamp(-1),
        "prefix_fingerprint": "a" * 64,
        "mtime_ns_at_commit": 123,
    }
    expected = ingestor._checkpoint_ledger_row(rel, checkpoint)
    malicious = json.loads(json.dumps(expected))
    # Preserve the source/offset authority prerequisite so this specifically
    # exercises immutable-content authentication for an existing event ID.
    malicious["engine_hash"] = "DIFFERENT-ENGINE"
    ingestor.ledgers["raw_file_checkpoints"].append(malicious)
    with ingestor.db:
        ingestor.db.execute(
            "insert into file_checkpoint("
            "source_file,offset,row_number,identity,size_at_commit,updated_at,"
            "frontier,prefix_fingerprint,mtime_ns_at_commit) "
            "values (?,?,?,?,?,?,?,?,?)",
            (
                rel,
                checkpoint["offset"],
                checkpoint["row"],
                checkpoint["identity"],
                checkpoint["size_at_commit"],
                checkpoint["updated_at"],
                None,
                checkpoint["prefix_fingerprint"],
                checkpoint["mtime_ns_at_commit"],
            ),
        )
    ingestor.checkpoint_path.write_text(json.dumps({rel: checkpoint}))
    ingestor.close()

    with pytest.raises(ValueError, match="different immutable content"):
        IncrementalJSONLIngestor(runtime)


def test_refusal_same_id_changed_detail_is_not_hidden_by_seen_set(tmp_path):
    _data, runtime = _direct_contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    args = (
        "MALFORMED_JSONL", "raw/2099-01-01/events_09.jsonl", 1, 0,
        "RAW-ONE",
    )
    ingestor._quality(*args, detail="canonical detail")
    canonical = dict(ingestor._quality_pending[0])
    malicious = dict(canonical)
    malicious["detail"] = "altered detail"
    ingestor.ledgers["refusals_data_quality"].append(malicious)
    ingestor._quality_pending = []
    ingestor._quality_pending_ids = set()
    ingestor._quality_pending_content = {}
    ingestor.close()

    restarted = IncrementalJSONLIngestor(runtime)
    with pytest.raises(ValueError, match="different immutable content"):
        restarted._quality(*args, detail="canonical detail")
    restarted.close()


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


def test_shared_refusal_identity_index_covers_both_live_producers(tmp_path):
    _data, runtime = _contract(tmp_path)
    ingestor = IncrementalJSONLIngestor(runtime)
    orchestrator = LiveAnalyticalOrchestrator(runtime, ingestor.ledgers)
    state = ShadowState(ingestor, {}, orchestrator)
    cache = _AuditReadCache()

    orchestrator._quality(
        {
            "observation_id": "ANALYTICAL-REFUSAL",
            "session_date": "2099-01-01",
            "receipt_timestamp": "2099-01-01T09:15:00+05:30",
            "source_file": "raw/2099-01-01/events_09.jsonl",
            "source_row_number": 1,
        },
        "ORCHESTRATOR_OBSERVATION_REFUSED",
        "synthetic refusal",
    )
    first = cache.read(state, state.analytical_snapshot(), 10)
    assert first["refusal_count"] == 1
    assert first["duplicate_analytical_ids"] == 0

    ingestor._quality(
        "MALFORMED_RECORD",
        "raw/2099-01-01/events_09.jsonl",
        2,
        100,
        "RAW-REFUSAL",
        "synthetic refusal",
    )
    ingestor._flush_quality()
    second = cache.read(state, state.analytical_snapshot(), 10)
    assert second["refusal_count"] == 2
    assert second["duplicate_analytical_ids"] == 0
    assert orchestrator.trusted_quality_identity_count() == 2
    assert len(ingestor._quality_seen) == 2
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


def test_path_replacement_between_stat_and_open_never_publishes_replacement(
    tmp_path, monkeypatch,
):
    data, contract = _contract(tmp_path)
    receipt = _timestamp(-0.2)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(
        _market(receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    )
    replacement = path.with_suffix(".replacement")
    replacement.write_text(
        _market(receipt, CANONICAL_INDEX_SYMBOL, 57_999, 100) + "\n"
    )
    original_open = Path.open
    swapped = False

    def replacing_open(opened_path, *args, **kwargs):
        nonlocal swapped
        mode = args[0] if args else kwargs.get("mode", "r")
        if opened_path == path and mode == "rb" and not swapped:
            os.replace(replacement, path)
            swapped = True
        return original_open(opened_path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replacing_open)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[path]) == []
    assert swapped
    assert ingestor.ledgers["normalized_raw_events"].rows() == []
    assert ingestor.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 0
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(path.relative_to(data)),),
    ).fetchone() == ("FILE_REPLACED",)
    ingestor.close()


def test_same_inode_append_during_snapshot_commits_then_replays_remainder(
    tmp_path, monkeypatch,
):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    original = (
        _market(_timestamp(-0.2), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    ).encode()
    appended = (
        _market(_timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 200) + "\n"
    ).encode()
    path.write_bytes(original)
    real_hash_blocks = IncrementalJSONLIngestor._new_complete_prefix_blocks
    appended_once = False

    def append_while_hashing(self, source, rel, committed_offset, **kwargs):
        nonlocal appended_once
        if not appended_once:
            with source.open("ab") as writer:
                writer.write(appended)
                writer.flush()
                os.fsync(writer.fileno())
            appended_once = True
        return real_hash_blocks(
            self, source, rel, committed_offset, **kwargs,
        )

    monkeypatch.setattr(
        IncrementalJSONLIngestor,
        "_new_complete_prefix_blocks",
        append_while_hashing,
    )
    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    first = ingestor.poll(source_paths=[path])
    assert [row.price for row in first] == [57_100]
    rel = str(path.relative_to(data))
    assert ingestor.checkpoints[rel]["offset"] == len(original)
    assert ingestor.checkpoints[rel]["size_at_commit"] == len(original + appended)
    second = ingestor.poll(source_paths=[path])
    assert [row.price for row in second] == [57_101]
    assert ingestor.checkpoints[rel]["offset"] == len(original + appended)
    ingestor.close()


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


def test_middle_committed_block_rewrite_with_growth_is_refused(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    blank_block = b" " * (block_size - 1) + b"\n"
    initial_record = (
        _market(_timestamp(-0.3), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    ).encode()
    path.write_bytes(blank_block * 5 + initial_record)

    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    rel = str(path.relative_to(data))
    checkpoint = dict(ingestor.checkpoints[rel])
    assert ingestor.db.execute(
        "select count(*) from file_prefix_block where source_file=?", (rel,)
    ).fetchone()[0] == 6

    # This byte is outside the 4 KiB head/midpoint/tail fingerprint windows,
    # but inside the durable midpoint block selected on a changed-file poll.
    rewrite_offset = block_size * 2 + 8192
    with path.open("r+b") as handle:
        handle.seek(rewrite_offset)
        assert handle.read(1) == b" "
        handle.seek(rewrite_offset)
        handle.write(b"\t")
        handle.seek(0, os.SEEK_END)
        handle.write(
            (
                _market(
                    _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 200,
                )
                + "\n"
            ).encode()
        )
        handle.flush()
        os.fsync(handle.fileno())

    assert ingestor.poll(source_paths=[path]) == []
    assert ingestor.checkpoints[rel]["offset"] == checkpoint["offset"]
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?", (rel,)
    ).fetchone()[0] == "FILE_REPLACED_IN_PLACE"
    ingestor.close()


def test_committed_partial_block_rewrite_before_append_is_refused(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    committed_size = 50 * 1024
    initial_record = (
        _market(_timestamp(-0.3), CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    ).encode()
    padding_size = committed_size - len(initial_record)
    assert padding_size > 1
    path.write_bytes(initial_record + b" " * (padding_size - 1) + b"\n")

    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    rel = str(path.relative_to(data))
    checkpoint = dict(ingestor.checkpoints[rel])
    assert ingestor.db.execute(
        "select block_index,byte_count from file_prefix_block "
        "where source_file=?",
        (rel,),
    ).fetchall() == [(0, committed_size)]

    # Twelve KiB misses the bounded prefix fingerprint's head, midpoint and
    # tail windows.  The exact digest of the old 50 KiB partial block must be
    # verified before append bytes can extend and replace that digest.
    rewrite_offset = 12 * 1024
    with path.open("r+b") as handle:
        handle.seek(rewrite_offset)
        assert handle.read(1) == b" "
        handle.seek(rewrite_offset)
        handle.write(b"\t")
        handle.seek(0, os.SEEK_END)
        handle.write(
            (
                _market(
                    _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 200,
                )
                + "\n"
            ).encode()
        )
        handle.flush()
        os.fsync(handle.fileno())

    assert ingestor.poll(source_paths=[path]) == []
    assert ingestor.checkpoints[rel]["offset"] == checkpoint["offset"]
    assert len(ingestor.ledgers["normalized_raw_events"].rows()) == 1
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?", (rel,)
    ).fetchone()[0] == "FILE_REPLACED_IN_PLACE"
    ingestor.close()


def test_rotating_integrity_scrub_cursor_survives_restart(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    blank_block = b" " * (block_size - 1) + b"\n"
    path.write_bytes(
        blank_block * 6
        + (
            _market(_timestamp(-0.3), CANONICAL_INDEX_SYMBOL, 57_100, 100)
            + "\n"
        ).encode()
    )
    rel = str(path.relative_to(data))

    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    with path.open("ab") as handle:
        handle.write(
            (
                _market(
                    _timestamp(-0.2), CANONICAL_INDEX_SYMBOL, 57_101, 200,
                )
                + "\n"
            ).encode()
        )
    assert len(ingestor.poll(source_paths=[path])) == 1
    assert ingestor.db.execute(
        "select next_block from file_integrity_scrub where source_file=?", (rel,)
    ).fetchone()[0] == 1
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract, lambda _row: None)
    with path.open("ab") as handle:
        handle.write(
            (
                _market(
                    _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_102, 300,
                )
                + "\n"
            ).encode()
        )
    assert len(restarted.poll(source_paths=[path])) == 1
    assert restarted.db.execute(
        "select next_block from file_integrity_scrub where source_file=?", (rel,)
    ).fetchone()[0] == 2
    restarted.close()


def test_unsampled_old_block_rewrite_cannot_cross_session_seal(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    blank_block = b" " * (block_size - 1) + b"\n"
    path.write_bytes(
        blank_block * 10
        + (
            _market(_timestamp(-0.3), CANONICAL_INDEX_SYMBOL, 57_100, 100)
            + "\n"
        ).encode()
    )
    rel = str(path.relative_to(data))
    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    checkpoint = dict(ingestor.checkpoints[rel])

    # Block two is neither head, midpoint, tail nor the first rotating target.
    # The bounded append poll may safely stage bytes beyond the immutable old
    # checkpoint, but the exhaustive seal gate must refuse the altered prefix.
    rewrite_offset = block_size * 2 + 8192
    with path.open("r+b") as handle:
        handle.seek(rewrite_offset)
        assert handle.read(1) == b" "
        handle.seek(rewrite_offset)
        handle.write(b"\t")
        handle.seek(0, os.SEEK_END)
        handle.write(
            (
                _market(
                    _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 200,
                )
                + "\n"
            ).encode()
        )
        handle.flush()
        os.fsync(handle.fileno())

    assert len(ingestor.poll(source_paths=[path])) == 1
    assert ingestor.checkpoints[rel]["offset"] > checkpoint["offset"]
    with pytest.raises(
        ValueError, match="committed source integrity verification failed",
    ):
        ingestor.verify_committed_sources(["2099-01-01"])
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?", (rel,)
    ).fetchone() == ("FILE_REPLACED_IN_PLACE",)
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    with pytest.raises(
        ValueError, match="committed source integrity verification failed",
    ):
        restarted.verify_committed_sources(["2099-01-01"])
    assert rel in restarted._quarantined_sources
    assert len(restarted.ledgers["normalized_raw_events"].rows()) == 2
    restarted.close()


def test_unchanged_polls_continue_rotating_integrity_scrub(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    blank_block = b" " * (block_size - 1) + b"\n"
    path.write_bytes(
        blank_block * 6
        + (
            _market(_timestamp(-0.2), CANONICAL_INDEX_SYMBOL, 57_100, 100)
            + "\n"
        ).encode()
    )
    rel = str(path.relative_to(data))
    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    first = ingestor.db.execute(
        "select next_block from file_integrity_scrub where source_file=?", (rel,)
    ).fetchone()[0]
    assert ingestor.poll(source_paths=[path]) == []
    second = ingestor.db.execute(
        "select next_block from file_integrity_scrub where source_file=?", (rel,)
    ).fetchone()[0]
    assert second != first
    ingestor.close()


def test_missing_block_inventory_fails_closed_without_historical_rescan(tmp_path):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    blank_block = b" " * (block_size - 1) + b"\n"
    path.write_bytes(
        blank_block * 5
        + (
            _market(_timestamp(-0.3), CANONICAL_INDEX_SYMBOL, 57_100, 100)
            + "\n"
        ).encode()
    )
    rel = str(path.relative_to(data))
    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[path])) == 1
    prior_offset = ingestor.checkpoints[rel]["offset"]
    # Whether this models a legacy database or damaged current state, no exact
    # historical block authority exists.  A changed source must fail closed;
    # silently baselining its current tail would bless an unsampled rewrite.
    with ingestor.db:
        ingestor.db.execute(
            "delete from file_prefix_block where source_file=?", (rel,)
        )
        ingestor.db.execute(
            "delete from file_integrity_scrub where source_file=?", (rel,)
        )
    ingestor.close()

    with path.open("ab") as handle:
        handle.write(
            (
                _market(
                    _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_101, 200,
                )
                + "\n"
            ).encode()
        )
    migrated = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert migrated.poll(source_paths=[path]) == []
    assert migrated.checkpoints[rel]["offset"] == prior_offset
    blocks = migrated.db.execute(
        "select block_index from file_prefix_block where source_file=? "
        "order by block_index",
        (rel,),
    ).fetchall()
    assert blocks == []
    assert migrated.db.execute(
        "select reason from quarantined_source where source_file=?", (rel,)
    ).fetchone() == ("FILE_REPLACED_IN_PLACE",)
    migrated.close()


def test_quarantined_committed_source_does_not_watermark_block_valid_rotated_file(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    first_receipt = _timestamp(-0.3)
    later_receipt = _timestamp(-0.1)
    damaged = data / "raw/2099-01-01/events_09.jsonl"
    original = (
        _market(first_receipt, CANONICAL_INDEX_SYMBOL, 57_100, 100) + "\n"
    ).encode()
    replacement = (
        _market(first_receipt, CANONICAL_INDEX_SYMBOL, 57_101, 100) + "\n"
    ).encode()
    assert len(original) == len(replacement)
    damaged.write_bytes(original)
    ingestor = IncrementalJSONLIngestor(contract, lambda _row: None)
    assert len(ingestor.poll(source_paths=[damaged])) == 1
    checkpoint = dict(ingestor.checkpoints[str(damaged.relative_to(data))])
    with damaged.open("r+b") as handle:
        handle.write(replacement)
        handle.flush()
        os.fsync(handle.fileno())
    if damaged.stat().st_mtime_ns == checkpoint["mtime_ns_at_commit"]:
        os.utime(
            damaged,
            ns=(damaged.stat().st_atime_ns, checkpoint["mtime_ns_at_commit"] + 1),
        )
    rotated = data / "raw/2099-01-01/events_10.jsonl"
    rotated.write_text(
        _market(later_receipt, CANONICAL_INDEX_SYMBOL, 57_102, 200) + "\n"
    )

    rows = ingestor.poll(source_paths=[damaged, rotated])
    assert [row.price for row in rows] == [57_102]
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(damaged.relative_to(data)),),
    ).fetchone()[0] == "FILE_REPLACED_IN_PLACE"
    assert [
        row["reason"] for row in ingestor.ledgers["refusals_data_quality"].rows()
        if row["reason"] == "FILE_REPLACED_IN_PLACE"
    ] == ["FILE_REPLACED_IN_PLACE"]
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[damaged, rotated]) == []
    assert str(damaged.relative_to(data)) in restarted._quarantined_sources
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


@pytest.mark.parametrize("durable_prefix", (0, 1, 3))
@pytest.mark.parametrize("restart", (False, True))
def test_normalized_ambiguous_batch_append_reconciles_physical_prefix_once(
    tmp_path, monkeypatch, durable_prefix, restart,
):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    base = datetime.now(IST) - timedelta(seconds=1)
    path.write_text("".join(
        _market(
            (base + timedelta(milliseconds=ordinal)).isoformat(
                timespec="microseconds"
            ),
            CANONICAL_INDEX_SYMBOL,
            57_100 + ordinal,
            ordinal,
        ) + "\n"
        for ordinal in range(3)
    ))
    received = []
    ingestor = IncrementalJSONLIngestor(contract, received.append)
    ledger = ingestor.ledgers["normalized_raw_events"]
    original = ledger.append_many
    attempts = []

    def durable_prefix_then_fail(rows):
        batch = list(rows)
        attempts.append(batch)
        if durable_prefix:
            original(batch[:durable_prefix])
        raise RuntimeError("synthetic normalized ambiguous append")

    monkeypatch.setattr(ledger, "append_many", durable_prefix_then_fail)
    with pytest.raises(RuntimeError, match="normalized ambiguous append"):
        ingestor.poll(source_paths=[path])
    expected_ids = [row["event_id"] for row in attempts[0]]
    assert received == []
    assert ingestor.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 3
    assert [
        row["event_id"] for row in ledger.rows()
    ] == expected_ids[:durable_prefix]
    assert set(expected_ids[:durable_prefix]) <= ingestor._normalized_seen
    assert set(expected_ids[:durable_prefix]) <= set(
        ingestor._normalized_out_of_order
    )

    if restart:
        ingestor.db.close()  # Abrupt process death; never clean-ACK the outbox.
        recovered = IncrementalJSONLIngestor(contract, received.append)
    else:
        monkeypatch.setattr(ledger, "append_many", original)
        recovered = ingestor
    replay = recovered.poll(source_paths=[path])
    assert [row.observation_id for row in replay] == expected_ids
    assert [row.observation_id for row in received] == expected_ids
    physical_ids = [
        row["event_id"]
        for row in recovered.ledgers["normalized_raw_events"].rows()
    ]
    assert physical_ids == expected_ids
    assert len(physical_ids) == len(set(physical_ids)) == 3
    assert recovered.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 0
    recovered.close()

    final = IncrementalJSONLIngestor(contract, received.append)
    assert final.poll(source_paths=[path]) == []
    assert [
        row["event_id"]
        for row in final.ledgers["normalized_raw_events"].rows()
    ] == expected_ids
    assert [row.observation_id for row in received] == expected_ids
    final.close()


@pytest.mark.parametrize("durable_prefix", (0, 1, 2))
@pytest.mark.parametrize("restart", (False, True))
def test_refusal_ambiguous_batch_append_retains_only_unwritten_rows(
    tmp_path, monkeypatch, durable_prefix, restart,
):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_bytes(b'{"received_at":\n[]\n')
    ingestor = IncrementalJSONLIngestor(contract)
    ledger = ingestor.ledgers["refusals_data_quality"]
    original = ledger.append_many
    attempts = []

    def durable_prefix_then_fail(rows):
        batch = list(rows)
        attempts.append(batch)
        assert len(batch) == 2
        if durable_prefix:
            original(batch[:durable_prefix])
        raise RuntimeError("synthetic refusal ambiguous append")

    monkeypatch.setattr(ledger, "append_many", durable_prefix_then_fail)
    with pytest.raises(RuntimeError, match="refusal ambiguous append"):
        ingestor.poll(source_paths=[path])
    expected_ids = [row["event_id"] for row in attempts[0]]
    assert [row["event_id"] for row in ledger.rows()] == expected_ids[:durable_prefix]
    assert [
        row["event_id"] for row in ingestor._quality_pending
    ] == expected_ids[durable_prefix:]
    assert ingestor._quality_pending_ids == set(expected_ids[durable_prefix:])
    assert set(expected_ids[:durable_prefix]) <= ingestor._quality_seen
    assert str(path.relative_to(data)) not in ingestor.checkpoints

    if restart:
        ingestor.db.close()  # Lose only the non-durable in-memory refusal tail.
        recovered = IncrementalJSONLIngestor(contract)
    else:
        monkeypatch.setattr(ledger, "append_many", original)
        recovered = ingestor
    assert recovered.poll(source_paths=[path]) == []
    physical = recovered.ledgers["refusals_data_quality"].rows()
    physical_ids = [row["event_id"] for row in physical]
    assert physical_ids == expected_ids
    assert len(physical_ids) == len(set(physical_ids)) == 2
    assert [row["reason"] for row in physical] == [
        "MALFORMED_JSONL", "INVALID_JSONL_RECORD",
    ]
    assert recovered._quality_pending == []
    assert recovered._quality_pending_ids == set()
    assert recovered.checkpoints[str(path.relative_to(data))]["offset"] == (
        path.stat().st_size
    )
    recovered.close()

    final = IncrementalJSONLIngestor(contract)
    assert final.poll(source_paths=[path]) == []
    assert [
        row["event_id"]
        for row in final.ledgers["refusals_data_quality"].rows()
    ] == expected_ids
    final.close()


@pytest.mark.parametrize("durable_prefix", (0, 1, 2))
@pytest.mark.parametrize("restart", (False, True))
def test_checkpoint_ambiguous_batch_append_replays_without_physical_duplicate(
    tmp_path, monkeypatch, durable_prefix, restart,
):
    data, contract = _contract(tmp_path)
    base = datetime.now(IST) - timedelta(seconds=1)
    paths = [
        data / "raw/2099-01-01/events_09.jsonl",
        data / "raw/2099-01-01/events_10.jsonl",
    ]
    for ordinal, path in enumerate(paths):
        path.write_text(
            _market(
                (base + timedelta(milliseconds=ordinal)).isoformat(
                    timespec="microseconds"
                ),
                CANONICAL_INDEX_SYMBOL,
                57_100 + ordinal,
                ordinal,
            ) + "\n"
        )
    received = []
    ingestor = IncrementalJSONLIngestor(contract, received.append)
    ledger = ingestor.ledgers["raw_file_checkpoints"]
    original = ledger.append_many
    attempts = []

    def durable_prefix_then_fail(rows):
        batch = list(rows)
        attempts.append(batch)
        assert len(batch) == 2
        if durable_prefix:
            original(batch[:durable_prefix])
        raise RuntimeError("synthetic checkpoint ambiguous append")

    monkeypatch.setattr(ledger, "append_many", durable_prefix_then_fail)
    with pytest.raises(RuntimeError, match="checkpoint ambiguous append"):
        ingestor.poll(source_paths=paths)
    expected_checkpoint_ids = [row["event_id"] for row in attempts[0]]
    assert received == []
    assert [
        row["event_id"] for row in ledger.rows()
    ] == expected_checkpoint_ids[:durable_prefix]
    assert [
        row["event_id"] for row in ingestor._checkpoint_pending
    ] == expected_checkpoint_ids[durable_prefix:]
    assert set(expected_checkpoint_ids[:durable_prefix]) <= ingestor._checkpoint_seen
    assert ingestor.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 2

    if restart:
        ingestor.db.close()
        recovered = IncrementalJSONLIngestor(contract, received.append)
    else:
        monkeypatch.setattr(ledger, "append_many", original)
        recovered = ingestor
    replay = recovered.poll(source_paths=paths)
    assert len(replay) == 2
    assert len(received) == 2
    physical_ids = [
        row["event_id"]
        for row in recovered.ledgers["raw_file_checkpoints"].rows()
    ]
    assert physical_ids == expected_checkpoint_ids
    assert len(physical_ids) == len(set(physical_ids)) == 2
    assert recovered.db.execute(
        "select count(*) from observation_outbox"
    ).fetchone()[0] == 0
    recovered.close()

    final = IncrementalJSONLIngestor(contract, received.append)
    assert final.poll(source_paths=paths) == []
    assert [
        row["event_id"]
        for row in final.ledgers["raw_file_checkpoints"].rows()
    ] == expected_checkpoint_ids
    assert len(received) == 2
    final.close()


def test_fully_durable_checkpoint_append_repairs_json_mirror_on_restart(
    tmp_path, monkeypatch,
):
    data, contract = _contract(tmp_path)
    path = data / "raw/2099-01-01/events_09.jsonl"
    path.write_text(
        _market(
            _timestamp(-0.1), CANONICAL_INDEX_SYMBOL, 57_100, 100,
        ) + "\n"
    )
    received = []
    failed = IncrementalJSONLIngestor(contract, received.append)
    ledger = failed.ledgers["raw_file_checkpoints"]
    original = ledger.append_many

    def durable_append_then_fail(rows):
        batch = list(rows)
        original(batch)
        raise RuntimeError("synthetic fully durable checkpoint append")

    monkeypatch.setattr(ledger, "append_many", durable_append_then_fail)
    with pytest.raises(RuntimeError, match="fully durable checkpoint append"):
        failed.poll(source_paths=[path])
    physical = ledger.rows()
    assert len(physical) == 1
    assert not failed.checkpoint_path.exists()
    sqlite_checkpoint = dict(failed.checkpoints)
    failed.db.close()  # Abrupt restart before the JSON mirror replacement.

    recovered = IncrementalJSONLIngestor(contract, received.append)
    assert recovered._checkpoint_pending == []
    assert json.loads(recovered.checkpoint_path.read_text()) == sqlite_checkpoint
    assert recovered.checkpoints == sqlite_checkpoint
    assert recovered.ledgers["raw_file_checkpoints"].rows() == physical
    assert len(recovered.poll(source_paths=[path])) == 1
    assert len(received) == 1
    assert recovered.ledgers["raw_file_checkpoints"].rows() == physical
    recovered.close()

    final = IncrementalJSONLIngestor(contract, received.append)
    assert final.poll(source_paths=[path]) == []
    assert final.ledgers["raw_file_checkpoints"].rows() == physical
    final.close()


@pytest.mark.parametrize(
    "ledger_name",
    ("normalized_raw_events", "refusals_data_quality", "raw_file_checkpoints"),
)
@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ('{"status":"MISSING"}\n', "has no event_id"),
        ('{"event_id":"PARTIAL"}', "partial line"),
        ('{"event_id":\n', "corrupt line"),
    ),
)
def test_ingestion_startup_rejects_corrupt_or_nonunique_ledger_identity(
    tmp_path, ledger_name, payload, message,
):
    _, contract = _contract(tmp_path)
    path = contract["state_root"] / "ledgers" / f"{ledger_name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    with pytest.raises(ValueError, match=message):
        IncrementalJSONLIngestor(contract)


@pytest.mark.parametrize(
    "ledger_name",
    ("normalized_raw_events", "refusals_data_quality", "raw_file_checkpoints"),
)
def test_ingestion_startup_rejects_duplicate_schema_valid_ledger_identity(
    tmp_path, ledger_name,
):
    data, contract = _contract(tmp_path)
    source = data / "raw/2099-01-01/events_09.jsonl"
    if ledger_name == "refusals_data_quality":
        source.write_text('{"malformed":\n')
    else:
        source.write_text(
            _market(
                _timestamp(), CANONICAL_INDEX_SYMBOL, 57_100, 100,
            )
            + "\n"
        )
    ingestor = IncrementalJSONLIngestor(contract)
    ingestor.poll(source_paths=[source])
    row = ingestor.ledgers[ledger_name].rows()[0]
    ingestor.close()

    path = contract["state_root"] / "ledgers" / f"{ledger_name}.jsonl"
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(encoded + encoded)

    with pytest.raises(ValueError, match="duplicate .* ledger event_id"):
        IncrementalJSONLIngestor(contract)


def test_bounded_tail_reconciliation_refuses_partial_or_mismatched_bytes(tmp_path):
    partial = AppendOnlyLedger(tmp_path / "partial.jsonl")
    partial.append({"event_id": "BASE"})
    partial_boundary = partial.append_boundary()
    with partial.path.open("ab") as handle:
        handle.write(b'{"event_id":"EXPECTED"')
        handle.flush()
        os.fsync(handle.fileno())
    with pytest.raises(ValueError, match="partial or mismatched appended line"):
        partial.reconcile_appended_prefix(
            partial_boundary,
            [{"event_id": "EXPECTED"}],
            identity_field="event_id",
        )
    assert partial._append_quarantine_path.is_file()
    with pytest.raises(ValueError, match="is quarantined"):
        AppendOnlyLedger(partial.path).rows()

    mismatched = AppendOnlyLedger(tmp_path / "mismatched.jsonl")
    mismatched.append({"event_id": "BASE"})
    mismatched_boundary = mismatched.append_boundary()
    mismatched.append({"event_id": "UNEXPECT"})
    with pytest.raises(ValueError, match="differs from attempted rows"):
        mismatched.reconcile_appended_prefix(
            mismatched_boundary,
            [{"event_id": "EXPECTED"}],
            identity_field="event_id",
        )
    assert mismatched._append_quarantine_path.is_file()
    with pytest.raises(ValueError, match="is quarantined"):
        AppendOnlyLedger(mismatched.path).rows()


def test_persisted_ledger_intent_recovers_exact_tail_and_quarantines_extra_tail(
    tmp_path, monkeypatch,
):
    recover_path = tmp_path / "recover.jsonl"
    recover = AppendOnlyLedger(recover_path)
    original_clear = recover._clear_persisted_append_intent_locked

    def fail_after_durable_append():
        raise OSError("synthetic intent-clear interruption")

    monkeypatch.setattr(
        recover, "_clear_persisted_append_intent_locked",
        fail_after_durable_append,
    )
    with pytest.raises(OSError, match="intent-clear interruption"):
        recover.append({"event_id": "EXPECTED"})
    assert recover._append_intent_path.is_file()

    restarted = AppendOnlyLedger(recover_path)
    assert restarted.rows() == [{"event_id": "EXPECTED"}]
    assert not restarted._append_intent_path.exists()
    assert not restarted._append_quarantine_path.exists()

    quarantine_path = tmp_path / "quarantine.jsonl"
    quarantine = AppendOnlyLedger(quarantine_path)
    quarantine.append({"event_id": "BASE"})
    boundary = quarantine.append_boundary()
    rows, encoded = quarantine._prepare_rows(
        [{"event_id": "DECLARED"}], context="test intent"
    )
    with quarantine._lock:
        quarantine._write_persisted_append_intent_locked(
            boundary, rows, encoded
        )
    unrelated = (
        json.dumps(
            {"event_id": "UNRELATED"},
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"
    ).encode()
    with quarantine.path.open("ab") as handle:
        handle.write(encoded[0] + unrelated)
        handle.flush()
        os.fsync(handle.fileno())

    with pytest.raises(ValueError, match="recovery is quarantined"):
        AppendOnlyLedger(quarantine_path).rows()
    assert quarantine._append_quarantine_path.is_file()
    with pytest.raises(ValueError, match="is quarantined"):
        AppendOnlyLedger(quarantine_path).rows()


def test_direct_retry_cannot_duplicate_a_recovered_committed_intent(
    tmp_path, monkeypatch,
):
    path = tmp_path / "retry.jsonl"
    first = AppendOnlyLedger(path)

    def fail_after_durable_append():
        raise OSError("synthetic intent-clear interruption")

    monkeypatch.setattr(
        first, "_clear_persisted_append_intent_locked",
        fail_after_durable_append,
    )
    with pytest.raises(OSError, match="intent-clear interruption"):
        first.append({"event_id": "ONLY-ONCE"})

    restarted = AppendOnlyLedger(path)
    with pytest.raises(ValueError, match="caller reconciliation is required"):
        restarted.append({"event_id": "ONLY-ONCE"})
    assert path.read_text().count("ONLY-ONCE") == 1
    assert restarted._append_intent_path.is_file()

    # Startup identity priming explicitly consumes the recovered append.
    assert restarted.rows() == [{"event_id": "ONLY-ONCE"}]
    assert not restarted._append_intent_path.exists()


def test_retained_append_requires_exact_caller_ack_before_next_append(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "retained.jsonl")
    receipt = ledger.append_many_retained([{"event_id": "FIRST"}])
    assert receipt is not None
    assert receipt.declared_identities == ("FIRST",)
    assert receipt.committed_identities == ("FIRST",)
    assert ledger._append_intent_path.is_file()

    with pytest.raises(ValueError, match="ACK identities differ"):
        ledger.acknowledge_retained_append(
            receipt, accepted_identities=(),
        )
    with pytest.raises(ValueError, match="caller reconciliation is required"):
        ledger.append({"event_id": "SECOND"})
    assert ledger.path.read_text().count("FIRST") == 1

    ledger.acknowledge_retained_append(
        receipt, accepted_identities=("FIRST",),
    )
    assert not ledger._append_intent_path.exists()
    ledger.append({"event_id": "SECOND"})
    assert [row["event_id"] for row in ledger.rows()] == ["FIRST", "SECOND"]


def test_retained_append_ack_failure_is_restart_visible_and_idempotent(
    tmp_path, monkeypatch,
):
    path = tmp_path / "retained-restart.jsonl"
    ledger = AppendOnlyLedger(path)
    receipt = ledger.append_many_retained([{"event_id": "ONLY"}])
    assert receipt is not None

    def fail_before_ack_clear():
        raise OSError("synthetic retained ACK interruption")

    monkeypatch.setattr(
        ledger, "_clear_persisted_append_intent_locked",
        fail_before_ack_clear,
    )
    with pytest.raises(OSError, match="retained ACK interruption"):
        ledger.acknowledge_retained_append(
            receipt, accepted_identities=("ONLY",),
        )
    assert ledger._append_intent_path.is_file()

    restarted = AppendOnlyLedger(path)
    rows, recovered = restarted.rows_with_retained_append()
    assert rows == [{"event_id": "ONLY"}]
    assert recovered is not None
    assert recovered.committed_identities == ("ONLY",)
    restarted.acknowledge_retained_append(
        recovered, accepted_identities=("ONLY",),
    )
    assert not restarted._append_intent_path.exists()
    restarted.append({"event_id": "NEXT"})
    assert [row["event_id"] for row in restarted.rows()] == ["ONLY", "NEXT"]


def test_retained_reconciliation_accepts_only_complete_prefix_then_retries(
    tmp_path,
):
    ledger = AppendOnlyLedger(tmp_path / "retained-prefix.jsonl")
    boundary = ledger.append_boundary()
    values, encoded = ledger._prepare_rows(
        [{"event_id": "FIRST"}, {"event_id": "SECOND"}],
        context="retained prefix test",
    )
    with ledger._lock:
        ledger._write_persisted_append_intent_locked(
            boundary, values, encoded,
        )
    with ledger.path.open("ab") as handle:
        handle.write(encoded[0])
        handle.flush()
        os.fsync(handle.fileno())

    receipt = ledger.reconcile_retained_append(
        boundary, values, identity_field="event_id",
    )
    assert receipt.declared_identities == ("FIRST", "SECOND")
    assert receipt.committed_identities == ("FIRST",)
    assert ledger._append_intent_path.is_file()
    ledger.acknowledge_retained_append(
        receipt, accepted_identities=("FIRST",),
    )
    ledger.append({"event_id": "SECOND"})
    assert [row["event_id"] for row in ledger.rows()] == ["FIRST", "SECOND"]


def test_stale_retained_receipt_cannot_ack_a_later_transaction(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "stale-receipt.jsonl")
    first = ledger.append_many_retained([{"event_id": "FIRST"}])
    assert first is not None
    ledger.acknowledge_retained_append(
        first, accepted_identities=("FIRST",),
    )
    second = ledger.append_many_retained([{"event_id": "SECOND"}])
    assert second is not None

    with pytest.raises(ValueError, match="stale or mismatched"):
        ledger.acknowledge_retained_append(
            first, accepted_identities=("FIRST",),
        )
    assert ledger._append_intent_path.is_file()
    ledger.acknowledge_retained_append(
        second, accepted_identities=("SECOND",),
    )
    assert [row["event_id"] for row in ledger.rows()] == ["FIRST", "SECOND"]


def test_reconciliation_intent_survives_quarantine_marker_failure_and_restart(
    tmp_path, monkeypatch,
):
    ledger = AppendOnlyLedger(tmp_path / "boundary-gap.jsonl")
    ledger.append({"event_id": "BASE"})
    boundary = ledger.append_boundary()
    ledger.append({"event_id": "UNRELATED"})

    original_atomic_json = ledger_module.atomic_json

    def fail_only_quarantine(path, value):
        if path.name.endswith(".append_quarantine.json"):
            raise OSError("synthetic quarantine marker failure")
        return original_atomic_json(path, value)

    monkeypatch.setattr(ledger_module, "atomic_json", fail_only_quarantine)
    with pytest.raises(ValueError, match="unexpected concurrent tail"):
        ledger.reconcile_appended_prefix(
            boundary,
            [{"event_id": "EXPECTED"}],
            identity_field="event_id",
        )
    assert ledger._append_intent_path.is_file()
    assert not ledger._append_quarantine_path.exists()

    monkeypatch.setattr(ledger_module, "atomic_json", original_atomic_json)
    with pytest.raises(ValueError, match="recovery is quarantined"):
        AppendOnlyLedger(ledger.path).rows()
    assert ledger._append_quarantine_path.is_file()


def test_incremental_ledger_scan_streams_only_new_complete_rows(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "audit.jsonl")
    ledger.append_many([{"event_id": "A"}, {"event_id": "B"}])
    first = []
    boundary = ledger.scan_from(None, first.append)
    assert first == [{"event_id": "A"}, {"event_id": "B"}]

    unchanged = []
    assert ledger.scan_from(boundary, unchanged.append) == boundary
    assert unchanged == []

    ledger.append({"event_id": "C"})
    appended = []
    advanced = ledger.scan_from(boundary, appended.append)
    assert appended == [{"event_id": "C"}]
    assert advanced.size > boundary.size

    with ledger.path.open("ab") as handle:
        handle.write(b'{"event_id":"PARTIAL"')
        handle.flush()
        os.fsync(handle.fileno())
    with pytest.raises(ValueError, match="partial line"):
        ledger.scan_from(advanced, lambda _row: None)


def test_incremental_ledger_scan_rejects_same_size_prefix_rewrite(tmp_path):
    ledger = AppendOnlyLedger(tmp_path / "audit.jsonl")
    ledger.append({"event_id": "ORIGINAL"})
    boundary = ledger.scan_from(None, lambda _row: None)
    original = ledger.path.read_bytes()
    modified = original.replace(b"ORIGINAL", b"MUTATED!", 1)
    assert len(modified) == len(original)
    with ledger.path.open("r+b") as handle:
        handle.write(modified)
        handle.flush()
        os.fsync(handle.fileno())
    with pytest.raises(ValueError, match="prefix changed"):
        ledger.scan_from(boundary, lambda _row: None)


def test_production_ledger_audit_is_bounded_and_rejects_external_mutation(
    tmp_path,
):
    ledger = AppendOnlyLedger(tmp_path / "audit.jsonl")
    rows = [
        {
            "event_id": f"QUALITY-{ordinal:04d}",
            "effective_timestamp": "2026-08-20T09:15:00+05:30",
            "publication_timestamp": "2026-08-20T09:15:01+05:30",
            "reason": "ORIGINAL",
        }
        for ordinal in range(520)
    ]
    ledger.append_many(rows)
    audit = ledger.audit_snapshot()
    assert audit["row_count"] == 520
    assert audit["duplicate_ids"] == 0
    assert audit["timestamp_backdating"] == 0
    assert len(audit["tail"]) == 500
    assert audit["tail"][0]["event_id"] == "QUALITY-0020"
    assert not hasattr(ledger._audit, "seen_ids")

    original = ledger.path.read_bytes()
    modified = original.replace(b"ORIGINAL", b"MUTATED!", 1)
    assert len(modified) == len(original)
    with ledger.path.open("r+b") as handle:
        handle.write(modified)
        handle.flush()
        os.fsync(handle.fileno())
    with pytest.raises(ValueError, match="changed after trusted access"):
        ledger.audit_snapshot()
    with pytest.raises(ValueError, match="changed after trusted access"):
        ledger.rows()


def test_ledger_refuses_blank_lines_and_invalid_present_audit_clocks(tmp_path):
    blank = AppendOnlyLedger(tmp_path / "blank.jsonl")
    blank.path.write_bytes(b'{"event_id":"A"}\n\n')
    with pytest.raises(ValueError, match="blank line"):
        blank.rows()

    invalid = AppendOnlyLedger(tmp_path / "invalid-clock.jsonl")
    with pytest.raises(ValueError, match="publication timestamp"):
        invalid.append({
            "event_id": "BAD-CLOCK",
            "publication_timestamp": "2026-08-20T09:15:01",
        })
    assert not invalid.path.exists()


def test_ledger_append_refuses_external_tail_before_audit_advancement(
    tmp_path, monkeypatch,
):
    ledger = AppendOnlyLedger(tmp_path / "concurrent.jsonl")
    boundary = ledger.append_boundary()
    original_fsync = os.fsync
    injected = False

    def fsync_then_external_append(descriptor):
        nonlocal injected
        original_fsync(descriptor)
        try:
            synchronized = Path(
                os.readlink(f"/proc/self/fd/{descriptor}")
            ).resolve()
        except OSError:
            return
        if injected or synchronized != ledger.path.resolve():
            return
        injected = True
        with ledger.path.open("ab") as external:
            external.write(b'{"event_id":"EXTERNAL"}\n')
            external.flush()
            original_fsync(external.fileno())

    monkeypatch.setattr(os, "fsync", fsync_then_external_append)
    attempted = {"event_id": "OWN"}
    with pytest.raises(ValueError, match="unexpected concurrent tail"):
        ledger.append(attempted)
    monkeypatch.setattr(os, "fsync", original_fsync)

    assert ledger._append_intent_path.is_file()
    with pytest.raises(ValueError, match="recovery is quarantined"):
        AppendOnlyLedger(ledger.path).rows()
    assert ledger._append_quarantine_path.is_file()
    with pytest.raises(ValueError, match="is quarantined"):
        ledger.reconcile_appended_prefix(
            boundary, [attempted], identity_field="event_id"
        )
    with pytest.raises(ValueError, match="is quarantined"):
        ledger.audit_snapshot()


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
    tied_index_receipt = raw_receipt
    index_receipt = f"{session}T09:15:00.500000+05:30"
    option_receipt = f"{session}T09:15:00.750000+05:30"
    oi_receipt = f"{session}T09:15:01.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(raw_receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100)
        + "\n"
        + _market(tied_index_receipt, CANONICAL_INDEX_SYMBOL, 58_099.0, 0)
        + "\n"
        + _market(index_receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 0)
        + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    # The later Index is durably staged, but the unresolved earlier Futures
    # receipt is a causal publication barrier until canonical depth evidence
    # selects the session contract.
    assert ingestor.poll() == []
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 1
    assert ingestor.db.execute("select count(*) from observation_outbox").fetchone()[0] == 2
    assert ingestor.checkpoints[str(raw_path.relative_to(data))]["offset"] == raw_path.stat().st_size
    ingestor.close()

    # Restart and repeated polling neither loses nor duplicates the unresolved
    # candidate or the Index held behind it.
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll() == []
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 1
    assert ingestor.db.execute("select count(*) from observation_outbox").fetchone()[0] == 2

    # The first growing-OI record can be an option-chain response. It remains
    # causally staged behind the unresolved raw Futures candidate and must not
    # prevent the next record in this same file from supplying selection
    # authority after another restart.
    option = {
        "source": "option_chain",
        "request_time": option_receipt,
        "received_at": option_receipt,
        "requested_symbol": CANONICAL_INDEX_SYMBOL,
        "response": {"data": {"optionsChain": [{
            "symbol": "NSE:BANKNIFTY26SEP58100CE",
            "ltp": 101.0,
            "oi": 500_000,
            "pdoi": 499_000,
            "strike_price": 58_100,
            "option_type": "CE",
            "expiry": "2026-09-29",
        }]}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(option) + "\n")
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.db.execute("select count(*) from observation_outbox").fetchone()[0] == 2
    assert str(oi_path.relative_to(data)) not in ingestor.checkpoints
    assert ingestor.db.execute(
        "select probe_offset from futures_selection_probe where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone()[0] == oi_path.stat().st_size
    ingestor.close()

    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[oi_path]) == []

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
    with oi_path.open("a") as handle:
        handle.write(json.dumps(depth) + "\n")
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.db.execute(
        "select replay_target from futures_selection_probe where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone()[0] == oi_path.stat().st_size
    # Only after primary ingestion has replayed every probed record may the
    # raw candidate and its held peers cross the callback boundary.
    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == [
        "INDEX", "FUTURES", "INDEX", "CE", "FUTURES_OI",
    ]
    assert rows[1].price == 58_130.2
    assert [row.receipt_timestamp for row in rows] == [
        tied_index_receipt, raw_receipt, index_receipt, option_receipt, oi_receipt,
    ]
    assert ingestor.metrics["candidate_selection_lookahead_reads"] == 1
    assert all(not row.out_of_order for row in rows)
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 0
    assert not any(
        row["reason"] == "FUTURES_SELECTION_PENDING"
        for row in ingestor.unknown_symbol_audit()
    )
    assert not any(
        row["reason"] in {"OUT_OF_ORDER_RECEIPT", "OUT_OF_ORDER_ANALYTICAL_RECEIPT"}
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    assert ingestor.poll() == []
    normalized = ingestor.ledgers["normalized_raw_events"].rows()
    assert len({row["event_id"] for row in normalized}) == 5
    ingestor.close()


def test_selected_candidate_waits_for_equal_clock_raw_chunk_and_callback_order(tmp_path):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    candidate_line = _market(
        receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100,
    ) + (" " * 1024) + "\n"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        candidate_line
        + _market(receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200)
        + "\n"
    )
    contract["config"]["max_read_bytes_per_file_per_poll"] = len(
        candidate_line.encode()
    )
    ingestor = IncrementalJSONLIngestor(contract)
    orchestrator = LiveAnalyticalOrchestrator(contract, ledgers=ingestor.ledgers)
    ingestor.register_callback(orchestrator)

    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.checkpoints[str(raw_path.relative_to(data))]["row"] == 1
    depth = {
        "source": "future_depth", "request_time": receipt,
        "received_at": receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(depth) + "\n")
    assert ingestor.poll(source_paths=[oi_path]) == []  # selection-only probe
    ingestor.close()

    # Selection authority and replay targets survive a restart before primary
    # OI ingestion and before any candidate callback acknowledgement.
    ingestor = IncrementalJSONLIngestor(contract)
    orchestrator = LiveAnalyticalOrchestrator(contract, ledgers=ingestor.ledgers)
    ingestor.register_callback(orchestrator)
    assert ingestor.poll(source_paths=[oi_path]) == []  # primary OI replay
    rows = ingestor.poll(source_paths=[raw_path])
    assert [row.instrument_class for row in rows] == [
        "INDEX", "FUTURES", "FUTURES_OI",
    ]
    assert all(row.receipt_timestamp == receipt for row in rows)
    assert not any(
        row["reason"] in {"OUT_OF_ORDER_RECEIPT", "OUT_OF_ORDER_ANALYTICAL_RECEIPT"}
        for row in ingestor.ledgers["refusals_data_quality"].rows()
    )
    ingestor.close()


def test_selection_probe_budget_is_durable_bounded_and_restores_market_liveness(tmp_path):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    candidate_receipt = f"{session}T09:15:00.100000+05:30"
    option_receipt = f"{session}T09:15:00.150000+05:30"
    index_receipt = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(candidate_receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100)
        + "\n" + _market(index_receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    )
    option = {
        "source": "option_chain", "request_time": option_receipt,
        "received_at": option_receipt, "requested_symbol": CANONICAL_INDEX_SYMBOL,
        "response": {"data": {"optionsChain": [{
            "symbol": "NSE:BANKNIFTY26SEP58100CE", "ltp": 101.0,
            "oi": 500_000, "pdoi": 499_000, "strike_price": 58_100,
            "option_type": "CE", "expiry": "2026-09-29",
        }]}},
    }
    option_line = json.dumps(option) + "\n"
    contract["config"]["max_read_bytes_per_file_per_poll"] = len(option_line.encode())
    contract["config"]["max_buffer_bytes_per_file"] = len(option_line.encode())
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(option_line)

    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.metrics["candidate_selection_probe_bytes"] == len(option_line.encode())
    assert ingestor.metrics["candidate_selection_probe_refusals"] == 0
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 1
    assert str(oi_path.relative_to(data)) not in ingestor.checkpoints
    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["CE"]
    rows = ingestor.poll(source_paths=[raw_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert ingestor.metrics["candidate_selection_probe_refusals"] == 1
    assert ingestor.db.execute("select count(*) from futures_candidate_outbox").fetchone()[0] == 0
    assert any(
        row["reason"] == "FUTURES_SELECTION_SEARCH_LIMIT"
        for row in ingestor.unknown_symbol_audit()
    )
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[oi_path]) == []
    assert restarted.metrics["candidate_selection_lookahead_reads"] == 0
    assert restarted.poll(source_paths=[oi_path]) == []
    restarted.close()


def test_selection_probe_replacement_before_selection_is_quarantined_and_unblocks_index(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    future_receipt = f"{session}T09:15:00.100000+05:30"
    option_receipt = f"{session}T09:15:00.150000+05:30"
    index_receipt = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(future_receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100)
        + "\n" + _market(index_receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200)
        + "\n"
    )
    option = {
        "source": "option_chain", "request_time": option_receipt,
        "received_at": option_receipt, "requested_symbol": CANONICAL_INDEX_SYMBOL,
        "response": {"data": {"optionsChain": [{
            "symbol": "NSE:BANKNIFTY26SEP58100CE", "ltp": 101.0,
            "oi": 500_000, "pdoi": 499_000, "strike_price": 58_100,
            "option_type": "CE", "expiry": "2026-09-29",
        }]}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(option) + "\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    target = ingestor.db.execute(
        "select probe_offset from futures_selection_probe where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone()[0]
    replacement = oi_path.with_suffix(".replacement")
    replacement.write_text("\n")
    os.replace(replacement, oi_path)

    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert ingestor.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 0
    quarantine = ingestor.db.execute(
        "select reason,expected_offset,detected_size from quarantined_source"
    ).fetchone()
    assert quarantine == ("FUTURES_SELECTION_PROBE_FILE_REPLACED", target, 1)
    assert not ingestor.symbols.selected_futures_for_session(session)
    assert any(
        row["reason"] == "FUTURES_SELECTION_EVIDENCE_QUARANTINED"
        for row in ingestor.unknown_symbol_audit()
    )
    assert [
        row["reason"] for row in ingestor.ledgers["refusals_data_quality"].rows()
        if row["reason"].startswith("FUTURES_SELECTION_PROBE_")
    ] == ["FUTURES_SELECTION_PROBE_FILE_REPLACED"]
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[oi_path]) == []
    assert str(oi_path.relative_to(data)) in restarted._quarantined_sources
    assert [
        row["reason"] for row in restarted.ledgers["refusals_data_quality"].rows()
        if row["reason"].startswith("FUTURES_SELECTION_PROBE_")
    ] == ["FUTURES_SELECTION_PROBE_FILE_REPLACED"]
    restarted.close()


def test_selected_probe_replacement_never_publishes_contract_from_vanished_evidence(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100)
        + "\n" + _market(receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    )
    depth = {
        "source": "future_depth", "request_time": receipt,
        "received_at": receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    original = (json.dumps(depth) + "\n").encode()
    oi_path.write_bytes(original)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.symbols.selected_futures_for_session(session) == {
        "NSE:BANKNIFTY26SEPFUT"
    }
    replacement = oi_path.with_suffix(".replacement")
    replacement.write_bytes(b" " * (len(original) - 1) + b"\n")
    os.replace(replacement, oi_path)

    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert not ingestor.symbols.selected_futures_for_session(session)
    assert ingestor.db.execute(
        "select value from runtime_meta where key=?",
        (f"selected_futures:{session}",),
    ).fetchone() is None
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert not any(
        row.instrument_class in {"FUTURES", "FUTURES_OI"} for row in rows
    )
    assert not ingestor.ledgers["normalized_raw_events"].rows()[-1].get(
        "source_file", ""
    ).startswith("oi/")
    ingestor.close()


def test_selected_candidate_raw_replacement_is_quarantined_without_freezing_index(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    original = (
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.2, 100)
        + "\n" + _market(receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    ).encode()
    raw_path.write_bytes(original)
    depth = {
        "source": "future_depth", "request_time": receipt,
        "received_at": receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(depth) + "\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    replacement = raw_path.with_suffix(".replacement")
    replacement.write_bytes(b" " * (len(original) - 1) + b"\n")
    os.replace(replacement, raw_path)

    rows = ingestor.poll(source_paths=[raw_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert not ingestor.symbols.selected_futures_for_session(session)
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(raw_path.relative_to(data)),),
    ).fetchone()[0] == "FUTURES_CANDIDATE_SOURCE_FILE_REPLACED"
    assert any(
        row["reason"] == "FUTURES_SELECTION_EVIDENCE_QUARANTINED"
        for row in ingestor.unknown_symbol_audit()
    )

    # The unmodified OI source is ingested through the primary cursor, so the
    # dynamic selection becomes authoritative again without ever consuming
    # bytes from the quarantined raw replacement.
    oi_rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in oi_rows] == ["FUTURES_OI"]
    assert ingestor.symbols.selected_futures_for_session(session) == {
        "NSE:BANKNIFTY26SEPFUT"
    }
    later = f"{session}T10:00:00.100000+05:30"
    later_raw = data / f"raw/{session}/events_10.jsonl"
    later_raw.write_text(
        _market(later, "NSE:BANKNIFTY26SEPFUT", 58_140.0, 300) + "\n"
    )
    later_rows = ingestor.poll(source_paths=[later_raw])
    assert [row.instrument_class for row in later_rows] == ["FUTURES"]
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    assert restarted.poll(source_paths=[raw_path]) == []
    assert [
        row["reason"] for row in restarted.ledgers["refusals_data_quality"].rows()
        if row["reason"].startswith("FUTURES_CANDIDATE_SOURCE_")
    ] == ["FUTURES_CANDIDATE_SOURCE_FILE_REPLACED"]
    restarted.close()


def test_unselected_candidate_remains_barrier_until_selection_authority_replays(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    candidate_receipt = f"{session}T09:15:00.100000+05:30"
    depth_receipt = f"{session}T09:15:00.150000+05:30"
    index_receipt = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(candidate_receipt, "NSE:BANKNIFTY26OCTFUT", 58_160.0, 100)
        + "\n" + _market(index_receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200)
        + "\n"
    )
    depth = {
        "source": "future_depth", "request_time": depth_receipt,
        "received_at": depth_receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(depth) + "\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.symbols.selected_futures_for_session(session) == {
        "NSE:BANKNIFTY26SEPFUT"
    }
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 1
    assert ingestor.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 1

    # Catching up the raw candidate source cannot classify or delete a
    # non-selected candidate while the selecting OI bytes are probe-only.
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 1
    assert not any(
        row["reason"] == "UNSELECTED_FUTURES_CONTRACT"
        for row in ingestor.unknown_symbol_audit()
    )

    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["FUTURES_OI", "INDEX"]
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert ingestor.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 0
    assert any(
        row["reason"] == "UNSELECTED_FUTURES_CONTRACT"
        for row in ingestor.unknown_symbol_audit()
    )
    ingestor.close()


def test_missing_candidate_source_is_quarantined_after_restart_and_unblocks_index(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    index_receipt = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n" + _market(index_receipt, CANONICAL_INDEX_SYMBOL, 58_100.0, 200)
        + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    ingestor.close()
    raw_path.unlink()

    restarted = IncrementalJSONLIngestor(contract)
    rows = restarted.poll()
    assert [row.instrument_class for row in rows] == ["INDEX"]
    rel = str(raw_path.relative_to(data))
    assert restarted.db.execute(
        "select reason,detected_identity,detected_size "
        "from quarantined_source where source_file=?",
        (rel,),
    ).fetchone() == ("FUTURES_CANDIDATE_SOURCE_MISSING", "<MISSING>", -1)
    assert restarted.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert any(
        row["reason"] == "FUTURES_CANDIDATE_SOURCE_QUARANTINED"
        for row in restarted.unknown_symbol_audit()
    )
    restarted.close()

    second_restart = IncrementalJSONLIngestor(contract)
    assert second_restart.poll() == []
    assert [
        row["reason"]
        for row in second_restart.ledgers["refusals_data_quality"].rows()
        if row["reason"] == "FUTURES_CANDIDATE_SOURCE_MISSING"
    ] == ["FUTURES_CANDIDATE_SOURCE_MISSING"]
    second_restart.close()


def test_unrelated_committed_mutation_does_not_invalidate_pending_selection(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    early = f"{session}T09:15:00.050000+05:30"
    candidate_receipt = f"{session}T09:15:00.100000+05:30"
    depth_receipt = f"{session}T09:15:00.150000+05:30"
    later = f"{session}T09:15:00.200000+05:30"
    unrelated = data / f"raw/{session}/events_08.jsonl"
    original = (
        _market(early, CANONICAL_INDEX_SYMBOL, 58_090.0, 10) + "\n"
    ).encode()
    replacement = (
        _market(early, CANONICAL_INDEX_SYMBOL, 58_091.0, 10) + "\n"
    ).encode()
    assert len(original) == len(replacement)
    unrelated.write_bytes(original)
    candidate = data / f"raw/{session}/events_09.jsonl"
    candidate.write_text(
        _market(candidate_receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n" + _market(later, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    )
    depth = {
        "source": "future_depth", "request_time": depth_receipt,
        "received_at": depth_receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(depth) + "\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert [row.price for row in ingestor.poll(
        source_paths=[unrelated, candidate]
    )] == [58_090.0]
    assert ingestor.poll(source_paths=[oi_path]) == []
    selected = ingestor.symbols.selected_futures_for_session(session)
    with unrelated.open("r+b") as handle:
        handle.write(replacement)
        handle.flush()
        os.fsync(handle.fileno())

    assert ingestor.poll(source_paths=[unrelated]) == []
    assert ingestor.symbols.selected_futures_for_session(session) == selected
    assert ingestor.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 1
    assert ingestor.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 1
    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == [
        "FUTURES", "FUTURES_OI", "INDEX",
    ]
    ingestor.close()


def test_incomplete_probe_budget_is_durable_across_restart_and_finitely_refused(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    later = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n" + _market(later, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    )
    partial = b'{"source":"future_depth"'
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_bytes(partial)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    ingestor.close()
    contract["config"]["max_read_bytes_per_file_per_poll"] = len(partial) * 2
    contract["config"]["max_buffer_bytes_per_file"] = len(partial) * 2
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.db.execute(
        "select probe_offset,inspected_offset,bytes_consumed "
        "from futures_selection_probe"
    ).fetchone() == (0, len(partial), len(partial))
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    # The exact incomplete-tail identity and inspected end survive restart.
    # An unchanged poll performs no selection-probe read and charges no byte a
    # second time.
    assert restarted.poll(source_paths=[oi_path]) == []
    assert restarted.metrics["candidate_selection_lookahead_reads"] == 0
    assert restarted.metrics["candidate_selection_probe_bytes"] == 0
    assert restarted.db.execute(
        "select probe_offset,inspected_offset,bytes_consumed "
        "from futures_selection_probe"
    ).fetchone() == (0, len(partial), len(partial))

    with oi_path.open("ab") as handle:
        handle.write(partial)
        handle.flush()
        os.fsync(handle.fileno())
    rows = restarted.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    # The append read includes the bounded old tail for exact validation and
    # parsing, but only the newly appended half consumes the durable budget.
    assert restarted.metrics["candidate_selection_probe_bytes"] == len(partial) * 2
    assert restarted.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 0
    assert restarted.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone()[0] == (
        "FUTURES_SELECTION_PROBE_INCOMPLETE_LINE_BUDGET_EXHAUSTED"
    )
    assert restarted.poll(source_paths=[oi_path]) == []
    assert restarted.metrics["candidate_selection_probe_bytes"] == len(partial) * 2
    restarted.close()


def test_incomplete_probe_cursor_schema_migration_reparses_once_then_stays_static(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(
            f"{session}T09:15:00.100000+05:30",
            "NSE:BANKNIFTY26SEPFUT",
            58_130.0,
            100,
        )
        + "\n"
    )
    partial = b'{"source":"future_depth"'
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_bytes(partial)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    with ingestor.db:
        ingestor.db.execute(
            "alter table futures_selection_probe rename to probe_with_cursor"
        )
        ingestor.db.execute(
            "create table futures_selection_probe("
            "source_file text primary key,session_date text not null,"
            "start_offset integer not null,probe_offset integer not null,"
            "identity text not null,prefix_fingerprint text not null,"
            "mtime_ns_at_probe integer not null,replay_target integer,"
            "bytes_consumed integer not null default 0)"
        )
        ingestor.db.execute(
            "insert into futures_selection_probe("
            "source_file,session_date,start_offset,probe_offset,identity,"
            "prefix_fingerprint,mtime_ns_at_probe,replay_target,bytes_consumed) "
            "select source_file,session_date,start_offset,probe_offset,identity,"
            "prefix_fingerprint,mtime_ns_at_probe,replay_target,bytes_consumed "
            "from probe_with_cursor"
        )
        ingestor.db.execute("drop table probe_with_cursor")
    ingestor.close()

    migrated = IncrementalJSONLIngestor(contract)
    assert migrated.db.execute(
        "select probe_offset,inspected_offset,bytes_consumed "
        "from futures_selection_probe"
    ).fetchone() == (0, 0, 0)
    assert migrated.poll(source_paths=[oi_path]) == []
    assert migrated.metrics["candidate_selection_lookahead_reads"] == 1
    assert migrated.metrics["candidate_selection_probe_bytes"] == len(partial)
    assert migrated.poll(source_paths=[oi_path]) == []
    assert migrated.metrics["candidate_selection_lookahead_reads"] == 1
    assert migrated.metrics["candidate_selection_probe_bytes"] == len(partial)
    migrated.close()


def test_static_incomplete_probe_after_complete_prefix_performs_no_raw_open(
    tmp_path, monkeypatch,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(
            f"{session}T09:15:00.100000+05:30",
            "NSE:BANKNIFTY26SEPFUT",
            58_130.0,
            100,
        )
        + "\n"
    )
    partial = b'{"source":"future_depth"'
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_bytes(b"{}\n" + partial)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.db.execute(
        "select probe_offset,inspected_offset from futures_selection_probe"
    ).fetchone() == (3, 3 + len(partial))
    ingestor.close()

    restarted = IncrementalJSONLIngestor(contract)
    original_open = Path.open
    raw_opens = []

    def measured_open(path, *args, **kwargs):
        if path == oi_path:
            raw_opens.append((args, kwargs))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", measured_open)
    assert restarted.poll(source_paths=[oi_path]) == []
    assert raw_opens == []
    assert restarted.metrics["candidate_selection_probe_bytes"] == 0
    restarted.close()


def test_inspected_probe_tail_rewrite_plus_append_is_quarantined(tmp_path):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(
            f"{session}T09:15:00.100000+05:30",
            "NSE:BANKNIFTY26SEPFUT",
            58_130.0,
            100,
        )
        + "\n"
        + _market(
            f"{session}T09:15:00.200000+05:30",
            CANONICAL_INDEX_SYMBOL,
            58_100.0,
            200,
        )
        + "\n"
    )
    partial = b'{"source":"future_depth"'
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_bytes(partial)
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    with oi_path.open("r+b") as handle:
        handle.seek(5)
        handle.write(b"X")
        handle.seek(0, os.SEEK_END)
        handle.write(b"}\n")
        handle.flush()
        os.fsync(handle.fileno())
    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone() == ("FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",)
    assert not ingestor.symbols.selected_futures_for_session(session)
    ingestor.close()


def test_complete_probe_authority_middle_rewrite_with_append_is_quarantined(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n"
        + _market(
            f"{session}T09:15:00.200000+05:30",
            CANONICAL_INDEX_SYMBOL,
            58_100.0,
            200,
        )
        + "\n"
    )
    block_size = IncrementalJSONLIngestor._INTEGRITY_BLOCK_BYTES
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_bytes((b" " * (block_size - 1) + b"\n") * 3 + b"{}\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    depth = {
        "source": "future_depth", "request_time": receipt,
        "received_at": receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    with oi_path.open("r+b") as handle:
        handle.seek(block_size + 8192)
        handle.write(b"\t")
        handle.seek(0, os.SEEK_END)
        handle.write((json.dumps(depth) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())
    rows = ingestor.poll(source_paths=[oi_path])
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert ingestor.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone() == ("FUTURES_SELECTION_PROBE_FILE_REPLACED_IN_PLACE",)
    assert not ingestor.symbols.selected_futures_for_session(session)
    ingestor.close()


def test_missing_selection_probe_authority_is_quarantined_after_restart(
    tmp_path,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    (data / f"oi/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n"
        + _market(
            f"{session}T09:15:00.200000+05:30",
            CANONICAL_INDEX_SYMBOL,
            58_100.0,
            200,
        )
        + "\n"
    )
    depth = {
        "source": "future_depth", "request_time": receipt,
        "received_at": receipt, "requested_symbol": "NSE:BANKNIFTY26SEPFUT",
        "response": {"d": {"NSE:BANKNIFTY26SEPFUT": {
            "ltp": 58_131.0, "v": 200, "oi": 2_000_000,
            "pdoi": 1_999_000, "expiry": "2026-09-29",
        }}},
    }
    oi_path = data / f"oi/{session}/oi_09.jsonl"
    oi_path.write_text(json.dumps(depth) + "\n")
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    assert ingestor.poll(source_paths=[oi_path]) == []
    assert ingestor.db.execute(
        "select replay_target from futures_selection_probe"
    ).fetchone()[0] is not None
    ingestor.close()
    oi_path.unlink()

    restarted = IncrementalJSONLIngestor(contract)
    rows = restarted.poll()
    assert [row.instrument_class for row in rows] == ["INDEX"]
    assert restarted.db.execute(
        "select reason from quarantined_source where source_file=?",
        (str(oi_path.relative_to(data)),),
    ).fetchone() == ("FUTURES_SELECTION_PROBE_MISSING",)
    assert restarted.db.execute(
        "select count(*) from futures_candidate_outbox"
    ).fetchone()[0] == 0
    assert restarted.db.execute(
        "select count(*) from futures_selection_probe"
    ).fetchone()[0] == 0
    restarted.close()


def test_quarantine_audit_uses_persisted_detection_clock_after_crash(
    tmp_path, monkeypatch,
):
    data, contract = _contract(tmp_path)
    contract["config"]["selected_futures_by_session"] = {}
    session = "2026-08-26"
    (data / f"raw/{session}").mkdir(parents=True)
    receipt = f"{session}T09:15:00.100000+05:30"
    later = f"{session}T09:15:00.200000+05:30"
    raw_path = data / f"raw/{session}/events_09.jsonl"
    raw_path.write_text(
        _market(receipt, "NSE:BANKNIFTY26SEPFUT", 58_130.0, 100)
        + "\n" + _market(later, CANONICAL_INDEX_SYMBOL, 58_100.0, 200) + "\n"
    )
    ingestor = IncrementalJSONLIngestor(contract)
    assert ingestor.poll(source_paths=[raw_path]) == []
    raw_path.unlink()

    def crash_before_audit_flush():
        if ingestor._quality_pending:
            raise RuntimeError("synthetic crash before quarantine audit flush")

    monkeypatch.setattr(ingestor, "_flush_quality", crash_before_audit_flush)
    with pytest.raises(RuntimeError, match="quarantine audit flush"):
        ingestor.poll()
    detected_at = ingestor.db.execute(
        "select detected_at from quarantined_source"
    ).fetchone()[0]
    pending = dict(ingestor._quality_pending[0])
    assert pending["effective_timestamp"] == detected_at
    ingestor.db.close()  # simulate process death; do not flush the pending ledger

    restarted = IncrementalJSONLIngestor(contract)
    rows = restarted.poll()
    assert [row.instrument_class for row in rows] == ["INDEX"]
    audit = [
        row for row in restarted.ledgers["refusals_data_quality"].rows()
        if row["reason"] == "FUTURES_CANDIDATE_SOURCE_MISSING"
    ]
    assert len(audit) == 1
    assert audit[0]["effective_timestamp"] == detected_at
    assert audit[0]["event_id"] == pending["event_id"]
    assert audit[0]["detail"] == pending["detail"]
    assert parse_timestamp(audit[0]["publication_timestamp"]) >= parse_timestamp(
        audit[0]["effective_timestamp"]
    )
    restarted.close()


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
