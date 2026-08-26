"""Frozen canonical runtime-configuration invariants.

These checks are deliberately separate from analytical calculations.  They
only refuse a configuration that does not identify the already-frozen
exchange timezone and basis synchronization tolerance exactly.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

CANONICAL_TIMEZONE = "Asia/Kolkata"
CANONICAL_SYNCHRONIZATION_TOLERANCE_MS = 2000
CANONICAL_INVENTORY_JOIN_TOLERANCE_SECONDS = 5


def validate_canonical_runtime_config(config: Mapping) -> dict:
    """Return a normalized copy after enforcing the frozen invariants."""
    timezone = config.get("timezone")
    if timezone != CANONICAL_TIMEZONE:
        raise ValueError(
            'frozen canonical timezone requirement: timezone must be exactly "Asia/Kolkata"'
        )

    tolerance = config.get("synchronization_tolerance_ms")
    if type(tolerance) is not int or tolerance != CANONICAL_SYNCHRONIZATION_TOLERANCE_MS:
        raise ValueError(
            "frozen canonical synchronization requirement: "
            "synchronization_tolerance_ms must be the integer 2000"
        )

    inventory_tolerance = config.get(
        "inventory_join_tolerance_seconds",
        CANONICAL_INVENTORY_JOIN_TOLERANCE_SECONDS,
    )
    if (
        isinstance(inventory_tolerance, bool)
        or not isinstance(inventory_tolerance, (int, float))
        or float(inventory_tolerance)
        != float(CANONICAL_INVENTORY_JOIN_TOLERANCE_SECONDS)
    ):
        raise ValueError(
            "frozen canonical inventory requirement: "
            "inventory_join_tolerance_seconds must equal 5"
        )

    return dict(config)


def canonical_configuration_bytes(config: Mapping) -> bytes:
    """Canonical serialization used to prove configuration identity."""
    normalized = validate_canonical_runtime_config(config)
    return (json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n").encode()


def canonical_configuration_sha256(config: Mapping) -> str:
    return hashlib.sha256(canonical_configuration_bytes(config)).hexdigest()
