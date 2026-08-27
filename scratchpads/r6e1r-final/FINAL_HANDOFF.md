# R6E1R-FINAL Handoff

Final status: **IN PROGRESS — NOT VERIFIED**

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

## Current handoff

The post-review repair is prepared on `fix/r6e1r-final-live-shadow`.
The public continuation is reconstructed linearly from remote head
`f0d6db65bf41357965f76e067569255919cc8031` so the additional local-only
unsanitized commits and evidence are not reachable from the public branch. It
does not rewrite or erase older already-public history. Public runtime repair
commit `8038c9fcdf1760f25e9b5ddf2d468e47935f749c` contains the callback,
ledger, GUI, harness, and regression repairs. Public deployment commit
`d6736b0108fb40722d2370da422b42e0425c112d` contains the portable deployment
and exact sealed-package bytes; the following public handoff commit changes
evidence text only. Verify the final remote head after publication. Do not reuse
a pre-repair analytical state or output root: the
append-only divergence and lifecycle publications now intentionally contain
only immutable event fields.

Current sealed package identities:

- Engine files: 38/38
- Engine manifest SHA-256: `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3`
- Engine hash: `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d`
- Deployment files: 47/47
- Deployment manifest SHA-256: `c75d269da49f141352aeedffd0e3b7fc09d9045ab814bdf917214e44ac905a7b`
- Package hash: `563e2d848933c41eea1db20008bf92e29ee6162baaeb767361e5c605aec18c4c`
- Runtime configuration hash: `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031`

Local current-source evidence before the Hostinger handoff is 127/127 for
ingestion, 111/111 for orchestration, 32 equivalence-harness passes plus three
ptrace/strace-blocked cases, and 130 deployment/package/gateway/runner passes
plus two user-systemd-blocked cases. No browser, successful host file-open
audit, full-six, live-service, or deployment result is claimed from this
workspace.

The stabilized full non-browser collection passed 545 tests, skipped 20,
failed 13, and errored 16 in 79.30 seconds. The 29 failures/errors break down
as user-systemd/bubblewrap (2), ptrace/strace (3), sealed R6C0 evidence (4),
and sealed R6C2R/R6D evidence (20). The 20 skips are additional external-
evidence gates. There was no remaining code-attributable failure.

## Repairs requiring fresh Hostinger evidence

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
callback tests; fresh full-six v7 on the exact published code/package commit is
still mandatory.

## Mandatory continuation

On Hostinger, fetch and fast-forward this branch only after confirming a clean
worktree and the exact remote head recorded by the final push. Use new versioned
work/state/output roots; do not reuse any pre-repair state.
Rerun the focused August 19 all-nine gate, the full six-session all-nine gate,
the complete repository regression, browser acceptance, manifest/package checks,
and isolated deployment checks. The six-session result must retain every frozen
count and report zero stream/batch differences, future joins, backdating,
duplicate analytical IDs, prohibited opens, unmeasured opens, checkpoint
failures, analytical refusals and source mutations.

Install on backend `127.0.0.1:18805` and external gateway `8805` only after all
gates pass. Do not modify ports 8803/8804, collectors, frozen packages, or
verified tags. Create `r6e1r-live-shadow-verified` only after deployment and all
acceptance evidence pass.
