from datetime import date, datetime, timezone
from pathlib import Path
import tomllib

import pytest

from banknifty_profiler.new_divergence.clock import IST, iso_ist, parse_instant, session_date
from banknifty_profiler.new_divergence.contracts import EngineConfig
from banknifty_profiler.new_divergence.configuration import load_config
from banknifty_profiler.new_divergence.provenance import RUNTIME_VERSION


def test_strict_clock_normalizes_one_instant_without_rounding() -> None:
    value = parse_instant("2031-04-07T09:45:00.123456+05:30")
    assert value == datetime(2031, 4, 7, 4, 15, 0, 123456, tzinfo=timezone.utc)
    assert iso_ist(value) == "2031-04-07T09:45:00.123456+05:30"
    assert session_date(value) == date(2031, 4, 7)


def test_naive_clock_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-naive"):
        parse_instant("2031-04-07T09:45:00")


def test_research_weight_cannot_be_enabled() -> None:
    with pytest.raises(ValueError, match="production_weight"):
        EngineConfig(production_weight=1)


def test_horizon_gap_tolerance_must_be_positive() -> None:
    with pytest.raises(ValueError, match="horizon_gap_tolerance_seconds"):
        EngineConfig(horizon_gap_tolerance_seconds=0)


def test_timezone_constant_is_explicit() -> None:
    assert IST.key == "Asia/Kolkata"


def test_checked_in_config_and_package_version_match_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    assert load_config(root / "configs" / "new_divergence_v1.json") == EngineConfig()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == RUNTIME_VERSION
