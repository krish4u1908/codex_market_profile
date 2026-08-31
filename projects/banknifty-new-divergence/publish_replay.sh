#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
run_root="${DIVERGENCE_RUN_ROOT:-${HOME}/divergence/sessions}"
browser_root="${DIVERGENCE_BROWSER_ROOT:-${HOME}/divergence/new-divergence-gui-v1.0.16}"
context_state_root="${CONTEXT_STATE_ROOT:-${HOME}/divergence/new-divergence-context-v1.0.12}"
enable_oi_vpoc=1
enable_volume_profile=1
archive_path=""
session_day=""
start_time=""
end_time=""
finalize_run=0
skip_archive_hash=0

usage() {
  cat <<'EOF'
Usage:
  ./publish_replay.sh --archive PATH --session YYYY-MM-DD [options]

Required:
  --archive PATH         Read-only collector .tar.gz archive
  --session YYYY-MM-DD   Exchange session to replay

Options:
  --run-root PATH        Verified run root
  --browser-root PATH    GUI projection root
  --context-state-root P Immutable nightly inventory context root
  --disable-oi-vpoc     Build GUI without OI-VPOC controls
  --disable-volume-profile
                        Build GUI without volume VPOC/VAH/VAL controls
  --start HH:MM[:SS]     Optional IST replay start
  --end HH:MM[:SS]       Optional IST replay end
  --finalize             Explicitly close an open episode at replay end
  --skip-archive-hash    Skip archive SHA-256 calculation
  -h, --help             Show this help

The script never deletes or overwrites an existing session run.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --archive) [[ $# -ge 2 ]] || fail "--archive requires a value"; archive_path="$2"; shift 2 ;;
    --session) [[ $# -ge 2 ]] || fail "--session requires a value"; session_day="$2"; shift 2 ;;
    --run-root) [[ $# -ge 2 ]] || fail "--run-root requires a value"; run_root="$2"; shift 2 ;;
    --browser-root) [[ $# -ge 2 ]] || fail "--browser-root requires a value"; browser_root="$2"; shift 2 ;;
    --context-state-root) [[ $# -ge 2 ]] || fail "--context-state-root requires a value"; context_state_root="$2"; shift 2 ;;
    --disable-oi-vpoc) enable_oi_vpoc=0; shift ;;
    --disable-volume-profile) enable_volume_profile=0; shift ;;
    --start) [[ $# -ge 2 ]] || fail "--start requires a value"; start_time="$2"; shift 2 ;;
    --end) [[ $# -ge 2 ]] || fail "--end requires a value"; end_time="$2"; shift 2 ;;
    --finalize) finalize_run=1; shift ;;
    --skip-archive-hash) skip_archive_hash=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ ${EUID} -ne 0 ]] || fail "run this replay as the normal project owner, not with sudo"
[[ -n "${archive_path}" ]] || fail "--archive is required"
[[ -n "${session_day}" ]] || fail "--session is required"
[[ "${session_day}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || fail "--session must be YYYY-MM-DD"
[[ -f "${archive_path}" ]] || fail "archive not found: ${archive_path}"
[[ "${run_root}" == /* && "${browser_root}" == /* && "${context_state_root}" == /* ]] \
  || fail "--run-root, --browser-root, and --context-state-root must be absolute paths"
[[ "${run_root}" != "/" && "${browser_root}" != "/" && "${context_state_root}" != "/" ]] \
  || fail "run, browser, and context roots must not be the filesystem root"
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
[[ -x "${cli}" ]] || fail "installed CLI not found: ${cli}; run ./install.sh first"

mkdir -p "${run_root}" "${browser_root}" "${context_state_root}"

replay_args=(
  replay-archive
  --archive "${archive_path}"
  --session "${session_day}"
  --output-root "${run_root}"
)
[[ -z "${start_time}" ]] || replay_args+=(--start "${start_time}")
[[ -z "${end_time}" ]] || replay_args+=(--end "${end_time}")
((finalize_run == 0)) || replay_args+=(--finalize)
((skip_archive_hash == 0)) || replay_args+=(--skip-archive-hash)

printf 'Replaying session %s...\n' "${session_day}"
"${cli}" "${replay_args[@]}"

run_directory="${run_root}/${session_day}"
printf 'Verifying completed run...\n'
"${cli}" verify-run --run-directory "${run_directory}"

printf 'Publishing refreshed replay GUI...\n'
build_args=(
  build-browser
  --run-root "${run_root}"
  --output-root "${browser_root}"
  --context-state-root "${context_state_root}"
)
((enable_oi_vpoc == 1)) || build_args+=(--no-oi-vpoc)
((enable_volume_profile == 1)) || build_args+=(--no-volume-profile)
"${cli}" "${build_args[@]}"

printf '\nReplay published successfully.\n'
printf 'Session: %s\n' "${session_day}"
printf 'Run: %s\n' "${run_directory}"
printf 'GUI files: %s\n' "${browser_root}"
printf 'Inventory context: %s\n' "${context_state_root}"
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet banknifty-new-divergence-gui.service; then
  printf 'GUI service is active; no restart is required.\n'
else
  printf 'GUI service is not active. Install it with sudo ./install_gui_service.sh.\n'
fi
