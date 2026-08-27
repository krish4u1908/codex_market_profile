# R6E1R V2 host validation failure

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

## Scope

- Tested commit: `3d0e8c1a364b28ca915f5969f3c3ecac5eda2f20`
- Remote branch head was exact before testing.
- The required five-commit chain was linear and exact.
- Testing used a fresh detached worktree. No source, test, manifest, or analytical semantic was repaired or changed.

## Pre-test gates

- Engine manifest: 38/38 exact.
- Engine manifest SHA-256: `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7`.
- Deployment manifest: 47/47 exact.
- Deployment manifest SHA-256: `d1b955715280670189dfd623f60ec8c57c870397057b7a81de597e68a9d42104`.
- Every allowlisted file hash was exact.
- `git diff --check`, credential scan, oversized reachable-blob scan, and initial clean-worktree gate passed.
- Largest reachable Git blob: 314,380 bytes; blobs over 10 MiB: 0.

## Complete host regression

The complete repository suite was run without deselection or weakening, with all sealed reference roots and browser libraries supplied.

- Passed: 642
- Failed: 1
- Skipped: 0
- Wall time: 121.78 seconds
- Peak RSS: 672,920 KiB
- Timing evidence SHA-256: `64b124bba41169c0722cfaaf577c7952f00c6fb3b799bdd693b1e5c72de2e7e8`

Exact failure:

```text
deploy/r6e1r/test_deployment.py::test_user_units_are_isolated_and_resource_bounded
```

The test renders the backend user service and requires it to authenticate the exact committed runtime-configuration example. The committed example has SHA-256:

```text
ecfa9e1a8afb4622f8d4f3128511817bef451f5353ff1998d72e6475c67ebab2
```

The committed backend service template does not contain that digest. It instead embeds this runtime-configuration digest:

```text
c38479baeefe25c4cc47981d5ad86cf5538b20aa0eb1ae6fab2fade1c1a58364
```

The activation-example digest is internally consistent; the mismatch is limited to the runtime-configuration example versus the backend service template. Consequently, a service rendered from this sealed package would reject its own committed runtime configuration at startup.

## Policy outcome

This is a mandatory deployment-package regression failure at the exact sealed V2 commit. Per failure policy:

- Focused V2 all-nine was not started.
- Full six-session V2 all-nine was not started.
- Deployment was not performed.
- No verification tag was created.
- No source, test, manifest, or analytical code was changed on the host.

An independently relaunched obsolete full-six process from old commit `e107280` was detected during validation. Its exact process tree was terminated safely and its partial output/work roots were preserved as obsolete diagnostic evidence. It was not used for V2 acceptance.

Ports 8803/8804 and collectors were not stopped, restarted, or modified.

## Repair guidance

Repair and reseal the deployment package in the development environment so the rendered backend unit authenticates the exact committed runtime-configuration payload. Update the corresponding sealed hashes atomically, add or retain this rendering regression, publish a new immutable head, and repeat all V2 host gates from fresh roots.
