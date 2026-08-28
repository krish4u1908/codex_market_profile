# R6E1R Browser Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR FIXTURE BROWSER PASS — TERMINAL FULL-SIX AND DEPLOYED-LIVE EVIDENCE PENDING**

Code-under-test repair commit: `e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

The complete post-repair regression ran Chromium/Playwright on the authorized
host. Its browser fixture passed with zero console errors and zero page errors.
This closes current fixture rendering only. Fresh installed-service browser
checks, screenshots, public reachability, and response-size evidence remain
pending.

## Current fixture and analytical evidence

| Check | Result | Scope |
|---|---|---|
| Complete repository regression | 660/660, zero failed/skipped | Current `e1d67c5...` code; includes host-only and fixture-browser coverage |
| Current Playwright/Chromium fixture | PASS within the complete suite | Current fixtures; not an installed service |
| Focused all-nine GUI projection | Exact across all nine focused schedules; summary SHA-256 `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9` | Post-repair checkpoint/callback fixture evidence |
| Fresh persistent-v9 R6D baseline | 180/180 rows PASS; 174,080 permitted live extensions; zero unexplained | Fresh full-six A/B baseline; terminal schedule suite pending |
| Console errors / page errors | 0 / 0 | Current fixture-browser evidence |
| External URL result | PENDING | No fresh post-repair externally reached browser result may yet be claimed |

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` browser and
deployment artifacts are historical only. They must not be used as evidence
for the repaired code, the terminal full-six run, or the final deployment.

## Mandatory current-source browser scenarios

| Scenario | Required assertion | Standing |
|---|---|---|
| Complete fixed horizons | 3D/2D/1D/Intraday controls and selected Price/OI VPOC render | POST-REPAIR FIXTURE PASS |
| Intraday-only degradation | Intraday remains visible; fixed controls/lines are absent; reasons are shown | POST-REPAIR FIXTURE PASS |
| Live/latest operational | Last chart remains visible with stale warning and receipt ages when appropriate | POST-REPAIR FIXTURE PASS; deployed-live pending |
| Index/Futures paths | Independently sorted multi-point paths plus aligned Basis | POST-REPAIR FIXTURE PASS |
| Category masters | Disable/enable all category children without losing child selections | POST-REPAIR FIXTURE PASS |
| 1D-only | Only selected 1D children render | POST-REPAIR FIXTURE PASS |
| Replay movement | Selections persist across all six replay dates | POST-REPAIR FIXTURE PASS |
| Poll, refresh, latest | Selections persist across polling, reload, and return to latest | POST-REPAIR FIXTURE PASS; installed-service repetition pending |
| Missing fixed horizons | Available Intraday remains visible with per-layer reasons | POST-REPAIR FIXTURE PASS |
| Missing options | Index/Futures chart remains available; only participation degrades | POST-REPAIR SUITE PASS; deployed-live visual pending |
| Stale Index/Futures | Divergence becomes `STALE_DATA`; last valid chart remains with warning | POST-REPAIR SUITE PASS; deployed-live visual pending |
| No outcome language | No live event is labelled SUCCESS or FAILURE | POST-REPAIR FIXTURE PASS |
| No client analytics | Browser performs no detector/inventory/lifecycle/participation recomputation | POST-REPAIR SUITE PASS |
| Security | No raw records, filesystem paths, secrets, or credentials appear in page/payload/log | POST-REPAIR SUITE PASS; deployed public-surface probe pending |
| Browser health | Zero console errors and zero page errors | POST-REPAIR FIXTURE PASS — 0/0 |
| Response size | Largest sanitized chart response remains below 8 MiB | PENDING DEPLOYED-SERVICE MEASUREMENT |

## Current tracked fixture evidence

The 660-test post-repair suite regenerated these tracked fixtures at 1600 x
1915. They prove the synthetic states shown, not an installed service.

| Current fixture | Dimensions | SHA-256 |
|---|---:|---|
| `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `e89811399f4215d4efb4df6db7aaf0a83d07dde1ddcb726d5762798e50c934bf` |
| `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `87174e261da8942ebb1bb6bc9080e2fa276899f46dc9cadf1aa112cbadc9fc9b` |
| `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `af4c7b4f072152f081ad0a26f75fcc72313e50802d6f0224a08a1154fbd798c0` |

The third image uses an operational fixture; it is not proof that a live
external service exists. All previously captured deployed screenshots from the
historical `81b0836...` state are explicitly rejected for final acceptance.
The final deployment must produce fresh screenshots from the repaired runtime.

## Fresh v9 baseline and terminal boundary

Persistent v9's sealed incremental A and independent clean chronological B
passed the R6D GUI reference comparison 180/180. Its 174,080 target-only rows
exactly equal the 174,080 independently permitted live-extension rows, leaving
zero reference-only or unexplained rows. The comparison matrix SHA-256 is
`dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467`.

That evidence establishes the fresh baseline GUI-visible as-of state. It is not
terminal full-six browser acceptance: all nine incremental schedules,
transition-boundary restarts, recovery matrices, and terminal marker remain
mandatory and pending.

## Deployed-live browser checks still required

- Load the isolated sanitized gateway over its final public interface and
  record the exact URL and port.
- Capture fresh complete-fixed-horizon, Intraday-only, and live/latest
  screenshots from the installed post-repair service.
- Repeat all master/child selection, replay, poll, refresh, latest, stale, and
  degradation checks against that service.
- Verify six historical replay sessions, health, after-hours readiness behavior,
  zero console/page errors, no browser-side analytics, and no sensitive payload
  fields.
- Measure the actual largest chart response and enforce the 8 MiB limit.
- Verify the public interface from an off-host client; a localhost-only pass is
  not external acceptance.

`CURRENT_BROWSER_ACCEPTANCE: POST_REPAIR_FIXTURE_AND_V9_BASELINE_PASS_TERMINAL_AND_DEPLOYED_LIVE_PENDING`
