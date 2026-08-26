# R6E1R Health and Readiness Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT SOURCE/API CONTRACT VERIFIED; LIVE DEPLOYMENT EVIDENCE PENDING**

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

There are no order, trade, write, alert, or callback-mutation endpoints. POST, PUT, PATCH, and DELETE are refused by the gateway. Unknown routes, unknown or duplicate query keys, and unavailable replay dates are refused.

## Health contract

Health returns HTTP 200 when the process is functioning. Its accepted payload must establish process operation and must not expose raw records, source paths, credentials, or secrets.

Final backend health payload/status: `PENDING_FINAL_EVIDENCE`

Final gateway health payload/status: `PENDING_FINAL_EVIDENCE`

## Readiness contract

Readiness is stricter than process health. A 503 is benign only when every reason is in the explicit after-hours stale/missing-market allowlist. Every readiness response must still establish:

- checkpoint integrity is valid;
- runtime engine-source manifest verification is true;
- future joins equal zero;
- synchronization tolerance violations equal zero;
- timestamp backdating and duplicate analytical IDs are measured, not asserted;
- missing options or fixed horizons do not make a valid Index/Futures chart unready.

Historical replay readiness is evaluated against the selected sealed replay and remains separate from live/latest wall-clock staleness. A verified-but-absent requested date must return a non-200 unavailable response rather than an empty replay object.

## Static/package evidence

Prepared deployment verification previously recorded:

- user-unit syntax verification passed;
- exact transient user-systemd bubblewrap `ExecStart` and `ExecStartPost` probes passed;
- deployment tests recorded 17/17 passed;
- consolidated operational/API/retention tests recorded 45/45 passed;
- no service bind or installation action occurred.

Additional code changes occurred afterward. Current-source final results are therefore required:

Current source identity is pushed head `4d160bcc61bcebd88135ce270c17926830022deb`. Its 26-file engine allowlist passes with manifest SHA-256 `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3` and engine hash `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`. The R6D-parity engine/GUI/API/browser gate passed 135/135 at pushed GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`, after which no tracked GUI/browser bytes changed; the later repaired-engine targeted gate passed 216/216 for the current runtime path. Neither result substitutes for current service-template/package verification after final freeze.

| Gate | Final result |
|---|---|
| Deployment tests | `PENDING_FINAL_EVIDENCE` |
| Live GUI/API unit tests | PASS — 135/135 at unchanged GUI/browser milestone bytes; final consolidated rerun `PENDING_FINAL_EVIDENCE` |
| Exact systemd verification | `PENDING_FINAL_EVIDENCE` |
| Bubblewrap runtime self-test | `PENDING_FINAL_EVIDENCE` |
| Credential-redaction failure test | `PENDING_FINAL_EVIDENCE` |
| Fatal readiness-503 test | `PENDING_FINAL_EVIDENCE` |

## Live evidence matrix

| Probe | Expected | Actual |
|---|---|---|
| Backend `/api/health` | HTTP 200 | `PENDING_FINAL_EVIDENCE` |
| Gateway `/api/health` | HTTP 200 | `PENDING_FINAL_EVIDENCE` |
| Backend `/api/readiness` | 200 or explicitly benign after-hours 503 | `PENDING_FINAL_EVIDENCE` |
| Gateway `/api/readiness` | Same sanitized state | `PENDING_FINAL_EVIDENCE` |
| `/api/audit` | Measured zero causal violations and verified manifest | `PENDING_FINAL_EVIDENCE` |
| Six `/api/session?date=...` checks | Nonempty `HISTORICAL_REPLAY` | `PENDING_FINAL_EVIDENCE` |
| Absent verified replay date | Non-200 unavailable | `PENDING_FINAL_EVIDENCE` |
| Public interface | Exact selected port only | `PENDING_FINAL_EVIDENCE` |

Exact probe commands are in [R6E1R_DEPLOYMENT_RUNBOOK.md](R6E1R_DEPLOYMENT_RUNBOOK.md).
