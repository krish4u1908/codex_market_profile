#!/usr/bin/env python3
"""Collector-side entry point retained for the V1.0.14 release."""

from __future__ import annotations

import sys

from banknifty_profiler.new_divergence.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["generate-samples", *sys.argv[1:]]))
