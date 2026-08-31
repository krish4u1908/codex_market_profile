"""Central, durable commentary records for replay and live consumers.

The deterministic layer decides *when* a material inventory event occurred and
which controls changed.  Codex may explain the verified causal facts, but it
does not create the event identity and cannot promote an experimental forecast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable

from .codex_replay import CodexAppServerClient, replay_fact_bundle
from .api import ProjectionReadModel
from .provenance import RUNTIME_VERSION


FAMILIES = (
    "CE_POS_OI_VPOC", "CE_NEG_OI_VPOC", "PE_POS_OI_VPOC",
    "PE_NEG_OI_VPOC", "FUT_POS_OI_VPOC", "FUT_NEG_OI_VPOC",
    "BN_REF_FUT_VOLUME_VPOC",
)
GENERATION_REVISION = 3


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def detect_inventory_shifts(bundle: dict[str, object]) -> list[dict[str, object]]:
    """Return only consecutive, causal control changes retained in the prefix."""
    history = bundle.get("recent_intraday_inventory_shifts", {})
    if not isinstance(history, dict):
        return []
    shifts: list[dict[str, object]] = []
    for family in FAMILIES:
        rows = history.get(family, [])
        if not isinstance(rows, list) or len(rows) < 2:
            continue
        previous, current = rows[-2], rows[-1]
        if not isinstance(previous, dict) or not isinstance(current, dict):
            continue
        old, new = previous.get("control_value"), current.get("control_value")
        if old is None or new is None or old == new:
            continue
        shifts.append({
            "family": family,
            "from": old,
            "to": new,
            "delta": float(new) - float(old),
            "receipt": current.get("receipt"),
        })
    return shifts


def _levels(bundle: dict[str, object]) -> tuple[list[float], list[float]]:
    market = bundle.get("latest_market", {})
    index = float(market.get("i", 0)) if isinstance(market, dict) else 0.0
    controls = bundle.get("visible_intraday_inventory", {})
    values = []
    if isinstance(controls, dict):
        for row in controls.values():
            if isinstance(row, dict) and row.get("control_value") is not None:
                values.append(float(row["control_value"]))
            if isinstance(row, dict):
                for key in ("value_area_low", "value_area_high"):
                    if row.get(key) is not None:
                        values.append(float(row[key]))
    supports = sorted({value for value in values if value <= index}, reverse=True)[:2]
    resistances = sorted({value for value in values if value >= index})[:2]
    return supports, resistances


def market_profile_analysis(
    bundle: dict[str, object], shifts: list[dict[str, object]],
) -> dict[str, object]:
    """Transparent textbook/rule-based interpretation of the verified facts."""
    market = bundle.get("latest_market", {})
    index = float(market.get("i", 0)) if isinstance(market, dict) else 0.0
    futures = float(market.get("f", 0)) if isinstance(market, dict) else 0.0
    basis = float(market.get("b", futures - index)) if isinstance(market, dict) else futures - index
    option = bundle.get("latest_option_summary", {})
    ce = option.get("CE", {}) if isinstance(option, dict) else {}
    pe = option.get("PE", {}) if isinstance(option, dict) else {}
    ce_delta = float(ce.get("delta_oi_total", 0) or 0) if isinstance(ce, dict) else 0.0
    pe_delta = float(pe.get("delta_oi_total", 0) or 0) if isinstance(pe, dict) else 0.0
    supports, resistances = _levels(bundle)
    observations = [
        f"Bank Nifty is {index:g}; futures are {futures:g}; visible basis is {basis:g}.",
        f"Latest selected-strike net OI change is CE {ce_delta:+g} versus PE {pe_delta:+g}.",
    ]
    if pe_delta > ce_delta:
        observations.append(
            "PE addition exceeds CE addition. Textbook interpretation is relatively stronger "
            "put-side inventory support, but writer/buyer initiation is not proven by OI alone."
        )
    elif ce_delta > pe_delta:
        observations.append(
            "CE addition exceeds PE addition. Textbook interpretation is relatively stronger "
            "call-side overhead inventory, but writer/buyer initiation is not proven by OI alone."
        )
    else:
        observations.append("CE and PE net additions are balanced in the selected strike set.")
    if shifts:
        observations.append(
            "A control migration changes the market's inventory reference; it becomes directional "
            "only after price reacts at or accepts beyond the migrated level."
        )
    else:
        observations.append("No fresh control migration is visible at this exact receipt.")
    structure = "ROTATION"
    if supports and resistances:
        structure = f"ROTATION_BETWEEN_{supports[0]:g}_AND_{resistances[0]:g}"
    migration = "UNCHANGED"
    if shifts:
        lower = sum(1 for row in shifts if float(row["delta"]) < 0)
        higher = sum(1 for row in shifts if float(row["delta"]) > 0)
        migration = "LOWER" if lower > higher else "HIGHER" if higher > lower else "MIXED"
    cluster = sorted({*supports, *resistances})
    concise_read = (
        f"Inventory controls migrated {migration.lower()} and now cluster near "
        f"{'–'.join(f'{value:g}' for value in cluster[:3]) or 'unavailable'}; "
        f"Bank Nifty is {index:g}."
    )
    basis_warning = None
    if abs(basis) >= 200:
        basis_warning = (
            f"Wide basis {basis:+g}: verify the active futures contract/roll before "
            "using futures confirmation."
        )
    return {
        "schema": "NEW_DIVERGENCE_MARKET_PROFILE_ANALYSIS_V1",
        "method": "TRANSPARENT_RULE_BASED_MARKET_PROFILE",
        "structure": structure,
        "inventory_migration": migration,
        "concise_read": concise_read,
        "basis_warning": basis_warning,
        "observations": observations,
        "support": supports,
        "resistance": resistances,
        "cautions": [
            "OI alone cannot distinguish opening buyers from opening writers.",
            "A VPOC is an inventory concentration, not automatically support or resistance.",
            "Direction requires price response, freshness and cross-layer confirmation.",
        ],
    }


def compact_commentary(
    bundle: dict[str, object], answer: dict[str, object], shifts: list[dict[str, object]],
) -> dict[str, object]:
    """Convert the diagnostic answer into the fixed compact GUI contract.

    Validation V0.1.3 selected no specialist, therefore direction is deliberately
    NO_EDGE and no numeric probability is fabricated.
    """
    supports, resistances = _levels(bundle)
    shift_text = "; ".join(
        f"{row['family']} {row['from']:g}→{row['to']:g}" for row in shifts
    ) or "No new material inventory-control migration at this receipt"
    return {
        "schema": "NEW_DIVERGENCE_CENTRAL_COMMENTARY_V1",
        "runtime_version": RUNTIME_VERSION,
        "generation_revision": GENERATION_REVISION,
        "classification": "EXPERIMENTAL_NOT_VALIDATED",
        "bias": "NO_EDGE",
        "horizon_minutes": 30,
        "confidence": "LOW",
        "probability": None,
        "headline": str(answer.get("headline", "Inventory context updated"))[:180],
        "what_changed": shift_text,
        "possible_outcome": (
            "Rotation between the nearest verified controls remains the base case; "
            "direction requires fresh price acceptance and confirming CE/PE/futures flow."
        ),
        "support": supports,
        "resistance": resistances,
        "confirmation": "Fresh price acceptance beyond a listed control with confirming option and futures flow.",
        "invalidation": "Opposite-side control acceptance or reversal of the latest inventory migration.",
        "summary": str(answer.get("summary", ""))[:1200],
        "market_profile_analysis": market_profile_analysis(bundle, shifts),
        "shifts": shifts,
        "causal_as_of": bundle["causal_as_of"],
        "verified_prefix_sha256": bundle["verified_prefix_sha256"],
        "generated_at": datetime.now(UTC).isoformat(),
    }


class CommentaryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS commentary (
                    event_id TEXT PRIMARY KEY,
                    session TEXT NOT NULL,
                    causal_as_of TEXT NOT NULL,
                    facts_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS commentary_session_cursor ON commentary(session, causal_as_of)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def put(self, session: str, payload: dict[str, object]) -> dict[str, object]:
        event_id = hashlib.sha256(_canonical({
            "session": session,
            "as_of": payload["causal_as_of"],
            "facts": payload["verified_prefix_sha256"],
            "generation_revision": payload.get("generation_revision", 1),
            "codex_status": payload.get("codex_status", "UNSPECIFIED"),
        })).hexdigest()
        stored = {**payload, "event_id": event_id, "session": session}
        encoded = _canonical(stored).decode()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO commentary VALUES(?,?,?,?,?,?)",
                (event_id, session, stored["causal_as_of"], stored["verified_prefix_sha256"],
                 encoded, stored["generated_at"]),
            )
        return self.get(event_id) or stored

    def get(self, event_id: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM commentary WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def current(self, session: str, as_of: str | None = None) -> dict[str, object] | None:
        sql = "SELECT payload_json FROM commentary WHERE session=?"
        params: list[object] = [session]
        if as_of is not None:
            sql += " AND causal_as_of<=?"
            params.append(as_of)
        sql += " ORDER BY causal_as_of DESC, created_at DESC LIMIT 1"
        with self._connect() as db:
            row = db.execute(sql, params).fetchone()
        return None if row is None else json.loads(row[0])

    def exact(self, session: str, as_of: str) -> dict[str, object] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT payload_json FROM commentary WHERE session=? AND causal_as_of=? "
                "ORDER BY created_at DESC LIMIT 1", (session, as_of),
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def history(self, session: str, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload_json FROM commentary WHERE session=? ORDER BY causal_as_of DESC LIMIT ?",
                (session, min(max(int(limit), 1), 500)),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]


@dataclass
class ReplayCommentaryCoordinator:
    directory: Path
    store: CommentaryStore
    client: CodexAppServerClient
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def current(self, session: str, as_of: str) -> dict[str, object] | None:
        return self.store.current(session, as_of)

    def generate(self, session: str, as_of: str) -> dict[str, object]:
        if not self._lock.acquire(blocking=False):
            existing = self.store.current(session, as_of)
            if existing:
                return {**existing, "cached": True, "generation_in_progress": True}
            raise RuntimeError("central commentary generation is already running")
        try:
            bundle, _ = replay_fact_bundle(ProjectionReadModel(self.directory), session, as_of)
            existing = self.store.current(session, as_of)
            shifts = detect_inventory_shifts(bundle)
            latest_shift = max(
                (str(row.get("receipt", "")) for row in shifts), default=""
            )
            if existing and existing.get("generation_revision") == GENERATION_REVISION and existing.get("codex_status") == "AVAILABLE" and (
                existing.get("verified_prefix_sha256") == bundle["verified_prefix_sha256"]
                or not latest_shift
                or latest_shift <= str(existing.get("causal_as_of", ""))
            ):
                return {**existing, "cached": True}
            try:
                answer = self.client.explain("CURRENT_CONTEXT", bundle)
                codex_status = "AVAILABLE"
            except Exception as error:
                answer = {
                    "headline": "Deterministic inventory context",
                    "summary": "Codex commentary is temporarily unavailable; transparent market-profile analysis remains available.",
                }
                codex_status = f"UNAVAILABLE:{type(error).__name__}"
            payload = compact_commentary(bundle, answer, shifts)
            payload["codex_status"] = codex_status
            if codex_status != "AVAILABLE":
                payload["codex_error"] = str(error)[:500]
            return {**self.store.put(session, payload), "cached": False}
        finally:
            self._lock.release()


@dataclass
class ReplayCommentaryQueue:
    """Bounded single-writer queue; HTTP clients never call Codex directly."""
    coordinator: ReplayCommentaryCoordinator
    hourly_limit: int = 30
    maximum_pending: int = 256
    _pending: deque[tuple[str, str]] = field(default_factory=deque, init=False, repr=False)
    _known: set[tuple[str, str]] = field(default_factory=set, init=False, repr=False)
    _calls: deque[float] = field(default_factory=deque, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _wake: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    last_error: str | None = field(default=None, init=False)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="replay-central-commentary", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def request(self, session: str, as_of: str) -> str:
        key = (session, as_of)
        exact = self.coordinator.store.exact(session, as_of)
        if (exact is not None and exact.get("generation_revision") == GENERATION_REVISION
                and exact.get("codex_status") == "AVAILABLE"):
            return "STORED"
        with self._lock:
            if key in self._known:
                return "PENDING"
            if len(self._pending) >= self.maximum_pending:
                return "QUEUE_FULL"
            self._known.add(key)
            self._pending.append(key)
            self._wake.set()
        return "PENDING"

    def status(self) -> dict[str, object]:
        with self._lock:
            pending = len(self._pending)
        return {"state": "RUNNING", "pending": pending, "hourly_limit": self.hourly_limit,
                "last_error": self.last_error}

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(1.0)
            self._wake.clear()
            while not self._stop.is_set():
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 3600:
                    self._calls.popleft()
                if len(self._calls) >= self.hourly_limit:
                    break
                with self._lock:
                    if not self._pending:
                        break
                    session, as_of = self._pending.popleft()
                try:
                    self._calls.append(time.monotonic())
                    self.coordinator.generate(session, as_of)
                    self.last_error = None
                except Exception as error:
                    self.last_error = f"{type(error).__name__}: {error}"[:500]
                finally:
                    with self._lock:
                        self._known.discard((session, as_of))


def live_fact_bundle(snapshot: dict[str, object]) -> dict[str, object]:
    observations = snapshot.get("observations", [])
    if not isinstance(observations, list) or not observations:
        raise ValueError("live commentary requires a synchronized market observation")
    latest = observations[-1]
    if not isinstance(latest, dict):
        raise ValueError("latest live observation is invalid")
    events = snapshot.get("events", [])
    option_event = next(
        (row for row in reversed(events) if isinstance(row, dict) and row.get("kind") == "OPTION_PRESSURE"),
        None,
    ) if isinstance(events, list) else None
    strikes = option_event.get("values", {}).get("strike_oi", []) if option_event else []
    option_summary = {}
    for option_type in ("CE", "PE"):
        rows = [row for row in strikes if isinstance(row, dict) and row.get("option_type") == option_type]
        option_summary[option_type] = {
            "absolute_oi_total": sum(float(row.get("oi", 0) or 0) for row in rows),
            "delta_oi_total": sum(float(row.get("delta_oi", 0) or 0) for row in rows),
            "strikes": rows,
        }
    causal_as_of = str(latest.get("receipt_timestamp") or latest.get("timestamp") or snapshot.get("server_time"))
    compact_market = {
        "i": latest.get("index_price"), "f": latest.get("futures_price"),
        "b": latest.get("basis"), "t": causal_as_of,
    }
    facts = {
        "schema": "NEW_DIVERGENCE_CODEX_LIVE_FACTS_V1",
        "runtime_version": RUNTIME_VERSION,
        "classification": "DIAGNOSTIC_NOT_A_SIGNAL",
        "session": snapshot.get("session"),
        "causal_as_of": causal_as_of,
        "latest_market": compact_market,
        "latest_state": (snapshot.get("evidence") or [None])[-1],
        "latest_option_summary": option_summary,
        "recent_events": events[-20:] if isinstance(events, list) else [],
        "recent_visible_transitions": (snapshot.get("transitions") or [])[-12:],
        "visible_intraday_inventory": {},
        "recent_intraday_inventory_shifts": {},
        "availability": "LIVE_PREFIX_ONLY",
    }
    facts["verified_prefix_sha256"] = hashlib.sha256(_canonical(facts)).hexdigest()
    return facts


@dataclass
class LiveCommentaryCoordinator:
    store: CommentaryStore
    client: CodexAppServerClient
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def generate(self, snapshot: dict[str, object]) -> dict[str, object]:
        bundle = live_fact_bundle(snapshot)
        session = str(bundle["session"])
        existing = self.store.current(session, str(bundle["causal_as_of"]))
        transitions = bundle.get("recent_visible_transitions", [])
        latest_transition = transitions[-1] if isinstance(transitions, list) and transitions else None
        trigger = hashlib.sha256(_canonical({
            "option": bundle.get("latest_option_summary"), "transition": latest_transition,
        })).hexdigest()
        if existing and existing.get("codex_status") == "AVAILABLE" and existing.get("live_trigger_sha256") == trigger:
            return {**existing, "cached": True}
        if not self._lock.acquire(blocking=False):
            if existing:
                return {**existing, "cached": True, "generation_in_progress": True}
            raise RuntimeError("central live commentary generation is already running")
        try:
            try:
                answer = self.client.explain("CURRENT_CONTEXT", bundle)
                codex_status = "AVAILABLE"
            except Exception as error:
                answer = {
                    "headline": "Deterministic live inventory context",
                    "summary": "Codex commentary is temporarily unavailable; transparent market-profile analysis remains available.",
                }
                codex_status = f"UNAVAILABLE:{type(error).__name__}"
            payload = compact_commentary(bundle, answer, [])
            payload["codex_status"] = codex_status
            if codex_status != "AVAILABLE":
                payload["codex_error"] = str(error)[:500]
            payload["live_trigger_sha256"] = trigger
            return {**self.store.put(session, payload), "cached": False}
        finally:
            self._lock.release()
