# R6E1R Final Report — Infrastructure-Blocked Handoff

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED**

This is a blocked handoff, not R6E1R acceptance. The post-repair regression and
focused fixture passed, and persistent v9 independently published a passing
full-six original-source A/B/reference baseline. At 20:39:00.999 IST an
external root/operator transaction runtime-masked the v9 unit, sent
SIGINT/SIGTERM on client request, and then deleted its evidence, work, and
control roots before any alternate-schedule marker or terminal summary existed.
A read-only survivor search found zero `equivalence_summary.json`,
`schedule_resume_contract.json`, or `schedule_bundle.json` files under the
authorized research/home roots.

This repeated the earlier external v2-v8 stop/deletion condition. Continuing
safely requires an explicit root-agreed uninterrupted verification window and
a protected evidence-retention location. Evading the active root operator with
a hidden or renamed high-memory process is not a safe recovery. Terminal
all-nine verification, preload, deployment, live browser/health/readiness, and
external reachability remain unverified. No tag is authorized and no URL was
deployed.

## Current authority and Git state

| Item | Current fact |
|---|---|
| Authorized preservation checkpoint | `065982c2ed49f6e7dad82bf29ed25f62ef78b024` |
| Working branch | `fix/r6e1r-final-live-shadow` |
| Current analytical repair | `e1d67c534bea5c61b0e3d379db7f599de7e1c445` — timezone-aware empty-Index backward-join repair |
| Pushed report head immediately before this edit | `cce61679dfc21ecb2cecd3acc592e8b151c538fe` |
| Remote state before this edit | `origin/fix/r6e1r-final-live-shadow` exactly matched `cce61679dfc21ecb2cecd3acc592e8b151c538fe` |
| Frozen R6C2R tag target | `r6c2r-full-stack-equivalence-verified` -> `9cbe46fea6e3a44f3cf574955f21b5b1ebb6aa96` |
| Frozen R6D tag target | `r6d-offline-gui-verified` -> `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14` |
| Verified R6E1R tag | `NOT_CREATED` |

The complete implemented commit list is intentionally not duplicated as a
manually maintained narrative. At final handoff it must be generated from the
authoritative branch with:

```text
git log --reverse --format='%H %s' 065982c2ed49f6e7dad82bf29ed25f62ef78b024..HEAD
```

That range currently includes the callback/ledger/harness/GUI/deployment work,
repair `e1d67c5...`, and evidence-report commits through `cce6167...`. The
future report/deployment commit hashes, final remote-head check, clean-worktree
check, and any tag decision remain pending and must not be guessed here.

## Current sealed implementation identities

| Closure or template | Result / SHA-256 |
|---|---|
| Engine allowlist | PASS — 38/38 files |
| Engine JSON manifest | `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210` |
| Engine aggregate | `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947` |
| Deployment allowlist | PASS — 47/47 files |
| Deployment JSON manifest | `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391` |
| Deployment package aggregate | `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949` |
| Runtime-configuration identity | `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41` |
| Raw runtime-config template | `cbcf9f43befa4b18b4798240c18d841f1629af7a015c538c8ff254e01b6957ad` |
| Backend service template | `153a2b493b864f9442fda8d94d0c6c2cececfde87bc9cdbfcb78d99c9aa9e7ac` |
| Gateway service template | `2b47c302ca3491686cd3b73d77f9190aecd413573676035923945147c49e5542` |

Both checked-in manifest companion checks pass. These identities authorize no
installation by themselves; the eventual runtime must reproduce them exactly.

## Current regression and focused production-path evidence

The fully provisioned complete repository suite passed **660/660**, with zero
failures, errors, skips, or deselections. Pytest elapsed was 118.03 seconds;
wall time was 1m58.43s and peak process RSS was 671,340 KiB. The preceding
659-pass/1-failure packaging run is a retained non-pass and is not acceptance
evidence.

The fresh post-repair August 19 focused run passed every required schedule and
callback surface. Its terminal summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.

| Focused gate | Current result |
|---|---:|
| Canonical components | 21/21 PASS |
| Append-only ledgers | 8/8 PASS |
| Causality/display groups | 9/9 PASS |
| Required schedules | 9/9 PASS |
| Storage rows | 16/16 PASS |
| Checkpoint-accounting rows | 72/72 PASS |
| Truncation/replacement recovery probes | 2/2 PASS |
| Source-integrity rows | 8/8 PASS |
| Prohibited / unmeasured runtime opens | 0 / 0 |

The focused audit contained 2,508 rows: 2,499 runtime-open rows, eight
source-inventory rows, and one fixture-manifest row, representing 1,190,240
opens. Stream/batch differences, future joins, synchronization-tolerance
violations, timestamp backdating, duplicate analytical IDs, analytical
refusals, checkpoint failures, source mutations, and prohibited/unmeasured
opens were all zero. Harness elapsed was 3,839.101 seconds; parent/child peak
RSS was 1,730,828/891,172 KiB and cgroup peak memory was 2,965,729,280 bytes.
This focused pass is a prerequisite and does not substitute for terminal
six-session evidence.

## Authoritative raw source and focused sample

The authoritative read-only root
`/opt/banknifty-collector/data-prod-v4` was readable with `raw` and `oi`
streams. The non-Git focused fixture at
`/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205` preserves
complete original JSONL records for 2026-08-19 09:15–12:05 IST, receipt
timestamps, and source-hour identity. Incomplete terminal lines were excluded.

Repository contract discovery selected `NSE:BANKNIFTY26AUGFUT`; it was not
hard-coded. The sample retains 46,550/46,550 selected byte identities: 46,210
raw records and 340 OI outer records, including BankNifty Index, Futures,
Futures OI, CE, and PE evidence. All eight relevant authoritative source files
retained identical pre/post hashes, sizes, and mtimes. The source-hour sample
manifest SHA-256 is
`31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382`.
Raw/sample JSONL is outside Git and must remain uncommitted.

## Persistent v9 six-session observations retained in the pushed handoff

The interrupted verifier was `market-profile-history-verifier-v9.service`,
pinned to a clean detached `e1d67c5...` checkout under invocation
`ce9595fd18b344ab8ab2765ae509f8fa`. It was an offline analytical verifier, not
the live API or GUI service. The baseline values below were independently
hashed and pushed before deletion. Their files no longer survive for final
review and they cannot substitute for an all-nine terminal bundle.

### Raw projection and causal scope

The v9 projection was rebuilt read-only from the authoritative raw root. It
selected 746,890 complete outer JSON records into 139 projection files from 141
authoritative files, representing 34,709,921 complete physical rows and
541,091,186 projected bytes. Construction took 117.675 seconds and peaked at
189,924 KiB RSS. Malformed selected records and observed projection-time source
mutations were zero.

The evaluation sessions are 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-18,
2026-08-19, and 2026-08-20. August 10 and August 17 were selected causally as
context. August 17 remains exactly
`PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`. Contracts were
selected through repository logic; no derived R2-R6 analytical tables were
used as A/B inputs.

| Projection artifact | SHA-256 |
|---|---|
| Raw projection manifest | `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426` |
| Projection provenance | `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0` |
| Pre-run source comparison | `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56` |
| Schedule contract file | `9579ec8a4dc5d3b06e3f0caf6005903a83a12804711aff3f8b01d05ce5663020` |
| Embedded schedule contract | `af10b6130ef38ca42c79be8aad0ebef3df4bbb9494ac974321cd315ae94583d0` |

All 141 source-comparison rows were unchanged at projection time. The distinct
terminal post-run rehash remains pending.

### Sealed original-source incremental A / independent clean B

Incremental A exercised the production callback/checkpoint path. Clean B used
three independently invoked repository-owned chronological processors over the
same selected bytes and a clean root. Both were sealed before the verified
reference packages were opened.

| Measure | Incremental A | Clean B |
|---|---:|---:|
| Selected source files / JSON records | 104 / 543,329 | Same bytes |
| Source bytes / complete physical rows | 396,713,521 / 25,293,503 | Same bytes |
| Elapsed seconds | 5,893.937 | 741.789 |
| Peak RSS KiB | 6,481,416 | 7,153,156 child-process peak |
| Seal SHA-256 | `fa62ace6fc2796c0101e1e9da908725d0ca12da364d971fa336a0868f0a83ce7` | `99322aa74ad4018400d11cc6336ca695c8f2e190ec279067351ef40ff2faa568` |
| Snapshot SHA-256 | `c03d1e3ef195a70df83221897bf7d1e73a63790b46629825ffc3ef3731c5ce87` | `285256f5438eaebd86916aabcee7413aa668e1d8d57a1c4fab281f87dffe2526` |
| Wrapper semantic SHA-256 | `bd8bdbaaeac3db54c289575d7c0d3f3fca73934f0830ab974656ded3c6175527` | `26d16e78e44b3de3849c7af6b73305a92fd6f1df0565276e980f19a40049d1a7` |
| Append-only ledger SHA-256 | `4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65` | `4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65` |

Incremental A sealed 26 state files. Its state-manifest SHA-256 is
`5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173`
and state-tree SHA-256 is
`f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6`.
Checkpoint failures, analytical refusals, undrained causal remainders, dirty or
unexpected sessions, future joins, timestamp backdating, and duplicate
analytical IDs were zero in the sealed A record.

The wrapper semantic hashes differ because the two modes seal different
orchestration surfaces. Canonical equivalence is established by the independent
component, ledger, causality, GUI, and reference projections below, not by
claiming wrapper snapshots are byte-identical.

### Canonical components, ledgers, and causality

The component matrix passes 21/21 with zero A-only rows, B-only rows, field
mismatches, or unexplained remainders.

| Canonical artifact | Incremental A | Clean B | Difference |
|---|---:|---:|---:|
| Synchronized basis | 158,746 | 158,746 | 0 |
| Frozen inventory | 255 | 255 | 0 |
| Divergence episodes (GREEN / RED) | 65 (41 / 24) | 65 (41 / 24) | 0 |
| Dependency groups / dependent retriggers | 65 / 14 | 65 / 14 | 0 |
| Lifecycle transitions | 14,201 | 14,201 | 0 |
| Dense resolution observations | 164,668 | 164,668 | 0 |
| Response observations | 65 | 65 | 0 |
| Dense participation | 69,225 | 69,225 | 0 |
| Participation transitions | 32,068 | 32,068 | 0 |
| Participation summaries / compatibility snapshots | 65 / 65 | 65 / 65 | 0 |
| Frozen cross-layer material transitions | 60,659 | 60,659 | 0 |
| Availability states / GUI-visible sessions | 24 / 6 | 24 / 6 | 0 |

Graceful-degradation extensions also match: 118 Intraday inventory plus 118
linked cross-layer rows, and 21 partial-fixed inventory plus 21 linked
cross-layer rows. The complete live surface therefore has 394 inventory and
60,798 cross-layer rows. These 139 permitted live-extension rows do not alter
the frozen 255/60,659 contract.

The append-only ledger matrix passes 8/8 with zero identity or content
difference: 65 divergence confirmations, 65 dependency/retrigger records,
14,201 lifecycle transitions, 394 inventory-winner transitions, 32,068
participation transitions, 60,798 cross-layer transitions, 72 availability
transitions, and 39 stale-recovery transitions.

The causality matrix passes 9/9 with zero future joins, synchronization-tolerance
violations, timestamp backdating, duplicate analytical IDs, valid timestamps
becoming `NaT`, analytical refusals, GUI clock violations, GUI display-contract
violations, or GUI path-clock violations.

| Baseline matrix | Pass | SHA-256 |
|---|---:|---|
| A/B canonical components | 21/21 | `fd5fad066510b5fe01f5914f55aa3fa2b7fbac9b27af9a9caa4da76b658cf388` |
| Append-only ledger identities | 8/8 | `e68f5f098b6157160b2a27e51c4bc709a6bc0fc25aa71e7fcb39617c8cb77e48` |
| Causality invariants | 9/9 | `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2` |

### Frozen reference comparison

The pinned R6C2R 74-file and R6D 40-file reference-package manifests passed
before comparison. R6C2R passes 30/30 rows with zero target-only,
reference-only, or unexplained rows. R6D GUI comparison passes 180/180 rows:
174,080 target-only rows exactly equal the 174,080 permitted live-extension
rows, with zero reference-only or unexplained rows. Reference-package
verification SHA-256 is
`ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.

| Reference matrix | Pass | SHA-256 |
|---|---:|---|
| R6C2R canonical reference | 30/30 | `0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8` |
| R6D GUI reference | 180/180 | `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467` |

These sealed original-source results establish current scoped values of zero
for stream/batch canonical differences, canonical unexplained mismatches,
ledger identity/content differences, GUI unexplained differences, future
joins, tolerance violations, timestamp backdating, duplicate IDs, and
analytical refusals. They do **not** establish terminal all-schedule values.

## Gates still pending

The original-source A/B baseline is sealed, but its marker-last terminal
schedule bundle and all eight alternate schedule bundles remain unpublished.
No historical schedule result is imported.

| Schedule | Current v9 status |
|---|---|
| Original source chunks | `OBSERVED_BASELINE_PASS; FILES_EXTERNALLY_DELETED` |
| One complete JSONL record per increment | `EXTERNALLY_INTERRUPTED_NO_MARKER` |
| Deterministic variable chunks | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Chunk boundaries inside JSONL lines | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Empty/repeated polls | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Multiple checkpoint restarts | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Restart at analytical transition boundaries | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Hourly file rotation | `NOT_RUN_AFTER_EXTERNAL_STOP` |
| Large chronological chunks | `NOT_RUN_AFTER_EXTERNAL_STOP` |

The following terminal gates also remain pending: fresh/final bundle-storage
validation, the complete checkpoint-accounting matrix, truncation/replacement
recovery, complete full-six runtime file-open audit, post-run hashes for all 141
authoritative sources, terminal all-gates summary, terminal elapsed/peak/output
measurements, and validation of incremental A as the deployment preload.

Until those artifacts pass, the final required values for all-schedule
stream/batch differences, canonical mismatches, future joins, backdating,
duplicate IDs, prohibited runtime opens, source mutations, and preload identity
remain `PENDING_FINAL_EVIDENCE`, even though their sealed baseline scope is
zero.

## GUI, API, and deployment state

Current fixture/browser regression is part of the 660/660 pass and exercises
the fixed-horizon, Intraday-only degradation, and latest/operational GUI
surfaces with zero asserted page or console errors. It is not deployed-browser
evidence.

The package provides only the required read-only `/api/health`,
`/api/readiness`, `/api/status`, `/api/session`, `/api/chart`, `/api/inventory`,
`/api/divergence`, `/api/lifecycle`, `/api/participation`, `/api/transitions`,
`/api/availability`, and `/api/audit` endpoints. It exposes no order, trade,
alert, or write endpoint.

No current `e1d67c5...` backend or gateway is installed or accepted. The
standard deployment units are inactive/dead and runtime-masked with stale
paths. The intended isolated backend is `127.0.0.1:18805`; preferred external
research port `8805` was free at preflight. The public address
`http://200.234.39.232:8805/` is a **candidate only — NOT DEPLOYED OR
VERIFIED**. Local health/readiness, all-six replay, cold-preload RSS, gateway
recovery, largest-response, deployed-browser, public-interface, and independent
off-host checks are pending.

Host UFW has default inbound policy `DROP`, and the current account lacks
firewall/provider authority. If analytics and local isolated deployment pass
but single-port off-host access cannot be enabled or verified, the authorized
terminal classification is
`R6E1R_ANALYTICS_VERIFIED_DEPLOYMENT_BLOCKED`; no verified tag may be created.

## Protected services and collector non-interference

The latest exact refresh retained the protected listeners:

- port 8803: PID `380743`, process start ticks `46015771`, invocation
  `d0df21acd54a440788d89f7cad5b4827`, last verified `NRestarts=0`;
- port 8804: PID `465394`, process start ticks `51980337`, invocation
  `260291b2ae4a4c70a95a0a37722af61e`, last verified `NRestarts=0`.

No R6E operation modified, restarted, or signalled either protected process.
Ports 18805 and 8805 were still unbound at this report refresh. Deployment must
repeat the exact PID/start-tick/invocation/restart and listener checks before
and after installation.

The blocked-state recheck found the collector still running as PID `1430352`,
start ticks `81242549`, with command line rooted at
`/opt/banknifty-collector/app/fyers_banknifty_collector_v4.py`. That script's
SHA-256 remains
`0dbd270ba3a1fedc63f4ed8c8eff1947a7c14d08e412b3f82a890cb5500a4a4a`.
No R6E operation signalled, restarted, reconfigured, or modified it.

## Authorized scope and frozen contracts

R6E1R authorizes repair and verification of the durable raw-JSONL callback
path, six-session incremental-versus-clean chronological equivalence, read-only
GUI/API, and an isolated research shadow deployment. It does not authorize
orders, trades, alerts, collector changes, changes to ports 8803/8804, changes
to `main`, destructive Git operations, verified-tag alteration, or changes to
frozen analytical thresholds, clocks, coordinates, lifecycle precedence,
inventory rules, colours, strike selection, elapsed windows, or freshness
semantics.

The canonical inventory coordinate remains
`CAUSAL_BANKNIFTY_INDEX_REFERENCE_PRICE_BIN` with label `BN-REF FUT VOL-VPOC`.
The clock contracts remain frozen: synchronized confirmation, strictly later
standalone Index response, valid synchronized basis-resolution clocks,
timezone-aware stalled-extreme duration, and constituent receipt clocks for
participation. Snapshot/display time never replaces or backdates evidence.

## Rejected and historical evidence

- `81b0836fe50939246ae210bb62780ac4e163e100` completed useful focused and
  six-session work before the aware empty-Index repair. Its schedules,
  terminal summary, performance, audits, and preload are historical only and
  do not establish current `e1d67c5...` acceptance.
- Earlier focused merged-v2/full-six-v1 runs exposed the clean-B GUI
  resolution-transition comparator defect. They were stopped and rejected;
  their partial values are not promoted.
- The `19c5489f...` line exposed provisional large-chunk analytical publication
  and forged/missing SQLite-authority defects. Those failures drove dedicated
  repairs and regression coverage but remain non-pass history.
- Post-repair full-six v2 reached sealed A/B/reference matrices, then was
  externally interrupted during the one-record schedule and its evidence tree
  was removed. Attempts v3 through v6 were interrupted or externally cleaned
  before terminal publication. None is reused.
- Direct v7 received an external SIGINT/`KeyboardInterrupt` after 16m44.56s,
  peak RSS 4,982,376 KiB, and published no A seal. Persistent v8 failed closed
  in preflight because the required v7 projection had already been removed.
  Both are rejected diagnostics.
- Persistent v9 was the only current-repair attempt to publish a full-six
  baseline. The external operator stopped it before an alternate marker and
  deleted all v9 roots. Recorded hashes remain provenance, not terminal
  evidence.

August 25 and 26 evidence remains operational diagnostic material only. It is
not prospective or canonical equivalence evidence.

## Current handoff summary

| Required field | Interim value |
|---|---|
| Final status | `R6E1R_FINAL_VERIFICATION_INFRASTRUCTURE_BLOCKED` |
| Branch | `fix/r6e1r-final-live-shadow` |
| Analytical commit | `e1d67c534bea5c61b0e3d379db7f599de7e1c445` |
| Pushed report head before this edit | `cce61679dfc21ecb2cecd3acc592e8b151c538fe` |
| Test count | 660/660 complete regression; focused 9/9 schedules |
| Current exact equivalence | Sealed original-source baseline: components 21/21, ledgers 8/8, causality 9/9, R6C2R 30/30, R6D 180/180; scoped differences/mismatches/safety violations 0 |
| Terminal six-session equivalence | `NOT_VERIFIED` — externally stopped during one-record processing; all roots deleted; no alternate marker/terminal bundle survived |
| Package manifest | Current engine 38/38 and deployment 47/47 companion checks PASS; deployment not installed |
| Deployment service status | `NOT_INSTALLED_OR_ACCEPTED`; v9 verifier stopped/masked and its roots deleted |
| Exact deployed URL | `NOT_DEPLOYED` |
| Candidate URL | `http://200.234.39.232:8805/` — not deployed or externally verified |
| Verified tag | `NOT_CREATED` |
| Remaining limitations | Requires a root-agreed uninterrupted window to rerun full six-session all-nine verification; terminal source/open/checkpoint/recovery/performance/preload, deployment, live browser/API/recovery, and external ingress remain unverified |
| Protected ports | 8803 and 8804 retain the exact identities recorded above and were not modified or restarted |
| Collector state | PID/start `1430352/81242549`, script SHA-256 `0dbd270b...`; unchanged by R6E |

Related callback, equivalence, GUI, performance, deployment, readiness,
causality, artifact-matrix, test, browser, file-open, source-hash, and scratchpad
reports remain the detailed evidence sources. This report must be refreshed from
terminal v9 and deployment artifacts before it may claim final acceptance.

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**
