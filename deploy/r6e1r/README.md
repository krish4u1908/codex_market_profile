# R6E1R isolated service templates

These templates keep the analytical server on `127.0.0.1:18805` and expose
only an exact allowlist of sanitized GET/HEAD routes through candidate research
port `8805`. Resolve the external port with `ss -ltnp` before installation and
replace `8805` consistently if it is occupied. Ports 8803 and 8804 are outside
this package.

The gateway refuses arbitrary paths, arbitrary query parameters, non-verified
replay dates, and all mutating HTTP methods. The six verified replay dates are
available through `/?date=YYYY-MM-DD` API selection when those session outputs
are present in the analytical state; live/latest remains the default. Journald
receives one JSON request record per gateway request and supplies rotation.

Before enabling the units, provision the unprivileged `banknifty-profiler`
service account, `/var/lib/banknifty-profiler/r6e1r`, and the non-secret
activation document at `/etc/banknifty-profiler/r6e1r-activation.json`. Do not
place credentials in that document or either unit.
