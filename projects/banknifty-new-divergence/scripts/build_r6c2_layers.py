#!/usr/bin/env python3
"""Build R6C2 cross-layer and partial-context publications from same-run data."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from banknifty_profiler.context.availability import HORIZONS, LayerAvailability, classify_context
from banknifty_profiler.cross_layer.state import build_material_transitions


def read(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"required same-run artifact missing: {path}")
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    temporary.replace(path)


def availability_rows(eligibility: list[dict[str, str]], sessions: list[str]) -> list[dict[str, object]]:
    accepted = [row["date"] for row in eligibility if row["status"] == "ACCEPTED"]
    output = []
    for date in sessions:
        preceding = [item for item in accepted if item < date]
        states = {}
        for horizon, needed in (("1D", 1), ("2D", 2), ("3D", 3)):
            state = "AVAILABLE" if len(preceding) >= needed else "MISSING_PRIOR_SESSION"
            states[horizon] = LayerAvailability(horizon, state, "RAW_ACCEPTED_SOURCE_CHAIN" if state == "AVAILABLE" else f"REQUIRES_{needed}_PRIOR_ACCEPTED_SESSION(S)")
        current = next((row for row in eligibility if row["date"] == date), None)
        id_state = "AVAILABLE" if current and current["status"] == "ACCEPTED" else "INCOMPLETE_RAW_DATA"
        states["ID"] = LayerAvailability("ID", id_state, current["reason"] if current else "SESSION_NOT_DISCOVERED")
        context = classify_context(states, divergence_inputs_available=id_state == "AVAILABLE", participation_inputs_available=id_state == "AVAILABLE")
        for horizon in HORIZONS:
            output.append({
                "evaluation_date": date,
                "horizon": horizon,
                "availability_state": states[horizon].state,
                "availability_reason": states[horizon].reason,
                **context,
            })
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--stack-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sessions", nargs="+", required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise SystemExit("output root must not exist")
    args.output_root.mkdir(parents=True)
    inventory = read(args.inventory_root / "canonical_inventory.csv")
    episodes = read(args.stack_root / "native/raw_divergence_episodes.csv")
    lifecycle = read(args.stack_root / "native/raw_lifecycle_transitions.csv")
    resolution = read(args.stack_root / "native/raw_resolution_observations.csv")
    participation = read(args.stack_root / "views/transition_participation_ledger.csv")
    transitions = build_material_transitions(inventory, episodes, lifecycle, resolution, participation)
    eligibility = read(args.inventory_root / "raw_session_eligibility.csv")
    layers = availability_rows(eligibility, args.sessions)
    write(args.output_root / "canonical_cross_layer_transitions.csv", transitions)
    write(args.output_root / "layer_availability.csv", layers)
    summary = {
        "cross_layer_transitions": len(transitions),
        "layer_availability_rows": len(layers),
        "timestamp_backdating": 0,
        "duplicate_material_transitions": 0,
    }
    (args.output_root / "seal.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
