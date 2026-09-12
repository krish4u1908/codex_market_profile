# GUI 3.0.9 OI/VIX research bubbles

Requires existing core **3.0.2** and `OPTION_REPORT_INPUTS_V1`. The updater
checks both cores before modifying the GUI. Cores below 3.0.2 require the full
update described in `DATA_UPDATE.md`.

Download `market-workspace-v3-gui-oi-vix-3.0.9.zip` to
`/home/bankadmin/divergence/releases/shared_engine` and run:

```bash
(
set -eu
cd /home/bankadmin/divergence/releases/shared_engine
bubble_update_dir=$(mktemp -d "$PWD/gui-oi-vix-3.0.9-XXXXXX")
unzip -q market-workspace-v3-gui-oi-vix-3.0.9.zip -d "$bubble_update_dir"
cd "$bubble_update_dir/market-workspace-v3-gui-update"
sudo python3 -B update_gui.py check
sudo python3 -B update_gui.py apply
)
```

Use a fresh extraction directory. Do not copy recordings or the ZIP into the
verified update directory. `-B` prevents Python cache files from affecting the
package manifest. `check` is read-only; `apply` performs installation.

Only `banknifty-gui.service` and `nifty-gui.service` restart. The updater keeps
both core PIDs and records the previous GUI for rollback. No collector, runtime
strategy, configuration or database changes are required.

```bash
curl -fsS http://127.0.0.1:8920/gui-release.json
curl -fsS http://127.0.0.1:8921/gui-release.json
```

Expect `3.0.9-oi-vix-research` and policy `BASIC_OTM_OI_VIX_V2` on both ports.
Hard refresh with Ctrl+F5, choose V2.0.0 and Replay. Standard BANKNIFTY is on
8920; NIFTY on 8921. The separate real-time preview has its own GUI assets.

| Bubble | Rule | Position |
| --- | --- | --- |
| Green | PE OI spike down + VIX rise >=0.4% | Above |
| Red | CE OI spike down + VIX fall >=0.4% | Below |
| Yellow | PE OI spike down + VIX fall >=0.4% | Above |
| Yellow | CE OI spike down + VIX rise >=0.4% | Below |

The OI rule remains a fall of at least 1%, at least 3 times its prior 20-update
median absolute change. VIX uses five report-minute slots. VPOC and other
trend gates remain excluded. Standalone VIX vertical ribbon marks keep their
existing red-rise/green-fall meaning; bubble colours express the table above.

In NIFTY replay, use Open session to load the supplied September 10 or 11
JSON.gz files. These copies include raw option-report inputs and retain the
original recorded V2 decisions. Server-catalog replays also load report inputs
through the existing core endpoint.

| Session at recording end | Green above | Red below | Yellow above | Yellow below |
| --- | ---: | ---: | ---: | ---: |
| September 10 | 4 | 6 | 2 | 0 |
| September 11 | 2 | 11 | 6 | 1 |

At 11:15:55.113 IST on September 10, the CE/VIX-fall bubble is now red below
the ribbon. It is absent before that report arrives. At 13:02:55.226, the
PE/VIX-rise bubble is green above. At 15:24:55.064, PE/VIX-fall is yellow above.

Rollback from the same extracted package using the exact `record` path printed
by apply (under `/opt/market-workspace-v3/gui-update-records/`):

```bash
sudo python3 -B update_gui.py rollback --record /opt/market-workspace-v3/gui-update-records/RECORD_FROM_APPLY.json
```

Replace the placeholder with the actual record. Results and paper trade tests
are research observations; they do not modify live core calls.
