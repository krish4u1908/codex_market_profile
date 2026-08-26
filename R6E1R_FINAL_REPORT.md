# R6E1R Final Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **IN PROGRESS — PENDING_FINAL_EVIDENCE**

This report is a controlled draft. `PENDING_FINAL_EVIDENCE` means the value must be copied from a newly completed, sealed final run. Earlier diagnostic or subsequently invalidated runs must not be substituted.

## Authorized scope

R6E1R completes the durable raw-JSONL callback path, the six-session incremental-versus-clean-batch equivalence harness, live read-only GUI/API integration, and an isolated shadow deployment. It does not authorize trading, orders, alerts, collector changes, changes to ports 8803/8804, or changes to frozen analytical semantics.

## Git and authority

| Item | Recorded fact |
|---|---|
| Authorized checkpoint | `065982c2ed49f6e7dad82bf29ed25f62ef78b024` |
| Working branch | `fix/r6e1r-final-live-shadow` |
| Frozen R6C2R tag target | `9cbe46fea6e3a44f3cf574955f21b5b1ebb6aa96` |
| Frozen R6D tag target | `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14` |
| Current published milestone at draft time | `4d160bcc61bcebd88135ce270c17926830022deb` |
| Final report/package commit | `PENDING_FINAL_EVIDENCE` |
| Final remote branch head | `PENDING_FINAL_EVIDENCE` |
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

Implementation, harness, and service-template milestones are pushed through `4d160bcc61bcebd88135ce270c17926830022deb`, and the remote feature branch was observed at the same hash. Report commits, deployment-package regeneration, final gates, and the final remote/tag verification remain pending.

## Verified foundation

The following facts were independently recorded before this draft:

- The authoritative raw root `/opt/banknifty-collector/data-prod-v4` was readable and contained `raw/` and `oi/`.
- Frozen tag manifests passed before modification: R6C2R 94/94 repository files and R6D 105/105 repository files.
- The focused August 19 sample retained 46,550/46,550 selected byte identities, comprising 46,210 raw records and 340 OI outer records.
- The sample selected `NSE:BANKNIFTY26AUGFUT` through repository contract-discovery logic; eight authoritative source files retained identical hashes, sizes, and mtimes.
- The source-hour-preserving sample manifest SHA-256 is `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382`; the authoritative focused A/B input is its eight-file `collector/` tree.
- A correctly provisioned repository regression invocation passed 289 tests with zero failures and zero skips in 62.29 seconds at that checkpoint. Current-source final rerun: `PENDING_FINAL_EVIDENCE`.
- Deployment-package/static operational verification passed at an earlier source checkpoint. That package identity is now deliberately stale; current package regeneration and verification remain pending. No R6E service was installed by the earlier verification.

## Diagnostic evidence that is not final evidence

Focused A/B v8 exited successfully and reported 21/21 component equality, zero causal invariant failures, and zero source mutations. A later independent audit found comparator and runtime-open blind spots, so v8 is explicitly rejected as final acceptance evidence. A one-record probe then exposed 668 out-of-order refusals caused by unresolved Futures candidates. The ingestor and harness were repaired afterward. Neither v8 nor any earlier focused rehearsal may be quoted as final equivalence.

## Accepted focused evidence

The replacement focused v12 is accepted for focused scope on pushed repair commit `71a868f1339773df06d0932dd72a3c908caa1028`: 21/21 components, 8/8 append-only ledgers, 9/9 schedules, 9/9 causality/GUI invariants, 72/72 checkpoint rows, 2/2 recovery probes, and 8/8 source hashes passed. All differences, refusals, future joins, backdating, duplicate IDs, prohibited or unmeasured opens, checkpoint failures, and source mutations were zero. Summary SHA-256: `19b6c15f426b925fa6ec018d65477f4364242d65cfaaa5425423098d3861de15`.

## Final acceptance gates

| Gate | Required final evidence | Status |
|---|---|---|
| Current engine allowlist | Checked-in manifest, companion SHA-256, explicit runtime pin, 26/26 identities | PASS — manifest `7c13b44c...`, engine `980b6af2...` |
| Focused production-path A/B | Exact component, ledger, availability, GUI, open-audit, and causality equality | PASS — focused v12 |
| Six-session A/B | All required schedules and frozen canonical counts | `PENDING_FINAL_EVIDENCE` |
| Causality | Future joins, tolerance violations, backdating, duplicate IDs, refusals all zero | `PENDING_FINAL_EVIDENCE` |
| Source integrity | Focused pre/post hashes and source mutations zero; final six still required | FOCUSED PASS; six-session `PENDING_FINAL_EVIDENCE` |
| Current complete regression | Passed, failed, skipped, elapsed, peak RSS | `PENDING_FINAL_EVIDENCE` |
| Browser acceptance | Current screenshots, console/page errors, toggle/degradation checks | FIXTURE/REPLAY PASS; external deployed browser `PENDING_FINAL_EVIDENCE` |
| Deployment | Installed units, health/readiness, replay checks, public-interface URL | `PENDING_FINAL_EVIDENCE` |
| Final Git state | Clean worktree, pushed commits, remote head, annotated tag | `PENDING_FINAL_EVIDENCE` |

## Required final handoff values

| Field | Final value |
|---|---|
| Final status | `PENDING_FINAL_EVIDENCE` |
| Branch | `fix/r6e1r-final-live-shadow` |
| All new commit hashes | Published milestones through `4d160bcc61bcebd88135ce270c17926830022deb` are listed above; final report/deployment commits `PENDING_FINAL_EVIDENCE` |
| Remote push verification | Remote feature branch matched `4d160bcc61bcebd88135ce270c17926830022deb`; final remote head/tag check `PENDING_FINAL_EVIDENCE` |
| Test counts | 216/216 repaired-engine targeted; 29/29 reference comparator; 135/135 R6D-parity targeted at GUI milestone with GUI/browser bytes unchanged afterward; complete regression `PENDING_FINAL_EVIDENCE` |
| Stream-versus-batch differences | `PENDING_FINAL_EVIDENCE` |
| Canonical reference mismatches | `PENDING_FINAL_EVIDENCE` |
| Future joins | `PENDING_FINAL_EVIDENCE` |
| Timestamp backdating | `PENDING_FINAL_EVIDENCE` |
| Duplicate analytical IDs | `PENDING_FINAL_EVIDENCE` |
| Prohibited runtime opens | `PENDING_FINAL_EVIDENCE` |
| Source mutations | `PENDING_FINAL_EVIDENCE` |
| Package manifest result | `PENDING_FINAL_EVIDENCE` |
| Service status | `PENDING_FINAL_EVIDENCE` |
| Exact deployed URL | `PENDING_FINAL_EVIDENCE` |
| Remaining limitations | `PENDING_FINAL_EVIDENCE` |
| Ports 8803/8804 and collectors unchanged | `PENDING_FINAL_EVIDENCE` |

Related evidence is organized in the callback, equivalence, GUI, performance, deployment, readiness, causality, matrix, test, browser, file-open, and source-hash reports at repository root.
