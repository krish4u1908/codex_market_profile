# Market Workspace V3

One responsive React GUI for BANKNIFTY and NIFTY, with adapters for v1.0.62 reference publications and native V2.0.0 contexts. The shared-core deployment runs one GUI service per instrument. Changing the instrument or version selects a different data contract and cancels the previous session's workers. Opening another GUI does not create another calculation engine.

| Workspace | URL query | Strike grid | Source |
| --- | --- | --- | --- |
| BANKNIFTY v1.0.62 | `?workspace=banknifty-v1062` | 100 points | Prepared v1.0.62 browser payload |
| NIFTY v1.0.62 | `?workspace=nifty-v1062` | 50 points | NIFTY prepared v1.0.62 browser payload |
| BANKNIFTY v2.0.0 | `?workspace=banknifty-v200` | 100 points | Native BANKNIFTY V2 session |
| NIFTY v2.0.0 | `?workspace=nifty-v200` | 50 points | Native NIFTY V2 session |

V3 identifies the GUI and deployment runtime. The [shared cores](../market-core-v3/README.md) reuse the frozen calculation packages: one authority per instrument supplies both views. V2 reference calls retain the v1.0.62 corrected rules. No thresholds, scoring, inventory coordinates, lifecycle states or publication rules are changed here.

## Run

Requires Node.js 22.13+; Python 3.10+ is needed only for the SQLite exporter and its test.

```sh
cd apps/market-workspace-v3
npm ci
npm run dev
```

Open the local URL printed by Vite. Select a workspace, then use **Open session** with a prepared `.json` or `.json.gz` file. The file is read locally in a worker and is not uploaded. A catalog is optional; an empty installation prompts for a file. Known instrument/version conflicts are rejected. Legacy V2 exports without an instrument field are bound to the explicitly selected workspace, so select the matching instrument before opening them.

```sh
npm test
npm run build
npm run preview
```

The build produces a standalone `dist/` directory. Serve it at the origin root using an ordinary static web server. No Sites account, Next.js server, Cloudflare credentials or broker credentials are required. The implementation uses browser workers, gzip decompression and canvas charts; it retains responsive desktop/mobile layouts, touch navigation and expand controls.

## Import saved sessions into a local catalog

Replay archives and market data are deliberately excluded from Git. Import existing prepared files on your own machine:

```sh
npm run import:session -- --profile banknifty-v1062 --file /path/to/banknifty-v1062-session.json.gz
npm run import:session -- --profile nifty-v1062 --file /path/to/nifty-v1062-session.json
npm run import:session -- --profile banknifty-v200 --file /path/to/banknifty-v200-session.json
npm run import:session -- --profile nifty-v200 --file /path/to/nifty-v200-session.json
```

The importer validates the contract, records the source fingerprint and writes one per-workspace catalog plus compressed session files under `public/data/`. Import before building when those catalogs should be included in your local static build. Serve sensitive recordings only on a host whose access you control. They are never included in this repository.

An optional `--note "..."` supplies a visible provenance note, for example to identify historical minute/OI reconstruction. The supplied 3 September NIFTY sample has no retained constituent cash or VIX; those panes show missing values.

## Full option bars in V2

Native V2 session exports contain reference calls, context, price history and basket aggregates. They do not always contain individual strike receipts. The GUI uses those native aggregates when necessary and explicitly identifies missing per-strike/cumulative data. It never sums overlapping five-minute windows to manufacture session cumulative flows.

For full strike bars and receipt-level futures deltas, export the original inputs from the **existing V2 engine's own database**:

```sh
python scripts/export-v2-inputs.py \
  --database /path/to/existing-v2/context.sqlite3 \
  --session 2026-09-07 \
  --profile banknifty-v200 \
  --output /path/to/banknifty-v200-with-inputs.json

npm run import:session -- --profile banknifty-v200 --file /path/to/banknifty-v200-with-inputs.json
```

Use `nifty-v200` for NIFTY. The exporter opens SQLite read-only, reads a coherent snapshot, copies immutable decisions verbatim and never imports or starts an engine.

For historical replay, matching prepared market receipts can also accompany a native V2 session:

```sh
npm run import:session -- \
  --profile nifty-v200 \
  --file /path/to/native-nifty-v2-session.json \
  --chart-inputs /path/to/matching-nifty-prepared-session.json
```

This copies only price, futures OI, cash/VIX and individual option receipts. It does **not** copy v1 calls or v1 inventory levels into V2. The session and instrument must match; available futures-contract identities and artifact fingerprints must also match. For older sources lacking those fields, the operator must provide receipts from the same underlying recording.

## Preserved GUI behavior

- Price chart with six signed OI-VPOC families, exact-value chips, persistent step lines and an explicit **Show lines** control.
- Red V2 futures volume-climax diamonds on the price and volume-ratio charts, labeled with the retained ratio strictly above 4×. Exactly 4, missing values and future publications are excluded; the ratio line stays amber.
- V2 CE/PE volume and signed OI climax candidates on the price chart, with separate toggles, first-burst/all-point display and native publication timestamps. See the named display policy below.
- Native V2 canonical, reconstructed cumulative and recent 15-minute volume VPOCs when retained, with distinct labels.
- Index, basis and VIX high/low through the replay cursor. Values reflect available source coverage; minute-close exports are not presented as full tick extremes.
- A three-minute price/basis ribbon directly below the index price chart, inside the same frame: green for falling index and rising basis, red for rising index and falling basis, gray otherwise. It shares the price chart's time axis and zoom. The separate basis panel retains its purple line.
- Nearby strike OI ladder: thick total bars, smaller cumulative positive/negative bars, potential support/resistance concentrations, source expiry and receipt times.
- Futures total OI, latest receipt delta and cumulative additions/removals in the same side panel. Missing receipt deltas remain unavailable.
- Fixed ATM plus three OTM contracts per side, option premiums, OI/volume flows, inventory, recorded events, replay steps and speed controls.
- Independent data and summary workers. Summary messages contain only a small current snapshot; chart histories are not cloned into summary requests.
- V2 context shows native short/broader price legs, fixed ATM, five-minute changes, basket totals/flows and input completeness separately from the reference call.

## Replay and live status

The [two-core deployment](../market-core-v3/DEPLOYMENT.md) supports Live and Replay for both instruments. Each GUI reads `/workspace-config.json`, exposes its two permitted version profiles, and polls its own core through a read-only proxy. The data worker fetches health and cached publications sequentially, retries failures, and cancels obsolete requests. Switching to replay reads saved publications while the core continues live ingestion. GUI restarts do not restart a core.

A static Vite build without that gateway continues to offer file/catalog replay. The earlier hosted static preview does not acquire live connectivity automatically. Live mode requires the accompanying backend deployment and running collectors.

Native call/context timestamps and separate price, OI and cash/VIX receipt clocks are preserved. Feed age and core/context errors are visible. New-day metadata waiting clears the previous live session. Market Summary uses an independent worker and remains bound to the snapshot requested. No order placement is implemented.

## Three-minute price/basis ribbon

The ribbon below the main index chart compares each synchronized index/basis receipt with the last receipt available at its timestamp minus three minutes. Green means `Δindex < 0` and `Δbasis > 0`; red means `Δindex > 0` and `Δbasis < 0`. Same-direction or flat changes are neutral gray. This is the net change across the window; every intermediate tick need not move in the same direction.

Both instruments and both version views use `PRICE_BASIS_RIBBON_3M_V1` in Live and Replay. The ribbon stays blank during initial warm-up, missing price/basis or feed gaps. Hover/tap shows both changes, the cutoff and the actual baseline receipt time. It draws forward only after the current receipt is available and stops at the replay cursor. The data worker computes the comparisons; native engine calls are unaffected.

GUI release `3.0.3-gui-price-ribbon` moves the existing ribbon from the basis panel into the price chart frame without changing its calculation. OI-VPOC overlays and V2 climax markers stay on the price chart. The ribbon also stays visible when the separate basis panel is hidden, and remains with the price chart when expanded.

## CE/PE climax display policy

`CE_PE_CLIMAX_DISPLAY_V1` is a separately named GUI research policy. CE and PE volume each use **≥2.5×**; CE/PE OI additions and reductions each use **≥3×** plus **≥0.5% of starting basket OI**. The denominator is the median of the four exact prior five-minute windows for the same metric and fixed basket. Missing, zero-baseline, incomplete or inconsistent OI data cannot produce a marker. The worker computes annotations once per loaded snapshot; the main thread only filters the current frame.

Amber markers identify CE and lavender identifies PE; circles mean volume, triangles mean OI additions/reductions. Coincident option events share a marker listing all their ratios. First qualifying publications mark bursts by default; **Every CE/PE point** includes subsequent qualifying windows. The expandable list retains exact event details when crowded chart labels are hidden. These trial settings reproduce the earlier one-session BANKNIFTY analysis; applying them to NIFTY is not an independent NIFTY calibration. They do not change any native call or frozen engine threshold.

Both instrument GUIs support the annotations in Live and Replay. For the existing server, use the [GUI-only updater](../market-core-v3/GUI_UPDATE.md); it preserves the two core processes and their databases.

## Verification

```sh
npm test
npm run build
node scripts/verify-session.mjs nifty-v200 /path/to/imported-session.json.gz
```

Tests use small synthetic contracts that are never served as market data. They exercise all four profiles, wrong-instrument rejection, delayed publications, missing VIX, cumulative reconciliation, retained VPOC gaps, independent summaries, obsolete worker loads and the read-only exporter. Private recordings can be checked separately with `verify-session.mjs`; none are required by CI.

See [DATA_CONTRACT.md](DATA_CONTRACT.md) for adapter semantics and [SOURCE_LINEAGE.md](SOURCE_LINEAGE.md) for the reviewed source packages.

## Cash/VIX data quality

GUI `3.0.4-cash-vix-data` uses the versioned indicator input stream from core 3.0.1 when present. VIX is plotted at source-minute close, with availability time in the tooltip and explicit missing-minute counts. Replay selects only revisions known at the cursor; Live uses the current snapshot knowledge time. Original exports retain their receipt-based display. Cash rolling display requires five complete consecutive minutes. See [the combined data update](../market-core-v3/DATA_UPDATE.md); the GUI-only package does not install the corrected reader.

## VIX ribbon marks: VIX_RIBBON_5M_PCT_V1

GUI 3.0.5 adds translucent vertical marks to the existing price/basis ribbon for both instruments and both version views. A five-minute VIX percentage change of at least +0.4% is red; at most −0.4% is green. Smaller changes have no mark. The percentage uses the close five elapsed minutes earlier as its denominator and requires six consecutive finite, positive one-minute VIX closes. Cash completeness is independent.

Marks use actual observation availability on the x-axis. The worker processes revisions in arrival order; after-session repairs cannot create earlier intraday marks. Rewinding preserves the original observations. Repeated cash-only revisions cannot duplicate a VIX mark, and a batch produces one assessment for the latest eligible five-minute window. Hover/tap shows endpoint values, source-minute close times and availability. This display-only policy does not alter reference calls, indicators in the core, or the three-minute basis ribbon. Installation is described in [GUI_UPDATE.md](../market-core-v3/GUI_UPDATE.md).
## GUI 3.0.6: near-OTM OI entry bubbles

V2 adds small translucent green/red circles above the shared price/basis/VIX
ribbon for the proposed long/short entry conditions. The worker checks
individual near-OTM OI spikes, a recent VIX/premium setup and the published
market context. Hover/tap shows evidence; expandable review shows filtered
spikes and can seek replay. See [the rule and replay walkthrough](OI_ENTRY_REPLAY.md)
and [GUI-only installation](../market-core-v3/GUI_UPDATE.md).
