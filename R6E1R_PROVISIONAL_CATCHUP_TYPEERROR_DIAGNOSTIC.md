# R6E1R Provisional Catch-up TypeError Diagnostic

## Scope and safety

- Tested commit: `bb249cc4e53f67a24209db1477d6ddfe1ff58116`.
- This was a bounded diagnostic only. No production source, test, manifest, service, deployment, collector, or accepted full-six state was changed.
- Both provisional services remained stopped and disabled. Their backend and gateway ports had no provisional listener.
- Both failed deployment/state roots and their journals were preserved unchanged.
- Reproduction used private state roots, a temporary untracked wrapper, a read-only collector-source mount, and no HTTP backend or gateway.
- No raw record, absolute Hostinger path, server address, username, process identifier, credential, environment value, or private traceback is included here.

## Result

The first matching exception occurred in phase 3, `finalize_prior_sessions()`. Phases 1 (`ingestor.poll()`) and 2 (observed-session ordering) completed. Explicit phases 4 (`orchestrator.flush()`) and 5 (`orchestrator.refresh_staleness()`) were not reached because phase 3 internally invoked `finalize_session()`, which invoked `flush()` and failed.

Repository-relative traceback:

1. `src/banknifty_profiler/shadow/orchestrator.py:1497` — `finalize_session`
2. `src/banknifty_profiler/shadow/orchestrator.py:1468` — `flush`
3. `src/banknifty_profiler/shadow/orchestrator.py:2005` — `_compute_sessions`
4. `src/banknifty_profiler/shadow/orchestrator.py:2235` — `_inventory`
5. `src/banknifty_profiler/inventory/engine.py:39` — `oi_events`
6. `src/banknifty_profiler/raw_io/reader.py:60` — `backward_join`

The failing operation at `src/banknifty_profiler/raw_io/reader.py:60` is the subtraction used to derive `join_age_seconds`:

```text
<OI_AVAILABILITY_TIMESTAMP_SERIES> - <MATCHED_INDEX_TIMESTAMP_SERIES>
```

Sanitized exception template:

```text
Cannot subtract <TZ_NAIVE_DATETIME_SERIES> and <TZ_AWARE_DATETIME_SERIES>
```

## Operand and input evidence

For the failing session, the inventory input contained 27,406 OI observations: 13,510 CE, 13,510 PE, and 386 Futures OI observations. The eligible canonical Index subset contained zero rows.

The left operand, `availability_timestamp`, had Python/Pandas dtype `datetime64[us, Asia/Kolkata]` and was timezone-aware. When the eligible Index subset was empty, `backward_join()` assigned scalar `pd.NaT` to `matched_price_timestamp`; Pandas materialized that fallback as timezone-naive `datetime64[s]`. The subsequent subtraction therefore raised `TypeError`.

This was not caused by a timezone-naive source timestamp. The incoming timestamp columns were timezone-aware. It was caused by the runtime-created empty-match fallback losing timezone compatibility.

The first deterministically ordered affected event had sanitized identity SHA-256:

```text
56ec7cb7cba413a747d4b618da39b969271f39922ad3c19b626a09b880fc1cd8
```

Its logical source class was CE. The failing join operates on a combined OI vector containing CE, PE, and Futures OI; the required Index match class was absent for the session. The session date was `2026-08-26`.

Present field/type inventory for the first affected logical event:

| Field | Python/Pandas type | State |
|---|---|---|
| `availability_timestamp` | timezone-aware `Timestamp` | present |
| `cumulative_volume` | `float64` | present |
| `delta_oi` | `float64` | null, expected for an initial counter |
| `duplicate_record` | `bool` | present |
| `expiry_date` | `date` | present |
| `instrument_class` | `str` | present |
| `instrument_price` | `float64` | present |
| `oi_changed` | `bool` | present |
| `oi_close` | `float64` | present |
| `oi_observation_timestamp` | timezone-aware `Timestamp` | present |
| `oi_receipt_timestamp` | timezone-aware `Timestamp` | present |
| `previous_oi` | `float64` | null, expected for an initial counter |
| `session_date` | `str` | present |
| `source_file` | `str` | present privately; value withheld |
| `source_row` | `int64` | present privately; value withheld |
| `strike` | `float64` | present |
| `symbol` | `str` | present privately; value withheld |
| `valid_receipt` | `bool` | present |

No numeric field required by this operation was encoded as a string. No required source timestamp was missing or timezone-naive. The null `previous_oi` and `delta_oi` fields were expected initial-counter values and were not operands in the exception.

The collector record was valid JSON and valid under the collector's OI REST schema. Its top-level field types were numeric latency, string receipt/request/symbol/source fields, and a dictionary response. It was not a malformed-record refusal case.

## Checkpoint and mutation evidence

The copied post-restart state began at a last successful logical checkpoint with:

- 45 checkpoint entries
- 108,913,269 aggregate committed source bytes
- 118,958 aggregate committed rows
- checkpoint semantic hash `93054dec9567416afc76e9f5b85d4934b5a36bda1c022dbd458880c5ebcad9d3`

Before phase 3 failed, phase 1 durably advanced one raw-stream checkpoint to:

- 113,107,365 aggregate committed source bytes
- 124,845 aggregate committed rows
- checkpoint semantic hash `8c0471535a1ec62de2eeb0a09a7171b242fa1bdafa6085a39954b92ee05a912f`
- changed checkpoint-key identity SHA-256 `1e822e0fb0a8c689ab1c8b78f90bd52d1bfa30598ad4da3dc3e51bacaa57e41e`

Five copied-state artifacts changed before the exception: the normalized analytical observation stage, raw-file checkpoint ledger, normalized-raw-event ledger, checkpoint file, and deduplication database metadata. These were poll/staging mutations in the private copy. No inventory result or other analytical publication from the failing finalization was produced before the exception.

Source-integrity mutation count was zero. The collector source was mounted read-only.

## Reproduction matrix

| State basis | Result | Cycle | Phase | Source mutations |
|---|---|---:|---|---:|
| Private copy of preserved post-restart state | Same `TypeError` | 1 | `finalize_prior_sessions()` | 0 |
| Independent new-empty diagnostic state | Same `TypeError` | 1 | `finalize_prior_sessions()` | 0 |

The independent new-empty result rules out checkpoint restoration as the necessary cause.

## Root-cause classification

**Category D — Timestamp/type comparison defect.**

The runtime handles an empty eligible Index subset by creating a timezone-naive `matched_price_timestamp` fallback and then subtracts it from a timezone-aware OI availability series. This is a valid input-availability edge, not malformed collector data and not a restart-only defect.

A production source repair is required. The smallest repair should preserve a timezone-aware dtype compatible with the availability series in the empty-Index branch, or safely avoid age arithmetic when no causal Index match exists. A regression test must exercise inventory OI processing with valid timezone-aware OI observations and an empty eligible Index subset, asserting graceful unmatched output without an exception, future join, or timestamp backdating.

No repair was implemented in this diagnostic.

## Operational continuity

- Provisional backend and gateway remained stopped and disabled throughout.
- No provisional listener was created on the backend or gateway port.
- The accepted full-six service retained its original process identity and invocation identity, had zero restarts and zero failure markers, and its checkpoint continued advancing during the diagnostic.
- Collectors remained running and unchanged.
- Existing services and listeners on ports 8803 and 8804 remained unchanged.
