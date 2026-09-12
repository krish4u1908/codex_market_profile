# GUI update 3.0.6: near-OTM OI entry bubbles

For the Cash/VIX data correction, install the combined core and GUI update described in [DATA_UPDATE.md](DATA_UPDATE.md). A GUI-only update displays the new input feed when the core already supplies it.

This GUI retains the existing three-minute price/basis ribbon directly below the main index price chart for BANKNIFTY and NIFTY, in v1.0.62 and V2 Live/Replay. It includes the previous ribbon and CE/PE climax changes. Apply this package once, either over the initial V3 installation or a previous GUI-only update, including `3.0.1-gui-climax-v1` and `3.0.2-gui-basis-ribbon`. It stops and starts only `banknifty-gui.service` and `nifty-gui.service`, briefly interrupting GUI access. It keeps both core processes, their configuration and databases running in place. No unit files or collectors are changed.

V2 now adds small translucent green long-setup and red short-setup bubbles above this ribbon. See [the rule and replay walkthrough](../market-workspace-v3/OI_ENTRY_REPLAY.md). The detailed walkthrough is also included in this update package as `OI_ENTRY_REPLAY.md`.

## Apply on the already-installed server

Download the **market-workspace-v3-gui-update** Actions artifact and upload it to `~/divergence/releases/shared_engine/market-workspace-v3-gui-update.zip`. The Actions download can wrap an inner ZIP with the same name. This block handles either form and keeps ZIPs outside the verified package:

```bash
(
set -eu
cd "$HOME/divergence/releases/shared_engine"
entry_gui_dir=$(mktemp -d "$PWD/oi-entry-XXXXXX")
unzip market-workspace-v3-gui-update.zip -d "$entry_gui_dir"
if [ -f "$entry_gui_dir/market-workspace-v3-gui-update.zip" ]; then
  unzip "$entry_gui_dir/market-workspace-v3-gui-update.zip" -d "$entry_gui_dir/package"
  cd "$entry_gui_dir/package/market-workspace-v3-gui-update"
else
  cd "$entry_gui_dir/market-workspace-v3-gui-update"
fi
sudo python3 -B update_gui.py check
sudo python3 -B update_gui.py apply
)
```

The check verifies package hashes, current installation paths, running core processes and the reviewed GUI commands. Apply stages versioned assets, saves the old GUI, switches the two GUIs, verifies their identities and release, and checks that both core PIDs are unchanged. The original `/opt/market-workspace-v3/current` symlink is retained. New assets and update records live under `gui-releases/` and `gui-update-records/` in that installation.

Keep the `record` path printed by apply. A failed update attempts to restore the previous GUI automatically and records the outcome. If interrupted, inspect that record before repeating an update. The explicit rollback also supports a prepared update whose GUI directory was moved before interruption:

```sh
sudo python3 update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/REPLACE_WITH_PRINTED_RECORD.json
```

A rollback refuses to overwrite a newer GUI update; roll back the most recent one first. It retains the downloaded package, staged assets, update record and all market data.

Hard-refresh the browser after apply. Existing ports are unchanged: BANKNIFTY GUI **8920**, NIFTY GUI **8921**; internal cores **8922** and **8923**. Both `/gui-release.json` endpoints should report `3.0.6-gui-oi-entry-bubbles` and `"basisRibbonPlacement":"price"`. This GUI-only command leaves the installed core version unchanged.

**Do not rerun `core/deploy/install.py install` for this update.** That command is the first-install migration. Do not replace the current release directory manually or restart a core to refresh the charts.

## Five-minute VIX marks on the same ribbon

GUI policy `VIX_RIBBON_5M_PCT_V1` adds narrow, translucent vertical marks over the existing price/basis ribbon:

- **Red:** VIX increases by **at least 0.4%** over five minutes.
- **Green:** VIX decreases by **at least 0.4%** over five minutes.
- No mark for a smaller move, an unchanged value or an incomplete window.

The percentage is `100 × (VIX_now − VIX_5_minutes_earlier) / VIX_5_minutes_earlier`. It compares two one-minute closes five elapsed minutes apart and requires all six consecutive closes. This is a percentage change, not a 0.4-point VIX movement. Marks appear at each qualifying observation; successive qualifying minutes can show successive marks. Hover/tap shows the exact change, endpoint VIX values, source-minute closes and availability time. The two colors use 48% opacity.

The marks share the price/ribbon time axis and zoom in desktop, mobile and expanded charts. They remain visible when the separate VIX or basis panel is hidden. A compact legend distinguishes VIX marks from the existing three-minute price/basis strip.

Observations are processed in arrival order. The corrected input feed retains original observations and later revisions; a later repair cannot create an earlier mark or rewrite a previously observed mark. Historical repairs received after the plotted session do not generate intraday signals. Consequently, a complete corrected VIX line can have fewer marks than a calculation that assumes every correction was known during trading. Replay and Live use the same causal mark history. Native calls, core calculations, input journals and existing ribbon rules are unchanged.

Older exports can supply marks when source-minute and arrival timestamps are retained. Missing source-minute timestamps or incomplete VIX windows produce no mark. Complete cash data is not required for a VIX-only mark.

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
