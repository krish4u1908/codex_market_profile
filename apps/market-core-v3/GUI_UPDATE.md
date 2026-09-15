# GUI 3.0.13 replay pace control

Requires the existing shared core **3.0.2**. This is a **GUI-only replay-control release** over 3.0.12. It does not change replay data, OI calculations, basket selection, VPOCs, calls, VIX, bubbles, workers, adapters, or backend/core logic.

The replay pace selector now describes how much real time is used to advance one recorded market minute:

- `1m / 1s` — one recorded minute every 1 real second
- `1m / 15s` — one recorded minute every 15 real seconds (**default**)
- `1m / 30s` — one recorded minute every 30 real seconds

The existing manual step selector remains unchanged (`1m`, `5m`, `10m` step). Pause, event seeking, timeline seeking, session switching and VPOC-shift playback continue to behave as before.

## Install on the existing VPS

Extract the package into a fresh directory, then run:

```bash
(
set -eu
cd /home/bankadmin/divergence/releases/shared_engine
replay_pace_dir=$(mktemp -d "$PWD/replay-pace-3.0.13-XXXXXX")
unzip -q market-workspace-v3-gui-replay-pace-3.0.13.zip -d "$replay_pace_dir"
cd "$replay_pace_dir/market-workspace-v3-gui-update"
sudo python3 -B update_gui.py check
sudo python3 -B update_gui.py apply
)
```

`check` is read-only. `apply` restarts only `banknifty-gui.service` and `nifty-gui.service`; both core PIDs must remain unchanged.

Verify:

```bash
curl -fsS http://127.0.0.1:8920/gui-release.json | python3 -m json.tool
curl -fsS http://127.0.0.1:8921/gui-release.json | python3 -m json.tool
```

Both should report `3.0.13-gui-replay-pace`. Hard-refresh the browser with **Ctrl+F5**. In Replay, the pace selector should default to `1m / 15s` and offer `1m / 1s`, `1m / 15s`, and `1m / 30s`.

Rollback with the exact record printed by `apply`:

```bash
sudo python3 -B update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/RECORD_FROM_APPLY.json
```
