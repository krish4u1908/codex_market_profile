#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
service_name="banknifty-new-divergence-nightly.service"
timer_name="banknifty-new-divergence-nightly.timer"
service_user="${SUDO_USER:-}"
service_group=""
data_root="${COLLECTOR_DATA_ROOT:-/opt/banknifty-collector/data-prod-v4}"
state_root="${CONTEXT_STATE_ROOT:-}"
enable_timer=0

usage() {
  cat <<'EOF'
Usage:
  sudo ./install_nightly_context.sh [options]

Options:
  --user USER          Service account; defaults to the sudo caller
  --group GROUP        Service group; defaults to USER's primary group
  --data-root PATH     Collector root (default: /opt/banknifty-collector/data-prod-v4)
  --state-root PATH    SQLite and immutable snapshot root
  --enable             Enable and start the timer after installing its files
  -h, --help           Show this help

The safe default installs the service and timer files but does not enable or
start either unit. The collector root is mounted read-only in the service.
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
    --data-root) [[ $# -ge 2 ]] || fail "--data-root requires a value"; data_root="$2"; shift 2 ;;
    --state-root) [[ $# -ge 2 ]] || fail "--state-root requires a value"; state_root="$2"; shift 2 ;;
    --enable) enable_timer=1; shift ;;
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
[[ -n "${state_root}" ]] || state_root="${service_home}/divergence/new-divergence-context-v1.0.12"

if [[ -z "${service_group}" ]]; then
  service_group="$(id -gn "${service_user}")"
fi
[[ "${service_group}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "invalid service group: ${service_group}"
getent group "${service_group}" >/dev/null || fail "unknown service group: ${service_group}"

for safe_path in "${project_dir}" "${data_root}" "${state_root}"; do
  [[ "${safe_path}" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "paths must be absolute and contain only letters, digits, '.', '_', '-', and '/': ${safe_path}"
done
[[ "${state_root}" != "/" ]] || fail "--state-root must not be the filesystem root"
[[ "${state_root}" != "${data_root}" && "${state_root}" != "${data_root}/"* ]] \
  || fail "--state-root must not be inside --data-root"

cli="${project_dir}/.venv/bin/banknifty-new-divergence"
config="${project_dir}/configs/nightly_context_v2.json"
service_template="${project_dir}/systemd/${service_name}.in"
timer_template="${project_dir}/systemd/${timer_name}.in"
[[ -x "${cli}" ]] || fail "installed CLI not found: ${cli}; run ./install.sh without sudo first"
[[ -f "${config}" ]] || fail "nightly configuration not found: ${config}"
[[ -f "${service_template}" ]] || fail "service template not found: ${service_template}"
[[ -f "${timer_template}" ]] || fail "timer template not found: ${timer_template}"
[[ -d "${data_root}/raw" && -d "${data_root}/oi" ]] \
  || fail "collector root must contain raw/ and oi/: ${data_root}"

command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
command -v runuser >/dev/null 2>&1 || fail "runuser is required"
runuser -u "${service_user}" -- test -r "${data_root}/raw" \
  || fail "${service_user} cannot read ${data_root}/raw"
runuser -u "${service_user}" -- test -x "${data_root}/raw" \
  || fail "${service_user} cannot traverse ${data_root}/raw"
runuser -u "${service_user}" -- test -r "${data_root}/oi" \
  || fail "${service_user} cannot read ${data_root}/oi"
runuser -u "${service_user}" -- test -x "${data_root}/oi" \
  || fail "${service_user} cannot traverse ${data_root}/oi"
runuser -u "${service_user}" -- "${cli}" --help >/dev/null \
  || fail "${service_user} cannot execute the installed CLI"

install -d -o "${service_user}" -g "${service_group}" -m 0750 "${state_root}"
runuser -u "${service_user}" -- test -w "${state_root}" \
  || fail "${service_user} cannot write ${state_root}; check parent-directory permissions"
runuser -u "${service_user}" -- test -x "${state_root}" \
  || fail "${service_user} cannot traverse ${state_root}; check parent-directory permissions"

environment_file="/etc/banknifty-new-divergence-nightly.env"
service_file="/etc/systemd/system/${service_name}"
timer_file="/etc/systemd/system/${timer_name}"
temporary_environment="$(mktemp)"
temporary_service="$(mktemp)"
temporary_timer="$(mktemp)"
cleanup() {
  rm -f "${temporary_environment}" "${temporary_service}" "${temporary_timer}"
}
trap cleanup EXIT

{
  printf 'DIVERGENCE_CLI=%s\n' "${cli}"
  printf 'COLLECTOR_DATA_ROOT=%s\n' "${data_root}"
  printf 'CONTEXT_STATE_ROOT=%s\n' "${state_root}"
  printf 'CONTEXT_CONFIG=%s\n' "${config}"
} >"${temporary_environment}"

sed \
  -e "s|@SERVICE_USER@|${service_user}|g" \
  -e "s|@SERVICE_GROUP@|${service_group}|g" \
  -e "s|@PROJECT_DIR@|${project_dir}|g" \
  -e "s|@DATA_ROOT@|${data_root}|g" \
  -e "s|@STATE_ROOT@|${state_root}|g" \
  "${service_template}" >"${temporary_service}"
sed -e "s|@PROJECT_DIR@|${project_dir}|g" \
  "${timer_template}" >"${temporary_timer}"

install -o root -g root -m 0644 "${temporary_environment}" "${environment_file}"
install -o root -g root -m 0644 "${temporary_service}" "${service_file}"
install -o root -g root -m 0644 "${temporary_timer}" "${timer_file}"
systemctl daemon-reload

if ((enable_timer)); then
  systemctl enable --now "${timer_name}"
  printf '\nNightly timer installed and enabled.\n'
else
  printf '\nNightly service and timer files installed; neither unit was enabled or started.\n'
fi
printf 'Timer: %s (00:15 Asia/Kolkata, with up to 120 seconds jitter)\n' "${timer_name}"
printf 'Collector root (read-only): %s\n' "${data_root}"
printf 'Context state: %s\n' "${state_root}"
printf 'Manual first run: sudo systemctl start %s\n' "${service_name}"
