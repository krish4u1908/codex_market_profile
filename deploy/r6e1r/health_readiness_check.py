#!/usr/bin/env python3
"""Dependency-free R6E1R health/readiness probe with safe stale handling."""
from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


CLASSIFICATION = "LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL"
BENIGN_NOT_READY_REASONS = frozenset({
    "STALE_DATA",
    "REQUIRED_MARKET_INPUTS_UNAVAILABLE",
    "REQUIRED_MARKET_INPUTS_UNAVAILABLE_OR_STALE",
})
BENIGN_NOT_READY_STATES = frozenset({
    "STALE_PARTIAL", "NO_VALID_MARKET_DATA", "FIXED_CONTEXT_ONLY",
})


def normalized_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be a credential-free HTTP origin")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("base URL contains an invalid port") from error
    if port is None or not 1 <= port <= 65535:
        raise ValueError("base URL must contain an explicit TCP port")
    return value.rstrip("/")


def base_url_for_log(value: str) -> str:
    """Return only a validated credential-free origin for probe diagnostics."""
    try:
        return normalized_base_url(value)
    except ValueError:
        return "REDACTED_INVALID_ORIGIN"


def fetch_json(url: str, timeout: float) -> tuple[int, dict[str, Any]]:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read(1024 * 1024)
    except HTTPError as error:
        status = error.code
        body = error.read(1024 * 1024)
    value = json.loads(body.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("endpoint did not return a JSON object")
    return status, value


def probe(base_url: str, timeout: float, health_only: bool = False) -> dict[str, Any]:
    base = normalized_base_url(base_url)
    health_status, health = fetch_json(f"{base}/api/health", timeout)
    if health_status != 200 or health.get("alive") is not True:
        raise RuntimeError(f"health failed with HTTP {health_status}")
    if health.get("classification") != CLASSIFICATION:
        raise RuntimeError("health classification contract mismatch")
    result: dict[str, Any] = {
        "base_url": base,
        "health_http_status": health_status,
        "alive": True,
        "classification": CLASSIFICATION,
    }
    if health_only:
        return result
    readiness_status, readiness = fetch_json(f"{base}/api/readiness", timeout)
    ready = readiness.get("ready")
    if ready is True and readiness_status != 200:
        raise RuntimeError("ready response must use HTTP 200")
    if ready is False and readiness_status != 503:
        raise RuntimeError("not-ready response must use HTTP 503")
    if not isinstance(ready, bool):
        raise RuntimeError("readiness response is missing boolean ready")
    if readiness.get("checkpoint_valid") is not True:
        raise RuntimeError("readiness checkpoint integrity is not verified")
    if readiness.get("future_joins") != 0:
        raise RuntimeError("readiness reports future joins or omits the metric")
    if readiness.get("synchronization_tolerance_violations") != 0:
        raise RuntimeError(
            "readiness reports synchronization violations or omits the metric"
        )
    if readiness.get("manifest_verified") is not True:
        raise RuntimeError("runtime source manifest is not verified")
    reasons = readiness.get("reasons", [])
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) for reason in reasons
    ):
        raise RuntimeError("readiness reasons must be a string list")
    if ready and reasons:
        raise RuntimeError("ready response must not contain failure reasons")
    if not ready and (
        not reasons
        or not set(reasons).issubset(BENIGN_NOT_READY_REASONS)
        or readiness.get("availability_state") not in BENIGN_NOT_READY_STATES
    ):
        raise RuntimeError("not-ready response contains a non-benign blocker")
    result.update({
        "readiness_http_status": readiness_status,
        "ready": ready,
        "readiness_reasons": reasons,
        "availability_state": readiness.get("availability_state"),
        "checkpoint_valid": True,
        "future_joins": 0,
        "synchronization_tolerance_violations": 0,
        "manifest_verified": True,
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--health-only", action="store_true")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.attempts < 1 or not 0 <= args.delay_seconds <= 60 or not 0 < args.timeout_seconds <= 60:
        parser.error("invalid retry or timeout bounds")
    if args.health_only and args.require_ready:
        parser.error("--health-only and --require-ready are mutually exclusive")

    last_error = "probe was not attempted"
    for attempt in range(1, args.attempts + 1):
        try:
            result = probe(args.base_url, args.timeout_seconds, args.health_only)
            result["attempt"] = attempt
            result["status"] = (
                "PASS"
                if args.health_only or result.get("ready") is True or not args.require_ready
                else "NOT_READY"
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0 if result["status"] == "PASS" else 1
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            last_error = f"{type(error).__name__}:{error}"
            if attempt < args.attempts:
                time.sleep(args.delay_seconds)
    print(json.dumps({
        "base_url": base_url_for_log(args.base_url),
        "attempts": args.attempts,
        "error": last_error,
        "status": "FAIL",
    }, sort_keys=True, separators=(",", ":")))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
