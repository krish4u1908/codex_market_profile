from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
import threading
import time
from zoneinfo import ZoneInfo

from . import VERSION
from .projection import baseline_payload, chart_inputs, v2_payload
from .source import SharedSource, WaitingForMetadata
from .indicator_inputs import IndicatorInputs, SCHEMA
from .option_reports import OptionReportCache, SCHEMA as REPORT_SCHEMA
from .storage import atomic_write, encode, PublishedStore
from .vendor import load

IST = ZoneInfo("Asia/Kolkata")


class InstanceLock:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a+")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise RuntimeError("Another core already owns this instrument state") from None
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(str(os.getpid()) + "\n")
        self.handle.flush()

    def close(self):
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


class Runtime:
    def __init__(self, config):
        config.validate()
        self.config = config
        self.instance_lock = InstanceLock(config.lock_path)
        try:
            self.vendor = load(config.instrument)
            self.context = self.vendor.LiveContext(config.state_root / "runtime", str(config.collector_root), config.poll_seconds)
        except Exception:
            self.instance_lock.close()
            raise
        # LiveContext.start/run is deliberately never used: it would create a
        # second collector and authority. We supply the one shared snapshot.
        self.source = SharedSource(config, self.vendor)
        self.store = PublishedStore(config)
        self.option_reports = OptionReportCache(config)
        self.store.option_reports = self.option_reports
        self.option_report_status = dict(schema=REPORT_SCHEMA, status="PENDING")
        self.stop = threading.Event()
        self.thread = self.maintenance_thread = None
        self.error = self.context_error = self.last_poll = self.last_price = None
        self.waiting_reason = None
        self.indicator_reader = None
        self.indicator_status = {'schema': SCHEMA, 'status': 'WAITING'}
        self.last_session = self.prior = None
        self.prior_generation = -1
        self.maintenance_generation = 0
        self.maintenance_status = "waiting for overnight window"
        self._health()

    def _prior(self, day):
        retained = self.config.state_root / "prior-publications" / (day + ".json")
        if retained.is_file():
            return json.loads(retained.read_text())
        value = self.vendor.projection.inventory_context_for_session(day,
            self.config.context_root or self.config.state_root / "prior-context")
        available_at = datetime.now(timezone.utc).isoformat()
        for row in value.get("controls", []):
            row["available_at"] = available_at
        if value.get("status") in {"AVAILABLE", "PARTIAL"}:
            # Freeze the first verified prior context for this live session.
            atomic_write(retained, encode(value))
        return value

    def _health(self):
        wall = datetime.now(timezone.utc)
        local = wall.astimezone(IST)
        market_open = local.weekday() < 5 and (9, 15) <= (local.hour, local.minute) <= (15, 30)
        age = (wall - self.last_price).total_seconds() if self.last_price else None
        status = "error" if self.error else "waiting" if not self.last_price else "stale" if market_open and age > 30 else "ready"
        self.store.set_health(dict(version=VERSION, instrument=self.config.instrument,
            status=status, market_open=market_open, server_time=wall.isoformat(),
            last_poll_at=self.last_poll, last_price_at=self.last_price.isoformat() if self.last_price else None,
            price_age_seconds=age, error=self.error, waiting_reason=self.waiting_reason, v2_context_error=self.context_error,
            session=self.last_session, pid=os.getpid(), authority_instances=1 if self.source.authority else 0,
            gui_independent=True, baseline_rules="1.0.62", v2_context_version="2.0.0",
            overnight_context=self.maintenance_status, indicator_inputs=self.indicator_status, option_report_inputs=self.option_report_status))

    def tick(self, now=None):
        wall = now or datetime.now(timezone.utc)
        day = wall.astimezone(IST).date().isoformat()
        option_reports = self.option_reports.request(day)['feed']
        self.option_report_status = {k: option_reports[k] for k in ('schema', 'status', 'quality') if k in option_reports}
        if day != self.last_session:
            self.store.reset_live()
            self.last_session, self.prior, self.last_price = day, None, None
            self.indicator_reader = None
            self.indicator_status = {'schema': SCHEMA, 'status': 'WAITING'}
        try:
            snapshot = self.source.snapshot(wall)
            self.waiting_reason = None
            self.last_poll = datetime.now(timezone.utc).isoformat()
            try:
                # Preserve the V2 actual-publication clock and its original
                # current-minute-only publication policy.
                self.context.ingest(snapshot)
                self.context_error = None
            except Exception as exc:
                self.context_error = type(exc).__name__ + ": " + str(exc)
            if self.prior is None or self.prior_generation != self.maintenance_generation:
                self.prior = self._prior(day)
                self.prior_generation = self.maintenance_generation
            inputs = chart_inputs(self.source, snapshot, self.config, self.prior)
            indicator_inputs = None
            try:
                if self.indicator_reader is None:
                    self.indicator_reader = IndicatorInputs(self.config, day)
                indicator_inputs = self.indicator_reader.poll()
                self.indicator_status = {key: indicator_inputs[key] for key in ('schema', 'status', 'error', 'quality', 'as_of')}
                self.store.publish_indicator_inputs(indicator_inputs)
            except Exception as exc:
                self.indicator_status = {'schema': SCHEMA, 'status': 'ERROR', 'error': type(exc).__name__ + ': ' + str(exc)}
                self.store.publish_indicator_inputs(self.indicator_status)
            if snapshot["observations"]:
                self.last_price = self.vendor.clock.parse_instant(snapshot["observations"][-1]["timestamp"])
                for profile, payload in [
                    (self.config.profile("v1062"), baseline_payload(self.source, snapshot, self.config, inputs)),
                    (self.config.profile("v200"), v2_payload(self.context, snapshot, self.config, inputs)),
                ]:
                    payload["live"] = dict(session=day, server_time=datetime.now(timezone.utc).isoformat(),
                        sequence=snapshot["sequence"], publication_clock="ACTUAL_LIVE_CALCULATION_COMPLETION")
                    if profile.endswith('-v200'):
                        payload['option_report_inputs'] = option_reports
                    if indicator_inputs is not None:
                        payload['indicator_inputs'] = indicator_inputs
                    else:
                        payload['indicator_inputs'] = dict(self.indicator_status, instrument=self.config.instrument, session=day)
                    self.store.publish(profile, payload, live=True)
            self.error = None
        except WaitingForMetadata as exc:
            self.waiting_reason = str(exc)
            self.error = None
        except Exception as exc:
            self.error = type(exc).__name__ + ": " + str(exc)
        self._health()

    def _run(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(self.config.poll_seconds)

    def _overnight(self):
        # A thread inside the instrument core replaces the old separate nightly
        # service. It never reads/writes the live authority's journals or DB.
        marker = self.config.state_root / "prior-context/completed.json"
        while not self.stop.wait(30):
            local = datetime.now(IST)
            if not ((0, 15) <= (local.hour, local.minute) < (8, 45)):
                continue
            cutoff = (local.date() - timedelta(days=1)).isoformat()
            try:
                if marker.exists() and json.loads(marker.read_text()).get("cutoff") == cutoff:
                    continue
                self.maintenance_status = "building prior context through " + cutoff
                from v2_engine.new_divergence.nightly_context import run_nightly_context
                result = run_nightly_context(self.config.collector_root,
                    self.config.context_root or self.config.state_root / "prior-context",
                    cutoff_session=local.date() - timedelta(days=1))
                atomic_write(marker, encode({"cutoff": cutoff, "completed_at": datetime.now(timezone.utc).isoformat()}))
                self.maintenance_generation += 1
                self.maintenance_status = "completed through " + cutoff
            except Exception as exc:
                self.maintenance_status = type(exc).__name__ + ": " + str(exc)
                self.stop.wait(900)

    def start(self):
        if self.thread:
            raise RuntimeError("Core already started")
        self.thread = threading.Thread(target=self._run, name="shared-market-authority", daemon=True)
        self.option_reports.start()
        self.maintenance_thread = threading.Thread(target=self._overnight, name="prior-context", daemon=True)
        self.thread.start()
        self.maintenance_thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
        if self.maintenance_thread:
            self.maintenance_thread.join()
        self.context.close()
        self.option_reports.close()
        self.instance_lock.close()
