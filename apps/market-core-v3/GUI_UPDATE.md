# GUI update: price-chart ribbon and CE/PE climax annotations

This update moves the existing three-minute price/basis ribbon directly below the main index price chart for BANKNIFTY and NIFTY, in v1.0.62 and V2 Live/Replay. It includes the previous ribbon and CE/PE climax changes. Apply this package once, either over the initial V3 installation or a previous GUI-only update, including `3.0.1-gui-climax-v1` and `3.0.2-gui-basis-ribbon`. It stops and starts only `banknifty-gui.service` and `nifty-gui.service`, briefly interrupting GUI access. It keeps both core processes, their configuration and databases running in place. No unit files or collectors are changed.

## Apply on the already-installed server

Upload `market-workspace-v3-gui-update.zip` to a new working directory on the server, then run:

```sh
unzip market-workspace-v3-gui-update.zip
cd market-workspace-v3-gui-update
sudo python3 update_gui.py check
sudo python3 update_gui.py apply
```

The check verifies package hashes, current installation paths, running core processes and the reviewed GUI commands. Apply stages versioned assets, saves the old GUI, switches the two GUIs, verifies their identities and release, and checks that both core PIDs are unchanged. The original `/opt/market-workspace-v3/current` symlink is retained. New assets and update records live under `gui-releases/` and `gui-update-records/` in that installation.

Keep the `record` path printed by apply. A failed update attempts to restore the previous GUI automatically and records the outcome. If interrupted, inspect that record before repeating an update. The explicit rollback also supports a prepared update whose GUI directory was moved before interruption:

```sh
sudo python3 update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/REPLACE_WITH_PRINTED_RECORD.json
```

A rollback refuses to overwrite a newer GUI update; roll back the most recent one first. It retains the downloaded package, staged assets, update record and all market data.

Hard-refresh the browser after apply. Existing ports are unchanged: BANKNIFTY GUI **8920**, NIFTY GUI **8921**; internal cores **8922** and **8923**. Both `/gui-release.json` endpoints should report `3.0.3-gui-price-ribbon` and `"basisRibbonPlacement":"price"`. The core API version remains `3.0.0`.

**Do not rerun `core/deploy/install.py install` for this update.** That command is the first-install migration. Do not replace the current release directory manually or restart a core to refresh the charts.

## Three-minute ribbon below the price chart

The ribbon sits directly below the main index price plot, inside the same chart frame. Its time axis and zoom are linked to price, including when the chart is expanded. OI-VPOC lines and climax markers remain on the price chart. The separate basis panel keeps its purple line; hiding that panel leaves the ribbon visible. The ribbon compares net index and basis changes against three minutes earlier:

| Index change | Basis change | Ribbon |
| --- | --- | --- |
| Down | Up | Green |
| Up | Down | Red |

Any other finite combination, including either unchanged value, is neutral gray. Missing history, initial warm-up and feed gaps stay blank.

Both instruments and both version views support the ribbon in Live and Replay. Hover/tap shows the changes and the retained baseline receipt time. No color appears before its receipt becomes available, and the ribbon stops at the current cursor. The comparison uses the last available receipt at or before the three-minute cutoff; stale baselines and broken receipt continuity are excluded. These are display rules; no core calculations are changed.

## Retained V2 climax behavior

- CE and PE volume: ratio **≥2.5×**; circular price-chart markers.
- CE and PE OI additions/reductions: ratio **≥3×** and amount **≥0.5% of starting basket OI**; up/down triangle price-chart markers.
- Each ratio compares a native five-minute amount with the median at the four exact previous five-minute cutoffs. Additions and reductions use separate baselines.
- Native futures volume ratios **>4×**: **red diamonds** on both price and futures-volume-ratio charts. The ratio line remains amber.
- Separate toggles isolate all six CE/PE metrics and futures. First burst markers are the default; **Every CE/PE point** reveals every qualifying publication. Coincident option events share one marker with all ratios in its label/tooltip.
- OI-VPOC lines remain available through the existing Show lines control.

The same display policy runs in Live and Replay. Markers appear only at native publication time and require complete basket windows. Historical chart reconstruction does not create earlier climax events. These are trial display thresholds from one BANKNIFTY session; they have not been independently calibrated for NIFTY or established as profitable trading signals. Native v1.0.62/V2 calls and frozen calculations are unchanged.

## Build this update from source

From the repository root:

```sh
cd apps/market-workspace-v3
npm ci
npm test
npm run build
cd ../market-core-v3
python3 scripts/build_bundle.py --output /tmp/market-workspace-v3.zip
python3 scripts/build_gui_update.py --deployment-bundle /tmp/market-workspace-v3.zip --output /tmp/market-workspace-v3-gui-update.zip
```

GitHub Actions uploads a separate `market-workspace-v3-gui-update` artifact. If downloading the Actions artifact wrapper, extract it first to obtain `market-workspace-v3-gui-update.zip`, then follow the server commands above. Session archives and databases are excluded from both bundles.
