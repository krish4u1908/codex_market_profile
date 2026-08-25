"""Verified R6B2R lifecycle/resolution primitives without data-root coupling."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

SYNC_TOLERANCE_MS = 2000.0
BASIS_MATERIAL_POINTS = 5.0
STALLED_SECONDS = 60.0
RESPONSE_POINTS = 10.0

@dataclass(frozen=True)
class Resolution:
    mechanism: str
    compatibility_label: str
    index_movement: float
    futures_movement: float
    basis_change: float
    index_contribution: float
    futures_contribution: float
    signed_convergence: float

def classify_resolution(colour: str, initial_index: float, initial_futures: float,
                        current_index: float, current_futures: float,
                        stalled_seconds: float) -> Resolution:
    """Apply the verified sequential R3 precedence; later masks override."""
    sign = 1.0 if colour == "GREEN" else -1.0
    di = current_index - initial_index
    df = current_futures - initial_futures
    db = df - di
    ic, fc = sign * di, -sign * df
    convergence = ic + fc
    mechanism = "UNRESOLVED"
    if convergence <= -BASIS_MATERIAL_POINTS:
        mechanism = "BASIS_EXPANSION_CONTINUING"
    both_constructive = ic >= BASIS_MATERIAL_POINTS and fc >= BASIS_MATERIAL_POINTS
    both_adverse = ic <= -BASIS_MATERIAL_POINTS and fc <= -BASIS_MATERIAL_POINTS
    if both_constructive:
        mechanism = "BOTH_CONVERGING_CONSTRUCTIVELY"
    if both_adverse:
        mechanism = "BOTH_CONVERGING_ADVERSELY"
    if not both_constructive and not both_adverse and ic >= BASIS_MATERIAL_POINTS and ic >= fc:
        mechanism = "INDEX_CATCH_UP" if colour == "GREEN" else "INDEX_CATCH_DOWN"
    if not both_constructive and not both_adverse and fc >= BASIS_MATERIAL_POINTS and fc > ic:
        mechanism = "FUTURES_REVERSED_TO_INDEX"
    if abs(convergence) < BASIS_MATERIAL_POINTS and stalled_seconds >= STALLED_SECONDS:
        mechanism = "BASIS_EXTREME_STALLED"
    compatibility = {
        "BOTH_CONVERGING_CONSTRUCTIVELY": "BOTH_CONVERGED",
        "BOTH_CONVERGING_ADVERSELY": "BOTH_CONVERGED",
        "BASIS_EXPANSION_CONTINUING": "REMAINED_EXTREME",
        "BASIS_EXTREME_STALLED": "REMAINED_EXTREME",
    }.get(mechanism, mechanism)
    return Resolution(mechanism, compatibility, di, df, db, ic, fc, convergence)

def deterministic_transition_id(episode_id: str, timestamp: str, state: str, ordinal: int) -> str:
    value = f"{episode_id}|{timestamp}|{state}|{ordinal}".encode()
    return "R6B2R-" + sha256(value).hexdigest()[:20].upper()

def valid_synchronized_age(age_ms: float) -> bool:
    return 0.0 <= age_ms <= SYNC_TOLERANCE_MS

