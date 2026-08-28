# R6E1R-FINAL Worklog

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

## 2026-08-26

- Fetched `origin` with tags and pruning.
- Verified `origin/feature/r6e-live-shadow` at `065982c2ed49f6e7dad82bf29ed25f62ef78b024`.
- Verified frozen annotated tag targets and repository manifests before editing:
  - `r6c2r-full-stack-equivalence-verified` -> `9cbe46fea6e3a44f3cf574955f21b5b1ebb6aa96`; 94/94 files PASS.
  - `r6d-offline-gui-verified` -> `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14`; 105/105 files PASS.
- Created `fix/r6e1r-final-live-shadow` exactly from the authorized checkpoint.
- Carried forward the existing callback repair as `0a35877` for inspection and extension.
- Confirmed authoritative raw root `/opt/banknifty-collector/data-prod-v4` is readable (45 GiB; `raw/` and `oi/` present).
- Confirmed the focused sample exists outside Git at `/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205` (52 MiB); independent revalidation is in progress.
- Port preflight: `8803` and `8804` are occupied by existing dashboards; `8805` through `8810` were unused. External IPv4 is `200.234.39.232`. No service changes have been made.
- Published the final feature branch; remote head initially verified at `0a3587731f9b0b4a99543d1fb059307340b588d3`.
- Independently revalidated the focused sample using repository contract-discovery logic. Selected Futures: `NSE:BANKNIFTY26AUGFUT`; 46,550/46,550 source byte identities passed (46,210 raw + 340 OI); eight source files retained identical content hashes, sizes, and mtimes.
- Started focused incremental-A versus independent chronological batch-B execution for 2026-08-19.
- Baseline focused run exposed and measured the inherited quadratic rebuild defect: after 8m56s it had not completed, peak RSS was 343,064 KiB, and filesystem output was 2,862,368 KiB. The obsolete run was interrupted after retaining evidence.
- Repaired callback/checkpoint semantics so each poll fsync-stages observations and acknowledges only after durable callback return; analytical rebuild is now bounded to refresh/finalize boundaries, never raw/API polls. Added measured checkpoint/readiness state, exact causal/provenance fields, restart-safe run identity, current-source engine hashing, cached discovery/source hashes, and linear one-record schedule hints.
- Focused verification after repair: 74 backend/harness tests PASS, 18 GUI/API integration tests PASS, `py_compile` PASS, `git diff --check` PASS.
- Completed sanitized live GUI/API and isolated gateway templates. Independent combined verification: 79 tests PASS in 48.82s (live API, shadow API, browser acceptance, and preserved R6D GUI); zero browser console/page errors; `py_compile` and `git diff --check` PASS.
- Captured 1600x1705 PNG evidence for complete fixed horizons, Intraday-only degradation, and live/latest operational projection. Current SHA-256 values: `8ece265418bff3ae7a01903b0b8f4e8c0188fcc6cf99d3050ef3ddc127b99ad9`, `c0be0b49535cda30911cb3b216c55660984ab38ccb5fdebaeeb1a6577e9e3577`, and `331f1c6d07717c42008919002dd1f8ac384377b265b8ae8f3d6e2c6f532710b0`.
- Focused manifest A/B v2 completed in 3m11.34s with peak RSS 1,063,876 KiB. Core analytics and causality matched; the only analytical remainder was 25 Intraday inventory rows (and their 25 cross-layer transitions) omitted by the legacy clean-batch eligibility gate. The live result is required behavior, so batch-B is being extended with an independent raw-byte Intraday fallback rather than suppressing live rows.
- Repaired callback durability under pre-write, ambiguous post-fsync, partial multi-session, and publication exceptions. Repaired same-inode committed-prefix replacement detection and strict future-receipt refusal. Current focused ingestion/orchestrator/shadow set: 69/69 PASS.
- Independent deployment audit identified repairable readiness, measured-audit, expected-manifest, absent-replay, gateway-log, health-helper, same-UID filesystem, inherited-agent-environment, and replay-retention gaps. Service installation remains correctly gated while these are repaired.
- Rehashed all eight authoritative August 19 source files after sample extraction. Every SHA-256 still exactly matches the sample manifest; elapsed 1.08s, peak RSS 3,712 KiB. Sample manifest SHA-256 remains `5bf62dda9b6613e2d6b3000c084a723133c5af01c7e4cb5acff84af84fb610e2`.
- Focused A/B v4 reached exact equality for every analytical component under the finalized comparator: 25/25 independently rebuilt Intraday inventory rows and 25/25 corresponding cross-layer transitions now match, with all causality invariants at zero. The v4 process itself loaded an older in-flight GUI comparator and therefore remains a non-passing rehearsal; a stable-code rerun is required.
- Proved a rootless bubblewrap gateway boundary is available on this host. Inside the namespace, the collector, deployment state, and `/run/user/1002` were absent; only the bound gateway script and two namespace PIDs were visible. This provides a viable same-UID process/filesystem isolation repair while sharing only the required network namespace.
- Verified both external visual/analytical reference package manifests before the final comparison: R6C2R 74/74 files PASS and R6D 40/40 files PASS (0.96s, 18,668 KiB peak RSS).
- Closed the operational clock, retention, measured-audit, replay-presence, query/log sanitization, and gateway filesystem/process-isolation defects found by independent review. Exact transient user-systemd probes proved both bubblewrap `ExecStart` and `ExecStartPost` work under the installed hardening set. The backend retains the three kernel namespace protections that conflict with rootless bubblewrap; the gateway uses the tested private bubblewrap mount/PID/user/IPC/UTS/cgroup boundary instead.
- Froze the final 26-file runtime allowlist after fixing health-probe credential redaction. Manifest SHA-256: `cc92e8a07c4a78e0b0aa8ecbe0114ebde08da2c73892875c2c333cd4e5ef9481`; engine hash: `200cd84e3e26049494653b1f349a9c87938f9c0c731c59718a80a4df128e0629`; 26/26 source identities PASS and prohibited opens zero.
- Final-engine focused A/B v8 PASS: all 21 canonical components matched with zero A-only, B-only, field-mismatch, or unexplained rows; all causality, checkpoint, file-open, and source-mutation gates were zero. Wall time 3m58.44s; parent peak RSS 1,121,076 KiB; child peak RSS 696,360 KiB.
- Complete repository regression PASS: 289/289 tests, zero skipped, in 62.29s after supplying all repository-required sealed R6C0I/R6B3/R6B3A/R6B3R evidence roots and the explicit venv Python path. The first environment-incomplete invocation failed eight legacy R6C0I tests and skipped twenty external-evidence tests; it was retained as an invocation failure and rerun correctly, without weakening or deselecting tests.
- Browser acceptance regenerated and visually inspected all three required 1600x1705 screenshots. Current fixture hashes: complete fixed horizons `edd2df7bebee95c2a51d4e0f316881170f680a9b1c6d45d7befc374d1ddd8e53`; Intraday-only `bd738cbaabe086d39fa37d36f6069681e03d853b9009e2e2378bf623eb3c0ebe`; live/latest operational `2b9ddf8c7e79264d772470bdd3637440e307f0e3a3aa8277d17620a2281264ba`.
- Independent final-gate audit rejected the focused-v8 result as final evidence despite its PASS exit: batch-B did not yet project independently derived append-only ledger identities; the GUI/as-of and availability comparisons omitted public fields; the incremental file-open rows were declarative rather than observed; malformed complete candidate records were not a hard gate; and the browser path builder did not sort Index/Futures clocks independently. The v8 evidence remains diagnostic only.
- A focused one-record schedule probe then exposed 668 genuine out-of-order refusals hidden by 512-record chunks. Raw Futures candidates at 09:15 were durably deferred until the first canonical Futures-OI evidence at 09:15:55, while later Index/OI observations advanced the global receipt high-water. The released candidates were consequently rejected. Repair is in progress by placing a strict causal publication barrier at the earliest unresolved candidate receipt, including restart, duplicate, equal-clock, and Index-between-candidate-and-depth tests.
- The checked-in runtime source manifest is intentionally stale while allowlisted ingestor, GUI, and live-runner repairs are in flight. Runtime contract validation continues to fail closed; the manifest will be regenerated only after all source edits freeze, followed by focused and complete-regression reruns.
- Replaced the quadratic durable-stage high-water recomputation with an incremental maximum. A regression counter proves one-record callback staging uses at most three ordering-key evaluations per observation and never rescans the accumulated session.
- Replaced the same-file option/depth candidate workaround with a durable, bounded selection-only OI probe. The probe leaves the primary checkpoint untouched, records replay targets, requires primary OI replay and raw-candidate source catch-up before publication, and audits a finite search-limit outcome only after probed option rows have crossed the causal boundary.
- Targeted ingestion, orchestration, and equivalence-harness verification passed 78/78 against the real regenerated engine manifest.
- Fresh current-code focused A/B passed in 2m58.41s: 21/21 components exact; eight append-only analytical ledgers exact; all nine causality/GUI invariants zero; 1,149,224 KiB parent and 715,080 KiB child peak RSS; zero prohibited opens, source mutations, checkpoint failures, or analytical refusals.
- Deployment preload hardening now validates real finalized-state shape, schema version, exact six-session equivalence and projection gates, August 17 rejection evidence, empty callback/selection outboxes, checkpoint parity, and ledger engine/config identities before an atomic same-filesystem rename. The regenerated 34-file package passed 75/75 deployment/API tests.
- An independent adversarial review found that replacing or truncating an OI selection-authority file between probe and primary replay could either accept replacement bytes or leave an unreachable replay target. The first all-schedule focused run was deliberately interrupted during one-record exercise; replacement quarantine and causal liveness repair is in progress, and none of that diagnostic output will be promoted.
- Added persistent source quarantine and reran the clean code gates: 82/82 ingestion/orchestrator/equivalence-harness tests and 78/78 deployment/API/logging tests passed against regenerated manifests. Browser acceptance was also extended to visit all six canonical replay dates and passed 1/1; fixture screenshots are now 1600x1733.
- The next fresh focused baseline again sealed with exact equality (21/21 canonical components, 8/8 analytical ledgers, and 9/9 causality/GUI invariants), but its one-record schedule was stopped after a separate independent review reproduced six uncovered edge cases: mismatched candidate selection could drop the replay barrier, missing candidate files could stall globally, unrelated mutations could revoke selection, partial probe tails could be reread without a durable bound, middle-prefix rewrites plus growth could evade the bounded fingerprint, and quarantine audit clocks could change after crash/restart. The output and work roots were deleted and will not be promoted. Reproduction-first repairs are in progress.
- Closed all six reproduced ingestion edge cases with durable candidate/probe replay barriers, path-scoped quarantine, exact bounded probe fingerprints, committed 64-KiB prefix-block identities with restart-safe rotating scrub, and stable quarantine evidence clocks. The transactional checkpoint review confirmed outboxes, checkpoints, block identities, and scrub initialization commit atomically. Independent final code review found no release blocker.
- Regenerated the 26-file engine source manifest after freezing those runtime bytes. Manifest SHA-256 is `2843d18ff5decd98a4a2cdb04390c80019f3a24b3da759a77b3d0b098be16f0e`; engine hash is `7016cbd4e4d908e5adcb551e4d3b12e64cc760d75a3eb37577f9aa491d451d38`.
- Clean real-manifest core verification passed 98/98 ingestion, orchestrator, and equivalence-harness tests in 13.98s with 135,800 KiB peak RSS. A preceding `/usr/bin/python3` invocation did not collect because that host interpreter lacks pytest; it was retained and rerun unchanged with the verified research virtual environment.
- Extended preload validation to require the current selection-probe schema and exact checkpoint-aligned 64-KiB integrity blocks, with digest/residual/orphan/scrub-bound checks and empty quarantine/probe/outbox gates. All 39 focused validator cases pass.
- Resealed the 34-file deployment package after correcting the engine companion to its repository-relative path. Deployment manifest SHA-256 is `0cb3c7e3ccfe65abe26e7ed695ccde2255aa36e60db091094d41683fb06565aa`; package hash is `c0293ac25af0717f281d083927ff2a6861ccf2f0e2d526d6ac053be0d1eb6651`; runtime configuration hash is `a853daa9b34a2fba2b1bb4bf3429bac441f99bc8671b92ab19377d77083cac03`; 34/34 file identities pass. The complete deployment/API/logging gate passes 87/87 in 17.33s with 123,468 KiB peak RSS.
- Final fixture-browser acceptance passes 1/1 in 3.20s and exercises every canonical replay date. The complete, Intraday-only, and fixture live/latest screenshots are each 1600x1733 with SHA-256 values `66af74411fc859a784aeafe963039c9e3bdc6a14e6d1a2eb942e5b23a005d5a5`, `6a13dfe3911dc4bc04532e9aad80b4a0708b0a975e99a7ef7d44e338bbd02430`, and `3ccee566595d9a7c0eda66c8d31dfcda2ce26711cb2ad54cff7e11950fb79e50`. The last image remains fixture evidence until the gated deployment is live and is not claimed as deployed proof.
- Rejected focused nine-schedule v3 after the one-record schedule exposed six refusal rows despite exact baseline A/B results. The diagnostic was stopped after 7m00.15s (1,408,444 KiB peak RSS) and preserved; it is not acceptance evidence.
- Reproduced the six rows independently: three physical observations were each refused once at ingestion and once at orchestration. Every inversion was an artifact of the old focused fixture collapsing original hourly files across the 09→10 and 11→12 boundaries. All eight authoritative source files are individually receipt-monotonic. A source-hour-preserving fixture rebuild is in progress; frozen clocks and ordering rules will not be changed to accommodate a malformed fixture.
- Independent release audit found three more repairable blockers: the preload state was not cryptographically bound to its PASS seal, a final append could strand an unsampled old-block rewrite, and a recovered prior-day session could remain mutable after the first next-day poll. Preload attestation is being added. Poll-time source work remains bounded, while unchanged polls advance the durable scrub and one exhaustive full-prefix pass now gates session sealing. Recovered and multi-date catch-up sessions finalize chronologically only after that integrity gate. Focused integrity and live-runner verification passes 49/49.
- Rebuilt the focused fixture into eight original hourly collector paths with repository-owned contract selection. Manifest SHA-256 is `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382`; selected Futures is `NSE:BANKNIFTY26AUGFUT`; 46,550 selected outer records and all source/projection byte identities passed; all eight authoritative before/during/after hashes remained unchanged. The flawed combined fixture was preserved at `/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205_combined_diagnostic` rather than deleted.
- Closed the three independent release-audit blockers. Session finalization now discovers recovered pending dates and seals them chronologically after source verification; a rotating bounded scrub runs on idle polls and an exhaustive stable-prefix pass gates finalization; the harness emits and seals an exact state-tree manifest and deployment validation rehashes that exact tree and independently recounts frozen analytical outputs. Accurate scope: the exhaustive source check is once per session seal, not every append.
- Focused nine-schedule v4 was rejected after the new sparse hourly fixture exposed a harness accounting error: 2,060,715 coordinate-preserving physical rows were mistaken for JSON-record count. Baseline A/B and every produced schedule semantic hash were exact, but eight schedules failed the truthful exercise gate. Wall time was 18m23.25s and peak RSS 1,508,212 KiB. The output remains diagnostic at `/dev/shm/r6e1r_focused_nine_final_v4`.
- Added a validated local scheduling contract for the temporary focused A/B copy so sparse blank rows preserve checkpoint coordinates without counting as market records. Fresh one-record proof v5 passed: exactly 46,550 records, increments, and production polls; zero analytical refusals or semantic/ledger differences; all 2,060,715 physical checkpoint rows exact; wall 5m45.06s; peak RSS 1,487,424 KiB.
- Focused all-nine v6 truthfully rejected one schedule: the inside-line harness polled only the fragmented destination while earlier chronological peer-file bytes in the same large group remained unpolled, manufacturing 30,452 out-of-order refusals. The other eight schedules, baseline A/B, component/ledger comparisons, and causality/source/file-open gates were exact. This was repaired without changing production clocks by polling the entire visible causal prefix during each fragment.
- Fresh boundary-only v7 passed against the real fixture: 17/17 configured partial-line boundaries, 46,550/46,550 records exposed, zero analytical refusals, and exact semantic and append-only-ledger hashes. Wall time 5m01.98s; peak RSS 1,477,200 KiB.
- Final focused all-nine v8 passed on pushed commit `abb5543572d8b5204d41b8d7ae3cac719c5cabbc`: 9/9 schedules, 21/21 component comparisons, 8/8 append-only ledger comparisons, and 9/9 causality/GUI invariants passed; 72/72 checkpoint rows and 2/2 recovery probes passed; 8/8 post-run source hashes passed. Differences, analytical refusals, prohibited opens, unmeasured open rows, and source mutations were all zero. Wall time 18m32.32s; parent peak RSS 1,584,328 KiB; child peak RSS 800,864 KiB. Summary SHA-256 is `cd7381d463261ab3862876dd18db49525267fff90b3caf6225462fda55da969d`; state-manifest/tree SHA-256 values are `1ab815ad81ad7305cbbe38c0ab50f8d5f8d5e069cd9d15eb6d010a29c8691fd3` and `0e448d257bb3a0b955c0a7a86cd5950ae932e18cce593684b5d3a96fc883a57a`.

## 2026-08-27

- Began the fresh full six-session run with all nine required schedules and both independently verified reference packages. A new byte-exact projection selected 746,890 causal records across 139 hourly source paths (929 MiB including provenance); incremental A processed and durably sealed all six evaluation sessions.
- Stopped that run before schedule execution after an independent R6D visual-authority comparison found a real engine-allowlisted browser projection omission: dependency grouping, price/premium 1m/3m/5m changes, and latest material participation transitions were present in sanitized API artifacts but absent from the live display. The partial output was rejected rather than promoted.
- Preserved the rejected 4.9-GiB partial output and empty work root recoverably under `/tmp/r6e1r_rejected_and_partial_diagnostics_20260826/six_final_v1_pre_gui_parity_*`; no authoritative source, protected service, collector, or verified tag was changed. The independently verified projection remains at `/tmp/r6e1r_six_final_v1_projection` for manifest-validated reuse after the repair.
- Completed the R6D live-projection repair and pushed commit `5efe70e9685b98556ae1ad9a860912c7bb1513fc`. The live chart now shows dependency grouping/classification, Futures price changes, CE/PE premium changes, and latest component transitions without browser recomputation. Enriched screenshots contain every fixed/Intraday Price/OI family and populated Futures/CE/PE cards. Current GUI/API/engine targeted suite: 135/135 PASS.
- Resealed the 26-file runtime allowlist: manifest SHA-256 `ed6abec222efd129638c5d7850722be6c638bee85c7702f8ac995ba3b8208064`; engine hash `8a80b51cc15eaa8e4cde7f03d655d780e013790a516f3b036f0b2776afe0b0b0`; 26/26 identities and prohibited-open count zero.
- Stopped the first post-parity focused rerun before schedule sealing when adversarial traceability showed the production harness restarted at only the first analytical ledger boundary. The 349-MiB output and 32-MiB work root were preserved under the rejected diagnostics directory. Extended the schedule to restart once after a durable append for every nonempty material analytical ledger type, reconcile each identity after process recreation, and prove every one remains exactly once after final seal. Added the missing Index-stale/Futures-fresh asymmetric suspension fixture; targeted proof passes.
- Focused all-nine v10 completed all nine schedules in 21m52.68s (parent peak RSS 1,587,568 KiB; child peak RSS 802,032 KiB). Every schedule, semantic hash, eight-ledger comparison, causality invariant, source-integrity gate, and file-open gate passed. The analytical-boundary schedule injected seven durable crashes, one for every nonempty material ledger; `stale_recovery_transitions` was truthfully empty. The run was nevertheless rejected because the availability component compared clean-B's retained pre-fallback inventory eligibility row with live-A's independently reconstructed post-fallback public state.
- Corrected that comparator to use `availability_detail`, the independently reconstructed operational public contract already used to build clean-B's GUI and availability ledger, while retaining the raw eligibility table for audit. A regression proves deliberately contradictory pre-fallback rows cannot override identical public state and that a real public-state mismatch still fails. Harness/orchestrator verification passes 57/57.
- Fresh focused all-nine v11 on pushed commit `85fd16712c2c53d593f4fb22d25d740dbb506b58` passed every acceptance gate. Independent validation confirmed 21/21 canonical components, 8/8 analytical ledgers, 9/9 causal/GUI invariants, 9/9 schedules, 72/72 checkpoint rows, 2/2 truncation/replacement probes, 8/8 source hashes, and 2,331 aggregated audit evidence rows (not a one-row-per-open count). All differences, refusals, future joins, backdating, duplicate IDs, prohibited/unmeasured opens, checkpoint failures, and source mutations were zero.
- Focused v11 wall time was 21m46.61s; harness elapsed was 1,305.894s; parent peak RSS was 1,584,964 KiB and clean-child peak RSS was 797,432 KiB. Summary SHA-256 is `a855629c0b9988e7ab289e5fef473681e6db3981fe8faabc021325eb4d3b3c4a`; state manifest/tree SHA-256 values are `cfc72427a7c9fb629420b47bb0192571f2f3952ff8ebf09e9f4fd08a1db3d957` and `0c7f9cfcde213996da98de45b809bac234c991dd5a6ac332cd99b0514df25871`. The 477-MiB output/work evidence was promoted from volatile storage to `/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_evidence/focused_nine_final_v11*`.
- Full-six v2 completed fresh incremental A and independently clean chronological B baselines, then was deliberately interrupted before schedule execution after the component matrices exposed two real implementation mismatches. Every frozen artifact except Inventory, cross-layer transitions, and their downstream GUI projection was exact; divergence 65, lifecycle 14,201, dense resolution 164,668, dense participation 69,225, participation transitions 32,068, summaries/snapshots 65/65, and synchronized basis 158,746 all matched. This output is diagnostic only.
- The full-six root causes were reproduced from raw-normalized inputs. Intraday inventory used the 2,000-ms basis synchronization tolerance instead of the frozen inventory engine's independent 5-second join, producing exactly four inventory transition-row mismatches. Cross-layer construction reset call-local source ordinals and inventory prior state once per session, while the clean canonical builder carries them chronologically; that explains every remaining ID and nine boundary-only transition differences. No frozen clock, detector threshold, or evidence timestamp requires alteration.
- Preserved the 6.2-GiB rejected full-six output, timing record, and empty work root recoverably at `/tmp/r6e1r_rejected_and_partial_diagnostics_20260826/six_final_v2_inventory_cross_identity*`. Incremental A took 2,157.316s at 6,968,204 KiB peak RSS; clean B took 745.375s; all command return codes, source hashes, and ingestion refusal/checkpoint gates were clean. The interrupted combined comparator high-water was 12,848,800 KiB and is not the deployment-process measurement.
- Repaired the inventory tolerance separation and cross-layer chronological continuation without altering the frozen 2,000-ms basis clock. The continuation persists only compact input-row counters and last states, rebuilds repeated flushes from the immutable predecessor context, preserves per-session fallback inventory identities, publishes sessions in sorted order, and promotes ledger-backed state transactionally. Earlier-session mutation after successor publication, unresolved predecessors, corrupt/evicted legacy contexts, and pre/post-replace persistence failures now fail closed or remain replayable.
- Rebuilt cross-layer transitions diagnostically from the preserved six-session artifacts using the repaired continuation and canonical five-second inventory rows: 60,659/60,659 rows matched exactly, with zero only-A or only-B rows. Cumulative checkpoints were inventory/episode/resolution `0/10/24928`, `0/23/58071`, `63/38/92718`, `137/47/115798`, `188/54/140350`, and `255/65/164668`; the final canonical inventory state contains 28 keys.
- Targeted repaired-engine verification passed 216/216 tests: 120 ingestion/orchestrator/runner tests, 28 equivalence-harness tests, and 68 engine/API/runtime/cross-layer tests. A real 3–4 second as-of fixture proves inventory accepts the frozen five-second join while basis remains unmatched beyond exactly 2,000 ms. State failure injection covers both pre-replace and ambiguous post-replace persistence failures with exactly-once retry.
- Resealed the 26-file runtime allowlist after these source changes. Engine hash: `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`; manifest SHA-256: `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3`. The deployment package remains intentionally stale pending fresh focused and six-session acceptance.
- Pushed the repair milestone as `71a868f1339773df06d0932dd72a3c908caa1028`; `git ls-remote` returned the identical feature-branch hash.
- Two focused v12 invocations were rejected before comparison: the first supplied the authorized fixture parent rather than its manifest-bound `collector/` root and read no analytics; the second omitted the established one-session stack/inventory configs and stopped after incremental A when clean B correctly refused the six-session config. Both partial roots/timing records are preserved under `/tmp/r6e1r_rejected_and_partial_diagnostics_20260826/focused_v12_invocation_*` and are not acceptance evidence.
- Fresh focused v12 then passed on pushed commit `71a868f...`: 21/21 components, 8/8 analytical ledgers, 9/9 schedules, 9/9 causality/GUI invariants, 72/72 checkpoint rows, 2/2 recovery probes, and 8/8 source hashes. Differences, refusals, future joins, backdating, duplicate IDs, prohibited/unmeasured opens, checkpoint failures, and source mutations were all zero; 2,340 runtime-open rows were measured.
- Focused v12 wall time was 22m09.73s; harness elapsed was 1,328.957s; parent peak RSS was 1,586,204 KiB and clean-child peak RSS was 803,968 KiB. Summary SHA-256 is `19b6c15f426b925fa6ec018d65477f4364242d65cfaaa5425423098d3861de15`; state manifest/tree SHA-256 values are `d38ca5e40e60d87d117894df84386fb19b5e1c08347392838a86eef832d92fb3` and `ece5d41515f182761e397b2bf06e1545daab6a91b6d313af18505fd01932a37f`. Evidence is preserved at `/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_evidence/focused_nine_final_v12*`.
- Fresh six-session v3 incremental A and independent chronological batch B matched all 21 canonical components, all eight analytical ledgers, and all nine causality/GUI invariants. Frozen counts were exact, including inventory 255, episodes 65 (41 GREEN/24 RED), lifecycle 14,201, resolution 164,668, dense participation 69,225, participation transitions 32,068, and cross-layer transitions 60,659. Every A/B difference, future join, backdating row, and duplicate analytical ID was zero.
- Stopped v3 before schedules because Reference C reported exactly two failures: both targets compared the rebuilt operational end-of-session availability surface to R6C2's distinct historical layer-eligibility table. The 6.2-GiB partial diagnostic was preserved recoverably at `/tmp/r6e1r_rejected_and_partial_diagnostics_20260826/six_final_v3_reference_availability_scope_*`; it is not acceptance evidence.
- Confirmed the fresh batch-B `layer_availability.csv` is byte-identical to Reference C (SHA-256 `ed70b601360a866a03789d1039316b8d59ace773494311603a57b94bca7fdd9a`). Added a reference-only projection: B/Reference C use their flat canonical horizon table; incremental A independently derives historical eligibility from its sealed inventory, synchronized-basis, and participation publications. Primary operational A/B comparison remains unchanged.
- Reference-availability regression passed 29/29 harness tests. Missing A participation or Intraday material fails only A; a mutated B canonical table fails only B. The preserved real v3 material produced 24/24 exact availability rows for both A and B against Reference C, with zero remainder.
- Deployment preflight found that both systemd post-start commands used health-only probes, which did not gate checkpoint integrity, causal counters, or runtime-source identity. Removed that bypass: both units now execute the full health-plus-readiness contract, still accepting only the explicit benign after-hours 503 state. Backend startup permits 600 attempts with a 250-ms request timeout inside a 900-second systemd boundary; measured six-session memory motivated 8-GiB reclaim and a 10-GiB hard ceiling with swap disabled.
- Deployment service verification passed 14 focused health/unit tests plus the live-GUI service-template regression; `systemd-analyze --user verify` and `git diff --check` passed. Nothing was installed, started, stopped, or restarted. Ports 8805/18805 remain free; protected 8803/8804 and collector processes/hashes remain unchanged. The package manifest remains deliberately stale until the final report/service/source freeze.
- Resealed the final 34-file deployment package after the service/source freeze. Manifest SHA-256: `ebaf193dca7f3cce82974906e05693864db087a60c7f7e3f028a6d1e7dc80ae3`; package hash: `cecb7638566fae1a3831e1ef3fdb94559dce897aa54d89db12c882550c8dbc41`; runtime configuration hash: `b733ea5cc3538b41b8bdc7fcf7a7171b98a41cb0c131968c0e26596bdab93d50`; engine hash: `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`. All 34 file identities and the companion pass.
- Current package/deployment/live-GUI API gate passed 98/98 in 19.50 seconds with 135,972 KiB peak RSS. This is static/package evidence only; install, preload, live health/readiness and public-interface evidence remain gated on six-session acceptance.
- Independent review confirmed the repaired historical availability projection matches preserved real v3 material exactly: incremental A, batch B, and Reference C share semantic hash `e819692a870674bd3826eaedab97a393a94f7046961b08b783b76bc244e826cb`; A and B each match 24/24 rows with zero remainder. Primary operational A/B remains separately exact at semantic hash `70b38e28fcfbcc359e8e97e74b5b8b628b9435582e7cdacac8663a2008c495a4`.
- The review also reproduced a fail-closed comparator gap: mixed flat/nested rows or an absent canonical B/reference availability table could fall back to material reconstruction. Added explicit role-aware schema enforcement: incremental A must supply a nonempty uniform nested operational table; batch B and Reference C must supply nonempty uniform flat canonical tables. Mixed, unknown, missing, or role-swapped schemas now refuse. Harness remains 29/29 PASS.
- Deliberately interrupted fresh full-six v4 after 20m02.30s, before any baseline seal, because its process had loaded the pre-hardening harness. It was analytically unaffected but cannot be promoted as current-source evidence. The 3.0-GiB output, 379-MiB work root, and timing record were preserved recoverably under `/tmp/r6e1r_rejected_and_partial_diagnostics_20260826/six_final_v4_pre_reference_schema_hardening_*`. Fresh v5 will start only after the hardening/package commit is pushed.
- Fresh full-six v5 sealed incremental A and independent clean B with all 21 A/B components, eight analytical ledgers, nine causality invariants, and 30/30 R6C2 reference rows exact. It was deliberately interrupted before schedule completion because R6D GUI comparison exposed 12 guaranteed failures, all historical-availability rows: six sessions times A/B. The 6.3-GiB partial output, work root, and timing record are preserved under `/tmp/r6e1r_rejected_and_partial_diagnostics_20260827/six_final_v5_gui_reference_failure_*`; they are diagnostic only.
- Root cause was a separate comparator wiring gap: the R6D visual-authority path bypassed the already verified role-aware historical-availability projector and compared nested terminal operational `STALE_DATA` directly with flat historical material eligibility. The GUI comparator now derives A independently in incremental mode and B independently in canonical mode only for this reference surface. Operational GUI publication remains unchanged.
- Targeted regression passes 3/3 and includes operational-state preservation, independent target failure when A material is missing, and mixed-schema fail-closed refusal. Recomparison against the preserved real v5 seals passes all 180/180 R6D GUI rows with zero failures in 1m19.43s at 7,306,544 KiB peak RSS.
- Fresh full-six v6 on pushed commit `6eec67bf11ad4ae1e88fda33565c3988d1ca2806` sealed an exact incremental-A/clean-B baseline: 21/21 canonical components, 8/8 append-only ledgers, 9/9 causality invariants, 30/30 R6C2 reference rows, and 180/180 repaired R6D rows passed. Frozen counts were exact through inventory 255, divergence 65, lifecycle 14,201, dense resolution 164,668, dense participation 69,225, participation transitions 32,068, and cross-layer transitions 60,659. Incremental A processed 543,329 records across 104 projected files and 396,713,521 bytes in 2,144.133442 seconds at 6,962,752 KiB peak RSS; clean B completed in 744.855895 seconds with return codes `[0,0,0]`.
- Full-six v6 was nevertheless rejected during `one_record_per_increment`: 898 observations were each refused once at ingestion and once at analytical orchestration, yielding exactly 898 `OUT_OF_ORDER_RECEIPT` and 898 `OUT_OF_ORDER_ANALYTICAL_RECEIPT` rows. The run was interrupted before later schedules and is not acceptance evidence. Wall time before interruption was 1:22:19 and measured peak RSS was 12,992,404 KiB.
- Root cause was confined to explicit-path schedule orchestration. An unresolved Futures candidate held `raw/2026-08-11/events_09.jsonl` behind its durable checkpoint, but later OI-only increments polled only newly changed paths. The OI high-water therefore advanced to `09:16:55.194991` before 898 already-visible raw observations through `09:16:54.963083` were retried. Production discovery was unaffected because production polls every visible stream.
- Repaired the schedule harness to poll each newly changed path plus only already-visible peers whose staged size remains ahead of their durable checkpoint. Explicit empty polls remain empty, the post-drain checkpoint remainder is now a measured zero gate, and no production ingestor, clock, tolerance, threshold, or frozen rule changed. A byte-exact sparse-coordinate regression proves the old scheduler produced one ingestion refusal plus its analytical mirror across an OI hourly rotation; the repaired one-record, restart, and hourly variants publish zero refusals with exact snapshots and ledgers.
- Current repair verification: isolated semantic regression 1/1 PASS; complete equivalence harness 31/31 PASS; ingestion/orchestrator/equivalence set 116/116 PASS in 14.31 seconds at 137,536 KiB peak RSS; `py_compile` and `git diff --check` PASS. Fresh full-six v7 remains mandatory.
- Rejected v6 artifacts were preserved recoverably at `/tmp/r6e1r_rejected_and_partial_diagnostics_20260827/six_final_v6_one_record_order_output`, `/tmp/r6e1r_rejected_and_partial_diagnostics_20260827/six_final_v6_one_record_order_work`, and `/tmp/r6e1r_rejected_and_partial_diagnostics_20260827/six_final_v6_one_record_order.time.txt`. Incremental and batch seal-file SHA-256 values are `6e9ad55ccfeac61ca40492ddccef1a53097cc41c28fbc1f828d6700525494867` and `e48645cfb14184e6f40e7e604508f4f02411d81aca2ddbb062361a2bbee11ba8`.
- Fresh full-six v7 sealed an exact A/B/reference baseline plus five required adversarial variants. The interactive execution cgroup then imposed an external six-hour `SIGTERM` during the intentional analytical-transition restart cut. Exit 143, zero-byte wrapper log/time files, and missing in-memory aggregate open/accounting evidence make v7 rejected partial diagnostics, not acceptance evidence; no analytical assertion failed.
- Started a fully fresh v8 under detached user-systemd unit `r6e1r-v8-equivalence.service` at 2026-08-27 14:14:48 IST. It uses the same pushed analytical commit, exact projection manifest SHA-256 `f6a33fcd95dc601ec8f5f2e07b02b4c9ac0c7a25cee2c66a3a2d3a7dbd257a1b`, all required schedules/references, and separate output/work roots. The service cgroup is independent of tool-session lifetime; v7 will not be stitched into v8.
- Repaired the preload evidence consumer for a manifest-validated reused projection. `reused_existing=true` now requires an exact six-field PASS object bound to 141/139 source/projection inventories, selected-record provenance, dynamic causal-session coverage, and exact contract-selection keys; fresh projections require an empty reuse object. Twelve fail-closed mutation classes plus exact positive acceptance pass.
- Resealed only the 34-file deployment package after the consumer repair. Deployment manifest SHA-256 is `d27aa61a4bb1a1c3ee631cfa108ef2ee0c9a2515c26636db83ec4239bc5757a4`; package hash is `529e72dffca3953ff6c7ecb37dc242afb866b6d371dfbc9f7a5458d3c04a65c5`. The engine manifest remains `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3`, engine hash remains `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602`, and runtime configuration identity is unchanged. Deployment/live-API tests pass 111/111; both unit templates and `git diff --check` pass.
- The first detached v8 attempt stopped after 4m14s because the user manager had `Linger=no`; its volatile `/tmp` and `/dev/shm` output vanished and it is not evidence. Enabled linger directly with `loginctl enable-linger codexuser` (`Linger=yes`). A first persistent v9 launch then correctly failed before analytics because the harness forbids raw staging beneath the research tree.
- Started fresh full-six v10 at 2026-08-27 14:22:32 IST as `r6e1r-v10-equivalence.service`. Its byte-exact projection was preserved under the research evidence tree with manifest SHA-256 `f6a33fcd95dc601ec8f5f2e07b02b4c9ac0c7a25cee2c66a3a2d3a7dbd257a1b`; acceptance output is persistent under research and the separately authorized raw work root is persistent under `/home/codexuser/r6e1r-work`. The service is running with `Linger=yes`; no result is claimed before exit zero and complete post-run validation.
- Hardened the reused-projection preload consumer after independent fail-closed review. It now refuses malformed/unhashable causal sessions, incomplete or invalid dynamic contract rows, invalid provenance/projection hashes, unsafe or duplicate paths, malformed row metrics, and any source/projection selected-record mismatch. The real 141-source/139-projection/746,890-record manifest passes the strengthened contract; 23 negative mutation classes and the complete 122-test deployment/live-API gate pass. Resealed deployment manifest SHA-256 `f0dfd498de4d6cc020517dc99c9c8abb9adfb6118f9fa2f2cf44e7aad3bbf0cc` and package hash `8384f8e55f3943c080e579a37c2fe5c7f16be8ebc554872257d564bf016c827a`.
- Fetched a concurrently published feature history that advanced the same authorized branch through runtime repair `8038c9fcdf1760f25e9b5ddf2d468e47935f749c`, portable deployment `d6736b0108fb40722d2370da422b42e0425c112d`, and handoff `c91df5a660195fa7b4595e0da02488c9db7cb8b1`. These commits materially change the engine/package and therefore must be retained and freshly verified; no published history was rebased or force-pushed.
- Stopped full-six v10 before its first analytical seal because it was running the pre-`8038c9f` engine and could not validate the eventual merged branch. Its persistent output/work/timing material was renamed with `rejected_remote_advance` and is diagnostic only; no canonical failure is attributed to it.
- Began a non-destructive merge of the concurrent feature history with local preload hardening commit `61807358473d46c392aafd97948bbee829d01c7f`. The merged deployment closure is 47 files; fresh focused and six-session acceptance are mandatory from the eventual merge commit.
- Resolved the merge by retaining both the parameterized authoritative-source-root contract and strict reused-projection binding. Fixed the authenticated import-closure test to use the executing virtual environment rather than a repository-local `.venv`, added fail-closed service-user/HOME and stopped-service preconditions to deployment instructions, and documented overload 503 versus oversized-response 502 precisely. Merged core tests pass 273/273; deployment/gateway tests pass 117/117; the broader deployment/API/runner selection passes 173/173; rendered units verify; 38/38 engine and 47/47 deployment identities pass.
- Current merged fixture-browser acceptance passes 1/1 with Chromium/Playwright after supplying the existing host library root. It exercises all six replay dates, separate Index/Futures/Basis paths, master/child persistence through polling/replay/refresh, Intraday-only degradation, participation, transitions, and no browser console/page errors. Current 1600x1915 screenshot hashes are `f1d5548afea149b024f8cac1b42c1ad450c5e2c0398d94ec794b9a8df4439a22`, `729db0b8828c67db807133b67d2f2b1861deaf5c1b1c049ad8436699c616ee90`, and `9cb2d78c568e5d6f2db22b2d4d2af2d4f01ff3f08fc5805175b5be80b72c1155`. The live/latest image is fixture-current, not deployed evidence.
- Focused merged v1 sealed incremental A, then correctly refused before clean B because the invocation supplied the six-session canonical stack/inventory configs for a one-session run. This was an invocation defect, not analytical evidence. The partial was preserved with `rejected_six_session_configs`; no schedule or equivalence result is claimed. Persisted the previously repository-selected one-session configs (stack SHA-256 `d45d8622...`, inventory `7dc5b22b...`), confirmed both match the fixture manifest's dynamically selected Futures, and started fresh focused merged v2 from clean roots. Full-six merged v1 continues independently.
- The exact merged-branch complete repository regression passed 634/634 with zero failures and zero skips. It ran under `r6e1r-complete-regression-merged-v1.service` from the authorized host environment and covered the host-only ptrace/file-open, user-systemd/bubblewrap, browser, and sealed-reference tests. Pytest reported 124.28 seconds; `/usr/bin/time` reported 2m04.69s wall and 670,164 KiB peak process RSS. The retained log/time SHA-256 values are `f076b8abb0535b4f941c99da70c0c1eb9ea4242e897a4c7fb1f54f199668ec6c` and `83aba30d44e6c4a65499afb4d6a7826d5b4aae23ba0bd78649a11af4cdfcf399`.
- Focused merged v2 exposed a single GUI comparator defect after exact analytical A/B publication: 20 analytical components and all eight ledgers passed, while clean B published 11,486 dense resolution observations into `gui_payload.resolution_mechanisms` and live A correctly compacted them to 1,294 material native-mechanism transitions. All other projected GUI surfaces were semantically exact. An in-memory application of the existing live compaction rule made the complete GUI projection exact.
- Stopped focused v2 and full-six v1 before wasting the remaining schedule hours because the shared clean-B GUI builder guaranteed the same false mismatch. Their partial outputs, work roots, logs, timings, and the freshly built six-session projection were preserved with `rejected_gui_resolution_compaction`; no result from either run is acceptance evidence.
- Repaired only `rebuild_clean_gui_payload`: it now independently applies the same per-episode native-mechanism transition compaction as the live callback while leaving dense resolution, lifecycle, clocks, IDs, ledgers, thresholds, and frozen artifacts unchanged. Added a regression proving `A,A,B,B,A` retains `A,B,A` and reports the compact count. Independent static review found exact live/R6D parity and no frozen-rule change.
- Current repair verification passes the complete harness 36/36 and the complete repository 635/635 with zero failures or skips. The retained complete-suite log/time SHA-256 values are `5f63c3436f3bb7dd94f822da05dbdb33d9569536d657fd055e234920ade1e31f` and `e76aa1cdcbec963ccaf73c8f55babd258b329f7baf08eda8952396a421364c8a`; wall time was 2m04.82s and peak process RSS was 670,496 KiB.
- Added a direct bounded-memory gateway regression that streams an 8-MiB-plus-one-byte upstream response and requires the sanitized 502 `UPSTREAM_RESPONSE_LIMIT` result. Gateway security passes 14/14. The complete repository gate after this hardening passes 636/636 with zero failures/skips in 129.36s (2m09.72 wall, 685,556 KiB peak process RSS). Retained log/time SHA-256 values are `a1132553080052c44424e8c936a33a8b7f548661b11390460fd0492463050bef` and `c2127eca2426ccb1a92a48875aa1d8ad2939e2be5ccf99bbaed921de8e175681`.
- Preliminary credential and unsafe-file scans found no key/token signatures, no credential-bearing filenames or raw JSONL/database files, and no tracked/reachable blob over 1 MiB. Current sanitized fixture screenshots are 1600x1915 with SHA-256 `532c0919...`, `307e3373...`, and `a5e75f67...`. Corrected the stale secret-scan note that had incorrectly claimed screenshots and a remote were absent; a final-commit scan remains required.
- Visually inspected all three current 1600x1915 fixture captures. Full context renders fixed 3D/2D/1D plus Intraday Price/OI controls, separate Index/Futures paths, event markers, participation cards and availability. Intraday-only retains the market chart and Intraday controls while fixed layers show explicit missing-prior-session reasons; a stale option layer does not block market display. No outcome language, raw lineage, source path, or credential is visible. Deployed-live capture remains pending.
- Fresh full-six projection manifest SHA-256 `3f4bc4f90d8868d7ef2654f05c5740cf28b2a51b4f835b481dd7262079b8a46d` records 141 authoritative sources, 139 positive-record projected files, and 746,890 selected complete JSON records. The two zero-selected authoritative paths are intentionally not materialized. The consumer split is 104 evaluation files/543,329 records plus 35 causal-context files/203,561 records. All 141 source before/after projection identities are unchanged; source mutations and malformed candidate records are zero; August 17 remains present only for canonical rejection.
- Focused merged v3 and full-six merged v2 were rejected after both independent processes received external `SIGINT` at the same instant, 15:36:16–17 IST, after 33m04s. `/usr/bin/time` records `Command terminated by signal 2`; both Python traces end in `KeyboardInterrupt`, and neither reports an analytical comparison failure. Focused v3 had already sealed exact baseline and one-record results; full-six v2 had built a fresh source-immutable projection. All partial output, work, projection, log, and timing material was renamed with `rejected_external_sigint` and is excluded from acceptance.
- Replaced the transient launch topology with two persistent non-transient user service files under the linger-enabled user manager. The acceptance wrapper ignores unrelated `SIGINT`; systemd still controls the jobs with `SIGTERM`, `KillMode=control-group`, `Restart=no`, and null standard input. Focused merged v4 and full-six merged v3 use clean versioned roots, the pinned clean `c42e703d76ce0fdd9c16f6ed860d8645b95b57c2` checkout, and explicit pinned `PYTHONPATH`.
- An initial persistent-unit launcher preflight failed immediately before any harness output because `PYTHONPATH` was absent. Its tiny log/time files were preserved with `launcher_env_failure`; no output/work/projection root existed. Added the exact pinned `src` path, verified both unit files with `systemd-analyze --user verify`, and relaunched successfully at 15:40:10/14 IST. This was a launcher configuration defect, not analytical evidence.
- The persistent retries were externally stopped before analytical comparison: full-six v3 received `SIGTERM` at 15:42:15 IST after 2m01s and focused v4 was stopped through systemd at 15:42:32 IST after 2m22s. Neither log contains an analytical result and neither root is acceptance evidence. The sender is not recoverable from the available user journal; these are external-interruption rejections, not failures of the callback path.
- A separate long-lived host verifier then started a clean detached focused run at 15:43:11 IST from exact commit `19c5489f9845f1325da1e1f6e3d9118b95bd959b`. That commit contains the identical `c42e703` analytical/harness bytes plus already-passed test/report changes. Its detached checkout is clean and its invocation has the correct fixture, one-session configs, nine schedules, and fresh versioned roots. Do not claim or promote it until exit zero and independent matrix/seal validation.
- Independent audit confirmed the replacement unit topology itself was correct: wrapper SHA-256 `4aa78b3853ff4ad4bd7dd37b848f81d3dc7d8d844561cb3cc032dd1d3b8a7509`; focused/six unit SHA-256 values `39430099c0f0db220fb6a6b1e7a2d8dd56b0d912fe321612e085fb5d08707379` and `0ea4df680642d72f625735409e1053ead3748982d6ba6c1907d9a164fd46d44b`. The later TERM was not OOM and the kernel sender is unavailable; no stronger attribution is claimed.
- Collector PID `1006842` self-exited at 15:40:56 IST through its own recurring near-close watchdog path after `active-option stream silent for 29.0s` and `collector requested clean restart`. The same 15:40 pattern exists on prior sessions. No R6E command signalled, restarted, or modified the collector; no replacement PID exists after close. Collector source SHA-256 remains `0dbd270ba3a1fedc63f4ed8c8eff1947a7c14d08e412b3f82a890cb5500a4a4a`, and its scripts/mtimes are unchanged. Final reporting must disclose the normal self-shutdown rather than falsely claim the old PID remains alive.
- Protected services remain exact despite the acceptance interruptions and collector self-shutdown: 8803 PID/start ticks `380743/46015771`, invocation `d0df21...`, NRestarts 0; 8804 `465394/51980337`, invocation `260291...`, NRestarts 0. Their unit and raw command identities remain unchanged; 8805 and localhost 18805 remain free.
- Created a clean detached worktree at current remote head `19c5489f...`. The exact 38-file engine and 47-file deployment seals, credential/size scans, diff check, and full 636-test regression passed. The three runtime-open/strace and two user-systemd/bubblewrap gates also passed separately 5/5.
- Ran the focused August 19 all-nine gate from new current-head roots. Eight schedules passed. `large_chronological_chunks` reached identical terminal semantic state but failed its append-only exercise/ledger gate with `PERIODIC_EPISODE_EVOLUTION_NOT_EXERCISED` and two differences. Baseline components, ledgers, invariants, runtime opens, checkpoint integrity, refusals, and source hashes were otherwise exact/zero. Preserved exact local reproduction evidence; did not start full-six, deployment, or tagging.
- The rejected focused gate retained 21/21 component, 8/8 ledger, 9/9 causality, 72/72 checkpoint, 2/2 recovery, and 8/8 source-hash passes, plus 2,532 measured open rows and zero refusals, future joins, backdating, duplicates, prohibited/unmeasured opens, or mutations. Large chunks used five nonempty refreshes, observed four lifecycle-exit changes but zero episode-end changes, and produced ledger hash `9f72c051...` versus canonical `27466e2c...` while final semantic hash stayed exact `68070652...`.
- Focused rejected-run summary SHA-256 is `a548c16fdf10f92f32cc33c023a5f7b0aa2ea468a202c9f38cb910afc8788919`; timing SHA-256 `00b22cea6e282d109f3d9e86085fb94b0fbfb809710b5dc39afa09e77a92c301`; wall 56m42.71s; peak parent/child RSS 1,763,052/900,908 KiB. A retained-snapshot, large-schedule-only diagnostic is running from a new versioned root to identify exact ledger rows before repair.
- The retained large-schedule snapshot isolated the entire semantic delta to one provisional absence-based lifecycle publication, `R6B2R-F91B70D4B8E10376C90C` (`EXPIRED_OR_UNRESOLVED`, effective `2026-08-19T11:07:20.370937+05:30`), and its linked cross-layer row `XL-0BC3579C663866CBE2C768A1`. A later standalone raw Index response at `11:52:29` causally suppresses that provisional expiry in the frozen final chronology. Shared ledger IDs were byte-exact and there were no canonical-only rows.
- Repaired append-only publication without changing GUI state or frozen analytics. Periodic flushes now defer provisional absence-based expiry rows, all participation transitions for the affected episode, and cross-layer rows sourced from either provisional lifecycle or participation IDs; the sealed flush releases only rows that survive the final immutable snapshot. A real adversarial fixture proves a later standalone Index response removes one lifecycle, six participation-transition, and seven cross-layer candidates without leaving ghost ledger rows, while retained rows publish once.
- Reworked large-chunk refresh evidence so each evaluation session contributes two deterministic interior, session-local targets bound dynamically to actual merged source coordinates. Closure now requires two successive periodic generations; changes first visible only at final seal are reported separately. The gate verifies exact discharge, dirty-state/flush/accepted-count/cutoff advancement, distinct target-session recomputation, target identity, actual global ordering, and opportunity/observed/missing set consistency.
- Independent re-review found no remaining release-blocking defect. Full orchestrator tests pass 112/112; full equivalence-harness tests pass 38/38 in 12.57 seconds at 137,656 KiB peak RSS; `git diff --check` passes. Engine manifest is 38/38 with manifest SHA-256 `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7` and engine hash `362474858eda75b18180ad2fce48e50e1d4acdd1b04a0db405eaae199e70b7a7`. Deployment package is 47/47 with manifest SHA-256 `ca505bb67ee46247e5d68d4dfa60d6b82de4dbc126eec3214ebed1b2647c33e4` and package hash `940ef119e7caf4cbc0599fd5bd24f79b5bca352061da67b00541242c33d1435e`.
- Two repair diagnostics are explicitly rejected: v2 failed at launch because `PYTHONPATH` was omitted; v3 was externally interrupted by signal 2 after 7m36.88s at 1,339,084 KiB peak RSS before schedule seal. Neither is analytical evidence. Fresh committed large-only, focused all-nine, and full-six all-nine gates remain mandatory.
- The combined repaired ingestion/callback/orchestrator/equivalence gate passes 277/277 in 28.98 seconds (29.25 seconds wall, 145,384 KiB peak RSS). Both manifest companions and `git diff --check` also pass immediately before the repair milestone commit.
- Committed and pushed the repair milestone as `bd01b8d3e7ca4670935a4eb1289e6dcfb80c8672`; `git ls-remote` returned the identical feature-branch hash. The verified historical tags remain unchanged and no R6E verified tag exists.
- Fresh focused large-chunk repair v4 passed from a clean detached checkout of `bd01b8d...`: component, ledger, causality, schedule, checkpoint, and recovery failures are all zero; its 1,733 total audit rows comprise 1,724 runtime-open rows, 8 source-inventory rows, and 1 fixture-manifest row, with zero prohibited/unmeasured opens; analytical refusals and source mutations are zero. Terminal semantic and ledger SHA-256 values are the canonical `68070652aaa24a54b3fb30649e7869731f0c37835d59cc1e315e332502d7cb69` and `27466e2caaa730b7a4999be7f6b413f418e3fcd45ff5fd3b34a214350d7613a1`.
- Both session-local periodic refreshes were exactly discharged at actual record ordinals 15,516 and 31,033; both advanced accepted counts, causal-evidence cutoffs, and valid-basis cutoffs, returned the dirty target, and used distinct poll generations. Future joins, timestamp backdating, duplicate analytical IDs, and synchronization-tolerance violations are all zero. There was no causal successive-periodic episode/lifecycle closure opportunity; two lifecycle changes were truthfully classified finalization-only and did not satisfy the periodic closure gate.
- Large-only summary/seal SHA-256 values are `4821b9fba0d9940f2020babf5974a104637d2ea1529691cddca80a09945a8387` / `a9787906afb3d13f406627f7386f9a570d25171596e0638fe127793e52321142`; timing SHA-256 is `982a63d47faeee32039444a43594c09ef7adadfa4decb576901c5091dc10a5b7`. Wall time was 8m54.59s, process peak RSS 1,568,472 KiB, clean-child peak RSS 900,372 KiB, and cgroup peak memory 2,426,519,552 bytes.
- Protected services were unchanged after the diagnostic: 8803 PID/start ticks `380743/46015771`, invocation `d0df21acd54a440788d89f7cad5b4827`, NRestarts 0; 8804 `465394/51980337`, invocation `260291b2ae4a4c70a95a0a37722af61e`, NRestarts 0. Ports 8805 and 18805 remain free.
- Pushed the large-only evidence handoff as `e01b5c6f7a6458923f71828c17d23f4afdefb10d`, then ran focused all-nine v13 from a clean detached checkout of that exact commit under non-networked persistent invocation `6c071f67e68649cfad967d23309b8750`.
- Focused all-nine v13 passed every acceptance surface: 21/21 components, 8/8 analytical ledgers, 9/9 causality invariants, 9/9 schedules, 72/72 checkpoint rows, 2/2 truncation/replacement recovery probes, 8/8 source-hash comparisons, and 9/9 required-feasibility rows. All component/ledger/causality/schedule/checkpoint/recovery differences or failures were zero; its 2,508 total audit rows comprise 2,499 runtime-open rows, 8 source-inventory rows, and 1 fixture-manifest row, with prohibited/unmeasured opens zero; analytical refusals and source mutations were zero.
- All schedule seals reproduced semantic SHA-256 `68070652aaa24a54b3fb30649e7869731f0c37835d59cc1e315e332502d7cb69` and ledger SHA-256 `27466e2caaa730b7a4999be7f6b413f418e3fcd45ff5fd3b34a214350d7613a1`. One-record exercised 46,550 polls/records with three required causal peer repolls and zero final remainder. Variable chunks exercised nine group sizes over 6,312 polls. Boundary mode exercised 17 partial-line splits. Empty mode injected 34 explicit empty polls. Checkpoint mode survived seven restarts. Analytical-boundary mode covered all six nonempty material ledgers exactly once; availability/stale-recovery were correctly empty. Hourly rotation exercised 6/6 boundaries. Large chunks discharged both actual periodic refresh targets and retained zero safety violations.
- Focused v13 harness elapsed was 3,429.450 seconds; `/usr/bin/time` wall was 57m10.47s. Peak parent process RSS was 1,775,736 KiB, clean-child peak RSS 895,316 KiB, and cgroup peak memory 2,408,161,280 bytes. Summary/state-manifest/state-tree SHA-256 values are `82ae10e47c06c7ed5d1a40545982ae2f43aae357654a173783d20be73f6f4576`, `6a0a9e9a4fd0acc4ad108a20051ad47f6b3101fe8cf10df267855bded14c50cc`, and `6c7e595ff66a9b6855329038eafaf18f5d69e282bb265f2d7766c70e11f9b452`; timing SHA-256 is `9c715e3bbbce2c365c40901f76389ea45b6af558a6879448a84d761cd1e247f7`.
- Post-focused fixture manifest verification passed. Protected services remain exact: 8803 `380743/46015771/d0df21acd54a440788d89f7cad5b4827/NRestarts0`; 8804 `465394/51980337/260291b2ae4a4c70a95a0a37722af61e/NRestarts0`. Ports 8805/18805 are still free. Full six-session all-nine is now the analytical deployment gate.
- Full-six v1 preflight passed on pushed head `e107280c886039a70c0128dbda64ea1998e15e24`: 38/38 engine and 47/47 deployment manifests exact; current engine verifier reports 39/39 allowlisted opens and zero prohibited; R6C2R/R6D reference manifests pass; all eight causal raw/OI session directories are readable; 261 GiB disk and 28 GiB available memory were present; protected service identities remained exact.
- The first hardened unit start correctly failed before analytics because systemd stripped quotes inside two inline Python prechecks. Only a 671-byte log existed; no projection/output/work/time root was created. Preserved it as `six_session_e107280_final_v1_launcher_quote_failure.log`, SHA-256 `55ae7148f6ae4fdf3f19e0037facee1425bd6c5455849cd463325ed2c5d5e807`. Ran both verifiers directly, removed the redundant broken inline checks, reverified the unit, and continued with fresh roots.
- Full-six v1 started at 18:32:23 IST under persistent invocation `1e09d6da7a064fbf855869968b56d8ad`. It is pinned to clean `e107280...`, builds a fresh authoritative projection, requires both references and frozen counts, runs all nine schedules with retained snapshots, cannot use TCP (`AF_UNIX` only), and has 24/28 GiB high/hard memory bounds with swap disabled. No result is claimed before complete seal validation.
- Full-six v1 was externally stopped through systemd at 20:18:00 IST before incremental A sealed. The journal contains an explicit `Stopping`/`Stopped` transition rather than a process-completion line; `/usr/bin/time` output is empty and `equivalence_summary.json` is absent. The last material counts were incomplete (54 divergence, 11,364 lifecycle, 26,959 participation transitions and 49,971 cross-layer transitions), so this root is rejected interruption evidence only. Neither the main agent nor the independent read-only monitor issued a stop, kill, restart, signal, reload or write command. No analytical mismatch occurred.
- The fresh v1 projection is retained and independently identified by manifest SHA-256 `d9456635a7dce996b45932e522e179eba6b6cb37d4c958352d86dabb76fd09b1`: 141 authoritative sources, 139 byte-exact projection files, 746,890 selected complete outer records, six evaluation sessions, canonical August 17 rejection, zero malformed candidates and zero source mutations. A fresh v2 run may reuse it only through the harness's complete manifest/source/provenance revalidation path; no v1 analytical state or partial ledger may be reused.
- Fresh full-six v2 started at 20:20:42 IST under invocation `38a2f191ee654b2ca0bc2fa622a59e1d`, pinned to the same clean `e107280...` checkout. It has brand-new output/work/state roots and reuses only the byte-exact v1 projection through the harness's fail-closed full manifest/provenance/authoritative-source revalidation. The unit refuses manual stop requests; its configured stop signal is the wrapper-ignored SIGINT with an infinite stop timeout, while an explicit SIGTERM kill remains available for a genuine analytical failure. Engine, harness, configs, references and frozen gates are unchanged.
- Full-six v2 passed reuse validation (141 sources, 139 projection files, 746,890 provenance rows and eight dynamic causal-session contracts), then received a direct unsolicited SIGTERM at 20:24:47 IST. It exited 143 after 4m04.08s with no summary and no analytical mismatch. This was not a systemd stop request, so `RefuseManualStop` could not block it; v2 is rejected interruption evidence only.
- Added a host-only acceptance launcher that carries ignored SIGHUP/SIGINT/SIGTERM dispositions across exec. A disposable isolated service proved GNU time and its Python child survive all three signals when delivered to the entire cgroup, then an explicit SIGKILL terminated only that test. Fresh full-six v3 started at 20:26:54 IST under invocation `8373f3d0a14d402ca4d08eeddac37aa1` with brand-new analytical/work roots and the same fully revalidated raw projection. Its unit still refuses manual stops and has infinite stop/runtime timeouts; a deliberate SIGKILL remains available only for genuine failure.
- Full-six v3 survived the tested HUP/INT/TERM windows, then received a direct SIGKILL at 20:58:10 IST after 31m16.12s. It exited 137 with no `equivalence_summary.json`, no canonical schedule seals, and no acceptance matrices. Cgroup peak memory was 10,301,947,904 bytes below the 24/28 GiB limits; swap was zero and no kernel OOM evidence was present. This root is rejected interruption evidence only.
- A separate pre-existing Codex session on the same host was identified as concurrently working on an independently reconstructed `fix/r6e1r-final-live-shadow-v2` branch. Four seconds after the v3 SIGKILL, the user-manager journal recorded a daemon reload, and that session immediately began host regression work. No attempt was made to stop, signal, attach to, or otherwise interfere with it. Its branch and outputs are being audited read-only; only independently verified, byte-compatible work may be integrated.
- Read-only branch audit found one material deployment fix on v2: the backend unit's embedded raw runtime-config SHA was synchronized to the committed template bytes and the 47-file deployment package was resealed. The engine manifest and engine/orchestrator bytes are otherwise exact against `e107280`. Deployment of the `e107280` package remains prohibited until that digest repair is integrated and independently verified on the authorized branch.
- Integrated only the independently confirmed deployment correction: the backend unit now authenticates raw runtime-config SHA-256 `ecfa9e1a8afb4622f8d4f3128511817bef451f5353ff1998d72e6475c67ebab2`. Preserved the stronger authorized-branch deployment README and excluded the v2 diagnostic harness/report rewrites. The current 47-file package is exact with manifest SHA-256 `aa1e0280613e4418db01bbaed9a14d79468dbbaf8cb98fdee33581c5621b5dd4`, package aggregate `a73163704cb8131ab0f1a157738bdea358accd5b7985f6b846a95bc3c760127f`, corrected service SHA-256 `e5dbf764dc89f1b5200fce2032851b737eda0f06d3047b316202b766b50709da`, and unchanged 38-file engine identity.
- Added two tests from independent review for behavior already present in the accepted engine: interleaved GUI resolution episodes compact independently, and restart before provisional-expiration stabilization produces one-shot-equivalent material ledgers for both late-response and session-seal outcomes. The targeted unit/package selection passed 5/5.
- The first complete-suite invocation was environment-incomplete: 613 passed, nine failed before or outside the affected product paths, and twenty external-evidence tests skipped because the explicit venv subprocess path, sealed reference roots and Chromium library root were absent. It is retained as an invocation failure. The unchanged fully provisioned rerun passed 642/642 with zero failures or skips in 116.61s; wall time was 1m56.96s and peak process RSS 672,784 KiB.
- Added a fail-closed, schedule-bundle resume path after three externally interrupted full-six attempts demonstrated that an indivisible 18+ hour all-nine run was operationally fragile. Every resumed invocation still rebuilds fresh incremental A and clean batch B, rechecks both references/counts/source hashes/runtime opens, and imports only marker-last, fully sealed schedule bundles bound to the exact clean Git commit, harness SHA-256, canonical engine identity, configs, projection, raw-source inventory and schedule definitions.
- Two independent security reviews rejected intermediate resume drafts and drove closure of artifact-publication durability, import-open accounting, path confinement, source/accounting rederivation, final destination revalidation, an identical-byte symlink-swap TOCTOU, and `/proc/self/fd` descriptor-number reuse in audit provenance. The final frozen harness/test SHA-256 values are `d1871428077d21eab52e409a809f885e197c5600cad10279e656da00b53c19f2` and `cc9fedc85883ac7ffa89f2edca5a4883c10c97050f7001157c72727e01001733`; both reviewers approved the final bytes.
- Exact-current verification passes 53/53 harness tests and 294/294 combined ingestion/orchestrator/harness tests. Descriptor-anchored reads walk ancestors with `O_DIRECTORY|O_NOFOLLOW`, open regular files with `O_RDONLY|O_NOFOLLOW`, stream/hash/copy from the same descriptor, classify resume imports from the resolved target only, and refuse the reproduced external-symlink attack. Existing engine/deployment manifests remain byte-exact because this offline harness is intentionally outside both allowlists; the historical R6E1R0 path-only manifest requires no reseal.
- Pushed the hardened resume milestone as `81b0836fe50939246ae210bb62780ac4e163e100`; the remote feature branch returned the identical hash. The first post-commit complete-suite invocation ran from a `/home` detached worktree and produced 654 passes plus two systemd/bubblewrap boundary failures because those tests intentionally use `ProtectHome=true`; this invocation is rejected as a launch-location error. The unchanged rerun from an `/opt` detached worktree passed 656/656 in 1m57.77s with 674,080 KiB peak RSS. Passing log/time SHA-256 values are `6eaf04009b8614136bf29a1cd52b04fef693e3e47b1ef851291650ec08ca3eaf` / `27bbb76f950b824eec1cd093dc7cadf69938e69387ee00476069d236b51b0e8f`.
- Fresh focused post-resume acceptance from clean commit `81b0836` passed: 21/21 components, 8/8 ledgers, 9/9 causality invariants, 9/9 schedules, 16/16 bundle-storage gates, 72/72 checkpoint rows, 2/2 recovery probes and 8/8 source hashes. Its 2,508 total audit rows comprise 2,499 runtime-open rows, 8 source-inventory rows, and 1 fixture-manifest row, with prohibited/unmeasured zero; future joins, backdating, duplicate IDs, refusals, source mutations and every comparison difference were zero. All eight fresh marker-last bundles independently passed fail-closed revalidation (40/40 artifacts). Summary SHA-256 is `c3014578c237b2ea13ff0167b6a520ffb48082897970fbeb4eff5e31a241620e`; contract payload `0e6913f9406504010e7eb24036b0287c238f2e7fd2351d73ac712b1b68f8c8b6`; wall 56m36.55s; parent/child peak RSS 1,784,340/898,880 KiB. This focused run published fresh bundles but intentionally did not exercise import, frozen six-session counts or references.
- Prepared and independently verified inactive full-six unit `r6e1r-six-81b0836-final-v1.service`, SHA-256 `6684d38c66bb00287d6b16ca80f54260f450dbb43fdddf447f965f371472215e`, with fresh absent roots and expected contract `3b5c467104c78522724169e517c841791e93490933930de0c3d87a0774c31b8f`. Its start preflight correctly aborted before creating any root when it detected the separate pre-existing session's active `r6e1r-v2-six-a12a586-v1.service`. Do not stop or reuse the other session; wait for it to become terminal before starting the authorized unit because concurrent full-six runs can exceed the no-swap host's safe memory envelope.
- Reassessed the launch hold after measuring the other cgroup rather than using
  its cache-inclusive peak: host MemAvailable was 28.95 GB, the other run used
  about 2.2 GB anonymous memory with most cgroup memory in reclaimable inactive
  file cache, eight CPUs were available, and disk free was 248.80 GB. Two
  observed acceptance peaks fit with substantial headroom, while the other
  run's 18.2 GB original-chunk pass was only about 1.9% complete and waiting
  would defer the authorized gate by well over a day.
- Repeated every fail-closed launch check and started the isolated canonical
  full-six unit at 2026-08-27 23:33:15 IST. Invocation is
  `b538f7e58a7c4f8796963ea46e58eeb0`, main PID at launch `1245008`, unit
  SHA-256 `6684d38c66bb00287d6b16ca80f54260f450dbb43fdddf447f965f371472215e`,
  commit/remote head `81b0836fe50939246ae210bb62780ac4e163e100`, and expected
  contract `3b5c467104c78522724169e517c841791e93490933930de0c3d87a0774c31b8f`.
  It uses fresh roots, reuses only the fully revalidated raw projection, binds
  no TCP family, and does not touch the separate run. Protected services remain
  `380743/46015771/d0df21acd54a440788d89f7cad5b4827/NRestarts0` and
  `465394/51980337/260291b2ae4a4c70a95a0a37722af61e/NRestarts0`.
- Independent live contract/isolation audit passed after launch. Contract file
  SHA-256 is `d50af58c41068d825bebfd420766619ebe6b8ad23136465a882c90ddd767fcd3`
  and its recomputed inner contract is the expected
  `3b5c467104c78522724169e517c841791e93490933930de0c3d87a0774c31b8f`.
  Projection 139/139 files (541,091,186 bytes), 141 authoritative-source rows,
  both references, frozen-count/reference contracts, commit, harness, engine,
  configs, dates, schedules, required profile, and source size/mtime identities
  all matched. Bidirectional live-FD inspection found zero cross-run paths;
  roots are distinct/non-nested, shared inputs are read-only, and the canonical
  unit has no network family beyond AF_UNIX. No harness/unit rule prohibits
  different-root concurrent offline runs. The other process therefore does not
  invalidate equivalence, but final elapsed time must be labelled conservative
  and contended rather than an isolated benchmark.
- Canonical incremental A sealed after the overnight date rollover and clean B
  began under child `strace` coverage. A seal file SHA-256 is
  `e8289a90cbad1e491bd3783f2e61574b1e4267870adfebd9d64746f1a2acd176`;
  snapshot/semantic/ledger hashes are
  `87e7caa946560191902fa1dff6ab1f839667ec18ccb96c04702f933bfc0b28d1`,
  `bd8bdbaaeac3db54c289575d7c0d3f3fca73934f0830ab974656ded3c6175527`,
  and `4eb8d6920a63821e469843e44e02a6996704b327a37e7f2d3918bee063a8fb65`.
  The 26-file state manifest file/tree identities are
  `5fd57ead140e18eba6a56cc215569611860e6cc4d816836239a9e69e610cbdc3` /
  `d9a34d15c60ba98a73853a004a454bbde3288c2d98c0d1677e1f9089fc5eb1f0`
  over 4,141,836,283 bytes. A measured 104 evaluation sources,
  396,713,521 bytes, 543,329 JSON records, 25,293,503 expanded complete rows,
  65 polls, 6,004.836 seconds and 6,496,920 KiB process peak RSS, with zero
  checkpoint failures, analytical refusals, dirty sessions or unexpected
  staged sessions. These are baseline facts, not a full equivalence result.
- Clean B sealed after 786.827 seconds with seal file SHA-256
  `47d20adf5e0c14cb44dc722c49fe333ae731794d878e0d28ec7303d32c84fbe0`,
  snapshot `082c5b727ba917196f9d3cf4382fd2c20b81b3a6c0f8e61500cfe08a0ce1aecd`
  and the same canonical ledger hash as A. Baseline A/B component equivalence
  then passed 21/21 with every A-only, B-only, field-mismatch and unexplained
  remainder zero. All frozen counts were exact, including 255 inventory,
  65 episodes (41 GREEN/24 RED), 14 retriggers, 14,201 lifecycle,
  164,668 dense resolution, 69,225 dense participation, 32,068 participation
  transitions and 60,659 cross-layer transitions. Component matrix SHA-256 is
  `fd5fad066510b5fe01f5914f55aa3fa2b7fbac9b27af9a9caa4da76b658cf388`.
  All 8 append-only analytical ledgers also passed with zero A/B identity or
  content differences; ledger matrix SHA-256 is
  `e68f5f098b6157160b2a27e51c4bc709a6bc0fc25aa71e7fcb39617c8cb77e48`.
  This closes only baseline A/B; causality, references, alternate schedules,
  runtime opens, source post-hashes and final summary remain mandatory.
- Baseline causality passed 9/9 for both A and B with future joins,
  synchronization-tolerance violations, timestamp backdating, duplicate IDs,
  valid-to-NaT regressions, analytical refusals and all three GUI clock/display/
  path violations equal to zero. Matrix SHA-256 is
  `f5370e1ce6ce067b2ae5a3a090c0215d9c6c7a548348b724f97d2df963164bf2`.
  The same run reverified the frozen R6C2R reference 74/74 files and R6D
  reference 40/40 files; verification artifact SHA-256 is
  `ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.
  Row-level reference comparisons, schedules and final gates remain pending.
- The independent row-level reference gates then passed without unexplained
  remainder. The R6C2R component matrix is 30/30 PASS with target-only,
  reference-only and unexplained rows all zero; SHA-256 is
  `0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8`.
  The R6D GUI matrix is 180/180 PASS with zero reference-only and zero
  unexplained rows. Its 174,080 target-only live-extension rows are exactly
  matched by 174,080 explicitly permitted extension rows; SHA-256 is
  `dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467`.
  The nine-schedule feasibility matrix SHA-256 is
  `8142dbaf073d59719922838bf41b59c1f231d6b32bcd2b08e33f1da943640682`;
  seven schedules are below the reporting cap and two are above it, but the
  required profile continues to execute all nine. Alternate schedule,
  recovery, runtime-open, post-source-hash and final-summary gates remain
  pending.
- A fresh read-only deployment preflight at 2026-08-28 01:51:56 IST found
  `127.0.0.1:18805` and public candidates 8805--8810 free, both R6E1R units
  uninstalled, `Linger=yes`, user-manager control available, package/engine
  manifests still 47/47 and 38/38, and an absent writable isolated root at
  `/opt/banknifty/research/r6e1r_live_shadow_81b0836`. Ports 8803/8804 retained
  exact PIDs, start ticks, invocation IDs and zero restarts. Local prerequisites
  pass; UFW is enabled with default input DROP and this account has neither
  rule-inspection/change authority nor provider-firewall authority. External
  reachability may therefore be the only genuine deployment blocker after
  analytics pass. No deployment byte or service state was changed.
- The full-six `one_record_per_increment` schedule published its atomic bundle
  at 2026-08-28 05:00:56 IST and an independent revalidation passed. Marker
  SHA-256 is
  `013c844625d1b67ff48568e5f3db4ab0859ae6cc2694ad360c14e29e2944dfaa`;
  it was published 0.700 seconds after the newest of five exact artifacts.
  Semantic/ledger hashes equal canonical A at `bd8bdbaa...` / `4eb8d692...`;
  exactly 543,329 one-record increments and polls exercised group size `{1}`.
  Checkpoint accounting is 104/104 with deferred tails zero; source integrity
  is 139/139 over 541,091,186 bytes; 616 trusted audit rows measured
  10,015,056 opens with exact 243-row required coverage and zero prohibited,
  unmeasured, failed or derived-input rows. Schedule elapsed time was
  11,835.445 seconds and peak process RSS 17,202,120 KiB. This closes only the
  first alternate schedule; the variable-chunk schedule then began.
- The full-six `deterministic_variable_chunks` bundle independently passed.
  Marker SHA-256 is
  `58ae34e2190f89254901e13c77c998a60b60f32bada7121a7a9c6b4f81ac75e8`
  and was marker-last by 0.703 seconds. It exercised exactly 73,672 increments
  over 543,329 records with group sizes `{1,2,3,5,7,11,13,17}` and the exact
  sequence SHA-256
  `446e05431b4b90f66badc41f09992b46391a2b890c21741d6ae523fb3026c584`.
  Semantic/ledger identities equal canonical A, refusals/differences are zero,
  checkpoints are 104/104, sources are 139/139, and 616 trusted audit rows
  cover 1,656,420 opens with no prohibited/unmeasured/derived/failed rows.
  Elapsed time was 4,005.174 seconds and peak process RSS 17,259,876 KiB.
  The 90 incidental hourly introductions are non-gating here; the dedicated
  hourly schedule owns the exact 92-boundary contract.
- The full-six `boundaries_inside_jsonl_lines` bundle independently passed.
  Marker SHA-256 is
  `3ead219a15f766399f7395d12e3f56da7a6e22d59f81db665c1f29a4e451fed2`
  and was marker-last by 0.721 seconds. Exactly 17 configured/expected/observed
  inside-line boundaries were exercised; all 543,329 records were exposed
  through 95 increments and 146 polls, with maximum group size 4,194,302 bytes
  under the 4,194,304-byte limit. Canonical semantic/ledger identities match;
  checkpoints are 104/104, sources 139/139, and 616 trusted audit rows cover
  328,727 opens with all prohibited/unmeasured/derived/failed counters zero.
  Elapsed time was 3,071.805 seconds and peak process RSS 17,259,876 KiB.
- The full-six `empty_repeated_polls` bundle independently passed. Marker
  SHA-256 is
  `4d95dec0d52bd1f8641cf8d3741bebb2767646c576ec1b8b588b8e8e7eddb7bb`
  and was marker-last by 0.718 seconds. Independent threshold derivation gives
  17 events times two repetitions, exactly matching 34 observed empty polls;
  95 data increments plus 34 empty polls equal 129 polls. Semantic/ledger
  hashes match A, checkpoints are 104/104, sources 139/139, and 616 trusted
  audit rows cover 328,173 opens with every prohibited/unmeasured/derived/
  failed counter zero. Elapsed time was 2,942.253 seconds and peak process RSS
  17,259,876 KiB.
- The full-six `multiple_checkpoint_restarts` bundle independently passed.
  Marker SHA-256 is
  `7f0d9f9bf168db7ca73117b9d36a27d2f6d625b572e299b276a384105a16a44d`
  and was marker-last by 0.682 seconds. Configured, independently expected and
  observed restart counts are exactly 7/7/7; checkpoint failures, maximum
  causal backlog paths, repolls and final remainders are all zero. Canonical
  semantic/ledger hashes match; checkpoints are 104/104, sources 139/139, and
  617 trusted audit rows cover 328,286 opens with all prohibited/unmeasured/
  derived/failed counters zero. Elapsed time was 3,995.251 seconds and peak
  process RSS 18,429,628 KiB.
- The full-six `analytical_boundary_restarts` bundle independently passed.
  Marker SHA-256 is
  `e9bdf96d5d2a7d404bd2d2a2077ebc1ea81f397ff73c67ac7b1292f9fe3420fc`
  and was marker-last by 0.646 seconds. Of eight material ledger types, six
  were nonempty at the probe and all six were crash-covered exactly once:
  divergence, dependency, lifecycle, inventory, participation and cross-layer.
  Availability and stale-recovery were empty at the injection point, so no
  boundary was manufactured. Every injected event occurs exactly 1/1/1 times
  before restart, after restart and after retry/seal. Canonical semantic/ledger
  identities match; checkpoints are 104/104, sources 139/139, and 990 trusted
  audit rows cover 351,146 opens with prohibited/unmeasured/derived/failed zero.
  Elapsed time was 7,813.369 seconds and peak process RSS 18,987,460 KiB.
- The full-six `hourly_file_rotation` bundle independently passed. Marker
  SHA-256 is
  `22a6d20302a7a3c4d7ac77181d29bfd0a31111b42fd6c0fd143bba9924be47e4`
  and was marker-last by 0.676 seconds. Independent reconstruction found 104
  live files across 12 stream/session chains, so the exact required rotation
  count is 104 minus 12 = 92; observed rotations were exactly 92, with zero
  files pre-staged before the first poll. All 543,329 records were exposed in
  5,484 increments/polls. Canonical semantic/ledger identities match;
  checkpoints are 104/104, sources 139/139, and 616 trusted audit rows cover
  425,427 opens with prohibited/unmeasured/derived/failed zero. Elapsed time
  was 3,209.040 seconds and peak process RSS 19,259,224 KiB.

- The first isolated live activation exposed a sparse-predecessor defect that
  the historical six sessions did not exercise: August 26 contains qualifying
  Futures/OI evidence but no in-window Index rows, and the empty Index branch
  of `backward_join` constructed a timezone-naive `NaT`. Subtracting it from
  aware Asia/Kolkata availability clocks raised `TypeError` during fixed-context
  construction. The branch now preserves the aware dtype, yielding unmatched
  rows and graceful empty OI evidence; naive availability clocks are refused.
  Frozen eligibility, thresholds, joins, and timestamp semantics are unchanged.
- The repair changes the authenticated engine identity to
  `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947`.
  Engine manifest SHA-256 is
  `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210`;
  runtime configuration identity is
  `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41`.
  The authenticated systemd config pin and 47-file package were resealed;
  package aggregate/manifest SHA-256 are
  `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949` /
  `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391`.
- Targeted aware/empty/refusal tests pass 3/3. The first complete regression was
  retained at 659 pass / 1 fail because the systemd unit still pinned the old
  config byte hash; after repairing that packaging defect, the exact failed
  tests pass 2/2 and the unchanged complete suite passes 660/660 in 118.03s,
  with zero failures or skips. Because an authenticated engine byte changed,
  focused and full-six all-nine equivalence must now be rerun from fresh state.

- Fresh post-repair focused acceptance completed from clean detached commit
  `e1d67c534bea5c61b0e3d379db7f599de7e1c445`: 21/21 components,
  8/8 ledgers, 9/9 causality invariants, and 9/9 schedules passed with every
  difference and safety counter zero. Eight alternate schedules published
  marker-last bundles and passed 16/16 publication/final storage gates;
  checkpoint accounting passed 72/72 and recovery passed 2/2. All 8/8 fixture
  sources rehashed unchanged. The measured file-open audit contains 2,508 rows,
  including 2,499 runtime rows representing 1,190,240 opens, with zero
  prohibited or unmeasured opens. Summary SHA-256 is
  `f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
  Harness elapsed was 3,839.101 seconds; wall time 1:04:00; process/child peak
  RSS was 1,730,828/891,172 KiB; systemd cgroup peak was 2,965,729,280 bytes
  with no swap or memory-pressure event. The fresh full-six run remains active.

- Full-six final-v2 was externally interrupted during its one-record schedule,
  not by an analytical or resource failure. The journal records SIGINT at
  17:18:05, SIGTERM at 17:18:23, and SIGKILL at 17:18:54, each "on client
  request"; the unit was runtime-masked. It had used no swap, emitted no OOM,
  and correctly withheld the incomplete schedule marker. Before interruption,
  fresh A/B/reference gates had passed (21/21 components, 8/8 ledgers, 9/9
  causality, 30/30 R6C2R, 180/180 GUI) with exact frozen counts and zeros.
  The v2 root is preserved unchanged as interrupted evidence.
- Recovery final-v3 launched under invocation
  `d15e42ff1149423e9dbcea606d3d638e` from the same clean analytical commit,
  source projection, references, configs, and all-nine contract. It uses the
  harness's fail-closed `--resume-schedules-from` interface against v2. Because
  v2 had no complete alternate schedule bundle, no partial output is imported:
  A, B, references, and all schedules run fresh. Recovery unit SHA-256 is
  `69d35b550f6493a2a8018001a4e54358772dd2c311d7bb7c786b478953892deb`.

- The same concurrent cleanup transaction then runtime-masked and SIGKILLed
  final-v3 after 30 seconds and a neutral-named final-v4 after launch; a direct
  final-v5 process collided with its continuing post-cleanup verification and
  exited 137. User-slice OOM counters remained exactly zero. Process inspection
  showed the external transaction explicitly checking R6E analytics, shadow,
  browser/gateway processes and masked units. After its final check exited and
  no cleanup process or systemd job remained, direct managed final-v6 launched
  from fresh roots. It retains the exact e1d67c5 contract and v2 resume source;
  it remained alive beyond the prior kill window with parent/Python PIDs
  1575349/1575354. V3-v5 produced no analytical state or eligible bundle.

- At 17:30:10 IST the direct final-v6 process was also externally terminated;
  OOM counters remained zero and it had not sealed A or any alternate schedule.
  Subsequent reconciliation found the cleanup had deleted the entire prior
  `r6e1r_final_evidence` tree, all v2-v6 work/output/log/time paths, the clean
  e1d67c5 checkout, and the reusable 541 MB raw projection. This also removed
  the interrupted v2 files after their A/B/reference identities had been
  independently recorded. Deleted or incomplete artifacts remain ineligible.
- After the cleanup transaction and its final checks were absent, a single
  neutral-path recovery was admitted at 17:42:56 IST. It uses a fresh clean
  detached checkout at `e1d67c534bea5c61b0e3d379db7f599de7e1c445`, exact
  engine/deployment manifests, the authoritative raw root, both frozen
  references, all six sessions, and all nine required schedules. Because the
  prior projection and bundles were deleted, it rebuilds the byte-exact raw
  projection and reruns A, clean B, references, and every schedule fresh.
  Its command executes the exact repository harness bytes with canonical
  `__file__`/`argv[0]` through an in-memory launcher; OS-visible checkout,
  work, projection, output, and control paths use the neutral `bnmp-final-e1d`
  prefix. Initial process IDs were 1578336/1578337; the projection provenance
  reached 136,636,980 bytes after 33 seconds. No protected service or port was
  changed.
- Neutral final-v7 completed its fresh projection gate in 117.692 seconds with
  process peak RSS 191,548 KiB. The manifest contains 141 authoritative source
  rows, 139 byte-exact projection files, 746,890 selected outer records, all
  six evaluation sessions and eight causal sessions, zero malformed candidates
  and zero source mutations. August 17 is explicitly
  `PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED`. Projection manifest
  and provenance SHA-256 are
  `5c01bff5daee03496b4643ce3ccf9c01228f41abb87ec6675ce75f317efaf2f1` /
  `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0`.
  The schedule-contract file/embedded SHA-256 are
  `e38f9d9db9e94bbeced0282fc19d59b7d723b1a2cbbad1c8cf895cb85fc3f061` /
  `2dc7e20ea92234565243464105bb071add1982066068a796ed188da5311b2bc1`.
  Incremental A then began; no terminal result is claimed before its seal.
- Direct final-v7 was interrupted by external signal 2 at 17:59:38 IST after
  exactly 16:44.56 wall time. The traceback is `KeyboardInterrupt` inside
  timestamp validation, not an analytical exception; peak RSS was 4,982,376
  KiB, swap was zero, and no A seal or schedule marker existed. Its projection
  and output roots were subsequently deleted while checkout/work/control
  remained. The partial work is rejected and not reused.
- A first persistent v8 unit failed closed in `ExecStartPre` because the deleted
  projection manifest was absent. Python never started and no v8 analytical
  root exists; its unit/log remain diagnostic evidence only.
- Persistent neutral recovery v9 started at 18:03:50 IST under user-manager
  invocation `ce9595fd18b344ab8ab2765ae509f8fa`, unit SHA-256
  `48a65a204e2d1ad491f3b0eae7eebee7f6afc7254065fc48d75efbad972f352c`,
  and initial parent/Python PIDs 1583843/1583845. A new clean detached e1d67c5
  checkout and both package companions passed before start. V9 owns fresh
  neutral output/work/projection roots, rebuilds the projection from the
  authoritative raw root, and runs all nine schedules. It is managed outside
  the terminal session lifetime with 24/28 GiB high/max memory limits, no swap,
  no network except AF_UNIX, and fail-closed preflight paths. No protected
  listener or collector was changed.
- V9's fresh projection gate sealed in 117.675 seconds with peak process RSS
  189,924 KiB. All 141 authoritative source rows rehashed unchanged, 139
  byte-exact projection files contain 746,890 selected records, and malformed
  candidates/source mutations are zero. Projection manifest/provenance and
  source-comparison SHA-256 are
  `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426`,
  `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0`,
  and `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56`.
  Contract file/embedded SHA-256 are
  `9579ec8a4dc5d3b06e3f0caf6005903a83a12804711aff3f8b01d05ce5663020` /
  `af10b6130ef38ca42c79be8aad0ebef3df4bbb9494ac974321cd315ae94583d0`.
  Incremental A is active; these preflight results do not imply analytical
  acceptance.
