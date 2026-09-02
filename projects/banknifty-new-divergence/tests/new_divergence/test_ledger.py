import json

import pytest

from banknifty_profiler.new_divergence.engine import run_replay
from banknifty_profiler.new_divergence.ledger import verify_ledger

from .helpers import green_episode_events


def test_ledger_verifies_and_detects_tampering(tmp_path) -> None:
    path = tmp_path / "transitions.jsonl"
    run_replay(green_episode_events(), ledger_path=path)
    assert verify_ledger(path)["valid"]
    rows = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(rows[0])
    first["colour"] = "RED"
    rows[0] = json.dumps(first)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    result = verify_ledger(path)
    assert not result["valid"]
    assert result["reason"] == "line 1: record_hash mismatch"


def test_engine_refuses_to_resume_without_state_restoration(tmp_path) -> None:
    path = tmp_path / "transitions.jsonl"
    run_replay(green_episode_events(), ledger_path=path)
    with pytest.raises(FileExistsError, match="state restoration"):
        run_replay(green_episode_events(), ledger_path=path)
