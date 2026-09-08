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

## Shared live runtime

The V3 core emits these same contracts over a read-only cached transport. Both versions receive the same authority's chart inputs; the V2 decisions remain native. Prior-context rows may include `available_at`, which the GUI respects when replaying a later first publication. `live.server_time` describes transport availability and never replaces a source or call clock. See [API.md](../market-core-v3/API.md).
