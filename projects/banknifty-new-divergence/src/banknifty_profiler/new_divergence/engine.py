"""Single causal divergence engine for replay and shadow-live inputs."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from .clock import inside_session_window, iso_utc, parse_instant
from .contracts import (
    BasisObservation,
    BasisState,
    EngineConfig,
    EpisodeState,
    EpisodeTransition,
    EventKind,
    EvidenceSnapshot,
    MarketEvent,
)
from .ledger import TransitionLedger
from .statistics import OrderStatisticMultiset


@dataclass
class _OpenEpisode:
    episode_id: str
    direction: BasisState
    colour: str
    state: EpisodeState
    started_at: datetime
    last_seen_at: datetime
    observations: int = 1
    transitions: int = 0


class CausalDivergenceEngine:
    """Consume normalized records once, strictly in receipt order.

    Event timestamps are retained as source evidence.  Availability,
    publication, matching, and every state transition are governed only by the
    receipt timestamp.  The engine is deliberately unaware of future outcomes.
    """

    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        ledger_path: Path | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.ledger = TransitionLedger(ledger_path)
        self.session: date | None = None
        self._last_sort_key: tuple | None = None
        self._seen_events: set[str] = set()
        self._index_tick: MarketEvent | None = None
        self._index_open_tick: MarketEvent | None = None
        self._index_symbol: str | None = None
        self._futures_symbol: str | None = None
        self._observations: list[BasisObservation] = []
        self._timeline: list[BasisObservation | None] = []
        self._timeline_times: list[datetime] = []
        self._timeline_valid_prefix: list[int] = []
        self._basis_distribution = OrderStatisticMultiset()
        self._continuous_basis_since: datetime | None = None
        self._last_valid_basis_at: datetime | None = None
        self._latest_aux: dict[EventKind, MarketEvent] = {}
        self._controls: dict[str, MarketEvent] = {}
        self._open: _OpenEpisode | None = None
        self._episode_sequence = 0
        self._latest_evidence: EvidenceSnapshot | None = None
        self._evidence_history: list[EvidenceSnapshot] = []
        self.diagnostics: list[dict[str, object]] = []

    @property
    def transitions(self) -> tuple[EpisodeTransition, ...]:
        return tuple(self.ledger.records)

    @property
    def observations(self) -> tuple[BasisObservation, ...]:
        return tuple(self._observations)

    @property
    def index_symbol(self) -> str | None:
        return self._index_symbol

    @property
    def index_open_tick(self) -> MarketEvent | None:
        """First valid Index tick accepted inside the configured session."""

        return self._index_open_tick

    @property
    def futures_symbol(self) -> str | None:
        return self._futures_symbol

    @property
    def latest_evidence(self) -> EvidenceSnapshot | None:
        return self._latest_evidence

    @property
    def evidence_snapshots(self) -> tuple[EvidenceSnapshot, ...]:
        return tuple(self._evidence_history)

    def _append_timeline(self, timestamp: datetime, observation: BasisObservation | None) -> None:
        self._timeline_times.append(timestamp)
        self._timeline.append(observation)
        previous = self._timeline_valid_prefix[-1] if self._timeline_valid_prefix else 0
        self._timeline_valid_prefix.append(previous + (observation is not None))
        if observation is None:
            self._continuous_basis_since = None

    def _continue_basis_timeline(self, timestamp: datetime) -> None:
        previous = self._last_valid_basis_at
        if (
            self._continuous_basis_since is None
            or previous is None
            or (timestamp - previous).total_seconds()
            > self.config.horizon_gap_tolerance_seconds
        ):
            self._continuous_basis_since = timestamp
        self._last_valid_basis_at = timestamp

    def _diagnostic(self, event: MarketEvent, reason: str, **details: object) -> None:
        self.diagnostics.append({
            "event_id": event.event_id,
            "receipt_timestamp": iso_utc(event.receipt_timestamp),
            "reason": reason,
            **details,
        })

    def ingest(self, event: MarketEvent) -> tuple[EpisodeTransition, ...]:
        if event.event_id in self._seen_events:
            self._diagnostic(event, "DUPLICATE_EVENT_ID")
            return ()
        if self._last_sort_key is not None and event.sort_key < self._last_sort_key:
            self._diagnostic(event, "OUT_OF_ORDER_RECEIPT_REFUSED")
            return ()
        if self.session is None:
            self.session = event.session
        elif event.session != self.session:
            raise ValueError("one engine instance may process only one exchange session")
        self._seen_events.add(event.event_id)
        self._last_sort_key = event.sort_key

        if event.kind == EventKind.INDEX_TICK:
            if not self._inside_market_session(event.receipt_timestamp):
                self._diagnostic(event, "OUTSIDE_MARKET_SESSION_REFUSED")
                return ()
            if self._index_symbol is None:
                self._index_symbol = event.symbol
            if event.symbol != self._index_symbol:
                self._diagnostic(event, "INDEX_SYMBOL_SWITCH_REFUSED", expected=self._index_symbol)
                return ()
            if self._index_open_tick is None:
                self._index_open_tick = event
            self._index_tick = event
            return ()
        if event.kind == EventKind.FUTURES_TICK:
            if not self._inside_market_session(event.receipt_timestamp):
                self._diagnostic(event, "OUTSIDE_MARKET_SESSION_REFUSED")
                return ()
            if self._futures_symbol is None:
                self._futures_symbol = event.symbol
            if event.symbol != self._futures_symbol:
                self._diagnostic(event, "FUTURES_SYMBOL_SWITCH_REFUSED", expected=self._futures_symbol)
                return ()
            return self._on_futures_tick(event)
        if event.kind == EventKind.CONTROL:
            self._controls[str(event.values["control_id"])] = event
        else:
            self._latest_aux[event.kind] = event
        if event.kind == EventKind.HEARTBEAT:
            return self._on_heartbeat(event.receipt_timestamp)
        return ()

    def _on_futures_tick(self, event: MarketEvent) -> tuple[EpisodeTransition, ...]:
        if self._index_tick is None:
            self._append_timeline(event.receipt_timestamp, None)
            self._diagnostic(event, "UNMATCHED_NO_PRIOR_INDEX")
            return self._handle_gap(event.receipt_timestamp)
        age_ms = (event.receipt_timestamp - self._index_tick.receipt_timestamp).total_seconds() * 1000
        if age_ms < 0:
            self._append_timeline(event.receipt_timestamp, None)
            self._diagnostic(event, "FUTURE_INDEX_JOIN_REFUSED", synchronization_age_ms=age_ms)
            return self._handle_gap(event.receipt_timestamp)
        if age_ms > self.config.match_tolerance_ms:
            self._append_timeline(event.receipt_timestamp, None)
            self._diagnostic(event, "UNMATCHED_TOLERANCE_EXCEEDED", synchronization_age_ms=age_ms)
            return self._handle_gap(event.receipt_timestamp)
        observation = BasisObservation(
            session=event.session,
            timestamp=event.receipt_timestamp,
            index_receipt_timestamp=self._index_tick.receipt_timestamp,
            futures_receipt_timestamp=event.receipt_timestamp,
            index_price=float(self._index_tick.values["price"]),
            futures_price=float(event.values["price"]),
            basis=float(event.values["price"]) - float(self._index_tick.values["price"]),
            synchronization_age_ms=age_ms,
        )
        self._continue_basis_timeline(observation.timestamp)
        self._observations.append(observation)
        self._append_timeline(observation.timestamp, observation)
        self._basis_distribution.add(observation.basis)
        state, supporting, horizon_evidence, percentile, robust_z = self._classify(observation)
        if self._open is None and not self._inside_discovery(observation.timestamp):
            state = BasisState.OUTSIDE_DISCOVERY_WINDOW
        evidence = self._snapshot(
            observation,
            state,
            supporting,
            horizon_evidence,
            percentile,
            robust_z,
        )
        self._latest_evidence = evidence
        self._evidence_history.append(evidence)
        return self._advance_episode(evidence)

    def _classify(
        self, observation: BasisObservation
    ) -> tuple[BasisState, int, dict[str, dict[str, object]], float, float]:
        percentile = self._basis_distribution.percentile_le(observation.basis)
        median = self._basis_distribution.median()
        mad = self._basis_distribution.mad(median)
        robust_z = 0.0 if mad == 0 else 0.6745 * (observation.basis - median) / mad
        rows: dict[str, dict[str, object]] = {}
        states: list[BasisState] = []
        for minutes in self.config.horizons_minutes:
            target = observation.timestamp - timedelta(minutes=minutes)
            index = bisect_right(self._timeline_times, target) - 1
            prior = None if index < 0 else self._timeline[index]
            if prior is None:
                state = BasisState.UNKNOWN_GAP
                rows[f"{minutes}m"] = {
                    "state": state.value,
                    "reason": "NO_PRIOR_OBSERVATION" if index < 0 else "PRIOR_OBSERVATION_UNMATCHED",
                    "target_timestamp": iso_utc(target),
                }
            elif self._continuous_basis_since is None or target < self._continuous_basis_since:
                state = BasisState.UNKNOWN_GAP
                rows[f"{minutes}m"] = {
                    "state": state.value,
                    "reason": "INSUFFICIENT_CONTINUOUS_HISTORY_AFTER_GAP",
                    "target_timestamp": iso_utc(target),
                    "prior_timestamp": iso_utc(prior.timestamp),
                    "continuous_since": None if self._continuous_basis_since is None else iso_utc(
                        self._continuous_basis_since
                    ),
                    "actual_elapsed_seconds": (observation.timestamp - prior.timestamp).total_seconds(),
                }
            else:
                reference_lag = (target - prior.timestamp).total_seconds()
                if reference_lag > self.config.horizon_gap_tolerance_seconds:
                    state = BasisState.UNKNOWN_GAP
                    rows[f"{minutes}m"] = {
                        "state": state.value,
                        "reason": "STALE_HORIZON_REFERENCE",
                        "target_timestamp": iso_utc(target),
                        "prior_timestamp": iso_utc(prior.timestamp),
                        "reference_lag_seconds": reference_lag,
                        "actual_elapsed_seconds": (observation.timestamp - prior.timestamp).total_seconds(),
                    }
                else:
                    index_change = observation.index_price - prior.index_price
                    futures_change = observation.futures_price - prior.futures_price
                    basis_change = observation.basis - prior.basis
                    high = percentile >= self.config.high_percentile or robust_z >= self.config.robust_z_threshold
                    low = percentile <= self.config.low_percentile or robust_z <= -self.config.robust_z_threshold
                    if index_change <= -self.config.index_material_points and (
                        basis_change >= self.config.basis_material_points or high
                    ):
                        state = BasisState.GREEN_CANDIDATE
                    elif index_change >= self.config.index_material_points and (
                        basis_change <= -self.config.basis_material_points or low
                    ):
                        state = BasisState.RED_CANDIDATE
                    else:
                        state = BasisState.NEUTRAL_BLUE
                    rows[f"{minutes}m"] = {
                        "state": state.value,
                        "target_timestamp": iso_utc(target),
                        "prior_timestamp": iso_utc(prior.timestamp),
                        "reference_lag_seconds": reference_lag,
                        "actual_elapsed_seconds": (observation.timestamp - prior.timestamp).total_seconds(),
                        "index_change": index_change,
                        "futures_change": futures_change,
                        "basis_change": basis_change,
                        "observation_count": self._timeline_valid_prefix[-1] - (
                            self._timeline_valid_prefix[index - 1] if index else 0
                        ),
                    }
            states.append(state)
        green = sum(state == BasisState.GREEN_CANDIDATE for state in states)
        red = sum(state == BasisState.RED_CANDIDATE for state in states)
        valid = sum(state != BasisState.UNKNOWN_GAP for state in states)
        supporting = max(green, red)
        if green >= self.config.minimum_supporting_horizons:
            aggregate = BasisState.GREEN_CANDIDATE
        elif red >= self.config.minimum_supporting_horizons:
            aggregate = BasisState.RED_CANDIDATE
        elif valid < self.config.minimum_supporting_horizons:
            aggregate = BasisState.UNKNOWN_GAP
        else:
            aggregate = BasisState.NEUTRAL_BLUE
        return aggregate, supporting, rows, percentile, robust_z

    def _visible_aux(self, kind: EventKind, as_of: datetime) -> Mapping[str, object] | None:
        event = self._latest_aux.get(kind)
        if event is None:
            return None
        age = (as_of - event.receipt_timestamp).total_seconds()
        if age < 0 or age > self.config.participation_max_age_seconds:
            return None
        compact_values = {
            key: value for key, value in event.values.items()
            if key != "strike_oi"
        }
        return {
            **compact_values,
            "symbol": event.symbol,
            "event_id": event.event_id,
            "receipt_timestamp": iso_utc(event.receipt_timestamp),
            "age_seconds": age,
        }

    def _nearest_control(self, observation: BasisObservation) -> Mapping[str, object] | None:
        visible = [
            event for event in self._controls.values()
            if event.receipt_timestamp <= observation.timestamp
        ]
        if not visible:
            return None
        control = min(
            visible,
            key=lambda event: (
                abs(float(event.values["price"]) - observation.index_price),
                str(event.values["control_id"]),
            ),
        )
        distance = observation.index_price - float(control.values["price"])
        return {
            **control.values,
            "event_id": control.event_id,
            "receipt_timestamp": iso_utc(control.receipt_timestamp),
            "distance_points": distance,
            "within_proximity": abs(distance) <= self.config.control_proximity_points,
        }

    def _snapshot(
        self,
        observation: BasisObservation,
        state: BasisState,
        supporting: int,
        horizons: Mapping[str, Mapping[str, object]],
        percentile: float,
        robust_z: float,
    ) -> EvidenceSnapshot:
        option = self._visible_aux(EventKind.OPTION_PRESSURE, observation.timestamp)
        cash = self._visible_aux(EventKind.CASH_PRESSURE, observation.timestamp)
        contradictions = []
        expected = 1 if state == BasisState.GREEN_CANDIDATE else -1 if state == BasisState.RED_CANDIDATE else 0
        for label, row in (("OPTION", option), ("CASH", cash)):
            if expected and row is not None and float(row.get("score", 0)) * expected < 0:
                contradictions.append(f"{label}_PRESSURE_OPPOSES_BASIS_STATE")
        return EvidenceSnapshot(
            as_of=observation.timestamp,
            basis_state=state,
            supporting_horizons=supporting,
            basis=observation,
            horizon_evidence=horizons,
            basis_percentile=percentile,
            basis_robust_z=robust_z,
            futures_oi=self._visible_aux(EventKind.FUTURES_OI, observation.timestamp),
            option_pressure=option,
            cash_pressure=cash,
            control_interaction=self._visible_aux(EventKind.CONTROL_INTERACTION, observation.timestamp),
            nearest_control=self._nearest_control(observation),
            contradictions=tuple(contradictions),
        )

    def _inside_discovery(self, timestamp: datetime) -> bool:
        assert self.session is not None
        return inside_session_window(
            timestamp,
            self.session,
            self.config.discovery_start,
            self.config.discovery_end,
        )

    def _inside_market_session(self, timestamp: datetime) -> bool:
        assert self.session is not None
        return inside_session_window(
            timestamp,
            self.session,
            self.config.session_start,
            self.config.session_end,
            include_end=True,
        )

    def _new_episode(self, evidence: EvidenceSnapshot) -> EpisodeTransition:
        self._episode_sequence += 1
        direction = evidence.basis_state
        colour = "GREEN" if direction == BasisState.GREEN_CANDIDATE else "RED"
        compact = evidence.as_of.strftime("%H%M%S%f")
        identifier = f"{self.session.isoformat()}-E{self._episode_sequence:04d}-{colour}-{compact}"
        self._open = _OpenEpisode(
            episode_id=identifier,
            direction=direction,
            colour=colour,
            state=EpisodeState.CANDIDATE,
            started_at=evidence.as_of,
            last_seen_at=evidence.as_of,
        )
        return self._publish(EpisodeState.CANDIDATE, evidence, ("MULTI_HORIZON_BASIS_CANDIDATE",))

    def _publish(
        self,
        new_state: EpisodeState,
        evidence: EvidenceSnapshot,
        reasons: tuple[str, ...],
        *,
        published_at: datetime | None = None,
    ) -> EpisodeTransition:
        episode = self._open
        if episode is None:
            raise RuntimeError("cannot publish without an open episode")
        instant = evidence.as_of if published_at is None else parse_instant(published_at)
        episode.transitions += 1
        transition = EpisodeTransition(
            transition_id=f"{episode.episode_id}-T{episode.transitions:03d}",
            episode_id=episode.episode_id,
            session=self.session,
            previous_state="" if episode.transitions == 1 else episode.state.value,
            state=new_state,
            colour=episode.colour,
            published_at=instant,
            effective_at=instant,
            candidate_started_at=episode.started_at,
            reason_codes=reasons,
            evidence=evidence,
        )
        episode.state = new_state
        return self.ledger.append(transition)

    def _close(
        self,
        state: EpisodeState,
        evidence: EvidenceSnapshot,
        reasons: tuple[str, ...],
        *,
        published_at: datetime | None = None,
    ) -> EpisodeTransition:
        transition = self._publish(state, evidence, reasons, published_at=published_at)
        self._open = None
        return transition

    def _advance_episode(self, evidence: EvidenceSnapshot) -> tuple[EpisodeTransition, ...]:
        state = evidence.basis_state
        candidate = state in {BasisState.GREEN_CANDIDATE, BasisState.RED_CANDIDATE}
        emitted: list[EpisodeTransition] = []
        episode = self._open

        if episode is None:
            if candidate and self._inside_discovery(evidence.as_of):
                emitted.append(self._new_episode(evidence))
            return tuple(emitted)

        gap = (evidence.as_of - episode.last_seen_at).total_seconds()
        same_direction = state == episode.direction
        if candidate and same_direction and gap <= self.config.merge_gap_seconds:
            episode.last_seen_at = evidence.as_of
            episode.observations += 1
            age = (evidence.as_of - episode.started_at).total_seconds()
            if episode.state == EpisodeState.CANDIDATE and (
                age >= self.config.persistence_seconds
                and episode.observations >= self.config.persistence_observations
            ):
                emitted.append(self._publish(
                    EpisodeState.CONFIRMED,
                    evidence,
                    ("PERSISTENCE_SECONDS_MET", "PERSISTENCE_OBSERVATIONS_MET"),
                ))
            elif episode.state == EpisodeState.CONFIRMED:
                emitted.append(self._publish(
                    EpisodeState.ACTIVE,
                    evidence,
                    ("POST_CONFIRMATION_OBSERVATION_VISIBLE",),
                ))
            elif episode.state == EpisodeState.ACTIVE and age >= self.config.active_timeout_seconds:
                emitted.append(self._close(
                    EpisodeState.EXPIRED,
                    evidence,
                    ("ACTIVE_TIMEOUT_REACHED",),
                ))
            return tuple(emitted)

        if gap > self.config.merge_gap_seconds:
            terminal = EpisodeState.NO_EDGE if episode.state == EpisodeState.CANDIDATE else EpisodeState.EXPIRED
            emitted.append(self._close(terminal, evidence, ("OBSERVATION_GAP_EXCEEDED",)))
        elif candidate and not same_direction:
            terminal = EpisodeState.INVALIDATED if episode.state == EpisodeState.CANDIDATE else EpisodeState.ROTATION
            emitted.append(self._close(terminal, evidence, ("OPPOSITE_BASIS_STATE_VISIBLE",)))
        elif state == BasisState.UNKNOWN_GAP:
            terminal = EpisodeState.NO_EDGE if episode.state == EpisodeState.CANDIDATE else EpisodeState.EXPIRED
            emitted.append(self._close(terminal, evidence, ("BASIS_EVIDENCE_GAP",)))
        else:
            terminal = EpisodeState.NO_EDGE if episode.state == EpisodeState.CANDIDATE else EpisodeState.RESOLVED
            emitted.append(self._close(terminal, evidence, ("NEUTRAL_BASIS_STATE_VISIBLE",)))

        if candidate and self._inside_discovery(evidence.as_of):
            emitted.append(self._new_episode(evidence))
        return tuple(emitted)

    def _handle_gap(self, timestamp: datetime) -> tuple[EpisodeTransition, ...]:
        if self._open is None or self._latest_evidence is None:
            return ()
        if (timestamp - self._open.last_seen_at).total_seconds() <= self.config.merge_gap_seconds:
            return ()
        evidence = replace(
            self._latest_evidence,
            as_of=timestamp,
            basis_state=BasisState.UNKNOWN_GAP,
            contradictions=(*self._latest_evidence.contradictions, "SYNCHRONIZATION_GAP"),
        )
        terminal = EpisodeState.NO_EDGE if self._open.state == EpisodeState.CANDIDATE else EpisodeState.EXPIRED
        return (self._close(terminal, evidence, ("SYNCHRONIZATION_GAP",), published_at=timestamp),)

    def _on_heartbeat(self, timestamp: datetime) -> tuple[EpisodeTransition, ...]:
        if self._open is None or self._latest_evidence is None:
            return ()
        age = (timestamp - self._open.started_at).total_seconds()
        limit = (
            self.config.candidate_timeout_seconds
            if self._open.state == EpisodeState.CANDIDATE
            else self.config.active_timeout_seconds
        )
        if age < limit:
            return ()
        evidence = replace(
            self._latest_evidence,
            as_of=timestamp,
            contradictions=(*self._latest_evidence.contradictions, "BASIS_OBSERVATION_STALE"),
        )
        return (self._close(EpisodeState.EXPIRED, evidence, ("STATE_TIMEOUT_REACHED",), published_at=timestamp),)

    def finalize(self, timestamp: datetime | None = None) -> tuple[EpisodeTransition, ...]:
        """Explicitly close an open episode; never called implicitly at a replay cutoff."""

        if self._open is None or self._latest_evidence is None:
            return ()
        instant = self._open.last_seen_at if timestamp is None else parse_instant(timestamp)
        if instant < self._open.last_seen_at:
            raise ValueError("finalization cannot precede the latest episode observation")
        evidence = replace(self._latest_evidence, as_of=instant)
        terminal = EpisodeState.NO_EDGE if self._open.state == EpisodeState.CANDIDATE else EpisodeState.EXPIRED
        return (self._close(terminal, evidence, ("EXPLICIT_SESSION_FINALIZATION",), published_at=instant),)


def run_replay(
    events: Iterable[MarketEvent],
    config: EngineConfig | None = None,
    *,
    ledger_path: Path | None = None,
    finalize_at: datetime | None = None,
) -> CausalDivergenceEngine:
    engine = CausalDivergenceEngine(config, ledger_path=ledger_path)
    for event in events:
        engine.ingest(event)
    if finalize_at is not None:
        engine.finalize(finalize_at)
    return engine
