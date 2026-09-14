# GUI 3.0.11 minute OI-flow ribbon

Requires the existing shared core **3.0.2** and its
`OPTION_REPORT_INPUTS_V1` feed. This GUI-only release retains every existing
panel and adds two compact, synchronized histogram lanes beneath the existing
price/basis and VIX captions inside the price-chart frame:

- PE near-OTM `ΔOI · 1m`
- CE near-OTM `ΔOI · 1m`

Green bars above zero are fresh positive OI. Red bars below zero are fresh
negative OI magnitude. Each minute is calculated from consecutive original OI
report receipts for the three current strict near-OTM contracts on that side.
Missing or stale receipts remain gaps. Calls, bubbles, VPOCs and market logic
are unchanged.

Extract the package into a fresh directory, then run:

```bash
(
set -eu
cd /home/bankadmin/divergence/releases/shared_engine
oi_flow_dir=$(mktemp -d "$PWD/oi-flow-3.0.11-XXXXXX")
unzip -q market-workspace-v3-gui-oi-flow-3.0.11.zip -d "$oi_flow_dir"
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

Both endpoints should report `3.0.11-gui-minute-oi-flow` and
`NEAR_OTM_OPTION_OI_FLOW_1M_V1`. Hard-refresh with **Ctrl+F5**. Test both
BANKNIFTY V2 on port **8920** and NIFTY V2 on port **8921**, in Live and Replay.

Rollback with the exact record printed by `apply`:

```bash
sudo python3 -B update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/RECORD_FROM_APPLY.json
```
