"""Deterministic, causal, transition-only cross-layer state ledger."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from typing import Iterable, Mapping

COMPONENT_ORDER = {
    "INVENTORY": 0,
    "DIVERGENCE": 1,
    "LIFECYCLE": 2,
    "RESOLUTION": 3,
    "FUTURES_PARTICIPATION": 4,
    "OPTION_PARTICIPATION": 5,
    "BREADTH_JOINT": 6,
    "FRESHNESS": 7,
}

MATERIAL_CONTEXT_VERSION = "R6E1R_CROSS_LAYER_CONTEXT_V1"


def empty_material_context() -> dict[str, object]:
    """Return the compact state needed to continue a chronological build."""
    return {
        "version": MATERIAL_CONTEXT_VERSION,
        "inventory_source_count": 0,
        "episode_source_count": 0,
        "resolution_source_count": 0,
        "inventory_previous": {},
        "resolution_previous": {},
    }


def normalize_material_context(
    value: Mapping[str, object] | None,
) -> dict[str, object]:
    """Validate persisted continuation state without accepting loose coercions."""
    if value is None:
        return empty_material_context()
    if not isinstance(value, Mapping):
        raise ValueError("cross-layer continuation context must be a mapping")
    if value.get("version", MATERIAL_CONTEXT_VERSION) != MATERIAL_CONTEXT_VERSION:
        raise ValueError("cross-layer continuation context version mismatch")
    result = empty_material_context()
    for field in (
        "inventory_source_count",
        "episode_source_count",
        "resolution_source_count",
    ):
        item = value.get(field, 0)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise ValueError(f"cross-layer {field} must be a non-negative integer")
        result[field] = item
    for field in ("inventory_previous", "resolution_previous"):
        item = value.get(field, {})
        if not isinstance(item, Mapping):
            raise ValueError(f"cross-layer {field} must be a mapping")
        result[field] = {
            str(key): str(state) for key, state in sorted(item.items())
        }
    return result


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(str(value).replace(" ", "T"))
    if result.tzinfo is None:
        raise ValueError("cross-layer timestamps must be timezone-aware")
    return result


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _transition(component: str, key: str, date: str, effective: str,
                previous: str, current: str, reason: str,
                constituents: Mapping[str, str], source_id: str,
                episode_id: str = "", horizon: str = "", family: str = "") -> dict[str, str]:
    instant = _time(effective)
    clocks = {k: str(v) for k, v in constituents.items() if str(v)}
    if any(_time(value) > instant for value in clocks.values()):
        raise ValueError(f"timestamp backdating in {component}:{source_id}")
    identity = _canonical([component, key, effective, current, source_id])
    return {
        "transition_id": "XL-" + hashlib.sha256(identity.encode()).hexdigest()[:24].upper(),
        "evaluation_date": date,
        "effective_timestamp": effective,
        "component": component,
        "state_key": key,
        "previous_state": previous,
        "new_state": current,
        "reason_code": reason,
        "constituent_effective_timestamps": _canonical(clocks),
        "source_record_id": source_id,
        "episode_id": episode_id,
        "horizon": horizon,
        "family": family,
    }


def build_material_transitions(
    inventory: Iterable[Mapping[str, object]],
    episodes: Iterable[Mapping[str, object]],
    lifecycle: Iterable[Mapping[str, object]],
    resolution: Iterable[Mapping[str, object]],
    participation: Iterable[Mapping[str, object]],
    *,
    initial_context: Mapping[str, object] | None = None,
    return_context: bool = False,
) -> list[dict[str, str]] | tuple[list[dict[str, str]], dict[str, object]]:
    """Merge layer changes without turning dense observations into events."""
    output: list[dict[str, str]] = []
    context = normalize_material_context(initial_context)
    inventory_previous = dict(context["inventory_previous"])
    resolution_previous = dict(context["resolution_previous"])

    inventory_rows = sorted(inventory, key=lambda r: (_time(str(r["control_effective_timestamp"])), str(r["horizon"]), str(r["family"])))
    inventory_offset = int(context["inventory_source_count"])
    for ordinal, row in enumerate(inventory_rows, inventory_offset + 1):
        key = f'{row["horizon"]}:{row["family"]}'
        current = f'AVAILABLE:{row["control_value"]}'
        prior = inventory_previous.get(key, "NOT_YET_AVAILABLE")
        if current == prior:
            continue
        effective = str(row["control_effective_timestamp"])
        clocks = {"control_effective_timestamp": effective}
        # Freshness is provenance, not an effective current-session clock for
        # fixed horizons; ID winner publication is already the effective clock.
        if str(row["horizon"]) == "ID":
            clocks["winner_change_timestamp"] = str(row.get("winner_change_timestamp", effective))
        output.append(_transition("INVENTORY", key, str(row["evaluation_date"]), effective,
                                  prior, current, "CONTROL_AVAILABLE_OR_WINNER_CHANGED", clocks,
                                  f"inventory:{ordinal}", horizon=str(row["horizon"]), family=str(row["family"])))
        inventory_previous[key] = current

    episode_rows = sorted(episodes, key=lambda r: _time(str(r["confirmation_timestamp"])))
    episode_offset = int(context["episode_source_count"])
    for ordinal, row in enumerate(episode_rows, episode_offset + 1):
        episode = str(row["episode_id"]); effective = str(row["confirmation_timestamp"])
        output.append(_transition("DIVERGENCE", episode, str(row["evaluation_date"]), effective,
                                  "CANDIDATE", f'{row["colour"]}_CONFIRMED', "FROZEN_DIVERGENCE_CONFIRMED",
                                  {"confirmation_timestamp": effective,
                                   "index_receipt_timestamp": str(row["index_receipt_timestamp"]),
                                   "futures_receipt_timestamp": str(row["futures_receipt_timestamp"])},
                                  f"episode:{ordinal}", episode_id=episode))

    for row in lifecycle:
        output.append(_transition("LIFECYCLE", str(row["episode_id"]), str(row["evaluation_date"]),
                                  str(row["state_entry_timestamp"]), str(row["previous_state"]), str(row["state"]),
                                  str(row["reason_code"]), {"state_entry_timestamp": str(row["state_entry_timestamp"])},
                                  str(row["record_id"]), episode_id=str(row["episode_id"])))

    sorted_resolution = sorted(resolution, key=lambda r: (_time(str(r["availability_timestamp"])), str(r["episode_id"]), str(r.get("record_id", ""))))
    resolution_offset = int(context["resolution_source_count"])
    for ordinal, row in enumerate(sorted_resolution, resolution_offset + 1):
        episode = str(row["episode_id"]); current = str(row["resolution_mechanism_native"])
        prior = resolution_previous.get(episode, "NOT_YET_AVAILABLE")
        if current == prior:
            continue
        effective = str(row["availability_timestamp"])
        output.append(_transition("RESOLUTION", episode, str(row["evaluation_date"]), effective, prior, current,
                                  "RESOLUTION_MECHANISM_CHANGED", {"availability_timestamp": effective},
                                  f"resolution:{ordinal}", episode_id=episode))
        resolution_previous[episode] = current

    for row in participation:
        component_name = str(row.get("component", "PARTICIPATION"))
        component = "FUTURES_PARTICIPATION" if component_name == "FUTURES" else "OPTION_PARTICIPATION" if component_name in {"CE", "PE", "OPTION"} else "BREADTH_JOINT"
        effective = str(row["effective_timestamp"])
        raw_clocks = str(row.get("constituent_effective_timestamps", ""))
        try:
            decoded = json.loads(raw_clocks) if raw_clocks else {}
            clocks = decoded if isinstance(decoded, dict) else {"evidence": effective}
        except json.JSONDecodeError:
            clocks = {"evidence_receipt_timestamp": str(row.get("evidence_receipt_timestamp", effective))}
        clocks["effective_timestamp"] = effective
        output.append(_transition(component, str(row["transition_id"]), str(row.get("evaluation_date", effective[:10])),
                                  effective, str(row["previous_state"]), str(row["new_state"]), str(row["reason_code"]),
                                  clocks, str(row["transition_id"]), episode_id=str(row["episode_id"])))

    output.sort(key=lambda r: (_time(r["effective_timestamp"]), COMPONENT_ORDER[r["component"]], r["transition_id"]))
    identities = [(r["component"], r["state_key"], r["effective_timestamp"], r["new_state"]) for r in output]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate material cross-layer transition")
    final_context = {
        "version": MATERIAL_CONTEXT_VERSION,
        "inventory_source_count": inventory_offset + len(inventory_rows),
        "episode_source_count": episode_offset + len(episode_rows),
        "resolution_source_count": resolution_offset + len(sorted_resolution),
        "inventory_previous": dict(sorted(inventory_previous.items())),
        "resolution_previous": dict(sorted(resolution_previous.items())),
    }
    if return_context:
        return output, final_context
    return output
