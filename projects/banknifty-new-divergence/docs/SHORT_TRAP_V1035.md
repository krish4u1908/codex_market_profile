# V1.0.35 causal short-trap detector

## Decision contract

V1.0.35 separates an observed volume/short-buildup event from a directional
reversal signal.

| Stage | Required evidence | Direction |
|---|---|---|
| Volume climax | Visible current-minute incremental Futures volume is at least 2.5 times the unrounded mean of the exact five preceding complete minutes | None |
| Candidate | Volume climax, five-minute Futures price change below zero, and Futures OI increase of at least 1.5% | `NO_EDGE` |
| Confirmation | A later market minute reclaims at least 15 Futures points from the probe low, Futures OI falls from the candidate value, basis improves, and Bank Nifty reclaims the visible PE positive-OI control by 5 points | `UP` |
| Expiry | Confirmation is absent five minutes after the candidate | `NO_EDGE` |

The 1.5% OI and 15/5-point reclaim constants came from the supplied strategy
and existing runtime margins. They are configuration hypotheses, not optimized
edge estimates. They must be evaluated out of sample before production use.

## Volume gate

The current minute is excluded from its own baseline. The comparison is
inclusive and unrounded:

`current_visible_minute_volume >= 2.5 * mean(previous five complete minute volumes)`

All five baseline minutes must be contiguous, complete, and positive. A
missing minute, counter reset, excessive receipt gap, missing value, or absent
synchronized Index observation makes the affected comparison ineligible.

The detector records the exact receipt at which the visible cumulative minute
delta first crosses the threshold. It does not wait for or use future receipts.

## Timing and deduplication

- `first_climax_receipt_utc/ist`: causal volume-threshold crossing receipt.
- `candidate_identified_receipt_utc/ist`: same causal candidate receipt.
- `signal_available_receipt_utc/ist`: first later-minute receipt satisfying all
  confirmation rules; never copied from the climax minute.
- `climax_to_signal_gap_seconds`: receipt-to-receipt latency.
- Repeated climax minutes remain one episode until two consecutive eligible
  minutes fall below 1.5x or the five-minute episode expires.

Option OI is retained as an inventory control only. The code does not label CE
or PE OI changes as buying or writing because OI alone cannot identify the
aggressor or trade direction.

## Scenario names

- `SHORT_TRAP_CANDIDATE`, `NO_EDGE`, `OBSERVING` or `EXPIRED`
- `CONFIRMED_SHORT_TRAP`, `UP`, `CONFIRMED`

The legacy same-freeze `SHORT_TRAP` route is removed. Scenario output is a
research classification, not an order instruction.
