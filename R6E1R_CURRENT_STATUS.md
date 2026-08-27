# R6E1R Current Status

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **DEPLOYMENT DIGEST REPAIRED AND RESEALED — HOST RE-VERIFICATION PENDING**

This file is the authoritative status block for the sanitized v2 branch. Older
diagnostic results remain useful only when explicitly scoped to their tested
commit; they do not override this status.

## Git authority

| Item | Value |
|---|---|
| Branch | `fix/r6e1r-final-live-shadow-v2` |
| Sanitized base | `c91df5a660195fa7b4595e0da02488c9db7cb8b1` |
| Projection/GUI hardening | `9669842054ec74b63b86576e4b5540b1a2c9dd63` |
| Ledger/harness repair | `a3c20bc2ea1a6251a84f41737d5b21413305bbd6` |
| Deployment digest/package repair | `bf182fa008a3b477c30a77b01f9a445ac2a8cc4a` |
| Diagnostic ancestry | `c990b8c` and `0da02be` are deliberately not ancestors of this branch |
| Verification tag | Not created |

## Implemented repair

- Periodic publication withholds an absence-derived
  `EXPIRED_OR_UNRESOLVED` lifecycle event until it becomes stable or the
  session is sealed.
- Participation transitions for that provisional episode and cross-layer rows
  linked to the provisional lifecycle/participation identities are withheld
  from immutable ledgers at the same boundary.
- Restart before a later Index response and restart before session seal both
  reproduce one-shot canonical artifacts and exactly-once ledgers.
- Large-chunk callback exercise now uses two exact interior refreshes per
  evaluation session, bound to actual merged-source coordinates.
- Closure accounting is opportunity-aware; no-opportunity is explicit and
  cannot hide failed callback/causal trace checks.
- A failed schedule retains only bounded ledger counts, deterministic event
  IDs, and content hashes before its dense snapshot is removed. Raw rows and
  source paths are not retained in this diagnostic.

No frozen analytical rule, threshold, synchronization tolerance, timestamp
semantic, lifecycle precedence, or participation clock was changed.

## Current evidence

| Gate | Result |
|---|---|
| Orchestrator module | 114 passed, 0 failed |
| Ingestion + orchestrator + equivalence harness | 278 passed, 3 failed because this container prohibits required `ptrace`/`strace`; 0 skipped |
| New repair selections | 7 passed, 0 failed |
| Projection reuse, gateway limit, and GUI parity selections | 27 passed, 0 failed |
| Manifest/package selections | 3 passed, 0 failed |
| Host regression on `3d0e8c1` | 642 passed, 1 failed; deployment stopped because the backend unit retained the pre-reseal runtime-configuration digest |
| Runtime-digest repair selection | 3 passed, 0 failed; rendered unit, renderer refusal, and exact package-manifest checks all pass |
| Deployment/API/security suite after repair | 116 passed, 2 failed because this container has no user-systemd bus; 0 skipped |
| Historical repaired large-chunk diagnostic | Passed on `bd01b8d`; informative only because the v2 harness has additional diagnostics/tests |
| Current v2 focused all-nine | Not run |
| Current v2 full six-session all-nine | Not run |
| Current v2 deployment | Not performed |

## Sealed identities

| Seal | Value |
|---|---|
| Engine files | 38/38 |
| Engine manifest SHA-256 | `51b527e17b60ce7453cd29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7` |
| Engine aggregate | `362474858eda75b18180ad2fce48e50e1d4acdd1b04a0db405eaae199e70b7a7` |
| Deployment files | 47/47 |
| Deployment manifest SHA-256 | `d5106846fcbfbc84e172ab00449535cf030b6f641745e6d048223c1b2fc799db` |
| Package aggregate | `1ba46ae9ac72d458ab2573ebf71d963f6dc36e483963245f97d01f21ccdd2a54` |
| Runtime configuration | `43654758453b2a39209dbe0df6f6d2587c63c2bf5cb77c99d44df07dd54f485b` |

## Remaining release gates

1. Run the complete repository suite on the host with its sealed references,
   user-systemd/bubblewrap boundary, and `ptrace`/`strace` file-open audit.
2. Run fresh focused all-nine equivalence from unused roots at the exact pushed
   v2 head.
3. Run fresh six-session all-nine equivalence at that same head and require all
   frozen counts plus zero differences, causality violations, duplicate IDs,
   prohibited opens, and source mutations.
4. Only after all gates pass, install and validate the isolated read-only
   service, verify the public endpoint, and create the annotated verification
   tag.

Protected ports and collectors were not modified by this reconstruction.
