# OI/VIX bubble outcome experiment

This is a retrospective description of the supplied NIFTY recordings. Detection
uses `BASIC_OTM_OI_VIX_V2` unchanged across dates. No outcome selects a threshold,
strike, bubble colour, VPOC level or live core call.

## Five, ten and fifteen minutes

The starting price is the NIFTY spot quote in the signal's option-chain report.
The endpoint is the report in the minute slot 5, 10 or 15 slots later. The output
records both receipt times and actual elapsed seconds, so subsecond polling
jitter is visible. Every intervening slot must be present, with positive spot
quotes and report gaps no larger than 90 seconds. Missing endpoints are missing
outcomes, not flat prices. No forward filling is applied.

Index change is endpoint minus starting quote. Positive means the index rose,
regardless of bubble colour. Direction-adjusted points reverse that sign for a
red short-watch event. Yellow has no assigned expected direction. Sampled maximum
up/down values use report quotes; they are not tick-level high/low excursions.

The report quotes end at 15:29. Consequently late bubbles do not all have 5/10/15
minute observations. The cash auction period begins at 15:15; index quotes there
may be indicative auction values. Results identify continuous-session,
auction-period and cross-boundary windows separately.

## Twenty-point option target and stop

For each green event buy the nearest strict OTM CE; for each red event buy the
nearest strict OTM PE. For each yellow event test CE and PE as two separate
research scenarios. Choose the contract from the signal report, using its spot
and expiry; keep that exact symbol throughout the observation. Do not switch
strikes as the underlying moves. This trade contract may differ from the option
whose OI triggered the bubble.

The entry proxy is the next minute's LTP open, after the OI report was received.
For example a signal at 11:15:55 enters at the 11:16 candle open. Actual browser
processing latency and order execution are not reconstructed. Bid/ask spread,
fees, taxes and slippage are not included. These are premium **points**, not
percentages, index points or rupees per lot.

```text
long premium target = entry + 20
long premium stop = entry - 20
```

Entry requires a valid OHLC candle, quote events and positive minute volume.
An opening premium at or below 20 cannot support a positive 20-point stop, so
that experiment is marked not entered. No alternative contract is substituted.

Track subsequent one-minute OHLC candles through the available recording,
excluding rows at or after 15:40 IST. There is no 5/10/15-minute exit for this
test. A candle whose high reaches the target or low reaches the stop resolves
the test. Barrier prices are rounded to two decimals to preserve exact touches.
If both are touched in one candle and its open does not already resolve a gap,
retain `AMBIGUOUS_BOTH`; never infer the intrabar path. A gap through the stop
uses the opening price, so loss can exceed 20. A gap above target conservatively
credits only 20. Exact exit seconds are unavailable; the exit minute is retained.

Missing candles, collector gap flags, timestamp anomalies or invalid OHLC
censor an open observation before evaluating later price touches. Positions
still open when the available session data ends remain unresolved, with their
last observed mark retained separately. Neither class is counted as a win or
loss. No overnight continuation or automatic end-of-day exit is assumed.

## Interpretation and reproducibility

Every qualifying report is an independent event study. Consecutive signals and
simultaneous PE/CE signals remain separate, so observations and hypothetical
trades can overlap. Summed points are not a one-position trading strategy or a
portfolio equity curve. The decided win rate excludes unresolved, censored,
ambiguous and not-entered experiments; all their counts must accompany it.

The 15 dates are an exploratory historical sample, including dates used in the
original discussion. They are not an untouched holdout. No confidence or
profitability claim follows from successful software verification.

From the repository root:

```bash
python3 apps/market-core-v3/scripts/prepare_bubble_research.py --archive /path/to/minute.zip --output /tmp/bubble-inputs
node apps/market-workspace-v3/scripts/analyze-bubble-outcomes.mjs --inputs /tmp/bubble-inputs --output /tmp/bubble-results
```

The preparation is read-only and records the archive and member SHA-256 hashes.
The analysis imports the actual GUI detector, verifies prefixes ending before
and at every event, and writes event/horizon/trade ledgers plus aggregate JSON.
The scripts run independently of the two existing market cores and GUI services.
Recordings and generated ledgers are excluded from GitHub and deployment assets.
