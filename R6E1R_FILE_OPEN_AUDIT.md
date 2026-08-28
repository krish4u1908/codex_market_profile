# R6E1R File-Open Audit Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR FOCUSED AUDIT PASS; CURRENT FULL-SIX TERMINAL AUDIT
PENDING**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

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

## Persistent v9 full-six standing

The fresh v9 preflight has independently established:

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

These immutable facts confirm source identity and analytical equivalence for
the original-source baseline. They do **not** yet provide the final aggregated
runtime-open audit across all eight alternate schedules.

## Current full-six audit gates

| Scope | Measured audit standing |
|---|---|
| Incremental A original-source baseline | Sealed analytically; terminal audit aggregation pending |
| Independent clean B and child processors | Sealed analytically; terminal audit aggregation pending |
| One record per increment | PENDING terminal v9 bundle |
| Deterministic variable chunks | PENDING terminal v9 bundle |
| Boundaries inside JSONL lines | PENDING terminal v9 bundle |
| Empty/repeated polls | PENDING terminal v9 bundle |
| Multiple checkpoint restarts | PENDING terminal v9 bundle |
| Analytical transition restarts | PENDING terminal v9 bundle |
| Hourly file rotation | PENDING terminal v9 bundle |
| Large chronological chunks | PENDING terminal v9 bundle |
| Final source/reference inventory metadata | PENDING terminal v9 aggregation |
| Final prohibited/unmeasured/failed-source counters | PENDING terminal v9 summary |

No current-engine totals are claimed for full-six audit rows, represented
opens, required-source rows, schedule scopes, or classification buckets until
the persistent v9 process exits 0 and its final audit is independently hashed
and validated.

## Regression closure for the auditor

The fully provisioned post-repair repository suite passed 660/660 in 118.03
seconds (1m58.43 wall), with zero failure, error, skip, or deselection and peak
RSS 671,340 KiB. It retains auditor coverage for child-process tracing,
unknown-path refusal, required-source enforcement, package integrity,
same-descriptor reuse, symlink/tamper defenses, and fail-closed measured-count
validation. Regression success validates the mechanism; only the terminal v9
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

Final file-open acceptance requires persistent v9 to publish all marker-last
schedule bundles, the final source/reference inventory, and one terminal audit
whose prohibited opens, unmeasured rows, failed required-source rows, and
derived analytical inputs are all zero. Preload and deployment activity may
not be used to fill this pending analytical gate.
