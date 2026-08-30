# Release Test Report

Release: `banknifty-market-profile-learning-lab-v0.1.3`

Date: 2026-08-30

## Result

**PASS**

## Automated checks

- Python source and tests compiled successfully with `compileall`.
- Eight `unittest` cases passed.
- The synthetic workflow verified causal-case construction, separate label
  binding, deterministic seed candidates, train and validation scoring,
  sealed-holdout refusal, one-time holdout opening, candidate freeze, report
  creation, and learning-run integrity verification.
- Every deterministic seed candidate generated a valid candidate
  specification.
- A v1.0.19-compatible legacy session with no declared `futures_market`
  artifact built successfully, retained no fabricated BN-reference volume,
  and passed exact equivalence for its available inventory families.
- An inconsistent payload that still published volume inventory without its
  raw Futures market artifact was rejected instead of being silently accepted.
- Both response schemas passed a local strict-object/type preflight; a fixture
  reproducing the missing-type API rejection was rejected locally.
- Candidate generation resumed in `codex-01-attempt-02` while preserving a
  failed `codex-01` workspace, checkpointed all successful roles, and reused
  the completed inventory without making duplicate Codex calls.
- All three generated candidate skill directories passed the Codex
  `skill-creator` quick validator.
- All JSON and TOML release resources parsed successfully.
- Ordered support testing proved reaction-before-breach and
  breach-before-reaction remain distinct.
- Frozen candidate import preserved the exact candidate and skill hashes in a
  new sealed run.
- Synthetic validation produced horizon-specific selection, session
  diagnostics, leave-one-session-out results, deterministic session bootstrap
  intervals, calibration bins, and ordered level-reaction metrics.
- Holdout opening bound the validation selection and restricted evaluation to
  eligible candidate/horizon pairs plus their baselines.
- Installation was tested from a clean temporary copy; the installed command
  reported version `0.1.3`.

## Deliberately deferred to the target server

- Verification against the nineteen real v1.0.19 session payloads and run
  summaries. The `build` command performs this and fails closed on any source
  hash or reconstructed-inventory mismatch.
- The live Codex permission-profile denial proof. The `profile-check` command
  performs an ephemeral read-denial test with the target server's Codex CLI
  and refuses candidate generation unless it passes.
- Import of the two real frozen V0.1.2 candidates and scoring of the real train
  and validation dates.
- Any holdout evaluation. V0.1.3 refuses it unless a predeclared specialist
  passes every validation gate.

No service, port, firewall rule, collector, replay process, live process, or
existing Codex worker was exercised or modified by these release tests.
