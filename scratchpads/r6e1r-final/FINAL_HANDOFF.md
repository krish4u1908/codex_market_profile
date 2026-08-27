# R6E1R-FINAL Handoff

Final status: **IN PROGRESS — NOT VERIFIED**

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

## Current handoff

The authorized branch `fix/r6e1r-final-live-shadow` contains concurrent
published runtime repair `8038c9fcdf1760f25e9b5ddf2d468e47935f749c`,
deployment repair `d6736b0108fb40722d2370da422b42e0425c112d`, and
handoff `c91df5a660195fa7b4595e0da02488c9db7cb8b1`, plus local fail-closed
preload repair `61807358473d46c392aafd97948bbee829d01c7f`. They are being merged
without rewriting published history. Verify the eventual merge SHA after push.
Do not reuse a pre-repair analytical state or output root: the
append-only divergence and lifecycle publications now intentionally contain
only immutable event fields.

Current sealed package identities:

- Engine files: 38/38
- Engine manifest SHA-256: `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`
- Engine hash: `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`
- Deployment files: 47/47
- Deployment manifest SHA-256: `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1`
- Package hash: `d68f22217f1dfb75817ebb9b7cb6af0d21306cf1081b7d222c6ecca130978380`
- Runtime configuration hash: `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031`

Merged targeted evidence is 273/273 for the complete ingestion/orchestrator/
equivalence-harness core and 117/117 for deployment/gateway, with a 173/173
deployment/live-API/runner selection. Historical pre-merge evidence is 127/127 for
ingestion, 111/111 for orchestration, 32 equivalence-harness passes plus three
ptrace/strace-blocked cases, and 130 deployment/package/gateway/runner passes
plus two user-systemd-blocked cases. Those counts require a merged rerun. No
current focused/full-six, live-service, or deployment result is claimed yet.

The stabilized full non-browser collection passed 545 tests, skipped 20,
failed 13, and errored 16 in 79.30 seconds. The 29 failures/errors break down
as user-systemd/bubblewrap (2), ptrace/strace (3), sealed R6C0 evidence (4),
and sealed R6C2R/R6D evidence (20). The 20 skips are additional external-
evidence gates. There was no remaining code-attributable failure.

## Repairs requiring fresh merged-host evidence

- Periodic refreshes publish immutable divergence-confirmation and lifecycle-entry
  events while the current API snapshot continues to expose episode end and
  lifecycle exit annotations.
- Same deterministic ledger identity with different immutable content now fails
  closed; duplicate physical identities fail at startup.
- Normalized, refusal, checkpoint, material and analytical-refusal ledgers now
  reconcile only an exact, bounded, complete attempted suffix after an ambiguous
  append failure.
- Durable SQLite checkpoints reconstruct a missing deterministic checkpoint audit
  suffix after an abrupt restart.
- `large_chronological_chunks` now performs exactly five intermediate analytical
  refreshes and proves repeated-session, episode-end and lifecycle-exit evolution.
- Disabled 1D/2D/3D/Intraday masters hide their child controls while preserving
  choices; Basis toggle behavior and the transitions API are explicitly tested.
- A nonempty JSON checkpoint mirror cannot seed a missing or empty SQLite
  authority. Deleting/emptying the mirror cannot hide surviving append-only
  checkpoint or normalized evidence either. Every represented source must keep
  causally covering SQLite row/offset/identity authority, so total deletion,
  partial multi-source deletion, and same-source rollback fail closed. Existing
  SQLite state rewrites mirror drift instead of skipping or replaying raw bytes.
- Durable lifecycle, participation-transition, and episode-scoped cross-layer
  publication excludes a trailing dependency group while a candidate remains
  unconfirmed. Provisional GUI/state remains visible; `finalize_session()`
  publishes the complete stable canonical snapshot idempotently.
- The public gateway refuses all backend redirects and returns a sanitized 502;
  GET/HEAD regressions prove no request reaches the redirect target. Gateway
  security passes 13/13 on the current resealed package.

## Uploaded August 20 diagnostic

The read-only projection retained 68,171/68,171 selected identities and zero
malformed records or source mutations. Its pre-fix large/original comparison
had identical terminal semantic state but failed append-only identity by 12
lifecycle and 24 cross-layer rows, all from one terminal dependency group. That
failure is repair-trigger evidence, not acceptance. On Hostinger, rerun this
auxiliary sample from fresh current-seal roots and require the large and
original ledgers to match exactly (expected final counts from the clean side:
1,943 lifecycle and 8,631 cross-layer rows). It cannot substitute for the
focused August 19 or canonical six-session gates.

## Concurrent Codex diagnostic

Full-six v6 produced exact A/B baselines and both reference surfaces, then the
one-record schedule produced 898 ingestion plus 898 analytical out-of-order
refusals. It was interrupted and rejected. The causal-backlog repair passes its
semantic hourly-peer regression, 31/31 harness tests, and 116/116 broader
callback tests. V7 was externally terminated at six hours, v8 stopped with the
non-lingering user manager, and v10 was stopped when the concurrent remote
engine advance was discovered. All are rejected diagnostics. Fresh focused and
full-six runs from the eventual merged commit are mandatory; `Linger=yes` now.

## Mandatory continuation

From the exact pushed merge commit, use new versioned work/state/output roots;
do not reuse any pre-repair state. Rerun the focused August 19 all-nine gate,
the full six-session all-nine gate,
the complete repository regression, browser acceptance, manifest/package checks,
and isolated deployment checks. The six-session result must retain every frozen
count and report zero stream/batch differences, future joins, backdating,
duplicate analytical IDs, prohibited opens, unmeasured opens, checkpoint
failures, analytical refusals and source mutations.

Install on backend `127.0.0.1:18805` and external gateway `8805` only after all
gates pass. Do not modify ports 8803/8804, collectors, frozen packages, or
verified tags. Create `r6e1r-live-shadow-verified` only after deployment and all
acceptance evidence pass.
