#!/usr/bin/env bash
set -euo pipefail

fail() { echo "error: $*" >&2; exit 2; }
usage() {
  cat <<'EOF'
Usage: sudo ./install_codex_worker.sh --user USER --codex-bin PATH [options]

Options:
  --codex-home PATH  Existing Codex configuration/authentication home
  --work-root PATH   Empty diagnostic worker directory
  --host ADDRESS     Literal loopback address (default: 127.0.0.1)
  --port PORT        App-server port (default: 4500)
  --enable           Enable and start after installation
EOF
}

codex_user=""; codex_bin=""; codex_home=""; work_root=""
codex_host="127.0.0.1"; codex_port="4500"; enable="false"
while (($#)); do
  case "$1" in
    --user) codex_user="$2"; shift 2;;
    --codex-bin) codex_bin="$2"; shift 2;;
    --codex-home) codex_home="$2"; shift 2;;
    --work-root) work_root="$2"; shift 2;;
    --host) codex_host="$2"; shift 2;;
    --port) codex_port="$2"; shift 2;;
    --enable) enable="true"; shift;;
    -h|--help) usage; exit 0;;
    *) fail "unknown argument: $1";;
  esac
done

[[ $EUID -eq 0 ]] || fail "run this installer with sudo"
[[ -n "$codex_user" && -n "$codex_bin" ]] || { usage >&2; exit 2; }
[[ "$codex_host" == "127.0.0.1" || "$codex_host" == "::1" ]] \
  || fail "Codex app-server must use a literal loopback address"
[[ "$codex_port" =~ ^[0-9]+$ ]] && ((codex_port >= 1 && codex_port <= 65535)) \
  || fail "invalid Codex app-server port"
id "$codex_user" >/dev/null 2>&1 || fail "unknown user: $codex_user"
[[ "$codex_bin" = /* && -x "$codex_bin" ]] || fail "--codex-bin must be an absolute executable path"

codex_group="$(id -gn "$codex_user")"
codex_user_home="$(getent passwd "$codex_user" | cut -d: -f6)"
[[ -n "$codex_user_home" && "$codex_user_home" = /* ]] || fail "cannot resolve user home"
[[ -n "$codex_home" ]] || codex_home="$codex_user_home/.codex"
[[ -n "$work_root" ]] || work_root="$codex_user_home/banknifty-codex-worker"
[[ "$codex_home" = /* && "$work_root" = /* ]] || fail "Codex paths must be absolute"

if [[ ! -d "$codex_home" ]]; then
  install -d -o "$codex_user" -g "$codex_group" -m 0700 "$codex_home"
fi
[[ "$(stat -c %U "$codex_home")" == "$codex_user" ]] \
  || fail "Codex home must be owned by $codex_user"
install -d -o "$codex_user" -g "$codex_group" -m 0700 "$work_root"
runuser -u "$codex_user" -- "$codex_bin" --version >/dev/null \
  || fail "Codex executable failed for $codex_user"

release_root="$(cd "$(dirname "$0")" && pwd)"
template="$release_root/systemd/banknifty-new-divergence-codex.service.in"
unit="/etc/systemd/system/banknifty-new-divergence-codex.service"
escape_sed() { printf '%s' "$1" | sed 's/[&|]/\\&/g'; }
sed \
  -e "s|@@CODEX_USER@@|$(escape_sed "$codex_user")|g" \
  -e "s|@@CODEX_GROUP@@|$(escape_sed "$codex_group")|g" \
  -e "s|@@CODEX_BIN@@|$(escape_sed "$codex_bin")|g" \
  -e "s|@@CODEX_HOME@@|$(escape_sed "$codex_home")|g" \
  -e "s|@@WORK_ROOT@@|$(escape_sed "$work_root")|g" \
  -e "s|@@CODEX_HOST@@|$(escape_sed "$codex_host")|g" \
  -e "s|@@CODEX_PORT@@|$(escape_sed "$codex_port")|g" \
  "$template" > "$unit"
chmod 0644 "$unit"
systemd-analyze verify "$unit"
systemctl daemon-reload
if [[ "$enable" == "true" ]]; then
  systemctl enable --now banknifty-new-divergence-codex.service
else
  echo "Installed but not started. Start explicitly with:"
  echo "  sudo systemctl start banknifty-new-divergence-codex.service"
fi
