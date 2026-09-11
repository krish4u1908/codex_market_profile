# Cash/VIX indicator data update

Core **3.0.1**, GUI **3.0.4-cash-vix-data**, input contract **CASH_VIX_INDICATOR_INPUTS_V1**.

This adds an observed Cash/VIX input stream inside each existing instrument core. It rereads changed collector minutes and appends later observations instead of permanently retaining an initially empty minute. Both GUIs use the new input history when present. VIX and cash validity are independent. No synthetic values, forward filling or interpolation are used to make a window complete.

The new stream is available to your indicator through `/api/indicator-inputs`. The retained v1.0.62/V2 reference calls and their original `cash_vix` inputs remain unchanged. Use the new endpoint for the new indicator. This is a separately named data contract, not a retrospective rewrite of the verified reference calculation.

## Install on the existing workspace

Download the **market-workspace-v3-deployment** artifact for this commit. This is a core and GUI update; applying the GUI-only artifact cannot install the input reader.

The Actions download is `market-workspace-v3-deployment.zip`; it contains `market-workspace-v3.zip`. Upload the download to `~/divergence/releases/shared_engine`, then run the complete block:

```bash
(
set -eu
cd "$HOME/divergence/releases/shared_engine"
data_update_dir=$(mktemp -d "$PWD/cash-vix-data-XXXXXX")
unzip market-workspace-v3-deployment.zip -d "$data_update_dir"
unzip "$data_update_dir/market-workspace-v3.zip" -d "$data_update_dir"
cd "$data_update_dir/market-workspace-v3"
sudo python3 -B core/deploy/update_data.py check
sudo python3 -B core/deploy/update_data.py apply
)
```

If you already extracted the wrapper and have `market-workspace-v3.zip`, extract that file into a fresh directory and use the last three commands. Keep downloaded ZIPs outside the extracted package directory; its file manifest is verified exactly.

Apply briefly stops and starts the **two cores and two GUIs**. It verifies the package, installed service commands, dependency compatibility and unchanged frozen vendor code, stages code/assets, saves the old code slots, activates the update, and checks the new core/GUI identities. Existing configuration, collectors, databases, native journals, units and the top-level `current` symlink are retained. This is not the first-install migration.

A failed activation attempts restoration of both old code slots. Keep the `record` path printed by apply. To restore a completed or interrupted update:

```bash
sudo python3 -B core/deploy/update_data.py rollback --record /opt/market-workspace-v3/data-update-records/REPLACE_WITH_PRINTED_RECORD.json
```

The updater rejects stale rollback records when a later update is active. New input journals remain available after rollback; the old core simply does not read them.

## Check data and export the September 11 audit

```bash
curl -fsS 'http://127.0.0.1:8920/api/health'
curl -fsS 'http://127.0.0.1:8921/api/health'
curl -fsS 'http://127.0.0.1:8920/api/indicator-inputs?profile=banknifty-v200' -o /tmp/banknifty-indicator-inputs.json
curl -fsS 'http://127.0.0.1:8921/api/indicator-inputs?profile=nifty-v200' -o /tmp/nifty-indicator-inputs.json
```

Both health responses should show core `3.0.1` and the input schema. Inspect the input `status`, `quality`, and `vix_window_5m` fields. A running core alone does not imply complete VIX data. A new session without collector metadata remains waiting. Refresh both GUIs with Ctrl+F5; `/gui-release.json` should report `3.0.4-cash-vix-data`.

This read-only audit compares the native retained receipts with the actual collector CSV for an earlier session and exports a new dataset outside production state:

```bash
sudo python3 -B /opt/market-workspace-v3/current/core/scripts/audit_indicator_inputs.py \
  --config /opt/market-workspace-v3/current/config/nifty.json \
  --session 2026-09-11 \
  --output /tmp/nifty-indicator-audit-20260911.json
```

For BANKNIFTY, use its config and a separate output filename. The audit reports recovered and still-missing VIX minutes. Recovery requires the corresponding readings to exist in the collector CSV. The previously supplied NIFTY JSON alone cannot supply its 12 absent values. Values found only during this audit are marked available at the audit time and cannot be used as if known in an earlier live decision.

## Indicator contract

- Nominal source window: **09:15–15:29 IST** minute starts, closing through **15:30**. Missing source minutes stay explicit; no values are invented when a collector stops earlier or a market session differs.
- `minute_ist` and `minute_end` describe the source bar. `available_at` is when this particular revision became known. `source_published_at` is the earliest publication permitted by completed-minute timing and source receipts. `vix_received_at` is retained when supplied by the CSV.
- `revision` increases per minute. Atomic, immutable journal batches include source file hashes and a previous-batch hash. Valid native receipt values can be seeded with their original observed timestamps; later raw-source corrections are separate observations.
- `vix_valid` requires a finite positive VIX value with an available source receipt. `cash_valid` requires all configured constituent weights to have valid closes and a usable session-open reference. A partial cash amount remains labeled partial; it cannot pass a cash indicator window.
- Cash is the weighted return of the configured collector basket, normalized to available weight. `expected_constituent_count` and `available_weight` describe that basket; they do not imply coverage of every index constituent.
- `indicator_window(feed, as_of, minutes, field)` selects the latest revision known at `as_of` and requires exact consecutive source minutes. It reports missing minutes and fails incomplete/unavailable windows. Its `ready` flag describes data completeness, not a trading signal. Also inspect `quality.session_open` and `quality.source_age_seconds` before using current-session inputs.
- Historical GUI replay filters observations by the replay cursor. Live displays use the snapshot publication time as the knowledge cutoff and can show later corrections at their source-minute coordinates. Hover shows arrival time. Recorded reference calls retain their original inputs in both modes.

Example inside the installed environment:

```python
import json
from urllib.request import urlopen
from market_core.indicator_inputs import indicator_window

with urlopen('http://127.0.0.1:8923/api/indicator-inputs?profile=nifty-v200') as response:
    feed = json.load(response)
window = indicator_window(feed, feed['as_of'], minutes=5, field='vix_close')
if window['ready'] and feed['quality']['session_open']:
    values = [row['vix_close'] for row in window['rows']]
    # Compute your separately specified indicator from these verified inputs.
```

The five-minute check is an input completeness example; this update does not choose or tune an indicator formula.
