# R6E1R Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FOCUSED INGESTION/ORCHESTRATION SUITES PASSED; LOCAL HOST-BOUND AND COMPLETE HOSTINGER GATES NOT ACCEPTED**

No failing or skipped test may be weakened, deselected, reclassified, or omitted to obtain acceptance. Environment-blocked tests are reported as non-passes until they pass in the required Hostinger environment.

## Current-source local evidence

| Suite | Passed | Failed | Errors | Skipped/deselected | Elapsed | Standing |
|---|---:|---:|---:|---:|---:|---|
| Ingestion suite | 127 | 0 | 0 | 0 | 7.51 s | PASS |
| Orchestrator suite | 111 | 0 | 0 | 0 | 19.98 s | PASS |
| Equivalence harness | 32 | 3 | 0 | 0 | 6.64 s | NOT ACCEPTED locally; all three failures require permitted `strace`/`ptrace` |
| Deployment package, gateway security, and runner | 130 | 2 | 0 | 0 | 42.79 s | NOT ACCEPTED locally; both failures require a user-systemd bus |
| Pre-final-repair selected functional baseline | 416 | 0 | 0 | 5 deliberately deselected host-only tests | 76.92 s | Historical local baseline; current complete Hostinger rerun required |
| Full non-browser collection | 545 | 13 | 16 | 20 skipped | 79.30 s | NOT ACCEPTED locally; 29 failures/errors plus 20 skips are environment/reference-bound as inventoried below |
| Current browser acceptance | 0 | 0 | 0 | Not run | — | UNAVAILABLE locally because Python Playwright/Chromium is absent |

The five deliberately deselected tests in the historical 416-test functional
selection are two user-systemd/bubblewrap tests and three clean-B `strace`
tests. The current focused runs above execute rather than deselect those cases:
three are blocked by this container's ptrace policy and two by its missing user
systemd bus. They remain mandatory Hostinger gates.

The 29 failures/errors in the full non-browser collection are retained exactly
as test outcomes. The additional 20 skips are also non-passing outcomes and
remain mandatory on Hostinger.

| Environment dependency | Failures/errors |
|---|---:|
| User-systemd bus unavailable | 2 |
| `ptrace`/`strace` prohibited | 3 |
| Sealed R6C0 reference absent under `/opt` | 4 |
| Sealed R6C2R/R6D references absent under `/opt` | 20 |
| **Total** | **29** |

This inventory explains the local result; it does not convert those failures or errors into passes. Hostinger must rerun them with the sealed references and host facilities available.

Current manifest checks pass for the 38-file engine allowlist and the 47-file
deployment package. The deployment rerun also caught and corrected a stale
runtime-config digest embedded in the systemd service before the final package
reseal. Byte integrity does not substitute for runtime, browser, six-session,
or deployment acceptance.

The gateway security suite passes 13/13. Its GET and HEAD redirect regressions
prove an allowlisted backend route cannot make the gateway follow `Location`
to a second authority; the gateway returns a sanitized 502 and the target sees
zero requests.

## New durability regressions

- A forged nonempty `checkpoints.json` can no longer bootstrap a missing or
  empty SQLite checkpoint database to EOF. SQLite is the sole authority once it
  exists; ambiguous mirror-only recovery fails closed. Trusted checkpoint and
  normalized-ledger progress is checked per source against SQLite offset, row,
  and identity coverage, so total deletion, partial multi-source deletion, and
  same-source rollback are refused. The ingestion suite's 127/127 result
  includes those cases plus clean bootstrap, forged EOF, legitimate-database
  mirror rewrite, and absent/empty mirror with missing/empty SQLite cases.
- The uploaded August 20 sample exposed schedule-dependent publication of a
  still-provisional terminal dependency group. Regular refresh now leaves the
  provisional GUI/state live while deferring that group's mutable lifecycle,
  participation-transition, and episode-scoped cross-layer rows. Finalization
  publishes the complete canonical snapshot idempotently. The 111/111
  orchestrator result includes periodic-versus-one-shot, restart, and
  post-write-failure identity tests.

## Required Hostinger completion gates

| Gate | Current standing |
|---|---|
| Full repository regression with sealed `/opt` references | `PENDING_HOSTINGER_EVIDENCE` |
| All host-only user-systemd/bubblewrap tests | `PENDING_HOSTINGER_EVIDENCE` |
| All `strace`/clean-B file-open tests | `PENDING_HOSTINGER_EVIDENCE` |
| Current-source Chromium/browser and geometry tests | `PENDING_HOSTINGER_EVIDENCE` |
| Focused all-nine incremental schedules | `PENDING_HOSTINGER_EVIDENCE` |
| Full six-session all-nine equivalence | `PENDING_HOSTINGER_EVIDENCE` |
| Restart, partial-line, rotation, replay, and transition-boundary host runs | `PENDING_HOSTINGER_EVIDENCE` |
| Health/readiness and external deployment probes | `PENDING_HOSTINGER_EVIDENCE` |

The selected local tests cover callback durability, ingestion, orchestration, API behavior, GUI projection, restart/replay logic, manifest enforcement, and gateway security. The exact host-dependent and end-to-end cases above remain mandatory and may not be inferred from the local pass.

## Historical evidence

The following results were produced at earlier source checkpoints. They are useful regression history only and are not current acceptance evidence:

- 289 passed, 0 failed, 0 skipped in 62.29 s at a prior correctly provisioned checkpoint.
- 135/135 R6D-parity engine/GUI/API/browser tests at GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`.
- Focused all-nine v12: 21/21 components, 8/8 ledgers, 9/9 schedules, 9/9 invariant groups, 72/72 checkpoint rows, and 2/2 recovery probes.
- Earlier 216/216 and 151/151 targeted gates at their respective pre-final-review source states.
- Full-six v6 produced exact A/B baselines and reference surfaces before the
  one-record schedule exposed 898 ingestion plus 898 analytical out-of-order
  refusals. The run was interrupted and rejected; none of it is final evidence.
- The causal-backlog repair then passed its semantic hourly-peer regression,
  31/31 harness tests, and 116/116 ingestion/orchestrator/harness tests in
  14.31 seconds (14.60 seconds wall) at 137,536 KiB peak RSS.

Source, tests, runtime closure, and package bytes changed after those checkpoints. None of those counts closes a current Hostinger gate.

## Final acceptance summary

Local source verification is sufficient for handoff, not release. Final aggregate status is:

`PENDING_HOSTINGER_COMPLETE_REGRESSION_EQUIVALENCE_BROWSER_AND_DEPLOYMENT_EVIDENCE`
