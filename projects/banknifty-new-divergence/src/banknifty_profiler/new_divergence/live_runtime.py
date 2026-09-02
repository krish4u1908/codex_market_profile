"""Background coordinator for the live collector and calculation authority."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import threading
import time

from .configuration import load_config
from .live_authority import LiveAuthority
from .live_collector import LiveCollectorTail


class LiveRuntime:
    def __init__(
        self,
        data_root: Path,
        state_root: Path,
        session: date,
        *,
        config_path: Path | None = None,
        futures_symbol: str | None = None,
        reorder_seconds: float = 3.0,
        poll_seconds: float = 0.25,
    ) -> None:
        if reorder_seconds < 0 or poll_seconds <= 0:
            raise ValueError("live timing intervals must be positive")
        self.authority = LiveAuthority(state_root, session, load_config(config_path))
        self.data_root = Path(data_root)
        self.session = session
        self.futures_symbol = futures_symbol
        self.reorder_seconds = float(reorder_seconds)
        self.poll_seconds = float(poll_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.failure: str | None = None

    def start(self) -> None:
        recovery = self.authority.recover()
        tail = LiveCollectorTail(
            self.data_root,
            self.session,
            offsets=self.authority.source_offsets,
            futures_symbol=self.futures_symbol,
        )

        def run() -> None:
            try:
                while not self._stop.is_set():
                    events, offsets = tail.poll()
                    self.authority.stage(events, offsets)
                    cutoff = datetime.now(UTC) - timedelta(seconds=self.reorder_seconds)
                    self.authority.commit_ready(cutoff)
                    self._stop.wait(self.poll_seconds)
            except Exception as error:  # boundary must fail closed and stay observable
                self.failure = f"{type(error).__name__}: {error}"
                self.authority.set_status("LIVE_RECOVERY_REQUIRED")

        self._thread = threading.Thread(target=run, name="new-divergence-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.poll_seconds * 4))

