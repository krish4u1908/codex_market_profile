#!/bin/sh
set -eu

release_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
venv="$release_root/.venv"

python3 -m venv "$venv"

site_packages=$(
  "$venv/bin/python" -c \
    'import sysconfig; print(sysconfig.get_paths()["purelib"])'
)

printf '%s\n' "$release_root/src" \
  > "$site_packages/banknifty_market_profile_learning_lab.pth"

wrapper="$venv/bin/banknifty-market-profile-lab"
{
  echo '#!/bin/sh'
  echo 'exec "$(dirname "$0")/python" -m banknifty_market_profile_lab "$@"'
} > "$wrapper"
chmod 755 "$wrapper"

echo "Installation complete."
echo "No replay, live service, worker, port, or background process was changed."
echo "Verify with:"
echo "  $venv/bin/banknifty-market-profile-lab --help"
