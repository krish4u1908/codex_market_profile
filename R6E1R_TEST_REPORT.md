# R6E1R Test Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **COMPLETE REGRESSION 636/636 — FOCUSED-V3/FULL-SIX-V2 RUNNING — DEPLOYMENT PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

No failing or skipped test may be weakened, deselected, reclassified, or omitted to obtain acceptance. Environment-blocked tests are reported as non-passes until they pass on the authorized host.

## Current pushed-commit evidence

| Suite | Passed | Failed | Errors | Skipped/deselected | Elapsed | Standing |
|---|---:|---:|---:|---:|---:|---|
| Complete repository regression | 636 | 0 | 0 | 0 | 129.36 s pytest; 2m09.72 wall | CURRENT PASS |
| Equivalence harness after clean-GUI repair | 36 | 0 | 0 | 0 | Included in complete run | CURRENT REGRESSION PASS; fresh A/B pending |
| Chromium/Playwright fixture | 1 | 0 | 0 | 0 | 4.86 s | CURRENT FIXTURE PASS; zero console/page errors; not deployed-live |

Peak process RSS for the complete run was 685,556 KiB. Its retained log and
timing SHA-256 values are
`a1132553080052c44424e8c936a33a8b7f548661b11390460fd0492463050bef`
and `c2127eca2426ccb1a92a48875aa1d8ad2939e2be5ccf99bbaed921de8e175681`.
No test was deselected, skipped, weakened, or reclassified. The run includes and
closes the current host-only user-systemd/bubblewrap, ptrace/strace clean-B,
sealed-reference, gateway, API, and fixture-browser regression gates.

Current manifest checks pass for the 38-file engine allowlist and the 47-file
deployment package. The deployment rerun also caught and corrected a stale
runtime-config digest embedded in the systemd service before the final package
reseal. Byte integrity and complete regression do not substitute for fresh
focused/full-six equivalence or installed/deployed-live acceptance.

The current complete suite includes the gateway security tests. Their GET and
HEAD redirect regressions
prove an allowlisted backend route cannot make the gateway follow `Location`
to a second authority; the gateway returns a sanitized 502 and the target sees
zero requests. A direct bounded-memory regression streams an
8-MiB-plus-one-byte upstream body and proves the gateway returns the sanitized
502 `UPSTREAM_RESPONSE_LIMIT`; gateway security is 14/14.

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
- Focused merged-v2 exposed one clean-B GUI-comparator defect after exact
  analytical components and eight ledgers: clean B projected 11,486 dense
  resolution observations instead of live A's 1,294 material transitions.
  Focused merged-v2 and full-six-v1 were stopped and rejected. Commit
  `c42e703...` repairs only that clean comparator; independent review found no
  frozen-rule, clock, dense-artifact, ID, or ledger change. The repaired harness
  passes 36/36.

## Required authorized-host completion gates

| Gate | Current standing |
|---|---|
| Full repository regression with sealed `/opt` references | PASS — 636/636, zero failed/skipped |
| All host-only user-systemd/bubblewrap tests | PASS within complete regression |
| All `strace`/clean-B file-open tests | PASS within complete regression; actual fresh-run traces pending |
| Current-source Chromium/browser and geometry fixture | PASS — 1/1 in 4.86 s; deployed browser pending |
| Focused all-nine incremental schedules | Focused-v3 running from pinned `c42e703...` since 2026-08-27 15:03:13 IST; `RUNNING_RESULT_PENDING` |
| Full six-session all-nine equivalence | Full-six-v2 running from pinned `c42e703...` since 2026-08-27 15:03:13 IST; `RUNNING_RESULT_PENDING` |
| Restart, partial-line, rotation, replay, and transition-boundary unit regressions | PASS within 636/636; measured fresh A/B schedules pending |
| Health/readiness and external deployment probes | `PENDING_AUTHORIZED_HOST_EVIDENCE` |

The current complete tests cover callback durability, ingestion, orchestration,
API behavior, GUI projection, restart/replay logic, manifest enforcement,
gateway security, and host-only facilities. The running raw-data equivalence and
all installed-service/deployed-live cases remain independently mandatory.

## Historical evidence

The following results were produced at earlier source checkpoints. They are useful regression history only and are not current acceptance evidence:

- 289 passed, 0 failed, 0 skipped in 62.29 s at a prior correctly provisioned checkpoint.
- A later pre-repair non-browser collection recorded 545 pass, 20 skip, 13 fail,
  and 16 error; its missing-facility/reference cases are superseded by the
  current fully provisioned 636/636 result, not retroactively relabelled.
- 135/135 R6D-parity engine/GUI/API/browser tests at GUI milestone `5efe70e9685b98556ae1ad9a860912c7bb1513fc`.
- Focused all-nine v12: 21/21 components, 8/8 ledgers, 9/9 schedules, 9/9 invariant groups, 72/72 checkpoint rows, and 2/2 recovery probes.
- Earlier 216/216 and 151/151 targeted gates at their respective pre-final-review source states.
- Full-six v6 produced exact A/B baselines and reference surfaces before the
  one-record schedule exposed 898 ingestion plus 898 analytical out-of-order
  refusals. The run was interrupted and rejected; none of it is final evidence.
- The causal-backlog repair then passed its semantic hourly-peer regression,
  31/31 harness tests, and 116/116 ingestion/orchestrator/harness tests in
  14.31 seconds (14.60 seconds wall) at 137,536 KiB peak RSS.

Source, tests, runtime closure, and package bytes changed after those
checkpoints. Only the current 636/636 result closes current regression gates.

## Final acceptance summary

Local source verification is sufficient for handoff, not release. Final aggregate status is:

`COMPLETE_REGRESSION_PASS_FRESH_EQUIVALENCE_AND_LIVE_DEPLOYMENT_PENDING`
# Current-head authorized-host addendum — 2026-08-27

- Tested commit: `19c5489f9845f1325da1e1f6e3d9118b95bd959b`
- Complete repository suite: 636 passed, 0 failed, 0 skipped in 116.45 seconds.
- Host-only closure: 3 runtime-open/strace plus 2 user-systemd/bubblewrap
  tests, 5/5 passed in 1.34 seconds.
- Focused all-nine equivalence: FAIL, eight schedules passed and
  `large_chronological_chunks` failed
  `PERIODIC_EPISODE_EVOLUTION_NOT_EXERCISED` with two differences.
- Baseline A/B: 21/21 components, 8/8 ledgers, and 9/9 invariants exact.
- Zero counters: future joins, tolerance violations, backdating, duplicate
  analytical IDs, analytical refusals, checkpoint failures, prohibited opens,
  unmeasured opens, and source mutations.
- Full-six and deployment: not started by failure policy.
