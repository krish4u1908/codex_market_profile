"""Fail-closed status boundary for the optional local Codex app-server worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import ipaddress
import socket
import time


@dataclass(frozen=True)
class CodexWorkerProbe:
    """Probe a loopback-only Codex worker without sending prompts or market data."""

    host: str = "127.0.0.1"
    port: int = 4500
    timeout_seconds: float = 0.2

    def __post_init__(self) -> None:
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as error:
            raise ValueError("Codex worker host must be a literal loopback address") from error
        if not address.is_loopback:
            raise ValueError("Codex worker must listen on a loopback address")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("Codex worker port must be between 1 and 65535")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 2:
            raise ValueError("Codex worker probe timeout must be greater than 0 and at most 2 seconds")

    def status(self) -> dict[str, object]:
        started = time.monotonic()
        try:
            with socket.create_connection(
                (self.host, int(self.port)), timeout=float(self.timeout_seconds)
            ):
                state = "REACHABLE_UNVERIFIED"
                detail = "loopback Codex app-server socket is reachable"
        except OSError:
            state = "OFFLINE"
            detail = "loopback Codex app-server socket is not reachable"
        return {
            "schema": "NEW_DIVERGENCE_CODEX_WORKER_STATUS_V1",
            "state": state,
            "detail": detail,
            "endpoint": f"{self.host}:{self.port}",
            "protocol": "codex-app-server-websocket",
            "checked_at": datetime.now(UTC).isoformat(),
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "prompting_enabled": False,
            "production_data_access": False,
        }
