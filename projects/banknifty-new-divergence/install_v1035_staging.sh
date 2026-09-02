#!/usr/bin/env bash
set -euo pipefail

fail() { echo "error: $*" >&2; exit 2; }
usage() {
  echo "Usage: sudo $0 --user USER --data-root PATH --state-root PATH --browser-root PATH [--host HOST] [--port PORT] [--codex-host LOOPBACK] [--codex-port PORT] [--enable-commentary] [--enable]"
}

service_user=""; data_root=""; state_root=""; browser_root=""
host="127.0.0.1"; port="8797"; codex_host="127.0.0.1"; codex_port="4500"
enable_commentary="false"; enable="false"
while (($#)); do
  case "$1" in
    --user) service_user="$2"; shift 2 ;;
    --data-root) data_root="$2"; shift 2 ;;
    --state-root) state_root="$2"; shift 2 ;;
    --browser-root) browser_root="$2"; shift 2 ;;
    --host) host="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --codex-host) codex_host="$2"; shift 2 ;;
    --codex-port) codex_port="$2"; shift 2 ;;
    --enable-commentary) enable_commentary="true"; shift ;;
    --enable) enable="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || fail "run this installer with sudo"
[[ -n "$service_user" && -n "$data_root" && -n "$state_root" && -n "$browser_root" ]] || { usage >&2; exit 2; }
[[ "$codex_host" == "127.0.0.1" || "$codex_host" == "::1" ]] || fail "Codex worker must use loopback"
[[ "$port" =~ ^[0-9]+$ ]] && ((port >= 1 && port <= 65535)) || fail "invalid staging port"
[[ "$codex_port" =~ ^[0-9]+$ ]] && ((codex_port >= 1 && codex_port <= 65535)) || fail "invalid Codex port"
id "$service_user" >/dev/null 2>&1 || fail "unknown user: $service_user"

service_group="$(id -gn "$service_user")"
release_root="$(cd "$(dirname "$0")" && pwd)"
[[ -x "$release_root/.venv/bin/banknifty-new-divergence" ]] || fail "run ./install.sh as $service_user first"
[[ -d "$data_root" ]] || fail "collector data root not found: $data_root"
[[ -f "$browser_root/build_manifest.json" ]] || fail "run build-live-browser first"
install -d -o "$service_user" -g "$service_group" -m 0750 "$state_root"

escape_sed() { printf '%s' "$1" | sed 's/[&|]/\\&/g'; }
commentary_args=""
if [[ "$enable_commentary" == "true" ]]; then commentary_args=" --enable-commentary"; fi
template="$release_root/systemd/banknifty-new-divergence-v1035-staging.service.in"
unit="/etc/systemd/system/banknifty-new-divergence-v1035-staging.service"
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
sed \
  -e "s|@@SERVICE_USER@@|$(escape_sed "$service_user")|g" \
  -e "s|@@SERVICE_GROUP@@|$(escape_sed "$service_group")|g" \
  -e "s|@@RELEASE_ROOT@@|$(escape_sed "$release_root")|g" \
  -e "s|@@DATA_ROOT@@|$(escape_sed "$data_root")|g" \
  -e "s|@@STATE_ROOT@@|$(escape_sed "$state_root")|g" \
  -e "s|@@BROWSER_ROOT@@|$(escape_sed "$browser_root")|g" \
  -e "s|@@HOST@@|$(escape_sed "$host")|g" \
  -e "s|@@PORT@@|$(escape_sed "$port")|g" \
  -e "s|@@CODEX_HOST@@|$(escape_sed "$codex_host")|g" \
  -e "s|@@CODEX_PORT@@|$(escape_sed "$codex_port")|g" \
  -e "s|@@COMMENTARY_ARGS@@|$(escape_sed "$commentary_args")|g" \
  "$template" > "$temporary"
install -m 0644 "$temporary" "$unit"
systemd-analyze verify "$unit"
systemctl daemon-reload
if [[ "$enable" == "true" ]]; then
  systemctl enable --now banknifty-new-divergence-v1035-staging.service
else
  echo "Installed but not started. Start explicitly with:"
  echo "  sudo systemctl start banknifty-new-divergence-v1035-staging.service"
fi
