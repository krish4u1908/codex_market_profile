# Near-OTM OI entry bubbles — GUI 3.0.6

V2 pages for NIFTY and BANKNIFTY show small translucent circles immediately
above the price/basis/VIX ribbon. Green means the proposed long-entry condition
passed; red means the proposed short-entry condition passed. Fill opacity is
22%, with a more visible 72% outline. The ribbon, VPOC lines and climax markers
remain visible. These are research annotations, not order instructions or
changes to the existing reference calls.

## Frozen first test rule

Policy: `NEAR_OTM_OI_ENTRY_V1`. Settings are starting hypotheses, not optimized
parameters or evidence of profitability.

| Requirement | Long | Short |
| --- | --- | --- |
| Contracts | Three nearest strictly OTM PEs | Three nearest strictly OTM CEs |
| Expiry | Already-selected session expiry | Already-selected session expiry |
| OI trigger | At least one strike falls ≥1% in one fresh OI report, and ≥3× its recent normal change | Same rule, independently per CE |
| Normal change | Median absolute percentage change across the preceding 20 valid OI updates, excluding the current update | Same |
| Recent setup | VIX five-minute return ≥+0.4%, with that PE's five-minute premium return >0 | VIX five-minute return of either sign with absolute size ≥0.4%, with that CE's five-minute premium return >0 |
| Setup age | Setup was available within the preceding three elapsed minutes | Same |
| Broader trend | Latest published V2 `broader_leg = +1` | Latest published V2 `broader_leg = -1` |
| Cash filter | Complete configured cash basket above its session open | Complete configured cash basket below its session open |
| VPOC filter | Index strictly above published intraday canonical futures-volume VPOC | Index strictly below that VPOC |

The short VIX sign has not been established by this research. This first version
explicitly accepts either sign and retains the actual percentage in the tooltip.
It does not assume a compulsory mirror of the long-side VIX direction.
The cash filter uses the collector's configured basket, not an assertion of
coverage of every NIFTY 50 constituent. The existing V2 broader price leg is
used instead of creating another trend engine. A pullback can coexist with an
UP broader leg; the short-term reference call is not an entry prerequisite.

For each contract, with report index `n`:

```text
drop_pct[n] = 100 * (OI[n-1] - OI[n]) / OI[n-1]
normal_pct = median(abs(drop_pct[n-20]), ..., abs(drop_pct[n-1]))
spike = drop_pct[n] >= 1 AND drop_pct[n] / normal_pct >= 3
```

The baseline needs 21 preceding OI observations plus the current observation.
Warm-up starts with retained reports from 09:15; entries begin no earlier than
09:45 and the actual expiry-selection publication. The overlay runs through
15:30, as do the existing ribbons; it does not impose a separate trade cutoff.
Missing/null retained OI deltas, inconsistent changes, gaps over 90 seconds,
and zero baselines suppress a spike. Repeated report identities are counted
once. GUI redraws and price ticks are not new OI reports. A reported change may
represent exchange/provider batching; no exact underlying transaction time is
inferred from it.

At every OI report, derive the three strike-grid positions below spot for PE,
or above spot for CE. Exact ATM and ITM strikes are excluded. A missing nearest
strike is not replaced with a farther one. Compare each contract only with its
own strike/expiry history. The existing fixed 09:45 option basket is unchanged.

## Timing and display

- A bubble is placed at the qualifying OI report's receipt/availability time.
  It is not moved back to the VIX surge or to a completed candle's start.
- The current GUI's VIX marks use six consecutive completed-minute closes,
  five elapsed minutes apart. Only a mark already available at the OI report
  can arm a setup. Intraminute highs from a later OHLC export cannot substitute
  for known ticks. The separate near-real-time preview is not changed.
- The PE/CE premium endpoints are the last available receipts at or before
  the VIX observation time and five minutes earlier. Both must be fresh within
  90 seconds, with continuous premium history. Premium rises learned only
  after the VIX observation cannot arm an earlier setup.
- V2 context must be published within 90 seconds and its input cutoff within
  120 seconds. Price receipt and synchronization ages are checked in
  milliseconds against 15 seconds. Cash source-minute age is at most 120
  seconds and the complete configured basket is required.
- The VPOC is the current published `volume_cumulative_mode_canonical`, never
  a final-session profile or a chosen prior-day chart overlay. Changing visible
  chart lines does not change the tested entry rule.
- Multiple qualifying strikes in one OI report share one bubble per direction.
  Hover/tap lists their OI changes, ratios, premium/VIX changes, market filters
  and timestamps. Separate qualifying reports remain separate observations;
  these counts are not counts of independent trades.
- `Entry bubbles` toggles visibility. `Review OI-spike reports` shows accepted
  and filtered reports and the reason for each rejection. Clicking a report
  time seeks replay to that receipt. Entry bubbles also appear in the Events
  tab and the existing next/previous-event navigation.
- Backward seeking hides events whose reports had not arrived. Live and replay
  share the same worker calculation; later corrections never create earlier
  bubbles. Summary work remains independent.

## Reproduce 11 September NIFTY

Open the NIFTY GUI on port **8921**, choose **V2.0.0 → Replay**, then use
**Open session** to load `nifty-v200-2026-09-11-entry-replay.json.gz` supplied
with this update. This combines the user's original session and indicator feed
without changing either source's availability timestamps. The file stays
outside the GitHub repository and the installed application assets.

With the rule above, the supplied session has **four LONG bubbles and zero
SHORT bubbles**, from **71 OI-spike report/side assessments**:

| OI receipt time, IST | Qualifying PEs |
| --- | --- |
| 14:46:55.247 | 23,350; 23,400 |
| 14:48:55.241 | 23,350 |
| 14:49:55.112 | 23,350; 23,400 |
| 14:55:55.121 | 23,350 |

1. Seek to **14:46:54**: there is no green bubble yet.
2. Seek to **14:46:56**: the first green bubble appears above the ribbon.
3. Seek backward to **14:46:54**: it disappears.
4. Seek to **15:00:00**: all four are visible; hover or tap each circle.
5. Seek to **13:43:00** and expand the review. At **13:42:55.139**, PE 23,300,
   23,250 and 23,200 satisfy the OI and recent VIX/premium tests. The available
   index is **23,331.80**, below volume VPOC **23,350**, so the long bubble is
   filtered. The earlier illustrated 23,500 PE is ITM and is excluded.

This audit establishes rule reproduction and availability timing, not trading
performance. The four accepted observations occur after 14:45; no earlier
entries are manufactured to match the hand-marked examples.

Automated reproduction from the source workspace:

```bash
node scripts/audit-entry-replay.mjs \
  --input /path/to/nifty-vix-live.json \
  --indicator-inputs /path/to/nifty-indicator-inputs.json \
  --profile nifty-v200 \
  --output /tmp/nifty-entry-replay-audit.json
```

The audit verifies full-history frames against inputs truncated at ten replay
checkpoints, including immediately before and at every bubble, and verifies
backward seeking and live/replay annotation parity. Outputs remain local.

NIFTY and BANKNIFTY long/short behavior is covered by synthetic, clearly labeled
contract tests. The supplied September 7 BANKNIFTY export has no individual
strike OI histories or selected expiry, so it cannot verify historical entry
bubbles; it correctly produces none. Use a newer full BANKNIFTY V2 export for
that instrument's market-data replay verification.

## Install

Use the GUI-only procedure in [GUI_UPDATE.md](../market-core-v3/GUI_UPDATE.md).
The package restarts only the two GUI services and verifies unchanged core
PIDs. Expected `/gui-release.json`: `3.0.6-gui-oi-entry-bubbles` with
`entryBubblePolicy: NEAR_OTM_OI_ENTRY_V1`. No VPS deployment is performed by
the source build or replay checks.
