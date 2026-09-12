**Reproduce the NIFTY bullish-context study**

This offline study tests whether an independently measured upward price context improves the existing green PE-OI-fall / VIX-rise bubble. The runtime GUI and bubble detector do not import the context module or outcome scripts.

The complete frozen choices are in `bullish-context-protocol.json`. For signal slot t, set s = t − 5. Signed efficiency is the net price change from s − 30 through s divided by the sum of the 30 absolute one-slot changes. The reference average covers prices s − 29 through s. A bullish classification requires efficiency ≥0.30 and both the price at s and the signal price above that reference average. A valid input needs all 36 minute slots and ordered positive prices with receipt gaps no greater than 90 seconds. Flat or invalid histories do not become bullish.

The price grid is the option-report spot quote sampled near second 55. It is not the cash one-minute close series. Both the classifier and the bubble detector use collector receipt times. Context ends before the five-slot event window, apart from the explicit check that the signal price still holds above the earlier average. VIX and OI are not used to manufacture the price-context classification.

The efficiency-ratio idea is described in [StockCharts' indicator documentation](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama). The sign, 30-minute horizon and 0.30 threshold are analyst research choices, not optimized or published optimal parameters.

**Run from the repository root**

Requires Node.js with its built-in test runner and Python 3. The preparer and verifier use Python's standard library. Supply the collector archive through `--archive`; the scripts do not read services or contact the broker.

```bash
study_dir=$(mktemp -d -t nifty-bull-context-XXXXXX)

python3 apps/market-core-v3/scripts/prepare_bubble_research.py \
  --archive '/path/to/minute(1).zip' \
  --output "$study_dir/inputs"

node --test apps/market-workspace-v3/tests/bullish-context.test.mjs

node apps/market-workspace-v3/scripts/analyze-bullish-context.mjs \
  --inputs "$study_dir/inputs" \
  --output "$study_dir/results"

python3 apps/market-workspace-v3/scripts/verify-bullish-context.py \
  --archive '/path/to/minute(1).zip' \
  --inputs "$study_dir/inputs" \
  --results "$study_dir/results"
```

The supplied historical archive SHA-256 was `11ccc397cab162a869422cc656470c8de5eab60b18eb961b8e8f2ba5270df79a`. Its 15 sessions span 24 August through 11 September 2026. A differently named byte-identical archive yields the same calculated outcomes, with a different recorded source filename. Prepared-file hashes depend on JSON serialization; the archive and raw-member hashes identify the underlying source independently.

**Recorded result**

There were 151 green bubbles. Eighteen late-session signals, one insufficient warm-up and 126 non-bullish contexts left six qualifying bubbles. A predeclared 15-minute cooldown left four episodes across three sessions. They occurred on 25 August at 14:00:55.216 and 15:03:55.082, 31 August at 14:47:55.212, and 1 September at 11:31:55.159, all IST. Neither 10 nor 11 September had a qualifying context under this rule.

Mean subsequent NIFTY changes were −2.54 points at five minutes (n=4), −2.13 at ten minutes (n=4) and −10.02 at fifteen minutes (n=3). The fourth fifteen-minute endpoint crosses the closing-auction boundary and is retained but excluded from the primary calculation.

The nearest strict OTM CE test, next-minute LTP-open entry with a 20-premium-point stop and target, produced zero targets, two stops, one feed-gap censor and one skipped premium ≤20. Gross resolved sum was −40 points, excluding costs and the unresolved observation. This is not a portfolio return. The frozen 0.20 and 0.40 sensitivity thresholds produced seven and one episodes respectively; neither supplied convincing contrary evidence.

The comparison matches controls by session, IST clock hour and sign of the current five-minute price movement. It averages all eligible controls within a case's stratum and gives each case equal weight. Relative to bullish VIX-rise periods without a PE OI spike, average case-minus-control differences were +0.15, −0.75 and −2.34 NIFTY points at 5/10/15 minutes. All four cases matched, using six distinct controls. The three sessions with cases are too few for a dependable effect estimate; bootstrap intervals are exploratory. None of the last five sessions had a selected case. That chronological slice is not an untouched holdout, since the archive was examined in the earlier study.

Primary signal times and index endpoints must precede 15:15 IST; the [NSE CAS schedule](https://www.nseindia.com/static/products-services/closing-auction-session) motivates keeping the transition separate. Option outcomes may continue until their barrier, first invalid/gap bar or the 15:40 derivative-session boundary, consistent with the original evaluator. Intrabar barrier order is not guessed if both are touched; stop gaps retain the worse open. Low premiums are not replaced by another strike after seeing outcomes.

**Outputs and verification**

- `summary.json`: protocol, hashes, selections, control comparisons, sensitivity, daily and chronological summaries.
- `observations.json` / `all-observations.csv`: context and CE outcomes for every eligible price observation, plus early green bubbles.
- `green-bubbles.json` / `green-bubble-timestamps.csv`: every original green bubble, with context and episode selection.
- `primary-episode-timestamps.csv`: the four main cases.
- `matched-controls.json`: exact case/control membership and per-horizon comparisons.
- `verification.json`: causal prefix checks.
- `raw-verification.json`: independent Python Decimal reconciliation to the original option reports and option OHLC CSV.

The recorded run passed six focused tests, 5,625 context-prefix checks, 5,625 raw-report checks, 5,101 context/eligibility checks, 14,853 available horizon arithmetic checks, 5,101 raw CE-bar outcome checks and eight control-stratum checks. Original green-bubble eligibility remained 151. No parameter was changed in response to these results. This supports retaining the definition as a research candidate; it does not establish a trading edge or validate broader daily bullish context.
