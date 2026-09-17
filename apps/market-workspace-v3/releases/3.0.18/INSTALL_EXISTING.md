# Update the existing installation

This package replaces the GUI assets served by the existing V3 installation. It does not run another prototype or create a listener/service.

Reviewed target: `srv1913330`, installation `/opt/market-workspace-v3`.
Existing NIFTY GUI: port **8921**. Existing BANKNIFTY GUI: port **8920**.
Both use the shared GUI directory, so the original updater restarts **both existing GUI services**. It does not restart either core or change their ports, credentials, stored sessions or calculations.

On the existing VPS, extract this ZIP into a new staging directory. From its `NIFTY_V3_0_18_PRESSURE_DIRECTION` directory, run:

```sh
sudo python3 -B update_gui.py check
sudo python3 -B update_gui.py apply
```

`check` validates checksums, the installed service commands and core compatibility. Stop if it reports a mismatch; do not force the update or remove the host check.

`apply` backs up the active GUI, switches its assets, restarts only the existing GUI services, checks their health/release, and checks that both core PIDs stayed unchanged. It attempts to restore the prior GUI if those checks fail. Keep the update record path printed by `apply`.

Then open your **same existing NIFTY address**, hard refresh, and select NIFTY V2 → Live or Replay → **OI Direction**. Use **Custom display** inside that tab to show/hide each frame. No npm process, prototype `server.py`, development server or extra port is required.

Verify on the VPS:

```sh
curl -fsS http://127.0.0.1:8921/gui-release.json
curl -fsS http://127.0.0.1:8920/gui-release.json
```

The release should be `3.0.18-gui-pressure-direction`.

Rollback, using the exact record path printed by the completed update:

```sh
sudo python3 -B update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/RECORD_FROM_APPLY.json
```

Replace `RECORD_FROM_APPLY.json` with the actual filename. This ZIP has been prepared and tested locally; it has not been applied to your VPS.
