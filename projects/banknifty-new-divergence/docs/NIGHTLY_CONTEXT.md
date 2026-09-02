# Nightly 1D/2D/3D context

## Purpose and boundary

The nightly job reads completed collector sessions from
`/opt/banknifty-collector/data-prod-v4/` and publishes compact, versioned
1D/2D/3D OI-VPOC and Futures-volume profile controls. It does not delete,
rename, or write under the collector
root. It also does not change divergence thresholds, confirmation rules,
weights, or `production_weight`.

The context producer identity remains `1.0.12` in V1.0.14 because the V2
calculation, schema, bins, and quality gates are unchanged. A verified existing
`new-divergence-context-v1.0.12` database and its immutable bundles are reused;
the GUI runtime version may advance independently.

This is a completed-session context builder, not the still-unimplemented live
collector tailer. A future live process can select the newest `COMPLETE`
snapshot whose cutoff session is strictly earlier than its current session and
pin that snapshot for the full trading day.

## Why SQLite plus immutable snapshots

SQLite is the local query and indexing layer. The stored information is small
relative to the raw source because each accepted session retains only weighted
price bins, totals, evidence counts, quality results, and provenance. Raw ticks
and option-chain payloads remain in the collector tree.

Every publication is also written under:

```text
STATE_ROOT/daily_context/YYYY-MM-DD/SNAPSHOT_ID/
  context.json
  source_manifest.json
  sha256_manifest.json
```

The JSON bundle is immutable and independently hash-verifiable. SQLite can be
backed up normally or reconstructed by rerunning the source analysis; it uses
WAL mode, foreign keys, a busy timeout, and full synchronous commits.
The active checked-in JSON contract is
`schemas/new-divergence-daily-context-v2.schema.json`. V1 remains only as a
historical schema.

The first bootstrap must read and hash each of the latest three contributing
sessions, so its runtime is governed by those raw-data volumes even though its
output is small. No older session is scanned because it cannot contribute to
the 1D/2D/3D controls. Later runs compare file metadata and reuse unchanged
session revisions; normally only the new or changed completed session is
parsed.

The multi-day result is not an average of daily VPOCs. Each session contributes
its underlying weighted bins in the common causal BankNifty Index-reference
coordinate. The 2D and 3D controls are selected again from the combined bins.

For `BN_REF_FUT_VOLUME_VPOC`, V2 also publishes a 70% contiguous value area.
Expansion begins at the aggregate VPOC and compares the immediately adjacent
25-point upper and lower bins. The heavier side is included first; an exact tie
includes both sides to avoid directional bias. Expansion continues until at
least 70% of aggregate Futures-volume weight is included. `VAL` and `VAH` are
the lower and upper bounds of that contiguous interval. Signed OI families
publish only their separate VPOC; VAH/VAL are not computed from OI deltas.

## Source selection and quality rules

- Dated directories under either `raw/YYYY-MM-DD` or `oi/YYYY-MM-DD` are
  discovered; a missing counterpart is rejected rather than silently skipped.
  Dates and contract years are not hard-coded.
- The nearest valid Futures and option expiries are selected from that
  session's OI records, then cross-checked against the raw Futures stream.
- Files must be unchanged for 600 seconds by default.
- Raw JSONL must parse without malformed records.
- Index, active Futures, Futures OI, Call OI, and Put OI must exist and cover
  both session edges within five minutes.
- Index ticks, Futures ticks, Futures OI, and option OI may each miss at most
  five expected session minutes.
- Index matching remains backward-only and within five seconds.
- The immediate prior one, two, or three discovered sessions are used. A
  rejected required session is never replaced with an older accepted session.
- A family with no eligible signed evidence is published as `UNAVAILABLE`.

The directory inventory does not itself identify an exchange holiday on which
no directory exists. If that distinction becomes operationally necessary, add
a versioned exchange-session calendar as a separate input rather than embedding
dates in code.

## Install the systemd timer

First install the Python package as the normal project owner:

```bash
./install.sh
```

Install service files without enabling or starting anything:

```bash
sudo ./install_nightly_context.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

If the collector root is readable only by another account, use that non-root
account with `--user` and choose an appropriate shared group/state-root policy.
The installer checks access before installing the units.

Inspect the installed schedule:

```bash
systemctl cat banknifty-new-divergence-nightly.timer
systemctl list-timers banknifty-new-divergence-nightly.timer
```

Run the first build manually and inspect it before scheduling:

```bash
sudo systemctl start banknifty-new-divergence-nightly.service
sudo systemctl status banknifty-new-divergence-nightly.service --no-pager
sudo journalctl -u banknifty-new-divergence-nightly.service -n 100 --no-pager

.venv/bin/banknifty-new-divergence context-status \
  --state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

Enable the timer only after that check:

```bash
sudo systemctl enable --now banknifty-new-divergence-nightly.timer
```

Alternatively, install and enable in one explicit operation:

```bash
sudo ./install_nightly_context.sh --user bankadmin --enable
```

The timer runs at 00:15 `Asia/Kolkata`, adds up to 120 seconds of randomized
delay, and has `Persistent=true`, so systemd catches a missed run after reboot.
The service has no network access, sees the collector root read-only, and can
write only its context state root under the systemd filesystem policy. A
transient failure such as a source file changing during analysis is retried up
to two times at five-minute intervals.

## Manual and cron-compatible operation

Run without systemd as the account that can read the collector:

```bash
./run_nightly_context.sh
```

For a reproducible historical cutoff:

```bash
./run_nightly_context.sh --cutoff-session YYYY-MM-DD --stability-seconds 0
```

The wrapper is cron-compatible, but systemd is preferred because its timezone,
missed-run recovery, logs, permissions, and resource policy are explicit. If
cron is required, install these two lines in the service account's crontab,
using the actual absolute project path:

```cron
CRON_TZ=Asia/Kolkata
15 0 * * * /home/bankadmin/divergence/banknifty-new-divergence/run_nightly_context.sh >> /home/bankadmin/divergence/nightly-context.log 2>&1
```

Do not configure both cron and the systemd timer. The process-level lock still
prevents overlapping systemd, cron, or manual runs.

## SQLite read contract

The database is `STATE_ROOT/context.sqlite3`. Consumers must read only rows in
`context_snapshots`, which accepts `COMPLETE` status only, or use the
`latest_complete_context` view. Controls are in `scope_controls`.

Example inspection:

```bash
sqlite3 /home/bankadmin/divergence/new-divergence-context-v1.0.12/context.sqlite3 '
  SELECT cutoff_session, snapshot_id, created_at
  FROM latest_complete_context;'

sqlite3 /home/bankadmin/divergence/new-divergence-context-v1.0.12/context.sqlite3 '
  SELECT scope, family, status, control_value,
         value_area_low, value_area_high, reason
  FROM scope_controls
  WHERE snapshot_id = (SELECT snapshot_id FROM latest_complete_context)
  ORDER BY scope, family;'
```

If a source session changes, a new session revision and context snapshot are
appended. Existing revisions and bundles are not overwritten. An unchanged
rerun reuses both the cached session revisions and deterministic snapshot.
