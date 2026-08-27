# R6E1R GUI Acceptance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FIXTURE GUI PASS — EXTERNAL DEPLOYED-LIVE ACCEPTANCE PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

The intended GUI contract follows the verified R6D visual model while adding operational availability and receipt-age state. The browser must render server-published analytical rows; it may select, sort, filter, and draw them, but it must not recompute detector, inventory, lifecycle, participation, or cross-layer analytics.

## Current regression and fixture evidence

| Evidence | Result | What it proves |
|---|---|---|
| Complete repository regression | 636/636, zero failed/skipped | Current API, GUI, gateway, host-only, and fixture-browser regression |
| Current Playwright/Chromium fixture | 1/1 in 4.86 s; zero console/page errors | Current synthetic rendering, replay/control persistence, and screenshots |
| External live service | Not deployed by this handoff | External GUI acceptance remains pending |

The current fixture-browser result is accepted for its synthetic scenarios. It
does not establish that a service is installed, publicly reachable, or healthy.

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

| Missing/stale layer | Required behavior | Current suite standing |
|---|---|---|
| 3D | Continue 2D, 1D, and Intraday; show reason | CURRENT SUITE PASS; deployed-live pending |
| 2D | Continue 1D and Intraday; show reason | CURRENT SUITE PASS; deployed-live pending |
| All fixed horizons | Continue Intraday when available | CURRENT FIXTURE PASS; deployed-live pending |
| Stale Index or Futures | Suspend divergence as `STALE_DATA`; retain last chart with warning | CURRENT SUITE PASS; deployed-live pending |
| Missing/stale options | Suspend only affected participation layer | CURRENT SUITE PASS; deployed-live pending |
| Missing CE/PE | Do not block Index/Futures chart | CURRENT SUITE PASS; deployed-live pending |

Live events must never be labelled `SUCCESS` or `FAILURE`.

## Current fixture visual evidence

The complete current regression regenerated the following fixtures. They are
current-source fixture evidence, not external-live proof.

| Current fixture scenario | File | Dimensions | Current SHA-256 |
|---|---|---:|---|
| Complete fixed horizons | `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `532c09190f817ddf697445b3a7351220f3be0d5c19083978ea35065a083a4fdc` |
| Intraday-only degradation | `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `307e33736bd9f9c68c4f6d99fd30a76d5a411352d0b633795f8957db90bb772c` |
| Fixture/latest operational | `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `a5e75f678a90ef67567222d2ed87d0bf57aad0d3a197f1b58371ecdaabdec3c2` |

Focused merged-v2 was stopped and rejected after its clean-B GUI builder
projected 11,486 dense resolution observations instead of the live GUI's 1,294
material transitions; full-six-v1 shared the same comparator and was also
stopped. The independently reviewed `c42e703...` repair changes only the clean
comparator. Focused-v3 and full-six-v2 have been running from that pinned commit
since 2026-08-27 15:03:13 IST, so their GUI A/B equality remains pending.

At GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, the R6D-parity engine/GUI/API/browser suite passed 135/135 and recorded zero console/page errors. Later source and package changes mean that result is historical only.

## Final acceptance gate

The current fixture coverage and screenshots pass. Final GUI acceptance still
requires actual response-size measurement plus repetition of the operational
checks against the isolated deployed URL.

`GUI_ACCEPTANCE: FIXTURE_PASS_EXTERNAL_LIVE_PENDING`

Detailed pending browser cases are listed in [R6E1R_BROWSER_TEST_REPORT.md](R6E1R_BROWSER_TEST_REPORT.md).
