# R6E1R Six-Session Equivalence Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **NOT STARTED — CURRENT-HEAD FOCUSED GATE FAILED**

## Current-head stop record

Verification commit `19c5489f9845f1325da1e1f6e3d9118b95bd959b`
passed the complete 636-test regression and sealed-package checks, but the
fresh focused all-nine prerequisite failed
`large_chronological_chunks` with
`PERIODIC_EPISODE_EVOLUTION_NOT_EXERCISED`. The focused terminal semantic
state matched and the baseline component, ledger, causality, runtime-open, and
source-integrity matrices were otherwise exact, but one required schedule is
still a failure. Therefore no current-head full-six run was started and none
of the frozen-count or equality cells below is promoted.

Current pushed repair commit: `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.

## Evaluation contract

The final run must process these evaluation sessions from the complete raw root:

- 2026-08-11
- 2026-08-12
- 2026-08-13
- 2026-08-18
- 2026-08-19
- 2026-08-20

Predecessor sessions are discovered causally from raw bytes. August 17 remains present for canonical rejection and is never forced into the accepted predecessor chain. Derived R2-R6 analytical tables are prohibited as A/B input.

Incremental A must use the production ingestor callback path, durable checkpoints, restarts, and explicit finalization. Clean B must start from a new state root and run the repository-owned chronological batch processors against the same selected raw bytes. Frozen reference packages may be opened only after both A and B are sealed.

## Required schedules

| Schedule | Required exercise evidence | Final result |
|---|---|---|
| Original source chunks | All evaluation files visible before the first poll; native bounded checkpoint progress measured | `PENDING_FINAL_EVIDENCE` |
| One record per increment | Every selected outer JSON record exposed in a one-record increment | `PENDING_FINAL_EVIDENCE` |
| Deterministic variable chunks | Configured deterministic size cycle exercised over the stream | `PENDING_FINAL_EVIDENCE` |
| Boundaries inside JSONL lines | Partial-line deferral and completion measured at configured boundaries | `PENDING_FINAL_EVIDENCE` |
| Empty/repeated polls | Configured repeated empty polls measured with no publication change | `PENDING_FINAL_EVIDENCE` |
| Multiple checkpoint restarts | Every configured checkpoint restart measured | `PENDING_FINAL_EVIDENCE` |
| Analytical transition restart | Durable append, restart, retry, and exactly-one identity measured | `PENDING_FINAL_EVIDENCE` |
| Hourly rotation | A new hourly path introduced after earlier polling in each applicable stream | `PENDING_FINAL_EVIDENCE` |
| Large chronological chunks | Configured large chronological groups measured | `PENDING_FINAL_EVIDENCE` |

## Frozen count contract

| Artifact | Required count |
|---|---:|
| Inventory | 255 |
| Divergence episodes | 65 |
| GREEN | 41 |
| RED | 24 |
| Dependency groups | 65 |
| Dependent retriggers | 14 |
| Lifecycle transitions | 14,201 |
| Dense resolution observations | 164,668 |
| Response observations | 65 |
| Dense participation | 69,225 |
| Participation transitions | 32,068 |
| Participation summaries | 65 |
| Compatibility snapshots | 65 |
| Cross-layer material transitions | 60,659 |

## Final equality matrix

| Measure | Required | Final value |
|---|---:|---|
| Stream-versus-batch differences | 0 | `PENDING_FINAL_EVIDENCE` |
| Canonical reference mismatches | 0 | `PENDING_FINAL_EVIDENCE` |
| Analytical ledger identity/content differences | 0 | `PENDING_FINAL_EVIDENCE` |
| GUI-visible state differences | 0 | `PENDING_FINAL_EVIDENCE` |
| Future joins | 0 | `PENDING_FINAL_EVIDENCE` |
| Synchronization tolerance violations | 0 | `PENDING_FINAL_EVIDENCE` |
| Timestamp backdating | 0 | `PENDING_FINAL_EVIDENCE` |
| Duplicate analytical IDs | 0 | `PENDING_FINAL_EVIDENCE` |
| Analytical refusals | 0 | `PENDING_FINAL_EVIDENCE` |
| Prohibited runtime opens | 0 | `PENDING_FINAL_EVIDENCE` |
| Source mutations | 0 | `PENDING_FINAL_EVIDENCE` |

## Evidence discipline

Focused v8 is not final evidence even though it reported equality: subsequent review found append-only ledger, GUI/as-of, observed-open, and schedule-exercise gaps.

Focused v12 passed its historical commit, but it predates the current
durable-authority, authenticated-dependency, gateway, and 38-file engine seal.
Its summary SHA-256 remains diagnostic provenance only and does not populate a
current focused or six-session result.

A fresh six-session v3 diagnostic sealed exact A/B baselines and frozen counts but was deliberately stopped before schedules after a reference-only availability-surface mismatch. The historical-availability comparator repair at pushed head `89f135064417ba537dc302027442a110477b5d03` passed 29/29 targeted tests; a separate preserved-material check matched incremental A and batch B 24/24 rows each against Reference C with zero remainder. The diagnostic remains rejected; the accepted six-session report must name the new sealed output root, seal hashes, command line, engine source identity, configuration identity, elapsed time, and peak RSS:

Fresh v6 subsequently proved that baseline and both reference surfaces were exact: 21/21 A/B components, 8/8 append-only ledgers, 9/9 invariants, 30/30 R6C2 rows, and 180/180 R6D rows passed with all frozen counts exact. It is still rejected because the explicit-path `one_record_per_increment` harness omitted a visible checkpoint-lagging raw peer and manufactured 898 ingestion plus 898 analytical out-of-order refusals. The harness now repolls only changed paths plus visible checkpoint remainders and gates the post-drain remainder at zero. A byte-exact sparse-coordinate/hourly-peer regression fails the former scheduler semantically and passes the repair. None of the final cells above is populated from v6; the current pinned six-session unit is running and its result remains pending.

Full-six-v1 was stopped and rejected before the remaining schedules because the
shared clean-B GUI builder had already failed focused merged-v2: it projected
11,486 dense resolution observations where live A correctly exposed 1,294
material transitions. Commit `c42e703...` repairs only that independent clean
comparator. The complete harness passes 36/36, the complete repository passes
636/636 with zero failures/skips, and an independent review found no frozen-rule,
clock, dense-artifact, ID, or ledger change. Those regression results do not
promote any full-six value.

`r6e1r-six-merged-v2.service` has been running from the pinned pushed repair
commit since 2026-08-27 15:03:13 IST. Its output and trace must seal and pass all
matrices before any final cell is populated.

- Final output root: `PENDING_FINAL_EVIDENCE`
- Incremental A seal SHA-256: `PENDING_FINAL_EVIDENCE`
- Clean B seal SHA-256: `PENDING_FINAL_EVIDENCE`
- Current pinned engine hash: `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`; accepted-run record: `PENDING_FINAL_EVIDENCE`
- Configuration hash: `PENDING_FINAL_EVIDENCE`
- Command: `PENDING_FINAL_EVIDENCE`
- Exit status: `PENDING_FINAL_EVIDENCE`
- Elapsed time: `PENDING_FINAL_EVIDENCE`
- Parent/child peak RSS: `PENDING_FINAL_EVIDENCE`

Per-artifact status belongs in [R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md](R6E1R_ARTIFACT_EQUIVALENCE_MATRIX.md).
