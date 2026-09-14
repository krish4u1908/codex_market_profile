# GUI 3.0.12 OI-flow histogram layout fix

Requires the existing shared core **3.0.2** and its `OPTION_REPORT_INPUTS_V1`
feed. This is a **GUI-only layout release** over 3.0.11. The PE/CE near-OTM
`ΔOI · 1m` histogram stays in the same price-chart frame, below the existing
price/basis and VIX captions and above the existing bubble review controls.

The only functional presentation change is more visible histogram space:

- PE and CE lanes grow from the cramped 60px plot to a 108px plot.
- Each lane gets a 46px chart grid, with the same independent PE/CE scale.
- Unused left/right plot margins are reduced so the histogram uses more of the
  available horizontal width.
- Bar width cap rises from 5px to 7px for clearer one-minute receipts.
- Fullscreen height accounting is adjusted so the larger ribbon does not move
  the surrounding frame or controls.

No OI calculation, basket selection, worker, adapter, core, replay, call, VPOC,
VIX, bubble, or backend behavior changes in 3.0.12. Missing/stale receipts remain
gaps exactly as in 3.0.11.

Extract the package into a fresh directory, then run:

```bash
(
set -eu
cd /home/bankadmin/divergence/releases/shared_engine
oi_flow_dir=$(mktemp -d "$PWD/oi-flow-3.0.12-XXXXXX")
unzip -q market-workspace-v3-gui-oi-flow-3.0.12.zip -d "$oi_flow_dir"
cd "$oi_flow_dir/market-workspace-v3-gui-update"
sudo python3 -B update_gui.py check
sudo python3 -B update_gui.py apply
)
```

Use a fresh extraction directory. Do not copy ZIPs or unrelated files into the
manifest-verified update directory. `check` is read-only. `apply` restarts only
`banknifty-gui.service` and `nifty-gui.service`; both core PIDs must remain
unchanged.

Verify:

```bash
curl -fsS http://127.0.0.1:8920/gui-release.json | python3 -m json.tool
curl -fsS http://127.0.0.1:8921/gui-release.json | python3 -m json.tool
```

Both endpoints should report `3.0.12-gui-oi-flow-layout` and
`NEAR_OTM_OPTION_OI_FLOW_1M_V1`. Hard-refresh with **Ctrl+F5**. Validate both
BANKNIFTY V2 on port **8920** and NIFTY V2 on port **8921**, in Live and Replay.
The PE/CE histogram must remain below the price/basis + VIX captions and above
the OI/VIX bubble review, with visibly taller lanes and no change to the price
chart frame placement.

Rollback with the exact record printed by `apply`:

```bash
sudo python3 -B update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/RECORD_FROM_APPLY.json
```
