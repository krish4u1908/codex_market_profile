# R6E1R0 Field-Preservation Matrix

| Required field | Collector source | Typed field | Consumer |
|---|---|---|---|
| Receipt timestamp | `received_at` | `receipt_timestamp`, `effective_timestamp` | ordering/availability |
| Event timestamp | `event_time` or `request_time` | `event_timestamp`, `exchange_timestamp` | audit; never backdates receipt |
| Symbol | message, response key or option item | source/canonical symbol | classification/routing |
| Price | `ltp` | `price` | analytical stack |
| Cumulative volume | `vol_traded_today`, `volume`, `v` | `cumulative_volume` | causal increments |
| OI and change | `oi`, `prev_oi`, `pdoi`, `oich` | OI fields | inventory/participation/audit |
| Strike, expiry, type | contract fields | matching typed fields | CE/PE and expiry routing |
| Source identity | file, byte, row, record | matching source fields | provenance/deterministic IDs |
| Quality/order/reset | validation and counters | status fields and quality ledger | refusal/degradation/views |

`NSE:NIFTYBANK-INDEX` is exact-match only. Futures, CE and PE require exact canonical grammar and consistent metadata.
