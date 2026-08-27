# R6E1R File-Open Audit Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **V2 HOST ACCEPTANCE PENDING — SEE `R6E1R_CURRENT_STATUS.md`**

Current exact v2 evidence is authoritative only in `R6E1R_CURRENT_STATUS.md`; the detailed sections below are acceptance contracts or commit-scoped historical evidence.

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

## Historical focused-v12 result

Focused v12 recorded the values below for its historical commit. The local
sandbox prohibits ptrace, so the three current clean-B strace tests cannot run
here. These values do not populate any current-commit final cell; Hostinger must
rerun the instrumented focused and full-six paths.

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
| Parent incremental-A opens observed | `PENDING_FINAL_EVIDENCE` |
| Every clean-B child process observed or independently traced | `PENDING_FINAL_EVIDENCE` |
| Every required A source opened | `PENDING_FINAL_EVIDENCE` |
| Every required B source opened | `PENDING_FINAL_EVIDENCE` |
| Unknown external data-like path fails closed | `PENDING_FINAL_EVIDENCE` |
| Same-run B intermediates explicitly classified | `PENDING_FINAL_EVIDENCE` |
| Post-seal reference opens separately classified | `PENDING_FINAL_EVIDENCE` |
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
