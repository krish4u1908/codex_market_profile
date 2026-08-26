# R6E1R0 Sample Provenance and Inventory

Authoritative root: `/opt/banknifty-collector/data-prod-v4`

Window: `2026-08-19 09:15:00` through `12:05:00` Asia/Kolkata, inclusive

Fixture: `/opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205`

Manifest SHA-256: `5bf62dda9b6613e2d6b3000c084a723133c5af01c7e4cb5acff84af84fb610e2`

Eight physical JSONL files were streamed line-by-line. All 46,550 selected records retain source line, byte offset, byte length and SHA-256 identity. Independent validation re-read every identity and all source hashes; source size, mtime and content were unchanged.

| Type | Count |
|---|---:|
| Index raw | 19,823 |
| Futures raw | 26,387 |
| Futures OI REST | 170 |
| CE REST | 5,950 |
| PE REST | 5,950 |
| Option-chain Index reference | 170 |

First receipt: `2026-08-19T09:15:00.636332+05:30`

Last receipt: `2026-08-19T12:04:59.616862+05:30`

Raw SHA-256: `cbbded304a8b6df50c05683b65a372fbbbbf4a828477e09e57e1b87a4bc7c3a0`

OI SHA-256: `a6aa069abd2a477bee0e28cc18e592ca064e1eea1379cd032bbc44dd61244c98`

The JSONL fixture is external and is not part of Git.
