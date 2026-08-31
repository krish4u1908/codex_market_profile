from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from banknifty_profiler.new_divergence.nightly_context import (
    CONTEXT_RUNTIME_VERSION,
    FAMILIES,
    NightlyContextConfig,
    _connect,
    _volume_value_area,
    inspect_context,
    run_nightly_context,
)
from banknifty_profiler.new_divergence.projection import inventory_context_for_session


IST = ZoneInfo("Asia/Kolkata")
INDEX = "NSE:NIFTYBANK-INDEX"
FUTURES = "NSE:BANKNIFTY31AUGFUT"
ROOT = Path(__file__).resolve().parents[2]


def _line(row: dict[str, object]) -> str:
    return json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"


def _build_session(root: Path, day: date) -> None:
    raw_directory = root / "raw" / day.isoformat()
    oi_directory = root / "oi" / day.isoformat()
    raw_directory.mkdir(parents=True)
    oi_directory.mkdir(parents=True)
    raw_lines = []
    oi_lines = []
    start = datetime.combine(day, datetime.min.time(), IST).replace(hour=9, minute=15)
    future_expiry = int(datetime(2031, 8, 28, tzinfo=IST).timestamp())
    option_expiry = int(datetime(2031, 8, 21, tzinfo=IST).timestamp())
    option_symbols = [
        ("NSE:BANKNIFTY31AUG44900CE", "call", 44900),
        ("NSE:BANKNIFTY31AUG45000CE", "call", 45000),
        ("NSE:BANKNIFTY31AUG45100CE", "call", 45100),
        ("NSE:BANKNIFTY31AUG44900PE", "put", 44900),
        ("NSE:BANKNIFTY31AUG45000PE", "put", 45000),
        ("NSE:BANKNIFTY31AUG45100PE", "put", 45100),
    ]
    base_shift = (day.day - 18) * 50
    for minute in range(375):
        timestamp = start + timedelta(minutes=minute)
        instant = timestamp.isoformat()
        index_price = 45000 + base_shift + (25 if minute % 7 else 0)
        raw_lines.append(
            _line(
                {
                    "event_time": instant,
                    "received_at": instant,
                    "message": {"symbol": INDEX, "ltp": index_price},
                }
            )
        )
        raw_lines.append(
            _line(
                {
                    "event_time": instant,
                    "received_at": instant,
                    "message": {
                        "symbol": FUTURES,
                        "ltp": index_price + 40,
                        "vol_traded_today": 10_000 + minute * 11,
                    },
                }
            )
        )
        future_oi = 100_000 + minute * 10 + (20 if minute % 2 else 0)
        oi_lines.append(
            _line(
                {
                    "source": "future_depth",
                    "received_at": instant,
                    "request_time": instant,
                    "response": {
                        "d": {
                            FUTURES: {
                                "expiry": future_expiry,
                                "ltp": index_price + 40,
                                "oi": future_oi,
                                "v": 10_000 + minute * 11,
                            }
                        }
                    },
                }
            )
        )
        chain = []
        for offset, (symbol, _instrument, strike) in enumerate(option_symbols):
            alternating = 30 if minute % 2 else 0
            chain.append(
                {
                    "symbol": symbol,
                    "strike_price": strike,
                    "expiry": option_expiry,
                    "ltp": 200 + offset,
                    "oi": 20_000 + offset * 100 + minute * 10 + alternating,
                    "volume": 1_000 + minute,
                }
            )
        oi_lines.append(
            _line(
                {
                    "source": "option_chain",
                    "received_at": instant,
                    "request_time": instant,
                    "response": {
                        "data": {
                            "expiryData": [{"date": "21-08-2031"}],
                            "optionsChain": chain,
                        }
                    },
                }
            )
        )
    (raw_directory / "events_09.jsonl").write_text("".join(raw_lines), encoding="utf-8")
    (oi_directory / "oi_09.jsonl").write_text("".join(oi_lines), encoding="utf-8")


def _three_sessions(root: Path) -> None:
    for day in (date(2031, 8, 18), date(2031, 8, 19), date(2031, 8, 20)):
        _build_session(root, day)


def _config() -> NightlyContextConfig:
    return NightlyContextConfig(stability_seconds=0)


def test_checked_in_nightly_config_is_quality_only() -> None:
    config_path = ROOT / "configs" / "nightly_context_v2.json"
    config = NightlyContextConfig.from_path(config_path)
    assert config == NightlyContextConfig()
    keys = set(json.loads(config_path.read_text(encoding="utf-8")))
    assert not keys & {
        "production_weight",
        "entry_threshold",
        "confirmation_threshold",
        "materiality_threshold",
    }


def test_volume_value_area_expands_contiguously_from_vpoc() -> None:
    result = _volume_value_area(
        {75.0: 20.0, 100.0: 40.0, 125.0: 30.0, 150.0: 10.0},
        100.0,
        bin_points=25,
        target_fraction=0.70,
    )
    assert result["value_area_low"] == 100.0
    assert result["value_area_high"] == 125.0
    assert result["value_area_weight"] == pytest.approx(70.0)
    assert result["value_area_achieved_fraction"] == pytest.approx(0.70)

    tied = _volume_value_area(
        {75.0: 15.0, 100.0: 40.0, 125.0: 15.0, 150.0: 30.0},
        100.0,
        bin_points=25,
        target_fraction=0.70,
    )
    assert (tied["value_area_low"], tied["value_area_high"]) == (75.0, 125.0)
    assert tied["value_area_tie_expansions"] == 1


def test_context_database_v1_migrates_value_area_columns(tmp_path: Path) -> None:
    database = tmp_path / "context.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO schema_metadata VALUES('schema_version','1');
            CREATE TABLE scope_controls(
                snapshot_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                family TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                control_value REAL,
                total_weight REAL,
                winning_bin_weight REAL,
                runner_up_bin REAL,
                runner_up_weight REAL,
                evidence_count INTEGER NOT NULL,
                tie_break_reason TEXT,
                latest_evidence_timestamp TEXT,
                source_sessions_json TEXT NOT NULL,
                source_revision_ids_json TEXT NOT NULL,
                source_contracts_json TEXT NOT NULL,
                source_expiries_json TEXT NOT NULL,
                rejected_sources_json TEXT NOT NULL,
                PRIMARY KEY(snapshot_id,scope,family)
            );
            """
        )
    connection = _connect(database)
    try:
        assert connection.execute(
            "SELECT value FROM schema_metadata WHERE key='schema_version'"
        ).fetchone()["value"] == "2"
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(scope_controls)")
        }
        assert {
            "value_area_low",
            "value_area_high",
            "value_area_weight",
            "value_area_target_fraction",
            "value_area_achieved_fraction",
            "value_area_method",
            "value_area_tie_expansions",
        } <= columns
    finally:
        connection.close()


def test_nightly_context_publishes_composable_scopes_and_is_idempotent(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    _three_sessions(data)

    first = run_nightly_context(
        data,
        state,
        config=_config(),
        cutoff_session=date(2031, 8, 20),
    )
    assert first["status"] == "COMPLETE"
    assert first["analyzed_session_count"] == 3
    assert first["source_chain"] == ["2031-08-18", "2031-08-19", "2031-08-20"]
    assert first["available_control_count"] == len(FAMILIES) * 3
    assert first["model_parameters_changed"] is False

    status = inspect_context(state)
    assert status["valid"] is True
    assert status["cutoff_source_session"] == "2031-08-20"
    artifact = Path(status["artifact_directory"])
    assert {path.name for path in artifact.iterdir()} == {
        "context.json",
        "sha256_manifest.json",
        "source_manifest.json",
    }
    context = json.loads((artifact / "context.json").read_text(encoding="utf-8"))
    assert context["runtime_version"] == CONTEXT_RUNTIME_VERSION
    call_control = next(
        row
        for row in context["controls"]
        if row["scope"] == "3D" and row["family"] == "CE_POS_OI_VPOC"
    )
    assert all(
        symbol.endswith("CE")
        for source in call_control["source_contracts"]
        for symbol in source["symbols"]
    )
    price_control = next(
        row
        for row in context["controls"]
        if row["scope"] == "3D" and row["family"] == "BN_REF_FUT_VOLUME_VPOC"
    )
    assert all(source["expiries"] == ["2031-08-28"] for source in price_control["source_expiries"])
    assert price_control["value_area_low"] <= price_control["control_value"]
    assert price_control["control_value"] <= price_control["value_area_high"]
    assert price_control["value_area_target_fraction"] == pytest.approx(0.70)
    assert price_control["value_area_achieved_fraction"] >= 0.70
    oi_control = next(
        row
        for row in context["controls"]
        if row["scope"] == "1D" and row["family"] == "FUT_POS_OI_VPOC"
    )
    assert oi_control["value_area_low"] is None
    assert oi_control["value_area_high"] is None

    browser_context = inventory_context_for_session("2031-08-21", state)
    assert browser_context["status"] == "AVAILABLE"
    assert browser_context["cutoff_source_session"] == "2031-08-20"
    assert browser_context["feature_flags"]["oi_vpoc"]["available"] is True
    assert browser_context["feature_flags"]["volume_profile"]["available"] is True
    assert len(browser_context["controls"]) == len(FAMILIES) * 3
    same_day = inventory_context_for_session("2031-08-20", state)
    assert same_day["status"] == "UNAVAILABLE"
    assert same_day["reason"] == "NO_CONTEXT_STRICTLY_BEFORE_REPLAY_SESSION"
    oi_disabled = inventory_context_for_session(
        "2031-08-21", state, enable_oi_vpoc=False
    )
    assert {row["family"] for row in oi_disabled["controls"]} == {
        "BN_REF_FUT_VOLUME_VPOC"
    }

    second = run_nightly_context(
        data,
        state,
        config=_config(),
        cutoff_session=date(2031, 8, 20),
    )
    assert second["snapshot_id"] == first["snapshot_id"]
    assert second["snapshot_reused"] is True
    assert second["analyzed_session_count"] == 0
    assert second["reused_session_count"] == 3

    shutil.rmtree(artifact)
    recovered = run_nightly_context(
        data,
        state,
        config=_config(),
        cutoff_session=date(2031, 8, 20),
    )
    assert recovered["snapshot_id"] == first["snapshot_id"]
    assert inspect_context(state)["valid"] is True

    with sqlite3.connect(state / "context.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM session_revisions").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM context_snapshots").fetchone()[0] == 1
        control = connection.execute(
            """SELECT c.control_value,c.total_weight,c.evidence_count,
                      c.value_area_low,c.value_area_high
               FROM scope_controls c
               WHERE c.scope='3D' AND c.family='BN_REF_FUT_VOLUME_VPOC'"""
        ).fetchone()
        total = connection.execute(
            """SELECT SUM(total_weight),SUM(evidence_count)
               FROM session_profiles WHERE family='BN_REF_FUT_VOLUME_VPOC'"""
        ).fetchone()
        assert control[1:3] == pytest.approx(total)
        assert control[3] <= control[0] <= control[4]

    # File hashes alone are not enough: a self-consistently rehashed bundle
    # with the wrong coordinate must still fail the browser identity contract.
    context_path = artifact / "context.json"
    tampered = json.loads(context_path.read_text(encoding="utf-8"))
    tampered["coordinate"] = "WRONG_COORDINATE"
    context_path.write_text(json.dumps(tampered, sort_keys=True) + "\n", encoding="utf-8")
    hash_manifest_path = artifact / "sha256_manifest.json"
    hash_manifest = json.loads(hash_manifest_path.read_text(encoding="utf-8"))
    hash_manifest["files"]["context.json"] = hashlib.sha256(
        context_path.read_bytes()
    ).hexdigest()
    hash_manifest_path.write_text(
        json.dumps(hash_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    refused = inventory_context_for_session("2031-08-21", state)
    assert refused["status"] == "UNAVAILABLE"
    assert refused["reason"] == "NEWEST_PRIOR_CONTEXT_FAILED_VERIFICATION"
    assert any("CONTEXT_IDENTITY_MISMATCH:coordinate" in row for row in refused["details"])


def test_changed_source_creates_revision_without_overwriting_history(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    _three_sessions(data)
    first = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    changed = data / "raw" / "2031-08-20" / "events_09.jsonl"
    changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    second = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    assert second["snapshot_id"] != first["snapshot_id"]
    assert second["analyzed_session_count"] == 1
    with sqlite3.connect(state / "context.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM session_revisions").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM context_snapshots").fetchone()[0] == 2


def test_rejected_latest_session_fails_every_scope_closed(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    _three_sessions(data)
    broken = data / "oi" / "2031-08-20" / "oi_09.jsonl"
    broken.write_text(broken.read_text(encoding="utf-8") + "{not-json}\n", encoding="utf-8")
    result = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    assert result["source_quality"]["2031-08-20"] == "REJECTED"
    assert result["available_control_count"] == 0
    assert result["unavailable_control_count"] == len(FAMILIES) * 3
    context = json.loads(
        (Path(result["artifact_directory"]) / "context.json").read_text(encoding="utf-8")
    )
    assert {row["reason"] for row in context["controls"]} == {
        "SOURCE_SESSION_QUALITY_REJECTED"
    }


def test_missing_source_counterpart_is_rejected_not_skipped(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    _three_sessions(data)
    shutil.rmtree(data / "oi" / "2031-08-20")
    result = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    assert result["cutoff_source_session"] == "2031-08-20"
    assert result["source_quality"]["2031-08-20"] == "REJECTED"
    assert result["available_control_count"] == 0


def test_cutoff_excludes_later_session_and_unstable_required_data_is_refused(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    _three_sessions(data)
    _build_session(data, date(2031, 8, 21))
    result = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    assert "2031-08-21" not in result["source_chain"]

    with pytest.raises(ValueError, match="not stable"):
        run_nightly_context(
            data,
            tmp_path / "unstable-state",
            config=NightlyContextConfig(stability_seconds=3600),
            cutoff_session=date(2031, 8, 20),
        )


def test_bootstrap_scans_only_latest_three_contributing_sessions(tmp_path: Path) -> None:
    data = tmp_path / "collector"
    state = tmp_path / "state"
    for day in (
        date(2031, 8, 17),
        date(2031, 8, 18),
        date(2031, 8, 19),
        date(2031, 8, 20),
    ):
        _build_session(data, day)

    result = run_nightly_context(
        data, state, config=_config(), cutoff_session=date(2031, 8, 20)
    )
    assert result["source_chain"] == ["2031-08-18", "2031-08-19", "2031-08-20"]
    assert result["discovered_session_count"] == 4
    assert result["selected_contributing_session_count"] == 3
    assert result["analyzed_session_count"] == 3
    with sqlite3.connect(state / "context.sqlite3") as connection:
        stored = connection.execute(
            "SELECT session_date FROM session_revisions ORDER BY session_date"
        ).fetchall()
    assert [row[0] for row in stored] == result["source_chain"]
