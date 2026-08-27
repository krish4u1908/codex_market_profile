# R6E1R isolated user-service deployment

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

This directory is a prepared deployment package. It does not authorize an
install before callback equivalence, regression, package-manifest, and source
hash gates pass. The commands below are intentionally not run as part of
deployment preparation.

## Host layout and isolation

- Repository (read only at runtime): `$R6E1R_REPO_ROOT`
- Collector root (read only): `$R6E1R_COLLECTOR_ROOT`
- Writable deployment root: `$DEPLOY_ROOT`
- Analytical API: `127.0.0.1:18805` only
- Sanitized gateway: `0.0.0.0:$R6E1R_GATEWAY_PORT`
- Candidate external URL: `http://<PUBLIC_HOST>:$R6E1R_GATEWAY_PORT/`
- Protected existing ports: `8803` and `8804`; no command in this runbook
  addresses either service or port.

The checked-in units are sealed install-time templates; never install them
before rendering every token with `render_service_units.py`. The selected
repository, collector, deployment, and Python paths must match the values
rendered into the units, must be pairwise non-overlapping where required, and
must remain outside home, temporary, and per-user runtime trees hidden by the
unit sandbox. The units are user-manager units. They deliberately contain no `User=` or
`Group=` directive and install into `default.target`, not
`multi-user.target`. `r6e1r-shadow.service` has the only collector access and
binds to localhost. `r6e1r-readonly-gateway.service` can reach the backend but
serves only the exact GET/HEAD route allowlist in `read_only_gateway.py`.
The gateway is ordered after, but is not lifecycle-coupled to, the backend: it
returns a sanitized 503 while the backend restarts and remains available to
recover automatically without a manual gateway restart.
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
: "${R6E1R_REPO_ROOT:?set the checked-out repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${DEPLOY_ROOT:?set the writable isolated deployment root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_USER:?set the unprivileged service account}"
: "${R6E1R_USER_HOME:?set the service account home directory}"
R6E1R_GATEWAY_PORT="${R6E1R_GATEWAY_PORT:-8805}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
cd "$R6E1R_REPO_ROOT"
git diff --check
UNIT_CHECK_ROOT="$(mktemp -d)"
"$R6E1R_PYTHON" deploy/r6e1r/render_service_units.py \
  --repository-root "$R6E1R_REPO_ROOT" \
  --collector-root "$R6E1R_COLLECTOR_ROOT" \
  --deploy-root "$DEPLOY_ROOT" \
  --python "$R6E1R_PYTHON" \
  --gateway-port "$R6E1R_GATEWAY_PORT" \
  --output-dir "$UNIT_CHECK_ROOT"
systemd-analyze --user verify \
  "$UNIT_CHECK_ROOT/r6e1r-shadow.service" \
  "$UNIT_CHECK_ROOT/r6e1r-readonly-gateway.service"
env PYTHONPATH=src "$R6E1R_PYTHON" -m pytest -q deploy/r6e1r/test_deployment.py deploy/r6e1r/test_gateway_security.py tests/unit/test_r6e1r_live_gui_api.py
ss -ltnp
loginctl show-user "$R6E1R_USER" -p Linger -p State -p RuntimePath
```

Immediately before installation, confirm `127.0.0.1:18805` and the selected
external candidate port are unused. Prefer 8805; if it is no longer free, set
`R6E1R_GATEWAY_PORT` to the first free port from 8806 through 8810 before
rendering. The renderer changes both the listener and post-start probe. Never
select 8803 or 8804. Do not change the backend bind or port.

## Provision non-secret files

The templates contain no credentials. The activation object remains internal
runtime configuration and must remain non-secret. `activation_day` is the first
collector session the live service may discover; the prepared value is
2026-08-26. Historical sessions are made available by the verified-state
preload below, not by moving the activation boundary backward.

```bash
: "${R6E1R_REPO_ROOT:?set the checked-out repository root}"
: "${DEPLOY_ROOT:?set the writable isolated deployment root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_USER:?set the unprivileged service account}"
: "${R6E1R_USER_HOME:?set the service account home directory}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
! systemctl --user is-active --quiet r6e1r-shadow.service
! systemctl --user is-active --quiet r6e1r-readonly-gateway.service
cd "$R6E1R_REPO_ROOT"
install -d -m 0700 "$DEPLOY_ROOT" "$DEPLOY_ROOT/config"
install -m 0600 deploy/r6e1r/r6e1r-runtime-config.json.example "$DEPLOY_ROOT/config/r6e1r-runtime-config.json"
install -m 0600 deploy/r6e1r/r6e1r-activation.json.example "$DEPLOY_ROOT/config/r6e1r-activation.json"
"$R6E1R_PYTHON" -m json.tool "$DEPLOY_ROOT/config/r6e1r-runtime-config.json"
"$R6E1R_PYTHON" -m json.tool "$DEPLOY_ROOT/config/r6e1r-activation.json"
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

The service bootstrap opens the runner, runtime configuration, and activation
object once, hashes those exact bytes, and executes or parses those same
captured payloads. The runner then captures all 38 allowlisted Python/static
sources and loads the `banknifty_profiler` namespace only from authenticated
in-memory bytes; an unallowlisted submodule or filesystem fallback is refused.
NumPy 2.5.2, pandas 3.0.5, python-dateutil 2.9.0.post0, and six 1.17.0 are
admitted only through pinned wheel-RECORD inventory identities. Before import,
each declared runtime file is content-verified and copied from those exact bytes
into a private process-lifetime snapshot; imports never execute from the
original virtual-environment tree. Repository paths, `site`, and `.pth` files
are not processed. Both user units explicitly discard
inherited dynamic-loader, Python-startup, and shell-startup injection variables
before any bootstrap process is launched.

## Preload the six verified replay sessions

Preload only a clean `runs/incremental_a/state` produced by the actual R6E1R
production checkpoint/callback path after its comparisons report zero
differences. Never preload independent clean batch-B output, a derived R2–R6
table, or raw JSONL. The source run must contain 2026-08-11, 2026-08-12,
2026-08-13, 2026-08-18, 2026-08-19, and 2026-08-20 and must retain the August
17 rejection.

The preload is staged below `DEPLOY_ROOT`, so staging and the final state
directory are on the same filesystem. The source and staged copies are both
verified against one SHA-256 manifest. The staged copy must then pass the
dependency-light state validator before a single atomic directory rename makes
it live. A pre-existing target is refused; do not merge, overlay, or repair a
target in place. Both services must remain stopped throughout this procedure.

```bash
: "${R6E1R_REPO_ROOT:?set the checked-out repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${DEPLOY_ROOT:?set the writable isolated deployment root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_USER:?set the unprivileged service account}"
: "${R6E1R_USER_HOME:?set the service account home directory}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
! systemctl --user is-active --quiet r6e1r-shadow.service
! systemctl --user is-active --quiet r6e1r-readonly-gateway.service
cd "$R6E1R_REPO_ROOT"
VERIFIED_OUTPUT=/absolute/path/to/the/passing/r6e1r-equivalence-output
VERIFIED_STATE="$VERIFIED_OUTPUT/runs/incremental_a/state"
EQUIVALENCE_SUMMARY="$VERIFIED_OUTPUT/equivalence_summary.json"
RAW_PROJECTION_MANIFEST="$VERIFIED_OUTPUT/raw_projection_manifest.json"
STATE_MANIFEST="$VERIFIED_OUTPUT/incremental_a_state_manifest.json"
PACKAGE_MANIFEST=manifests/r6e1r_deployment_package_manifest.json
test ! -e "$DEPLOY_ROOT/state"
sha256sum -c manifests/r6e1r_deployment_package_manifest.sha256
jq -r '.files[] | "\(.sha256)  \(.path)"' "$PACKAGE_MANIFEST" | sha256sum -c -
EXPECTED_ENGINE_MANIFEST_SHA256="$(jq -er '.files[] | select(.path == "manifests/r6e1r_engine_source_manifest.json") | .sha256' "$PACKAGE_MANIFEST")"
EXPECTED_RUNTIME_CONFIG_SHA256="$(jq -er '.files[] | select(.path == "deploy/r6e1r/r6e1r-runtime-config.json.example") | .sha256' "$PACKAGE_MANIFEST")"
EXPECTED_ENGINE_HASH="$(jq -er '.engine_hash' "$PACKAGE_MANIFEST")"
EXPECTED_CONFIGURATION_HASH="$(jq -er '.runtime_configuration_hash' "$PACKAGE_MANIFEST")"
test -f "$EQUIVALENCE_SUMMARY"
test -f "$RAW_PROJECTION_MANIFEST"
test -f "$STATE_MANIFEST"
jq -er '.schema == "R6E1R_INCREMENTAL_A_STATE_TREE_MANIFEST_V1" and (.file_count > 0)' "$STATE_MANIFEST"
jq -r '.files[] | "\(.sha256)  \(.path)"' "$STATE_MANIFEST" | (cd "$VERIFIED_STATE" && sha256sum -c -)
STATE_STAGE="$(mktemp -d "$DEPLOY_ROOT/.state.preload.XXXXXX")"
chmod 0700 "$STATE_STAGE"
cp -a -- "$VERIFIED_STATE/." "$STATE_STAGE/"
chmod -R go-rwx "$STATE_STAGE"
jq -r '.files[] | "\(.sha256)  \(.path)"' "$STATE_MANIFEST" | (cd "$STATE_STAGE" && sha256sum -c -)
"$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null deploy/r6e1r/validate_preloaded_state.py \
  --state-root "$STATE_STAGE" \
  --expected-session 2026-08-11 \
  --expected-session 2026-08-12 \
  --expected-session 2026-08-13 \
  --expected-session 2026-08-18 \
  --expected-session 2026-08-19 \
  --expected-session 2026-08-20 \
  --engine-manifest manifests/r6e1r_engine_source_manifest.json \
  --expected-engine-manifest-sha256 "$EXPECTED_ENGINE_MANIFEST_SHA256" \
  --expected-engine-hash "$EXPECTED_ENGINE_HASH" \
  --runtime-config "$DEPLOY_ROOT/config/r6e1r-runtime-config.json" \
  --expected-runtime-config-sha256 "$EXPECTED_RUNTIME_CONFIG_SHA256" \
  --expected-configuration-hash "$EXPECTED_CONFIGURATION_HASH" \
  --equivalence-summary "$EQUIVALENCE_SUMMARY" \
  --raw-projection-manifest "$RAW_PROJECTION_MANIFEST" \
  --expected-authoritative-source-root "$R6E1R_COLLECTOR_ROOT" \
  --state-manifest "$STATE_MANIFEST"
test ! -e "$DEPLOY_ROOT/state"
mv -T -- "$STATE_STAGE" "$DEPLOY_ROOT/state"
```

The validator requires the exact state schema, streams every nonempty durable
ledger to bind the preload to the expected engine and configuration hashes,
requires both callback outboxes and the durable futures-selection probe table
to be empty,
and accepts only the fresh full six-session equivalence PASS. The equivalence
gate requires all zero-difference, causality, restart, file-open, source-hash,
reference-manifest, and frozen-count fields; it also binds the copied raw
projection manifest and its explicit August 17 present-for-rejection policy.
The state manifest must be the immutable `incremental_a_state_manifest.json`
emitted and cryptographically bound by that same passing harness run. Never
generate, replace, or refresh it during deployment. The validator requires an
exact file set, sizes, digests and aggregate hash, then recounts the actual
six-session analytical output lists against every frozen count. Its only
output is a sanitized JSON summary; retain it and the harness-emitted state
manifest with the equivalence evidence. If any command fails, leave the hidden
staging directory in place for offline inspection and do not start either
service. This preload does not alter the authoritative raw root or repository.
On startup, existing checkpoint identities and append-only analytical IDs
remain durable; only new files at or after `activation_day` are polled.

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
: "${R6E1R_REPO_ROOT:?set the checked-out repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${DEPLOY_ROOT:?set the writable isolated deployment root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_USER:?set the unprivileged service account}"
: "${R6E1R_USER_HOME:?set the service account home directory}"
R6E1R_GATEWAY_PORT="${R6E1R_GATEWAY_PORT:-8805}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
cd "$R6E1R_REPO_ROOT"
install -d -m 0700 "$R6E1R_USER_HOME/.config/systemd/user"
"$R6E1R_PYTHON" deploy/r6e1r/render_service_units.py \
  --repository-root "$R6E1R_REPO_ROOT" \
  --collector-root "$R6E1R_COLLECTOR_ROOT" \
  --deploy-root "$DEPLOY_ROOT" \
  --python "$R6E1R_PYTHON" \
  --gateway-port "$R6E1R_GATEWAY_PORT" \
  --output-dir "$R6E1R_USER_HOME/.config/systemd/user"
systemd-analyze --user verify \
  "$R6E1R_USER_HOME/.config/systemd/user/r6e1r-shadow.service" \
  "$R6E1R_USER_HOME/.config/systemd/user/r6e1r-readonly-gateway.service"
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

As a host crash-recovery acceptance check, first record the backend PID and the
listeners on ports 8803/8804. Then use exactly the service-scoped failure below;
a normal `stop` or SIGTERM is not a failure because the runner exits cleanly and
does not exercise `Restart=on-failure`.

```bash
: "${R6E1R_GATEWAY_PORT:?set the rendered gateway port}"
BACKEND_PID_BEFORE="$(systemctl --user show -p MainPID --value r6e1r-shadow.service)"
ss -ltnp | grep -E ":(8803|8804|18805|${R6E1R_GATEWAY_PORT})\\b"
systemctl --user kill --signal=SIGKILL --kill-whom=main r6e1r-shadow.service
RECOVERED=0
for attempt in $(seq 1 60); do
  BACKEND_PID_AFTER="$(systemctl --user show -p MainPID --value r6e1r-shadow.service)"
  if test "$BACKEND_PID_AFTER" -gt 0 && test "$BACKEND_PID_AFTER" != "$BACKEND_PID_BEFORE" \
    && systemctl --user is-active --quiet r6e1r-shadow.service \
    && systemctl --user is-active --quiet r6e1r-readonly-gateway.service \
    && "$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null \
      deploy/r6e1r/health_readiness_check.py --base-url "http://127.0.0.1:${R6E1R_GATEWAY_PORT}"; then
    RECOVERED=1
    break
  fi
  sleep 1
done
test "$RECOVERED" -eq 1
test "$BACKEND_PID_AFTER" -gt 0
test "$BACKEND_PID_AFTER" != "$BACKEND_PID_BEFORE"
systemctl --user is-active --quiet r6e1r-shadow.service
systemctl --user is-active --quiet r6e1r-readonly-gateway.service
```

Require the selected gateway port to recover without manually restarting the gateway, and
confirm the recorded 8803/8804 listeners and PIDs remain unchanged. Do not send
signals to any process serving ports 8803 or 8804.

Both units use `Restart=on-failure`, bounded restart bursts, SIGTERM shutdown,
and systemd memory, swap, CPU, task, and file-descriptor limits. The backend's
post-start health-plus-readiness retry permits up to 600 attempts for a
verified six-session cold preload and its start timeout is 900 seconds; the
lightweight gateway retains its 30-attempt/75-second boundary. The backend
begins memory reclaim above 8 GiB and has a hard 10 GiB ceiling with no swap
allowance. These are safety boundaries, not permission to truncate analytics;
an actual cold preload must remain below them before the deployment is
accepted.
The public gateway admits at most eight concurrent requests, permits no more
than 8 MiB in any backend response and 64 MiB across all in-flight response
bodies, and applies a five-second absolute accepted-socket/header deadline so a
slow client cannot extend the timeout one byte at a time. Excess concurrent
work fails with a sanitized 503; an oversized backend response fails with a
sanitized 502 `UPSTREAM_RESPONSE_LIMIT`. Before deployment, measure the
largest allowlisted `/api/chart` replay response for all six sessions and
require it to remain below 8 MiB; do not raise this boundary merely to make a
test pass.
Both localhost post-start probes use a 250-ms per-request timeout, so their
complete delay-plus-request budgets remain below the corresponding systemd
start timeout even when every request times out. They use the full readiness
contract: an allowlisted after-hours 503 is accepted, while checkpoint,
causality, or runtime-source identity failures prevent service activation.

## Health, readiness, replay, and external checks

The helper treats HTTP 503 readiness as benign only when all reasons are the
explicit stale/missing-market after-hours allowlist. Every probe, including a
benign 503, still requires checkpoint integrity, zero future joins, and a
verified runtime source manifest. Any other 503 is a failed operational probe.
`--require-ready` is reserved for an in-hours freshness acceptance check.

```bash
: "${R6E1R_REPO_ROOT:?set the checked-out repository root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_PUBLIC_ORIGIN:?set the externally reachable origin, including port}"
: "${R6E1R_GATEWAY_PORT:?set the rendered gateway port}"
cd "$R6E1R_REPO_ROOT"
"$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null deploy/r6e1r/health_readiness_check.py --base-url http://127.0.0.1:18805
"$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null deploy/r6e1r/health_readiness_check.py --base-url "http://127.0.0.1:${R6E1R_GATEWAY_PORT}"
for date in 2026-08-11 2026-08-12 2026-08-13 2026-08-18 2026-08-19 2026-08-20; do
  curl -fsS "http://127.0.0.1:${R6E1R_GATEWAY_PORT}/api/session?date=$date" | jq -e --arg date "$date" '.mode == "HISTORICAL_REPLAY" and .session_date == $date'
done
"$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null deploy/r6e1r/health_readiness_check.py --base-url "$R6E1R_PUBLIC_ORIGIN"
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

Check `loginctl show-user "$R6E1R_USER" -p Linger` at deployment time.
Services can restart while the current user manager is alive, but unattended
startup across logout/reboot requires `Linger=yes`. If it is disabled, an
administrator must run the narrowly scoped host action
`loginctl enable-linger "$R6E1R_USER"`.

This account also has no authority to change the host or provider firewall.
If the public-interface probe fails because inbound traffic is filtered, an
administrator must allow only the single rendered gateway port. Never open
8803–8810 as a range. Neither limitation justifies changing
the backend from `127.0.0.1`, touching collectors, or restarting the protected
8803/8804 services.
