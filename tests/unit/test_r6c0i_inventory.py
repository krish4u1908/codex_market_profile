from pathlib import Path
import json
import os
import subprocess
import numpy as np
import pandas as pd
import pytest

from banknifty_profiler.inventory.engine import choose, profile, price_events
from banknifty_profiler.raw_io.reader import backward_join


def test_deterministic_winner_and_tie_break():
    assert choose({100.0: 5.0, 125.0: 5.0}, 112.5)[0] == 100.0
    assert choose({100.0: 5.0, 125.0: 5.0}, 112.5)[1] == "TIE_LOWER_BIN"


def test_profile_uses_bn_reference_bin_and_positive_weights_only():
    frame = pd.DataFrame({"px": [101.0, 112.0, 126.0], "w": [3.0, 4.0, -9.0]})
    result = profile(frame, 25)
    assert result["control_value"] == 100.0
    assert result["total_weight"] == 7.0


def test_backward_join_is_causal():
    tz = "Asia/Kolkata"
    oi = pd.DataFrame({"availability_timestamp": pd.to_datetime(["2026-08-13 09:15:01+05:30"]), "symbol": ["X"]})
    market = pd.DataFrame({
        "receipt_timestamp": pd.to_datetime(["2026-08-13 09:15:00.500+05:30", "2026-08-13 09:15:01.500+05:30"]),
        "last_price": [100.0, 200.0], "source_file": ["a", "a"], "source_row": [1, 2],
    })
    result = backward_join(oi, market, tolerance_seconds=5).iloc[0]
    assert result.matched_underlying_price == 100.0
    assert result.future_join == False


def test_backward_join_empty_index_keeps_unmatched_clock_timezone_aware():
    oi = pd.DataFrame({
        "availability_timestamp": pd.to_datetime(
            ["2026-08-28T09:15:00.100+05:30"]
        ),
    })
    market = pd.DataFrame(columns=[
        "receipt_timestamp", "last_price", "source_file", "source_row",
    ])

    result = backward_join(oi, market, tolerance_seconds=5).iloc[0]

    assert pd.isna(result.matched_price_timestamp)
    assert pd.isna(result.matched_underlying_price)
    assert pd.isna(result.join_age_seconds)
    assert result.future_join == False
    assert isinstance(
        backward_join(oi, market).matched_price_timestamp.dtype,
        pd.DatetimeTZDtype,
    )


def test_backward_join_refuses_naive_availability_clock():
    oi = pd.DataFrame({
        "availability_timestamp": pd.to_datetime(["2026-08-28T09:15:00.100"]),
    })
    market = pd.DataFrame(columns=[
        "receipt_timestamp", "last_price", "source_file", "source_row",
    ])

    with pytest.raises(ValueError, match="timezone-aware"):
        backward_join(oi, market, tolerance_seconds=5)


def test_volume_reset_and_first_counter_are_excluded():
    ts = pd.to_datetime(["2026-08-13 09:15:00+05:30", "2026-08-13 09:15:01+05:30", "2026-08-13 09:15:02+05:30"])
    market = pd.DataFrame({
        "symbol": ["F", "I", "F", "I", "F", "I"],
        "receipt_timestamp": [ts[0], ts[0], ts[1], ts[1], ts[2], ts[2]],
        "source_file": ["x"] * 6, "source_row": range(6),
        "cumulative_volume": [100, np.nan, 110, np.nan, 5, np.nan],
        "last_price": [101, 100, 102, 101, 103, 102],
    })
    result = price_events(market, "2026-08-13", "F", "I", 5)
    assert list(result.reject) == ["FIRST_VALID_COUNTER", "", "COUNTER_RESET"]
    assert result.w.notna().sum() == 1 and result.w.dropna().iloc[0] == 10


def test_signed_oi_weights_are_not_netted():
    delta = pd.Series([10.0, -7.0, 0.0])
    assert delta.clip(lower=0).sum() == 10.0
    assert (-delta.clip(upper=0)).sum() == 7.0


def test_no_outcome_or_trading_fields_in_canonical_schema():
    forbidden = {"outcome", "profit", "pnl", "target", "stop", "prediction", "trade"}
    source = Path(__file__).parents[2] / "src/banknifty_profiler/inventory/engine.py"
    text = source.read_text().lower()
    assert not any(f'"{field}"' in text for field in forbidden)


def test_executable_inventory_source_has_no_prohibited_dependency():
    source = Path(__file__).parents[2] / "src/banknifty_profiler/inventory/engine.py"
    text = source.read_text()
    forbidden = ["/opt/banknifty", "market_1m.csv", "locked_primitives", "sys.path", "SourceFileLoader", "spec_from_file_location", "8803", "8804"]
    assert [token for token in forbidden if token in text] == []


def test_cli_requires_all_explicit_arguments():
    result = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "banknifty_profiler.inventory.engine"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "required" in result.stderr


def test_cli_refuses_missing_data_root(tmp_path):
    config = tmp_path / "config.json"; config.write_text("{}")
    result = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "banknifty_profiler.inventory.engine", "--mode", "stream", "--data-root", str(tmp_path/"missing"), "--output-root", str(tmp_path/"out"), "--config", str(config)], capture_output=True, text=True)
    assert result.returncode != 0 and "data root missing" in result.stderr


def test_cli_refuses_nonempty_output(tmp_path):
    data = tmp_path / "data"; data.mkdir(); output = tmp_path / "out"; output.mkdir(); (output/"x").write_text("x")
    config = tmp_path / "config.json"; config.write_text("{}")
    result = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "banknifty_profiler.inventory.engine", "--mode", "stream", "--data-root", str(data), "--output-root", str(output), "--config", str(config)], capture_output=True, text=True)
    assert result.returncode != 0 and "must not exist" in result.stderr


def test_cli_refuses_research_derived_root(tmp_path):
    data = tmp_path / "research" / "derived"; data.mkdir(parents=True)
    config = tmp_path / "config.json"; config.write_text("{}")
    result = subprocess.run([os.environ.get("PYTHON", "python"), "-m", "banknifty_profiler.inventory.engine", "--mode", "stream", "--data-root", str(data), "--output-root", str(tmp_path/"out"), "--config", str(config)], capture_output=True, text=True)
    assert result.returncode != 0 and "derived analytical input root refused" in result.stderr


def test_sealed_stream_batch_reference_are_byte_identical():
    audit = Path(os.environ["R6C0I_AUDIT_ROOT"])
    reference = Path(os.environ["R6C0I_REFERENCE_CSV"])
    stream = (audit/"run_stream/canonical_inventory.csv").read_bytes()
    batch = (audit/"run_batch/canonical_inventory.csv").read_bytes()
    assert stream == batch == reference.read_bytes()


def test_sealed_output_has_exact_gate_counts():
    audit = Path(os.environ["R6C0I_AUDIT_ROOT"])
    rows = pd.read_csv(audit/"run_stream/canonical_inventory.csv")
    summary = json.loads((audit/"run_stream/summary.json").read_text())
    assert len(rows) == 255
    assert summary["future_joins"] == 0
    assert summary["current_session_leakage"] == 0
    assert summary["august_17_accepted"] is False


def test_discovered_chains_are_chronological_and_exclude_evaluation():
    audit = Path(os.environ["R6C0I_AUDIT_ROOT"])
    rows = pd.read_csv(audit/"run_stream/discovered_source_chains.csv")
    for row in rows.itertuples():
        sources = row.source_sessions.split("|")
        assert len(sources) == 3 and sources == sorted(sources)
        assert all(source < row.evaluation_date for source in sources)


def test_raw_file_open_audit_has_no_derived_inputs():
    audit = Path(os.environ["R6C0I_AUDIT_ROOT"])
    rows = pd.read_csv(audit/"run_stream/file_open_audit.csv")
    assert len(rows) > 0
    assert rows.path.str.contains(r"/(?:raw|oi)/\d{4}-\d{2}-\d{2}/(?:events|oi)_\d{2}\.jsonl$").all()
    assert not rows.path.str.contains("market_1m|research/vpoc",regex=True).any()
