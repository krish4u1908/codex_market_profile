from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re


INSTRUMENTS = {"BANKNIFTY": "NSE:NIFTYBANK-INDEX", "NIFTY": "NSE:NIFTY50-INDEX"}


def session_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Expected a valid YYYY-MM-DD session")
    return value


@dataclass(frozen=True)
class Config:
    instrument: str
    collector_root: Path
    state_root: Path
    lock_path: Path
    host: str = "127.0.0.1"
    port: int = 8922
    poll_seconds: float = 10
    futures_symbols_by_session: dict | None = None
    context_root: Path | None = None

    @classmethod
    def read(cls, path):
        raw = json.loads(Path(path).read_text())
        if raw.get("version") != "3.0.0":
            raise ValueError("Expected a version 3.0.0 core configuration")
        config = cls(raw["instrument"], Path(raw["collector_root"]).resolve(),
            Path(raw["state_root"]).resolve(), Path(raw["lock_path"]).resolve(),
            raw.get("host", "127.0.0.1"), int(raw["port"]), float(raw.get("poll_seconds", 10)),
            raw.get("futures_symbols_by_session", {}),
            Path(raw["context_root"]).resolve() if raw.get("context_root") else None)
        config.validate()
        return config

    def validate(self):
        if self.instrument not in INSTRUMENTS:
            raise ValueError("Unknown instrument")
        if self.host != "127.0.0.1":
            raise ValueError("The core API must bind to loopback; expose the GUI proxy")
        if not 1024 <= self.port <= 65535 or not 5 <= self.poll_seconds <= 30:
            raise ValueError("Invalid API port or poll interval")
        if self.state_root == self.collector_root or self.collector_root in self.state_root.parents or self.state_root in self.collector_root.parents:
            raise ValueError("State and collector trees must not overlap")
        if self.lock_path == self.collector_root or self.collector_root in self.lock_path.parents:
            raise ValueError("The lock must be outside the collector tree")
        if self.context_root and self.state_root not in self.context_root.parents:
            raise ValueError("Prior context must be a separate directory inside this instrument's state tree")
        for day, symbol in (self.futures_symbols_by_session or {}).items():
            session_date(day)
            if not isinstance(symbol, str) or not re.fullmatch(r"NSE:" + self.instrument + r"\d{2}(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)FUT", symbol):
                raise ValueError("Futures override belongs to another instrument or contract type")

    def profile(self, version):
        if version not in {"v1062", "v200"}:
            raise ValueError("Unknown GUI profile version")
        return self.instrument.lower() + "-" + version

    def check_profile(self, profile):
        if profile not in {self.profile("v1062"), self.profile("v200")}:
            raise ValueError("Profile does not belong to this core")
        return profile
