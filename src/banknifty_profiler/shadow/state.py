from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


IST = ZoneInfo("Asia/Kolkata")


class ShadowState:
    def __init__(self, ingestor, activation, orchestrator=None):
        self.ingestor = ingestor
        self.activation = activation
        self.orchestrator = orchestrator
        self.started = datetime.now(IST)
        self.last_error = ""

    def analytical_snapshot(self):
        return (
            self.orchestrator.snapshot(flush_dirty=False)
            if self.orchestrator is not None else {}
        )

    def ages(self):
        current = pd.Timestamp(datetime.now(IST))
        # Tests and pre-R6E state may have only `latest`; production uses the
        # valid-evidence clock so null depth messages cannot imply readiness.
        receipts = self.ingestor.latest_valid or self.ingestor.latest
        output = {}
        for key, value in receipts.items():
            try:
                output[key] = (current - pd.Timestamp(value)).total_seconds()
            except (TypeError, ValueError):
                output[key] = None
        return output

    def availability(self):
        analytical = self.analytical_snapshot()
        if analytical and analytical.get("availability"):
            if self.orchestrator is not None and hasattr(
                self.orchestrator, "operational_availability"
            ):
                return self.orchestrator.operational_availability()
            return analytical["availability"]
        ages = self.ages()
        limits = self.ingestor.c["config"]["freshness_seconds"]
        index = ages.get("INDEX")
        futures = ages.get("FUTURES")
        futures_oi = ages.get("FUTURES_OI")
        ce = ages.get("CE", ages.get("OPTION_OI"))
        pe = ages.get("PE", ages.get("OPTION_OI"))
        market = (
            index is not None
            and futures is not None
            and 0 <= index <= limits["index"]
            and 0 <= futures <= limits["futures"]
        )
        intraday = (
            "AVAILABLE"
            if market
            else "STALE"
            if index is not None or futures is not None
            else "MISSING"
        )
        fixed = "INSUFFICIENT_PRIOR_SESSIONS"
        state = (
            "LIVE_INTRADAY_ONLY"
            if market
            else "STALE_PARTIAL"
            if index is not None or futures is not None
            else "NO_VALID_MARKET_DATA"
        )
        return {
            "3D": fixed,
            "2D": fixed,
            "1D": fixed,
            "Intraday": intraday,
            "Divergence": "AVAILABLE" if market else "STALE_DATA",
            "Lifecycle": "AVAILABLE" if market else "STALE_DATA",
            "FuturesParticipation": "AVAILABLE"
            if futures_oi is not None and 0 <= futures_oi <= limits["futures_oi"]
            else "STALE",
            "CEParticipation": "AVAILABLE"
            if ce is not None and 0 <= ce <= limits["ce"]
            else "STALE",
            "PEParticipation": "AVAILABLE"
            if pe is not None and 0 <= pe <= limits["pe"]
            else "STALE",
            "overall_state": state,
            "market_display_enabled": market,
        }

    def health(self):
        return {
            "alive": True,
            "classification": self.ingestor.c["config"]["classification"],
            "started_at": self.started.isoformat(),
        }

    def readiness(self):
        availability = self.availability()
        checkpoint = self.ingestor.checkpoint_health()
        causality = (
            self.orchestrator.causality_metrics()
            if self.orchestrator is not None
            and hasattr(self.orchestrator, "causality_metrics")
            else {
                "valid_basis_pairs": 0,
                "future_joins": 0,
                "synchronization_tolerance_violations": 0,
            }
        )
        reasons = []
        if self.last_error:
            reasons.append(self.last_error)
        if availability.get("overall_state") in {
            "NO_VALID_MARKET_DATA",
            "STALE_PARTIAL",
        }:
            reasons.append("REQUIRED_MARKET_INPUTS_UNAVAILABLE_OR_STALE")
        if not checkpoint["valid"]:
            reasons.append("CHECKPOINT_INTEGRITY_FAILED")
        if causality["future_joins"]:
            reasons.append("FUTURE_JOIN_DETECTED")
        if causality["synchronization_tolerance_violations"]:
            reasons.append("SYNCHRONIZATION_TOLERANCE_VIOLATION")
        source_identity_verified = bool(
            self.ingestor.c.get("engine_source_verified", False)
        )
        if not source_identity_verified:
            reasons.append("ENGINE_SOURCE_IDENTITY_UNVERIFIED")
        ready = not reasons
        return {
            "ready": ready,
            "reasons": reasons,
            "engine_hash": self.ingestor.c["engine_hash"],
            "configuration_hash": self.ingestor.c["configuration_hash"],
            "checkpoint_valid": checkpoint["valid"],
            "checkpoint": checkpoint,
            **causality,
            "runtime_source_identity_verified": source_identity_verified,
            "manifest_verified": source_identity_verified,
        }

    def status(self):
        analytical = self.analytical_snapshot()
        return {
            "activation": self.activation,
            "operational_diagnostic_only": True,
            "prospective_session_eligible": False,
            "availability": self.availability(),
            "ages_seconds": self.ages(),
            "metrics": self.ingestor.metrics,
            "latest_receipts": self.ingestor.latest,
            "latest_valid_receipts": self.ingestor.latest_valid,
            "raw_run_id": self.ingestor.c["raw_run_id"],
            "analytical_session": analytical.get("session_date", ""),
            "analytical_counts": analytical.get("counts", {}),
        }
