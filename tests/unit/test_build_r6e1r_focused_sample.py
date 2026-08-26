from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[2] / "scripts/build_r6e1r_focused_sample.py"
HARNESS = Path(__file__).parents[2] / "scripts/run_r6e1r_equivalence.py"


def _module():
    spec = importlib.util.spec_from_file_location("build_r6e1r_focused_sample", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _harness_module():
    spec = importlib.util.spec_from_file_location(
        "run_r6e1r_equivalence_sample_test", HARNESS
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _line(value: dict) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode()


def _market(receipt: str, symbol: str, price: float) -> bytes:
    return _line(
        {
            "received_at": receipt,
            "event_time": receipt,
            "message": {"symbol": symbol, "ltp": price, "vol_traded_today": 10},
        }
    )


def test_builds_byte_exact_hourly_projection_and_compatibility_archives(tmp_path):
    module = _module()
    session = "2026-08-19"
    source = tmp_path / "authoritative"
    raw = source / "raw" / session
    oi = source / "oi" / session
    raw.mkdir(parents=True)
    oi.mkdir(parents=True)
    future = "NSE:BANKNIFTY26AUGFUT"
    index = "NSE:NIFTYBANK-INDEX"
    expiry = int(datetime(2026, 8, 26, tzinfo=timezone.utc).timestamp())

    excluded = _market(f"{session}T09:14:59+05:30", "NSE:OTHER", 1.0)
    index_line = _market(f"{session}T09:15:00.123456+05:30", index, 57_100.0)
    future_line = _market(f"{session}T09:15:01+05:30", future, 57_200.0)
    (raw / "events_09.jsonl").write_bytes(
        excluded + index_line + future_line + b'{"received_at":"incomplete"'
    )
    depth_line = _line(
        {
            "source": "future_depth",
            "request_time": f"{session}T09:15:02+05:30",
            "received_at": f"{session}T09:15:02+05:30",
            "response": {
                "d": {
                    future: {
                        "ltp": 57_201,
                        "v": 20,
                        "oi": 2_000_000,
                        "pdoi": 1_999_000,
                        "expiry": expiry,
                    }
                }
            },
        }
    )
    chain_line = _line(
        {
            "source": "option_chain",
            "request_time": f"{session}T09:15:03+05:30",
            "received_at": f"{session}T09:15:03+05:30",
            "response": {
                "data": {
                    "optionsChain": [
                        {
                            "symbol": "NSE:BANKNIFTY2681957000CE",
                            "strike_price": 57_000,
                            "expiry": expiry,
                            "oi": 100,
                        },
                        {
                            "symbol": "NSE:BANKNIFTY2681957000PE",
                            "strike_price": 57_000,
                            "expiry": expiry,
                            "oi": 110,
                        },
                    ]
                }
            },
        }
    )
    (oi / "oi_09.jsonl").write_bytes(depth_line + chain_line)
    for hour in (10, 11, 12):
        (raw / f"events_{hour:02d}.jsonl").write_bytes(b"")
        (oi / f"oi_{hour:02d}.jsonl").write_bytes(b"")
    output = tmp_path / "fixture"

    manifest = module.build_focused_sample(
        authoritative_root=source,
        output_root=output,
        session=session,
        start_ist="09:15",
        end_ist="12:05",
    )

    projected_raw = output / "collector/raw" / session / "events_09.jsonl"
    projected_oi = output / "collector/oi" / session / "oi_09.jsonl"
    assert projected_raw.read_bytes() == b"\n" + index_line + future_line
    assert projected_oi.read_bytes() == depth_line + chain_line
    assert (output / "raw.jsonl").read_bytes() == index_line + future_line
    assert (output / "oi.jsonl").read_bytes() == depth_line + chain_line
    assert manifest["canonical_symbols"]["futures"] == future
    assert manifest["record_counts"] == {
        "ce": 1,
        "futures": 1,
        "futures_oi": 1,
        "index": 1,
        "pe": 1,
    }
    assert manifest["source_mutations"] == 0
    assert all(row["unchanged"] for row in manifest["source_files"])
    assert len(manifest["collector_files"]) == 8
    assert manifest["selected_records"][0]["source_row"] == 2
    assert manifest["selected_records"][0]["projection_row"] == 2
    assert manifest["selected_records"][0]["source_byte_offset"] == len(excluded)
    assert manifest["selected_records"][0]["projection_byte_offset"] == 1
    assert manifest["source_files"][0]["incomplete_final_bytes_excluded"] > 0
    assert (output / "manifest.sha256").read_text().startswith(
        manifest["manifest_sha256"]
    )

    harness = _harness_module()
    harness._validate_focused_fixture_manifest(
        output / "collector",
        expected_manifest_sha256=manifest["manifest_sha256"],
    )
    projected_raw.write_bytes(b"X" + projected_raw.read_bytes()[1:])
    try:
        harness._validate_focused_fixture_manifest(
            output / "collector",
            expected_manifest_sha256=manifest["manifest_sha256"],
        )
    except ValueError as error:
        assert "collector identity mismatch" in str(error)
    else:
        raise AssertionError("collector tamper was accepted")
