# R6E1R Health and Readiness Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT REGRESSION 636/636 — SERVICES NOT INSTALLED — LIVE VERIFICATION PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

No R6E1R service has been installed or accepted from this worktree. No external
URL has been deployed, and no verification tag has been created. The results
below separate local source/package evidence from the mandatory authorized-host
service evidence.

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
| Deployment manifest/companion SHA-256 | `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1` |
| Deployment package aggregate hash | `d68f22217f1dfb75817ebb9b7cb6af0d21306cf1081b7d222c6ecca130978380` |
| Runtime configuration hash | `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031` |

Both checked-in companion checks pass locally. These hashes identify the package
the authorized host must verify byte-for-byte before testing or installation;
they do not constitute live-service acceptance.

The pushed repair commit passed the complete repository regression 636/636 with
zero failures or skips in 129.36 seconds (2m09.72 wall, 685,556 KiB peak RSS).
The retained log/time SHA-256 values are
`a1132553080052c44424e8c936a33a8b7f548661b11390460fd0492463050bef`
and `c2127eca2426ccb1a92a48875aa1d8ad2939e2be5ccf99bbaed921de8e175681`.

## Prior targeted/local evidence

| Gate | Prior targeted/local result | Current authorized-host acceptance status |
|---|---|---|
| API and gateway tests | Included in 636/636 current regression | Fresh installed-service probes pending |
| User-systemd/bubblewrap tests | CURRENT REGRESSION PASS; zero failures/skips | Actual service install/lifecycle pending |
| Unit syntax verification | CURRENT REGRESSION PASS | Rendered deployment-host unit verification pending |
| Complete repository collection | 636 passed, 0 failed, 0 skipped | CURRENT REGRESSION PASS |
| Browser fixture | 1/1 in 4.86 s; zero console/page errors | CURRENT FIXTURE PASS; deployed browser pending |
| Runtime file-open instrumentation | Host-only ptrace/strace tests pass within 636/636 | Fresh focused/full-six measured trace pending |

## Required authorized-host live evidence

| Probe | Expected | Current evidence |
|---|---|---|
| Backend `/api/health` | HTTP 200 | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Gateway `/api/health` | HTTP 200 | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Backend `/api/readiness` | 200 or explicitly benign after-hours 503 | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Gateway `/api/readiness` | Same sanitized state | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| `/api/audit` | Measured zero causal violations and verified manifest | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Six `/api/session?date=...` checks | Nonempty `HISTORICAL_REPLAY` | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Absent verified replay date | Non-200 unavailable | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Largest public chart response | Less than the gateway's 8 MiB per-response ceiling | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Backend SIGKILL recovery | Gateway remains active; backend recovers automatically without a manual gateway restart | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Public interface | Only the selected research port is exposed | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| External URL | HTTP 200 after all analytical gates pass | `NOT_DEPLOYED` |

The exact acceptance order and probe commands are recorded in
[R6E1R_DEPLOYMENT_RUNBOOK.md](R6E1R_DEPLOYMENT_RUNBOOK.md).
