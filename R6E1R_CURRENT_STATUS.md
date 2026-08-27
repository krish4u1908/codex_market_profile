# R6E1R Current Status

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **REPAIRED AND SEALED FOR HOST VERIFICATION — NOT YET VERIFIED OR DEPLOYED**

This file is the authoritative status block for the sanitized v2 branch. Older
diagnostic results remain useful only when explicitly scoped to their tested
commit; they do not override this status.

## Git authority

| Item | Value |
|---|---|
| Branch | `fix/r6e1r-final-live-shadow-v2` |
| Sanitized base | `c91df5a660195fa7b4595e0da02488c9db7cb8b1` |
| Projection/GUI hardening | `a6b0e1c` |
| Ledger/harness repair | `d92c715` |
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
| Deployment manifest SHA-256 | `d1b955715280670189dfd623f60ec8c57c870397057b7a81de597e68a9d42104` |
| Package aggregate | `83ac33a6a82bc93db49a1464d237adc9658f9318b5331321a6693622384a6bf8` |
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
