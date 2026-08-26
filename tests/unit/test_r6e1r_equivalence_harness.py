from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/run_r6e1r_equivalence.py"
SPEC = importlib.util.spec_from_file_location("run_r6e1r_equivalence", SCRIPT)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))


def _config(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Kolkata",
                "synchronization_tolerance_ms": 2000,
                "poll_interval_seconds": 0.01,
                "max_read_bytes_per_file_per_poll": 1_048_576,
                "max_buffer_bytes_per_file": 65_536,
                "freshness_seconds": {
                    "index": 10,
                    "futures": 10,
                    "futures_oi": 180,
                    "ce": 180,
                    "pe": 180,
                },
                "allowed_bind": "127.0.0.1",
                "classification": "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL",
                "analytical_threshold_overrides": None,
            }
        )
    )
    return path


def _physical_fixture(root: Path) -> tuple[Path, tuple[str, ...]]:
    prior = "2026-08-19"
    session = "2026-08-20"
    for date in (prior, session):
        base = f"{date}T09:15:00"
        _write_jsonl(
            root / f"raw/{date}/events_09.jsonl",
            [
                {
                    "received_at": base + ".100000+05:30",
                    "event_time": base + ".090000+05:30",
                    "message": {
                        "symbol": "NSE:NIFTYBANK-INDEX",
                        "ltp": 57_000.0,
                        "vol_traded_today": 0,
                    },
                },
                {
                    "received_at": base + ".200000+05:30",
                    "event_time": base + ".190000+05:30",
                    "message": {
                        "symbol": "NSE:BANKNIFTY26AUGFUT",
                        "ltp": 57_025.0,
                        "vol_traded_today": 10,
                    },
                },
                {
                    "received_at": base + ".900000+05:30",
                    "event_time": base + ".890000+05:30",
                    "message": {
                        "symbol": "NSE:NIFTYBANK-INDEX",
                        "ltp": 57_002.0,
                        "vol_traded_today": 0,
                    },
                },
                {
                    "received_at": base + ".950000+05:30",
                    "event_time": base + ".940000+05:30",
                    "message": {
                        "symbol": "NSE:BANKNIFTY26AUGFUT",
                        "ltp": 57_028.0,
                        "vol_traded_today": 25,
                    },
                },
            ],
        )
        _write_jsonl(
            root / f"oi/{date}/oi_09.jsonl",
            [
                {
                    "received_at": base + ".300000+05:30",
                    "request_time": base + ".250000+05:30",
                    "source": "future_depth",
                    "response": {
                        "d": {
                            "NSE:BANKNIFTY26AUGFUT": {
                                "oi": 1000,
                                "ltp": 57_025.0,
                                "v": 100,
                                "expiry": 1_787_788_800,
                            }
                        }
                    },
                },
                {
                    "received_at": base + ".400000+05:30",
                    "request_time": base + ".350000+05:30",
                    "source": "option_chain",
                    "response": {
                        "data": {
                            "expiryData": [{"date": "27-08-2026"}],
                            "optionsChain": [
                                {
                                    "symbol": "NSE:BANKNIFTY26AUG57000CE",
                                    "strike_price": 57_000,
                                    "oi": 500,
                                    "ltp": 250.0,
                                    "volume": 50,
                                },
                                {
                                    "symbol": "NSE:BANKNIFTY26AUG57000PE",
                                    "strike_price": 57_000,
                                    "oi": 450,
                                    "ltp": 230.0,
                                    "volume": 45,
                                },
                            ],
                        }
                    },
                },
            ],
        )
    return root, (session,)


def _batch_configs(root: Path, sessions: tuple[str, ...]) -> tuple[Path, Path]:
    stack = root / "stack.json"
    stack.write_text(
        json.dumps(
            {
                "timezone": "Asia/Kolkata",
                "windows_minutes": [1, 3, 5],
                "volume_window_minutes": 5,
                "freshness_seconds": 180,
                "strike_step": 100,
                "near_strikes_each_side": 3,
                "volume_spike_percentile": 0.9,
                "oi_spike_percentile": 0.9,
                "robust_z_threshold": 3.0,
                "raw_market_subdirectory": "raw",
                "raw_oi_subdirectory": "oi",
                "index_symbol": "NSE:NIFTYBANK-INDEX",
                "futures_symbol": "NSE:BANKNIFTY26AUGFUT",
                "synchronization_tolerance_ms": 2000,
                "sessions": list(sessions),
            }
        )
    )
    inventory = root / "inventory.json"
    inventory.write_text(
        json.dumps(
            {
                "timezone": "Asia/Kolkata",
                "index_symbol": "NSE:NIFTYBANK-INDEX",
                "futures_symbol": "NSE:BANKNIFTY26AUGFUT",
                "discovery_start": "2026-08-19",
                "discovery_end": "2026-08-20",
                "evaluation_start": "2026-08-20",
                "evaluation_end": "2026-08-20",
                "maximum_missing_oi_minutes": 400,
                "join_tolerance_seconds": 5,
                "bin_points": 25,
                "coordinate": "CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN",
                "canonical_price_control": "BN_REF_FUT_VOLUME_VPOC",
            }
        )
    )
    return stack, inventory


def test_canonicalize_drops_only_run_metadata() -> None:
    value = {
        "effective_timestamp": "2026-08-20T09:15:00+05:30",
        "snapshot_timestamp": "2026-08-20T09:20:00+05:30",
        "publication_timestamp": "different-each-run",
        "calculation_timestamp": "different-each-run",
        "raw_run_id": "A",
        "price": 57_000.0,
    }
    result = harness.canonicalize(value)
    assert result["effective_timestamp"].endswith("+05:30")
    assert result["snapshot_timestamp"].endswith("+05:30")
    assert result["price"] == "__NUMBER__:57000"
    assert "publication_timestamp" not in result
    assert "calculation_timestamp" not in result
    assert "raw_run_id" not in result


def test_compare_snapshots_is_order_independent_but_value_exact() -> None:
    rows = [
        {"episode_id": "E1", "colour": "GREEN", "basis": 10.0},
        {"episode_id": "E2", "colour": "RED", "basis": -10.0},
    ]
    a = {"episodes": rows, "inventory": [], "dependencies": []}
    b = {
        "episodes": [
            {**rows[1], "publication_timestamp": "B"},
            {**rows[0], "publication_timestamp": "B"},
        ],
        "inventory": [],
        "dependencies": [],
    }
    comparison = harness.compare_snapshots(a, b, expected=None)
    assert all(row["status"] == "PASS" for row in comparison)

    b["episodes"][1]["basis"] = 10.01
    comparison = harness.compare_snapshots(a, b, expected=None)
    episode = next(row for row in comparison if row["component"] == "divergence_episodes")
    assert episode["status"] == "FAIL"
    assert episode["unexplained_remainder"] > 0


def test_discovery_includes_predecessor_and_refuses_derived_root(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    sources = harness.discover_sources(physical, sessions)
    relatives = {str(source.relative) for source in sources}
    assert "raw/2026-08-19/events_09.jsonl" in relatives
    assert "oi/2026-08-19/oi_09.jsonl" in relatives
    assert "raw/2026-08-20/events_09.jsonl" in relatives

    derived = tmp_path / "research/derived"
    (derived / "raw").mkdir(parents=True)
    (derived / "oi").mkdir()
    with pytest.raises(ValueError, match="research-derived"):
        harness.discover_sources(derived, sessions)


def test_merged_source_lines_are_chronological_and_byte_exact(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    sources = harness.discover_sources(physical, sessions)
    merged = list(harness.merged_source_lines(sources))
    receipts = [json.loads(line)["received_at"] for _, line in merged]
    assert receipts == sorted(receipts)
    reconstructed: dict[str, bytes] = {}
    for source, line in merged:
        key = str(source.relative)
        reconstructed[key] = reconstructed.get(key, b"") + line
    for source in sources:
        assert reconstructed[str(source.relative)] == source.source.read_bytes()


def test_checkpoint_accounting_detects_tail_and_exact_commit(tmp_path: Path) -> None:
    source_path = tmp_path / "source/raw/2026-08-20/events_09.jsonl"
    _write_jsonl(source_path, [{"received_at": "2026-08-20T09:15:00+05:30"}])
    rows, newline = harness._count_lines(source_path)
    source = harness.SourceFile(
        source_path,
        Path("raw/2026-08-20/events_09.jsonl"),
        source_path.stat().st_size,
        rows,
        newline,
    )
    staged = tmp_path / "staged" / source.relative
    staged.parent.mkdir(parents=True)
    staged.write_bytes(source_path.read_bytes())
    exact = harness.checkpoint_accounting(
        [source],
        tmp_path / "staged",
        {str(source.relative): {"offset": source.size, "row": 1}},
    )
    assert exact[0]["status"] == "PASS"
    partial = harness.checkpoint_accounting(
        [source],
        tmp_path / "staged",
        {str(source.relative): {"offset": source.size - 2, "row": 0}},
    )
    assert partial[0]["status"] == "FAIL"
    assert partial[0]["deferred_tail_bytes"] == 2


def test_schedule_hash_comparator_reports_dependency() -> None:
    canonical = {
        "analytical_semantic_sha256": "abc",
        "analytical_ledgers_sha256": "ledger",
    }
    rows = harness.scheduling_comparison(
        canonical,
        [
            (
                "same",
                {
                    "analytical_semantic_sha256": "abc",
                    "analytical_ledgers_sha256": "ledger",
                },
            ),
            (
                "different",
                {
                    "analytical_semantic_sha256": "def",
                    "analytical_ledgers_sha256": "ledger",
                },
            ),
        ],
    )
    assert rows[0]["status"] == "PASS"
    assert rows[1]["status"] == "FAIL"
    assert rows[1]["differences"] == 1


def test_schedule_feasibility_quantifies_without_claiming_semantics(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"{}\n" * 100)
    source = harness.SourceFile(path, Path("raw/2026-08-20/events.jsonl"), 300, 100, True)
    estimate = harness.estimate_schedule_work(
        harness.SCHEDULES["one_record_per_increment"], [source], maximum_polls=50
    )
    assert estimate["estimated_polls"] == 100
    assert estimate["estimated_minimum_fsyncs"] == 200
    assert not estimate["feasible"]
    assert estimate["semantics_if_skipped"] == "REQUIRED_NOT_SATISFIED"


def test_real_checkpoint_recovery_refuses_truncate_and_replace(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    config = _config(tmp_path / "shadow.json")
    sources = harness.discover_sources(physical, sessions)
    rows = harness.checkpoint_recovery_probes(
        sources=sources,
        work_root=tmp_path / "recovery_work",
        state_root=tmp_path / "recovery_state",
        config_path=config,
    )
    assert [row["observed_refusal"] for row in rows] == [
        "FILE_TRUNCATED",
        "FILE_REPLACED",
    ]
    assert all(row["status"] == "PASS" for row in rows)
    assert not any(row["checkpoint_advanced"] for row in rows)


def test_b_uses_independent_repository_canonical_batch_processors(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    stack_config, inventory_config = _batch_configs(tmp_path, sessions)
    snapshot, metrics, opens = harness.run_clean_canonical_batch(
        data_root=physical,
        batch_root=tmp_path / "canonical_b",
        stack_config_path=stack_config,
        inventory_config_path=inventory_config,
        sessions=sessions,
    )
    assert metrics["schedule"] == "independent_clean_canonical_batch"
    assert metrics["processor_count"] == 3
    assert metrics["command_returncodes"] == [0, 0, 0]
    assert snapshot["basis"]
    assert sessions[0] in snapshot["gui_payload"]
    assert (tmp_path / "canonical_b/generated/runs/stream_stack/seal.json").is_file()
    assert opens


def test_reference_comparison_uses_reference_fields_after_type_normalization() -> None:
    a = {
        "episodes": [
            {
                "episode_id": "E1",
                "evaluation_date": "2026-08-20",
                "colour": "GREEN",
                "basis_at_confirmation": 25.0,
                "live_only_metadata": "ignored",
            }
        ]
    }
    b = {
        "episodes": [
            {
                "episode_id": "E1",
                "evaluation_date": "2026-08-20",
                "colour": "GREEN",
                "basis_at_confirmation": "25.000",
            }
        ]
    }
    reference = {
        "episodes": [
            {
                "episode_id": "E1",
                "evaluation_date": "2026-08-20",
                "colour": "GREEN",
                "basis_at_confirmation": "25.0",
            }
        ]
    }
    rows = harness.compare_reference_snapshot(
        a_snapshot=a,
        b_snapshot=b,
        reference_snapshot=reference,
        reference_name="C",
        components=("divergence_episodes",),
    )
    assert len(rows) == 2
    assert all(row["status"] == "PASS" for row in rows)


def test_gui_comparison_ignores_packaging_but_not_visible_rows() -> None:
    packed = {"fields": ["episode_id", "state"], "rows": [["E1", "ACTIVE"]]}
    a = {"gui_payload": {"2026-08-20": {"schema": "LIVE", "episodes": json.loads(json.dumps(packed))}}}
    b = {"gui_payload": {"2026-08-20": {"schema": "BATCH", "episodes": json.loads(json.dumps(packed))}}}
    reference = {
        "gui_payload": {"2026-08-20": {"source_contract_hash": "R6D", "episodes": json.loads(json.dumps(packed))}}
    }
    rows = harness.compare_reference_snapshot(
        a_snapshot=a,
        b_snapshot=b,
        reference_snapshot=reference,
        reference_name="R6D",
        components=("gui_visible_state",),
    )
    assert all(row["status"] == "PASS" for row in rows)
    b["gui_payload"]["2026-08-20"]["episodes"]["rows"][0][1] = "ENDED"
    rows = harness.compare_reference_snapshot(
        a_snapshot=a,
        b_snapshot=b,
        reference_snapshot=reference,
        reference_name="R6D",
        components=("gui_visible_state",),
    )
    assert next(row for row in rows if row["target"] == "batch_b")["status"] == "FAIL"


def test_real_live_path_chunk_split_and_restart_equivalence(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    config = _config(tmp_path / "shadow.json")
    sources = harness.discover_sources(physical, sessions)

    chunked, chunked_accounting, _ = harness.run_schedule(
        schedule=harness.SCHEDULES["large_chronological_chunks"],
        sources=sources,
        staging_root=tmp_path / "chunked_collector",
        state_root=tmp_path / "chunked_state",
        config_path=config,
        sessions=sessions,
    )
    split, split_accounting, _ = harness.run_schedule(
        schedule=harness.SCHEDULES["boundaries_inside_jsonl_lines"],
        sources=sources,
        staging_root=tmp_path / "split_collector",
        state_root=tmp_path / "split_state",
        config_path=config,
        sessions=sessions,
    )
    restarted, restart_accounting, restart_metrics = harness.run_schedule(
        schedule=harness.Schedule("restart_fixture", (1,), restart_every=2),
        sources=sources,
        staging_root=tmp_path / "restart_collector",
        state_root=tmp_path / "restart_state",
        config_path=config,
        sessions=sessions,
    )

    assert all(row["status"] == "PASS" for row in chunked_accounting)
    assert all(row["status"] == "PASS" for row in split_accounting)
    assert all(row["status"] == "PASS" for row in restart_accounting)
    assert restart_metrics["restart_count"] > 0
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, split, expected=None)
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, restarted, expected=None)
    )
    assert len(chunked["basis"]) >= 1
