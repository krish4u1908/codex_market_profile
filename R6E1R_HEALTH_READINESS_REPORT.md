# R6E1R Health and Readiness Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

No R6E1R service has been installed or accepted from this worktree. There is no
verified external URL and no verification tag. The results below separate local
source/package evidence from the mandatory Hostinger service evidence.

## Read-only endpoint inventory

The backend and sanitized gateway expose only GET/HEAD access to:

- `/api/health`
- `/api/readiness`
- `/api/status`
- `/api/session`
- `/api/chart`
- `/api/inventory`
- `/api/divergence`
- `/api/lifecycle`
- `/api/participation`
- `/api/transitions`
- `/api/availability`
- `/api/audit`

There are no order, trade, write, alert, or callback-mutation endpoints. POST,
PUT, PATCH, and DELETE are refused by the gateway. Unknown routes, unknown or
duplicate query keys, and unavailable replay dates are refused.

## Health and readiness contract

Health returns HTTP 200 only when the process is functioning. Its accepted
payload must not expose raw records, source paths, credentials, or secrets.

Readiness is stricter than process health. A 503 is benign only when every reason
is in the explicit after-hours stale/missing-market allowlist. Every readiness
response must still establish:

- checkpoint integrity is valid;
- runtime engine-source manifest verification is true;
- future joins equal zero;
- synchronization-tolerance violations equal zero;
- timestamp backdating and duplicate analytical IDs are measured, not asserted;
- missing options or fixed horizons do not make a valid Index/Futures chart
  unready.

Historical replay readiness is evaluated against the selected sealed replay and
remains separate from live/latest wall-clock staleness. A verified-but-absent
requested date must return a non-200 unavailable response rather than an empty
replay object.

## Current sealed package identity

| Item | Current result |
|---|---|
| Engine allowlist | PASS — 38/38 files |
| Engine manifest/companion SHA-256 | `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7` |
| Engine aggregate hash | `362474858eda75b18180ad2fce48e50e1d4acdd1b04a0db405eaae199e70b7a7` |
| Deployment allowlist | PASS — 47/47 files |
| Deployment manifest/companion SHA-256 | `d1b955715280670189dfd623f60ec8c57c870397057b7a81de597e68a9d42104` |
| Deployment package aggregate hash | `83ac33a6a82bc93db49a1464d237adc9658f9318b5331321a6693622384a6bf8` |
| Runtime configuration hash | `43654758453b2a39209dbe0df6f6d2587c63c2bf5cb77c99d44df07dd54f485b` |

Both checked-in companion checks pass locally. These hashes identify the package
Hostinger must verify byte-for-byte before testing or installation; they do not
constitute live-service acceptance.

## Current local evidence

| Gate | Local result | Hostinger acceptance status |
|---|---|---|
| API tests | PASS — 39/39 | Fresh live probes pending |
| Gateway security tests | PASS — 13/13, including GET/HEAD redirect refusal and hidden-path validation | Namespace and public-surface probes pending |
| Deployment/runner tests | 130 passed; 2 user-systemd tests unavailable because this environment has no user bus | Exact user-systemd lifecycle pending |
| Unit syntax verification | PASS locally | Exact Hostinger unit verification pending |
| Complete non-browser collection | 545 passed, 20 skipped; 13 failures and 16 errors are host-reference/ptrace/user-systemd environment gates | Complete Hostinger regression pending |
| Browser acceptance | Chromium/Playwright unavailable locally | Mandatory Hostinger browser/geometry run pending |
| Runtime file-open trace | Ptrace/strace unavailable locally | Mandatory Hostinger strace audit pending |

## Required Hostinger live evidence

| Probe | Expected | Current evidence |
|---|---|---|
| Backend `/api/health` | HTTP 200 | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Gateway `/api/health` | HTTP 200 | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Backend `/api/readiness` | 200 or explicitly benign after-hours 503 | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Gateway `/api/readiness` | Same sanitized state | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| `/api/audit` | Measured zero causal violations and verified manifest | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Six `/api/session?date=...` checks | Nonempty `HISTORICAL_REPLAY` | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Absent verified replay date | Non-200 unavailable | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Largest public chart response | Less than the gateway's 8 MiB per-response ceiling | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Backend SIGKILL recovery | Gateway remains active; backend recovers automatically without a manual gateway restart | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| Public interface | Only the selected research port is exposed | `PENDING_HOSTINGER_LIVE_EVIDENCE` |
| External URL | HTTP 200 after all analytical gates pass | `NOT_DEPLOYED` |

The exact acceptance order and probe commands are recorded in
[R6E1R_DEPLOYMENT_RUNBOOK.md](R6E1R_DEPLOYMENT_RUNBOOK.md).
