# R6E1R Performance Report

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **FOCUSED V12 MEASURED; FINAL SIX-SESSION MEASUREMENTS PENDING**

## Measured repair history

| Run | Outcome | Elapsed | Peak RSS | Notes |
|---|---|---:|---:|---|
| Inherited focused incremental baseline | Interrupted after defect confirmation | 8m56.43s | 343,064 KiB | Full dirty session rebuilt per poll; output grew to 2,862,368 KiB before interruption |
| Focused A/B v2 | Repair required | 3m11.34s | 1,063,876 KiB | Core analytics matched; legacy batch omitted required Intraday fallback rows |
| Focused A/B v4 | Rehearsal only | 3m49.54s | 1,113,236 KiB | Running process contained a pre-edit GUI comparator |
| Focused A/B v8 | Diagnostic only | 3m58.44s | Parent 1,121,076 KiB; child 696,360 KiB | Later audit rejected the comparator as final evidence |
| Authoritative sample-source rehash | Passed | 1.08s | 3,712 KiB | Eight source identities remained unchanged |
| Source-hour-preserving sample build/integrity check | Passed | 9.91s | 434,972 KiB | Eight hourly collector paths; manifest `31077f42...`; 46,550/46,550 identities |
| Frozen reference-manifest verification | Passed | 0.96s | 18,668 KiB | R6C2R 74/74 and R6D 40/40 package files |
| Correctly provisioned prior complete regression | Passed | 62.29s | 663,256 KiB | 289 passed, zero failed, zero skipped at that checkpoint |
| Accepted focused all-nine v12 | Passed | 22m09.73s | Parent 1,586,204 KiB; child 803,968 KiB | 21/21 components, 8/8 ledgers, 9/9 schedules, all invariant/open/source gates zero |

The baseline measurement directly identified the quadratic rebuild. The repaired design stages and acknowledges incrementally, refreshes analytics at a bounded interval or explicit boundary, and prevents API reads from rebuilding a session.

## Final measurements

| Workload | Records/bytes | Elapsed | Peak parent RSS | Peak child RSS | Output bytes | Status |
|---|---:|---:|---:|---:|---:|---|
| Focused August 19 sample, complete all-nine v12 | 46,550 records / 33,326,536 bytes | 22m09.73s | 1,586,204 KiB | 803,968 KiB | 465,846,934 bytes accepted output; 33,365,301 bytes retained work root | PASS |
| Six-session original chunks | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Six-session one-record schedule | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |
| Complete required schedule set | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` | `PENDING_FINAL_EVIDENCE` |

Record the exact command, seal hashes, `/usr/bin/time -v` output, child-resource measurement, and filesystem usage for each accepted run. A killed or comparator-invalid run remains diagnostic only.

Accepted focused command:

```bash
PYTHONPATH=src /usr/bin/time -v -o /tmp/r6e1r_focused_nine_final_v12.time.txt \
  /opt/banknifty/research/.venv/bin/python scripts/run_r6e1r_equivalence.py \
  --data-root /opt/banknifty/research/sample_fixtures/r6e1r0_aug19_0915_1205/collector \
  --output-root /dev/shm/r6e1r_focused_nine_final_v12 \
  --work-root /dev/shm/r6e1r_focused_nine_final_v12_work --keep-work \
  --config configs/r6e_shadow.json \
  --stack-config /tmp/r6e1r_focused_stack.json \
  --inventory-config /tmp/r6e1r_focused_inventory.json \
  --sessions 2026-08-19 --skip-references --no-expected-count-gate
```

Focused summary SHA-256: `19b6c15f426b925fa6ec018d65477f4364242d65cfaaa5425423098d3861de15`; state manifest SHA-256: `d38ca5e40e60d87d117894df84386fb19b5e1c08347392838a86eef832d92fb3`; state tree SHA-256: `ece5d41515f182761e397b2bf06e1545daab6a91b6d313af18505fd01932a37f`.

## Scaling design

- Raw files are read in bounded per-file chunks.
- Discovery and source identities are cached and invalidated by directory/file identity changes.
- Fixed context is source-hash cached and excludes the evaluation session.
- Finalized raw observation buckets are compacted after durable output publication.
- Six protected replay outputs are retained independently of a rolling live-session window.
- The configured live output ceiling is 32 non-protected sessions; dense output cost still varies by session.
- Browser responses are tail-limited and never load all raw or dense analytical history.

These properties support extension toward 20-30 sessions without loading all raw history into browser memory. The final report must still record an evidence-backed conclusion:

`20-30 session extension assessment: PENDING_FINAL_EVIDENCE`

The current committed but uninstalled backend unit uses `MemoryHigh=8G` and `MemoryMax=10G`. Those limits and the final six-session peak must be verified together before installation; no passing run may be truncated to fit the service budget.
