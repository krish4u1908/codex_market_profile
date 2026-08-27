# R6E1R Source-Hash Comparison Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

This public report omits physical source locations, archive names, raw
filenames, temporary roots, and receipt-level lineage. Raw/sample JSONL remains
outside Git.

## Focused August 19 fixture

The focused fixture remains the fast regression input. Its historical identity
must be rerun from the exact published commit for current acceptance.

| Item | Recorded fact |
|---|---|
| Physical location | `<HOST_FOCUSED_SAMPLE_ROOT>` |
| Evaluation window | 2026-08-19, 09:15–12:05 IST |
| Selected Futures | `NSE:BANKNIFTY26AUGFUT`, selected by repository logic |
| Selected record identities | 46,550/46,550 |
| Raw outer records | 46,210 |
| OI outer records | 340 |
| Projected collector paths | 8 original hourly paths |
| Authoritative source files | 8 |
| Pre/post hashes, sizes, mtimes | 8/8 unchanged |
| Projection manifest SHA-256 | `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382` |
| Source mutations | 0 |

## August 20 auxiliary fixture

The auxiliary fixture was validated read-only as a parser, provenance, and
replay diagnostic. It cannot replace canonical focused or full-six evidence.

| Item | Verified local fact |
|---|---|
| Physical/archive identity | Omitted from public evidence |
| Safe archive members | 92 |
| Expanded member bytes | 2,976,963,143 |
| Repository-selected Futures | `NSE:BANKNIFTY26AUGFUT` |
| Authoritative source files selected | 24 |
| Projected collector files | 23 |
| Selected outer records | 68,171 |
| Provenance identities | 68,171/68,171 |
| Index observations | 25,279 |
| Futures observations | 41,353 |
| Futures OI observations | 770 |
| CE observations | 26,915 |
| PE observations | 26,915 |
| Malformed selected records | 0 |
| Source mutations | 0 |
| Projection manifest SHA-256 | `e3635d4c5d491f3ae25386c5888f86c1f1a51848aac0a83b09e69b610831c87a` |
| Receipt/path-session mismatches | 1, retained without exposing raw coordinates |

The pre-fix large/original auxiliary replay had identical terminal semantic
state but differed by 12 lifecycle and 24 cross-layer append-only identities.
That failure exposed unstable terminal-group publication and is not a passing
result. A fresh current-seal auxiliary rerun remains pending.

## Frozen comparison packages

- R6C2R comparison package: 74/74 files passed.
- R6D GUI comparison package: 40/40 files passed.
- R6C2R repository-tag manifest: 94/94 files passed.
- R6D repository-tag manifest: 105/105 files passed.

These are comparators, not stream/batch inputs.

## Canonical six-session raw-source comparison

Hostinger must resolve `<HOST_RAW_ROOT>` privately and hash the exact selected
source set before and after processing August 11, 12, 13, 18, 19, and 20.

| Measure | Before | After | Required result |
|---|---|---|---|
| Authoritative source file count | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Equal |
| Total source bytes | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Equal |
| SHA-256 identities | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Every file equal |
| Size/mtime identities | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Every file equal |
| Incomplete final bytes excluded | `PENDING_HOSTINGER_EVIDENCE` | Not written | Recorded only |
| Source mutations | — | `PENDING_HOSTINGER_EVIDENCE` | 0 |
| August 17 rejection retained | `PENDING_HOSTINGER_EVIDENCE` | `PENDING_HOSTINGER_EVIDENCE` | Yes |

Final raw projection manifest identity: `PENDING_HOSTINGER_EVIDENCE`.

## Current runtime/package allowlists

| Item | Current sealed value |
|---|---|
| Engine source files | PASS — 38/38 |
| Engine manifest/companion SHA-256 | `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7` |
| Engine aggregate hash | `362474858eda75b18180ad2fce48e50e1d4acdd1b04a0db405eaae199e70b7a7` |
| Engine file mismatches | 0 |
| Deployment package files | PASS — 47/47 |
| Deployment manifest/companion SHA-256 | `d1b955715280670189dfd623f60ec8c57c870397057b7a81de597e68a9d42104` |
| Deployment package aggregate hash | `83ac33a6a82bc93db49a1464d237adc9658f9318b5331321a6693622384a6bf8` |
| Runtime configuration hash | `43654758453b2a39209dbe0df6f6d2587c63c2bf5cb77c99d44df07dd54f485b` |
| Deployment file mismatches | 0 |
| Runtime file-open audit | `PENDING_HOSTINGER_STRACE_EVIDENCE` |

Hostinger must independently verify both companions, every allowlisted byte,
the explicit runtime pin, and the runtime file-open trace before installation.
No verification tag or deployment exists yet.

## Publication boundary

These public evidence reports contain no authoritative raw filename,
host-local evidence path, credential, raw record, or source payload. Runtime
templates and synthetic tests remain separately governed by their sealed
package and test contracts.
