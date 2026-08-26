import copy
from pathlib import Path

import pytest

from banknifty_profiler.runtime.anchors import EpisodeAnchor, contract_hash, validate
from banknifty_profiler.runtime.configuration import (
    canonical_configuration_sha256,
    validate_canonical_runtime_config,
)


def canonical():
    return {
        "timezone": "Asia/Kolkata",
        "synchronization_tolerance_ms": 2000,
        "sessions": ["2026-08-20"],
    }


def test_valid_frozen_configuration_is_accepted():
    assert validate_canonical_runtime_config(canonical()) == canonical()


@pytest.mark.parametrize("value", ["UTC", "IST", "asia/kolkata", " Asia/Kolkata", "+05:30", None])
def test_invalid_timezone_is_rejected(value):
    config = canonical()
    if value is None:
        config.pop("timezone")
    else:
        config["timezone"] = value
    with pytest.raises(ValueError, match="timezone must be exactly"):
        validate_canonical_runtime_config(config)


@pytest.mark.parametrize("value", [1999, 2001, -1, 0, "2000", 2000.0, True, None])
def test_invalid_tolerance_is_rejected(value):
    config = canonical()
    if value is None:
        config.pop("synchronization_tolerance_ms")
    else:
        config["synchronization_tolerance_ms"] = value
    with pytest.raises(ValueError, match="integer 2000"):
        validate_canonical_runtime_config(config)


@pytest.mark.parametrize("value", [0, 2, 4.999, 5.001, "5", True, None])
def test_invalid_inventory_tolerance_is_rejected(value):
    config = canonical()
    config["inventory_join_tolerance_seconds"] = value
    with pytest.raises(ValueError, match="inventory_join_tolerance_seconds"):
        validate_canonical_runtime_config(config)


def test_configuration_hash_changes_when_timezone_changes(tmp_path):
    valid = canonical()
    altered = copy.deepcopy(valid)
    altered["timezone"] = "UTC"
    valid_path = tmp_path / "valid.json"
    altered_path = tmp_path / "altered.json"
    valid_path.write_text(str(valid))
    altered_path.write_text(str(altered))
    assert contract_hash([], valid_path) != contract_hash([], altered_path)
    with pytest.raises(ValueError):
        canonical_configuration_sha256(altered)
    assert canonical_configuration_sha256(valid) == canonical_configuration_sha256(valid)


def test_configuration_hash_changes_when_tolerance_changes(tmp_path):
    valid = canonical()
    altered = copy.deepcopy(valid)
    altered["synchronization_tolerance_ms"] = 2001
    valid_path = tmp_path / "valid.json"
    altered_path = tmp_path / "altered.json"
    valid_path.write_text(str(valid))
    altered_path.write_text(str(altered))
    assert contract_hash([], valid_path) != contract_hash([], altered_path)
    with pytest.raises(ValueError):
        canonical_configuration_sha256(altered)
    assert canonical_configuration_sha256(valid) == canonical_configuration_sha256(valid)


def test_mismatched_typed_anchor_is_rejected():
    anchor = EpisodeAnchor(
        "E1", "G1", "2026-08-20", "GREEN",
        "2026-08-20T10:00:00+05:30", "2026-08-20T10:30:00+05:30",
        "2026-08-20T11:00:00+05:30", 57000, 57100, 100,
        "index|futures", "RUN", "VALID_CONFIG_HASH",
    )
    with pytest.raises(ValueError, match="hash mismatch"):
        validate([anchor], "RUN", "ALTERED_CONFIG_HASH")


def test_canonical_entrypoints_offer_no_runtime_invariant_override():
    root = Path(__file__).parents[2]
    for relative in ("scripts/run_r6b3.py", "scripts/run_raw_divergence.py"):
        text = (root / relative).read_text()
        assert "validate_canonical_runtime_config" in text
        assert "add_argument('--timezone'" not in text
        assert 'add_argument("--timezone"' not in text
        assert "add_argument('--synchronization-tolerance-ms'" not in text
        assert 'add_argument("--synchronization-tolerance-ms"' not in text
