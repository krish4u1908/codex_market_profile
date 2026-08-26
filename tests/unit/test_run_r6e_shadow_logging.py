from __future__ import annotations

import json
from pathlib import Path
import runpy


SCRIPT = Path("scripts/run_r6e_shadow.py")


def test_runtime_logs_are_structured_and_never_include_exception_detail(capsys):
    module = runpy.run_path(str(SCRIPT))
    emit = module["emit_runtime_log"]
    emit("SERVICE_RUNNING", "RUNNING")
    emit(
        "INGESTION_CYCLE_ERROR",
        "DEGRADED",
        error=RuntimeError(
            "secret-token raw={\"received_at\":\"private\"} "
            "/opt/banknifty-collector/data-prod-v4/raw/private.jsonl"
        ),
    )

    output = capsys.readouterr().out
    assert "secret-token" not in output
    assert "received_at" not in output
    assert "/opt/" not in output
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows == [
        {
            "classification": (
                "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
            ),
            "component": "r6e1r-shadow",
            "event": "SERVICE_RUNNING",
            "status": "RUNNING",
        },
        {
            "classification": (
                "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
            ),
            "component": "r6e1r-shadow",
            "error_type": "RuntimeError",
            "event": "INGESTION_CYCLE_ERROR",
            "status": "DEGRADED",
        },
    ]


def test_runtime_entrypoint_suppresses_tracebacks_and_error_text(capsys):
    module = runpy.run_path(str(SCRIPT))

    def fail_with_private_detail():
        raise RuntimeError(
            "secret-token raw={\"received_at\":\"private\"} "
            "/opt/banknifty-collector/data-prod-v4/raw/private.jsonl"
        )

    entrypoint = module["entrypoint"]
    entrypoint.__globals__["main"] = fail_with_private_detail
    assert entrypoint() == 1

    output = capsys.readouterr().out
    assert "secret-token" not in output
    assert "received_at" not in output
    assert "/opt/" not in output
    assert json.loads(output) == {
        "classification": (
            "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
        ),
        "component": "r6e1r-shadow",
        "error_type": "RuntimeError",
        "event": "SERVICE_FATAL",
        "status": "TERMINATED",
    }

    source = SCRIPT.read_text()
    assert 'state.last_error = f"INGESTION_ERROR:{error_type}"' in source
    assert "traceback.print" not in source
    assert "raise error" not in source
    assert "str(error)" not in source
    assert "repr(error)" not in source


class _RecoveredOrchestrator:
    def __init__(self, pending):
        self.pending = set(pending)
        self.finalized = []

    def pending_session_dates(self):
        return tuple(sorted(self.pending))

    def finalize_session(self, session):
        self.finalized.append(session)
        self.pending.discard(session)


class _IntegrityVerifier:
    def __init__(self):
        self.sessions = []

    def verify_committed_sources(self, sessions):
        self.sessions.extend(sessions)


def test_first_next_day_poll_finalizes_recovered_session_in_order():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    ingestor = _IntegrityVerifier()
    orchestrator = _RecoveredOrchestrator(["2026-08-26"])

    newest, finalized = finalize(
        ingestor, orchestrator, ["2026-08-27"],
    )

    assert newest == "2026-08-27"
    assert finalized == ("2026-08-26",)
    assert ingestor.sessions == ["2026-08-26"]
    assert orchestrator.finalized == ["2026-08-26"]


def test_multi_date_catchup_finalizes_every_prior_session_chronologically():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    ingestor = _IntegrityVerifier()
    orchestrator = _RecoveredOrchestrator(
        ["2026-08-25", "2026-08-26"],
    )

    newest, finalized = finalize(
        ingestor, orchestrator, ["2026-08-26", "2026-08-27"],
    )

    assert newest == "2026-08-27"
    assert finalized == ("2026-08-25", "2026-08-26")
    assert ingestor.sessions == ["2026-08-25", "2026-08-26"]
    assert orchestrator.finalized == ["2026-08-25", "2026-08-26"]


def test_integrity_failure_prevents_session_finalization():
    module = runpy.run_path(str(SCRIPT))
    finalize = module["finalize_prior_sessions"]
    orchestrator = _RecoveredOrchestrator(["2026-08-26"])

    class RefusingIntegrity:
        def verify_committed_sources(self, _sessions):
            raise ValueError("synthetic integrity refusal")

    try:
        finalize(RefusingIntegrity(), orchestrator, ["2026-08-27"])
    except ValueError as error:
        assert str(error) == "synthetic integrity refusal"
    else:
        raise AssertionError("integrity refusal did not propagate")
    assert orchestrator.finalized == []
