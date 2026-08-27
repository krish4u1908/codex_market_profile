# R6E1R File-Open Audit Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT FILE-OPEN REGRESSION PASS — FRESH A/B RUNTIME AUDIT PENDING**

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

## Acceptance rule

Incremental A and clean B may read only:

- the authorized raw/projection roots selected for the run;
- their own independent state/output roots;
- repository code, configuration, and verified manifests;
- operating-system/runtime libraries required to execute.

They must not open inherited R2-R6 analytical tables, old research outputs, unrelated derived CSV/JSONL/Parquet/Feather inputs, secrets, or credentials. Frozen R6C2R/R6D reference packages may be opened only after A and B are sealed and only for comparison.

## Rejected evidence

Focused v8 reported prohibited opens zero, but an independent audit rejected that result because:

- the Python audit hook observed only the parent interpreter, not the three clean-B subprocesses;
- only self-reported inventory/stack open CSVs were imported, and the layers subprocess lacked equivalent child-open evidence;
- imported observed counts could be defaulted rather than measured;
- unknown external paths could fall through to a permitted runtime-library classification;
- clean B lacked a hard required-every-source-open coverage gate.

Therefore the v8 zero must not appear as the final file-open result.

## Current regression evidence

The pushed repair commit passed the complete repository regression 636/636 with
zero failures or skips. That fully provisioned invocation includes the host-only
ptrace/strace, clean-B child observation, required-source, unknown-path
fail-closed, and package/refusal tests that earlier containers could not run.
Its log and timing SHA-256 values are
`a1132553080052c44424e8c936a33a8b7f548661b11390460fd0492463050bef`
and `c2127eca2426ccb1a92a48875aa1d8ad2939e2be5ccf99bbaed921de8e175681`.

This closes the current regression gate for the instrumentation. It does not
substitute test-fixture observations for the measured focused/full-six runtime
audit. Focused-v3 and full-six-v2 have been running from pinned commit
`c42e703...` since 2026-08-27 15:03:13 IST; all final values below remain
pending until accepted run seals and traces exist.

## Historical focused-v12 result

Focused v12 recorded the values below for its historical commit. The earlier
local container prohibited ptrace, so its three clean-B strace tests could not
run. Current regression now proves those tests on the authorized host, but these
historical measurements still do not populate any current-commit final cell;
the instrumented focused and full-six paths must finish.

| Scope | Audit rows | Summed observed opens | Required-source rows | Prohibited | Unmeasured |
|---|---:|---:|---:|---:|---:|
| Incremental A baseline | 88 | 310 | 16 | 0 | 0 |
| Clean batch B | 1,501 | 1,712 | 8 | 0 | 0 |
| Required focused schedules and recovery probes | 742 | 378,822 | 128 | 0 | 0 |
| A/B authorized-source inventory | 8 | 0 | — | 0 | 0 |
| Same-run exact-copy classification summary | 1 | 0 | — | 0 | 0 |
| Total | 2,340 | 380,844 | 152 | 0 | 0 |

Focused file-open audit SHA-256: `cdfa9b5a380992a3d49c4d7065e6237a9b90d5608a20f3cdacb11719fb979c48`.

The 2,340 figure is the number of aggregated evidence rows, not the observed-open count. These focused values must not populate the final six-session table below.

## Required final instrumentation

| Requirement | Final evidence |
|---|---|
| Parent incremental-A opens observed | Instrumentation regression PASS; fresh A/B observation count pending |
| Every clean-B child process observed or independently traced | PASS in current 636/636 regression; fresh A/B trace pending |
| Every required A source opened | Required-source regression PASS; fresh A/B coverage rows pending |
| Every required B source opened | Required-source regression PASS; fresh A/B coverage rows pending |
| Unknown external data-like path fails closed | PASS in current 636/636 regression |
| Same-run B intermediates explicitly classified | Classification regression PASS; fresh A/B rows pending |
| Post-seal reference opens separately classified | Classification regression PASS; fresh A/B rows pending |
| Prohibited open count | `PENDING_FINAL_EVIDENCE` — required 0 |
| Unmeasured required rows | `PENDING_FINAL_EVIDENCE` — required 0 |
| Audit evidence SHA-256 | `PENDING_FINAL_EVIDENCE` |

The recorder caches path resolution/classification by stable requested path so the one-record schedule does not repeat a realpath walk for every read open. The audit output aggregates counts by scope/requested/resolved path without discarding evidence of child-process or unknown paths.

## Final result

| Scope | Observed opens | Required source coverage | Prohibited | Unmeasured | Status |
|---|---:|---:|---:|---:|---|
| Incremental A | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Clean batch B | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Required schedules | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Post-seal references | `PENDING_FINAL_EVIDENCE` | Not analytical input | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
