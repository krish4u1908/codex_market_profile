from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
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


def test_participation_calculation_clock_is_not_masked_by_equivalence() -> None:
    row = {
        "event_id": "R6B3-TRANSITION-ONE",
        "transition_id": "R6B3-TRANSITION-ONE",
        "episode_id": "BDR1-2026-08-20-GREEN-001",
        "component": "FUTURES",
        "effective_timestamp": "2026-08-20T10:00:00+05:30",
        "calculation_timestamp": "2026-08-20T10:00:01+05:30",
        "new_state": "SUPPORTIVE",
    }
    changed = {
        **row,
        "calculation_timestamp": "2026-08-20T10:00:02+05:30",
    }
    incremental = {
        "participation_transitions": [row],
        "analytical_ledgers": {"participation_transitions": [row]},
    }
    batch = {
        "participation_transitions": [changed],
        "analytical_ledgers": {"participation_transitions": [changed]},
    }

    component = next(
        result for result in harness.compare_snapshots(
            incremental, batch, expected=None
        )
        if result["component"] == "participation_transitions"
    )
    ledger = next(
        result for result in harness.compare_analytical_ledgers(
            incremental, batch
        )
        if result["ledger"] == "participation_transitions"
    )
    assert component["status"] == "FAIL"
    assert ledger["status"] == "FAIL"
    assert harness.named_rows_semantic_hash(
        harness.component_rows(incremental)
    ) != harness.named_rows_semantic_hash(harness.component_rows(batch))
    assert harness.named_rows_semantic_hash(
        harness.analytical_ledger_rows(incremental)
    ) != harness.named_rows_semantic_hash(
        harness.analytical_ledger_rows(batch)
    )


def test_clean_batch_ledgers_project_only_immutable_event_fields() -> None:
    snapshot = {
        "episodes": [{
            "episode_id": "BDR1-2026-08-20-GREEN-001",
            "evaluation_date": "2026-08-20",
            "colour": "GREEN",
            "candidate_start_timestamp": "2026-08-20T10:00:00+05:30",
            "confirmation_timestamp": "2026-08-20T10:01:00+05:30",
            "episode_end_timestamp": "2026-08-20T10:05:00+05:30",
        }],
        "lifecycle": [{
            "record_id": "R6B2R-ONE",
            "episode_id": "BDR1-2026-08-20-GREEN-001",
            "evaluation_date": "2026-08-20",
            "state": "DIVERGENCE_DETECTED",
            "previous_state": "NEUTRAL",
            "state_entry_timestamp": "2026-08-20T10:01:00+05:30",
            "state_exit_timestamp": "2026-08-20T10:02:00+05:30",
        }],
        "dependencies": [],
        "inventory": [],
        "participation_transitions": [],
        "cross_layer_transitions": [],
        "availability_detail": {},
    }
    ledgers = harness.build_batch_analytical_ledgers(snapshot)
    confirmation = ledgers["divergence_confirmations"][0]
    lifecycle = ledgers["lifecycle_transitions"][0]
    assert "episode_end_timestamp" not in confirmation
    assert "state_exit_timestamp" not in lifecycle
    assert confirmation["confirmation_timestamp"].endswith("+05:30")
    assert lifecycle["state_entry_timestamp"].endswith("+05:30")


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


def test_availability_comparison_uses_post_fallback_public_contract() -> None:
    session = "2026-08-19"
    detail = {
        "overall_state": "LIVE_INTRADAY_ONLY",
        "market_display_enabled": True,
        "divergence_state": "AVAILABLE",
        "participation_state": "AVAILABLE",
        "available_horizons": ["ID"],
        "unavailable_horizons": ["1D", "2D", "3D"],
        "layers": {
            "ID": {"state": "AVAILABLE", "reason": "FRESH_SYNCHRONIZED_MARKET"},
            "1D": {
                "state": "INSUFFICIENT_PRIOR_SESSIONS",
                "reason": "INSUFFICIENT_PRIOR_SESSIONS",
            },
        },
    }
    live = {
        # This is the real incremental-A shape: its public operational contract
        # is already stored in ``availability`` and has no clean-B auxiliary.
        "availability": [{"session_date": session, **detail}],
    }
    clean_batch = {
        # The frozen inventory engine keeps this pre-fallback eligibility table
        # for audit.  It must not override the rebuilt public availability.
        "availability": [
            {
                "evaluation_date": session,
                "horizon": "ID",
                "state": "INCOMPLETE_SESSION",
                "reason": "NO_MARKET_DATA",
            }
        ],
        "availability_detail": {session: detail},
    }

    comparison = harness.compare_snapshots(live, clean_batch, expected=None)
    availability = next(
        row for row in comparison if row["component"] == "availability_states"
    )
    assert availability["status"] == "PASS"
    assert availability["incremental_a_count"] == availability["batch_b_count"] == 2

    clean_batch["availability_detail"] = {
        session: {**detail, "overall_state": "UNAVAILABLE"}
    }
    comparison = harness.compare_snapshots(live, clean_batch, expected=None)
    availability = next(
        row for row in comparison if row["component"] == "availability_states"
    )
    assert availability["status"] == "FAIL"

    clean_batch["availability_detail"] = {
        session: {
            **detail,
            "layers": {
                **detail["layers"],
                "1D": {"state": "AVAILABLE", "reason": "RAW_ACCEPTED_SOURCE_CHAIN"},
            },
        }
    }
    comparison = harness.compare_snapshots(live, clean_batch, expected=None)
    availability = next(
        row for row in comparison if row["component"] == "availability_states"
    )
    assert availability["status"] == "FAIL"


def test_reference_availability_uses_historical_material_surface() -> None:
    session = "2026-08-20"
    common = {
        "evaluation_date": session,
        "overall_state": "LIVE_FULL_CONTEXT",
        "market_display_enabled": True,
        "divergence_state": "AVAILABLE",
        "participation_state": "AVAILABLE",
        "available_horizons": "1D|2D|3D|ID",
        "unavailable_horizons": "",
    }
    canonical_availability = [
        {
            **common,
            "horizon": horizon,
            "availability_state": "AVAILABLE",
            "availability_reason": (
                "RAW_CONTINUITY_VERIFIED"
                if horizon == "ID"
                else "RAW_ACCEPTED_SOURCE_CHAIN"
            ),
        }
        for horizon in ("1D", "2D", "3D", "ID")
    ]
    operational_stale = {
        "session_date": session,
        "overall_state": "STALE_PARTIAL",
        "market_display_enabled": True,
        "divergence_state": "STALE_DATA",
        "participation_state": "SUSPENDED_REQUIRED_INPUT_UNAVAILABLE",
        "available_horizons": "1D|2D|3D",
        "unavailable_horizons": "ID",
        "layers": {
            "1D": {"state": "AVAILABLE", "reason": "CACHED_RAW_PRIOR_CONTEXT"},
            "2D": {"state": "AVAILABLE", "reason": "CACHED_RAW_PRIOR_CONTEXT"},
            "3D": {"state": "AVAILABLE", "reason": "CACHED_RAW_PRIOR_CONTEXT"},
            "ID": {"state": "STALE_DATA", "reason": "MARKET_INPUT_STALE_OR_MISSING"},
        },
    }
    incremental = {
        "availability": [operational_stale],
        "inventory": [
            {"evaluation_date": session, "horizon": horizon}
            for horizon in ("1D", "2D", "3D", "ID")
        ],
        "basis": [{"evaluation_date": session, "validity_status": "VALID"}],
        "participation_dense": [{"evaluation_date": session}],
    }
    batch = {
        "availability": canonical_availability,
        # Reference comparison must ignore this operational auxiliary; primary
        # compare_snapshots coverage above proves that it remains authoritative
        # for live A/B equivalence.
        "availability_detail": {session: operational_stale},
    }
    reference = {"availability": canonical_availability}

    rows = harness.compare_reference_snapshot(
        a_snapshot=incremental,
        b_snapshot=batch,
        reference_snapshot=reference,
        reference_name="R6C2R_REFERENCE_C",
        components=("availability_states",),
    )
    assert len(rows) == 2
    assert all(row["status"] == "PASS" for row in rows)

    incremental["participation_dense"] = []
    rows = harness.compare_reference_snapshot(
        a_snapshot=incremental,
        b_snapshot=batch,
        reference_snapshot=reference,
        reference_name="R6C2R_REFERENCE_C",
        components=("availability_states",),
    )
    assert next(row for row in rows if row["target"] == "incremental_a")[
        "status"
    ] == "FAIL"
    assert next(row for row in rows if row["target"] == "batch_b")["status"] == "PASS"

    incremental["participation_dense"] = [{"evaluation_date": session}]
    incremental["inventory"] = [
        row for row in incremental["inventory"] if row["horizon"] != "ID"
    ]
    rows = harness.compare_reference_snapshot(
        a_snapshot=incremental,
        b_snapshot=batch,
        reference_snapshot=reference,
        reference_name="R6C2R_REFERENCE_C",
        components=("availability_states",),
    )
    assert next(row for row in rows if row["target"] == "incremental_a")[
        "status"
    ] == "FAIL"
    assert next(row for row in rows if row["target"] == "batch_b")["status"] == "PASS"

    incremental["inventory"].append(
        {"evaluation_date": session, "horizon": "ID"}
    )
    changed_batch = {
        **batch,
        "availability": json.loads(json.dumps(canonical_availability)),
    }
    changed_batch["availability"][0]["availability_state"] = "INCOMPLETE_RAW_DATA"
    rows = harness.compare_reference_snapshot(
        a_snapshot=incremental,
        b_snapshot=changed_batch,
        reference_snapshot=reference,
        reference_name="R6C2R_REFERENCE_C",
        components=("availability_states",),
    )
    assert next(row for row in rows if row["target"] == "incremental_a")[
        "status"
    ] == "PASS"
    assert next(row for row in rows if row["target"] == "batch_b")["status"] == "FAIL"

    with pytest.raises(
        ValueError, match="canonical reference availability must be a nonempty"
    ):
        harness.compare_reference_snapshot(
            a_snapshot=incremental,
            b_snapshot={**batch, "availability": []},
            reference_snapshot=reference,
            reference_name="R6C2R_REFERENCE_C",
            components=("availability_states",),
        )

    with pytest.raises(
        ValueError, match="canonical reference availability must be a nonempty"
    ):
        harness.compare_reference_snapshot(
            a_snapshot=incremental,
            b_snapshot={
                **batch,
                "availability": [*canonical_availability, operational_stale],
            },
            reference_snapshot=reference,
            reference_name="R6C2R_REFERENCE_C",
            components=("availability_states",),
        )

    with pytest.raises(
        ValueError, match="incremental reference availability must be a nonempty"
    ):
        harness.compare_reference_snapshot(
            a_snapshot={
                **incremental,
                "availability": [operational_stale, canonical_availability[0]],
            },
            b_snapshot=batch,
            reference_snapshot=reference,
            reference_name="R6C2R_REFERENCE_C",
            components=("availability_states",),
        )

    with pytest.raises(
        ValueError, match="canonical reference availability must be a nonempty"
    ):
        harness.compare_reference_snapshot(
            a_snapshot=incremental,
            b_snapshot=batch,
            reference_snapshot={"availability": []},
            reference_name="R6C2R_REFERENCE_C",
            components=("availability_states",),
        )


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


def test_raw_projection_hard_refuses_malformed_candidate_json(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    source = physical / "raw/2026-08-20/events_09.jsonl"
    source.write_bytes(source.read_bytes() + b'{"received_at":"broken","message":{"symbol":"NSE:NIFTYBANK-INDEX"}\n')
    source_hash = harness._sha256_file(source)

    with pytest.raises(ValueError, match="malformed candidate JSON records: 1"):
        harness.build_raw_projection(
            data_root=physical,
            projection_root=tmp_path / "malformed_projection",
            sessions=sessions,
        )

    assert harness._sha256_file(source) == source_hash


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


def test_failed_schedule_retains_bounded_row_free_ledger_diagnostic(
    tmp_path: Path,
) -> None:
    def snapshot(rows):
        ledgers = {name: [] for name in harness.MATERIAL_LEDGER_NAMES}
        ledgers["lifecycle_transitions"] = rows
        return {"analytical_ledgers": ledgers}

    canonical = snapshot([
        {
            "event_id": "L-STABLE",
            "state": "ACTIVE",
            "raw_source_references": "SENSITIVE_CANONICAL_SOURCE",
        }
    ])
    schedule = snapshot([
        {
            "event_id": "L-STABLE",
            "state": "EXPIRED_OR_UNRESOLVED",
            "raw_source_references": "SENSITIVE_SCHEDULE_SOURCE_A",
        },
        {
            "event_id": "L-GHOST",
            "state": "EXPIRED_OR_UNRESOLVED",
            "raw_source_references": "SENSITIVE_SCHEDULE_SOURCE_B",
        },
    ])
    run_root = tmp_path / "schedule"
    run_root.mkdir()
    snapshot_path = run_root / "snapshot.json"
    snapshot_path.write_text("large snapshot placeholder")

    summary = harness.retain_bounded_ledger_differences(
        run_root, canonical, schedule
    )
    snapshot_path.unlink()

    assert not snapshot_path.exists()
    retained = run_root / "ledger_difference_summary.json"
    assert retained.is_file()
    assert summary["difference_count"] == 3
    assert summary["differing_ledger_count"] == 1
    ledger = summary["ledgers"][0]
    assert ledger["ledger"] == "lifecycle_transitions"
    assert ledger["canonical_only_count"] == 1
    assert ledger["schedule_only_count"] == 2
    assert {row["event_id"] for row in ledger["schedule_only"]} == {
        "L-STABLE", "L-GHOST",
    }
    serialized = retained.read_text()
    assert "SENSITIVE_" not in serialized
    assert "raw_source_references" not in serialized


def test_named_schedule_cannot_pass_when_adversary_was_not_exercised() -> None:
    base = {
        "analytical_semantic_sha256": "abc",
        "analytical_ledgers_sha256": "ledger",
        "source_json_records": 10,
        "exposed_records": 10,
        "poll_calls_by_harness": 1,
        "analytical_refusals": 0,
    }
    rows = harness.scheduling_comparison(
        base,
        [
            ("boundaries_inside_jsonl_lines", dict(base)),
            (
                "empty_repeated_polls",
                {**base, "explicit_empty_poll_count": 20},
            ),
        ],
    )
    assert rows[0]["status"] == "FAIL"
    assert "CONFIGURED_INSIDE_LINE_BOUNDARIES_NOT_MEASURED" in rows[0][
        "schedule_exercise_failures"
    ]
    assert rows[1]["status"] == "PASS"


def test_periodic_refresh_plan_is_session_local_and_asymmetric() -> None:
    sources = [
        harness.SourceFile(
            Path(f"/source/{stream}/{session}/{name}"),
            Path(f"{stream}/{session}/{name}"),
            1,
            records,
            True,
            records,
        )
        for session, values in (
            ("2026-08-19", (("raw", "events.jsonl", 90), ("oi", "oi.jsonl", 9))),
            ("2026-08-20", (("raw", "events.jsonl", 12), ("oi", "oi.jsonl", 3))),
        )
        for stream, name, records in values
    ]
    assert harness._per_session_refresh_thresholds(sources, 2) == (
        {
            "session_date": "2026-08-19",
            "session_generation": 1,
            "session_record_ordinal": 33,
            "session_record_count": 99,
        },
        {
            "session_date": "2026-08-19",
            "session_generation": 2,
            "session_record_ordinal": 66,
            "session_record_count": 99,
        },
        {
            "session_date": "2026-08-20",
            "session_generation": 1,
            "session_record_ordinal": 5,
            "session_record_count": 15,
        },
        {
            "session_date": "2026-08-20",
            "session_generation": 2,
            "session_record_ordinal": 10,
            "session_record_count": 15,
        },
    )

    targets = {
        (str(row["session_date"]), int(row["session_record_ordinal"])): row
        for row in harness._per_session_refresh_thresholds(sources, 2)
    }
    seen: Counter[str] = Counter()
    bound = []
    for global_ordinal, session in enumerate(
        (
            *("2026-08-20" for _ in range(5)),
            *("2026-08-19" for _ in range(66)),
            *("2026-08-20" for _ in range(5)),
            *("2026-08-19" for _ in range(33)),
            *("2026-08-20" for _ in range(5)),
        ),
        start=1,
    ):
        value = harness._bind_analytical_refresh_target(
            targets,
            seen,
            source_session=session,
            global_record_ordinal=global_ordinal,
        )
        if value is not None:
            bound.append(value)
    assert [
        (row["session_date"], row["session_record_ordinal"], row["global_record_ordinal"])
        for row in bound
    ] == [
        ("2026-08-20", 5, 5),
        ("2026-08-19", 33, 38),
        ("2026-08-19", 66, 71),
        ("2026-08-20", 10, 76),
    ]


def test_refresh_closure_coverage_is_opportunity_aware() -> None:
    snapshot = {
        "session_snapshots": {
            "2026-08-20": {
                "episodes": [
                    {
                        "episode_id": "E1",
                        "confirmation_timestamp": "2026-08-20T10:00:00+05:30",
                        "episode_end_timestamp": "2026-08-20T10:05:00+05:30",
                    },
                    {
                        "episode_id": "ACTIVE",
                        "confirmation_timestamp": "2026-08-20T10:07:00+05:30",
                        "episode_end_timestamp": None,
                    },
                ],
                "lifecycle": [
                    {
                        "record_id": "L1",
                        "state_entry_timestamp": "2026-08-20T10:00:00+05:30",
                        "state_exit_timestamp": "2026-08-20T10:04:00+05:30",
                    },
                    {
                        "record_id": "ACTIVE-L",
                        "state_entry_timestamp": "2026-08-20T10:07:00+05:30",
                        "state_exit_timestamp": None,
                    },
                ],
            }
        }
    }
    early = {
            "session_date": "2026-08-20",
            "evidence_cutoff_timestamp": "2026-08-20T10:02:00+05:30",
            "episodes": {"E1": "2026-08-20T10:02:00+05:30"},
            "lifecycle": {"L1": ""},
    }
    finalization_only = harness._analytical_refresh_closure_coverage(
        [early],
        snapshot,
    )
    assert finalization_only[
        "analytical_refresh_episode_boundary_opportunity_ids"
    ] == []
    assert finalization_only[
        "analytical_refresh_episode_boundary_finalization_only_ids"
    ] == ["E1"]
    assert finalization_only[
        "analytical_refresh_lifecycle_boundary_finalization_only_ids"
    ] == ["L1"]

    later = {
        "session_date": "2026-08-20",
        "evidence_cutoff_timestamp": "2026-08-20T10:06:00+05:30",
        "episodes": {"E1": "2026-08-20T10:05:00+05:30"},
        "lifecycle": {"L1": "2026-08-20T10:04:00+05:30"},
    }
    measured = harness._analytical_refresh_closure_coverage(
        [early, later], snapshot
    )
    assert measured["analytical_refresh_episode_boundary_opportunity_ids"] == [
        "E1"
    ]
    assert measured["analytical_refresh_episode_boundary_observed_ids"] == [
        "E1"
    ]
    assert measured[
        "analytical_refresh_lifecycle_boundary_opportunity_ids"
    ] == ["L1"]
    assert measured["analytical_refresh_lifecycle_boundary_observed_ids"] == [
        "L1"
    ]

    missed = harness._analytical_refresh_closure_coverage(
        [
            early,
            {
                **later,
                "episodes": {"E1": "2026-08-20T10:03:00+05:30"},
                "lifecycle": {"L1": ""},
            },
        ],
        snapshot,
    )
    assert missed["analytical_refresh_episode_boundary_missing_ids"] == ["E1"]
    assert missed["analytical_refresh_lifecycle_boundary_missing_ids"] == ["L1"]

    not_applicable = harness._analytical_refresh_closure_coverage([], snapshot)
    assert not_applicable["analytical_refresh_episode_boundary_status"] == (
        "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
    )
    assert not_applicable["analytical_refresh_lifecycle_boundary_status"] == (
        "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
    )


def test_every_configured_schedule_predicate_is_exact() -> None:
    records = 1000
    variable_count, variable_hash = harness.expected_record_group_sequence(
        records, harness.SCHEDULES["deterministic_variable_chunks"].line_groups
    )
    base = {
        "source_json_records": records,
        "exposed_records": records,
        "poll_calls_by_harness": records,
        "source_files": 2,
        "analytical_refusals": 0,
    }
    refresh_plan = [
        {
            "session_date": session,
            "session_generation": generation,
            "session_record_ordinal": local,
            "session_record_count": 500,
            "global_record_ordinal": prefix + local,
        }
        for session, prefix in (("2026-08-19", 0), ("2026-08-20", 500))
        for generation, local in ((1, 166), (2, 333))
    ]
    refresh_trace = [
        {
            **row,
            "exact_threshold_discharge": True,
            "distinct_poll_generation": True,
            "target_was_dirty": True,
            "flush_returned_target": True,
            "accepted_observation_count_advanced": True,
            "causal_evidence_cutoff_advanced": True,
            "valid_basis_cutoff_advanced": True,
        }
        for row in refresh_plan
    ]
    passing = {
        "original_source_chunks": {
            **base,
            "original_source_files_staged_before_first_poll": 2,
            "maximum_exposure_bytes": 100,
            "source_sizes_by_relative": {"raw/file": 1000, "oi/file": 500},
            "original_checkpoint_chunk_counts": {"raw/file": 10, "oi/file": 5},
            "original_checkpoint_delta_bytes": {"raw/file": 1000, "oi/file": 500},
            "original_source_chunk_count": 15,
            "original_checkpoint_delta_oversize_count": 0,
        },
        "one_record_per_increment": {
            **base,
            "record_group_sizes_exercised": [1],
            "record_increment_count": records,
        },
        "deterministic_variable_chunks": {
            **base,
            "record_group_sizes_exercised": [1, 2, 3, 5, 7, 11, 13, 17],
            "record_increment_count": variable_count,
            "record_group_sequence_sha256": variable_hash,
        },
        "boundaries_inside_jsonl_lines": {**base, "split_line_boundary_count": 17},
        "empty_repeated_polls": {**base, "explicit_empty_poll_count": 34},
        "multiple_checkpoint_restarts": {**base, "checkpoint_restart_count": 7},
        "hourly_file_rotation": {
            **base,
            "expected_hourly_rotation_boundaries": 2,
            "hourly_rotation_boundary_count": 2,
        },
        "large_chronological_chunks": {
            **base,
            "record_group_sizes_exercised": [1000],
            "maximum_exposure_bytes": 1_000_000,
            "maximum_record_group_bytes": 900_000,
            "analytical_refresh_events_per_session": 2,
            "analytical_refresh_evaluation_session_count": 2,
            "analytical_refresh_evaluation_sessions": [
                "2026-08-19", "2026-08-20",
            ],
            "analytical_refresh_expected_count": 4,
            "analytical_refresh_plan": refresh_plan,
            "analytical_refresh_trace": refresh_trace,
            "analytical_refresh_recomputed_target_sessions": [
                "2026-08-19", "2026-08-20",
            ],
            "analytical_refresh_flush_count": 4,
            "analytical_refresh_nonempty_count": 4,
            "analytical_refresh_repeat_session_count": 2,
            "analytical_refresh_episode_end_update_count": 0,
            "analytical_refresh_lifecycle_exit_update_count": 0,
            "analytical_refresh_episode_boundary_opportunity_count": 0,
            "analytical_refresh_episode_boundary_observed_count": 0,
            "analytical_refresh_episode_boundary_opportunity_ids": [],
            "analytical_refresh_episode_boundary_observed_ids": [],
            "analytical_refresh_episode_boundary_missing_ids": [],
            "analytical_refresh_episode_boundary_finalization_only_ids": [],
            "analytical_refresh_episode_boundary_status": (
                "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
            ),
            "analytical_refresh_lifecycle_boundary_opportunity_ids": [],
            "analytical_refresh_lifecycle_boundary_observed_ids": [],
            "analytical_refresh_lifecycle_boundary_missing_ids": [],
            "analytical_refresh_lifecycle_boundary_finalization_only_ids": [],
            "analytical_refresh_lifecycle_boundary_opportunity_count": 0,
            "analytical_refresh_lifecycle_boundary_observed_count": 0,
            "analytical_refresh_lifecycle_boundary_status": (
                "NOT_APPLICABLE_NO_CAUSAL_REFRESH_BOUNDARY"
            ),
            "analytical_refresh_timestamp_backdating": 0,
            "analytical_refresh_duplicate_analytical_ids": 0,
            "analytical_refresh_future_joins": 0,
            "analytical_refresh_synchronization_tolerance_violations": 0,
        },
    }
    for name, seal in passing.items():
        assert harness.schedule_exercise_failures(name, seal) == [], name
    for name, seal in passing.items():
        broken = dict(seal)
        if name == "original_source_chunks":
            broken["original_checkpoint_delta_bytes"] = {
                "raw/file": 999,
                "oi/file": 500,
            }
        elif name == "one_record_per_increment":
            broken["record_increment_count"] -= 1
        elif name == "deterministic_variable_chunks":
            broken["record_group_sequence_sha256"] = "wrong"
        elif name == "boundaries_inside_jsonl_lines":
            broken["split_line_boundary_count"] = 16
        elif name == "empty_repeated_polls":
            broken["explicit_empty_poll_count"] = 33
        elif name == "multiple_checkpoint_restarts":
            broken["checkpoint_restart_count"] = 6
        elif name == "hourly_file_rotation":
            broken["hourly_rotation_boundary_count"] = 1
        else:
            broken["analytical_refresh_flush_count"] -= 1
        assert harness.schedule_exercise_failures(name, broken), name
    remainder = {
        **passing["one_record_per_increment"],
        "causal_checkpoint_remainders_after_drain": 1,
    }
    assert "CAUSAL_CHECKPOINT_REMAINDER_AFTER_DRAIN" in (
        harness.schedule_exercise_failures("one_record_per_increment", remainder)
    )

    large = passing["large_chronological_chunks"]
    assert harness.schedule_exercise_failures(
        "large_chronological_chunks", large
    ) == []
    for field in (
        "exact_threshold_discharge",
        "distinct_poll_generation",
        "target_was_dirty",
        "flush_returned_target",
        "accepted_observation_count_advanced",
        "causal_evidence_cutoff_advanced",
        "valid_basis_cutoff_advanced",
    ):
        broken_trace = [dict(row) for row in refresh_trace]
        broken_trace[0][field] = False
        failures = harness.schedule_exercise_failures(
            "large_chronological_chunks",
            {**large, "analytical_refresh_trace": broken_trace},
        )
        assert "PERIODIC_ANALYTICAL_REFRESH_CAUSAL_TRACE_FAILED" in failures
    tampered_plan = [dict(row) for row in refresh_plan]
    tampered_plan[0]["session_generation"] = 2
    assert "PER_SESSION_ANALYTICAL_REFRESH_PLAN_STRUCTURE_INVALID" in (
        harness.schedule_exercise_failures(
            "large_chronological_chunks",
            {
                **large,
                "analytical_refresh_plan": tampered_plan,
                "analytical_refresh_trace": [
                    {**row, "session_generation": 2}
                    if index == 0 else row
                    for index, row in enumerate(refresh_trace)
                ],
            },
        )
    )
    assert "PERIODIC_ANALYTICAL_RECOMPUTATION_NOT_EXERCISED" in (
        harness.schedule_exercise_failures(
            "large_chronological_chunks",
            {
                **large,
                "analytical_refresh_recomputed_target_sessions": [
                    "2026-08-19"
                ],
            },
        )
    )
    missed_episode_boundary = {
        **large,
        "analytical_refresh_episode_boundary_opportunity_ids": ["E1"],
        "analytical_refresh_episode_boundary_observed_ids": [],
        "analytical_refresh_episode_boundary_missing_ids": ["E1"],
        "analytical_refresh_episode_boundary_opportunity_count": 1,
        "analytical_refresh_episode_boundary_observed_count": 0,
        "analytical_refresh_episode_boundary_status": "EXERCISED",
    }
    assert "PERIODIC_EPISODE_BOUNDARY_UPDATE_MISSING" in (
        harness.schedule_exercise_failures(
            "large_chronological_chunks", missed_episode_boundary
        )
    )
    covered_episode_boundary = {
        **missed_episode_boundary,
        "analytical_refresh_episode_boundary_observed_ids": ["E1"],
        "analytical_refresh_episode_boundary_missing_ids": [],
        "analytical_refresh_episode_boundary_observed_count": 1,
    }
    assert harness.schedule_exercise_failures(
        "large_chronological_chunks", covered_episode_boundary
    ) == []
    inconsistent_boundary_status = {
        **large,
        "analytical_refresh_episode_boundary_status": "EXERCISED",
    }
    assert "PERIODIC_EPISODE_BOUNDARY_STATUS_INCONSISTENT" in (
        harness.schedule_exercise_failures(
            "large_chronological_chunks", inconsistent_boundary_status
        )
    )
    missed_large_target = {
        **large,
        "record_group_sizes_exercised": [1],
        "maximum_record_group_bytes": 1,
    }
    assert "LARGE_CHRONOLOGICAL_TARGET_NOT_MEASURED" in (
        harness.schedule_exercise_failures(
            "large_chronological_chunks", missed_large_target
        )
    )
    transient_causality_failure = {
        **large,
        "analytical_refresh_timestamp_backdating": 1,
        "analytical_refresh_duplicate_analytical_ids": 1,
        "analytical_refresh_future_joins": 1,
        "analytical_refresh_synchronization_tolerance_violations": 1,
    }
    transient_failures = harness.schedule_exercise_failures(
        "large_chronological_chunks", transient_causality_failure
    )
    assert "PERIODIC_TIMESTAMP_BACKDATING_DETECTED" in transient_failures
    assert (
        "PERIODIC_DUPLICATE_ANALYTICAL_ID_DETECTED" in transient_failures
    )
    assert "PERIODIC_FUTURE_JOIN_DETECTED" in transient_failures
    assert (
        "PERIODIC_SYNCHRONIZATION_TOLERANCE_VIOLATION"
        in transient_failures
    )


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
                "classification": "PERMITTED_OBSERVED_RAW_OPEN",
                "evidence_source": "PYTHON_SYS_AUDIT_HOOK_OPEN",
                "observed_open_count": 1,
            },
            {
                "run": "batch_b",
                "path": "/tmp/b/raw/events.jsonl",
                "classification": "PERMITTED_RUNTIME_RAW_OPEN",
                "evidence_source": "LINUX_STRACE_SUCCESSFUL_READ_OPEN",
                "observed_open_count": 1,
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
                "evidence_source": "REPOSITORY_READER_FILE_OPEN_AUDIT",
                "observed_open_count": 1,
            }
        ]
    )
    assert refused["prohibited_rows"] == 1

    unmeasured = harness.runtime_open_audit_summary(
        [{"run": "batch_b", "path": "/tmp/unknown"}]
    )
    assert unmeasured["measured"] is False
    assert unmeasured["unmeasured_rows"] == 1


def test_runtime_open_recorder_observes_required_sources_and_prohibited_data(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source/raw/2026-08-20/events_09.jsonl"
    staged_root = tmp_path / "staged"
    staged_path = staged_root / "raw/2026-08-20/events_09.jsonl"
    _write_jsonl(source_path, [{"received_at": "2026-08-20T09:15:00+05:30"}])
    _write_jsonl(staged_path, [{"received_at": "2026-08-20T09:15:00+05:30"}])
    source = harness.SourceFile(
        source_path,
        Path("raw/2026-08-20/events_09.jsonl"),
        source_path.stat().st_size,
        1,
        True,
    )
    recorder = harness.RuntimeOpenRecorder()
    with recorder.recording("incremental_a"):
        source_path.read_bytes()
        staged_path.read_bytes()
    coverage = harness.required_schedule_open_coverage(
        recorder,
        scope="incremental_a",
        sources=[source],
        context_sources=[],
        staging_root=staged_root,
    )
    assert all(row["status"] == "PASS" for row in coverage)

    derived = tmp_path / "research/derived/table.csv"
    derived.parent.mkdir(parents=True)
    derived.write_text("derived\n")
    external = tmp_path / "ordinary_external.csv"
    external.write_text("external\n")
    with recorder.recording("batch_b"):
        derived.read_text()
        external.read_text()
        created = tmp_path / "created_not_read.csv"
        created.write_text("created,not-read\n")
    assert recorder.observed_count("batch_b", created) == 0
    rows = [
        *coverage,
        *recorder.audit_rows(
            scope="incremental_a",
            permitted_data_roots=(tmp_path / "source", staged_root),
            permitted_state_roots=(),
            repository=Path(__file__).resolve().parents[2],
        ),
        *recorder.audit_rows(
            scope="batch_b",
            permitted_data_roots=(),
            permitted_state_roots=(),
            repository=Path(__file__).resolve().parents[2],
        ),
    ]
    summary = harness.runtime_open_audit_summary(rows)
    assert summary["measured"] is True
    assert summary["prohibited_rows"] == 2


def test_child_strace_audits_every_raw_source_and_layers_generated_state(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    raw = data / "raw/2026-08-20/events_09.jsonl"
    oi = data / "oi/2026-08-20/oi_09.jsonl"
    _write_jsonl(raw, [{"received_at": "2026-08-20T09:15:00+05:30"}])
    _write_jsonl(oi, [{"received_at": "2026-08-20T09:15:00+05:30"}])
    generated = tmp_path / "batch/generated"
    intermediate = generated / "runs/stream_stack/native/basis.csv"
    intermediate.parent.mkdir(parents=True)
    intermediate.write_text("basis\n")
    traces = {
        name: tmp_path / f"traces/{name}.strace"
        for name in ("inventory", "stack", "layers")
    }
    for prefix, opened in (
        (traces["inventory"], raw),
        (traces["stack"], oi),
        (traces["layers"], intermediate),
    ):
        prefix.parent.mkdir(parents=True, exist_ok=True)
        (prefix.parent / f"{prefix.name}.123").write_text(
            f'openat(AT_FDCWD<{tmp_path}>, "{opened}", '
            f'O_RDONLY|O_CLOEXEC) = 3<{opened.resolve()}>\n'
        )
    rows = harness.child_open_audit_rows(
        traces=traces,
        data_root=data,
        generated_root=generated,
        repository=Path(__file__).resolve().parents[2],
        config_paths=(),
    )
    required = [row for row in rows if row.get("required_source_open")]
    assert len(required) == 2
    assert all(row["status"] == "PASS" for row in required)
    coverage = [
        row
        for row in rows
        if str(row.get("purpose", "")).startswith("REQUIRED_")
        and not row.get("required_source_open")
    ]
    assert {row["component"] for row in coverage} == {
        "inventory", "stack", "layers"
    }
    assert all(row["status"] == "PASS" for row in coverage)
    assert not any("PROHIBITED" in row["classification"] for row in rows)
    external = tmp_path / "outside/untrusted.csv"
    external.parent.mkdir(parents=True)
    external.write_text("derived\n")
    stack_trace = traces["stack"].parent / f"{traces['stack'].name}.123"
    with stack_trace.open("a") as handle:
        handle.write(
            f'openat(AT_FDCWD<{tmp_path}>, "{external}", '
            f'O_RDONLY|O_CLOEXEC) = 4<{external.resolve()}>\n'
        )
    refused = harness.child_open_audit_rows(
        traces=traces,
        data_root=data,
        generated_root=generated,
        repository=Path(__file__).resolve().parents[2],
        config_paths=(),
    )
    assert any("PROHIBITED" in row["classification"] for row in refused)

    malformed = tmp_path / "malformed.strace"
    malformed.write_text('openat(AT_FDCWD, "unterminated\n')
    with pytest.raises(ValueError, match="unparsed successful child open"):
        harness._parse_strace_read_opens(malformed, tmp_path)


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


def test_schedule_roots_are_exclusively_claimed(tmp_path: Path) -> None:
    staging = tmp_path / "schedule_collector"
    state = tmp_path / "schedule_state"
    harness._claim_schedule_roots(staging, state)
    assert staging.is_dir()
    assert state.is_dir()

    sentinel = staging / "existing-evidence"
    sentinel.write_text("preserve")
    with pytest.raises(ValueError, match="schedule staging root must not exist"):
        harness._claim_schedule_roots(staging, tmp_path / "unused_state")
    assert sentinel.read_text() == "preserve"
    with pytest.raises(ValueError, match="schedule staging root must not exist"):
        harness.run_schedule(
            schedule=harness.Schedule("root_collision", (1,)),
            sources=[],
            staging_root=staging,
            state_root=tmp_path / "unused_run_state",
            config_path=tmp_path / "not_read.json",
            sessions=(),
        )
    assert sentinel.read_text() == "preserve"

    existing_state = tmp_path / "existing_state"
    existing_state.mkdir()
    fresh_staging = tmp_path / "fresh_collector"
    with pytest.raises(ValueError, match="schedule state root must not exist"):
        harness._claim_schedule_roots(fresh_staging, existing_state)
    assert not fresh_staging.exists()


def test_drain_reports_exact_quarantined_source(tmp_path: Path) -> None:
    relative = Path("raw/2026-08-20/events_09.jsonl")
    staging = tmp_path / "collector"
    destination = staging / relative
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"{}\n")
    source = harness.SourceFile(
        source=tmp_path / "authority.jsonl",
        relative=relative,
        size=3,
        complete_rows=1,
        ends_with_newline=True,
    )

    class QuarantinedContext:
        checkpoints = {str(relative): {"offset": 0}}
        quarantined_sources = {
            str(relative): {"reason": "FILE_REPLACED"}
        }

        def poll(self, source_paths=None):
            return 0

    with pytest.raises(RuntimeError) as captured:
        harness._drain(QuarantinedContext(), [source], staging)
    assert str(captured.value) == (
        "checkpoint drain blocked by quarantined source: "
        "raw/2026-08-20/events_09.jsonl=FILE_REPLACED"
    )


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
    assert {row.get("evidence_source") for row in opens} == {
        "LINUX_STRACE_SUCCESSFUL_READ_OPEN"
    }
    assert not any("PROHIBITED" in row["classification"] for row in opens)
    required = [row for row in opens if row.get("required_source_open")]
    assert len(required) == len(harness.discover_sources(physical, sessions))
    assert all(row["status"] == "PASS" for row in required)
    component_coverage = {
        row["component"]: row
        for row in opens
        if row.get("purpose") in {
            "REQUIRED_CHILD_RAW_READ",
            "REQUIRED_LAYERS_GENERATED_STATE_READ",
        }
    }
    assert set(component_coverage) == {"inventory", "stack", "layers"}
    assert all(row["status"] == "PASS" for row in component_coverage.values())
    gate = harness.runtime_open_audit_summary(
        [
            {
                "run": "incremental_a",
                "path": str(physical),
                "classification": "PERMITTED_OBSERVED_RAW_OPEN",
                "evidence_source": "PYTHON_SYS_AUDIT_HOOK_OPEN",
                "observed_open_count": 1,
            },
            *opens,
        ]
    )
    assert gate == {
        "measured": True,
        "audited_rows": len(opens) + 1,
        "a_b_runtime_rows": len(opens) + 1,
        "unmeasured_rows": 0,
        "prohibited_rows": 0,
    }


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
    ledger_rows = harness.compare_analytical_ledgers(incremental, batch)
    assert {row["ledger"] for row in ledger_rows} == set(
        harness.MATERIAL_LEDGER_NAMES
    )
    assert all(row["status"] == "PASS" for row in ledger_rows)
    assert all(
        row["incremental_a_count"] == row["batch_b_expected_count"]
        for row in ledger_rows
    )
    gui_a = harness._gui_projection(incremental["gui_payload"][sessions[0]])
    gui_b = harness._gui_projection(batch["gui_payload"][sessions[0]])
    assert harness._row_counter(gui_a["display_metadata"]) == harness._row_counter(
        gui_b["display_metadata"]
    )
    assert harness._row_counter(
        gui_a["availability_instruments"]
    ) == harness._row_counter(gui_b["availability_instruments"])
    assert harness._row_counter(gui_a["counts"]) == harness._row_counter(
        gui_b["counts"]
    )


def test_intraday_fallback_uses_inventory_five_second_join(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    session = sessions[0]
    raw_path = physical / f"raw/{session}/events_09.jsonl"
    rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
    rows = [rows[0], rows[1], rows[3]]
    rows[1]["received_at"] = f"{session}T09:15:03.100000+05:30"
    rows[1]["event_time"] = f"{session}T09:15:03.090000+05:30"
    rows[2]["received_at"] = f"{session}T09:15:04.100000+05:30"
    rows[2]["event_time"] = f"{session}T09:15:04.090000+05:30"
    _write_jsonl(raw_path, rows)
    stack_config, inventory_config = _batch_configs(tmp_path, sessions)

    intraday, _, intraday_cross, _, fallback_sessions = (
        harness.build_intraday_inventory_fallback(
            data_root=physical,
            stack_config_path=stack_config,
            inventory_config_path=inventory_config,
            sessions=sessions,
            canonical_inventory=[],
        )
    )
    volume = [
        row for row in intraday
        if row["family"] == "BN_REF_FUT_VOLUME_VPOC"
    ]
    assert fallback_sessions == sessions
    assert len(volume) == 1
    assert volume[0]["eligible_observation_count"] == 1
    assert any(
        row["family"] == "BN_REF_FUT_VOLUME_VPOC"
        for row in intraday_cross
    )


def test_clean_b_terminal_null_receipt_advances_cutoff_not_valid_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = "2026-08-20"
    future = "NSE:BANKNIFTY26AUGFUT"
    base = pd.Timestamp(f"{session}T09:15:00+05:30")
    terminal = base + pd.Timedelta(seconds=30)
    market = pd.DataFrame(
        [
            {
                "symbol": "NSE:NIFTYBANK-INDEX",
                "receipt_timestamp": base,
                "last_price": 57_000.0,
            },
            {
                "symbol": future,
                "receipt_timestamp": base,
                "last_price": 57_025.0,
            },
            {
                "symbol": "NSE:NIFTYBANK-INDEX",
                "receipt_timestamp": base + pd.Timedelta(seconds=20),
                "last_price": None,
            },
        ]
    )
    oi = pd.DataFrame(
        [
            {
                "instrument_class": "future",
                "symbol": future,
                "oi_receipt_timestamp": base,
                "oi_close": 1000.0,
            },
            {
                "instrument_class": "future",
                "symbol": future,
                "oi_receipt_timestamp": base + pd.Timedelta(seconds=25),
                "oi_close": None,
            },
            {
                "instrument_class": "call",
                "symbol": "NSE:BANKNIFTY26AUG57000CE",
                "oi_receipt_timestamp": base,
                "oi_close": 500.0,
            },
            {
                "instrument_class": "call",
                "symbol": "NSE:BANKNIFTY26AUG57000CE",
                "oi_receipt_timestamp": terminal,
                "oi_close": None,
            },
            {
                "instrument_class": "put",
                "symbol": "NSE:BANKNIFTY26AUG57000PE",
                "oi_receipt_timestamp": base,
                "oi_close": 450.0,
            },
        ]
    )
    monkeypatch.setattr(harness.raw_reader, "load_market", lambda *_args, **_kwargs: market)
    monkeypatch.setattr(harness.raw_reader, "load_oi", lambda *_args, **_kwargs: oi)
    monkeypatch.setattr(
        harness.raw_reader,
        "select_contracts",
        lambda *_args, **_kwargs: (future, "2026-08-25", "2026-08-25"),
    )
    stack = tmp_path / "stack.json"
    stack.write_text(json.dumps({"index_symbol": "NSE:NIFTYBANK-INDEX"}))
    shadow = _config(tmp_path / "shadow.json")
    inventory_row = {
        "evaluation_date": session,
        "horizon": "ID",
        "family": "BN_REF_FUT_VOLUME_VPOC",
        "control_value": 57_000.0,
        "control_effective_timestamp": base.isoformat(),
    }
    snapshot = {"intraday_inventory": [inventory_row]}
    detail = harness.build_clean_batch_availability_detail(
        snapshot=snapshot,
        data_root=tmp_path / "unused",
        stack_config_path=stack,
        shadow_config_path=shadow,
        sessions=(session,),
    )[session]
    assert detail["evidence_cutoff_timestamp"] == terminal.isoformat()
    assert detail["reference_timestamp"] == terminal.isoformat()
    assert detail["index_state"] == "STALE_OR_MISSING"
    assert detail["futures_state"] == "STALE_OR_MISSING"
    assert detail["futures_oi_state"] == "AVAILABLE"
    assert detail["ce_state"] == "AVAILABLE"
    assert detail["receipt_ages_seconds"] == {
        "INDEX": 30.0,
        "FUTURES": 30.0,
        "FUTURES_OI": 30.0,
        "CE": 30.0,
        "PE": 30.0,
    }
    snapshot["availability_detail"] = {session: detail}
    snapshot["gui_payload"] = {session: {}}
    harness.rebuild_clean_gui_payload(snapshot, (session,))
    ledgers = harness.build_batch_analytical_ledgers(snapshot)
    assert ledgers["availability_transitions"]
    assert all(
        row["effective_timestamp"] == terminal.isoformat()
        for row in ledgers["availability_transitions"]
    )
    assert all(
        row["reason"] == "SESSION_AVAILABILITY_SEAL"
        for row in ledgers["availability_transitions"]
    )
    gui = harness._gui_projection(snapshot["gui_payload"][session])
    metadata = gui["display_metadata"][0]
    assert metadata["reference_timestamp"] == terminal.isoformat()
    assert metadata["evidence_cutoff_timestamp"] == terminal.isoformat()
    assert metadata["as_of_matches_availability_calculation"] is True
    assert harness.audit_invariants(snapshot)["gui_clock_contract_violations"] == 0


def test_rebuild_clean_gui_compacts_dense_resolution_like_live_callback() -> None:
    session = "2026-08-19"
    mechanisms = ("CONVERGENCE", "CONVERGENCE", "STALL", "STALL", "CONVERGENCE")
    snapshot = {
        "availability_detail": {
            session: {
                "calculation_timestamp": f"{session}T12:05:00+05:30",
                "evidence_cutoff_timestamp": f"{session}T12:05:00+05:30",
                "reference_timestamp": f"{session}T12:05:00+05:30",
                "layers": {},
            }
        },
        "resolution": [
            {
                "evaluation_date": session,
                "episode_id": "E1",
                "timestamp": f"{session}T09:15:0{ordinal}+05:30",
                "resolution_mechanism_native": mechanism,
            }
            for ordinal, mechanism in enumerate(mechanisms)
        ],
        "gui_payload": {session: {}},
    }

    harness.rebuild_clean_gui_payload(snapshot, (session,))

    payload = snapshot["gui_payload"][session]
    rows = harness._as_rows(payload["resolution_mechanisms"])
    assert [row["resolution_mechanism_native"] for row in rows] == [
        "CONVERGENCE",
        "STALL",
        "CONVERGENCE",
    ]
    assert payload["counts"]["resolution_mechanisms"] == 3


def test_rebuild_clean_gui_compacts_interleaved_episodes_independently() -> None:
    session = "2026-08-19"
    sequence = (
        ("E1", "CONVERGENCE"),
        ("E2", "STALL"),
        ("E1", "CONVERGENCE"),
        ("E2", "STALL"),
        ("E1", "STALL"),
        ("E2", "CONVERGENCE"),
    )
    snapshot = {
        "availability_detail": {
            session: {
                "calculation_timestamp": f"{session}T12:05:00+05:30",
                "evidence_cutoff_timestamp": f"{session}T12:05:00+05:30",
                "reference_timestamp": f"{session}T12:05:00+05:30",
                "layers": {},
            }
        },
        "resolution": [
            {
                "evaluation_date": session,
                "episode_id": episode,
                "timestamp": f"{session}T09:15:{ordinal:02d}+05:30",
                "resolution_mechanism_native": mechanism,
            }
            for ordinal, (episode, mechanism) in enumerate(sequence)
        ],
        "gui_payload": {session: {}},
    }

    harness.rebuild_clean_gui_payload(snapshot, (session,))

    rows = harness._as_rows(
        snapshot["gui_payload"][session]["resolution_mechanisms"]
    )
    assert [
        (row["episode_id"], row["resolution_mechanism_native"])
        for row in rows
    ] == [
        ("E1", "CONVERGENCE"),
        ("E2", "STALL"),
        ("E1", "STALL"),
        ("E2", "CONVERGENCE"),
    ]


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


def test_gui_component_gate_requires_public_contract_and_visible_rows() -> None:
    packed = {"fields": ["episode_id", "state"], "rows": [["E1", "ACTIVE"]]}
    contract = {
        "schema": "R6E_SESSION_PAYLOAD_V1",
        "classification": "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL",
    }
    a = {
        "gui_payload": {
            "2026-08-20": {**contract, "episodes": json.loads(json.dumps(packed))}
        }
    }
    b = {
        "gui_payload": {
            "2026-08-20": {**contract, "episodes": json.loads(json.dumps(packed))}
        }
    }
    reference = {
        "gui_payload": {
            "2026-08-20": {**contract, "episodes": json.loads(json.dumps(packed))}
        }
    }
    rows = harness.compare_reference_snapshot(
        a_snapshot=a,
        b_snapshot=b,
        reference_snapshot=reference,
        reference_name="R6D",
        components=("gui_visible_state",),
    )
    assert all(row["status"] == "PASS" for row in rows)
    b["gui_payload"]["2026-08-20"]["schema"] = "WRONG"
    rows = harness.compare_reference_snapshot(
        a_snapshot=a,
        b_snapshot=b,
        reference_snapshot=reference,
        reference_name="R6E",
        components=("gui_visible_state",),
    )
    assert next(row for row in rows if row["target"] == "batch_b")["status"] == "FAIL"
    b["gui_payload"]["2026-08-20"]["schema"] = contract["schema"]
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


def test_gui_visual_authority_compares_historical_availability_by_target_role() -> None:
    session = "2026-08-20"
    common = {
        "evaluation_date": session,
        "overall_state": "LIVE_FULL_CONTEXT",
        "market_display_enabled": True,
        "divergence_state": "AVAILABLE",
        "participation_state": "AVAILABLE",
        "available_horizons": "1D|2D|3D|ID",
        "unavailable_horizons": "",
    }
    canonical_availability = [
        {
            **common,
            "horizon": horizon,
            "availability_state": "AVAILABLE",
            "availability_reason": (
                "RAW_CONTINUITY_VERIFIED"
                if horizon == "ID"
                else "RAW_ACCEPTED_SOURCE_CHAIN"
            ),
        }
        for horizon in ("1D", "2D", "3D", "ID")
    ]
    operational_stale = {
        "session_date": session,
        "overall_state": "STALE_PARTIAL",
        "market_display_enabled": True,
        "divergence_state": "STALE_DATA",
        "participation_state": "SUSPENDED_REQUIRED_INPUT_UNAVAILABLE",
        "available_horizons": "1D|2D|3D",
        "unavailable_horizons": "ID",
        "layers": {
            horizon: {
                "state": "STALE_DATA" if horizon == "ID" else "AVAILABLE",
                "reason": (
                    "MARKET_INPUT_STALE_OR_MISSING"
                    if horizon == "ID"
                    else "CACHED_RAW_PRIOR_CONTEXT"
                ),
            }
            for horizon in ("1D", "2D", "3D", "ID")
        },
    }
    gui_payload = {
        "date": session,
        "availability": operational_stale,
    }
    incremental = {
        "availability": [operational_stale],
        "inventory": [
            {"evaluation_date": session, "horizon": horizon}
            for horizon in ("1D", "2D", "3D", "ID")
        ],
        "basis": [{"evaluation_date": session, "validity_status": "VALID"}],
        "participation_dense": [{"evaluation_date": session}],
        "gui_payload": {session: gui_payload},
    }
    batch = {
        "availability": canonical_availability,
        "gui_payload": {session: gui_payload},
    }
    reference = {
        "gui_payload": {
            session: {
                "date": session,
                "availability": canonical_availability,
            }
        }
    }

    rows = harness.compare_gui_visual_authority(
        a_snapshot=incremental,
        b_snapshot=batch,
        reference_snapshot=reference,
        reference_name="R6D_GUI",
    )
    availability = [row for row in rows if row["component"] == "availability"]
    assert len(availability) == 2
    assert all(row["status"] == "PASS" for row in availability)
    operational_rows = harness._gui_projection(gui_payload)["availability"]
    assert next(row for row in operational_rows if row["horizon"] == "ID")[
        "availability_state"
    ] == "STALE_DATA"

    incremental["participation_dense"] = []
    rows = harness.compare_gui_visual_authority(
        a_snapshot=incremental,
        b_snapshot=batch,
        reference_snapshot=reference,
        reference_name="R6D_GUI",
    )
    availability = [row for row in rows if row["component"] == "availability"]
    assert next(row for row in availability if row["target"] == "incremental_a")[
        "status"
    ] == "FAIL"
    assert next(row for row in availability if row["target"] == "batch_b")[
        "status"
    ] == "PASS"

    mixed_batch = {
        **batch,
        "availability": [*canonical_availability, operational_stale],
    }
    with pytest.raises(
        ValueError, match="canonical reference availability must be a nonempty"
    ):
        harness.compare_gui_visual_authority(
            a_snapshot=incremental,
            b_snapshot=mixed_batch,
            reference_snapshot=reference,
            reference_name="R6D_GUI",
        )


def test_real_live_path_chunk_split_and_restart_equivalence(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    session = sessions[0]
    raw_path = physical / f"raw/{session}/events_09.jsonl"
    raw_rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
    raw_rows.insert(
        2,
        {
            "received_at": f"{session}T09:15:00.250000+05:30",
            "event_time": f"{session}T09:15:00.240000+05:30",
            "message": {
                "symbol": "NSE:NIFTYBANK-INDEX",
                "ltp": 57_001.0,
                "vol_traded_today": 0,
            },
        },
    )
    _write_jsonl(raw_path, raw_rows)
    config = _config(tmp_path / "shadow.json")
    all_sources = harness.discover_sources(physical, sessions)
    sources = harness.discover_sources(
        physical, sessions, include_predecessors=False
    )
    live_relatives = {source.relative for source in sources}
    context_sources = [
        source for source in all_sources if source.relative not in live_relatives
    ]

    chunked, chunked_accounting, chunked_metrics = harness.run_schedule(
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
    one_record, one_record_accounting, one_record_metrics = harness.run_schedule(
        schedule=harness.SCHEDULES["one_record_per_increment"],
        sources=sources,
        staging_root=tmp_path / "one_record_collector",
        state_root=tmp_path / "one_record_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    middle_split, middle_split_accounting, middle_split_metrics = harness.run_schedule(
        schedule=harness.Schedule(
            "middle_split_fixture", (8192,), split_inside_lines=True, split_events=1
        ),
        sources=sources,
        staging_root=tmp_path / "middle_split_collector",
        state_root=tmp_path / "middle_split_state",
        config_path=config,
        sessions=sessions,
        context_sources=context_sources,
    )
    restarted, restart_accounting, restart_metrics = harness.run_schedule(
        # Restart after the raw candidate and the later Index row are visible.
        # The next increment changes only OI, so equality proves the unchanged
        # raw checkpoint remainder survives process recreation and is repolled.
        schedule=harness.Schedule("restart_fixture", (1,), restart_every=3),
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
    assert all(row["status"] == "PASS" for row in one_record_accounting)
    assert all(row["status"] == "PASS" for row in middle_split_accounting)
    assert all(row["status"] == "PASS" for row in restart_accounting)
    assert all(row["status"] == "PASS" for row in boundary_accounting)
    assert split_metrics["split_line_boundary_count"] > 0
    assert middle_split_metrics["split_line_boundary_count"] == 1
    assert middle_split_metrics["analytical_refusals"] == 0
    assert one_record_metrics["analytical_refusals"] == 0
    assert one_record_metrics["causal_backlog_path_repolls"] > 0
    assert one_record_metrics["maximum_causal_backlog_paths"] > 0
    assert one_record_metrics["causal_checkpoint_remainders_after_drain"] == 0
    assert harness.schedule_exercise_failures(
        "one_record_per_increment", one_record_metrics
    ) == []
    assert not any(
        str(row.get("reason", "")).startswith("OUT_OF_ORDER")
        for row in harness._as_rows(
            one_record.get("analytical_ledgers", {}).get(
                "refusals_data_quality", []
            )
        )
    )
    assert chunked_metrics["analytical_refresh_flush_count"] == 2
    # This compact ordering fixture intentionally leaves one refresh behind a
    # selection barrier; the real-schedule gate separately requires every
    # planned refresh target to compute on the complete focused/full inputs.
    assert chunked_metrics["analytical_refresh_nonempty_count"] == 1
    assert chunked["session_snapshots"][sessions[0]]["session_date"] == sessions[0]
    assert boundary_metrics["unexpected_staged_sessions"] == []
    assert boundary_metrics["dirty_sessions_after_seal"] == []
    assert restart_metrics["restart_count"] > 0
    assert restart_metrics["causal_backlog_path_repolls"] > 0
    assert restart_metrics["maximum_causal_backlog_paths"] > 0
    assert restart_metrics["causal_checkpoint_remainders_after_drain"] == 0
    assert restart_metrics["analytical_refusals"] == 0
    probe = boundary_metrics["analytical_boundary_probe"]
    assert probe["measured"] is True
    assert boundary_metrics["analytical_boundary_restart_count"] == probe[
        "restart_count"
    ] == len(probe["events"])
    assert probe["restart_count"] > 1
    assert probe["crash_covered_ledgers"] == probe["material_ledgers_with_rows"]
    assert probe["exactly_once_after_seal"] is True
    assert all(
        event["durable_occurrences_before_restart"] == 1
        and event["durable_occurrences_after_restart"] == 1
        and event["occurrences_after_retry_and_seal"] == 1
        and event["exactly_once_after_seal"] is True
        for event in probe["events"]
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, split, expected=None)
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, one_record, expected=None)
    )
    assert harness.analytical_ledger_rows(chunked) == (
        harness.analytical_ledger_rows(one_record)
    )
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(chunked, middle_split, expected=None)
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


def test_checkpoint_lagging_hourly_peer_is_repolled_before_later_receipt(
    tmp_path: Path,
) -> None:
    """A visible partial prefix cannot be omitted when a later hour changes.

    The blank rows model a byte-exact raw projection: they preserve physical
    source coordinates but are not schedule records. With a 512-byte read
    bound, the second Index record remains beyond the durable raw checkpoint
    after its one-record increment. Polling only the newly introduced OI hour
    would publish 09:15:00.600 before that visible 09:15:00.500 Index row.
    """
    session = "2026-08-20"
    projection_root = tmp_path / "projection"
    physical = projection_root / "collector"
    raw = physical / f"raw/{session}/events_09.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)

    def index_record(fraction: str, price: float) -> dict:
        return {
            "received_at": f"{session}T09:15:00.{fraction}+05:30",
            "event_time": f"{session}T09:15:00.{int(fraction) - 10_000:06d}+05:30",
            "message": {
                "symbol": "NSE:NIFTYBANK-INDEX",
                "ltp": price,
                "vol_traded_today": 0,
            },
        }

    raw.write_bytes(
        json.dumps(index_record("100000", 57_000.0), separators=(",", ":")).encode()
        + b"\n"
        + b"\n" * 700
        + json.dumps(index_record("500000", 57_002.0), separators=(",", ":")).encode()
        + b"\n"
    )

    def option_record(fraction: str, oi: int) -> dict:
        return {
            "received_at": f"{session}T09:15:00.{fraction}+05:30",
            "request_time": f"{session}T09:15:00.{int(fraction) - 10_000:06d}+05:30",
            "source": "option_chain",
            "response": {
                "data": {
                    "expiryData": [{"date": "27-08-2026"}],
                    "optionsChain": [
                        {
                            "symbol": "NSE:BANKNIFTY26AUG57000CE",
                            "strike_price": 57_000,
                            "oi": oi,
                            "ltp": 250.0,
                            "volume": 50,
                        },
                        {
                            "symbol": "NSE:BANKNIFTY26AUG57000PE",
                            "strike_price": 57_000,
                            "oi": oi - 50,
                            "ltp": 230.0,
                            "volume": 45,
                        },
                    ],
                }
            },
        }

    oi_09 = physical / f"oi/{session}/oi_09.jsonl"
    oi_10 = physical / f"oi/{session}/oi_10.jsonl"
    _write_jsonl(oi_09, [option_record("300000", 500)])
    _write_jsonl(oi_10, [option_record("600000", 510)])

    projection_files = []
    for path, selected_records in ((raw, 2), (oi_09, 1), (oi_10, 1)):
        physical_rows, ends_with_newline = harness._count_lines(path)
        assert ends_with_newline is True
        projection_files.append(
            {
                "relative_path": str(path.relative_to(physical)),
                "bytes": path.stat().st_size,
                "physical_rows": physical_rows,
                "selected_json_records": selected_records,
                "sha256": harness._sha256_file(path),
            }
        )
    (projection_root / "projection_manifest.json").write_text(
        json.dumps(
            {
                "schema": "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1",
                "collector_root": str(physical.resolve()),
                "source_mutations": 0,
                "projection_files": projection_files,
            }
        )
    )

    config = _config(tmp_path / "shadow.json")
    config_payload = json.loads(config.read_text())
    config_payload["max_read_bytes_per_file_per_poll"] = 512
    config.write_text(json.dumps(config_payload))
    sources = harness.discover_sources(
        physical, (session,), include_predecessors=False
    )

    runs = {}
    for name in (
        "original_source_chunks",
        "one_record_per_increment",
        "hourly_file_rotation",
    ):
        snapshot, accounting, metrics = harness.run_schedule(
            schedule=harness.SCHEDULES[name],
            sources=sources,
            staging_root=tmp_path / f"{name}_collector",
            state_root=tmp_path / f"{name}_state",
            config_path=config,
            sessions=(session,),
        )
        assert all(row["status"] == "PASS" for row in accounting)
        assert metrics["analytical_refusals"] == 0
        assert metrics["causal_checkpoint_remainders_after_drain"] == 0
        assert harness.schedule_exercise_failures(name, metrics) == []
        assert not any(
            str(row.get("reason", "")).startswith("OUT_OF_ORDER")
            for row in harness._as_rows(
                snapshot.get("analytical_ledgers", {}).get(
                    "refusals_data_quality", []
                )
            )
        )
        runs[name] = (snapshot, metrics)

    baseline = runs["original_source_chunks"][0]
    for name in ("one_record_per_increment", "hourly_file_rotation"):
        snapshot, metrics = runs[name]
        assert metrics["causal_backlog_path_repolls"] > 0
        assert metrics["maximum_causal_backlog_paths"] > 0
        assert all(
            row["status"] == "PASS"
            for row in harness.compare_snapshots(baseline, snapshot, expected=None)
        )
        assert harness.analytical_ledger_rows(baseline) == (
            harness.analytical_ledger_rows(snapshot)
        )
    assert runs["hourly_file_rotation"][1]["hourly_rotation_boundary_count"] == 1
    assert runs["hourly_file_rotation"][1][
        "expected_hourly_rotation_boundaries"
    ] == 1


def test_original_byte_chunks_and_hourly_rotation_are_measured(tmp_path: Path) -> None:
    physical, sessions = _physical_fixture(tmp_path / "collector")
    session = sessions[0]
    for stream, first_name, rotated_name in (
        ("raw", "events_09.jsonl", "events_10.jsonl"),
        ("oi", "oi_09.jsonl", "oi_10.jsonl"),
    ):
        first = physical / stream / session / first_name
        lines = first.read_bytes().splitlines(keepends=True)
        first.write_bytes(b"".join(lines[:-1]))
        (first.parent / rotated_name).write_bytes(lines[-1])
    config = _config(tmp_path / "shadow.json")
    sources = harness.discover_sources(
        physical, sessions, include_predecessors=False
    )

    original, original_accounting, original_metrics = harness.run_schedule(
        schedule=harness.SCHEDULES["original_source_chunks"],
        sources=sources,
        staging_root=tmp_path / "original_collector",
        state_root=tmp_path / "original_state",
        config_path=config,
        sessions=sessions,
    )
    rotated, rotated_accounting, rotated_metrics = harness.run_schedule(
        schedule=harness.SCHEDULES["hourly_file_rotation"],
        sources=sources,
        staging_root=tmp_path / "rotated_collector",
        state_root=tmp_path / "rotated_state",
        config_path=config,
        sessions=sessions,
    )

    assert all(row["status"] == "PASS" for row in original_accounting)
    assert all(row["status"] == "PASS" for row in rotated_accounting)
    assert original_metrics["original_source_chunk_count"] >= len(sources)
    assert original_metrics["original_source_files_staged_before_first_poll"] == len(
        sources
    )
    assert original_metrics["analytical_refusals"] == 0
    assert rotated_metrics["hourly_rotation_boundary_count"] == 2
    assert rotated_metrics["analytical_refusals"] == 0
    assert harness.schedule_exercise_failures(
        "original_source_chunks", original_metrics
    ) == []
    assert harness.schedule_exercise_failures(
        "hourly_file_rotation", rotated_metrics
    ) == []
    assert all(
        row["status"] == "PASS"
        for row in harness.compare_snapshots(original, rotated, expected=None)
    )
    assert harness.analytical_ledger_rows(original) == (
        harness.analytical_ledger_rows(rotated)
    )
