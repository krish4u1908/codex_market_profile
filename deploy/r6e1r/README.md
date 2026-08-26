# R6E1R isolated user-service deployment

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

This directory is a prepared deployment package. It does not authorize an
install before callback equivalence, regression, package-manifest, and source
hash gates pass. The commands below are intentionally not run as part of
deployment preparation.

## Host layout and isolation

- Repository (read only at runtime):
  `/opt/banknifty/repositories/banknifty-market-profiler`
- Collector root (read only): `/opt/banknifty-collector/data-prod-v4`
- Writable deployment root:
  `/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow`
- Analytical API: `127.0.0.1:18805` only
- Sanitized gateway: `0.0.0.0:8805`
- Candidate external URL: `http://200.234.39.232:8805/`
- Protected existing ports: `8803` and `8804`; no command in this runbook
  addresses either service or port.

The units are user-manager units. They deliberately contain no `User=` or
`Group=` directive and install into `default.target`, not
`multi-user.target`. `r6e1r-shadow.service` has the only collector access and
binds to localhost. `r6e1r-readonly-gateway.service` can reach the backend but
serves only the exact GET/HEAD route allowlist in `read_only_gateway.py`.
The gateway mount namespace masks the collector root, analytical state,
runtime configuration, and user GnuPG runtime directory even though both
services run under the same unprivileged UID. Both units explicitly discard
inherited SSH-agent and D-Bus session addresses and use private kernel
keyrings.
The gateway intentionally leaves `ProtectKernelTunables`, `ProtectKernelLogs`,
and `ProtectHostname` to the backend unit: on this host those systemd-created
namespaces prevent rootless bubblewrap from mounting its private procfs. The
gateway instead uses bubblewrap's verified private mount, PID, user, IPC, UTS,
and cgroup namespaces; the deployment test exercises both its main command and
post-start probe through the compatible user-systemd boundary.
POST, PUT, PATCH, and DELETE always return 405; other paths, query keys, and
unverified replay dates are refused. There are no trade, order, write, or
alert routes.

## Pre-install checks

Run these only after all analytical gates pass:

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
git diff --check
systemd-analyze --user verify deploy/r6e1r/r6e1r-shadow.service deploy/r6e1r/r6e1r-readonly-gateway.service
env PYTHONPATH=src /opt/banknifty/research/.venv/bin/python -m pytest -q deploy/r6e1r/test_deployment.py tests/unit/test_r6e1r_live_gui_api.py
ss -ltnp
loginctl show-user codexuser -p Linger -p State -p RuntimePath
```

Immediately before installation, confirm `127.0.0.1:18805` and external
candidate `8805` are unused. If `8805` is no longer free, select the first free
port from 8806 through 8810 and change both `--port` and the gateway
`ExecStartPost --base-url` in the copied gateway unit. Never select 8803 or
8804. Do not change the backend bind or port.

## Provision non-secret files

The templates contain no credentials. The activation object remains internal
runtime configuration and must remain non-secret. `activation_day` is the first
collector session the live service may discover; the prepared value is
2026-08-26. Historical sessions are made available by the verified-state
preload below, not by moving the activation boundary backward.

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
DEPLOY_ROOT=/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow
install -d -m 0700 "$DEPLOY_ROOT" "$DEPLOY_ROOT/state" "$DEPLOY_ROOT/config"
install -m 0600 deploy/r6e1r/r6e1r-runtime-config.json.example "$DEPLOY_ROOT/config/r6e1r-runtime-config.json"
install -m 0600 deploy/r6e1r/r6e1r-activation.json.example "$DEPLOY_ROOT/config/r6e1r-activation.json"
/opt/banknifty/research/.venv/bin/python -m json.tool "$DEPLOY_ROOT/config/r6e1r-runtime-config.json"
/opt/banknifty/research/.venv/bin/python -m json.tool "$DEPLOY_ROOT/config/r6e1r-activation.json"
```

Do not add secrets, threshold overrides, fixed contract selections, or
prospective claims to either file. The committed runtime template preserves
the frozen timezone, 2,000 ms causal join, canonical Index symbol, and
repository-owned contract discovery.

Startup verifies every allowlisted analytical, API, GUI, gateway, and probe
source against `manifests/r6e1r_engine_source_manifest.json` and the independent
SHA-256 recorded in the runtime configuration. A hash mismatch prevents the
backend from starting; merely hashing the current checkout cannot assert a
successful verification.

## Preload the six verified replay sessions

Preload only a clean `runs/incremental_a/state` produced by the actual R6E1R
production checkpoint/callback path after its comparisons report zero
differences. Never preload independent clean batch-B output, a derived R2–R6
table, or raw JSONL. The source run must contain 2026-08-11, 2026-08-12,
2026-08-13, 2026-08-18, 2026-08-19, and 2026-08-20 and must retain the August
17 rejection.

The following copy is safe only while the new target state directory is empty
and both services are stopped:

```bash
DEPLOY_ROOT=/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow
VERIFIED_OUTPUT=/absolute/path/to/the/passing/r6e1r-equivalence-output
VERIFIED_STATE="$VERIFIED_OUTPUT/runs/incremental_a/state"
STATE_MANIFEST="$VERIFIED_OUTPUT/incremental_a-state.sha256"
test -f "$VERIFIED_STATE/live_analytical_orchestrator.json"
test -f "$VERIFIED_STATE/checkpoints.json"
test -f "$VERIFIED_STATE/dedup.sqlite3"
test -z "$(find "$VERIFIED_STATE" -type l -print -quit)"
test -z "$(find "$DEPLOY_ROOT/state" -mindepth 1 -print -quit)"
(cd "$VERIFIED_STATE" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > "$STATE_MANIFEST"
cp -a -- "$VERIFIED_STATE/." "$DEPLOY_ROOT/state/"
chmod -R go-rwx "$DEPLOY_ROOT/state"
(cd "$DEPLOY_ROOT/state" && sha256sum -c "$STATE_MANIFEST")
```

Retain the generated state manifest with the equivalence evidence. This copy
does not alter the authoritative raw root or repository. On startup, existing
checkpoint identities and append-only analytical IDs remain durable; only
new files at or after `activation_day` are polled.

The runtime configuration retains a rolling window of at most 32 non-protected
live analytical outputs in addition to the six independently protected
verified replay outputs. Finalized normalized-observation buckets are removed
from process memory and persisted JSON after their output is durably sealed;
the append-only stage and deterministic identities remain for restart safety.
Retained outputs still include dense analytical state, so RSS grows with
session density until the oldest non-protected output is evicted; the ceiling
is not a promise that every session has equal memory cost. Browser responses
remain independently tail-capped and never materialize all dense history.

## Install and operate the user units

The following is the installation step to run only after verification and
state preload:

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
install -d -m 0700 /home/codexuser/.config/systemd/user
install -m 0644 deploy/r6e1r/r6e1r-shadow.service /home/codexuser/.config/systemd/user/r6e1r-shadow.service
install -m 0644 deploy/r6e1r/r6e1r-readonly-gateway.service /home/codexuser/.config/systemd/user/r6e1r-readonly-gateway.service
systemctl --user daemon-reload
systemctl --user enable --now r6e1r-shadow.service r6e1r-readonly-gateway.service
```

Routine operations:

```bash
systemctl --user start r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user stop r6e1r-readonly-gateway.service r6e1r-shadow.service
systemctl --user restart r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user status r6e1r-shadow.service r6e1r-readonly-gateway.service --no-pager
systemctl --user is-enabled r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user is-active r6e1r-shadow.service r6e1r-readonly-gateway.service
```

Both units use `Restart=on-failure`, bounded restart bursts, SIGTERM shutdown,
and systemd memory, swap, CPU, task, and file-descriptor limits. The 6 GiB
backend ceiling is a safety boundary, not permission to truncate analytics;
measured six-session peak RSS must remain below it before installation.

## Health, readiness, replay, and external checks

The helper treats HTTP 503 readiness as benign only when all reasons are the
explicit stale/missing-market after-hours allowlist. Every probe, including a
benign 503, still requires checkpoint integrity, zero future joins, and a
verified runtime source manifest. Any other 503 is a failed operational probe.
`--require-ready` is reserved for an in-hours freshness acceptance check.

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://127.0.0.1:18805
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://127.0.0.1:8805
for date in 2026-08-11 2026-08-12 2026-08-13 2026-08-18 2026-08-19 2026-08-20; do
  curl -fsS "http://127.0.0.1:8805/api/session?date=$date" | jq -e --arg date "$date" '.mode == "HISTORICAL_REPLAY" and .session_date == $date'
done
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://200.234.39.232:8805
```

Also inspect `/api/chart?date=...` for every replay session. The final public
URL is not verified until the public-interface health probe and browser replay
both pass from an external client.

## Logs and retention

Both services write stdout and stderr only to journald and use stable
`SyslogIdentifier` values. Gateway access records contain only a normalized
method, allowlisted route, allowlisted query-key names, and status; raw paths,
query values, request lines, and client-controlled parser messages are never
logged. Journald adds service, PID, priority, and timestamp fields. There is no
second unbounded application log. The host journal already provides size- and
time-based rotation; retention is governed by the host journald policy and
cannot be broadened by an unprivileged unit.

```bash
journalctl --user -u r6e1r-shadow.service -u r6e1r-readonly-gateway.service --since today --output=json
journalctl --user -u r6e1r-shadow.service -u r6e1r-readonly-gateway.service -f -o cat
journalctl --user --disk-usage
```

## Host-level blockers

The mount and environment restrictions materially limit an exploited gateway,
but a same-UID process outside these service namespaces could still read files
that the account itself can read. This prepared user-service design accepts
that residual limitation because privileged service-account provisioning is
not available. Do not weaken file modes: deployment config/state remain 0700
directories with 0600 files. A future administrator may migrate the backend
and gateway to distinct locked-down system users without changing API or
analytical semantics.

`loginctl show-user codexuser -p Linger` currently reports `Linger=no`.
Services can restart while the current user manager is alive, but unattended
startup across logout/reboot is not guaranteed until an administrator runs
the narrowly scoped host action `loginctl enable-linger codexuser`.

This account also has no authority to change the host or provider firewall.
If the public-interface probe fails because inbound traffic is filtered, an
administrator must allow only TCP port 8805 (or the single documented fallback
port). Never open 8803–8810 as a range. Neither limitation justifies changing
the backend from `127.0.0.1`, touching collectors, or restarting the protected
8803/8804 services.
