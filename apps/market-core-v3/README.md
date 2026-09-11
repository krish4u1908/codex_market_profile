# Shared market cores · V3 runtime

One continuously running core for BANKNIFTY and one for NIFTY. Each core supplies
both the v1.0.62 reference view and native V2.0.0 context view. The two separate
V3 GUIs serve the same responsive frontend with instrument-specific configuration.
No broker login or calculation authority runs inside a GUI.

| Instrument | Core service | Private API | GUI service | GUI port |
| --- | --- | --- | --- | --- |
| BANKNIFTY | `banknifty-core.service` | `127.0.0.1:8922` | `banknifty-gui.service` | 8920 |
| NIFTY | `nifty-core.service` | `127.0.0.1:8923` | `nifty-gui.service` | 8921 |

Both GUI versions are available at each instrument's GUI port. Live and Replay
are views of the same instrument core. Desktop/mobile clients share its state.

## Runtime boundaries

- One `LiveCollectorTail` and one `LiveAuthority` per instrument/session, recovered
  from the existing V2 journal. File ingestion uses the existing collectors.
- The unmodified native V2 context consumes that authority's snapshots. Its
  standalone collector/polling loop is never started. v1.0.62 calls come from
  the same authority's retained reference publications.
- A producer thread publishes cached JSON/gzip bytes. HTTP handlers serve those
  bytes and saved replay files; they never invoke calculations or query the
  mutable context database. Threaded GUI proxies keep requests independent.
- Separate browser data and summary workers keep a summary calculation apart
  from live/replay processing. Switching versions or modes cancels obsolete work.
- Nightly prior-context maintenance runs in an additional thread **inside each
  of the two core processes**, during 00:15–08:45 IST. It replaces the retired
  nightly service and uses a separate prior-context database. It is not a third
  live authority. It can consume CPU while building a large initial history.
- Exclusive process locks prevent a second configured instance from opening an
  instrument's state. GUIs have no systemd dependency that restarts a core when
  a GUI stops or restarts.

The frozen source files are verified against `VENDOR_MANIFEST.json` at startup.
The runtime wraps deployment, recovery and presentation; it does not change
thresholds, synchronization, inventory coordinates, lifecycle or call rules.
See [SOURCE_LINEAGE.md](SOURCE_LINEAGE.md).

## Data and clocks

The first poll after restart reconstructs price/OI history from the retained
journal and continues from saved collector offsets. Old direction publications
and V2 SQLite decisions remain unchanged. Missed live calls are not generated
retroactively. Native V2 still waits for the matching current-minute reference
call under its existing publication policy.

Price, basis, OI, cash/VIX and publication times remain separate. New-day startup
clears the previous live frame while waiting for current-session metadata. Feed
age, collector/recovery errors and V2 context errors are exposed in health.
Outside market hours, an available session remains visible and is labelled as
outside market hours. Missing current-day metadata produces a waiting status.

Both views receive the shared authority's full chart inputs. Raw option receipts
are expanded for display once per core poll; they do not replace the frozen V2
decision inputs. The frontend retains signed OI-VPOCs, price/basis/VIX ranges,
compact positive/negative cumulative OI plus total OI, futures deltas, and strict
`ratio > 4` V2 volume-climax labels. Total OI means outstanding OI.

Replay uses retained publications saved as compressed files. Migration imports
existing prepared v1/V2 sessions and exports original V2 SQLite publications as
separate catalog entries. Historical imports, migrated recordings and new live
recordings on the same date remain distinct. Partial old exports cannot supply
missing individual strike receipts or unrecorded extremes.

Prior context is selected using the frozen earlier-session cutoff. Its first
availability to the new live runtime is recorded and retained; replay does not
show it before that time. Existing prior context is copied for BANKNIFTY when
present. NIFTY builds its own from its collector history overnight.

## Build and verify

Python 3.11+ (tested on 3.12), NumPy 2.3.5, pandas 2.2.3. Node 22.13+ is needed
to build the frontend; the supplied deployment ZIP already contains that build.

```sh
cd apps/market-core-v3
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
cd ../market-workspace-v3
npm ci
npm test
npm run build
cd ../market-core-v3
python3 scripts/build_bundle.py --output /tmp/market-workspace-v3.zip
```

The bundle contains source, the compiled GUI, exact service/config templates,
an offline migration installer, rollback instructions and a checksum manifest.
It excludes collector data, recorded sessions, credentials, environments and
databases. The repository contains source and small synthetic test contracts.

## Deployment and verification limits

Follow [DEPLOYMENT.md](DEPLOYMENT.md). This is a first-install migration for the
captured `srv1913330` layout. It deliberately refuses to overwrite existing new
state or units. The installer does not remove any old release or dataset.

Local validation covers both instruments' ingestion, recovery, native V2
equivalence, partial receipts, rollover, instrument separation, HTTP/replay
isolation, SQLite migration, installation guards and rollback. Frontend tests
cover four profiles, source clocks, reconnects, cancellation, cumulative OI,
VPOC persistence, independent summaries and strict volume-climax thresholds.
The browser check could not be completed in this environment. Live VPS feed
permissions, performance on a full active session and actual market-hour
publication continuity still require post-install verification.

See [API.md](API.md) for read-only routes and caching.

## Cash/VIX indicator data

Core 3.0.1 adds `CASH_VIX_INDICATOR_INPUTS_V1` inside each existing core. It accepts late data as new observations, preserves native call inputs, and exposes full-session VIX with independent cash/VIX quality. See [DATA_UPDATE.md](DATA_UPDATE.md) for the combined update and a read-only historical audit.
