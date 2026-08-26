# R6E1R Source-Hash Comparison Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED SOURCE AND ENGINE INTEGRITY VERIFIED; FINAL SIX-SESSION AND PACKAGE HASHES PENDING**

## Focused August 19 sample

| Item | Verified fact |
|---|---|
| Sample root | `/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205` |
| Authoritative focused A/B input | `/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205/collector` |
| Evaluation window | 2026-08-19, 09:15-12:05 IST |
| Selected Futures | `NSE:BANKNIFTY26AUGFUT`, selected by repository logic |
| Selected record identities | 46,550/46,550 |
| Raw outer records | 46,210 |
| OI outer records | 340 |
| Projected collector files | 8 original hourly paths |
| Authoritative source files | 8, each independently hashed before/during/after extraction |
| Pre/post source hashes, sizes, mtimes | 8/8 unchanged |
| Manifest SHA-256 | `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382` |
| Hour-preserving build and integrity verification | 9.91s elapsed; 434,972 KiB peak RSS |
| Source mutations | 0 |

Raw/sample JSONL is outside Git. The repository contains only reports, manifests, tests, and sanitized evidence.

## Frozen reference packages

Before final comparison, external comparison-package verification recorded:

- R6C2R comparison package: 74/74 files passed.
- R6D GUI comparison package: 40/40 files passed.

The corresponding verified Git tags were checked before editing. References remain post-seal comparators, not A/B inputs.

These are distinct from the repository tag manifests verified before editing: R6C2R 94/94 repository files and R6D 105/105 repository files.

## Final six-session raw-source comparison

| Measure | Before | After | Required result |
|---|---|---|---|
| Authoritative source file count | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | Equal |
| Total source bytes | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | Equal |
| SHA-256 identities | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | Every file equal |
| Size/mtime identities | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | Every file equal |
| Incomplete final bytes excluded | `PENDING_FINAL_EVIDENCE` | Not written | Recorded only |
| Source mutations | — | `PENDING_FINAL_EVIDENCE` | 0 |
| August 17 rejection input present | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | Yes, never forced accepted |

Final raw projection manifest path/SHA-256: `PENDING_FINAL_EVIDENCE`

Final source-hash comparison CSV path/SHA-256: `PENDING_FINAL_EVIDENCE`

## Runtime package allowlist

The current 26-file engine-source allowlist and its 34-file deployment superset are sealed and verified after the final service-template hardening.

| Item | Final value |
|---|---|
| Engine source manifest path | `manifests/r6e1r_engine_source_manifest.json` |
| Manifest file count | 26 |
| Manifest SHA-256 | `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3` |
| Companion check | PASS — companion records the same manifest digest |
| Explicit deployed config pin | Template pins `7c13b44c...`; installed deployment copy `PENDING_FINAL_EVIDENCE` |
| Engine hash | `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602` |
| Allowlisted file mismatches | 0 — 26/26 PASS |
| Prohibited runtime source opens | 0 in accepted focused v12; final six `PENDING_FINAL_EVIDENCE` |
| Deployment package file count | 34 |
| Deployment manifest SHA-256 | `ebaf193dca7f3cce82974906e05693864db087a60c7f7e3f028a6d1e7dc80ae3` |
| Deployment package hash | `cecb7638566fae1a3831e1ef3fdb94559dce897aa54d89db12c882550c8dbc41` |
| Runtime configuration hash | `b733ea5cc3538b41b8bdc7fcf7a7171b98a41cb0c131968c0e26596bdab93d50` |
| Deployment file mismatches | 0 — 34/34 PASS |

The deployed configuration copy must pin the final checked-in manifest with an explicit 64-hex digest; reading a mutable companion beside mutable runtime sources is not sufficient production trust.
