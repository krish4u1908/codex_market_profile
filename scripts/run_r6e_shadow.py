#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import threading
import time
import uuid
from pathlib import Path

from banknifty_profiler.shadow.api import create_server
from banknifty_profiler.shadow.contracts import validate_shadow_contract
from banknifty_profiler.shadow.ingest import IncrementalJSONLIngestor
from banknifty_profiler.shadow.orchestrator import LiveAnalyticalOrchestrator
from banknifty_profiler.shadow.state import ShadowState


CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
LOG_COMPONENT = "r6e1r-shadow"


def _safe_log_token(value: object, fallback: str) -> str:
    token = str(value)
    return token if token and token.replace("_", "").isalnum() else fallback


def emit_runtime_log(
    event: str,
    status: str,
    *,
    error: BaseException | None = None,
) -> None:
    """Emit one bounded structured record without raw or exception detail."""
    record = {
        "classification": CLASSIFICATION,
        "component": LOG_COMPONENT,
        "event": _safe_log_token(event, "RUNTIME_EVENT"),
        "status": _safe_log_token(status, "UNKNOWN"),
    }
    if error is not None:
        record["error_type"] = _safe_log_token(
            type(error).__name__, "RUNTIME_ERROR"
        )
    print(
        json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        flush=True,
    )


def finalize_prior_sessions(
    ingestor: IncrementalJSONLIngestor,
    orchestrator: LiveAnalyticalOrchestrator,
    observed_sessions: list[str],
) -> tuple[str | None, tuple[str, ...]]:
    """Seal every recovered/live session strictly before the newest one."""
    pending = set(orchestrator.pending_session_dates()) | set(observed_sessions)
    if not pending:
        return None, ()
    newest = max(pending)
    finalized = []
    for session_date in sorted(session for session in pending if session < newest):
        # Full-prefix verification is a session boundary, not poll-time work.
        # No arbitrary old-block rewrite can be promoted into sealed replay.
        ingestor.verify_committed_sources([session_date])
        orchestrator.finalize_session(session_date)
        finalized.append(session_date)
    return newest, tuple(finalized)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--activation", type=Path, required=True)
    args = parser.parse_args()

    contract = validate_shadow_contract(
        args.data_root, args.state_root, args.config, args.bind, args.mode
    )
    contract["raw_run_id"] = "R6E-" + uuid.uuid4().hex.upper()
    activation = json.loads(args.activation.read_text())
    contract["minimum_session_date"] = activation["activation_day"]
    ingestor = IncrementalJSONLIngestor(contract)
    orchestrator = LiveAnalyticalOrchestrator(
        contract, ledgers=ingestor.ledgers
    )
    ingestor.register_callback(orchestrator)
    state = ShadowState(ingestor, activation, orchestrator)
    server = create_server(state, args.bind, args.port)
    stop = threading.Event()
    last_refresh = 0.0
    refresh_seconds = float(contract["config"]["analytical_refresh_seconds"])
    active_error_type = ""

    def halt(*_: object) -> None:
        stop.set()
        server.shutdown()

    signal.signal(signal.SIGTERM, halt)
    signal.signal(signal.SIGINT, halt)
    emit_runtime_log("SERVICE_STARTING", "STARTING")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    emit_runtime_log("SERVICE_RUNNING", "RUNNING")
    try:
        while not stop.is_set():
            try:
                observations = ingestor.poll()
                observed_sessions = sorted(
                    {row.session_date for row in observations}
                )
                _, finalized_sessions = finalize_prior_sessions(
                    ingestor, orchestrator, observed_sessions,
                )
                for _session_date in finalized_sessions:
                    emit_runtime_log("SESSION_FINALIZED", "SEALED")

                # Analytical rebuilds are bounded by the configured refresh
                # interval; callback staging is already durable and API reads
                # remain read-only.
                current = time.monotonic()
                if current - last_refresh >= refresh_seconds:
                    orchestrator.flush()
                    last_refresh = current
                orchestrator.refresh_staleness()
                state.last_error = ""
                if active_error_type:
                    emit_runtime_log("INGESTION_RECOVERED", "RUNNING")
                active_error_type = ""
            except Exception as error:
                error_type = _safe_log_token(
                    type(error).__name__, "RUNTIME_ERROR"
                )
                state.last_error = f"INGESTION_ERROR:{error_type}"
                if error_type != active_error_type:
                    emit_runtime_log(
                        "INGESTION_CYCLE_ERROR", "DEGRADED", error=error
                    )
                active_error_type = error_type
            stop.wait(float(contract["config"]["poll_interval_seconds"]))
    finally:
        emit_runtime_log("SERVICE_STOPPING", "STOPPING")
        server.server_close()
        try:
            orchestrator.flush()
        finally:
            ingestor.close()
        emit_runtime_log("SERVICE_STOPPED", "STOPPED")
    return 0


def entrypoint() -> int:
    try:
        return main()
    except Exception as error:
        # Never let an unhandled traceback place paths, records, configuration,
        # or exception text into the service journal.
        emit_runtime_log("SERVICE_FATAL", "TERMINATED", error=error)
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
