# Read-only transport

The core binds only to `127.0.0.1`. Each GUI proxies only the four `/api/` routes
below to its own fixed core port. No request starts, stops, reconfigures or
backfills an engine. Unsupported methods are rejected.

| Route | Result |
| --- | --- |
| `GET /health` or `/api/health` on a core | Instrument, session, PID, authority count, feed/poll age, waiting/error information, prior-context maintenance status |
| `GET /api/live?profile=banknifty-v200` | Latest cached native publication envelope, or 503 while waiting; wrong-instrument profile returns 400 |
| `GET /api/catalog?profile=banknifty-v1062` | `{profile, sessions:[{id, session, source, payload, sha256}]}` |
| `GET /api/replay?profile=banknifty-v200&key=recorded-YYYY-MM-DD` | Stored compressed publication snapshot; no engine or mutable database work |
| `GET /workspace-config.json` on a GUI | Its instrument, two allowed profiles, default V2 view, Live default and polling interval |
| `GET /health` on a GUI | GUI availability with `owns_engine:false`; remains reachable if its core is offline |

Replace `banknifty` with `nifty` on the NIFTY endpoint. `v1062` and `v200` are
the only supported view suffixes. Replay keys come from the catalog; they are
validated and cannot escape the replay directory.

Live replies support gzip and SHA-256 ETags. `If-None-Match` returns 304 when
unchanged. Polling is sequential in the browser data worker: it does not overlap
requests, retries disconnects, and cancels old generations on mode/profile
changes. The GUI proxy has a five-second upstream timeout. A failed request
retains the last frame with a disconnected status; a changed session clears it.

Each core publishes two envelopes over the **same** inputs. v1 uses
`NEW_DIVERGENCE_BROWSER_PAYLOAD_V1`; V2 keeps `version:2.0.0`, native `decisions`
and adds `chart_inputs`. `live.server_time` is transport availability, not an
exchange receipt or a call publication time. Original call and context clocks
remain intact. Health derives elapsed age at request time, even if a producer
has stalled. All transport responses use `Cache-Control:no-store`.

No order placement, broker credentials, alert transmission or authentication
changes are part of this runtime. Existing collector/auth services keep their
own configuration.
