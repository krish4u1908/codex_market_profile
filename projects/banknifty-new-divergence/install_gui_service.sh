#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
service_name="banknifty-new-divergence-gui.service"
service_user="${SUDO_USER:-}"
service_group=""
run_root="${DIVERGENCE_RUN_ROOT:-}"
browser_root="${DIVERGENCE_BROWSER_ROOT:-}"
context_state_root="${CONTEXT_STATE_ROOT:-}"
enable_oi_vpoc=1
enable_volume_profile=1
gui_host="127.0.0.1"
gui_port="8793"
codex_host="127.0.0.1"
codex_port="4500"
codex_cwd="/home/codexuser/banknifty-codex-worker"
codex_token_file="/etc/banknifty-new-divergence-codex-gui.token"
start_service=1

usage() {
  cat <<'EOF'
Usage:
  sudo ./install_gui_service.sh [options]

Options:
  --user USER            Service account; defaults to the sudo caller
  --group GROUP          Service group; defaults to USER's primary group
  --run-root PATH        Verified replay-run root
  --browser-root PATH    Generated GUI root
  --context-state-root P Immutable nightly inventory context root
  --disable-oi-vpoc     Build GUI without OI-VPOC controls
  --disable-volume-profile
                        Build GUI without volume VPOC/VAH/VAL controls
  --host ADDRESS         127.0.0.1 (default) or 0.0.0.0
  --port PORT            Listening port (default: 8793)
  --codex-host ADDRESS   Loopback Codex app-server address (default: 127.0.0.1)
  --codex-port PORT      Loopback Codex app-server port (default: 4500)
  --codex-cwd PATH       Restricted worker directory
  --codex-token-file P  Internal server enable-token file; never expose to browsers
  --no-start             Install files without enabling or starting service
  -h, --help             Show this help

The GUI is read-only. Binding 0.0.0.0 exposes it without application-level
authentication; restrict access with a firewall or authenticated reverse proxy.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --user) [[ $# -ge 2 ]] || fail "--user requires a value"; service_user="$2"; shift 2 ;;
    --group) [[ $# -ge 2 ]] || fail "--group requires a value"; service_group="$2"; shift 2 ;;
    --run-root) [[ $# -ge 2 ]] || fail "--run-root requires a value"; run_root="$2"; shift 2 ;;
    --browser-root) [[ $# -ge 2 ]] || fail "--browser-root requires a value"; browser_root="$2"; shift 2 ;;
    --context-state-root) [[ $# -ge 2 ]] || fail "--context-state-root requires a value"; context_state_root="$2"; shift 2 ;;
    --disable-oi-vpoc) enable_oi_vpoc=0; shift ;;
    --disable-volume-profile) enable_volume_profile=0; shift ;;
    --host) [[ $# -ge 2 ]] || fail "--host requires a value"; gui_host="$2"; shift 2 ;;
    --port) [[ $# -ge 2 ]] || fail "--port requires a value"; gui_port="$2"; shift 2 ;;
    --codex-host) [[ $# -ge 2 ]] || fail "--codex-host requires a value"; codex_host="$2"; shift 2 ;;
    --codex-port) [[ $# -ge 2 ]] || fail "--codex-port requires a value"; codex_port="$2"; shift 2 ;;
    --codex-cwd) [[ $# -ge 2 ]] || fail "--codex-cwd requires a value"; codex_cwd="$2"; shift 2 ;;
    --codex-token-file) [[ $# -ge 2 ]] || fail "--codex-token-file requires a value"; codex_token_file="$2"; shift 2 ;;
    --no-start) start_service=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ ${EUID} -eq 0 ]] || fail "run this installer with sudo"
[[ -n "${service_user}" && "${service_user}" != "root" ]] \
  || fail "a non-root --user is required when there is no sudo caller"
[[ "${service_user}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "invalid service user: ${service_user}"
getent passwd "${service_user}" >/dev/null || fail "unknown service user: ${service_user}"

service_home="$(getent passwd "${service_user}" | cut -d: -f6)"
[[ "${service_home}" == /* ]] || fail "service account has no absolute home directory"
[[ -n "${run_root}" ]] || run_root="${service_home}/divergence/sessions"
[[ -n "${browser_root}" ]] || browser_root="${service_home}/divergence/new-divergence-gui-v1.0.22"
[[ -n "${context_state_root}" ]] || context_state_root="${service_home}/divergence/new-divergence-context-v1.0.12"

if [[ -z "${service_group}" ]]; then
  service_group="$(id -gn "${service_user}")"
fi
[[ "${service_group}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "invalid service group: ${service_group}"
getent group "${service_group}" >/dev/null || fail "unknown service group: ${service_group}"

[[ "${gui_host}" == "127.0.0.1" || "${gui_host}" == "0.0.0.0" ]] \
  || fail "--host must be 127.0.0.1 or 0.0.0.0"
[[ "${codex_host}" == "127.0.0.1" || "${codex_host}" == "::1" ]] \
  || fail "--codex-host must be a literal loopback address"
[[ "${gui_port}" =~ ^[0-9]+$ ]] || fail "--port must be an integer"
((gui_port >= 1024 && gui_port <= 65535)) || fail "--port must be between 1024 and 65535"
[[ "${codex_port}" =~ ^[0-9]+$ ]] || fail "--codex-port must be an integer"
((codex_port >= 1024 && codex_port <= 65535)) || fail "--codex-port must be between 1024 and 65535"

for safe_path in "${project_dir}" "${run_root}" "${browser_root}" "${context_state_root}" "${codex_cwd}" "${codex_token_file}"; do
  [[ "${safe_path}" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "paths must be absolute and contain only letters, digits, '.', '_', '-', and '/': ${safe_path}"
done
[[ "${run_root}" != "/" && "${browser_root}" != "/" && "${context_state_root}" != "/" ]] \
  || fail "run, browser, and context roots must not be the filesystem root"
[[ -d "${codex_cwd}" ]] || fail "restricted Codex worker directory not found: ${codex_cwd}"
[[
  "${browser_root}" != "${run_root}"
  && "${browser_root}" != "${run_root}/"*
  && "${run_root}" != "${browser_root}/"*
  && "${context_state_root}" != "${run_root}"
  && "${context_state_root}" != "${run_root}/"*
  && "${run_root}" != "${context_state_root}/"*
  && "${context_state_root}" != "${browser_root}"
  && "${context_state_root}" != "${browser_root}/"*
  && "${browser_root}" != "${context_state_root}/"*
]] || fail "run, browser, and context roots must be separate non-nested directories"

cli="${project_dir}/.venv/bin/banknifty-new-divergence"
unit_template="${project_dir}/systemd/banknifty-new-divergence-gui.service.in"
[[ -x "${cli}" ]] || fail "installed CLI not found: ${cli}; run ./install.sh without sudo first"
[[ -f "${unit_template}" ]] || fail "service template not found: ${unit_template}"

command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
command -v runuser >/dev/null 2>&1 || fail "runuser is required"
command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v openssl >/dev/null 2>&1 || fail "openssl is required"

install -d -o "${service_user}" -g "${service_group}" -m 0750 \
  "${run_root}" "${browser_root}" "${context_state_root}"

printf 'Initializing browser projection at %s...\n' "${browser_root}"
build_args=(
  build-browser
  --run-root "${run_root}"
  --output-root "${browser_root}"
  --context-state-root "${context_state_root}"
)
((enable_oi_vpoc == 1)) || build_args+=(--no-oi-vpoc)
((enable_volume_profile == 1)) || build_args+=(--no-volume-profile)
runuser -u "${service_user}" -- "${cli}" "${build_args[@]}" >/dev/null

[[ ! -L "${codex_token_file}" ]] || fail "Codex token file must not be a symbolic link"
if [[ ! -e "${codex_token_file}" ]]; then
  temporary_token="$(mktemp)"
  openssl rand -hex 32 >"${temporary_token}"
  install -o root -g "${service_group}" -m 0640 "${temporary_token}" "${codex_token_file}"
  rm -f "${temporary_token}"
else
  [[ -f "${codex_token_file}" ]] || fail "Codex token path is not a regular file"
  chown root:"${service_group}" "${codex_token_file}"
  chmod 0640 "${codex_token_file}"
fi
codex_token="$(tr -d '\n' <"${codex_token_file}")"
[[ "${#codex_token}" -ge 32 && "${#codex_token}" -le 256 && "${codex_token}" != *[[:space:]]* ]] \
  || fail "Codex token must contain 32 to 256 non-whitespace characters"
unset codex_token

environment_file="/etc/banknifty-new-divergence-gui.env"
unit_file="/etc/systemd/system/${service_name}"
temporary_environment="$(mktemp)"
temporary_unit="$(mktemp)"
cleanup() {
  rm -f "${temporary_environment}" "${temporary_unit}"
}
trap cleanup EXIT

{
  printf 'DIVERGENCE_CLI=%s\n' "${cli}"
  printf 'BROWSER_ROOT=%s\n' "${browser_root}"
  printf 'GUI_HOST=%s\n' "${gui_host}"
  printf 'GUI_PORT=%s\n' "${gui_port}"
  printf 'CODEX_HOST=%s\n' "${codex_host}"
  printf 'CODEX_PORT=%s\n' "${codex_port}"
  printf 'CODEX_CWD=%s\n' "${codex_cwd}"
  printf 'CODEX_TOKEN_FILE=%s\n' "${codex_token_file}"
  printf 'COMMENTARY_DB=%s\n' "${browser_root}/commentary.sqlite3"
} >"${temporary_environment}"

sed \
  -e "s|@SERVICE_USER@|${service_user}|g" \
  -e "s|@SERVICE_GROUP@|${service_group}|g" \
  -e "s|@PROJECT_DIR@|${project_dir}|g" \
  -e "s|@CODEX_TOKEN_FILE@|${codex_token_file}|g" \
  -e "s|@BROWSER_ROOT@|${browser_root}|g" \
  "${unit_template}" >"${temporary_unit}"

install -o root -g root -m 0644 "${temporary_environment}" "${environment_file}"
install -o root -g root -m 0644 "${temporary_unit}" "${unit_file}"
systemctl daemon-reload

if ((start_service)); then
  systemctl enable "${service_name}" >/dev/null
  systemctl restart "${service_name}"
  healthy=0
  for _ in {1..20}; do
    if systemctl is-active --quiet "${service_name}" \
      && curl --fail --silent --show-error --max-time 2 \
      "http://127.0.0.1:${gui_port}/healthz" >/dev/null 2>&1; then
      healthy=1
      break
    fi
    sleep 0.25
  done
  if ((healthy == 0)); then
    systemctl status "${service_name}" --no-pager || true
    fail "service did not pass its health check; inspect journalctl -u ${service_name}"
  fi
  printf '\nGUI service installed and running.\n'
else
  printf '\nGUI service files installed; service was not enabled or started.\n'
fi

printf 'Service: %s\n' "${service_name}"
printf 'Run root: %s\n' "${run_root}"
printf 'Browser root: %s\n' "${browser_root}"
printf 'Health: http://127.0.0.1:%s/healthz\n' "${gui_port}"
printf 'Codex status: http://127.0.0.1:%s/api/v1/codex/status\n' "${gui_port}"
printf 'Central commentary: enabled; internal token remains server-side at %s\n' "${codex_token_file}"
if [[ "${gui_host}" == "0.0.0.0" ]]; then
  printf 'WARNING: port %s is exposed on all interfaces without application-level authentication.\n' "${gui_port}"
fi
