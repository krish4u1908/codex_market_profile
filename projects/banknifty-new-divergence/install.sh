#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
VENV_DIR="${VENV_DIR:-${PROJECT_DIR}/.venv}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ ! -f "${PROJECT_DIR}/pyproject.toml" ]]; then
  fail "pyproject.toml was not found. Extract the complete release archive, then run this script from that extracted folder."
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 \
    || fail "PYTHON_BIN '${PYTHON_BIN}' was not found."
  PYTHON_COMMAND="$(command -v "${PYTHON_BIN}")"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON_COMMAND="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_COMMAND="$(command -v python3)"
else
  fail "Python 3.12 or newer is required. Install it and rerun this script."
fi

"${PYTHON_COMMAND}" -c \
  'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
  || fail "${PYTHON_COMMAND} is too old. Python 3.12 or newer is required."

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  if [[ -e "${VENV_DIR}" ]]; then
    fail "${VENV_DIR} exists but is not a usable virtual environment. Move it aside and rerun this script."
  fi
  printf 'Creating virtual environment: %s\n' "${VENV_DIR}"
  "${PYTHON_COMMAND}" -m venv "${VENV_DIR}"
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
"${VENV_PYTHON}" -c \
  'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
  || fail "The existing virtual environment uses Python older than 3.12. Move ${VENV_DIR} aside and rerun this script."

printf 'Installing BankNifty New Divergence...\n'
"${VENV_PYTHON}" -m pip install --disable-pip-version-check --upgrade "${PROJECT_DIR}"

printf 'Checking the installed command...\n'
"${VENV_PYTHON}" -m banknifty_profiler.new_divergence --help >/dev/null

printf '\nInstallation complete.\n'
printf 'Activate it with:\n  source "%s/bin/activate"\n' "${VENV_DIR}"
printf 'Then verify it with:\n  banknifty-new-divergence --help\n'
printf '\nNo replay, server, service, or background process was started.\n'
