"""One file reader and one authority; no GUI or V2-context polling thread."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class WaitingForMetadata(ValueError):
    pass


class SharedSource:
    def __init__(self, config, vendor):
        self.config, self.vendor = config, vendor
        self.day = self.authority = self.tail = self.failure = None

    def snapshot(self, now=None):
        now = now or datetime.now(timezone.utc)
        day = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
        if self.day != day:
            self.day, self.authority, self.tail, self.failure = day, None, None, None
        if self.failure:
            raise RuntimeError("Collector recovery required; restart after resolving: " + self.failure)
        if not self.config.collector_root.is_dir():
            raise FileNotFoundError("Collector root unavailable")
        if self.tail is None:
            override = (self.config.futures_symbols_by_session or {}).get(day.isoformat())
            tail = self.vendor.LiveCollectorTail(self.config.collector_root, day, futures_symbol=override)
            selected = tail.adapter.selected_futures_symbol
            if selected is None:
                raise WaitingForMetadata("Waiting for current-session " + self.config.instrument + " futures metadata")
            if override and tail.adapter._metadata_future and override != tail.adapter._metadata_future:
                raise ValueError("Futures override conflicts with current-session metadata")
            authority = self.vendor.LiveAuthority(self.config.state_root / "runtime/engine", day)
            authority.cash_vix_source = self.vendor.LiveCashVixSource(self.config.collector_root, day,
                authority.root / "cash_vix_first_observed_v2.jsonl")
            authority.recover()
            if authority.engine.futures_symbol and authority.engine.futures_symbol != selected:
                raise ValueError("Futures contract conflicts with recovered state")
            self.tail = self.vendor.LiveCollectorTail(self.config.collector_root, day,
                offsets=authority.source_offsets, futures_symbol=selected)
            self.authority = authority
        try:
            events, offsets = self.tail.poll()
            self.authority.stage(events, offsets)
            self.authority.commit_ready(now - timedelta(seconds=3))
            self.authority.publish_due_direction()
            return self.authority.browser_snapshot(observation_limit=None)
        except Exception as exc:
            self.failure = type(exc).__name__ + ": " + str(exc)
            raise
