# R6E1R Browser Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FIXTURE VERIFIED; DEPLOYED BROWSER RUN PENDING**

## Required scenarios

| Browser scenario | Required assertion | Final result |
|---|---|---|
| Complete fixed horizons | 3D/2D/1D/Intraday controls and selected Price/OI VPOC render | PASS — current tracked fixture |
| Intraday-only degradation | Intraday remains visible; fixed controls/lines absent; reasons shown | PASS — current tracked fixture |
| Live/latest operational | Last chart retained with stale warning and receipt ages when appropriate | PASS — fixture/latest only; deployed live proof pending |
| Index/Futures paths | Independently sorted multi-point paths plus aligned Basis | PASS — current tracked fixture |
| Category masters | Hide/show all children without losing child selections | PASS — current tracked fixture |
| 1D-only | Only selected 1D children visible | PASS — current tracked fixture |
| Replay movement | Selections persist across all six replay dates | PASS — all six canonical replay dates exercised |
| Poll and refresh | Selections persist across polling and reload | PASS — current tracked fixture |
| Return to latest | Selections and current operational state remain correct | PASS — fixture/latest only |
| Missing options | Chart remains available; participation alone degrades | PASS — targeted fixture/API coverage |
| No outcome language | No live event labelled SUCCESS or FAILURE | PASS — targeted fixture/browser coverage |
| No client analytics | No detector/inventory/lifecycle/participation recomputation | PASS — targeted fixture/browser coverage |
| Security | No raw records, paths, secrets, or credentials in page/payload/log | PASS — targeted fixture/API coverage |
| Console/page errors | Exactly zero | PASS — current fixture browser run |

## Screenshot files

| File | Current dimensions | Current tracked-fixture SHA-256 | Deployed-live standing |
|---|---:|---|---|
| `evidence/r6e1r/gui/complete_fixed_horizons.png` | 1600 x 1915 | `f7676c44a6fa49d2822c3285705abf8749f9675196429ab02e229e53fa976bae` | Fixture accepted; external proof not applicable |
| `evidence/r6e1r/gui/intraday_only_degradation.png` | 1600 x 1915 | `250ba99fd8f473d428b6069459ed7874423aa2d1d19faf1177a2e7f3783ea005` | Fixture accepted; external proof not applicable |
| `evidence/r6e1r/gui/live_latest_operational.png` | 1600 x 1915 | `ebb0c7b2afb7e8ea6e6461a733b3b1534822270c870a0cff73a8c917e2ab3b6c` | Fixture/latest only; deployed live capture `PENDING_FINAL_EVIDENCE` |

The hashes above bind the current tracked fixture images at pushed head `4d160bcc61bcebd88135ce270c17926830022deb`. The third image is generated from the operational fixture and is not evidence that the external service is live. Record a separate deployed live/latest capture, browser engine/version, viewport, command, test count, console errors, and page errors after installation.

## Recorded foundation

At pushed GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, the R6D-parity engine/GUI/API/browser targeted suite passed 135/135 tests. No tracked GUI/browser bytes have changed since that gate. All three current fixture screenshots were visually inspected, including the independently sorted Index/Futures paths and enriched dependency, price-change, option-premium-change, and transition projection. The later repaired-engine targeted gate passed 216/216 for the current runtime path. A separate deployed-browser run remains mandatory.

Final browser command: `PENDING_FINAL_EVIDENCE`

Current targeted suite count: 135 passed, 0 failed. Final isolated/deployed browser test count: `PENDING_FINAL_EVIDENCE`

External deployed URL/browser result: `PENDING_FINAL_EVIDENCE`
