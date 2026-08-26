from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parent
CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
EXPECTED_REPLAY_SESSIONS = (
    "2026-08-11", "2026-08-12", "2026-08-13",
    "2026-08-18", "2026-08-19", "2026-08-20",
)
REQUIRED_IDENTITY_LEDGERS = (
    "availability_transitions.jsonl",
    "cross_layer_transitions.jsonl",
    "dependency_retriggers.jsonl",
    "divergence_confirmations.jsonl",
    "inventory_winner_transitions.jsonl",
    "lifecycle_transitions.jsonl",
    "normalized_raw_events.jsonl",
    "participation_transitions.jsonl",
    "raw_file_checkpoints.jsonl",
)
FROZEN_OUTPUT_COUNTS = {
    "inventory": 255,
    "episodes": 65,
    "green": 41,
    "red": 24,
    "retriggers": 14,
    "lifecycle": 14_201,
    "resolution": 164_668,
    "responses": 65,
    "participation_dense": 69_225,
    "participation_transitions": 32_068,
    "participation_summaries": 65,
    "compatibility_snapshots": 65,
    "cross_layer_transitions": 60_659,
}


def _bubblewrap_prefix() -> list[str]:
    return [
        "/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--share-net",
        "--disable-userns", "--assert-userns-disabled", "--die-with-parent",
        "--new-session", "--cap-drop", "ALL", "--clearenv",
        "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", str(ROOT), "/app/deploy/r6e1r", "--dev", "/dev",
        "--proc", "/proc", "--tmpfs", "/tmp", "--dir", "/run",
        "--chdir", "/app", "/usr/bin/python3", "-I", "-B",
    ]


def _run_in_gateway_systemd_boundary(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Exercise bwrap below the same compatible user-unit restrictions."""
    properties = [
        "WorkingDirectory=" + str(ROOT.parents[1]),
        "UMask=0077",
        "UnsetEnvironment=SSH_AUTH_SOCK DBUS_SESSION_BUS_ADDRESS",
        "KeyringMode=private",
        "MemoryHigh=192M", "MemoryMax=256M", "MemorySwapMax=0",
        "CPUQuota=50%", "TasksMax=128", "LimitNOFILE=4096",
        "OOMPolicy=stop", "NoNewPrivileges=true", "PrivateTmp=true",
        "PrivateDevices=true", "ProtectHome=true", "ProtectSystem=strict",
        "ReadOnlyPaths=" + str(ROOT.parents[1]),
        "InaccessiblePaths=-/opt/banknifty-collector/data-prod-v4",
        "InaccessiblePaths=-/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/state",
        "InaccessiblePaths=-/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow/config",
        f"InaccessiblePaths=-/run/user/{os.getuid()}/gnupg",
        "ProtectControlGroups=true", "ProtectKernelModules=true",
        "ProtectClock=true", "RestrictSUIDSGID=true",
        "RestrictNamespaces=~net", "LockPersonality=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=",
    ]
    systemd = [
        "/usr/bin/systemd-run", "--user", "--wait", "--collect", "--pipe",
        "--quiet",
    ]
    for value in properties:
        systemd.extend(("--property", value))
    return subprocess.run(
        [*systemd, "--", *_bubblewrap_prefix(), *command],
        check=True, capture_output=True, text=True, timeout=15,
    )


def test_user_units_are_isolated_and_resource_bounded() -> None:
    backend = (ROOT / "r6e1r-shadow.service").read_text()
    gateway = (ROOT / "r6e1r-readonly-gateway.service").read_text()
    combined = backend + gateway

    assert "User=" not in combined and "Group=" not in combined
    assert "WantedBy=default.target" in backend
    assert "WantedBy=default.target" in gateway
    assert "multi-user.target" not in combined
    assert "/var/lib/" not in combined and "/etc/banknifty" not in combined
    assert "PYTHONPATH=/opt/banknifty/repositories/banknifty-market-profiler/src" in backend
    assert "--bind 127.0.0.1 --port 18805" in backend
    assert "--bind 0.0.0.0 --port 8805 --backend http://127.0.0.1:18805" in gateway
    assert "8803" not in combined and "8804" not in combined
    assert "Restart=on-failure" in backend and "Restart=on-failure" in gateway
    for directive in (
        "MemoryHigh=", "MemoryMax=", "CPUQuota=", "TasksMax=",
        "NoNewPrivileges=true", "ProtectSystem=strict", "StandardOutput=journal",
        "UnsetEnvironment=SSH_AUTH_SOCK DBUS_SESSION_BUS_ADDRESS",
        "KeyringMode=private", "PrivateDevices=true",
        "ProtectKernelModules=true",
    ):
        assert directive in backend and directive in gateway
    assert "network.target" not in combined
    assert "ExecStart=/usr/bin/bwrap" in gateway
    assert "ExecStartPost=/usr/bin/bwrap" in gateway
    assert "--unshare-all --unshare-user --share-net" in gateway
    assert "--disable-userns --assert-userns-disabled" in gateway
    assert "--clearenv" in gateway and "--require-isolation" in gateway
    assert "RestrictNamespaces=~net" in gateway
    assert "InaccessiblePaths=" in gateway
    # These systemd-created namespaces prevent rootless bwrap from mounting its
    # private procfs. The backend retains them; bwrap supplies the gateway's
    # stronger private PID/mount/UTS boundary and verifies it at startup.
    for incompatible in (
        "ProtectKernelTunables=true", "ProtectKernelLogs=true",
        "ProtectHostname=true",
    ):
        assert incompatible in backend and incompatible not in gateway
    prefix = " ".join(_bubblewrap_prefix())
    assert f"ExecStart={prefix} /app/deploy/r6e1r/read_only_gateway.py" in gateway
    assert f"ExecStartPost={prefix} /app/deploy/r6e1r/health_readiness_check.py" in gateway
    for hidden in (
        "/opt/banknifty-collector/data-prod-v4",
        "r6e1r_final_live_shadow/state",
        "r6e1r_final_live_shadow/config",
        "%t/gnupg",
    ):
        assert hidden in gateway

    assert "--attempts 300 --delay-seconds 1" in backend
    assert "TimeoutStartSec=360s" in backend
    assert "--attempts 30 --delay-seconds 1" in gateway
    assert "TimeoutStartSec=75s" in gateway


def test_preload_runbook_requires_verified_atomic_same_filesystem_staging() -> None:
    readme = (ROOT / "README.md").read_text()
    assert 'mktemp -d "$DEPLOY_ROOT/.state.preload.XXXXXX"' in readme
    assert 'STATE_MANIFEST="$VERIFIED_OUTPUT/incremental_a_state_manifest.json"' in readme
    assert 'test -f "$STATE_MANIFEST"' in readme
    assert '(cd "$STATE_STAGE" && sha256sum -c -)' in readme
    assert '(cd "$VERIFIED_STATE" && sha256sum -c -)' in readme
    assert "validate_preloaded_state.py" in readme
    assert "raw_projection_manifest.json" in readme
    assert "equivalence_summary.json" in readme
    assert "--equivalence-summary" in readme
    assert "--raw-projection-manifest" in readme
    assert "--state-manifest" in readme
    assert "jq -r '.files[]" in readme and "sha256sum -c -" in readme
    assert "find . -type f" not in readme
    assert 'test ! -e "$STATE_MANIFEST"' not in readme
    assert 'test ! -e "$DEPLOY_ROOT/state"' in readme
    assert 'mv -T -- "$STATE_STAGE" "$DEPLOY_ROOT/state"' in readme
    assert 'cp -a -- "$VERIFIED_STATE/." "$DEPLOY_ROOT/state/"' not in readme


def test_harness_seals_exact_state_tree_and_verifies_sources_before_finalize(
    tmp_path: Path,
) -> None:
    harness = runpy.run_path(
        str(ROOT.parents[1] / "scripts/run_r6e1r_equivalence.py")
    )
    state = tmp_path / "state"
    (state / "ledgers").mkdir(parents=True)
    (state / "checkpoints.json").write_text("{}\n")
    (state / "ledgers/events.jsonl").write_text('{"id":"A"}\n')
    manifest_path = tmp_path / "incremental_a_state_manifest.json"
    seal = harness["write_state_tree_manifest"](state, manifest_path)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "R6E1R_INCREMENTAL_A_STATE_TREE_MANIFEST_V1"
    assert [row["path"] for row in manifest["files"]] == [
        "checkpoints.json", "ledgers/events.jsonl",
    ]
    assert seal == {
        "state_manifest_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "state_tree_sha256": manifest["state_tree_sha256"],
        "state_file_count": 2,
    }
    (state / "dedup.sqlite3-wal").write_bytes(b"unsafe")
    with pytest.raises(ValueError, match="state-tree file is unsafe"):
        harness["write_state_tree_manifest"](state, tmp_path / "refused.json")

    finalized = []

    class FailingIngestor:
        def verify_committed_sources(self, sessions):
            assert tuple(sessions) == (EXPECTED_REPLAY_SESSIONS[0],)
            raise ValueError("committed source integrity verification failed")

    class Finalizer:
        def finalize_session(self, session):
            finalized.append(session)
            return {}

    context = object.__new__(harness["_RunContext"])
    context.ingestor = FailingIngestor()
    context.orchestrator = Finalizer()
    with pytest.raises(
        ValueError, match="committed source integrity verification failed",
    ):
        context.snapshot((EXPECTED_REPLAY_SESSIONS[0],))
    assert finalized == []

    class VerifiedIngestor:
        ledgers = {}

        def verify_committed_sources(self, sessions):
            assert tuple(sessions) == (EXPECTED_REPLAY_SESSIONS[0],)
            return {"source_files": 2, "prefix_blocks": 7}

    context.ingestor = VerifiedIngestor()
    result = context.snapshot((EXPECTED_REPLAY_SESSIONS[0],))
    assert finalized == [EXPECTED_REPLAY_SESSIONS[0]]
    assert result["committed_source_integrity"] == {
        "source_files": 2,
        "prefix_blocks": 7,
    }


def test_templates_are_non_secret_and_preserve_runtime_contract() -> None:
    activation = json.loads((ROOT / "r6e1r-activation.json.example").read_text())
    config = json.loads((ROOT / "r6e1r-runtime-config.json.example").read_text())
    assert activation["activation_day"] == "2026-08-26"
    assert activation["classification"] == CLASSIFICATION
    assert config["timezone"] == "Asia/Kolkata"
    assert config["synchronization_tolerance_ms"] == 2000
    assert config["index_symbol"] == "NSE:NIFTYBANK-INDEX"
    assert config["selected_futures_by_session"] == {}
    assert config["analytical_threshold_overrides"] is None
    assert config["max_live_sessions"] == 32
    assert config["engine_source_manifest_path"] == (
        "manifests/r6e1r_engine_source_manifest.json"
    )
    repo = ROOT.parents[1]
    manifest_path = repo / config["engine_source_manifest_path"]
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert config["engine_source_manifest_sha256"] == actual
    companion = (
        repo / "manifests/r6e1r_engine_source_manifest.sha256"
    ).read_text().split()
    assert companion == [actual, config["engine_source_manifest_path"]]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "R6E1R_ENGINE_SOURCE_MANIFEST_V1"
    assert manifest["classification"] == CLASSIFICATION
    assert manifest["file_count"] == len(manifest["files"])
    serialized = json.dumps({"activation": activation, "config": config}).lower()
    for token in ("password", "api_key", "secret", "credential", "token"):
        assert token not in serialized


def _distributed_rows(
    rows: list[dict], session_index: int,
) -> list[dict]:
    size, remainder = divmod(len(rows), len(EXPECTED_REPLAY_SESSIONS))
    start = session_index * size + min(session_index, remainder)
    stop = start + size + int(session_index < remainder)
    return rows[start:stop]


def _frozen_outputs_fixture(
    frozen_counts: dict[str, int] = FROZEN_OUTPUT_COUNTS,
) -> dict[str, dict]:
    aggregate_rows = {
        "inventory": [{}] * frozen_counts["inventory"],
        "episodes": (
            [{"colour": "GREEN"}] * frozen_counts["green"]
            + [{"colour": "RED"}] * frozen_counts["red"]
        ),
        "dependencies": (
            [{"retrigger_flag": True, "classification": "DEPENDENT_RETRIGGER"}]
            * frozen_counts["retriggers"]
            + [{"retrigger_flag": False, "classification": "NEW_INDEPENDENT_HYPOTHESIS"}]
            * (frozen_counts["episodes"] - frozen_counts["retriggers"])
        ),
        "lifecycle": [{}] * frozen_counts["lifecycle"],
        "resolution": [{}] * frozen_counts["resolution"],
        "responses": [{}] * frozen_counts["responses"],
        "participation_dense": [{}] * frozen_counts["participation_dense"],
        "participation_transitions": (
            [{}] * frozen_counts["participation_transitions"]
        ),
        "participation_summaries": (
            [{}] * frozen_counts["participation_summaries"]
        ),
        "compatibility_snapshots": (
            [{}] * frozen_counts["compatibility_snapshots"]
        ),
        "cross_layer_transitions": (
            [{}] * frozen_counts["cross_layer_transitions"]
        ),
    }
    callbacks = {
        name: 1
        for name in (
            "synchronization", "inventory", "divergence_detector",
            "dependency", "lifecycle", "participation",
            "participation_views", "cross_layer", "gui_projection",
        )
    }
    outputs = {}
    for index, session in enumerate(EXPECTED_REPLAY_SESSIONS):
        basis = [
            {
                "validity_status": "VALID",
                "basis_timestamp": f"{session}T09:15:0{ordinal}+05:30",
                "index_receipt_timestamp": f"{session}T09:15:0{ordinal}+05:30",
                "futures_receipt_timestamp": f"{session}T09:15:0{ordinal}.100+05:30",
                "index_price": 57_000.0 + ordinal,
                "futures_price": 57_010.0 + ordinal,
                "basis_value": 10.0,
            }
            for ordinal in (1, 2)
        ]
        output = {
            "session_date": session,
            "basis": basis,
            **{
                field: _distributed_rows(rows, index)
                for field, rows in aggregate_rows.items()
            },
            "availability": {
                "overall_state": "LIVE_COMPLETE",
                "market_display_enabled": True,
                "layers": {"ID": {"state": "AVAILABLE"}},
            },
            "gui_payload": {
                "schema": "R6E_LIVE_SESSION_PAYLOAD_V1",
                "classification": CLASSIFICATION,
                "date": session,
                "price": {
                    "fields": ["t", "i", "f", "b"],
                    "rows": [
                        [row["basis_timestamp"], row["index_price"],
                         row["futures_price"], row["basis_value"]]
                        for row in basis
                    ],
                },
            },
            "callback_invocations": callbacks,
            "participation_view_seal": {"mode": "stream"},
            "fixed_inventory_cache": {"status": "AVAILABLE"},
        }
        output["counts"] = {
            "observations": 1,
            **{
                field: len(output[field])
                for field in (
                    "basis", "inventory", "episodes", "dependencies",
                    "lifecycle", "resolution", "participation_dense",
                    "participation_transitions", "participation_summaries",
                    "compatibility_snapshots", "cross_layer_transitions",
                )
            },
        }
        outputs[session] = output
    return outputs


def _write_bound_state_manifest(
    state: Path, manifest_path: Path, summary_path: Path | None = None,
) -> dict[str, object]:
    files = []
    for path in sorted(
        (path for path in state.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(state).as_posix(),
    ):
        files.append({
            "path": path.relative_to(state).as_posix(),
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    aggregate = hashlib.sha256()
    for row in files:
        aggregate.update(
            f'{row["path"]}\0{row["sha256"]}\0{row["size"]}\n'.encode()
        )
    manifest = {
        "schema": "R6E1R_INCREMENTAL_A_STATE_TREE_MANIFEST_V1",
        "classification": CLASSIFICATION,
        "file_count": len(files),
        "state_tree_sha256": aggregate.hexdigest(),
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )
    seal = {
        "state_manifest_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "state_tree_sha256": manifest["state_tree_sha256"],
        "state_file_count": manifest["file_count"],
    }
    if summary_path is not None:
        summary = json.loads(summary_path.read_text())
        summary["incremental_a_seal"].update(seal)
        summary["incremental_a_state_manifest_sha256"] = seal[
            "state_manifest_sha256"
        ]
        summary["incremental_a_state_tree_sha256"] = seal["state_tree_sha256"]
        summary["incremental_a_state_file_count"] = seal["state_file_count"]
        summary_path.write_text(json.dumps(summary))
    return seal


def _valid_preload_fixture(
    root: Path, *, frozen_outputs: bool = False,
    frozen_counts: dict[str, int] = FROZEN_OUTPUT_COUNTS,
) -> tuple[Path, Path, str, Path, str, Path, Path, Path]:
    state = root / "state"
    state.mkdir()
    outputs = (
        _frozen_outputs_fixture(frozen_counts)
        if frozen_outputs
        else {
            session: {"session_date": session}
            for session in EXPECTED_REPLAY_SESSIONS
        }
    )
    (state / "live_analytical_orchestrator.json").write_text(json.dumps({
        "version": "R6E1R_LIVE_ANALYTICAL_STATE_V1",
        "outputs": outputs,
        "finalized_sessions": list(EXPECTED_REPLAY_SESSIONS),
        "dirty_sessions": [],
        "sessions": {},
    }))
    checkpoint = {
        "offset": 65_636,
        "row": 2,
        "identity": "1:2",
        "size_at_commit": 65_636,
        "updated_at": "2026-08-20T15:30:00+05:30",
        "prefix_fingerprint": "a" * 64,
        "mtime_ns_at_commit": 123,
    }
    (state / "checkpoints.json").write_text(json.dumps({
        "raw/2026-08-20/events.jsonl": checkpoint,
    }))

    database = sqlite3.connect(state / "dedup.sqlite3")
    database.executescript("""
        create table file_checkpoint(
            source_file text primary key, offset integer not null,
            row_number integer not null, identity text not null,
            size_at_commit integer not null, updated_at text not null,
            frontier text, prefix_fingerprint text not null,
            mtime_ns_at_commit integer not null
        );
        create table observation_outbox(id text primary key, payload text not null);
        create table futures_candidate_outbox(
            id text primary key, session_date text not null,
            receipt_timestamp text, payload text not null
        );
        create table futures_selection_probe(
            source_file text primary key, session_date text not null,
            start_offset integer not null, probe_offset integer not null,
            identity text not null, prefix_fingerprint text not null,
            mtime_ns_at_probe integer not null, replay_target integer,
            bytes_consumed integer not null default 0,
            inspected_offset integer not null default 0,
            inspected_fingerprint text not null default '',
            size_at_probe integer not null default -1,
            authority_fingerprint text not null default ''
        );
        create table quarantined_source(
            source_file text primary key, session_date text not null,
            reason text not null, expected_identity text not null,
            expected_offset integer not null,
            expected_fingerprint text not null,
            detected_identity text not null, detected_size integer not null,
            invalidates_selection integer not null, detected_at text not null
        );
        create table file_prefix_block(
            source_file text not null, block_index integer not null,
            byte_count integer not null, digest text not null,
            primary key(source_file, block_index)
        );
        create table file_integrity_scrub(
            source_file text primary key,
            next_block integer not null default 0,
            updated_at text not null
        );
    """)
    database.execute(
        "insert into file_checkpoint values (?,?,?,?,?,?,?,?,?)",
        (
            "raw/2026-08-20/events.jsonl", checkpoint["offset"],
            checkpoint["row"], checkpoint["identity"],
            checkpoint["size_at_commit"], checkpoint["updated_at"],
            "2026-08-20T15:30:00+05:30", checkpoint["prefix_fingerprint"],
            checkpoint["mtime_ns_at_commit"],
        ),
    )
    database.executemany(
        "insert into file_prefix_block values (?,?,?,?)",
        (
            ("raw/2026-08-20/events.jsonl", 0, 65_536, "d" * 64),
            ("raw/2026-08-20/events.jsonl", 1, 100, "e" * 64),
        ),
    )
    database.execute(
        "insert into file_integrity_scrub values (?,?,?)",
        (
            "raw/2026-08-20/events.jsonl", 1,
            "2026-08-20T15:30:00+05:30",
        ),
    )
    database.commit()
    database.close()

    engine_manifest = root / "engine-manifest.json"
    engine_manifest.write_text(json.dumps({"engine_hash": "b" * 64}))
    engine_hash = hashlib.sha256(engine_manifest.read_bytes()).hexdigest()
    runtime_config = root / "runtime-config.json"
    runtime_config.write_text(json.dumps({
        "engine_source_manifest_sha256": engine_hash,
    }))
    config_hash = hashlib.sha256(runtime_config.read_bytes()).hexdigest()
    configuration_hash = hashlib.sha256(
        (
            json.dumps(
                json.loads(runtime_config.read_text()),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    ).hexdigest()

    ledgers = state / "ledgers"
    ledgers.mkdir()
    identity_row = json.dumps({
        "event_id": "fixture-event",
        "engine_hash": "b" * 64,
        "configuration_hash": configuration_hash,
    }) + "\n"
    for name in REQUIRED_IDENTITY_LEDGERS:
        (ledgers / name).write_text(identity_row)

    state_manifest = root / "incremental_a_state_manifest.json"
    state_seal = _write_bound_state_manifest(state, state_manifest)

    source_digest = "c" * 64
    projection = root / "raw_projection_manifest.json"
    projection.write_text(json.dumps({
        "schema": "R6E1R_BYTE_EXACT_RAW_RECORD_PROJECTION_V1",
        "classification": CLASSIFICATION,
        "authoritative_source_root": "/opt/banknifty-collector/data-prod-v4",
        "evaluation_sessions": list(EXPECTED_REPLAY_SESSIONS),
        "causal_source_sessions": [
            "2026-08-10", *EXPECTED_REPLAY_SESSIONS[:3],
            "2026-08-17", *EXPECTED_REPLAY_SESSIONS[3:],
        ],
        "august_17_policy": "PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED",
        "contract_selection": {
            "2026-08-17": {
                "futures_symbol": "NSE:BANKNIFTY26AUGFUT",
                "selection_authority": "banknifty_profiler.raw_io.reader.select_contracts",
            },
        },
        "complete_json_records_only": True,
        "selected_records_byte_exact": True,
        "source_mutations": 0,
        "malformed_candidate_records": 0,
        "source_files": [{
            "unchanged_after_projection": True,
            "sha256_before": source_digest,
            "sha256_after": source_digest,
        }],
    }))
    projection_hash = hashlib.sha256(projection.read_bytes()).hexdigest()
    summary = root / "equivalence_summary.json"
    summary.write_text(json.dumps({
        "status": "PASS",
        "sessions": list(EXPECTED_REPLAY_SESSIONS),
        "focused_equivalence": False,
        "frozen_count_contract_applicable": True,
        "frozen_count_gate_enforced": True,
        "frozen_count_gate_satisfied": True,
        "references_skipped": False,
        "reference_manifests_verified": True,
        "reference_package_manifests": [
            {"status": "PASS"}, {"status": "PASS"},
        ],
        "file_open_audit_measured": True,
        "file_open_audit_rows": 1,
        "component_failures": 0,
        "analytical_ledger_failures": 0,
        "causality_failures": 0,
        "reference_failures": 0,
        "schedule_failures": 0,
        "checkpoint_failures": 0,
        "checkpoint_recovery_failures": 0,
        "file_open_audit_unmeasured_rows": 0,
        "prohibited_a_b_opens": 0,
        "post_run_source_mutations": 0,
        "incremental_a_seal": {
            "sealed": True,
            "dirty_sessions_after_seal": [],
            "staged_sessions": [],
            "unexpected_staged_sessions": [],
            "analytical_refusals": 0,
            "checkpoint_failures": 0,
            "committed_source_integrity": {
                "source_files": 1,
                "prefix_blocks": 2,
            },
            **state_seal,
        },
        "incremental_a_state_manifest_sha256": state_seal[
            "state_manifest_sha256"
        ],
        "incremental_a_state_tree_sha256": state_seal["state_tree_sha256"],
        "incremental_a_state_file_count": state_seal["state_file_count"],
        "incremental_a_committed_source_integrity": {
            "source_files": 1,
            "prefix_blocks": 2,
        },
        "batch_b_seal": {
            "sealed": True,
            "command_returncodes": [0, 0, 0],
        },
        "raw_projection": {
            "used": True,
            "reused_existing": False,
            "source_mutations": 0,
            "malformed_candidate_records": 0,
            "selected_outer_records": 1,
            "manifest_sha256": projection_hash,
        },
    }))
    return (
        state, engine_manifest, engine_hash, runtime_config, config_hash,
        summary, projection, state_manifest,
    )


def _run_validator(
    root: Path, *, frozen_outputs: bool = False,
) -> subprocess.CompletedProcess[str]:
    fixture = _valid_preload_fixture(root, frozen_outputs=frozen_outputs)
    return _run_existing_validator(fixture)


def _run_existing_validator(fixture) -> subprocess.CompletedProcess[str]:
    (
        state, engine, engine_hash, config, config_hash, summary, projection,
        state_manifest,
    ) = fixture
    configuration_hash = hashlib.sha256(
        (json.dumps(json.loads(config.read_text()), sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    command = [
        sys.executable, "-I", "-B", str(ROOT / "validate_preloaded_state.py"),
        "--state-root", str(state),
    ]
    for session in EXPECTED_REPLAY_SESSIONS:
        command.extend(("--expected-session", session))
    command.extend((
        "--engine-manifest", str(engine),
        "--expected-engine-manifest-sha256", engine_hash,
        "--expected-engine-hash", "b" * 64,
        "--runtime-config", str(config),
        "--expected-runtime-config-sha256", config_hash,
        "--expected-configuration-hash", configuration_hash,
        "--equivalence-summary", str(summary),
        "--raw-projection-manifest", str(projection),
        "--state-manifest", str(state_manifest),
    ))
    return subprocess.run(command, check=False, capture_output=True, text=True)


def test_preloaded_state_validator_accepts_exact_finalized_state(tmp_path: Path) -> None:
    module = runpy.run_path(str(ROOT / "validate_preloaded_state.py"))
    actual_orchestrator = {"outputs": _frozen_outputs_fixture()}
    assert module["FROZEN_OUTPUT_COUNTS"] == FROZEN_OUTPUT_COUNTS
    actual_counts = module["validate_analytical_outputs"](
        actual_orchestrator, EXPECTED_REPLAY_SESSIONS,
    )
    assert actual_counts == {
        **FROZEN_OUTPUT_COUNTS,
        "basis": 12,
        "valid_basis": 12,
    }

    compact_counts = {
        key: (3 if key in {"green", "red"} else 1 if key == "retriggers" else 6)
        for key in FROZEN_OUTPUT_COUNTS
    }
    (
        state, engine, engine_hash, config, config_hash, summary, projection,
        state_manifest,
    ) = _valid_preload_fixture(
        tmp_path, frozen_outputs=True, frozen_counts=compact_counts,
    )
    module["FROZEN_OUTPUT_COUNTS"].clear()
    module["FROZEN_OUTPUT_COUNTS"].update(compact_counts)
    configuration_hash = hashlib.sha256(
        (
            json.dumps(
                json.loads(config.read_text()), sort_keys=True, separators=(",", ":"),
            )
            + "\n"
        ).encode()
    ).hexdigest()
    arguments = ["--state-root", str(state)]
    for session in EXPECTED_REPLAY_SESSIONS:
        arguments.extend(("--expected-session", session))
    arguments.extend((
        "--engine-manifest", str(engine),
        "--expected-engine-manifest-sha256", engine_hash,
        "--expected-engine-hash", "b" * 64,
        "--runtime-config", str(config),
        "--expected-runtime-config-sha256", config_hash,
        "--expected-configuration-hash", configuration_hash,
        "--equivalence-summary", str(summary),
        "--raw-projection-manifest", str(projection),
        "--state-manifest", str(state_manifest),
    ))
    value = module["validate"](module["parser"]().parse_args(arguments))
    assert value["schema"] == "R6E1R_PRELOADED_STATE_VALIDATION_V1"
    assert value["ok"] is True
    assert value["session_count"] == 6
    assert value["output_count"] == 6
    assert value["finalized_session_count"] == 6
    assert value["dirty_session_count"] == 0
    assert value["mutable_session_count"] == 0
    assert value["checkpoint_count"] == 1
    assert value["observation_outbox_count"] == 0
    assert value["futures_candidate_outbox_count"] == 0
    assert value["futures_selection_probe_count"] == 0
    assert value["quarantined_source_count"] == 0
    assert value["file_prefix_block_count"] == 2
    assert value["file_integrity_scrub_count"] == 1
    assert value["sqlite_quick_check"] == "ok"
    assert value["identity_ledger_count"] == len(REQUIRED_IDENTITY_LEDGERS)
    assert value["identity_ledger_row_count"] == len(REQUIRED_IDENTITY_LEDGERS)
    assert value["raw_source_evidence_count"] == 1
    assert value["august_17_policy"] == (
        "PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED"
    )
    assert len(value["equivalence_summary_sha256"]) == 64
    assert len(value["raw_projection_manifest_sha256"]) == 64
    assert len(value["state_manifest_sha256"]) == 64
    assert len(value["state_tree_sha256"]) == 64
    assert value["analytical_output_counts"] == {
        **compact_counts,
        "basis": 12,
        "valid_basis": 12,
    }


def test_analytical_output_recount_refuses_count_and_basis_tamper() -> None:
    module = runpy.run_path(str(ROOT / "validate_preloaded_state.py"))
    outputs = _frozen_outputs_fixture()
    first = outputs[EXPECTED_REPLAY_SESSIONS[0]]
    first["inventory"].pop()
    first["counts"]["inventory"] = len(first["inventory"])
    with pytest.raises(module["ValidationError"]) as mismatch:
        module["validate_analytical_outputs"](
            {"outputs": outputs}, EXPECTED_REPLAY_SESSIONS,
        )
    assert mismatch.value.code == "FROZEN_ANALYTICAL_OUTPUT_COUNT_MISMATCH"

    outputs = _frozen_outputs_fixture()
    first = outputs[EXPECTED_REPLAY_SESSIONS[0]]
    first["basis"].pop()
    first["counts"]["basis"] = 1
    with pytest.raises(module["ValidationError"]) as basis:
        module["validate_analytical_outputs"](
            {"outputs": outputs}, EXPECTED_REPLAY_SESSIONS,
        )
    assert basis.value.code == "ANALYTICAL_BASIS_MULTIPOINT_REQUIRED"


def test_preloaded_state_validator_refuses_bound_empty_outputs(tmp_path: Path) -> None:
    result = _run_validator(tmp_path, frozen_outputs=False)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "schema": "R6E1R_PRELOADED_STATE_VALIDATION_V1",
        "ok": False,
        "error_code": "ANALYTICAL_OUTPUT_SHAPE_INVALID",
    }
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("same_size_state_tamper", "STATE_MANIFEST_FILE_HASH_MISMATCH"),
        ("state_growth", "STATE_MANIFEST_FILE_SIZE_MISMATCH"),
        ("extra_state_file", "STATE_MANIFEST_FILE_SET_MISMATCH"),
        ("missing_state_file", "STATE_MANIFEST_FILE_SET_MISMATCH"),
        ("manifest_tamper", "STATE_MANIFEST_SEAL_MISMATCH"),
        ("summary_binding", "INCREMENTAL_STATE_SEAL_GATE_FAILED"),
    ),
)
def test_preloaded_state_validator_refuses_state_binding_tamper(
    tmp_path: Path, mutation: str, error_code: str,
) -> None:
    fixture = _valid_preload_fixture(tmp_path)
    state, *_, summary, projection, state_manifest = fixture
    del projection
    if mutation == "same_size_state_tamper":
        path = state / "checkpoints.json"
        payload = path.read_bytes()
        path.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    elif mutation == "state_growth":
        (state / "checkpoints.json").write_text(
            (state / "checkpoints.json").read_text() + "\n"
        )
    elif mutation == "extra_state_file":
        (state / "unbound.json").write_text("{}\n")
    elif mutation == "missing_state_file":
        (state / "ledgers/raw_file_checkpoints.jsonl").unlink()
    elif mutation == "manifest_tamper":
        state_manifest.write_text(state_manifest.read_text() + " ")
    elif mutation == "summary_binding":
        value = json.loads(summary.read_text())
        value["incremental_a_state_tree_sha256"] = "0" * 64
        summary.write_text(json.dumps(value))
    result = _run_existing_validator(fixture)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "schema": "R6E1R_PRELOADED_STATE_VALIDATION_V1",
        "ok": False,
        "error_code": error_code,
    }
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("dirty", "DIRTY_SESSIONS_PRESENT"),
        ("mutable", "MUTABLE_SESSIONS_PRESENT"),
        ("output", "OUTPUT_SESSION_SET_MISMATCH"),
        ("finalized", "FINALIZED_SESSION_SET_MISMATCH"),
        ("version", "ORCHESTRATOR_STATE_VERSION_MISMATCH"),
        ("engine_ledger", "STATE_ENGINE_IDENTITY_MISMATCH"),
        ("configuration_ledger", "STATE_CONFIGURATION_IDENTITY_MISMATCH"),
        ("missing_ledger", "REQUIRED_IDENTITY_LEDGER_MISSING"),
        ("empty_ledger", "REQUIRED_IDENTITY_LEDGER_EMPTY"),
        ("observation", "OBSERVATION_OUTBOX_NOT_EMPTY"),
        ("candidate", "FUTURES_CANDIDATE_OUTBOX_NOT_EMPTY"),
        ("selection_probe", "FUTURES_SELECTION_PROBE_NOT_EMPTY"),
        ("quarantined_source", "QUARANTINED_SOURCE_NOT_EMPTY"),
        ("missing_block", "PREFIX_BLOCK_INVENTORY_INVALID"),
        ("corrupt_block_byte_count", "PREFIX_BLOCK_INVENTORY_INVALID"),
        ("corrupt_block_digest", "PREFIX_BLOCK_INVENTORY_INVALID"),
        ("orphan_block", "PREFIX_BLOCK_ORPHAN_SOURCE"),
        ("orphan_scrub", "INTEGRITY_SCRUB_ORPHAN_SOURCE"),
        ("scrub_bounds", "INTEGRITY_SCRUB_BOUNDS_INVALID"),
        ("missing_block_table", "DATABASE_REQUIRED_TABLE_MISSING"),
        ("missing_scrub_table", "DATABASE_REQUIRED_TABLE_MISSING"),
        ("legacy_probe_schema", "DATABASE_REQUIRED_COLUMN_MISSING"),
        ("checkpoint", "CHECKPOINT_JSON_SQLITE_MISMATCH"),
        ("wal", "SQLITE_SIDECAR_PRESENT"),
        ("symlink", "STATE_TREE_SYMLINK"),
    ),
)
def test_preloaded_state_validator_refuses_unsafe_state(
    tmp_path: Path, mutation: str, error_code: str,
) -> None:
    (
        state, engine, engine_hash, config, config_hash, summary, projection,
        state_manifest,
    ) = (
        _valid_preload_fixture(tmp_path)
    )
    configuration_hash = hashlib.sha256(
        (json.dumps(json.loads(config.read_text()), sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    orchestrator_path = state / "live_analytical_orchestrator.json"
    orchestrator = json.loads(orchestrator_path.read_text())
    if mutation == "dirty":
        orchestrator["dirty_sessions"] = [EXPECTED_REPLAY_SESSIONS[0]]
        orchestrator_path.write_text(json.dumps(orchestrator))
    elif mutation == "mutable":
        orchestrator["sessions"] = {
            EXPECTED_REPLAY_SESSIONS[0]: [{"session_date": EXPECTED_REPLAY_SESSIONS[0]}]
        }
        orchestrator_path.write_text(json.dumps(orchestrator))
    elif mutation == "output":
        orchestrator["outputs"].pop(EXPECTED_REPLAY_SESSIONS[0])
        orchestrator_path.write_text(json.dumps(orchestrator))
    elif mutation == "finalized":
        orchestrator["finalized_sessions"].pop()
        orchestrator_path.write_text(json.dumps(orchestrator))
    elif mutation == "version":
        orchestrator["version"] = "R6E1R_LIVE_ANALYTICAL_STATE_UNKNOWN"
        orchestrator_path.write_text(json.dumps(orchestrator))
    elif mutation in {"engine_ledger", "configuration_ledger"}:
        ledger_path = state / "ledgers/normalized_raw_events.jsonl"
        row = json.loads(ledger_path.read_text())
        row[
            "engine_hash" if mutation == "engine_ledger" else "configuration_hash"
        ] = "0" * 64
        ledger_path.write_text(json.dumps(row) + "\n")
    elif mutation == "missing_ledger":
        (state / "ledgers/normalized_raw_events.jsonl").unlink()
    elif mutation == "empty_ledger":
        (state / "ledgers/normalized_raw_events.jsonl").write_text("")
    elif mutation in {"observation", "candidate"}:
        database = sqlite3.connect(state / "dedup.sqlite3")
        table = "observation_outbox" if mutation == "observation" else "futures_candidate_outbox"
        if mutation == "observation":
            database.execute(f"insert into {table} values (?,?)", ("id", "{}"))
        else:
            database.execute(
                f"insert into {table} values (?,?,?,?)",
                ("id", EXPECTED_REPLAY_SESSIONS[0], None, "{}"),
            )
        database.commit()
        database.close()
    elif mutation == "selection_probe":
        database = sqlite3.connect(state / "dedup.sqlite3")
        database.execute(
            "insert into futures_selection_probe values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "oi/2026-08-20/oi.jsonl", "2026-08-20", 0, 100,
                "1:2", "a" * 64, 123, None, 100, 100,
                "b" * 64, 100, "c" * 64,
            ),
        )
        database.commit()
        database.close()
    elif mutation in {
        "missing_block", "corrupt_block_byte_count", "corrupt_block_digest",
        "orphan_block", "orphan_scrub", "scrub_bounds",
        "missing_block_table", "missing_scrub_table", "legacy_probe_schema",
    }:
        database = sqlite3.connect(state / "dedup.sqlite3")
        if mutation == "missing_block":
            database.execute("delete from file_prefix_block where block_index=0")
        elif mutation == "corrupt_block_byte_count":
            database.execute("update file_prefix_block set byte_count=99")
        elif mutation == "corrupt_block_digest":
            database.execute("update file_prefix_block set digest=?", ("D" * 64,))
        elif mutation == "orphan_block":
            database.execute(
                "insert into file_prefix_block values (?,?,?,?)",
                ("oi/2026-08-20/orphan.jsonl", 0, 1, "e" * 64),
            )
        elif mutation == "orphan_scrub":
            database.execute(
                "insert into file_integrity_scrub values (?,?,?)",
                (
                    "oi/2026-08-20/orphan.jsonl", 0,
                    "2026-08-20T15:30:00+05:30",
                ),
            )
        elif mutation == "scrub_bounds":
            database.execute("update file_integrity_scrub set next_block=2")
        elif mutation == "missing_block_table":
            database.execute("drop table file_prefix_block")
        elif mutation == "missing_scrub_table":
            database.execute("drop table file_integrity_scrub")
        elif mutation == "legacy_probe_schema":
            database.execute("drop table futures_selection_probe")
            database.execute(
                "create table futures_selection_probe("
                "source_file text primary key,session_date text not null,"
                "start_offset integer not null,probe_offset integer not null,"
                "identity text not null,prefix_fingerprint text not null,"
                "mtime_ns_at_probe integer not null,replay_target integer)"
            )
        database.commit()
        database.close()
    elif mutation == "quarantined_source":
        database = sqlite3.connect(state / "dedup.sqlite3")
        database.execute(
            "insert into quarantined_source values (?,?,?,?,?,?,?,?,?,?)",
            (
                "oi/2026-08-20/oi.jsonl", "2026-08-20",
                "FILE_REPLACED_OR_TRUNCATED", "1:2", 100, "a" * 64,
                "3:4", 50, 1, "2026-08-20T12:00:00+05:30",
            ),
        )
        database.commit()
        database.close()
    elif mutation == "checkpoint":
        checkpoints = json.loads((state / "checkpoints.json").read_text())
        checkpoints["raw/2026-08-20/events.jsonl"]["offset"] += 1
        (state / "checkpoints.json").write_text(json.dumps(checkpoints))
    elif mutation == "wal":
        (state / "dedup.sqlite3-wal").write_bytes(b"not permitted")
    elif mutation == "symlink":
        (state / "unsafe-link").symlink_to(state / "checkpoints.json")

    if mutation not in {"wal", "symlink"}:
        _write_bound_state_manifest(state, state_manifest, summary)

    command = [
        sys.executable, "-I", "-B", str(ROOT / "validate_preloaded_state.py"),
        "--state-root", str(state),
    ]
    for session in EXPECTED_REPLAY_SESSIONS:
        command.extend(("--expected-session", session))
    command.extend((
        "--engine-manifest", str(engine),
        "--expected-engine-manifest-sha256", engine_hash,
        "--expected-engine-hash", "b" * 64,
        "--runtime-config", str(config),
        "--expected-runtime-config-sha256", config_hash,
        "--expected-configuration-hash", configuration_hash,
        "--equivalence-summary", str(summary),
        "--raw-projection-manifest", str(projection),
        "--state-manifest", str(state_manifest),
    ))
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "schema": "R6E1R_PRELOADED_STATE_VALIDATION_V1",
        "ok": False,
        "error_code": error_code,
    }
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("wrong_argument", "error_code"),
    (
        ("engine_manifest", "ENGINE_MANIFEST_HASH_MISMATCH"),
        ("runtime_config", "RUNTIME_CONFIG_HASH_MISMATCH"),
        ("engine_identity", "ENGINE_IDENTITY_MISMATCH"),
        ("configuration_identity", "CONFIGURATION_IDENTITY_MISMATCH"),
    ),
)
def test_preloaded_state_validator_refuses_wrong_supplied_hashes(
    tmp_path: Path, wrong_argument: str, error_code: str,
) -> None:
    (
        state, engine, engine_hash, config, config_hash, summary, projection,
        state_manifest,
    ) = (
        _valid_preload_fixture(tmp_path)
    )
    configuration_hash = hashlib.sha256(
        (json.dumps(json.loads(config.read_text()), sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    expected = {
        "engine_manifest": engine_hash,
        "runtime_config": config_hash,
        "engine_identity": "b" * 64,
        "configuration_identity": configuration_hash,
    }
    expected[wrong_argument] = "0" * 64
    command = [
        sys.executable, "-I", "-B", str(ROOT / "validate_preloaded_state.py"),
        "--state-root", str(state),
    ]
    for session in EXPECTED_REPLAY_SESSIONS:
        command.extend(("--expected-session", session))
    command.extend((
        "--engine-manifest", str(engine),
        "--expected-engine-manifest-sha256", expected["engine_manifest"],
        "--expected-engine-hash", expected["engine_identity"],
        "--runtime-config", str(config),
        "--expected-runtime-config-sha256", expected["runtime_config"],
        "--expected-configuration-hash", expected["configuration_identity"],
        "--equivalence-summary", str(summary),
        "--raw-projection-manifest", str(projection),
        "--state-manifest", str(state_manifest),
    ))
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)["error_code"] == error_code


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    (
        ("summary_status", "EQUIVALENCE_ACCEPTANCE_GATE_FAILED"),
        ("zero_gate", "EQUIVALENCE_ACCEPTANCE_GATE_FAILED"),
        ("reference_manifests", "REFERENCE_MANIFEST_GATE_FAILED"),
        ("seal", "EQUIVALENCE_SEAL_GATE_FAILED"),
        ("state_seal", "INCREMENTAL_STATE_SEAL_GATE_FAILED"),
        ("source_integrity", "COMMITTED_SOURCE_INTEGRITY_SEAL_FAILED"),
        ("projection_summary", "RAW_PROJECTION_SUMMARY_GATE_FAILED"),
        ("projection_hash", "RAW_PROJECTION_MANIFEST_HASH_MISMATCH"),
        ("projection_policy", "RAW_PROJECTION_POLICY_GATE_FAILED"),
        ("august_contract", "AUGUST_17_REJECTION_POLICY_UNVERIFIED"),
        ("source_evidence", "RAW_PROJECTION_SOURCE_MUTATION_EVIDENCE_FAILED"),
    ),
)
def test_preloaded_state_validator_refuses_unverified_equivalence_evidence(
    tmp_path: Path, mutation: str, error_code: str,
) -> None:
    (
        state, engine, engine_hash, config, config_hash, summary_path,
        projection_path, state_manifest,
    ) = (
        _valid_preload_fixture(tmp_path)
    )
    configuration_hash = hashlib.sha256(
        (
            json.dumps(
                json.loads(config.read_text()), sort_keys=True, separators=(",", ":"),
            )
            + "\n"
        ).encode()
    ).hexdigest()
    summary = json.loads(summary_path.read_text())
    projection = json.loads(projection_path.read_text())
    update_projection_hash = False
    if mutation == "summary_status":
        summary["status"] = "FAIL"
    elif mutation == "zero_gate":
        summary["component_failures"] = 1
    elif mutation == "reference_manifests":
        summary["reference_package_manifests"].pop()
    elif mutation == "seal":
        summary["incremental_a_seal"]["dirty_sessions_after_seal"] = [
            EXPECTED_REPLAY_SESSIONS[0]
        ]
    elif mutation == "state_seal":
        summary["incremental_a_seal"]["state_tree_sha256"] = "0" * 64
    elif mutation == "source_integrity":
        summary["incremental_a_seal"]["committed_source_integrity"] = {
            "source_files": 1,
            "prefix_blocks": 0,
        }
    elif mutation == "projection_summary":
        summary["raw_projection"]["reused_existing"] = True
    elif mutation == "projection_hash":
        projection["receipt_path_session_mismatches"] = 1
    elif mutation == "projection_policy":
        projection["causal_source_sessions"].remove("2026-08-17")
        update_projection_hash = True
    elif mutation == "august_contract":
        projection["contract_selection"]["2026-08-17"][
            "selection_authority"
        ] = "HARDCODED"
        update_projection_hash = True
    elif mutation == "source_evidence":
        projection["source_files"][0]["unchanged_after_projection"] = False
        update_projection_hash = True
    projection_path.write_text(json.dumps(projection))
    if update_projection_hash:
        summary["raw_projection"]["manifest_sha256"] = hashlib.sha256(
            projection_path.read_bytes()
        ).hexdigest()
    summary_path.write_text(json.dumps(summary))

    command = [
        sys.executable, "-I", "-B", str(ROOT / "validate_preloaded_state.py"),
        "--state-root", str(state),
    ]
    for session in EXPECTED_REPLAY_SESSIONS:
        command.extend(("--expected-session", session))
    command.extend((
        "--engine-manifest", str(engine),
        "--expected-engine-manifest-sha256", engine_hash,
        "--expected-engine-hash", "b" * 64,
        "--runtime-config", str(config),
        "--expected-runtime-config-sha256", config_hash,
        "--expected-configuration-hash", configuration_hash,
        "--equivalence-summary", str(summary_path),
        "--raw-projection-manifest", str(projection_path),
        "--state-manifest", str(state_manifest),
    ))
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "schema": "R6E1R_PRELOADED_STATE_VALIDATION_V1",
        "ok": False,
        "error_code": error_code,
    }
    assert str(tmp_path) not in result.stdout
    assert result.stderr == ""


def test_deployment_package_manifest_is_exact_and_hash_verified() -> None:
    repo = ROOT.parents[1]
    engine_manifest_path = repo / "manifests/r6e1r_engine_source_manifest.json"
    engine_manifest = json.loads(engine_manifest_path.read_text())
    package_path = repo / "manifests/r6e1r_deployment_package_manifest.json"
    package = json.loads(package_path.read_text())
    deployment_only = {
        "deploy/r6e1r/README.md",
        "deploy/r6e1r/r6e1r-activation.json.example",
        "deploy/r6e1r/r6e1r-readonly-gateway.service",
        "deploy/r6e1r/r6e1r-runtime-config.json.example",
        "deploy/r6e1r/r6e1r-shadow.service",
        "deploy/r6e1r/validate_preloaded_state.py",
        "manifests/r6e1r_engine_source_manifest.json",
        "manifests/r6e1r_engine_source_manifest.sha256",
    }
    expected = sorted(set(engine_manifest["allowlist"]) | deployment_only)
    assert package["schema"] == "R6E1R_DEPLOYMENT_PACKAGE_MANIFEST_V1"
    assert package["classification"] == CLASSIFICATION
    assert package["engine_source_manifest_sha256"] == hashlib.sha256(
        engine_manifest_path.read_bytes()
    ).hexdigest()
    assert package["engine_hash"] == engine_manifest["engine_hash"]
    runtime_config = json.loads(
        (repo / "deploy/r6e1r/r6e1r-runtime-config.json.example").read_text()
    )
    assert package["runtime_configuration_hash"] == hashlib.sha256(
        (json.dumps(runtime_config, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    assert package["allowlist"] == expected
    assert package["file_count"] == len(expected) == len(package["files"])
    assert [row["path"] for row in package["files"]] == expected
    for row in package["files"]:
        path = repo / row["path"]
        assert path.is_file() and not path.is_symlink()
        assert row["size"] == path.stat().st_size
        assert row["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    aggregate = hashlib.sha256()
    for row in package["files"]:
        aggregate.update(
            f'{row["path"]}\0{row["sha256"]}\0{row["size"]}\n'.encode()
        )
    assert package["package_hash"] == aggregate.hexdigest()
    package_sha = hashlib.sha256(package_path.read_bytes()).hexdigest()
    companion = (
        repo / "manifests/r6e1r_deployment_package_manifest.sha256"
    ).read_text().split()
    assert companion == [
        package_sha, "manifests/r6e1r_deployment_package_manifest.json",
    ]


class _ProbeHandler(BaseHTTPRequestHandler):
    readiness_status = 503
    readiness = {
        "ready": False,
        "reasons": ["STALE_DATA"],
        "availability_state": "STALE_PARTIAL",
        "checkpoint_valid": True,
        "future_joins": 0,
        "synchronization_tolerance_violations": 0,
        "manifest_verified": True,
    }

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            status = 200
            value = {"alive": True, "classification": CLASSIFICATION}
        elif self.path == "/api/readiness":
            status = self.readiness_status
            value = self.readiness
        else:
            status = 404
            value = {"error": "NOT_FOUND"}
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture()
def probe_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_health_helper_accepts_structured_stale_readiness(probe_server: str) -> None:
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    result = module["probe"](probe_server, 2.0)
    assert result["health_http_status"] == 200
    assert result["readiness_http_status"] == 503
    assert result["ready"] is False
    assert result["readiness_reasons"] == ["STALE_DATA"]
    assert result["checkpoint_valid"] is True
    assert result["future_joins"] == 0
    assert result["synchronization_tolerance_violations"] == 0
    assert result["manifest_verified"] is True


@pytest.mark.parametrize(
    "override",
    (
        {"reasons": ["CHECKPOINT_INTEGRITY_FAILED"]},
        {"checkpoint_valid": False},
        {"future_joins": 1},
        {"synchronization_tolerance_violations": 1},
        {"manifest_verified": False},
        {"reasons": []},
    ),
)
def test_health_helper_rejects_non_benign_503(
    probe_server: str, monkeypatch: pytest.MonkeyPatch, override: dict,
) -> None:
    monkeypatch.setattr(
        _ProbeHandler,
        "readiness",
        {**_ProbeHandler.readiness, **override},
    )
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    with pytest.raises(RuntimeError):
        module["probe"](probe_server, 2.0)


def test_gateway_bubblewrap_self_test_hides_same_uid_runtime() -> None:
    result = _run_in_gateway_systemd_boundary([
        "/app/deploy/r6e1r/read_only_gateway.py",
        "--backend", "http://127.0.0.1:18805", "--isolation-self-test",
    ])
    value = json.loads(result.stdout)
    assert value["collector_state_config_hidden"] is True
    assert value["user_runtime_hidden"] is True
    assert value["process_namespace_private"] is True
    assert value["visible_pid_count"] <= 2


def test_gateway_post_start_probe_runs_in_same_systemd_bubblewrap_boundary() -> None:
    result = _run_in_gateway_systemd_boundary([
        "/app/deploy/r6e1r/health_readiness_check.py", "--help",
    ])
    assert "--base-url BASE_URL" in result.stdout


@pytest.mark.parametrize(
    "value",
    (
        "https://127.0.0.1:8805",
        "http://user:password@127.0.0.1:8805",
        "http://127.0.0.1",
        "http://127.0.0.1:8805/api/health",
        "http://127.0.0.1:8805?target=elsewhere",
    ),
)
def test_health_helper_refuses_unsafe_or_ambiguous_origins(value: str) -> None:
    module = runpy.run_path(str(ROOT / "health_readiness_check.py"))
    with pytest.raises(ValueError):
        module["normalized_base_url"](value)


def test_health_helper_never_logs_credentials_from_invalid_origin() -> None:
    secret = "probe-password-must-not-appear"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "health_readiness_check.py"),
            "--base-url",
            f"http://user:{secret}@127.0.0.1:8805",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert json.loads(result.stdout)["base_url"] == "REDACTED_INVALID_ORIGIN"
