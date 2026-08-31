#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
service_name="banknifty-new-divergence-samples.service"
timer_name="banknifty-new-divergence-samples.timer"
service_user="${SUDO_USER:-}"
service_group=""
collector_root="${COLLECTOR_ROOT:-/opt/banknifty-collector}"
data_root="${COLLECTOR_DATA_ROOT:-}"
output_root="${DIVERGENCE_RUN_ROOT:-}"
browser_root="${DIVERGENCE_BROWSER_ROOT:-}"
context_state_root="${CONTEXT_STATE_ROOT:-}"
enable_oi_vpoc=1
enable_volume_profile=1
enable_timer=0

usage() {
  cat <<'EOF'
Usage:
  sudo ./install_sample_generator.sh [options]

Options:
  --user USER          Service account; defaults to the sudo caller
  --group GROUP        Service group; defaults to USER's primary group
  --collector-root P   Collector install root (default: /opt/banknifty-collector)
  --data-root PATH     Collector data-prod-v4 root
  --output-root PATH   Direct session root (default: USER_HOME/divergence/sessions)
  --browser-root PATH  V1.0.22 GUI build root
  --context-state-root PATH
                       Immutable nightly inventory context root
  --disable-oi-vpoc   Rebuild GUI without OI-VPOC controls
  --disable-volume-profile
                       Rebuild GUI without volume VPOC/VAH/VAL controls
  --enable             Enable the daily 15:40 IST timer after installation
  -h, --help           Show this help

The installer adds a versioned generator entry point under the collector's
app/ directory and a runner under bin/. It does not modify collector source,
configuration, subscriptions, or running services. The safe default installs
the timer without enabling it.
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
    --collector-root) [[ $# -ge 2 ]] || fail "--collector-root requires a value"; collector_root="$2"; shift 2 ;;
    --data-root) [[ $# -ge 2 ]] || fail "--data-root requires a value"; data_root="$2"; shift 2 ;;
    --output-root) [[ $# -ge 2 ]] || fail "--output-root requires a value"; output_root="$2"; shift 2 ;;
    --browser-root) [[ $# -ge 2 ]] || fail "--browser-root requires a value"; browser_root="$2"; shift 2 ;;
    --context-state-root) [[ $# -ge 2 ]] || fail "--context-state-root requires a value"; context_state_root="$2"; shift 2 ;;
    --disable-oi-vpoc) enable_oi_vpoc=0; shift ;;
    --disable-volume-profile) enable_volume_profile=0; shift ;;
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

if [[ -z "${service_group}" ]]; then
  service_group="$(id -gn "${service_user}")"
fi
[[ "${service_group}" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "invalid service group: ${service_group}"
getent group "${service_group}" >/dev/null || fail "unknown service group: ${service_group}"

service_home="$(getent passwd "${service_user}" | cut -d: -f6)"
[[ "${service_home}" == /* ]] || fail "service account has no absolute home directory"
[[ -n "${data_root}" ]] || data_root="${collector_root}/data-prod-v4"
[[ -n "${output_root}" ]] || output_root="${service_home}/divergence/sessions"
[[ -n "${browser_root}" ]] || browser_root="${service_home}/divergence/new-divergence-gui-v1.0.22"
[[ -n "${context_state_root}" ]] || context_state_root="${service_home}/divergence/new-divergence-context-v1.0.12"

for safe_path in "${project_dir}" "${collector_root}" "${data_root}" "${output_root}" "${browser_root}" "${context_state_root}"; do
  [[ "${safe_path}" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "paths must be absolute and contain only letters, digits, '.', '_', '-', and '/': ${safe_path}"
done
for write_path in "${output_root}" "${browser_root}" "${context_state_root}"; do
  [[ "${write_path}" != "/" ]] || fail "writable roots must not be the filesystem root"
  [[ "${write_path}" != "${data_root}" && "${write_path}" != "${data_root}/"* ]] \
    || fail "writable roots must not be inside --data-root"
done
[[
  "${browser_root}" != "${output_root}"
  && "${browser_root}" != "${output_root}/"*
  && "${output_root}" != "${browser_root}/"*
  && "${context_state_root}" != "${output_root}"
  && "${context_state_root}" != "${output_root}/"*
  && "${output_root}" != "${context_state_root}/"*
  && "${context_state_root}" != "${browser_root}"
  && "${context_state_root}" != "${browser_root}/"*
  && "${browser_root}" != "${context_state_root}/"*
]] || fail "output, browser, and context roots must be separate non-nested directories"

sample_source="${project_dir}/scripts/generate_banknifty_samples_v1_0_14.py"
runner_template="${project_dir}/scripts/run_banknifty_samples.sh.in"
service_template="${project_dir}/systemd/${service_name}.in"
timer_template="${project_dir}/systemd/${timer_name}.in"
sample_python="${project_dir}/.venv/bin/python"
divergence_cli="${project_dir}/.venv/bin/banknifty-new-divergence"
sample_generator="${collector_root}/app/generate_banknifty_samples_v1_0_14.py"
sample_runner="${collector_root}/bin/generate_banknifty_samples_v1_0_14"

[[ -x "${sample_python}" && -x "${divergence_cli}" ]] \
  || fail "installed V1.0.22 environment not found; run ./install.sh without sudo first"
[[ -f "${sample_source}" && -f "${runner_template}" ]] || fail "sample generator assets are missing"
[[ -f "${service_template}" && -f "${timer_template}" ]] || fail "sample systemd templates are missing"
[[ -d "${collector_root}" ]] || fail "collector root does not exist: ${collector_root}"
[[ -d "${data_root}/minute" ]] || fail "collector data root must contain minute/: ${data_root}"

command -v systemctl >/dev/null 2>&1 || fail "systemctl is required"
command -v runuser >/dev/null 2>&1 || fail "runuser is required"
runuser -u "${service_user}" -- test -r "${data_root}/minute" \
  || fail "${service_user} cannot read ${data_root}/minute"
runuser -u "${service_user}" -- test -x "${data_root}/minute" \
  || fail "${service_user} cannot traverse ${data_root}/minute"
runuser -u "${service_user}" -- "${divergence_cli}" generate-samples --help >/dev/null \
  || fail "${service_user} cannot execute the V1.0.22 environment"

[[ -d "${collector_root}/app" ]] || install -d -o root -g root -m 0755 "${collector_root}/app"
[[ -d "${collector_root}/bin" ]] || install -d -o root -g root -m 0755 "${collector_root}/bin"
install -o root -g root -m 0755 "${sample_source}" "${sample_generator}"
runuser -u "${service_user}" -- test -x "${sample_generator}" \
  || fail "${service_user} cannot execute ${sample_generator}"

install -d -o "${service_user}" -g "${service_group}" -m 0750 \
  "${output_root}" "${browser_root}" "${context_state_root}"
runuser -u "${service_user}" -- test -w "${output_root}" \
  || fail "${service_user} cannot write ${output_root}"
runuser -u "${service_user}" -- test -w "${browser_root}" \
  || fail "${service_user} cannot write ${browser_root}"

temporary_runner="$(mktemp)"
temporary_service="$(mktemp)"
temporary_timer="$(mktemp)"
cleanup() {
  rm -f "${temporary_runner}" "${temporary_service}" "${temporary_timer}"
}
trap cleanup EXIT

sed \
  -e "s|@SAMPLE_PYTHON@|${sample_python}|g" \
  -e "s|@SAMPLE_GENERATOR@|${sample_generator}|g" \
  -e "s|@DIVERGENCE_CLI@|${divergence_cli}|g" \
  -e "s|@DATA_ROOT@|${data_root}|g" \
  -e "s|@OUTPUT_ROOT@|${output_root}|g" \
  -e "s|@BROWSER_ROOT@|${browser_root}|g" \
  -e "s|@CONTEXT_STATE_ROOT@|${context_state_root}|g" \
  -e "s|@ENABLE_OI_VPOC@|${enable_oi_vpoc}|g" \
  -e "s|@ENABLE_VOLUME_PROFILE@|${enable_volume_profile}|g" \
  "${runner_template}" >"${temporary_runner}"
install -o root -g root -m 0755 "${temporary_runner}" "${sample_runner}"
runuser -u "${service_user}" -- test -x "${sample_runner}" \
  || fail "${service_user} cannot execute ${sample_runner}"

sed \
  -e "s|@SERVICE_USER@|${service_user}|g" \
  -e "s|@SERVICE_GROUP@|${service_group}|g" \
  -e "s|@PROJECT_DIR@|${project_dir}|g" \
  -e "s|@COLLECTOR_ROOT@|${collector_root}|g" \
  -e "s|@DATA_ROOT@|${data_root}|g" \
  -e "s|@OUTPUT_ROOT@|${output_root}|g" \
  -e "s|@BROWSER_ROOT@|${browser_root}|g" \
  -e "s|@CONTEXT_STATE_ROOT@|${context_state_root}|g" \
  -e "s|@SAMPLE_GENERATOR@|${sample_generator}|g" \
  -e "s|@SAMPLE_RUNNER@|${sample_runner}|g" \
  "${service_template}" >"${temporary_service}"
sed -e "s|@PROJECT_DIR@|${project_dir}|g" \
  "${timer_template}" >"${temporary_timer}"

service_file="/etc/systemd/system/${service_name}"
timer_file="/etc/systemd/system/${timer_name}"
install -o root -g root -m 0644 "${temporary_service}" "${service_file}"
install -o root -g root -m 0644 "${temporary_timer}" "${timer_file}"
systemctl daemon-reload

if ((enable_timer)); then
  systemctl enable --now "${timer_name}"
  printf '\nSample generator installed; daily timer enabled.\n'
else
  printf '\nSample generator installed; timer is not enabled.\n'
fi
printf 'Generator: %s\n' "${sample_generator}"
printf 'Runner: %s\n' "${sample_runner}"
printf 'Source (read-only): %s/minute\n' "${data_root}"
printf 'Session root: %s/YYYY-MM-DD\n' "${output_root}"
printf 'Browser root: %s\n' "${browser_root}"
printf 'Inventory context: %s\n' "${context_state_root}"
printf 'Schedule: daily at 15:40 Asia/Kolkata (covers special trading Saturdays)\n'
printf 'First backfill: sudo systemctl start %s\n' "${service_name}"
