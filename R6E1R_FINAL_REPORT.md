# R6E1R Final Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **IMPLEMENTATION REVIEWED AND SEALED — HOSTINGER VERIFICATION AND DEPLOYMENT PENDING**

This report is a controlled handoff. `PENDING_FINAL_EVIDENCE` means the value
must come from a newly completed Hostinger run over the exact pushed commit.
Earlier diagnostic runs and all stale 26/34-file identities are historical only.

## Current local implementation record — 2026-08-27

- Engine closure: 38/38 files; manifest SHA-256
  `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`;
  engine hash
  `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`.
- Deployment closure: 47/47 files; manifest SHA-256
  `c75d269da49f141352aeedffd0e3b7fc09d9045ab814bdf917214e44ac905a7b`;
  package hash
  `563e2d848933c41eea1db20008bf92e29ee6162baaeb767361e5c605aec18c4c`;
  runtime configuration hash
  `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031`.
- Independent source and package reviews found no known blocker within the
  completed local code, durability, callback, bounded-memory, schema, GUI/API,
  bootstrap, and package-pin scope. Pending Hostinger gates can still expose a
  host/data-scale defect.
- Current focused suites: ingestion 127/127 and orchestration 111/111 passed.
  The equivalence harness passed 32 tests with three non-passes caused by this
  container prohibiting `strace`/`ptrace`. Deployment/package/gateway/runner
  coverage passed 130 tests with two non-passes caused by its unavailable user
  systemd bus. Every host-bound case remains mandatory on Hostinger.
- The stabilized full non-browser collection passed 545 tests, skipped 20,
  failed 13, and errored 16 in 79.30 seconds. Its 29 failures/errors are exactly
  the same unavailable host/reference classes: user-systemd/bubblewrap (2),
  ptrace/strace (3), absent sealed R6C0 evidence (4), and absent sealed R6C2R/R6D
  evidence (20); the 20 skips are additional non-passing outcomes. No
  code-attributable failure remained.
- Gateway redirects are refused before following `Location`; focused GET/HEAD
  regressions prove the redirect target receives zero requests. Gateway
  security is 13/13 and the resealed runtime/package closure is exact.
- Browser collection cannot run locally because Python Playwright/Chromium is
  absent. It is not waived; Hostinger browser acceptance remains mandatory.
- No service was installed, no public URL was verified, and no verification tag
  was created in this environment.

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
rerun and the canonical Hostinger gates remain required.

## Authorized scope

R6E1R prepares the durable raw-JSONL callback path, six-session
incremental-versus-clean-batch equivalence harness, live read-only GUI/API, and
isolated shadow deployment package. Deployment remains gated by Hostinger
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
| Final remote branch head | The sanitized evidence commit at the published branch head follows the code/package commit |
| Verified tag | `PENDING_FINAL_EVIDENCE` — do not create unless every gate passes |

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
The final public continuation is reconstructed linearly from the existing
remote head so the additional local-only unsanitized commits and evidence never
become reachable from the public branch. This does not rewrite or erase older
already-public history. The code/package commit contains the exact reviewed runtime,
tests, and sealed package bytes; a following sanitized handoff commit contains
only public-safe reports. The exact verified remote head must still be read from
the branch after publication.
No verified tag is authorized before Hostinger completes every gate.

## Verified foundation

The following facts were independently recorded before this draft:

- The host-private authoritative raw root was readable and contained the required
  raw and OI streams. Its physical location is intentionally omitted from public
  evidence.
- Frozen tag manifests passed before modification: R6C2R 94/94 repository files and R6D 105/105 repository files.
- The focused August 19 sample retained 46,550/46,550 selected byte identities, comprising 46,210 raw records and 340 OI outer records.
- The sample selected `NSE:BANKNIFTY26AUGFUT` through repository contract-discovery logic; eight authoritative source files retained identical hashes, sizes, and mtimes.
- The source-hour-preserving sample manifest SHA-256 is `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382`; the authoritative focused A/B input is its eight-file `collector/` tree.
- A correctly provisioned repository regression invocation passed 289 tests with zero failures and zero skips in 62.29 seconds at that checkpoint. Current-source final rerun: `PENDING_FINAL_EVIDENCE`.
- The final local 38-file engine and 47-file deployment closures are recorded in
  the current implementation record above. Both companion checks, exact
  per-file inventories, unit digest pins, and package aggregate tests pass.
  Hostinger must independently rerun them before installation.

## Diagnostic evidence that is not final evidence

Focused A/B v8 exited successfully and reported 21/21 component equality, zero causal invariant failures, and zero source mutations. A later independent audit found comparator and runtime-open blind spots, so v8 is explicitly rejected as final acceptance evidence. A one-record probe then exposed 668 out-of-order refusals caused by unresolved Futures candidates. The ingestor and harness were repaired afterward. Neither v8 nor any earlier focused rehearsal may be quoted as final equivalence.

## Historical focused evidence

Focused v12 passed its historical scope on commit `71a868f...`, but predates
the current durable-authority, authenticated-import, gateway, and manifest
repairs. It is diagnostic precedent only; the exact pushed commit requires a
fresh focused all-nine run on Hostinger.

## Final acceptance gates

| Gate | Required final evidence | Status |
|---|---|---|
| Current engine allowlist | Checked-in manifest, companion SHA-256, explicit runtime pin, 38/38 identities | PASS — manifest `715a82b4...`, engine `021935bc...` |
| Deployment closure | Exact per-file package and companion, 47/47 identities | PASS — manifest `c75d269d...`, package `563e2d84...` |
| Focused production-path A/B | Exact component, ledger, availability, GUI, open-audit, and causality equality | Historical v12 only; current Hostinger run pending |
| Six-session A/B | All required schedules and frozen canonical counts | `PENDING_FINAL_EVIDENCE` |
| Causality | Future joins, tolerance violations, backdating, duplicate IDs, refusals all zero | `PENDING_FINAL_EVIDENCE` |
| Source integrity | Focused pre/post hashes and source mutations zero; final six still required | FOCUSED PASS; six-session `PENDING_FINAL_EVIDENCE` |
| Current complete regression | Passed, failed, skipped, elapsed, peak RSS | Local non-browser: 545 pass, 20 skip, 13 fail, 16 error; all 29 failures/errors and 20 skips host/reference-bound; complete Hostinger run pending |
| Browser acceptance | Current screenshots, console/page errors, toggle/degradation checks | Current Playwright/Chromium run pending on Hostinger |
| Deployment | Installed units, health/readiness, replay checks, public-interface URL | `PENDING_FINAL_EVIDENCE` |
| Final Git state | Clean worktree, pushed commits, remote head, annotated tag | `PENDING_FINAL_EVIDENCE` |

## Required final handoff values

| Field | Final value |
|---|---|
| Final status | `PENDING_FINAL_EVIDENCE` |
| Branch | `fix/r6e1r-final-live-shadow` |
| All new commit hashes | Runtime repair `8038c9fcdf1760f25e9b5ddf2d468e47935f749c`; deployment package `d6736b0108fb40722d2370da422b42e0425c112d`; the sanitized handoff commit is the published branch head |
| Remote push verification | Verify the exact published branch head after connector publication; no tag authorized |
| Test counts | Ingestion 127/127; orchestration 111/111; local stable-seal non-browser 545 pass, 20 skip, 13 fail, 16 error; complete Hostinger run required |
| Stream-versus-batch differences | `PENDING_FINAL_EVIDENCE` |
| Canonical reference mismatches | `PENDING_FINAL_EVIDENCE` |
| Future joins | `PENDING_FINAL_EVIDENCE` |
| Timestamp backdating | `PENDING_FINAL_EVIDENCE` |
| Duplicate analytical IDs | `PENDING_FINAL_EVIDENCE` |
| Prohibited runtime opens | `PENDING_FINAL_EVIDENCE` |
| Source mutations | `PENDING_FINAL_EVIDENCE` |
| Package manifest result | PASS — 47/47 files, companion and package aggregate exact; manifest `c75d269da49f141352aeedffd0e3b7fc09d9045ab814bdf917214e44ac905a7b` |
| Service status | `PENDING_FINAL_EVIDENCE` |
| Exact deployed URL | `PENDING_FINAL_EVIDENCE` |
| Remaining limitations | `PENDING_FINAL_EVIDENCE` |
| Ports 8803/8804 and collectors unchanged | Local work made no host/service/collector mutation; Hostinger pre/post verification pending |

Related evidence is organized in the callback, equivalence, GUI, performance, deployment, readiness, causality, matrix, test, browser, file-open, and source-hash reports at repository root.
