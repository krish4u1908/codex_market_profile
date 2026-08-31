"""Command line boundary for replay, nightly context, projection, and serving."""

from __future__ import annotations

import argparse
from datetime import date, time
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tarfile

from .adapters import ReplayAdapter, load_events
from .cash_samples import generate_samples
from .clock import session_instant
from .collector_archive import CollectorArchiveAdapter, OI_MEMBER, RAW_MEMBER
from .configuration import load_config
from .contracts import BasisObservation, EpisodeTransition
from .ledger import verify_ledger
from .outcomes import evaluate_basis_outcomes, write_outcomes
from .output import publish_run, verify_run, write_session_catalog
from .projection import build_browser
from .service import serve


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _local_instant(day: date, value: str, field: str):
    try:
        local_time = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid {field} local time: {value!r}") from error
    if local_time.tzinfo is not None:
        raise ValueError(f"{field} must be an IST wall-clock time without an offset")
    return session_instant(day, local_time)


def _replay_events(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    paths = [Path(value).resolve() for value in args.events]
    materialized = [event for path in paths for event in load_events(path)]
    replay = ReplayAdapter(materialized)
    if not replay.events:
        raise ValueError("normalized input contains no events")
    session = replay.events[0].session
    source = {
        "schema": "NORMALIZED_EVENT_SOURCE_V1",
        "kind": "NORMALIZED_EVENT_FILES",
        "files": [
            {"path": str(path), "sha256": _file_sha256(path), "size_bytes": path.stat().st_size}
            for path in paths
        ],
    }
    destination = publish_run(
        args.output_root,
        session,
        replay.stream(as_of=args.as_of),
        config,
        source=source,
        finalize_at=args.finalize_at,
    )
    print(destination)
    return 0


def _replay_archive(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    day = date.fromisoformat(args.session)
    start = _local_instant(day, args.start or config.session_start.isoformat(), "start")
    end = _local_instant(day, args.end or config.session_end.isoformat(), "end")
    archive = Path(args.archive).resolve()
    digest = None if args.skip_archive_hash else _file_sha256(archive)
    adapter = CollectorArchiveAdapter(
        archive,
        day,
        start=start,
        end=end,
        futures_symbol=args.futures_symbol,
        include_auxiliary=not args.basis_only,
        chunk_size=args.chunk_size,
    )

    def source_manifest() -> dict[str, object]:
        return {
            **adapter.stats,
            "archive_sha256": digest,
            "archive_hash_status": "SKIPPED_BY_OPERATOR" if digest is None else "COMPUTED",
        }

    destination = publish_run(
        args.output_root,
        day,
        adapter.stream(),
        config,
        source=source_manifest,
        finalize_at=end if args.finalize else None,
    )
    print(destination)
    return 0


def _catalog(args: argparse.Namespace) -> int:
    catalog = write_session_catalog(Path(args.run_root))
    print(json.dumps(catalog, indent=2, sort_keys=True))
    return 0


def _generate_samples(args: argparse.Namespace) -> int:
    sessions = (
        None
        if not args.session
        else tuple(date.fromisoformat(value) for value in args.session)
    )
    result = generate_samples(
        args.data_root,
        args.output_root,
        sessions=sessions,
        stability_seconds=args.stability_seconds,
        force=args.force,
    )
    write_session_catalog(args.output_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    status_counts = result.get("status_counts", {})
    if int(status_counts.get("MISSING_SOURCE", 0)):
        return 2
    if int(status_counts.get("SOURCE_NOT_STABLE", 0)):
        # The 15:40 timer can overlap the collector's final derivative-minute
        # write. A non-zero status lets systemd retry after RestartSec rather
        # than silently skipping the day until the next timer activation.
        return 3
    return 0


def _build_browser(args: argparse.Namespace) -> int:
    destination = build_browser(
        args.run_root,
        args.output_root,
        context_state_root=args.context_state_root,
        enable_oi_vpoc=args.oi_vpoc,
        enable_volume_profile=args.volume_profile,
    )
    print(destination)
    return 0


def _verify(args: argparse.Namespace) -> int:
    result = verify_ledger(Path(args.ledger))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


def _verify_complete_run(args: argparse.Namespace) -> int:
    result = verify_run(Path(args.run_directory))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


def _evaluate_outcomes(args: argparse.Namespace) -> int:
    run = Path(args.run_directory).resolve()
    integrity = verify_run(run)
    if not integrity["valid"]:
        raise ValueError(f"outcomes refused because run integrity is invalid: {integrity['reasons']}")
    ledger = run / "transitions.jsonl"
    status = verify_ledger(ledger)
    if not status["valid"]:
        raise ValueError(f"outcomes refused because transition ledger is invalid: {status['reason']}")
    with ledger.open(encoding="utf-8") as handle:
        transitions = [EpisodeTransition.from_dict(json.loads(line)) for line in handle if line.strip()]
    with (run / "basis_observations.jsonl").open(encoding="utf-8") as handle:
        observations = [BasisObservation.from_dict(json.loads(line)) for line in handle if line.strip()]
    rows = evaluate_basis_outcomes(
        transitions,
        observations,
        horizons_minutes=tuple(args.horizons),
    )
    write_outcomes(args.output, rows)
    print(args.output)
    return 0


def _inspect_archive(args: argparse.Namespace) -> int:
    path = Path(args.archive).resolve()
    sessions: dict[str, dict[str, list[str]]] = {}
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            raw = RAW_MEMBER.search(member.name)
            oi = OI_MEMBER.search(member.name)
            match = raw or oi
            if match is None:
                continue
            kind = "raw" if raw else "oi"
            sessions.setdefault(match.group("session"), {"raw": [], "oi": []})[kind].append(member.name)
    result = {
        "schema": "COLLECTOR_ARCHIVE_INVENTORY_V1",
        "archive": str(path),
        "size_bytes": path.stat().st_size,
        "sessions": {
            day: {kind: sorted(names) for kind, names in groups.items()}
            for day, groups in sorted(sessions.items())
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _serve(args: argparse.Namespace) -> int:
    if not args.acknowledge_research_only:
        raise ValueError("serve requires --acknowledge-research-only")
    serve(
        args.directory,
        args.host,
        args.port,
        codex_host=args.codex_host,
        codex_port=args.codex_port,
        codex_cwd=args.codex_cwd,
        codex_token_file=args.codex_token_file,
        commentary_db=args.commentary_db,
    )
    return 0


def _build_live_browser(args: argparse.Namespace) -> int:
    from .live_service import build_live_browser

    print(build_live_browser(args.output_root))
    return 0


def _serve_live(args: argparse.Namespace) -> int:
    if not args.acknowledge_research_only:
        raise ValueError("serve-live requires --acknowledge-research-only")
    from .live_runtime import LiveRuntime
    from .live_service import serve_live

    runtime = LiveRuntime(
        args.data_root,
        args.state_root,
        date.fromisoformat(args.session),
        config_path=args.config,
        futures_symbol=args.futures_symbol,
        reorder_seconds=args.reorder_seconds,
        poll_seconds=args.poll_seconds,
    )
    serve_live(
        runtime,
        args.directory,
        args.host,
        args.port,
        codex_host=args.codex_host,
        codex_port=args.codex_port,
        codex_cwd=args.codex_cwd,
        commentary_db=args.commentary_db,
        enable_commentary=args.enable_commentary,
    )
    return 0


def _nightly_context(args: argparse.Namespace) -> int:
    from .nightly_context import NightlyContextConfig, run_nightly_context

    config = NightlyContextConfig.from_path(args.config)
    cutoff = None if args.cutoff_session is None else date.fromisoformat(args.cutoff_session)
    result = run_nightly_context(
        args.data_root,
        args.state_root,
        config=config,
        cutoff_session=cutoff,
        stability_seconds=args.stability_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _context_status(args: argparse.Namespace) -> int:
    from .nightly_context import inspect_context

    result = inspect_context(args.state_root, snapshot_id=args.snapshot_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="banknifty-new-divergence",
        description="Causal, research-only BankNifty divergence runtime",
    )
    commands = root.add_subparsers(dest="command", required=True)

    normalized = commands.add_parser("replay-events", help="replay normalized JSONL/CSV events")
    normalized.add_argument("--events", nargs="+", required=True, type=Path)
    normalized.add_argument("--output-root", required=True, type=Path)
    normalized.add_argument("--config", type=Path)
    normalized.add_argument("--as-of", help="absolute receipt-time cutoff with timezone")
    normalized.add_argument("--finalize-at", help="explicit absolute close instant with timezone")
    normalized.set_defaults(handler=_replay_events)

    archive = commands.add_parser("replay-archive", help="stream one collector archive session")
    archive.add_argument("--archive", required=True, type=Path)
    archive.add_argument("--session", required=True, help="exchange session YYYY-MM-DD")
    archive.add_argument("--start", help="IST wall time, defaults to config session start")
    archive.add_argument("--end", help="IST wall time, defaults to config session end")
    archive.add_argument("--futures-symbol", help="optional explicit contract audit override")
    archive.add_argument("--basis-only", action="store_true", help="exclude OI/option evidence")
    archive.add_argument("--skip-archive-hash", action="store_true")
    archive.add_argument("--chunk-size", type=int, default=25_000)
    archive.add_argument("--finalize", action="store_true", help="explicitly close an open episode at --end")
    archive.add_argument("--output-root", required=True, type=Path)
    archive.add_argument("--config", type=Path)
    archive.set_defaults(handler=_replay_archive)

    inspect_archive = commands.add_parser("inspect-archive", help="list archive sessions without extraction")
    inspect_archive.add_argument("--archive", required=True, type=Path)
    inspect_archive.set_defaults(handler=_inspect_archive)

    catalog = commands.add_parser("catalog", help="regenerate a run-root session catalog")
    catalog.add_argument("--run-root", required=True, type=Path)
    catalog.set_defaults(handler=_catalog)

    samples = commands.add_parser(
        "generate-samples",
        help="publish 09:45+ cash breadth and participant-volume samples",
    )
    samples.add_argument(
        "--data-root",
        required=True,
        type=Path,
        help="collector data-prod-v4 root containing minute/ and metadata/",
    )
    samples.add_argument(
        "--output-root",
        required=True,
        type=Path,
        help="direct session root; writes OUTPUT_ROOT/YYYY-MM-DD",
    )
    samples.add_argument(
        "--session",
        action="append",
        help="generate one YYYY-MM-DD; repeat for multiple dates (default: discover all minute dates)",
    )
    samples.add_argument(
        "--stability-seconds",
        type=int,
        default=120,
        help="minimum age of market_1m.csv before reading (default: 120)",
    )
    samples.add_argument(
        "--force",
        action="store_true",
        help="regenerate even when source hashes and the verified output are unchanged",
    )
    samples.set_defaults(handler=_generate_samples)

    browser = commands.add_parser("build-browser", help="build calculation-free replay assets")
    browser.add_argument("--run-root", required=True, type=Path)
    browser.add_argument("--output-root", required=True, type=Path)
    browser.add_argument(
        "--context-state-root",
        type=Path,
        help="immutable nightly inventory context root",
    )
    browser.add_argument(
        "--oi-vpoc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="publish OI-VPOC display controls (default: enabled)",
    )
    browser.add_argument(
        "--volume-profile",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="publish Futures-volume VPOC/VAH/VAL display controls (default: enabled)",
    )
    browser.set_defaults(handler=_build_browser)

    live_browser = commands.add_parser(
        "build-live-browser", help="build the shared-clock live monitor assets"
    )
    live_browser.add_argument("--output-root", required=True, type=Path)
    live_browser.set_defaults(handler=_build_live_browser)

    verification = commands.add_parser("verify-ledger", help="verify an append-only transition ledger")
    verification.add_argument("--ledger", required=True, type=Path)
    verification.set_defaults(handler=_verify)

    run_verification = commands.add_parser(
        "verify-run", help="verify every artifact and the transition ledger"
    )
    run_verification.add_argument("--run-directory", required=True, type=Path)
    run_verification.set_defaults(handler=_verify_complete_run)

    outcomes = commands.add_parser(
        "evaluate-outcomes",
        help="write a separate retrospective research measurement file",
    )
    outcomes.add_argument("--run-directory", required=True, type=Path)
    outcomes.add_argument("--output", required=True, type=Path)
    outcomes.add_argument("--horizons", nargs="+", type=int, default=[5, 15, 30])
    outcomes.set_defaults(handler=_evaluate_outcomes)

    nightly = commands.add_parser(
        "nightly-context",
        help="publish immutable 1D/2D/3D context from completed collector sessions",
    )
    nightly.add_argument("--data-root", required=True, type=Path)
    nightly.add_argument("--state-root", required=True, type=Path)
    nightly.add_argument("--config", type=Path)
    nightly.add_argument(
        "--cutoff-session",
        help="latest completed source session allowed (YYYY-MM-DD)",
    )
    nightly.add_argument(
        "--stability-seconds",
        type=int,
        help="override the source-file stability interval",
    )
    nightly.set_defaults(handler=_nightly_context)

    context_status = commands.add_parser(
        "context-status", help="verify and summarize a complete nightly context snapshot"
    )
    context_status.add_argument("--state-root", required=True, type=Path)
    context_status.add_argument("--snapshot-id")
    context_status.set_defaults(handler=_context_status)

    local = commands.add_parser("serve", help="serve a previously built browser projection")
    local.add_argument("--directory", required=True, type=Path)
    local.add_argument("--host", default="127.0.0.1")
    local.add_argument("--port", type=int, default=8080)
    local.add_argument(
        "--codex-host", default="127.0.0.1",
        help="literal loopback address of the isolated Codex app-server",
    )
    local.add_argument("--codex-port", type=int, default=4500)
    local.add_argument(
        "--codex-cwd", type=Path,
        default=Path("/home/codexuser/banknifty-codex-worker"),
        help="restricted Codex worker directory",
    )
    local.add_argument(
        "--codex-token-file", type=Path,
        help="server-side access-token file required to enable replay explanations",
    )
    local.add_argument(
        "--commentary-db", type=Path,
        help="central SQLite commentary store (default: DIRECTORY/commentary.sqlite3)",
    )
    local.add_argument("--acknowledge-research-only", action="store_true")
    local.set_defaults(handler=_serve)

    live = commands.add_parser(
        "serve-live", help="tail collector data read-only and serve snapshot/SSE live monitoring"
    )
    live.add_argument("--data-root", required=True, type=Path)
    live.add_argument("--state-root", required=True, type=Path)
    live.add_argument("--directory", required=True, type=Path, help="built live browser root")
    live.add_argument("--session", required=True, help="exchange session YYYY-MM-DD")
    live.add_argument("--config", type=Path)
    live.add_argument("--futures-symbol")
    live.add_argument("--reorder-seconds", type=float, default=3.0)
    live.add_argument("--poll-seconds", type=float, default=0.25)
    live.add_argument("--host", default="127.0.0.1")
    live.add_argument("--port", type=int, default=8793)
    live.add_argument(
        "--codex-host",
        default="127.0.0.1",
        help="literal loopback address of the isolated Codex app-server",
    )
    live.add_argument(
        "--codex-port",
        type=int,
        default=4500,
        help="loopback port of the isolated Codex app-server",
    )
    live.add_argument(
        "--codex-cwd", type=Path,
        default=Path("/home/codexuser/banknifty-codex-worker"),
    )
    live.add_argument("--commentary-db", type=Path)
    live.add_argument(
        "--enable-commentary", action="store_true",
        help="enable centralized stored Codex commentary (experimental, research-only)",
    )
    live.add_argument("--acknowledge-research-only", action="store_true")
    live.set_defaults(handler=_serve_live)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        return int(args.handler(args))
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        ValueError,
        sqlite3.Error,
        tarfile.TarError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
