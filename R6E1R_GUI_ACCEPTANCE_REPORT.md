# R6E1R GUI Acceptance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FIXTURE/REPLAY ACCEPTED; EXTERNAL LIVE ACCEPTANCE PENDING**

## Visual authority and content

The live GUI follows the verified R6D visual contract while adding operational availability and receipt-age state. It presents separate BankNifty Index and Futures paths, synchronized Basis, fixed and Intraday Price/OI VPOC, divergence segments, lifecycle markers/badge, Futures/CE/PE participation context, stale warnings, and per-layer availability.

No browser-side analytical detector, inventory, lifecycle, participation, or cross-layer computation is permitted. The browser only selects, sorts, filters, and renders server-published rows.

## Category control contract

- A master checkbox appears immediately before 3D, 2D, 1D, and Intraday.
- Disabling a master hides all category children without erasing their individual selections.
- Re-enabling restores the saved child selections.
- A 1D-only selection renders only selected 1D children.
- Intraday-only renders Intraday without fixed-horizon graph controls.
- Selection state persists across replay movement, polling, refresh, and return to latest.

## Graceful degradation contract

| Missing/stale layer | Required behavior | Final browser evidence |
|---|---|---|
| 3D | Continue 2D, 1D, Intraday; show reason | PASS — targeted fixture/API coverage |
| 2D | Continue 1D, Intraday; show reason | PASS — targeted fixture/API coverage |
| All fixed horizons | Continue Intraday when available | PASS — current Intraday-only fixture |
| Stale Index or Futures | Suspend divergence as `STALE_DATA`; retain last chart with warning | PASS — targeted fixture/API coverage |
| Missing/stale options | Suspend only affected participation layer | PASS — targeted fixture/API coverage |
| Missing CE/PE | Do not block Index/Futures chart | PASS — targeted fixture/API coverage |

Live events are never labelled `SUCCESS` or `FAILURE`.

## Screenshot inventory

The three current tracked fixture files exist at 1600 x 1915 pixels and are bound to pushed head `4d160bcc61bcebd88135ce270c17926830022deb`. The third image is fixture/latest operational evidence, not proof of an externally deployed live service.

| Scenario | File | Current tracked-fixture SHA-256 | External-live standing |
|---|---|---|---|
| Complete fixed horizons | `evidence/r6e1r/gui/complete_fixed_horizons.png` | `f7676c44a6fa49d2822c3285705abf8749f9675196429ab02e229e53fa976bae` | Fixture accepted |
| Intraday-only degradation | `evidence/r6e1r/gui/intraday_only_degradation.png` | `250ba99fd8f473d428b6069459ed7874423aa2d1d19faf1177a2e7f3783ea005` | Fixture accepted |
| Fixture/latest operational | `evidence/r6e1r/gui/live_latest_operational.png` | `ebb0c7b2afb7e8ea6e6461a733b3b1534822270c870a0cff73a8c917e2ab3b6c` | Deployed live/latest capture `PENDING_FINAL_EVIDENCE` |

## Test evidence

At pushed GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, the R6D-parity engine/GUI/API/browser targeted suite passed 135/135 tests. No tracked GUI/browser bytes have changed since that gate. The three current fixture screenshots were visually inspected, and the fixture browser run recorded zero console and page errors. The later repaired-engine targeted gate passed 216/216 for the current runtime path. External deployed-browser acceptance remains pending.

| Final check | Result |
|---|---|
| Current tracked GUI/browser bytes | PASS — 135/135 parity suite at their unchanged milestone bytes |
| Current runtime GUI/API integration path | PASS — later 216/216 repaired-engine suite plus focused GUI equality |
| Console errors | 0 — fixture browser run |
| Page errors | 0 — fixture browser run |
| Independent Index/Futures sorting | PASS — targeted path-clock and browser coverage |
| Toggle persistence across all transitions | PASS — polling, refresh, replay movement, and return-to-latest fixture coverage |
| External deployed browser check | `PENDING_FINAL_EVIDENCE` |

Detailed browser cases are listed in [R6E1R_BROWSER_TEST_REPORT.md](R6E1R_BROWSER_TEST_REPORT.md).
