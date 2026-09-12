# Basic OI / VIX bubble update

Installs core **3.0.2** and GUI **3.0.8-basic-oi-vix-bubbles** on the existing
BANKNIFTY/NIFTY shared workspace. PE bubbles sit above the ribbon and CE below;
red means VIX rise ≥0.4%, green means VIX fall ≥0.4%, with the approved OI spike.

The raw report-quote feed is necessary to reproduce the approved September 10
and 11 timestamps. Completed-minute VIX closes cannot substitute for those
quotes. The configured collector roots must retain `oi/YYYY-MM-DD/oi_*.jsonl`.

## Existing VPS installation

Download `market-workspace-v3-basic-oi-vix-3.0.8.zip` into
`/home/bankadmin/divergence/releases/shared_engine`. Run this in a subshell so a
failed command cannot accidentally apply an older updater in the current folder:

```bash
(
set -eu
cd /home/bankadmin/divergence/releases/shared_engine
bubble_update_dir=$(mktemp -d "$PWD/basic-oi-vix-3.0.8-XXXXXX")
unzip -q market-workspace-v3-basic-oi-vix-3.0.8.zip -d "$bubble_update_dir"
cd "$bubble_update_dir/market-workspace-v3"
sudo python3 -B core/deploy/update_data.py check
sudo python3 -B core/deploy/update_data.py apply
)
```

Extract the download once into this fresh directory. Do not copy the ZIP into
an already extracted, manifest-verified bundle. This is a **full core + GUI
update**; do not run an old `update_gui.py` or reinstall with `install.py`.

Apply briefly restarts only these four existing units:

- `banknifty-core.service` / `nifty-core.service`
- `banknifty-gui.service` / `nifty-gui.service`

It preserves configuration, collector files, saved native calls and the current
release location. The package verifies frozen vendor files and dependencies,
records backups, checks health and restores both code slots on a failed apply.
No extra engine or broker connection is created. The separate near-real-time
preview ports are outside this updater's scope.

## Verify and replay

```bash
curl -fsS http://127.0.0.1:8920/gui-release.json
curl -fsS http://127.0.0.1:8921/gui-release.json
curl -fsS http://127.0.0.1:8920/api/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8921/api/health | python3 -m json.tool
```

Expected GUI version: `3.0.8-basic-oi-vix-bubbles`, policy `BASIC_OTM_OI_VIX_V1`.
Both cores should show version `3.0.2` and
`option_report_inputs.schema: OPTION_REPORT_INPUTS_V1`. An out-of-hours/current
session with no archive can show pending/missing data without preventing older
session replay.

Hard-refresh each browser with **Ctrl+F5**. Use BANKNIFTY port **8920** or NIFTY
port **8921**, choose V2.0.0 → Replay → September 10 or 11. Keep “OI / VIX
bubbles” checked. The old replay opens immediately; report quotes load in the
background. Move the replay slider to the session end to see the complete totals:

| NIFTY session | PE red above | PE green above | CE red below | CE green below |
| --- | ---: | ---: | ---: | ---: |
| September 10 | 4 | 2 | 0 | 6 |
| September 11 | 2 | 6 | 1 | 11 |

If the raw quote status is unavailable, this read-only endpoint identifies it:

```bash
curl -fsS 'http://127.0.0.1:8921/api/option-report-inputs?profile=nifty-v200&session=2026-09-11' -o /tmp/nifty-option-reports.json
python3 -c 'import json; d=json.load(open("/tmp/nifty-option-reports.json")); print({k:d.get(k) for k in ("schema","instrument","session","status","quality","error")})'
```

An initial HTTP 202 means the archive is loading; repeat after a few seconds.
Missing original option-chain quotes are reported explicitly. Local file imports
need an embedded `option_report_inputs`; use server-catalog replay to load raw
quotes automatically. Core ports remain **8922** BANKNIFTY / **8923** NIFTY.

## Rollback

The apply output contains the exact `record` path under
`/opt/market-workspace-v3/data-update-records/`. From the extracted bundle:

```bash
sudo python3 -B core/deploy/update_data.py rollback --record /opt/market-workspace-v3/data-update-records/RECORD_FROM_APPLY.json
```

Replace the placeholder with the actual record. This restores both prior core
and GUI slots; stale rollback records are rejected before stopping services.
