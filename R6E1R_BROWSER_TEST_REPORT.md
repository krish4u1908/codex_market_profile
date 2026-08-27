# R6E1R Browser Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FIXTURE BROWSER PASS — DEPLOYED-LIVE EVIDENCE PENDING — NOT DEPLOYED**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

The complete current-commit regression ran Chromium/Playwright on the authorized
host. Its browser fixture passed 1/1 in 4.86 seconds with zero console errors and
zero page errors. This closes current fixture rendering only; no service or
external URL has been deployed, so it is not deployed-live browser evidence.

## Current fixture and regression evidence

| Check | Result | Scope |
|---|---|---|
| Complete repository regression | 636/636, zero failed/skipped | Current pushed repair commit; includes host-only and fixture-browser coverage |
| Current Playwright/Chromium fixture | 1/1 in 4.86 s | CURRENT FIXTURE PASS; not a deployed service |
| Console errors | 0 | CURRENT FIXTURE PASS |
| Page errors | 0 | CURRENT FIXTURE PASS |
| External URL result | `NOT_DEPLOYED` | No service has been deployed from this handoff |

## Mandatory current-source browser scenarios

| Scenario | Required assertion | Standing |
|---|---|---|
| Complete fixed horizons | 3D/2D/1D/Intraday controls and selected Price/OI VPOC render | CURRENT FIXTURE PASS |
| Intraday-only degradation | Intraday remains visible; fixed controls/lines are absent; reasons are shown | CURRENT FIXTURE PASS |
| Live/latest operational | Last chart remains visible with stale warning and receipt ages when appropriate | CURRENT SUITE PASS; current screenshot is fixture-only; deployed-live pending |
| Index/Futures paths | Independently sorted multi-point paths plus aligned Basis | CURRENT FIXTURE PASS |
| Category masters | Disable/enable all category children without losing child selections | CURRENT FIXTURE PASS |
| 1D-only | Only selected 1D children render | CURRENT FIXTURE PASS |
| Replay movement | Selections persist across all six replay dates | CURRENT FIXTURE PASS |
| Poll, refresh, latest | Selections persist across polling, reload, and return to latest | CURRENT FIXTURE PASS |
| Missing fixed horizons | Available Intraday remains visible with per-layer reasons | CURRENT FIXTURE PASS |
| Missing options | Index/Futures chart remains available; only participation degrades | CURRENT SUITE PASS; deployed-live visual pending |
| Stale Index/Futures | Divergence becomes `STALE_DATA`; last valid chart remains with warning | CURRENT SUITE PASS; deployed-live visual pending |
| No outcome language | No live event is labelled SUCCESS or FAILURE | CURRENT FIXTURE PASS |
| No client analytics | Browser performs no detector/inventory/lifecycle/participation recomputation | CURRENT SUITE PASS |
| Security | No raw records, filesystem paths, secrets, or credentials appear in page/payload/log | CURRENT SUITE PASS; deployed public-surface probe pending |
| Browser health | Zero console errors and zero page errors | CURRENT FIXTURE PASS — 0/0 |
| Response size | Largest sanitized chart response remains below 8 MiB | `PENDING_AUTHORIZED_HOST_EVIDENCE` |

## Current fixture evidence

The 636-test complete suite regenerated these current-commit fixtures at 1600 x
1915. They prove the synthetic fixture states shown, not a deployed service.

| Current fixture | Dimensions | Current SHA-256 |
|---|---:|---|
| `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `532c09190f817ddf697445b3a7351220f3be0d5c19083978ea35065a083a4fdc` |
| `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `307e33736bd9f9c68c4f6d99fd30a76d5a411352d0b633795f8957db90bb772c` |
| `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `a5e75f678a90ef67567222d2ed87d0bf57aad0d3a197f1b58371ecdaabdec3c2` |

The third image uses an operational fixture. It is not evidence that an
external live service exists.

At GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, an R6D-parity engine/GUI/API/browser gate passed 135/135 with zero recorded console/page errors. Runtime, tests, and package bytes changed afterward, so that result is regression history only.

## Final standing

Current fixture-browser acceptance is complete. Browser acceptance remains open
for the isolated deployed URL, including the live public surface, actual
response-size measurement, and operational refresh checks after service start.

`CURRENT_BROWSER_ACCEPTANCE: FIXTURE_PASS_DEPLOYED_LIVE_PENDING`
