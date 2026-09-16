#!/usr/bin/env bash
set -euo pipefail
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8920}"
exec python3 server.py --host "$HOST" --port "$PORT"
