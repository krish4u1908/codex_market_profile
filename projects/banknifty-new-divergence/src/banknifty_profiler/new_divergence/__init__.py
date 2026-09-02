"""Causal, date-agnostic BankNifty divergence runtime.

The package is intentionally diagnostic.  Replay and live adapters feed the
same normalized event contract and the same state machine.  Outcome evaluation
is kept outside the inference engine.
"""

from .contracts import (
    BasisState,
    EngineConfig,
    EpisodeState,
    EventKind,
    MarketEvent,
)
from .engine import CausalDivergenceEngine, run_replay
from .collector_archive import CollectorArchiveAdapter
from .provenance import RUNTIME_VERSION

__version__ = RUNTIME_VERSION

__all__ = [
    "BasisState",
    "CausalDivergenceEngine",
    "CollectorArchiveAdapter",
    "EngineConfig",
    "EpisodeState",
    "EventKind",
    "MarketEvent",
    "run_replay",
    "__version__",
]
