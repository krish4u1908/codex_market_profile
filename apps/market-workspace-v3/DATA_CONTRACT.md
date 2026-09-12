# Adapter contract

`public/profiles.mjs` owns instrument and engine-version identities. The UI consumes one normalized frame. `public/payload-adapters.mjs` has two explicit source adapters; it never re-scores a call or derives a new VPOC.

| Input | v1.0.62 | v2.0.0 |
| --- | --- | --- |
| Session identity | `schema: NEW_DIVERGENCE_BROWSER_PAYLOAD_V1`, `session` | `version: 2.0.0`, `baseline_version: 1.0.62`, `session`, `decisions` |
| Calls | `directional_prediction` packed fields/rows or array | `decisions[].baseline_call`; fallback projection of `corrected_direction` and `corrected_score` |
| Availability | Call `published_at`, otherwise `t` | Later of enclosing context publication and embedded call publication |
| Price/basis | Synchronized `price` receipts | Own `chart_inputs.price`, otherwise `price_history` minute snapshots |
| Futures OI | `futures_oi` original receipts | Own original receipts when supplied; otherwise retained minute totals without cumulative deltas |
| Options | `option_strike_oi` with retained fixed selection | Own `chart_inputs.option_strike_oi`, otherwise native basket aggregates |
| Intraday levels | `intraday_inventory` | Own V2 input inventory or the levels retained in native V2 context publications |
| Prior levels | Frozen `inventory_context.controls` | Only when supplied by V2's own inputs; never borrowed from v1 |
| VIX/cash | Retained `cash_vix` rows | Own retained rows or native context/chart values at their availability time |

Every emitted frame is bounded by the replay cursor. First observation, selection time, price receipt time, cash/VIX observation time and call publication time are separate clocks. Sparse VPOC publications persist until updated or explicitly unavailable. Tick-series gaps remain gaps.

V2 `chart_history` is presentation-only reconstructed history. It cannot supply earlier reference calls or backdate VPOC publications. Reconstructed cash/VIX rows honor `cash_first_observed_at` and `cash_publication` when present; a source minute by itself does not establish earlier availability. History provenance remains visible. This is historical replay, not evidence that a later reconstruction was available live.

The adapter does not populate absent confidence, state, horizon, drivers or invalidation text. Embedded calls keep all their original fields. The added `x` field is the GUI availability timestamp in epoch milliseconds. Original timestamp strings remain unchanged.

## Optional V2 chart input envelope

An enriched V2 session keeps its native fields and adds:

```json
{
  "workspace_profile": "nifty-v200",
  "version": "2.0.0",
  "baseline_version": "1.0.62",
  "instrument": "NIFTY",
  "session": "YYYY-MM-DD",
  "decisions": [],
  "price_history": [],
  "chart_inputs": {
    "session": "YYYY-MM-DD",
    "instrument": "NIFTY",
    "price": [],
    "futures_oi": [],
    "cash_vix": [],
    "option_strike_oi": [],
    "strike_selection": {},
    "intraday_inventory": [],
    "provenance": {"note": "Original inputs from this V2 engine"}
  }
}
```

Arrays contain the original receipt rows. The original packed `{fields, rows}` format is also supported. An option selection can live inside `option_strike_oi.strike_selection` or alongside it as `strike_selection`. A nonempty retained price series is required to render the session.

Cumulative +OI and −OI start from the first available receipt at or after 09:45. Its outstanding OI establishes the initial balance. Subsequent finite original deltas accumulate by symbol, expiry, side and strike; missing deltas mark partial coverage. Futures minute snapshots and five-minute basket windows are insufficient to establish those gross session flows. `total OI` always denotes outstanding OI, not the sum of the cumulative positive and negative bars.

Potential support/resistance labels select the highest visible PE OI below the index and CE OI above it, in the selected expiry and among the displayed nearby strikes. These are presentation labels for OI concentrations, not a new trading signal.

## Execution boundaries

- Main thread: responsive controls, chart painting and small summary request snapshots.
- Data worker: file fetching/decompression, instrument/version validation, presentation aggregation and cursor filtering.
- Summary worker: saved-call explanation for an immutable requested snapshot; independent of replay processing.
- Existing backend: ingestion, engine calculations, immutable publication and shared state. This GUI never starts it.

Profile changes remount the workspace and terminate old workers. Data loads use a generation counter and obsolete fetch cancellation. Message IDs prevent previous frame requests from replacing newer state. A failed summary leaves replay and other panes available.

## V2 volume-climax annotations

The display marks `futures_volume_ratio > 4` on the index chart and a dedicated volume-ratio pane. The supplied V2 engine defines this ratio as valid five-minute futures volume divided by the median of the previous four five-minute volume windows. The GUI uses the recorded number; it does not recalculate the ratio, change scoring or publish a new engine signal.

Markers use the native V2 context publication time, with the input cutoff available in the tooltip. Their index coordinate uses the context's retained index value, or the last price available at that publication time if the context omits it. A missing price leaves the ratio point available in the ratio pane without inventing a price coordinate. Reconstructed `chart_history` never creates a volume-climax event. Labels retain precision near the strict threshold so a qualifying point cannot be rounded down to `4.00×`. Crowded chart labels can be hidden to avoid collisions; the point tooltip and expandable list retain every ratio in the visible time range.

## Separately named CE/PE display research: CE_PE_CLIMAX_DISPLAY_V1

`public/v2-option-climax.mjs` annotates native V2 contexts for BANKNIFTY and NIFTY. It never changes a context, baseline call, inventory coordinate or VPOC. It produces six independent metric streams: CE volume, PE volume, CE OI additions, CE OI reductions, PE OI additions and PE OI reductions.

For each metric at input cutoff `t`, use the native amount in `(t−5m, t]`, divided by the median of the amounts published for `t−5m`, `t−10m`, `t−15m`, and `t−20m`. Those four contexts must already be available when the current context is published. The current amount never enters its own denominator. A missing exact cutoff or a zero median suppresses the point. Each context must belong to the same session, retain the same fixed ATM and have four-contract coverage for that side. If a retained basket selection timestamp is supplied, all five windows must start at or after selection. Without constituent identifiers in a legacy aggregate export, the check is limited to its retained fixed ATM and coverage metadata; identity/expiry cannot be recovered from aggregates.

Volume qualifies at `ratio >= 2.5`. OI additions and reductions qualify separately at `ratio >= 3` and `amount / starting_oi * 100 >= 0.5`, where `starting_oi = current_oi - net_oi_delta_5m`. OI additions and reductions must be finite and nonnegative and reconcile to the native net delta. A ratio spike does not by itself imply a price direction. These settings are display candidates from a single BANKNIFTY session, not revised production scoring thresholds or calibrated NIFTY settings.

Only the first native publication of an input cutoff is used. Reconstructed chart history cannot create points. A point is available at the normalized context publication clock (`x`); input cutoff is retained separately. The native index value supplies its price coordinate, with only the last already-available price as fallback. A missing price suppresses its chart symbol without inventing a coordinate. The replay cursor filters all annotations, including Live snapshots viewed in Replay. A late dependency does not retroactively add a point to an earlier publication.

The default chart shows the first qualifying publication of each per-metric burst. Qualifying cutoffs separated by at most five minutes share a burst; later peaks never move its first marker. The all-point control shows every qualifying publication. Coincident option metrics are grouped visually at their original time and price, with all values retained in their tooltip and event list. Futures use their existing native `>4` rule and red diamonds; the underlying futures ratio line remains amber.

## Price/basis ribbon: PRICE_BASIS_RIBBON_3M_V1

This named display revision applies to both instruments and both version profiles. It uses the existing synchronized `price` series (`i` for index and `b` for basis); it does not change native synchronization, scoring, calls or VPOCs.

At each available receipt time `t`, calculate net changes against the last same-session receipt at or before `t - 180 seconds`. The baseline may precede that cutoff by at most 60 seconds to accommodate minute snapshots and receipt jitter. Later receipts are never interpolated into the baseline. The tooltip exposes the cutoff and actual baseline receipt time. A negative index change with positive basis change is green; a positive index change with negative basis change is red. All other finite combinations, including either zero change, are neutral gray. The rule does not require a monotonic path within the three minutes.

Missing/nonfinite index or basis, or a consecutive receipt gap exceeding 90 seconds, breaks continuity. A complete new three-minute history is required after the break. Different IST session dates cannot supply a baseline. Initial warm-up and unavailable history remain blank. A stale final receipt loses its active colored status after 90 seconds, and the ribbon is never extended beyond receipt freshness or the current cursor.

The worker computes comparisons once per normalized snapshot. Each frame filters to available receipts, retaining all state transitions and the first/last receipt of each minute; a later minute close cannot move or erase an earlier color change or missing-data boundary. The main thread draws the ribbon under the main index price chart in the same panel, with identical horizontal bounds and linked zoom axes. Price, OI-VPOC and climax series retain their existing price axis; the ribbon has its own hidden band axis. The separate basis panel retains its basis line, and hiding it does not hide the price-chart ribbon. No ribbon history is added to summary-worker messages.

## Shared live runtime

The V3 core emits these same contracts over a read-only cached transport. Both versions receive the same authority's chart inputs; the V2 decisions remain native. Prior-context rows may include `available_at`, which the GUI respects when replaying a later first publication. `live.server_time` describes transport availability and never replaces a source or call clock. See [API.md](../market-core-v3/API.md).

## Versioned Cash/VIX indicator inputs

`CASH_VIX_INDICATOR_INPUTS_V1` is a separate input revision alongside the unchanged native reference inputs. Each source minute can have immutable revisions with `available_at`. The GUI selects the latest revision available at its knowledge cutoff and plots it at `minute_end`. Replay knowledge is the cursor; Live knowledge is the snapshot publication time. Late recovery therefore cannot enter an earlier replay frame. Missing source minutes and invalid readings remain explicit nulls. VIX validity is independent of cash completeness, and cash rolling display requires five exact valid source minutes. Nominal source coverage is 09:15–15:29 IST; a source shortage remains missing. New GUI quality counts refer to the displayed input history. Native reference calls, VPOCs and their retained input fields are not rewritten. The core exposes the same revision stream through `/api/indicator-inputs`; see the core data-update contract for indicator gating and historical export rules.

## VIX ribbon marks: VIX_RIBBON_5M_PCT_V1

GUI 3.0.5 adds translucent vertical marks to the existing price/basis ribbon for both instruments and both version views. A five-minute VIX percentage change of at least +0.4% is red; at most −0.4% is green. Smaller changes have no mark. The percentage uses the close five elapsed minutes earlier as its denominator and requires six consecutive finite, positive one-minute VIX closes. Cash completeness is independent.

Marks use actual observation availability on the x-axis. The worker processes revisions in arrival order; after-session repairs cannot create earlier intraday marks. Rewinding preserves the original observations. Repeated cash-only revisions cannot duplicate a VIX mark, and a batch produces one assessment for the latest eligible five-minute window. Hover/tap shows endpoint values, source-minute close times and availability. This display-only policy does not alter reference calls, indicators in the core, or the three-minute basis ribbon. Installation is described in [GUI_UPDATE.md](../market-core-v3/GUI_UPDATE.md).
## Near-OTM OI entry bubbles: NEAR_OTM_OI_ENTRY_V1

GUI 3.0.6 adds a separately named research overlay on V2 only, for both indices.
The complete rule, quality gates, short-side VIX assumption, receipt clocks and
replay audit are specified in [OI_ENTRY_REPLAY.md](OI_ENTRY_REPLAY.md).
The new worker calculation reads the full individual-strike ledger, including
pre-09:45 baseline reports, without changing the existing fixed-basket flows.
The full session is evaluated in receipt order; frames expose only entries and
filtered-spike assessments already available at the cursor. No new broker feed,
core service, native decision or order operation is added.
