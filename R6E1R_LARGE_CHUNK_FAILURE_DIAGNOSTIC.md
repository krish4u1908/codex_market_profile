# R6E1R large-chunk periodic-evolution failure diagnostic

## Scope and provenance

- Remote evidence head: `c990b8c9c460d6c37cb0aa195807529af19b8d71`
- Tested implementation: `19c5489f9845f1325da1e1f6e3d9118b95bd959b`
- Focused result: 8/9 schedules passed; elapsed `3401.8550905559678` seconds.
- Retained evidence: `<HOST_OUTPUT_ROOT>` and `<HOST_WORK_ROOT>` were read only. No equivalence test was restarted, and no output/work root was modified.
- The failed schedule was sealed with `snapshot_removed_after_seal=true`. Its detailed snapshot was intentionally removed by the harness, so row-level IDs, fields, timestamps, and ledger-specific counts are not present in the retained evidence. This report does not invent them.

## Exact failure evidence

The comparison's `differences=2` is the sum of two comparator-level conditions:

1. `ANALYTICAL_LEDGER_HASH_MISMATCH`: canonical ledger hash `27466e2caaa730b7a4999be7f6b413f418e3fcd45ff5fd3b34a214350d7613a1` versus schedule ledger hash `9f72c051becc98e50e7f85a3b7024463ccf9020019309258ddb023bc742753f3`. Classification: aggregate immutable-ledger identity/content mismatch. Because the detailed failed-schedule snapshot was removed, the affected ledger/artifact, deterministic analytical IDs, row counts, first divergent event, expected/actual canonical fields, and whether individual rows are missing, extra, or same-ID/different-content are not recoverable without a prohibited rerun.
2. `PERIODIC_EPISODE_EVOLUTION_NOT_EXERCISED`: classification: schedule-exercise counter failure. Five non-empty analytical refreshes occurred, four revisited the same session, lifecycle-exit publications changed four times, but episode-end evolution publications changed zero times.

Terminal semantic state is equal on both sides: canonical and schedule semantic SHA-256 are both `68070652aaa24a54b3fb30649e7869731f0c37835d59cc1e315e332502d7cb69`. Analytical refusals are `0/0`. Thus terminal semantics agree while immutable publication history differs.

No per-refresh timestamps or episode-open/closure publication counts were retained. The available counters are: analytical refreshes `5`, non-empty refreshes `5`, repeated-session refreshes `4`, episode-end evolutions `0`, lifecycle-exit evolutions `4`, restarts `0`, checkpoint restarts `0`, future joins `0`, timestamp backdating `0`, duplicate analytical IDs `0`, synchronization-tolerance violations `0`, checkpoint failures `0`, analytical refusals `0`, and source mutations `0`.

The schedule exposed 46,550 records (33,326,536 bytes) in eight chronological groups of `[5422, 5761, 5769, 5793, 5847, 5934, 5978, 6046]` records. The maximum exposure was 4,194,304 bytes and maximum complete-record group was 4,194,302 bytes. Five fractional refresh thresholds for 46,550 records are `[1, 11638, 23275, 34912, 46550]`; a refresh occurs after the containing complete group is consumed. Exact boundary receipt timestamps were not retained.

## Callback and refresh sequence

For each chronological group, the harness appends complete source records, calls `poll()` to expose the causal prefix, then calls `periodic_analytical_flush()` whenever exposed-record count crosses a fractional threshold. That function captures immutable closure annotations, conditionally finalizes earlier sessions, calls `orchestrator.flush()`, and compares episode-end and lifecycle-exit annotations before/after. This fixture contains one focused session, so no earlier session is eligible for intermediate finalization. Final drain and `snapshot(sessions)` perform terminal finalization.

The failed schedule had eight harness polls and five intermediate refreshes. The retained seal has no refresh timestamps and no counts for episode-open or closure publications. Lifecycle exits evolved four times; episode-end closures evolved zero times.

## Exercise counters for all nine schedules

| Schedule | Polls | Restarts | Checkpoint restarts | Split-line / empty polls | Refresh / repeat / episode / lifecycle | Result |
|---|---:|---:|---:|---:|---:|---|
| original_source_chunks | baseline source chunks | 0 | 0 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| one_record_per_increment | 46,550 | 0 | 0 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| deterministic_variable_chunks | 6,312 | 0 | 0 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| boundaries_inside_jsonl_lines | 59 | 0 | 0 | 17 / 0 | 0 / 0 / 0 / 0 | PASS |
| empty_repeated_polls | 42 | 0 | 0 | 0 / 34 | 0 / 0 / 0 / 0 | PASS |
| multiple_checkpoint_restarts | 8 | 7 | 7 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| analytical_boundary_restarts | 91 | 6 | 0 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| hourly_file_rotation | 395 | 0 | 0 | 0 / 0 | 0 / 0 / 0 / 0 | PASS |
| large_chronological_chunks | 8 | 0 | 0 | 0 / 0 | 5 / 4 / 0 / 4 | FAIL |

Every passing schedule has the canonical terminal semantic and ledger hashes. The nearest passing schedule, `hourly_file_rotation`, exercises six hourly boundaries and 395 polls, but no intermediate analytical refresh; it therefore proves rotation/path equivalence, not periodic immutable-publication equivalence. The other eight pass because they finalize analytically at the terminal boundary and do not invoke the failing intermediate-publication path.

## Source responsibility at tested commit

Line references are for tested implementation `19c5489f9845f1325da1e1f6e3d9118b95bd959b`.

- Large-chunk schedule definition: `scripts/run_r6e1r_equivalence.py:442-444` (`line_groups=(8192,)`, `analytical_flush_events=5`).
- Fractional refresh thresholds: `scripts/run_r6e1r_equivalence.py:2691-2704`.
- Periodic analytical refresh and accounting: `scripts/run_r6e1r_equivalence.py:2966-3070`.
- Pending-group ingestion, polling and threshold callbacks: `scripts/run_r6e1r_equivalence.py:3080-3168`; chronological grouping: `3248-3278`; terminal drain/snapshot: `3279-3294`.
- Exercise acceptance: `scripts/run_r6e1r_equivalence.py:4802-4971`, with the large-schedule episode requirement at `4918-4970` and code emission at `4950`.
- Final comparison/difference arithmetic: `scripts/run_r6e1r_equivalence.py:4974-5011`.
- Runtime flush/finalization: `src/banknifty_market_profiler/r6e/orchestrator.py:1448-1485` and `1495-1544`.
- Immutable publication and append-once identity: `src/banknifty_market_profiler/r6e/orchestrator.py:2727-2772` and `2988-3028`.

## Root-cause classification and repair proposal

Confirmed category: **D — compound demonstrated cause**.

The exercise failure is category C in isolation: the callback occurred five times, but acceptance equates `episode_end_update_count == 0` with a missing exercise even though this single-session fixture may provide no episode-closure evolution opportunity at those fixed global thresholds. Accounting is not opportunity-aware. Separately, the unequal aggregate immutable-ledger hash proves schedule-dependent publication history despite terminal semantic equality. Because the failed detailed snapshot was removed, retained evidence cannot honestly assign that aggregate mismatch to a particular ledger row or conclusively classify the runtime portion as category A.

A source repair is required at minimum in the harness: schedule refresh boundaries around an observed eligible episode evolution (or record explicit eligible-opportunity counts), and require evolution only when an opportunity exists. Preserve the separate immutable-ledger equality requirement. The smallest regression should construct one session with a known open episode, refresh before and after an evolution/closure boundary, assert callback count and opportunity count, assert exactly-once deterministic publication, and assert identical terminal semantic and immutable-ledger hashes against chronological batch. It must also cover a no-opportunity fixture where zero episode evolution is accepted but the callback is still proven.

The aggregate ledger mismatch needs a retained-detail diagnostic test that preserves only sanitized per-ledger row counts, IDs, and semantic hashes on failure. That test should identify the first differing immutable publication without retaining raw records. No analytical/runtime repair should be selected until that evidence identifies the responsible ledger.

## Reproduction identity

Sanitized command:

```text
PYTHONPATH=src <PYTHON> -B -u scripts/run_r6e1r_equivalence.py --data-root <FOCUSED_FIXTURE_ROOT>/collector --authorized-focused-fixture-root <FOCUSED_FIXTURE_ROOT>/collector --output-root <HOST_OUTPUT_ROOT> --work-root <HOST_WORK_ROOT> --keep-work --config configs/r6e_shadow.json --stack-config <FOCUSED_CONFIG_ROOT>/stack.json --inventory-config <FOCUSED_CONFIG_ROOT>/inventory.json --sessions 2026-08-19 --schedules original_source_chunks one_record_per_increment deterministic_variable_chunks boundaries_inside_jsonl_lines empty_repeated_polls multiple_checkpoint_restarts analytical_boundary_restarts hourly_file_rotation large_chronological_chunks --schedule-profile required --skip-references --no-expected-count-gate
```

- Configuration SHA-256: `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031`
- Engine SHA-256: `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`
- Engine-manifest SHA-256: `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`
- Deployment-manifest SHA-256: `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1`
- Package SHA-256: `d68f22217f1dfb75817ebb9b7cb6af0d21306cf1081b7d222c6ecca130978380`

No focused/full-six test was restarted, no deployment or service was changed, and no tag was created.
