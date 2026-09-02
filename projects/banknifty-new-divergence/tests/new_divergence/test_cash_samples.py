from __future__ import annotations

import csv
from datetime import date
import json
from pathlib import Path

import pytest

from banknifty_profiler.new_divergence.api import ProjectionReadModel
from banknifty_profiler.new_divergence.cash_samples import (
    MANIFEST_FILE,
    PARAMETERS,
    SAMPLE_FILE,
    generate_samples,
    generate_session_sample,
    validate_sample_bundle,
)
from banknifty_profiler.new_divergence.cli import main
from banknifty_profiler.new_divergence.contracts import EngineConfig
from banknifty_profiler.new_divergence.output import publish_run, write_session_catalog
from banknifty_profiler.new_divergence.projection import build_browser

from .helpers import green_episode_events


DAY = date(2031, 4, 7)
FIELDS = (
    "minute",
    "symbol",
    "instrument_class",
    "ltp_close",
    "minute_volume",
    "last_received_time",
)


def _source_tree(
    root: Path,
    *,
    missing_second_volume: bool = False,
    reference_hhmm: str = "09:44",
) -> Path:
    data = root / "data-prod-v4"
    minute = data / "minute" / DAY.isoformat()
    minute.mkdir(parents=True)
    rows = [
        (reference_hhmm, "NSE:AAA-EQ", 100, 1, f"{reference_hhmm}:59"),
        (reference_hhmm, "NSE:BBB-EQ", 200, 2, f"{reference_hhmm}:59"),
        ("09:45", "NSE:AAA-EQ", 101, 10, "09:45:58"),
        ("09:45", "NSE:BBB-EQ", 199, 20, "09:45:59"),
        ("09:46", "NSE:AAA-EQ", 102, 12, "09:46:59"),
        ("09:46", "NSE:BBB-EQ", 201, None if missing_second_volume else 30, "09:46:59"),
    ]
    with (minute / "market_1m.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for hhmm, symbol, price, volume, receipt in rows:
            writer.writerow({
                "minute": f"{DAY}T{hhmm}:00+05:30",
                "symbol": symbol,
                "instrument_class": "cash",
                "ltp_close": price,
                "minute_volume": "" if volume is None else volume,
                "last_received_time": f"{DAY}T{receipt}+05:30",
            })
    metadata = data / "metadata"
    metadata.mkdir()
    (metadata / "startup_20310407T090000+0530-1.json").write_text(json.dumps({
        "started_at": f"{DAY}T09:00:00+05:30",
        "constituent_weights": {"AAA": 60, "BBB": 40},
        "finalize_delay": 8,
        "market_schedule": {"cash_continuous_close_exclusive": "09:47"},
    }), encoding="utf-8")
    return data


def _rows(directory: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (directory / SAMPLE_FILE).read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_sample_generator_publishes_exactly_two_causal_parameters(tmp_path) -> None:
    data = _source_tree(tmp_path)
    output = tmp_path / "sessions"
    result = generate_session_sample(data, output, DAY)
    assert result["status"] == "GENERATED"
    directory = output / DAY.isoformat()
    rows = _rows(directory)
    assert len(rows) == 2
    assert rows[0]["minute_ist"] == "2031-04-07T09:45:00+05:30"
    assert rows[0]["t"] == "2031-04-07T04:16:08.000000Z"
    assert rows[0]["cash_breadth"] == 0.0
    assert rows[0]["index_participant_volume"] == 30
    assert rows[1]["cash_breadth"] == 100.0
    assert rows[1]["index_participant_volume"] == 42
    assert all(row["status"] == "VALID" for row in rows)

    manifest = json.loads((directory / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["parameters"] == list(PARAMETERS)
    assert manifest["divergence_engine_input"] is False
    assert manifest["production_weight"] == 0
    assert manifest["derivation"]["reference_rule"] == (
        "EXACT_0944_BUCKET_CLOSE_AT_0945_IST"
    )
    assert validate_sample_bundle(directory, expected_session=DAY.isoformat())["valid"] is True
    assert generate_session_sample(data, output, DAY)["status"] == "UNCHANGED"


def test_missing_constituent_volume_fails_only_that_parameter_closed(tmp_path) -> None:
    data = _source_tree(tmp_path, missing_second_volume=True)
    output = tmp_path / "sessions"
    generate_session_sample(data, output, DAY)
    second = _rows(output / DAY.isoformat())[1]
    assert second["cash_breadth"] == 100.0
    assert second["index_participant_volume"] is None
    assert second["breadth_coverage_count"] == 2
    assert second["volume_coverage_count"] == 1
    assert second["status"] == "INCOMPLETE_VOLUME"


def test_manifest_cannot_assign_engine_weight_to_cash_parameters(tmp_path) -> None:
    data = _source_tree(tmp_path)
    output = tmp_path / "sessions"
    generate_session_sample(data, output, DAY)
    directory = output / DAY.isoformat()
    manifest_path = directory / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["production_weight"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = validate_sample_bundle(directory, expected_session=DAY.isoformat())
    assert result["valid"] is False
    assert "PRODUCTION_WEIGHT_MISMATCH" in result["reasons"]


def test_breadth_does_not_fall_back_to_a_stale_pre_0945_reference(tmp_path) -> None:
    data = _source_tree(tmp_path, reference_hhmm="09:43")
    output = tmp_path / "sessions"
    generate_session_sample(data, output, DAY)
    rows = _rows(output / DAY.isoformat())
    assert all(row["cash_breadth"] is None for row in rows)
    assert all(row["breadth_coverage_count"] == 0 for row in rows)
    assert all(row["index_participant_volume"] is not None for row in rows)
    manifest = json.loads(
        (output / DAY.isoformat() / MANIFEST_FILE).read_text(encoding="utf-8")
    )
    assert manifest["derivation"]["reference_status"] == "INCOMPLETE_0945_REFERENCE"


def test_all_date_generation_discovers_minute_tree_and_catalogues_sample_only(tmp_path) -> None:
    data = _source_tree(tmp_path)
    output = tmp_path / "sessions"
    result = generate_samples(data, output, stability_seconds=0)
    assert result["status_counts"] == {"GENERATED": 1}
    catalog = write_session_catalog(output)
    assert catalog["session_root_contract"] == "RUN_ROOT/YYYY-MM-DD"
    assert catalog["session_count"] == 1
    entry = catalog["sessions"][0]
    assert entry["eligible"] is False
    assert entry["cash_sample_available"] is True
    assert entry["cash_parameters"] == list(PARAMETERS)
    assert entry["run_integrity"]["reasons"] == ["MISSING_VERIFIED_DIVERGENCE_RUN"]


def test_replay_atomically_promotes_sample_only_directory_and_browser_prefixes_cash(
    tmp_path,
) -> None:
    data = _source_tree(tmp_path)
    output = tmp_path / "sessions"
    generate_session_sample(data, output, DAY)
    events = green_episode_events()
    run = publish_run(
        output,
        DAY,
        events,
        EngineConfig(),
        source={"kind": "SYNTHETIC_SAMPLE_PROMOTION"},
    )
    assert run == output / DAY.isoformat()
    assert (run / "summary.json").is_file()
    assert validate_sample_bundle(run, expected_session=DAY.isoformat())["valid"] is True

    browser = build_browser(output, tmp_path / "browser")
    payload = ProjectionReadModel(browser).session(DAY.isoformat())
    assert payload["cash_participation"]["retained"] is True
    assert len(payload["cash_participation"]["rows"]) == 2
    assert payload["projection_window"]["start"] == payload["summary"]["first_observation"]
    assert payload["projection_window"]["bar_analysis_start"] == "2031-04-07T04:15:00.000000Z"
    prefix = ProjectionReadModel(browser).session(
        DAY.isoformat(), as_of="2031-04-07T04:16:08Z"
    )
    assert len(prefix["cash_participation"]["rows"]) == 1
    assert prefix["availability"]["future_cash_participation_returned"] is False


def test_output_root_inside_collector_tree_is_refused(tmp_path) -> None:
    data = _source_tree(tmp_path)
    with pytest.raises(ValueError, match="must not be inside"):
        generate_samples(data, data / "samples", stability_seconds=0)


def test_cli_returns_retry_status_while_collector_file_is_still_active(tmp_path) -> None:
    data = _source_tree(tmp_path)
    output = tmp_path / "sessions"
    assert main([
        "generate-samples",
        "--data-root", str(data),
        "--output-root", str(output),
        "--stability-seconds", "3600",
    ]) == 3
    assert not (output / DAY.isoformat() / SAMPLE_FILE).exists()
