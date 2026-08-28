# R6E1R Source-Hash Comparison Summary

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED SOURCE INTEGRITY PASS; FULL-SIX PROJECTION INTEGRITY PASS;
TERMINAL FULL-SIX POST-RUN COMPARISON PENDING**

Current analytical commit:
`e1d67c534bea5c61b0e3d379db7f599de7e1c445`.

This report records authorized roots and aggregate identities without exposing
raw filenames, receipt-level records, credentials, or source payloads.
Raw/sample JSONL remains outside Git.

## Persistent v9 full-six projection authority

Persistent v9 rebuilt its byte-exact projection from the authoritative
read-only root `/opt/banknifty-collector/data-prod-v4`. Evaluation sessions are
August 11, 12, 13, 18, 19, and 20. Causal predecessor chains were discovered
from repository logic and raw bytes. August 17 remains present only for
canonical rejection and was never forced accepted.

| Projection-time integrity measure | Verified value | Result |
|---|---:|---|
| Authoritative source rows rehashed | 141/141 | PASS |
| Byte-exact projected collector files | 139 | PASS |
| Selected complete outer records | 746,890 | PASS |
| Evaluation sessions | 6 | PASS |
| Dynamic causal sessions | 8 | PASS |
| Malformed selected records | 0 | PASS |
| Source mutations during projection | 0 | PASS |
| August 17 policy | `PRESENT_FOR_CANONICAL_REJECTION_NEVER_FORCED_ACCEPTED` | PASS |

The projection sealed in 117.675 seconds at 189,924 KiB peak process RSS.
Its immutable identities are:

| Evidence | SHA-256 |
|---|---|
| Raw projection manifest | `4e56160c3e48bc3c1f2d9a50982973fa9cb6701bf076e3c4cdef4df9d7bb4426` |
| Projection provenance | `ea2430747045621a1a835ce84d9888b5179bdc5c2e14f7a68b73eb78a99507e0` |
| Projection-time source comparison | `3726fbfba76ff4b3cdab50cba4288eca2a34506140f167a6adaba5583d0c5c56` |
| All-nine schedule contract file | `9579ec8a4dc5d3b06e3f0caf6005903a83a12804711aff3f8b01d05ce5663020` |
| Embedded schedule contract | `af10b6130ef38ca42c79be8aad0ebef3df4bbb9494ac974321cd315ae94583d0` |

Canonical incremental A and independently clean chronological B then sealed
over these projected bytes. A's 26-file state manifest/tree SHA-256 values are
`5e205bdbe5d5706325116389b5caf2ba7067b408f58a016ef7ec734111462173`
and
`f404a5f0bf2d0484318685339c08a978c3bbc9ce7a9f824f2055f38565568cb6`.
Those are immutable state identities, not a substitute for the required final
post-run source rehash or preload validation.

## Terminal full-six source gate still pending

The v9 source-comparison hash above is a projection-time before/after result.
The mandatory final comparison must independently rehash authoritative and
projected sources after A, B, and every alternate schedule finish.

| Required terminal measure | Current standing |
|---|---|
| Post-run authoritative identities | PENDING terminal v9 summary |
| Post-run projection identities | PENDING terminal v9 summary |
| Combined authoritative + projection comparison rows | PENDING terminal v9 summary |
| Post-run source mutations | PENDING terminal v9 summary |
| Full-six final source-comparison SHA-256 | PENDING terminal v9 publication |

Accordingly no post-repair claim is yet made for a final 280/280 combined
matrix or its digest. The pre-repair combined result must not be carried
forward into this table.

## Focused August 19 fixture

The focused fixture at
`/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205` remains
outside Git. Repository logic selected `NSE:BANKNIFTY26AUGFUT`; the contract
was not hard-coded.

| Item | Current verified value |
|---|---|
| Selected record identities | 46,550/46,550 |
| Raw / OI outer records | 46,210 / 340 |
| Projected hourly paths / authoritative files | 8 / 8 |
| Before/after source identities | 8/8 unchanged |
| Projection manifest SHA-256 | `31077f42ae1bf639f746e5980aba028b1369b8d44ba9a15973b2a517cc8a8382` |
| Post-repair all-nine source checks | 8/8 sources plus 1/1 fixture manifest |
| Source mutations | 0 |

The current focused equivalence summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
Its measured 2,508-row audit represents 1,190,240 runtime opens and has zero
prohibited or unmeasured opens.

## Frozen comparison packages

The comparison packages are post-seal comparators, never A/B analytical input.

| Package | Files | Manifest result | Use |
|---|---:|---|---|
| R6C2R comparison package | 74/74 | PASS | Post-A/B-seal comparator only |
| R6D GUI comparison package | 40/40 | PASS | Post-A/B-seal comparator only |

Fresh v9 row-level comparison passed 30/30 R6C2R rows and 180/180 R6D GUI
rows with zero unexplained remainder. Reference-package verification SHA-256:
`ed81708afac9cbb5c30915a56d2f46cf05611a4a12565a37a7a6c3d5d1366c67`.
R6C2R/R6D comparison matrix SHA-256 values are
`0e985193a48ede2baf5ad07f5601af90f5471d61f17c8f9da8a694a009de98f8`
and
`dc0c5814dbabaafd5d914627b4435038729f4a187a41beb98f385a19b1e6c467`.

## Current engine and deployment allowlists

| Item | Current sealed value |
|---|---|
| Engine source files | PASS — 38/38 |
| Engine manifest SHA-256 | `866bfd55e434ddacef29fdbb951c83dfb2190cd0f0fc97058671bd99636bd7` |
| Engine aggregate | `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947` |
| Runtime configuration hash | `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41` |
| Raw runtime-template SHA-256 | `cbcf9f43befa4b18b4798240c18d841f1629af7a015c538c8ff254e01b6957ad` |
| Backend template SHA-256 | `153a2b493b864f9442fda8d94d0c6c2cececfde87bc9cdbfcb78d99c9aa9e7ac` |
| Deployment package files | PASS — 47/47 |
| Deployment JSON manifest SHA-256 | `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391` |
| Deployment aggregate | `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949` |
| Engine/deployment mismatches | 0 / 0 |
| Complete current regression | 660/660 PASS; zero failures/skips |

These identities supersede all `81b0836` engine/configuration/deployment
allowlists. The package was resealed because the sparse empty-Index repair
changed an authenticated engine byte and its configuration pin; the frozen
analytical contract was not changed.

## Preloaded-state binding pending

The fresh v9 incremental-A state is sealed, contains 26 files and
4,141,835,394 bytes, and has the state manifest/tree identities recorded above.
It has not yet been promoted to deployment state. The real copied-state preload
validator must wait for terminal v9 acceptance and then verify SQLite integrity,
six finalized sessions, exact frozen/live recounts, clean session state, empty
callback outboxes, engine/configuration/projection bindings, and source
evidence. No current preload-validator digest or success claim is made here.

## Historical exclusions

- The prior post-run authoritative/combined matrices and 280/280 result belong
  to the pre-repair `81b0836` engine. They remain historical only.
- The previous preload state/tree and validator result also belong to that
  pre-repair engine and are not current deployment authority.
- Full-six attempts v2-v8 were externally interrupted, deleted, or failed
  closed before terminal publication. Their partial source views are not
  accepted post-run evidence.
- An auxiliary August 20 projection remains an operational parser/provenance
  diagnostic only. It is `NOT_REQUIRED / NOT_PROMOTED` and is not prospective
  or full-six evidence.

No rejected analytical output or superseded manifest contributes to the
current source-integrity tables above.
