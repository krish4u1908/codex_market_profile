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
- V2 volume-climax diamonds on the price and volume-ratio charts, labeled with the retained ratio strictly above 4×. Exactly 4, missing values and future publications are excluded.
- Native V2 canonical, reconstructed cumulative and recent 15-minute volume VPOCs when retained, with distinct labels.
- Index, basis and VIX high/low through the replay cursor. Values reflect available source coverage; minute-close exports are not presented as full tick extremes.
- Nearby strike OI ladder: thick total bars, smaller cumulative positive/negative bars, potential support/resistance concentrations, source expiry and receipt times.
- Futures total OI, latest receipt delta and cumulative additions/removals in the same side panel. Missing receipt deltas remain unavailable.
- Fixed ATM plus three OTM contracts per side, option premiums, OI/volume flows, inventory, recorded events, replay steps and speed controls.
- Independent data and summary workers. Summary messages contain only a small current snapshot; chart histories are not cloned into summary requests.
- V2 context shows native short/broader price legs, fixed ATM, five-minute changes, basket totals/flows and input completeness separately from the reference call.

## Replay and live status

The [two-core deployment](../market-core-v3/DEPLOYMENT.md) supports Live and Replay for both instruments. Each GUI reads `/workspace-config.json`, exposes its two permitted version profiles, and polls its own core through a read-only proxy. The data worker fetches health and cached publications sequentially, retries failures, and cancels obsolete requests. Switching to replay reads saved publications while the core continues live ingestion. GUI restarts do not restart a core.

A static Vite build without that gateway continues to offer file/catalog replay. The earlier hosted static preview does not acquire live connectivity automatically. Live mode requires the accompanying backend deployment and running collectors.

Native call/context timestamps and separate price, OI and cash/VIX receipt clocks are preserved. Feed age and core/context errors are visible. New-day metadata waiting clears the previous live session. Market Summary uses an independent worker and remains bound to the snapshot requested. No order placement is implemented.

## Verification

```sh
npm test
npm run build
node scripts/verify-session.mjs nifty-v200 /path/to/imported-session.json.gz
```

Tests use small synthetic contracts that are never served as market data. They exercise all four profiles, wrong-instrument rejection, delayed publications, missing VIX, cumulative reconciliation, retained VPOC gaps, independent summaries, obsolete worker loads and the read-only exporter. Private recordings can be checked separately with `verify-session.mjs`; none are required by CI.

See [DATA_CONTRACT.md](DATA_CONTRACT.md) for adapter semantics and [SOURCE_LINEAGE.md](SOURCE_LINEAGE.md) for the reviewed source packages.
