# Basic near-OTM OI / VIX bubbles — 3.0.8

This replaces the older gated entry setup. The four user-selected combinations
are displayed for NIFTY and BANKNIFTY V2.0.0. Colours express VIX direction;
they are condition markers, not a generated trade recommendation.

| OI-fall side | Location | VIX rises ≥0.4% | VIX falls ≥0.4% |
| --- | --- | --- | --- |
| PE | Above the price/basis ribbon | Transparent red | Transparent green |
| CE | Below the price/basis ribbon | Transparent red | Transparent green |

## Exact rule

At each successful option-chain report, select the three nearest **strict OTM**
strikes for each side from that report's underlying index quote. NIFTY uses
50-point spacing; BANKNIFTY uses 100. ATM is excluded at exact strike equality.
A symbol is compared only within the same expiry and session.

For consecutive report totals `OI[t-1]` and `OI[t]`:

```text
fall_pct = 100 × (OI[t-1] − OI[t]) / OI[t-1]
normal_pct = median(abs(previous 20 report-to-report percentage changes))
OI spike = fall_pct ≥ 1 AND normal_pct > 0 AND fall_pct / normal_pct ≥ 3
VIX_pct = 100 × (VIX[current report] − VIX[report 5 minute slots earlier])
                / VIX[report 5 minute slots earlier]
bubble = any of the 3 near-OTM strikes has an OI spike AND abs(VIX_pct) ≥ 0.4
```

The current OI change is excluded from the baseline. This needs 22 OI totals.
Positive OI and continuous report history are required; gaps over 90 seconds
invalidate the affected baseline. Zero normal movement does not imply an
infinite spike ratio. Report totals are used, not provider `oich`/`prev_oi`.

VIX comes from `response.data.indiavixData.ltp` in the **same option-chain
report**, against five minute slots earlier. All six minute slots must have
valid quotes and consecutive gaps no larger than 90 seconds. If multiple
reports occur within a minute, the latest already-seen quote in each baseline
slot is used. This avoids millisecond receipt jitter selecting six minutes ago.

Screening runs 09:45–15:30 IST, with baseline history from 09:15. No trend,
cash, price/basis, premium, VPOC, prior-VIX grace period or day-high gate applies.
Adjacent matching reports each remain visible. Several qualifying strikes on
one side share one bubble. PE and CE at the same instant occupy separate lanes.

## Timing and data

Core 3.0.2 reads existing `collector_root/oi/YYYY-MM-DD/oi_*.jsonl` files through
a bounded background reader. This adds no service, broker subscription or
strategy engine. The native v1.0.62/V2 decision code, volume climaxes and the
completed-minute VIX chart/ribbon are unchanged.

New V2 payloads include `option_report_inputs` with schema
`OPTION_REPORT_INPUTS_V1`. The GUI asynchronously requests that feed for older
server-catalog replays. The price and other panes remain available during the
archive read. Missing or unverifiable raw quotes produce a visible status,
not fabricated bubbles. Imported local files must include the matching feed;
they are never silently combined with a server's unrelated session.

Bubbles are anchored at the collector's `received_at`, including milliseconds.
Replay reveals them only when the cursor reaches that receipt. Historical
reconstruction does not prove the old live GUI displayed them at that instant.
Live appearance follows the existing collector and core polling cadence;
this update does not introduce tick-speed OI or change the separate real-time
preview deployment.

The VIX line/vertical ribbon marks still use completed-minute closes. Therefore
their marks can differ from the report-quote bubble screen. Hover a bubble for
its two VIX quotes, exact interval, strike, OI fall and spike ratio.

## Recorded-session verification

The production calculation was checked against all 15 supplied NIFTY sessions:
472 matching report/side events. Every match was checked on prefixes ending just
before and exactly at its receipt (944 prefix checks). No date or timestamp is
encoded in the production condition.

| Session | PE red | PE green | CE red | CE green | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-09-10 | 4 | 2 | 0 | 6 | 12 |
| 2026-09-11 | 2 | 6 | 1 | 11 | 20 |

These reproduce the user-approved timestamps exactly. Simultaneous PE/CE count
as two markers. Real BANKNIFTY report archives were not supplied for this audit;
the same rule, contract identity and placement are tested with synthetic data.

For a local audit without modifying the original replay:

```bash
node scripts/audit-entry-replay.mjs --input SESSION.json --profile nifty-v200 --option-reports REPORTS.json --output audit.json
```

## Installation

Use the full 3.0.8 update bundle and `core/deploy/update_data.py`, as explained
in `apps/market-core-v3/DATA_UPDATE.md`. This updates core 3.0.2 and GUI 3.0.8
on the existing four services. A GUI-only update is valid only after core
3.0.2 is already installed; the GUI updater checks that requirement.
