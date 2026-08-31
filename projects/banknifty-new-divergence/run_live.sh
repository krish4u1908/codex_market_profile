#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 --data-root PATH --state-root PATH --browser-root PATH [--host HOST] [--port PORT] [--session YYYY-MM-DD] [--codex-host LOOPBACK] [--codex-port PORT] [--enable-commentary]"; }
data_root=""; state_root=""; browser_root=""; host="127.0.0.1"; port="8793"; session=""
codex_host="127.0.0.1"; codex_port="4500"; enable_commentary="false"
while (($#)); do case "$1" in
  --data-root) data_root="$2"; shift 2;; --state-root) state_root="$2"; shift 2;;
  --browser-root) browser_root="$2"; shift 2;; --host) host="$2"; shift 2;;
  --port) port="$2"; shift 2;; --session) session="$2"; shift 2;;
  --codex-host) codex_host="$2"; shift 2;; --codex-port) codex_port="$2"; shift 2;;
  --enable-commentary) enable_commentary="true"; shift;;
  -h|--help) usage; exit 0;; *) echo "Unknown argument: $1" >&2; usage >&2; exit 2;;
esac; done
[[ -n "$data_root" && -n "$state_root" && -n "$browser_root" ]] || { usage >&2; exit 2; }
[[ -n "$session" ]] || session="$(TZ=Asia/Kolkata date +%F)"
commentary_args=()
[[ "$enable_commentary" == "true" ]] && commentary_args+=(--enable-commentary --commentary-db "$state_root/commentary.sqlite3")
exec "$(dirname "$0")/.venv/bin/banknifty-new-divergence" serve-live \
  --data-root "$data_root" --state-root "$state_root" --directory "$browser_root" \
  --session "$session" --host "$host" --port "$port" \
  --codex-host "$codex_host" --codex-port "$codex_port" "${commentary_args[@]}" --acknowledge-research-only
