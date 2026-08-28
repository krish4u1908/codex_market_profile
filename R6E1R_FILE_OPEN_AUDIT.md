# R6E1R File-Open Audit Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

## Terminal infrastructure stop

The operator stop applied the v9 runtime mask at `20:39:00.999`; systemd
recorded a client-requested `SIGINT` at `20:39:01` and client-requested
`SIGTERM` at `20:39:06`. No OOM kill occurred, swap use was zero, and the
observed peak was 14.5 GiB. The v9 evidence, work, and control roots were
externally deleted after the operator stop. A post-stop search found zero surviving alternate-schedule bundles,
no bundle marker, and no terminal all-gates summary.

The v9 baseline source/audit observations below were independently observed
and pushed before deletion; they are not surviving final all-nine audit
artifacts. A fresh run requires an explicit uninterrupted root-agreed window
and must not evade an active root operator. Deployment was not performed and
no verified tag was created.

## Acceptance rule

Incremental A and clean chronological B may read only selected authoritative
raw/projection roots, their independent state/output roots, verified repository
code/configuration/manifests, and required operating-system/runtime libraries.
They may not consume inherited R2-R6 analytical tables, unrelated derived
CSV/JSONL/Parquet/Feather inputs, secrets, or credentials. Frozen R6C2R/R6D
packages may be opened only after A and B seal and only as comparators.

Unknown external data-like paths fail closed. Requested and resolved paths must
remain distinguishable, descriptor reuse must not collapse provenance, and
every selected source must have measured coverage. An unmeasured/defaulted
counter is a failure, not a zero.

## Accepted focused audit

The fresh post-repair August 19 all-nine run completed its measured runtime-open
audit at the current engine commit.

| Measure | Current value | Result |
|---|---:|---|
| Total audit rows | 2,508 | PASS |
| Runtime-open rows | 2,499 | PASS |
| Aggregated observed runtime opens represented | 1,190,240 | PASS |
| Source-inventory rows | 8 | PASS |
| Fixture-manifest rows | 1 | PASS |
| Prohibited runtime opens | 0 | PASS |
| Unmeasured runtime-open rows | 0 | PASS |
| Derived analytical input opens | 0 | PASS |
| Source mutations | 0 | PASS |

The focused run also passed 21/21 component rows, 8/8 ledger rows, 9/9
causality groups, 9/9 schedules, 16/16 bundle-storage rows, 72/72 checkpoint
rows, 2/2 recovery probes, and 8/8 source identities. Its terminal summary
SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
Those figures are accepted for the focused fixture only; they do not substitute
for the mandatory full-six runtime audit.

## Observed v9 full-six baseline standing

Before root deletion, fresh v9 preflight independently established:

- 141/141 authoritative source identities rehashed unchanged;
- 139 byte-exact projection files;
- 746,890 selected complete records;
- six evaluation and eight causal sessions;
- zero malformed selected records and zero projection-time source mutations;
- projection source-comparison SHA-256
  `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56`.

Canonical incremental A and independent clean B are sealed. Their canonical
components pass 21/21, ledgers pass 8/8, and causality groups pass 9/9 with all
comparison/safety counters zero. Frozen package reads occurred after the A/B
seals and their 30/30 R6C2R and 180/180 R6D comparison rows pass.

These retained observations confirm source identity and analytical equivalence
for the original-source baseline only. They do **not** provide the final
aggregated runtime-open audit across all eight alternate schedules.

## Blocked full-six audit gates

| Scope | Measured audit standing |
|---|---|
| Incremental A original-source baseline | Observed analytically; root deleted; no terminal audit aggregation |
| Independent clean B and child processors | Observed analytically; root deleted; no terminal audit aggregation |
| One record per increment | BLOCKED; no surviving bundle |
| Deterministic variable chunks | BLOCKED; no surviving bundle |
| Boundaries inside JSONL lines | BLOCKED; no surviving bundle |
| Empty/repeated polls | BLOCKED; no surviving bundle |
| Multiple checkpoint restarts | BLOCKED; no surviving bundle |
| Analytical transition restarts | BLOCKED; no surviving bundle |
| Hourly file rotation | BLOCKED; no surviving bundle |
| Large chronological chunks | BLOCKED; no surviving bundle |
| Final source/reference inventory metadata | BLOCKED; no terminal aggregation |
| Final prohibited/unmeasured/failed-source counters | BLOCKED; no terminal summary |

No current-engine totals are claimed for full-six audit rows, represented
opens, required-source rows, schedule scopes, or classification buckets. A
fresh verifier must exit 0 and publish an independently hashed final audit.

## Regression closure for the auditor

The fully provisioned post-repair repository suite passed 660/660 in 118.03
seconds (1m58.43 wall), with zero failure, error, skip, or deselection and peak
RSS 671,340 KiB. It retains auditor coverage for child-process tracing,
unknown-path refusal, required-source enforcement, package integrity,
same-descriptor reuse, symlink/tamper defenses, and fail-closed measured-count
validation. Regression success validates the mechanism; only a fresh terminal
artifact can establish its full-six runtime result.

## Historical results excluded from current acceptance

The `81b0836fe50939246ae210bb62780ac4e163e100` full-six run recorded an
8,315-row audit representing 14,100,048 opens with zero prohibited/unmeasured
rows. Those numbers predate the authenticated sparse-context repair and are
retained only as historical evidence. They must not populate the post-repair
acceptance table or be quoted as the current full-six result.

Likewise, focused packages with parent-only hooks, defaultable measurement
counters, incomplete child coverage, or pre-current package seals remain
rejected. Externally interrupted/deleted v2-v8 full-six attempts did not
publish a terminal current-engine audit and contribute no accepted totals.

## Remaining boundary

Final file-open acceptance requires a fresh uninterrupted run to publish all
marker-last schedule bundles, the final source/reference inventory, and one terminal audit
whose prohibited opens, unmeasured rows, failed required-source rows, and
derived analytical inputs are all zero. Preload and deployment activity may
not be used to fill this blocked analytical gate.
