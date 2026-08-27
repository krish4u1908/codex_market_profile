# R6E1R Health and Readiness Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT SOURCE/PACKAGE SEALED; HOSTINGER LIVE VERIFICATION PENDING**

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
| Engine manifest/companion SHA-256 | `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3` |
| Engine aggregate hash | `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d` |
| Deployment allowlist | PASS — 47/47 files |
| Deployment manifest/companion SHA-256 | `c75d269da49f141352aeedffd0e3b7fc09d9045ab814bdf917214e44ac905a7b` |
| Deployment package aggregate hash | `563e2d848933c41eea1db20008bf92e29ee6162baaeb767361e5c605aec18c4c` |
| Runtime configuration hash | `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031` |

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
