# Near real-time display preview — 3.1.0-preview.1

This is a separate trial for BANKNIFTY and NIFTY, in both the V1.0.62 and V2.0.0 views.
It requires the existing shared core 3.0.1 installation. The normal application stays installed and running.

## What changes in this trial

- The index chart gets a dotted extension from incoming collector readings. The headline index price follows that feed while it is fresh.
- VIX also gets a dotted incoming extension; its confirmed minute history and five-minute ribbon rules stay intact.
- An **Incoming volume** pane shows observed futures or fixed-basket CE/PE volume increases by receipt minute. The current minute is outlined. Grey bars indicate incomplete coverage.
- The existing **Futures volume ratio**, red climax diamonds, CE/PE climax annotations, OI, VPOCs, calls and ribbons continue to use the existing core's confirmed data.
- The preview labels incoming values as provisional. It does not calculate intraminute climax ratios or introduce early climax markers.

This intentionally lets you compare fast market movement against the existing completed-minute climax detector. It is not a different trading model.

## How isolation works

The package installs two additional web services, each with a read-only collector-file reader. They are display services, **not additional strategy engines**. They make no FYERS connections and import no engine or strategy code.

| Component | Normal installation | Preview |
|---|---|---|
| BANKNIFTY GUI | Existing service, unchanged | Separate port, default 8930 |
| NIFTY GUI | Existing service, unchanged | Separate port, default 8931 |
| Both shared cores | Existing code, polling, buffers and publication timing | Reused through GET requests only |
| Raw collector files | Existing writer | Read only |
| Strategy databases and journals | Existing owners | Never opened by the preview reader |

The existing confirmed API response body, compression and ETag are forwarded without modifying their contents. Incoming readings travel through a separate endpoint and browser worker; they never enter the normalized decision input or the replay frame. A slow confirmed-data request does not block the incoming-data endpoint.

The reader checks files approximately every 250 ms and the browser requests its bounded display snapshot approximately every second, after the previous request completes. These are scheduling intervals, not guaranteed latency. Collector flushes, disk throughput, server load, browser rendering and network time still matter. A display service has a 256 MiB memory limit, a 20%-of-one-CPU quota and low CPU/I/O priority.

Confirmed basis remains on the existing synchronized index/futures path. The preview does not subtract two unrelated latest prices to create a new basis.

## Download and install

Use the **market-workspace-realtime-preview** artifact from this preview branch's successful GitHub Actions run. Do not use the old GUI updater or data updater for this package.

Copy `market-workspace-realtime-preview.zip` to your release-download directory on the server, then run the following from that directory. It handles both the outer Actions ZIP and the inner package ZIP and extracts into a new directory to avoid manifest errors.

```bash
(
set -eu
preview_dir=$(mktemp -d "$PWD/realtime-preview-XXXXXX")
unzip market-workspace-realtime-preview.zip -d "$preview_dir"
if [ -f "$preview_dir/market-workspace-realtime-preview.zip" ]; then
  unzip "$preview_dir/market-workspace-realtime-preview.zip" -d "$preview_dir/package"
  cd "$preview_dir/package/market-workspace-realtime-preview"
else
  cd "$preview_dir/market-workspace-realtime-preview"
fi
sudo python3 -B install_preview.py check --host 0.0.0.0
sudo python3 -B install_preview.py apply --host 0.0.0.0
)
```

The default existing-installation path is `/opt/market-workspace-v3/current`. Override it with `--base PATH` on both commands if needed. The preview is installed separately at `/opt/market-workspace-preview/3.1.0-preview.1`.

`check` verifies the package, existing core identity, non-root service users, port availability and separate installation paths. `apply` starts only these new services:

```text
banknifty-display-preview.service
nifty-display-preview.service
```

It checks that all four existing service PIDs and both core configuration hashes remain unchanged. If preview startup fails, it removes only the newly created preview installation and units. It does not restart a production service. An external restart during installation is reported rather than silently accepted.

`--host 0.0.0.0` exposes the preview like the existing GUI; omit it on both commands to bind only to localhost. The installer does not change firewall or reverse-proxy rules. Use your existing access restrictions for these additional ports.

Check the preview endpoints on the server:

```bash
curl -fsS --max-time 5 http://127.0.0.1:8930/health
curl -fsS --max-time 5 http://127.0.0.1:8931/health
curl -fsS --max-time 5 http://127.0.0.1:8930/gui-release.json
curl -fsS --max-time 5 http://127.0.0.1:8931/gui-release.json
```

Open the same server address you use for the normal GUI, using port **8930** for BANKNIFTY or **8931** for NIFTY. Both version views are available in the existing selector.

## Trial procedure

1. Keep the normal GUI open beside the preview during market hours.
2. Select the preview's **5m** chart range. Confirm that the preview index price and dotted extension advance between normal core snapshots. Check the receipt age in the preview banner.
3. Compare the **confirmed** futures volume ratio and climax markers for the same publication time in both pages. They should agree once each page has fetched that publication. Browser polling can make one page receive it before the other.
4. Check the Incoming volume pane separately. Its forming/partial bars are not the input bars of the confirmed climax model.
5. Open Market summary or switch panes. Incoming updates should continue independently.
6. Switch to Replay: the incoming reader stops in that browser, and replay shows only retained confirmed history.

The preview retains at most two minutes of incoming price/VIX points and ten minutes of observed volume, in memory. On attachment it reads a bounded recent tail, not the full session. The first volume baseline, gaps over 15 seconds, and cumulative-counter resets are excluded from volume increments and marked partial. Repeated or older receipts cannot add the same volume again. File truncation, replacement, contract changes and session rollover reset the preview generation and baselines.

CE/PE panes use the original fixed basket. They cannot invent quotes for contracts the collector no longer subscribes to; coverage remains visible. Missing readings are not filled from the other instrument's collector. A receipt older than five seconds is no longer shown as a fresh incoming price. At market close, fresh readings stop naturally; this is not evidence of a broken preview.

Incoming readings are not persisted by this trial. They will not appear as tick-level replay history later. Existing collector recordings and confirmed replay remain available through their original paths.

## Stop the trial

```bash
sudo systemctl disable --now banknifty-display-preview.service nifty-display-preview.service
```

Return to the original GUI addresses. Neither core nor original GUI needs a restart. Preview files can remain installed while disabled.

## Verification and limitations

Tests cover partial file writes, duplicates, counter resets, gaps, session rollover, file replacement/truncation, instrument separation, read-only source integrity, unchanged confirmed HTTP bytes/ETags, independent responses during a blocked core request, unchanged marker coordinates/ratios, and cancellation on leaving Live.

The existing frontend and core regression suites are also run. The preview has not been validated against a live trading session or timed on the deployment server. These checks establish implementation isolation; they do not establish an intraminute trading edge or guarantee latency. The branch deliberately produces only the preview package, not a replacement core or normal GUI update.

A comparison of the original and preview display projections used two supplied session exports and all **657 retained publication checkpoints**. Confirmed calls, futures and CE/PE climax events, ratios, coordinates, OI, controls and ribbons matched, including while injecting provisional index readings. All **107 files** in the original core source tree remained byte-identical. This comparison verifies retained-data parity; live-server resource impact still needs observation during the trial.

## Build from source

```bash
cd apps/market-workspace-v3
npm ci
npm test
npm run build
cd ../market-realtime-preview
python3 -B -m unittest discover -s tests -v
python3 -B build_preview.py --output /tmp/market-workspace-realtime-preview.zip
```
