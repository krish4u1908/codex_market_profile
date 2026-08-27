# R6E1R Six-Session Equivalence Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **CURRENT V2 SIX-SESSION EQUIVALENCE NOT RUN**

## Required sessions

- 2026-08-11
- 2026-08-12
- 2026-08-13
- 2026-08-18
- 2026-08-19
- 2026-08-20

August 17 remains a canonical rejection. Derived analytical tables are
prohibited as A/B input.

## Required schedules

| Schedule | V2 result |
|---|---|
| Original source chunks | Not run |
| One complete record per increment | Not run |
| Deterministic variable chunks | Not run |
| Boundaries inside JSONL lines | Not run |
| Empty/repeated polls | Not run |
| Multiple checkpoint restarts | Not run |
| Restart at analytical transition boundaries | Not run |
| Hourly rotation | Not run |
| Large chronological chunks | Not run |

A repaired large-only run passed on historical repair commit `bd01b8d` with
identical semantic and ledger hashes and zero causality/exercise failures. It is
diagnostic evidence, not current v2 acceptance, because v2 adds bounded failure
retention and additional regressions.

## Frozen acceptance counts

| Artifact | Required |
|---|---:|
| Inventory | 255 |
| Divergence episodes | 65 |
| GREEN / RED | 41 / 24 |
| Dependent retriggers | 14 |
| Lifecycle transitions | 14,201 |
| Dense resolution | 164,668 |
| Dense participation | 69,225 |
| Participation transitions | 32,068 |
| Participation summaries | 65 |
| Compatibility snapshots | 65 |
| Cross-layer transitions | 60,659 |

The current v2 run must additionally prove zero stream/batch differences,
reference mismatches, future joins, synchronization violations, timestamp
backdating, duplicate analytical IDs, analytical refusals, prohibited opens,
checkpoint failures, and source mutations.

No deployment or verification tag is authorized until the complete matrix
passes at the exact pushed v2 head.
