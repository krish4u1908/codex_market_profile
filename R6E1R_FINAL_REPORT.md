# R6E1R Final Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **COMPLETE REGRESSION 636/636 — FRESH EQUIVALENCE RUNNING — DEPLOYMENT NOT STARTED**

This report is a controlled handoff. `PENDING_FINAL_EVIDENCE` means the value
must come from a newly completed run on the authorized `/opt/banknifty` host
over the exact pushed repair commit.
Earlier diagnostic runs and all stale 26/34-file identities are historical only.

## Current local implementation record — 2026-08-27

- Current pushed repair commit:
  `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`.
- Engine closure: 38/38 files; manifest SHA-256
  `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`;
  engine hash
  `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`.
- Deployment closure: 47/47 files; manifest SHA-256
  `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1`;
  package hash
  `d68f22217f1dfb75817ebb9b7cb6af0d21306cf1081b7d222c6ecca130978380`;
  runtime configuration hash
  `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031`.
- The complete repository regression passed 636/636 with zero failures and zero
  skips. Pytest reported 129.36 seconds; `/usr/bin/time` reported 2m09.72 wall
  and 685,556 KiB peak process RSS. Retained log/time SHA-256 values are
  `a1132553080052c44424e8c936a33a8b7f548661b11390460fd0492463050bef`
  and `c2127eca2426ccb1a92a48875aa1d8ad2939e2be5ccf99bbaed921de8e175681`.
  No test was deselected, skipped, weakened, or reclassified.
- That complete suite closes the current host-only ptrace/file-open,
  user-systemd/bubblewrap, sealed-reference, API, gateway, and fixture-browser
  regression gates. It does not supply the final focused/full-six runtime trace
  or any installed-service evidence.
- Gateway redirects are refused before following `Location`; focused GET/HEAD
  regressions recorded that the redirect target received zero requests. The
  targeted gateway-security record is 14/14 and includes a real
  8-MiB-plus-one-byte upstream response refused as the sanitized 502
  `UPSTREAM_RESPONSE_LIMIT`; deployed end-to-end evidence remains pending. The
  resealed runtime/package closure is exact.
- The current Chromium/Playwright fixture passed 1/1 in 4.86 seconds with zero
  console and page errors. The complete suite regenerated the three 1600 x 1915
  fixture screenshots with SHA-256 values
  `532c09190f817ddf697445b3a7351220f3be0d5c19083978ea35065a083a4fdc`,
  `307e33736bd9f9c68c4f6d99fd30a76d5a411352d0b633795f8957db90bb772c`,
  and `a5e75f678a90ef67567222d2ed87d0bf57aad0d3a197f1b58371ecdaabdec3c2`.
  The latest/operational image is fixture evidence, not proof of a deployed
  service; deployed-browser acceptance remains pending.
- No service was installed, no public URL was deployed, and no verification tag
  was created in this environment.

Focused merged-v2 reached exact analytical components and all eight ledgers,
then exposed one clean-B GUI-comparator defect: clean B projected 11,486 dense
resolution observations where live A correctly projected 1,294 material
native-mechanism transitions. Full-six-v1 shared that comparator. Both units
were stopped, preserved, and rejected without promoting partial results.
Commit `c42e703...` repairs only the independent clean GUI comparator, and an
independent review found no frozen-rule, clock, dense-artifact, ID, or ledger
change. Fresh focused-v3 and full-six-v2 have been running from that pinned
commit since 2026-08-27 15:03:13 IST. Their results remain pending.

The uploaded August 20 archive also served its intended purpose: it exposed a
real schedule-dependent append-only-ledger defect. Large-chunk refreshes had
published 12 mutable lifecycle rows and 24 derived cross-layer rows for a
terminal dependency group that a later confirmation changed. The repair keeps
provisional GUI/state output available but defers only that unstable group's
durable publications until finalization. A second independent defect allowed a
forged checkpoint mirror to seed a missing/empty SQLite authority at EOF; mirror
bootstrap has now been removed, every source represented by trusted checkpoint
or normalized-ledger evidence must retain causally covering SQLite authority,
and missing, partial, or rolled-back authority fails closed. Both
repairs have dedicated restart/idempotency tests. A fresh August 20 current-seal
rerun and the canonical authorized-host gates remain required.

## Authorized scope

R6E1R prepares the durable raw-JSONL callback path, six-session
incremental-versus-clean-batch equivalence harness, live read-only GUI/API, and
isolated shadow deployment package. Deployment remains gated by authorized-host
evidence. It does not authorize trading, orders, alerts, collector changes,
changes to ports 8803/8804, or changes to frozen analytical semantics.

## Git and authority

| Item | Recorded fact |
|---|---|
| Authorized checkpoint | `065982c2ed49f6e7dad82bf29ed25f62ef78b024` |
| Working branch | `fix/r6e1r-final-live-shadow` |
| Frozen R6C2R tag target | `9cbe46fea6e3a44f3cf574955f21b5b1ebb6aa96` |
| Frozen R6D tag target | `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14` |
| Public reconstruction base | `f0d6db65bf41357965f76e067569255919cc8031` |
| Public runtime repair commit | `8038c9fcdf1760f25e9b5ddf2d468e47935f749c` — callback, ledger, GUI, harness, and regression repairs |
| Public code/package commit | `d6736b0108fb40722d2370da422b42e0425c112d` — portable deployment and exact sealed package bytes |
| Current pushed repair commit | `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2` |
| Verified tag | `NOT_CREATED` — do not create unless every gate passes |

Published milestone commits already present on the feature branch are:

- `43b66024d5a2689ad0855878b4780a1bb3bec56b` — handoff scratchpad initialization.
- `5c3afcc74f2bd3cd8177ec99959f818cb9f868ea` — durable callback wiring milestone.
- `ee760c8281340041293a9a2417af1cb6c22558a2` — live GUI/read-only API milestone.
- `27838f6fc54a914e58a155fb7bec835427dbf4ad` — equivalence and operational gate milestone.
- `6ea2ba02bcfe4f1ab163f7c7f0a7963c13d831e5` — callback durability and sealed-equivalence wiring.
- `abb5543572d8b5204d41b8d7ae3cac719c5cabbc` — causal partial-line schedule repair.
- `f2cebdc4595bd18b2426ba00916cce209a2f35bc` — focused nine-schedule equivalence milestone.
- `5efe70e9685b98556ae1ad9a860912c7bb1513fc` — R6D parity in the live GUI/API.
- `a9a28e84ae5999e102a24b64d490a437997088fe` — every material-ledger restart boundary.
- `85fd16712c2c53d593f4fb22d25d740dbb506b58` — rebuilt operational-availability comparison.
- `d947b5217b6427644e53edcae57d68a6cb01ac52` — accepted focused nine-schedule milestone.
- `71a868f1339773df06d0932dd72a3c908caa1028` — six-session incremental identity-continuity repair.
- `02594dc222afeff5135ac0404dd24211d09f425f` — accepted focused v12 evidence record.
- `89f135064417ba537dc302027442a110477b5d03` — historical-availability reference equivalence repair.
- `4d160bcc61bcebd88135ce270c17926830022deb` — isolated deployment startup-gate hardening.
- `6eec67bf11ad4ae1e88fda33565c3988d1ca2806` — historical R6D availability equivalence repair on the concurrent remote line.
- `f0d6db65bf41357965f76e067569255919cc8031` — causal-prefix schedule repair on the concurrent remote line.
- `dcccc723c6584bd929fab1aef531c3aad32eb1a2` — merge of the authorized concurrent feature milestones.
- `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2` — clean-B GUI resolution-transition comparator repair.
The pushed repair at `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`
contains the reviewed runtime, preload binding, tests, and sealed package bytes.
This report cleanup changes evidence text only. Record the later report commit
and verify the exact remote head after it is pushed. No verified tag is
authorized before every gate completes on the authorized host.

## Verified foundation

The following facts were independently recorded before this draft:

- The authoritative raw root `/opt/banknifty-collector/data-prod-v4` was readable
  and contained the required `raw` and `oi` streams.
- Frozen tag manifests passed before modification: R6C2R 94/94 repository files and R6D 105/105 repository files.
- The focused August 19 sample retained 46,550/46,550 selected byte identities, comprising 46,210 raw records and 340 OI outer records.
- The sample selected `NSE:BANKNIFTY26AUGFUT` through repository contract-discovery logic; eight authoritative source files retained identical hashes, sizes, and mtimes.
- The source-hour-preserving sample manifest SHA-256 is `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382`; the authoritative focused A/B input is its eight-file `collector/` tree.
- A correctly provisioned historical repository invocation passed 289 tests at
  its checkpoint; the current pushed repair supersedes it with 636/636, zero
  failed/skipped, as recorded above.
- The final local 38-file engine and 47-file deployment closures are recorded in
  the current implementation record above. Both companion checks, exact
  per-file inventories, unit digest pins, and package aggregate tests pass.
  They must be independently rerun on the authorized host before installation.

## Diagnostic evidence that is not final evidence

Focused A/B v8 exited successfully and reported 21/21 component equality, zero causal invariant failures, and zero source mutations. A later independent audit found comparator and runtime-open blind spots, so v8 is explicitly rejected as final acceptance evidence. A one-record probe then exposed 668 out-of-order refusals caused by unresolved Futures candidates. The ingestor and harness were repaired afterward. Neither v8 nor any earlier focused rehearsal may be quoted as final equivalence.

## Historical focused evidence

Focused v12 passed its historical scope on commit `71a868f...`, but predates
the current durable-authority, authenticated-import, gateway, and manifest
repairs. It is diagnostic precedent only; the exact pushed commit requires a
fresh focused all-nine run on the pushed repair commit.

## Final acceptance gates

| Gate | Required final evidence | Status |
|---|---|---|
| Current engine allowlist | Checked-in manifest, companion SHA-256, explicit runtime pin, 38/38 identities | PASS — manifest `715a82b4...`, engine `021935bc...` |
| Deployment closure | Exact per-file package and companion, 47/47 identities | PASS — manifest `7dcd1d15...`, package `d68f2221...` |
| Focused production-path A/B | Exact component, ledger, availability, GUI, open-audit, and causality equality | Focused-v3 running since 2026-08-27 15:03:13 IST; `PENDING_FINAL_EVIDENCE` |
| Six-session A/B | All required schedules and frozen canonical counts | Full-six-v2 running since 2026-08-27 15:03:13 IST; `PENDING_FINAL_EVIDENCE` |
| Causality | Future joins, tolerance violations, backdating, duplicate IDs, refusals all zero | `PENDING_FINAL_EVIDENCE` |
| Source integrity | Focused pre/post hashes and source mutations zero; final six still required | Historical fixture integrity recorded; current focused/full-six post-run evidence pending |
| Current complete regression | Passed, failed, skipped, elapsed, peak RSS | PASS — 636/636, zero failed/skipped; 129.36 s pytest; 2m09.72 wall; 685,556 KiB |
| Browser acceptance | Current screenshots, console/page errors, toggle/degradation checks | FIXTURE PASS — 1/1 in 4.86 s, zero console/page errors; deployed-browser pending |
| Deployment | Installed units, health/readiness, replay checks, public-interface URL | `PENDING_FINAL_EVIDENCE` |
| Final Git state | Clean worktree, pushed commits, remote head, annotated tag | `PENDING_FINAL_EVIDENCE` |

## Required final handoff values

| Field | Final value |
|---|---|
| Final status | `IN PROGRESS — NOT VERIFIED` |
| Branch | `fix/r6e1r-final-live-shadow` |
| All new commit hashes | Runtime repair `8038c9fcdf1760f25e9b5ddf2d468e47935f749c`; deployment package `d6736b0108fb40722d2370da422b42e0425c112d`; merged implementation `dcccc723c6584bd929fab1aef531c3aad32eb1a2`; clean-comparator repair `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2`; later report-only commit pending |
| Remote push verification | Repair commit `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2` is the recorded remote branch head; verify the later report-only remote head after push; no tag authorized |
| Test counts | Complete current regression 636/636, zero failed/skipped, including fixture browser 1/1; fresh focused-v3/full-six-v2 results pending |
| Stream-versus-batch differences | `PENDING_FINAL_EVIDENCE` |
| Canonical reference mismatches | `PENDING_FINAL_EVIDENCE` |
| Future joins | `PENDING_FINAL_EVIDENCE` |
| Timestamp backdating | `PENDING_FINAL_EVIDENCE` |
| Duplicate analytical IDs | `PENDING_FINAL_EVIDENCE` |
| Prohibited runtime opens | `PENDING_FINAL_EVIDENCE` |
| Source mutations | `PENDING_FINAL_EVIDENCE` |
| Package manifest result | PASS — 47/47 files, companion and package aggregate exact; manifest `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1` |
| Service status | `NOT_INSTALLED` |
| Exact deployed URL | `NOT_DEPLOYED` |
| Remaining limitations | Fresh focused/full-six equivalence, measured run-specific runtime-open/source/performance evidence, installed services, deployed-browser, health/readiness, recovery, and external-interface evidence remain pending |
| Ports 8803/8804 and collectors unchanged | No deployment action has been taken; mandatory pre/post verification remains pending |

Related evidence is organized in the callback, equivalence, GUI, performance, deployment, readiness, causality, matrix, test, browser, file-open, and source-hash reports at repository root.
