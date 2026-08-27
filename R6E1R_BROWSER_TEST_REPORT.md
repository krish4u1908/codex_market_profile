# R6E1R Browser Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT BROWSER RUN UNAVAILABLE LOCALLY; HOSTINGER BROWSER AND DEPLOYED-LIVE EVIDENCE PENDING**

Python Playwright/Chromium is not installed in the current local environment. No current-source browser run was executed here, so historical screenshots or browser counts are not promoted to current acceptance evidence.

## Current local evidence

| Check | Result | Scope |
|---|---|---|
| Current API suite | 39/39 passed | Server/API behavior only; not a browser result |
| Pre-final-repair selected functional baseline | 416 passed; 5 host-only tests deliberately deselected | Historical non-browser GUI/API/runtime coverage; not a Chromium result |
| Gateway security | 13/13 passed | Sanitization, concurrency, hidden-path validation, and GET/HEAD redirect-refusal tests; not a browser result |
| Current Playwright/Chromium run | `NOT_RUN_LOCALLY` | Browser runtime unavailable |
| Console errors | `PENDING_HOSTINGER_EVIDENCE` | Must be measured in current Chromium run |
| Page errors | `PENDING_HOSTINGER_EVIDENCE` | Must be measured in current Chromium run |
| External URL result | `PENDING_DEPLOYMENT_EVIDENCE` | No service has been deployed from this handoff |

## Mandatory current-source browser scenarios

| Scenario | Required assertion | Standing |
|---|---|---|
| Complete fixed horizons | 3D/2D/1D/Intraday controls and selected Price/OI VPOC render | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Intraday-only degradation | Intraday remains visible; fixed controls/lines are absent; reasons are shown | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Live/latest operational | Last chart remains visible with stale warning and receipt ages when appropriate | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Index/Futures paths | Independently sorted multi-point paths plus aligned Basis | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Category masters | Disable/enable all category children without losing child selections | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| 1D-only | Only selected 1D children render | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Replay movement | Selections persist across all six replay dates | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Poll, refresh, latest | Selections persist across polling, reload, and return to latest | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Missing fixed horizons | Available Intraday remains visible with per-layer reasons | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Missing options | Index/Futures chart remains available; only participation degrades | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Stale Index/Futures | Divergence becomes `STALE_DATA`; last valid chart remains with warning | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| No outcome language | No live event is labelled SUCCESS or FAILURE | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| No client analytics | Browser performs no detector/inventory/lifecycle/participation recomputation | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Security | No raw records, filesystem paths, secrets, or credentials appear in page/payload/log | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Browser health | Zero console errors and zero page errors | `PENDING_HOSTINGER_BROWSER_EVIDENCE` |
| Response size | Largest sanitized chart response remains below 8 MiB | `PENDING_HOSTINGER_EVIDENCE` |

## Historical fixture evidence

These tracked images and hashes were recorded at earlier pushed head `4d160bcc61bcebd88135ce270c17926830022deb`. They remain historical visual fixtures only; they are not proof of current-source rendering or a deployed service.

| Historical fixture | Dimensions | Historical SHA-256 |
|---|---:|---|
| `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `f7676c44a6fa49d2822c3285705abf8749f9675196429ab02e229e53fa976bae` |
| `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `250ba99fd8f473d428b6069459ed7874423aa2d1d19faf1177a2e7f3783ea005` |
| `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `ebb0c7b2afb7e8ea6e6461a733b3b1534822270c870a0cff73a8c917e2ab3b6c` |

The third historical image used an operational fixture. It is not evidence that an external live service existed.

At GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, an R6D-parity engine/GUI/API/browser gate passed 135/135 with zero recorded console/page errors. Runtime, tests, and package bytes changed afterward, so that result is regression history only.

## Final standing

Browser acceptance remains open until Hostinger runs the current source and sealed package in Chromium, visually inspects all required screenshots, records browser/version/viewport and exact command, observes zero console/page errors, and repeats the relevant checks against the isolated deployed URL.

`CURRENT_BROWSER_ACCEPTANCE: PENDING_HOSTINGER_BROWSER_AND_DEPLOYED_LIVE_EVIDENCE`
