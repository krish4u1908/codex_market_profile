#!/bin/sh
set -eu

release_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
codex_home=${CODEX_HOME:-"$HOME/.codex"}
source_file="$release_root/config/codex-learning.config.toml"
destination="$codex_home/banknifty-learning.config.toml"

mkdir -p "$codex_home"
chmod 700 "$codex_home"

if [ -e "$destination" ]; then
  if cmp -s "$source_file" "$destination"; then
    echo "Opt-in Codex profile already matches: $destination"
    exit 0
  fi
  echo "Refusing to overwrite existing profile: $destination" >&2
  exit 2
fi

install -m 600 "$source_file" "$destination"

echo "Installed opt-in Codex profile: $destination"
echo "It is active only with: --profile banknifty-learning"
echo "Run the lab profile-check before generating any candidate."
