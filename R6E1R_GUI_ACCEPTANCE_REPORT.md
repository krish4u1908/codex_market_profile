# R6E1R GUI Acceptance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT LOCAL API/FUNCTIONAL EVIDENCE PASSED; CURRENT BROWSER AND EXTERNAL LIVE ACCEPTANCE PENDING**

The intended GUI contract follows the verified R6D visual model while adding operational availability and receipt-age state. The browser must render server-published analytical rows; it may select, sort, filter, and draw them, but it must not recompute detector, inventory, lifecycle, participation, or cross-layer analytics.

## Current local evidence boundary

| Evidence | Result | What it proves |
|---|---|---|
| Current API suite | 39/39 passed | Current server/API projection behavior |
| Pre-final-repair selected functional baseline | 416 passed; 5 host-only tests deliberately deselected | Historical selected non-browser behavior; current Hostinger browser run remains mandatory |
| Gateway security | 13/13 passed | Current sanitized gateway behavior, including hidden-path validation and redirect refusal |
| Current Playwright/Chromium run | Not available locally | Nothing about current visual rendering; Hostinger run required |
| External live service | Not deployed by this handoff | External GUI acceptance remains pending |

Python Playwright/Chromium is absent in the local environment. Therefore, every browser-visible requirement below remains pending even where non-browser unit/API coverage passed.

## Required GUI contract

### Content

- Separate BankNifty Index and Futures multi-point paths.
- Synchronized Basis.
- 3D, 2D, 1D, and Intraday Price/OI VPOC.
- Divergence segments and confirmation/lifecycle markers.
- Lifecycle badge separate from line colour.
- Futures, CE, and PE participation context.
- Receipt ages, stale warnings, and per-layer availability reasons.
- Classification displayed as `LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL`.

### Category controls

- A master checkbox appears immediately before 3D, 2D, 1D, and Intraday.
- Disabling a master hides all category children without erasing individual selections.
- Re-enabling restores saved child selections.
- A 1D-only selection renders only selected 1D children.
- Intraday-only renders Intraday without fixed-horizon graph controls or lines.
- Selection state persists across replay movement, polling, refresh, and return to latest.

### Graceful degradation

| Missing/stale layer | Required behavior | Current browser standing |
|---|---|---|
| 3D | Continue 2D, 1D, and Intraday; show reason | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| 2D | Continue 1D and Intraday; show reason | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| All fixed horizons | Continue Intraday when available | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Stale Index or Futures | Suspend divergence as `STALE_DATA`; retain last chart with warning | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Missing/stale options | Suspend only affected participation layer | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Missing CE/PE | Do not block Index/Futures chart | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |

Live events must never be labelled `SUCCESS` or `FAILURE`.

## Historical visual evidence

The following fixtures were recorded at earlier pushed head `4d160bcc61bcebd88135ce270c17926830022deb`. They remain useful historical references, but they are not current-source browser evidence or external-live proof.

| Historical scenario | File | Dimensions | Historical SHA-256 |
|---|---|---:|---|
| Complete fixed horizons | `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `f7676c44a6fa49d2822c3285705abf8749f9675196429ab02e229e53fa976bae` |
| Intraday-only degradation | `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `250ba99fd8f473d428b6069459ed7874423aa2d1d19faf1177a2e7f3783ea005` |
| Fixture/latest operational | `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `ebb0c7b2afb7e8ea6e6461a733b3b1534822270c870a0cff73a8c917e2ab3b6c` |

At GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, the R6D-parity engine/GUI/API/browser suite passed 135/135 and recorded zero console/page errors. Later source and package changes mean that result is historical only.

## Final acceptance gate

Hostinger must run current-source Chromium/Playwright coverage, visually inspect complete fixed-horizon, Intraday-only, and live/latest scenarios, verify toggle persistence and graceful degradation, observe zero console/page errors, measure the largest sanitized chart response below the 8 MiB gateway cap, and repeat the operational checks against the isolated deployed URL.

`GUI_ACCEPTANCE: PENDING_HOSTINGER_BROWSER_AND_EXTERNAL_LIVE_EVIDENCE`

Detailed pending browser cases are listed in [R6E1R_BROWSER_TEST_REPORT.md](R6E1R_BROWSER_TEST_REPORT.md).
