from dataclasses import replace
from pathlib import Path
import pytest

from banknifty_profiler.runtime.anchors import EpisodeAnchor, validate


def anchor():
    return EpisodeAnchor("E1","G1","2026-08-20","GREEN","2026-08-20T10:00:00+05:30","2026-08-20T10:30:00+05:30","2026-08-20T11:00:00+05:30",57000,57100,100,"i|f","RUN1","HASH1")


def test_valid_anchor_contract(): validate([anchor()],"RUN1","HASH1")
def test_hash_mismatch_rejected():
    with pytest.raises(ValueError,match="hash mismatch"):validate([anchor()],"RUN1","WRONG")
def test_other_run_rejected():
    with pytest.raises(ValueError,match="another or unknown"):validate([anchor()],"RUN2","HASH1")
def test_duplicate_episode_rejected():
    with pytest.raises(ValueError,match="duplicate"):validate([anchor(),anchor()],"RUN1","HASH1")
def test_naive_timestamp_rejected():
    with pytest.raises(ValueError,match="timezone-aware"):validate([replace(anchor(),confirmation_timestamp="2026-08-20T10:00:00")],"RUN1","HASH1")
def test_future_dated_outside_session_rejected():
    with pytest.raises(ValueError,match="outside"):validate([replace(anchor(),confirmation_timestamp="2026-08-21T10:00:00+05:30")],"RUN1","HASH1")
def test_cutoff_before_confirmation_rejected():
    with pytest.raises(ValueError,match="precedes"):validate([replace(anchor(),lifecycle_cutoff="2026-08-20T09:59:00+05:30")],"RUN1","HASH1")


def test_production_config_has_no_machine_root():
    text=(Path(__file__).parents[2]/"configs/r6b3_participation.json").read_text()
    assert "/opt/" not in text and "raw_market_root" not in text and "raw_oi_root" not in text


def test_production_source_has_no_historical_dependency():
    root=Path(__file__).parents[2]
    text=(root/"scripts/run_r6b3.py").read_text()+(root/"src/banknifty_profiler/participation/views.py").read_text()
    forbidden=("clean_combined_profiler_r4","clean_combined_profiler_r5","inventory_horizon_revision_1","sys.path","SourceFileLoader","spec_from_file_location")
    assert [x for x in forbidden if x in text]==[]
