"""Retrospective outcome measurements kept outside causal inference."""

from __future__ import annotations

from bisect import bisect_left
from datetime import timedelta
from pathlib import Path
from typing import Iterable

from .clock import iso_utc
from .contracts import BasisObservation, EpisodeState, EpisodeTransition, EventKind, MarketEvent
from .output import atomic_text
from .ledger import canonical_json


def evaluate_outcomes(
    transitions: Iterable[EpisodeTransition],
    market_events: Iterable[MarketEvent],
    *,
    horizons_minutes: tuple[int, ...] = (5, 15, 30),
) -> list[dict[str, object]]:
    """Measure later Index movement; never classify an episode as a trade."""

    if not horizons_minutes or any(value <= 0 for value in horizons_minutes):
        raise ValueError("outcome horizons must be positive")
    index_events = sorted(
        (event for event in market_events if event.kind == EventKind.INDEX_TICK),
        key=lambda event: event.sort_key,
    )
    times = [event.receipt_timestamp for event in index_events]
    anchors = [
        transition for transition in transitions
        if transition.state == EpisodeState.CONFIRMED
    ]
    results = []
    for transition in anchors:
        anchor_price = transition.evidence.basis.index_price
        measurements = {}
        for minutes in horizons_minutes:
            target = transition.published_at + timedelta(minutes=minutes)
            index = bisect_left(times, target)
            if index >= len(index_events):
                measurements[f"{minutes}m"] = {"availability": "UNAVAILABLE"}
                continue
            observed = index_events[index]
            measurements[f"{minutes}m"] = {
                "availability": "AVAILABLE",
                "target_timestamp": iso_utc(target),
                "observation_timestamp": iso_utc(observed.receipt_timestamp),
                "index_price": float(observed.values["price"]),
                "index_change_points": float(observed.values["price"]) - anchor_price,
            }
        results.append({
            "schema": "NEW_DIVERGENCE_RETROSPECTIVE_OUTCOME_V1",
            "classification": "RETROSPECTIVE RESEARCH MEASUREMENT — NOT ENGINE INPUT",
            "production_weight": 0,
            "episode_id": transition.episode_id,
            "colour": transition.colour,
            "anchor_transition_id": transition.transition_id,
            "anchor_published_at": iso_utc(transition.published_at),
            "anchor_index_price": anchor_price,
            "measurements": measurements,
        })
    return results


def write_outcomes(path: Path, rows: Iterable[dict[str, object]]) -> None:
    atomic_text(Path(path), "".join(canonical_json(row) + "\n" for row in rows))


def evaluate_basis_outcomes(
    transitions: Iterable[EpisodeTransition],
    observations: Iterable[BasisObservation],
    *,
    horizons_minutes: tuple[int, ...] = (5, 15, 30),
) -> list[dict[str, object]]:
    """Equivalent retrospective measurement over persisted basis observations."""

    if not horizons_minutes or any(value <= 0 for value in horizons_minutes):
        raise ValueError("outcome horizons must be positive")
    ordered = sorted(observations, key=lambda row: row.timestamp)
    times = [row.timestamp for row in ordered]
    results = []
    for transition in transitions:
        if transition.state != EpisodeState.CONFIRMED:
            continue
        anchor_price = transition.evidence.basis.index_price
        measurements = {}
        for minutes in horizons_minutes:
            target = transition.published_at + timedelta(minutes=minutes)
            index = bisect_left(times, target)
            if index >= len(ordered):
                measurements[f"{minutes}m"] = {"availability": "UNAVAILABLE"}
                continue
            observed = ordered[index]
            measurements[f"{minutes}m"] = {
                "availability": "AVAILABLE",
                "target_timestamp": iso_utc(target),
                "observation_timestamp": iso_utc(observed.timestamp),
                "index_price": observed.index_price,
                "index_change_points": observed.index_price - anchor_price,
            }
        results.append({
            "schema": "NEW_DIVERGENCE_RETROSPECTIVE_OUTCOME_V1",
            "classification": "RETROSPECTIVE RESEARCH MEASUREMENT — NOT ENGINE INPUT",
            "production_weight": 0,
            "episode_id": transition.episode_id,
            "colour": transition.colour,
            "anchor_transition_id": transition.transition_id,
            "anchor_published_at": iso_utc(transition.published_at),
            "anchor_index_price": anchor_price,
            "measurements": measurements,
        })
    return results
