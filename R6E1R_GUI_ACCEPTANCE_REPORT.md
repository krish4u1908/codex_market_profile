# R6E1R GUI Acceptance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR FIXTURE AND FRESH V9 BASELINE PASS — TERMINAL FULL-SIX AND DEPLOYED-LIVE ACCEPTANCE PENDING**

Code-under-test repair commit: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

The intended GUI contract follows the verified R6D visual model while adding
operational availability and receipt-age state. The browser renders
server-published analytical rows; it may select, sort, filter, and draw them,
but it must not recompute detector, inventory, lifecycle, participation, or
cross-layer analytics.

## Current post-repair evidence

| Evidence | Result | What it proves |
|---|---|---|
| Complete repository regression on `e1d67c5...` | 660/660, zero failed/skipped | Current API, GUI, gateway, host-only, fixture-browser, and analytical regression |
| Current Playwright/Chromium fixture | PASS within the 660-test suite; zero console/page errors | Current synthetic rendering, replay/control persistence, and tracked fixture screenshots |
| Focused August 19 all-nine callback run | PASS; summary SHA-256 `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9` | Actual post-repair checkpoint/callback GUI projection across all nine focused schedules |
| Fresh persistent-v9 A/B GUI baseline | R6D 180/180 rows PASS; 174,080 target-only rows equal 174,080 permitted live extensions; zero unexplained | Fresh full-six baseline parity with the frozen R6D GUI reference |
| Terminal persistent-v9 schedule suite | PENDING | Baseline success must not be promoted to terminal all-nine full-six acceptance |
| Isolated deployed GUI and public browser | PENDING | Fresh installed-service screenshots, external reachability, and public-surface checks remain required |

The historical `81b0836fe50939246ae210bb62780ac4e163e100` result is retained
only as regression history. It is not current post-repair, terminal full-six, or
deployed-live evidence.

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

| Missing/stale layer | Required behavior | Current standing |
|---|---|---|
| 3D | Continue 2D, 1D, and Intraday; show reason | POST-REPAIR SUITE PASS; deployed-live pending |
| 2D | Continue 1D and Intraday; show reason | POST-REPAIR SUITE PASS; deployed-live pending |
| All fixed horizons | Continue Intraday when available | POST-REPAIR FIXTURE PASS; deployed-live pending |
| Stale Index or Futures | Suspend divergence as `STALE_DATA`; retain last chart with warning | POST-REPAIR SUITE PASS; deployed-live pending |
| Missing/stale options | Suspend only affected participation layer | POST-REPAIR SUITE PASS; deployed-live pending |
| Missing CE/PE | Do not block Index/Futures chart | POST-REPAIR SUITE PASS; deployed-live pending |

Live events must never be labelled `SUCCESS` or `FAILURE`.

## Current tracked fixture visual evidence

The 660-test post-repair regression regenerated these fixtures. They prove the
current synthetic GUI states shown; they are not screenshots of an installed or
externally reached service.

| Current fixture scenario | File | Dimensions | SHA-256 |
|---|---|---:|---|
| Complete fixed horizons | `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `e89811399f4215d4efb4df6db7aaf0a83d07dde1ddcb726d5762798e50c934bf` |
| Intraday-only degradation | `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `87174e261da8942ebb1bb6bc9080e2fa276899f46dc9cadf1aa112cbadc9fc9b` |
| Fixture/latest operational | `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `af4c7b4f072152f081ad0a26f75fcc72313e50802d6f0224a08a1154fbd798c0` |

Any screenshots from the earlier `81b0836...` deployment attempt are
explicitly rejected as final evidence because the callback repair changed the
code-under-test. Fresh screenshots must be captured from the final isolated
deployment for complete fixed horizons, Intraday-only degradation, and the
live/latest operational state.

## Fresh v9 GUI baseline

Persistent v9 has sealed its incremental A and independently clean
chronological B baselines. Their canonical GUI-visible artifacts passed the
fresh R6D row-level comparison 180/180. All 174,080 target-only rows are the
independently enumerated 174,080 permitted live-degradation extensions; there
are zero reference-only or unexplained rows. The R6D comparison matrix SHA-256
is `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467`.

This baseline establishes fresh GUI parity for the original-chunk incremental
path and clean chronological batch path. It does not establish terminal
full-six acceptance: every required schedule, restart/recovery gate, and
terminal marker must still complete successfully.

## Remaining final acceptance gates

- Complete and seal the persistent-v9 all-nine full-six schedule suite.
- Start the verified isolated backend and sanitized gateway without touching
  ports 8803/8804.
- Measure the deployed chart response and confirm it remains below 8 MiB.
- Repeat selection-persistence, stale/degradation, payload-security, console,
  page-error, refresh, health, readiness, and historical-replay checks against
  the installed service.
- Capture fresh deployed-browser screenshots and verify the selected public URL
  from an off-host client.

`GUI_ACCEPTANCE: POST_REPAIR_FIXTURE_AND_V9_BASELINE_PASS_TERMINAL_AND_DEPLOYED_LIVE_PENDING`

Detailed pending browser cases are listed in [R6E1R_BROWSER_TEST_REPORT.md](R6E1R_BROWSER_TEST_REPORT.md).
