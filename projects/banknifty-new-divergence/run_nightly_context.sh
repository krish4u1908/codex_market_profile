#!/usr/bin/env bash

set -Eeuo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cli="${project_dir}/.venv/bin/banknifty-new-divergence"
data_root="${COLLECTOR_DATA_ROOT:-/opt/banknifty-collector/data-prod-v4}"
state_root="${CONTEXT_STATE_ROOT:-${HOME}/divergence/new-divergence-context-v1.0.12}"
config="${CONTEXT_CONFIG:-${project_dir}/configs/nightly_context_v2.json}"

if [[ ! -x "${cli}" ]]; then
  printf 'ERROR: installed CLI not found: %s; run ./install.sh first\n' "${cli}" >&2
  exit 1
fi

exec "${cli}" nightly-context \
  --data-root "${data_root}" \
  --state-root "${state_root}" \
  --config "${config}" \
  "$@"
