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
                "inventory_maximum_missing_oi_minutes": 400,
                "inventory_join_tolerance_seconds": 5,
                "inventory_bin_points": 25,
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


def test_frozen_six_session_counts_and_gate_are_mandatory() -> None:
    assert harness.EXPECTED_COUNTS == {
        "inventory": 255,
        "divergence_episodes": 65,
        "dependency_groups": 65,
        "green": 41,
        "red": 24,
        "retriggers": 14,
        "lifecycle_transitions": 14_201,
        "dense_resolution_observations": 164_668,
        "response_observations": 65,
        "participation_dense": 69_225,
        "participation_transitions": 32_068,
        "participation_summaries": 65,
        "compatibility_snapshots": 65,
        "cross_layer_transitions": 60_659,
    }
    assert harness.frozen_count_gate_satisfied(harness.SESSIONS, disabled=False)
    assert not harness.frozen_count_gate_satisfied(harness.SESSIONS, disabled=True)
    assert harness.frozen_count_gate_satisfied(("2026-08-19",), disabled=True)
    assert {
        "inventory",
        "divergence_episodes",
        "dependency_groups",
        "lifecycle_transitions",
        "dense_resolution_observations",
        "response_observations",
        "participation_dense",
        "participation_transitions",
        "participation_summaries",
        "compatibility_snapshots",
        "cross_layer_transitions",
        "availability_states",
    } <= set(harness.REFERENCE_COMPONENTS)


def test_reference_package_requires_pinned_manifest_and_every_file(
    tmp_path: Path,
) -> None:
    package = tmp_path / "reference"
    artifact = package / "runs/canonical.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"id,value\n1,canonical\n")
    manifest = {
        "commit": "abc123",
        "file_count": 1,
        "files": [
            {
                "path": "runs/canonical.csv",
                "sha256": harness._sha256_file(artifact),
                "size": artifact.stat().st_size,
            }
        ],
        "status": "VERIFIED",
        "tag": "verified-tag",
        "tag_target": "abc123",
    }
    manifest_path = package / "package_manifest.json"
    manifest_path.write_bytes(harness._json_bytes(manifest))
    contract = {
        "manifest_sha256": harness._sha256_file(manifest_path),
        "file_count": 1,
        "status": "VERIFIED",
        "tag": "verified-tag",
    }
    result = harness.verify_reference_package_manifest(
        package, reference_name="FIXTURE", contract=contract
    )
    assert result["status"] == "PASS"
    assert result["verified_files"] == 1

    artifact.write_bytes(b"id,value\n1,tampered\n")
    with pytest.raises(ValueError, match="file identity mismatch"):
        harness.verify_reference_package_manifest(
            package, reference_name="FIXTURE", contract=contract
        )


def test_causality_audit_enforces_tolerance_backdating_and_all_public_ids() -> None:
    snapshot = {
        "basis": [
            {
                "validity_status": "VALID",
                "index_receipt_timestamp": "2026-08-20T09:15:00+05:30",
                "futures_receipt_timestamp": "2026-08-20T09:15:02.001+05:30",
                "absolute_receipt_difference_ms": 2001,
            }
        ],
        "participation_dense": [
            {"record_id": "DUPLICATE"},
            {"record_id": "DUPLICATE"},
        ],
        "participation_transitions": [
            {
                "transition_id": "T1",
                "effective_timestamp": "2026-08-20T09:15:01+05:30",
                "calculation_timestamp": "2026-08-20T09:15:00+05:30",
            }
        ],
    }
    audit = harness.audit_invariants(snapshot)
    assert audit["future_joins"] == 0
    assert audit["synchronization_tolerance_violations"] > 0
    assert audit["timestamp_backdating"] == 1
    assert audit["duplicate_analytical_ids"] == 1

    snapshot["basis"][0]["index_receipt_timestamp"] = (
        "2026-08-20T09:15:03+05:30"
    )
    audit = harness.audit_invariants(snapshot)
    assert audit["future_joins"] > 0


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


def test_raw_projection_is_byte_exact_preserves_rows_and_matches_clean_batch(
    tmp_path: Path,
) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    source = physical / "raw/2026-08-20/events_09.jsonl"
    selected_lines = source.read_bytes().splitlines(keepends=True)
    unrelated = {
        "received_at": "2026-08-20T09:14:59.000000+05:30",
        "event_time": "2026-08-20T09:14:59.000000+05:30",
        "message": {"symbol": "NSE:SBIN-EQ", "ltp": 900.0},
    }
    unrelated_line = (json.dumps(unrelated, separators=(",", ":")) + "\n").encode()
    source.write_bytes(unrelated_line + b"".join(selected_lines))
    source_hashes = {
        str(path.relative_to(physical)): harness._sha256_file(path)
        for path in physical.rglob("*.jsonl")
    }

    manifest = harness.build_raw_projection(
        data_root=physical,
        projection_root=tmp_path / "projection",
        sessions=sessions,
    )
    projected_root = Path(manifest["collector_root"])
    projected = projected_root / "raw/2026-08-20/events_09.jsonl"
    projected_lines = projected.read_bytes().splitlines(keepends=True)

    assert projected_lines[0] == b"\n"
    assert projected_lines[1:] == selected_lines
    assert manifest["source_mutations"] == 0
    assert manifest["selected_outer_records"] == 12
    assert manifest["contract_selection"]["2026-08-20"]["futures_symbol"] == (
        "NSE:BANKNIFTY26AUGFUT"
    )
    assert all(
        harness._sha256_file(physical / relative) == digest
        for relative, digest in source_hashes.items()
    )
    projected_sources = harness.discover_sources(projected_root, sessions)
    assert sum(source.json_records or 0 for source in projected_sources) == 12
    reused = harness.validate_existing_raw_projection(
        manifest_path=Path(manifest["manifest_path"]),
        data_root=physical,
        sessions=sessions,
    )
    assert reused["manifest_sha256"] == manifest["manifest_sha256"]
    assert reused["reuse_validation"] == {
        "status": "PASS",
        "authoritative_source_hashes_verified": 4,
        "projection_file_hashes_verified": 4,
        "provenance_verified": True,
        "provenance_rows_verified": 12,
        "dynamic_contract_sessions_verified": 2,
    }

    stack_config, inventory_config = _batch_configs(tmp_path, sessions)
    direct, _, _ = harness.run_clean_canonical_batch(
        data_root=physical,
        batch_root=tmp_path / "direct_b",
        stack_config_path=stack_config,
        inventory_config_path=inventory_config,
        sessions=sessions,
    )
    projected_batch, _, _ = harness.run_clean_canonical_batch(
        data_root=projected_root,
        batch_root=tmp_path / "projected_b",
        stack_config_path=stack_config,
        inventory_config_path=inventory_config,
        sessions=sessions,
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(direct, projected_batch, expected=None)
    )


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


def test_runtime_open_gate_is_measured_and_derived_from_classifications() -> None:
    permitted = harness.runtime_open_audit_summary(
        [
            {
                "run": "incremental_a",
                "path": "/tmp/a/raw/events.jsonl",
                "classification": "PERMITTED_RUNTIME_RAW_OPEN",
            },
            {
                "run": "batch_b",
                "path": "/tmp/b/raw/events.jsonl",
                "classification": "PERMITTED_RUNTIME_RAW_OPEN",
            },
        ]
    )
    assert permitted["measured"] is True
    assert permitted["prohibited_rows"] == 0

    refused = harness.runtime_open_audit_summary(
        [
            {
                "run": "batch_b",
                "path": "/research/derived/table.csv",
                "classification": "PROHIBITED_DERIVED_ANALYTICAL_INPUT",
            }
        ]
    )
    assert refused["prohibited_rows"] == 1

    unmeasured = harness.runtime_open_audit_summary(
        [{"run": "batch_b", "path": "/tmp/unknown"}]
    )
    assert unmeasured["measured"] is False
    assert unmeasured["unmeasured_rows"] == 1


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
    assert metrics["intraday_fallback_sessions"] == list(sessions)
    assert metrics["intraday_fallback_rows"] > 0
    assert snapshot["intraday_inventory"]
    assert not any(row["horizon"] != "ID" for row in snapshot["intraday_inventory"])
    assert len(snapshot["intraday_cross_layer_transitions"]) == len(
        snapshot["intraday_inventory"]
    )
    assert sessions[0] in snapshot["gui_payload"]
    assert (tmp_path / "canonical_b/generated/runs/stream_stack/seal.json").is_file()
    assert opens


def test_intraday_fallback_is_explicitly_equivalent_to_live_degradation(
    tmp_path: Path,
) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    config = _config(tmp_path / "shadow.json")
    stack_config, inventory_config = _batch_configs(tmp_path, sessions)
    all_sources = harness.discover_sources(physical, sessions)
    sources = harness.discover_sources(
        physical, sessions, include_predecessors=False
    )
    live_relatives = {source.relative for source in sources}
    context_sources = [
        source for source in all_sources if source.relative not in live_relatives
    ]
    incremental, _, _ = harness.run_schedule(
        schedule=harness.SCHEDULES["large_chronological_chunks"],
        sources=sources,
        staging_root=tmp_path / "incremental_collector",
        state_root=tmp_path / "incremental_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    batch, metrics, _ = harness.run_clean_canonical_batch(
        data_root=physical,
        batch_root=tmp_path / "batch",
        stack_config_path=stack_config,
        inventory_config_path=inventory_config,
        sessions=sessions,
    )
    projected = harness.project_incremental_fallback(
        incremental, metrics["intraday_fallback_sessions"]
    )
    a_rows = harness.component_rows(projected)
    b_rows = harness.component_rows(batch)
    assert not a_rows["inventory"]
    assert not b_rows["inventory"]
    assert len(a_rows["intraday_inventory"]) == len(b_rows["intraday_inventory"]) > 0
    assert harness._row_counter(a_rows["intraday_inventory"]) == harness._row_counter(
        b_rows["intraday_inventory"]
    )
    assert harness._row_counter(
        a_rows["intraday_cross_layer_transitions"]
    ) == harness._row_counter(b_rows["intraday_cross_layer_transitions"])
    assert len(a_rows["partial_fixed_inventory"]) == len(
        b_rows["partial_fixed_inventory"]
    ) > 0
    assert harness._row_counter(
        a_rows["partial_fixed_inventory"]
    ) == harness._row_counter(b_rows["partial_fixed_inventory"])
    assert harness._row_counter(
        a_rows["partial_fixed_cross_layer_transitions"]
    ) == harness._row_counter(b_rows["partial_fixed_cross_layer_transitions"])


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


def test_gui_visual_authority_requires_reference_rows_but_allows_live_extensions() -> None:
    reference = {
        "gui_payload": {
            "2026-08-20": {
                "date": "2026-08-20",
                "price": {"fields": ["t", "i"], "rows": [["09:15", 57000]]},
                "inventory": {
                    "fields": ["evaluation_date", "horizon", "control_value"],
                    "rows": [["2026-08-20", "1D", 57000]],
                },
            }
        }
    }
    live_payload = {
        "date": "2026-08-20",
        "price": {
            "fields": ["t", "i", "f"],
            "rows": [["09:15", 57000, 57025], ["09:16", 57010, 57035]],
        },
        "inventory": {
            "fields": ["evaluation_date", "horizon", "control_value"],
            "rows": [
                ["2026-08-20", "1D", 57000],
                ["2026-08-20", "ID", 57025],
            ],
        },
    }
    live = {"gui_payload": {"2026-08-20": live_payload}}
    rows = harness.compare_gui_visual_authority(
        a_snapshot=live,
        b_snapshot=live,
        reference_snapshot=reference,
        reference_name="R6D",
    )
    assert all(row["status"] == "PASS" for row in rows)
    assert sum(int(row["permitted_live_extension_rows"]) for row in rows) == 4

    broken = json.loads(json.dumps(live))
    broken["gui_payload"]["2026-08-20"]["price"]["rows"][0][1] = 56999
    rows = harness.compare_gui_visual_authority(
        a_snapshot=broken,
        b_snapshot=live,
        reference_snapshot=reference,
        reference_name="R6D",
    )
    assert any(
        row["target"] == "incremental_a"
        and row["component"] == "price"
        and row["status"] == "FAIL"
        for row in rows
    )


def test_real_live_path_chunk_split_and_restart_equivalence(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    config = _config(tmp_path / "shadow.json")
    all_sources = harness.discover_sources(physical, sessions)
    sources = harness.discover_sources(
        physical, sessions, include_predecessors=False
    )
    live_relatives = {source.relative for source in sources}
    context_sources = [
        source for source in all_sources if source.relative not in live_relatives
    ]

    chunked, chunked_accounting, _ = harness.run_schedule(
        schedule=harness.SCHEDULES["large_chronological_chunks"],
        sources=sources,
        staging_root=tmp_path / "chunked_collector",
        state_root=tmp_path / "chunked_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    split, split_accounting, split_metrics = harness.run_schedule(
        schedule=harness.SCHEDULES["boundaries_inside_jsonl_lines"],
        sources=sources,
        staging_root=tmp_path / "split_collector",
        state_root=tmp_path / "split_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    restarted, restart_accounting, restart_metrics = harness.run_schedule(
        schedule=harness.Schedule("restart_fixture", (1,), restart_every=2),
        sources=sources,
        staging_root=tmp_path / "restart_collector",
        state_root=tmp_path / "restart_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    boundary, boundary_accounting, boundary_metrics = harness.run_schedule(
        schedule=harness.SCHEDULES["analytical_boundary_restarts"],
        sources=sources,
        staging_root=tmp_path / "boundary_collector",
        state_root=tmp_path / "boundary_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )

    assert all(row["status"] == "PASS" for row in chunked_accounting)
    assert all(row["status"] == "PASS" for row in split_accounting)
    assert all(row["status"] == "PASS" for row in restart_accounting)
    assert all(row["status"] == "PASS" for row in boundary_accounting)
    assert split_metrics["split_line_boundary_count"] > 0
    assert chunked["session_snapshots"][sessions[0]]["session_date"] == sessions[0]
    assert boundary_metrics["unexpected_staged_sessions"] == []
    assert boundary_metrics["dirty_sessions_after_seal"] == []
    assert restart_metrics["restart_count"] > 0
    assert boundary_metrics["analytical_boundary_restart_count"] == 1
    assert boundary_metrics["analytical_boundary_probe"]["measured"] is True
    assert boundary_metrics["analytical_boundary_probe"][
        "exactly_once_after_seal"
    ] is True
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, split, expected=None)
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, restarted, expected=None)
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, boundary, expected=None)
    )
    assert len(chunked["basis"]) >= 1
