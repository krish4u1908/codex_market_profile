# R6E1R Health and Readiness Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED — NO TERMINAL PRELOAD OR DEPLOYMENT**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

Pushed report head immediately before this refresh:
`c555b099ffdfbee66117b33ad4693de9f61eaaea`.

No current `e1d67c5` R6E1R deployment backend or gateway has been installed or
accepted. The standard service names are inactive/dead and runtime-masked; their
stale definitions must not be started. No local endpoint or external URL has
been accepted, and no verification tag has been created. The separate v9
full-six analytical unit was an offline verifier, not the deployment API or GUI.
At 20:39 IST an external root/operator transaction runtime-masked and stopped
that verifier on client request, then deleted its evidence, work, and control
roots before any alternate-schedule marker or terminal summary existed.
The earlier `81b0836fe50939246ae210bb62780ac4e163e100` service package and
full-six result are retained as historical evidence only because the current
authenticated engine changed after the sparse empty-Index repair.

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
| Engine JSON manifest SHA-256 (companion verification PASS) | `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210` |
| Engine aggregate hash | `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947` |
| Deployment allowlist | PASS — 47/47 files |
| Deployment JSON manifest SHA-256 (companion verification PASS) | `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391` |
| Deployment package aggregate hash | `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949` |
| Runtime configuration hash | `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41` |
| Raw runtime-config template SHA-256 | `cbcf9f43befa4b18b4798240c18d841f1629af7a015c538c8ff254e01b6957ad` |
| Backend service template SHA-256 | `153a2b493b864f9442fda8d94d0c6c2cececfde87bc9cdbfcb78d99c9aa9e7ac` |
| Gateway service template SHA-256 | `2b47c302ca3491686cd3b73d77f9190aecd413573676035923945147c49e5542` |

Both checked-in companion checks pass locally. These hashes identify the package
the authorized host must verify byte-for-byte before testing or installation;
they do not constitute live-service acceptance.

The current analytical commit passed the fully provisioned complete repository
regression 660/660 with zero failures or skips in 118.03 seconds (1m58.43 wall,
671,340 KiB peak RSS). This was the unchanged complete rerun after the stale
runtime-configuration pin was repaired; the preceding 659/1 packaging run is
retained as a non-pass.

The fresh post-repair focused August 19 all-nine run passed 21/21 components, 8/8
ledgers, 9/9 causality gates, 9/9 schedules, 72/72 checkpoint rows, 2/2 recovery
probes, 8/8 source-inventory rows, and 1/1 fixture-manifest row. Its 2,508 total
audit rows comprised 2,499 runtime-open rows, 8 source-inventory rows, and 1
fixture-manifest row. Differences, refusals, future joins, timestamp backdating,
duplicate IDs, prohibited/unmeasured runtime opens, and source mutations were
all zero. Summary SHA-256:
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
This focused evidence does not satisfy the full six-session preload requirement.

Persistent v9 ran from a clean detached `e1d67c5` checkout under invocation
`ce9595fd18b344ab8ab2765ae509f8fa`. Its independently recorded incremental-A,
clean chronological-B, component, ledger, causality, R6C2R, and R6D baseline
matrices were PASS before the stop. Their files no longer survive for terminal
review. No alternate schedule, terminal source rehash/final summary, terminal
state validation, or eligible preload survived. Cold-start RSS,
installed-service health/readiness, and public evidence were not measured.

## Prior targeted/local evidence

| Gate | Prior targeted/local result | Current authorized-host acceptance status |
|---|---|---|
| API and gateway tests | Included in 660/660 current regression | Fresh installed-service probes pending |
| User-systemd/bubblewrap tests | CURRENT REGRESSION PASS; zero failures/skips | Actual service install/lifecycle pending |
| Unit syntax verification | CURRENT REGRESSION PASS | Rendered deployment-host unit verification pending |
| Complete repository collection | 660 passed, 0 failed, 0 skipped | CURRENT REGRESSION PASS |
| Browser fixture | CURRENT FIXTURE PASS; zero console/page errors | Deployed browser pending |
| Runtime file-open instrumentation | Focused PASS: 2,508 total audit / 2,499 runtime-open rows; 8 source-inventory + 1 fixture-manifest; prohibited/unmeasured runtime opens 0 | Full-six and installed-runtime audit pending |

## Static host readiness and external blocker

The current read-only preflight found:

- backend `127.0.0.1:18805` and candidate gateway port `8805` free;
- port 8803 unchanged at PID `380743`, start ticks `46015771`, invocation
  `d0df21acd54a440788d89f7cad5b4827`, and `NRestarts=0`;
- port 8804 unchanged at PID `465394`, start ticks `51980337`, invocation
  `260291b2ae4a4c70a95a0a37722af61e`, and `NRestarts=0`;
- standard `r6e1r-shadow.service` and `r6e1r-readonly-gateway.service` units
  inactive/dead and runtime-masked with stale paths;
- preferred clean runtime worktree
  `/opt/banknifty/repositories/r6e1r-runtime-e1d67c5` and isolated deployment
  root `/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final` not yet
  accepted as an installation; and
- public IPv4 `200.234.39.232`, making
  `http://200.234.39.232:8805/` a candidate only, not a deployed or verified
  URL.

Host UFW is active with IPv4/IPv6 enabled and default inbound policy `DROP`.
The current account has neither firewall-change permission nor provider
firewall authority. External ingress is therefore likely blocked even after a
local deployment succeeds. An administrator must verify or allow only the
single selected TCP port, and an independent external client must prove
reachability. This preflight is not evidence that a local endpoint or the public
candidate URL works.

The units mount repository/collector inputs read-only and isolate the gateway
from collector/state/config. The same service UID nevertheless has host-level
write authority to the repository and collector `raw`/`oi` directories outside
those namespaces. This residual same-UID limitation must remain documented and
does not authorize deployment code to modify those paths.

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
| Full-six preload validation | Exact finalized incremental-A state and bound manifest | `BLOCKED_NO_TERMINAL_STATE_SURVIVED` |
| Cold-preload backend RSS | Below configured hard limit without analytical truncation | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Largest public chart response | Less than the gateway's 8 MiB per-response ceiling | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Backend SIGKILL recovery | Gateway remains active; backend recovers automatically without a manual gateway restart | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Public interface | Only the selected research port is exposed | `PENDING_AUTHORIZED_HOST_LIVE_EVIDENCE` |
| Candidate external URL | `http://200.234.39.232:8805/` after all analytical and firewall gates pass | `NOT_DEPLOYED_OR_VERIFIED` |

The exact acceptance order and probe commands are recorded in
[R6E1R_DEPLOYMENT_RUNBOOK.md](R6E1R_DEPLOYMENT_RUNBOOK.md).
