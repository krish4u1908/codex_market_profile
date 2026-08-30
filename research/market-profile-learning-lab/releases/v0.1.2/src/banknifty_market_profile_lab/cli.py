"""Command-line boundary for the isolated learning lab."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .candidates import (
    create_seed_candidates,
    generate_codex_candidates,
    installed_resource,
    verify_codex_profile,
)
from .dataset import build_dataset
from .report import generate_report, verify_learning_run
from .scoring import evaluate_split


def _json(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="banknifty-market-profile-lab",
        description="Isolated causal learning and evaluation for BankNifty profile-shift agents",
    )
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="verify inputs and build causal cases plus sealed labels")
    build.add_argument("--run-root", type=Path, required=True)
    build.add_argument("--gui-root", type=Path, required=True)
    build.add_argument(
        "--config",
        type=Path,
        default=installed_resource("config", "learning_run.json"),
    )
    build.add_argument("--output-root", type=Path, required=True)

    seeds = commands.add_parser("seed-candidates", help="create deterministic comparison candidates")
    seeds.add_argument("--learning-run", type=Path, required=True)

    profile = commands.add_parser(
        "profile-check",
        help="prove the Codex candidate profile cannot read outside its workspace",
    )
    profile.add_argument("--learning-run", type=Path, required=True)
    profile.add_argument(
        "--codex-bin",
        type=Path,
        default=Path("/home/codexuser/.local/bin/codex"),
    )
    profile.add_argument("--profile", default="banknifty-learning")
    profile.add_argument("--timeout-seconds", type=int, default=300)

    generate = commands.add_parser(
        "generate-candidates",
        help="ask isolated Codex runs to create candidate numeric agents from training summaries",
    )
    generate.add_argument("--learning-run", type=Path, required=True)
    generate.add_argument(
        "--agent-schema",
        type=Path,
        default=installed_resource("schemas", "agent-spec.schema.json"),
    )
    generate.add_argument(
        "--codex-bin",
        type=Path,
        default=Path("/home/codexuser/.local/bin/codex"),
    )
    generate.add_argument("--profile", default="banknifty-learning")
    generate.add_argument("--count", type=int, default=3)
    generate.add_argument("--timeout-seconds", type=int, default=900)

    evaluate = commands.add_parser("evaluate", help="forecast and score one split")
    evaluate.add_argument("--learning-run", type=Path, required=True)
    evaluate.add_argument("--split", choices=("train", "validation", "holdout"), required=True)
    evaluate.add_argument(
        "--open-holdout",
        action="store_true",
        help="irreversibly freeze current candidates and open the holdout once",
    )

    report = commands.add_parser("report", help="write the current scored Markdown report")
    report.add_argument("--learning-run", type=Path, required=True)

    verify = commands.add_parser("verify", help="verify source hashes, case/label bindings, and seal")
    verify.add_argument("--learning-run", type=Path, required=True)

    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build":
            _json(build_dataset(
                run_root=args.run_root.resolve(),
                gui_root=args.gui_root.resolve(),
                config_path=args.config.resolve(),
                output_root=args.output_root.resolve(),
            ))
            return 0
        if args.command == "seed-candidates":
            _json({"candidates": create_seed_candidates(args.learning_run.resolve())})
            return 0
        if args.command == "profile-check":
            _json(verify_codex_profile(
                args.learning_run.resolve(),
                codex_bin=args.codex_bin.resolve(),
                profile=args.profile,
                timeout_seconds=args.timeout_seconds,
            ))
            return 0
        if args.command == "generate-candidates":
            _json({"candidates": generate_codex_candidates(
                args.learning_run.resolve(),
                schema_path=args.agent_schema.resolve(),
                codex_bin=args.codex_bin.resolve(),
                profile=args.profile,
                count=args.count,
                timeout_seconds=args.timeout_seconds,
            )})
            return 0
        if args.command == "evaluate":
            _json(evaluate_split(
                args.learning_run.resolve(),
                split=args.split,
                open_holdout=args.open_holdout,
            ))
            return 0
        if args.command == "report":
            path = generate_report(args.learning_run.resolve())
            _json({"report": str(path), "status": "WRITTEN"})
            return 0
        if args.command == "verify":
            result = verify_learning_run(args.learning_run.resolve())
            _json(result)
            return 0 if result["valid"] else 2
        raise AssertionError(args.command)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
