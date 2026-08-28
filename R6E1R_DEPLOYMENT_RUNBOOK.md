# R6E1R Deployment Runbook

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **POST-REPAIR REGRESSION 660/660 AND FOCUSED PASS — V9 BASELINE PASS;
TERMINAL FULL-SIX SCHEDULES, PRELOAD, AND DEPLOYMENT PENDING**

The authoritative package guide is
[deploy/r6e1r/README.md](deploy/r6e1r/README.md). This root-level runbook records
the acceptance order and unfilled deployment evidence. It does not authorize
installation before equivalence, regression, source-integrity, browser,
runtime-file-open, systemd, and package gates pass.

No current `e1d67c5` deployment backend or gateway is installed or accepted,
no local endpoint or external URL is verified, and no R6E1R verification tag
has been created. The standard deployment units are inactive/dead and
runtime-masked with stale paths; do not start or reuse them. The separate v9
analytical acceptance unit does not expose the deployment API or GUI.

## Intended isolated layout

| Component | Intended address/path | Exposure |
|---|---|---|
| Analytical backend | `127.0.0.1:18805` | Localhost only |
| Sanitized gateway | Prefer `0.0.0.0:8805` if free | Read-only external surface |
| Preferred clean runtime worktree | `/opt/banknifty/repositories/r6e1r-runtime-e1d67c5` | Read-only at runtime; must be exact `e1d67c5` code |
| Raw collector | `/opt/banknifty-collector/data-prod-v4` | Backend read-only; hidden from gateway |
| Isolated deployment/state root | `/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final` | Backend state/config only; hidden from gateway |

Ports 8803 and 8804 are protected and must not be modified or restarted. Resolve
listeners with `ss -ltnp` immediately before installation. If 8805 is occupied,
select only the first unused port from 8806 through 8810 and document that one
port; never open the range.

The current read-only preflight found backend `127.0.0.1:18805` and gateway
port `8805` free. It found port 8803 unchanged at PID `380743`, process start
ticks `46015771`, invocation `d0df21acd54a440788d89f7cad5b4827`, and
`NRestarts=0`; port 8804 was unchanged at PID `465394`, process start ticks
`51980337`, invocation `260291b2ae4a4c70a95a0a37722af61e`, and
`NRestarts=0`. These are pre-install facts, not permission to skip the mandatory
immediate pre-install and post-deployment comparisons.

The standard `r6e1r-shadow.service` and
`r6e1r-readonly-gateway.service` names are currently inactive/dead and
runtime-masked. Existing definitions contain superseded paths. Fresh units may
be rendered, verified, and unmasked only after terminal analytical and
regression acceptance. Collector services and sources remain outside this
deployment scope; final source-hash and process-identity comparisons are still
required, and no command in this runbook authorizes modifying or restarting a
collector.

## Sealed source and package identity

| Item | Required value |
|---|---|
| Feature branch | `fix/r6e1r-final-live-shadow` |
| Current analytical commit | `e1d67c534bea5c61b0e3d379db7f599de7e1c445` |
| Pushed report head immediately before this refresh | `c555b099ffdfbee66117b33ad4693de9f61eaaea` |
| Final report-only pushed commit | `PENDING_FINAL_PUSH` |
| Preferred clean runtime worktree | `/opt/banknifty/repositories/r6e1r-runtime-e1d67c5` — `PENDING_FINAL_DEPLOYMENT_PREFLIGHT` |
| Isolated deployment root | `/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final` — `NOT_PROVISIONED_OR_ACCEPTED` |
| Engine source files | PASS — 38/38 |
| Engine JSON manifest SHA-256 (companion verification PASS) | `866bfd55e434ddacef29a952e3d618a71478463c44a95b44ca31340b3d96a210` |
| Engine aggregate hash | `eb3e848d75ef10471d14c641507f44b6f825c4dd63c305e27a803376048f2947` |
| Deployment package files | PASS — 47/47 |
| Deployment JSON manifest SHA-256 (companion verification PASS) | `80a439d67f6afb2b24e5e121f71770df5255e23297d06ec7e72a09d7dbd83391` |
| Deployment package aggregate hash | `4c2db034cb99a3391346155af708788896a04fa9b8bac6e7225f74bcb3ec5949` |
| Runtime configuration hash | `b4148be9892cc4e19c2a13d52ef68a65239578e6147cb3cdf94fd2d812e48a41` |
| Raw runtime-config template SHA-256 | `cbcf9f43befa4b18b4798240c18d841f1629af7a015c538c8ff254e01b6957ad` |
| Backend/gateway unit-template SHA-256 | `153a2b493b864f9442fda8d94d0c6c2cececfde87bc9cdbfcb78d99c9aa9e7ac` / `2b47c302ca3491686cd3b73d77f9190aecd413573676035923945147c49e5542` |

The current analytical commit passed the fully provisioned complete repository
regression 660/660 with zero failures or skips in 118.03 seconds (1m58.43 wall,
671,340 KiB peak RSS). The preceding 659/1 packaging result remains a non-pass;
the stale runtime-configuration pin was repaired before the complete clean
rerun.
That run includes the host-only ptrace/file-open, user-systemd/bubblewrap,
sealed-reference, API/gateway, and Chromium fixture gates. It does not install
or exercise the isolated live services.

The fresh post-repair focused August 19 all-nine run passed from the current
analytical commit: 21/21 canonical components, 8/8 ledgers, 9/9 causality gates,
9/9 schedules, 72/72 checkpoint rows, 2/2 recovery probes, 8/8
source-inventory rows, and 1/1 fixture-manifest row. The 2,508 total audit rows
comprised 2,499 runtime-open rows, 8 source-inventory rows, and 1
fixture-manifest row. All differences, refusals, future joins, timestamp
backdating, duplicate IDs, prohibited/unmeasured runtime opens, and source
mutations were zero.
Its summary SHA-256 is
`f83d519226bf7876be5446e16b657bbea9c3624f3ecb7a5e2a724bf35b0954f9`.
This focused result is not a substitute for the full six-session preload gate.

The earlier `81b0836fe50939246ae210bb62780ac4e163e100` full-six result and
deployment identities are historical only. They must not be used to provision
or validate the repaired `e1d67c5` engine.

The authorized host must fetch the exact final commit, fast-forward only, start from a clean
worktree, and independently verify both companions and every allowlisted byte.
Any byte mismatch stops installation. Do not regenerate or accept a manifest on
the deployment host merely to make a mismatch pass.

## Mandatory gates before installation

Run against fresh versioned state/output roots. Earlier focused and full-six
outputs are historical diagnostics and must not be reused as current acceptance
evidence.

1. Verify Git identity, clean worktree, both sealed manifests, runtime config,
   source hashes, and unchanged collectors.
2. Run focused August 19 all-nine schedule equivalence through the actual
   checkpoint/callback path.
3. Run full six-session all-nine schedule equivalence over the authoritative
   collector bytes for August 11, 12, 13, 18, 19, and 20.
4. Require exact canonical artifact equality, frozen reference equality, two
   causal periodic refreshes per evaluation session (12 total across six
   sessions) where specified, zero future joins, zero timestamp
   backdating, zero duplicate analytical IDs, zero prohibited runtime opens,
   zero source mutations, and deterministic restart/checkpoint behavior.
5. Run the complete repository regression suite, including host-only sealed
   comparison-package tests.
6. Run Chromium/Playwright browser and geometry tests on the authorized host, including
   fixed-horizon and Intraday-only graceful degradation.
7. Run the authorized-host ptrace/strace file-open audit and prove the runtime opens no
   prohibited source.
8. Verify both user-systemd units with the real authorized-host user manager and run
   the bubblewrap/namespace/refusal probes.
9. Prove the largest public chart response remains below the gateway's 8 MiB
   per-response ceiling.

The complete regression, focused equivalence, current fixture-browser, package,
and static service-template portions of these gates are closed for `e1d67c5`.
Persistent v9 runs from a clean detached checkout under invocation
`ce9595fd18b344ab8ab2765ae509f8fa`. Its immutable incremental-A,
independently clean chronological-B, canonical component, append-only ledger,
causality, R6C2R, and R6D GUI baseline matrices are sealed PASS. The alternate
schedules, terminal source rehash/final summary, and terminal state validation
are not yet complete. V9 state must not be copied or promoted until that final
terminal validation passes. This is the offline acceptance harness, not an
installed deployment backend or gateway, and no deployed URL exists.
Cold-preload RSS, public chart sizes, installed-service behavior, and every
deployed-live gate therefore remain pending. The user-supplied August 20 archive
is an auxiliary parser/replay diagnostic only and must not replace the
canonical full-six collector inputs.

Suggested pre-install checks include:

```bash
R6E1R_REPO_ROOT="${R6E1R_REPO_ROOT:-/opt/banknifty/repositories/r6e1r-runtime-e1d67c5}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final}"
: "${R6E1R_PYTHON:?set the verified Python executable}"
: "${R6E1R_USER:?set the service user}"
: "${R6E1R_USER_HOME:?set the service user's home}"
R6E1R_GATEWAY_PORT="${R6E1R_GATEWAY_PORT:-8805}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
cd "$R6E1R_REPO_ROOT"
git status --short --branch
git diff --check
sha256sum -c manifests/r6e1r_engine_source_manifest.sha256
sha256sum -c manifests/r6e1r_deployment_package_manifest.sha256
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
ss -ltnp
loginctl show-user "$R6E1R_USER" -p Linger -p State -p RuntimePath
```

Use the repository's current test commands and report files for the exact
equivalence and regression invocation. Do not weaken, deselect, or reclassify a
failure on the authorized host.

## Provision and preload after all gates pass

Create the deployment root with mode 0700 and configuration files with mode
0600, using the committed activation/runtime templates. Do not add credentials,
thresholds, fixed Futures contracts, or prospective claims.

Provisioning, preload, installation, and `systemctl --user` must all run in one
verified service-account shell. Repeat these fail-closed checks before either
provisioning or preload writes any byte:

```bash
: "${R6E1R_REPO_ROOT:?set the private repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${R6E1R_USER:?set the service user}"
: "${R6E1R_USER_HOME:?set the service user's home}"
test "$(id -un)" = "$R6E1R_USER"
test "$HOME" = "$R6E1R_USER_HOME"
test "$(getent passwd "$R6E1R_USER" | cut -d: -f6)" = "$R6E1R_USER_HOME"
! systemctl --user is-active --quiet r6e1r-shadow.service
! systemctl --user is-active --quiet r6e1r-readonly-gateway.service
cd "$R6E1R_REPO_ROOT"
```

Preload only the sealed state from the passing six-session production callback
run. Do not preload batch-B output, derived analytical tables, raw JSONL, or any
ledger created before the current immutable-event projection. Before copying,
require:

- all six replay sessions in the sealed state;
- August 17 rejection retained;
- no symlinks in source state;
- empty target state;
- both services stopped;
- a sorted SHA-256 manifest that passes after copy.

The only eligible candidate is persistent v9 `runs/incremental_a/state`, along
with its root terminal summary, projection manifest, and immutable state
manifest. It becomes eligible only after all nine schedules and terminal source
and state validations publish PASS. A sealed A baseline by itself is not preload
authorization.

Verified preload source and manifest: `PENDING_TERMINAL_V9_VALIDATION`

## Install user services

Run only after every preceding gate passes:

```bash
R6E1R_REPO_ROOT="${R6E1R_REPO_ROOT:-/opt/banknifty/repositories/r6e1r-runtime-e1d67c5}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final}"
: "${R6E1R_PYTHON:?set the verified Python executable}"
: "${R6E1R_USER:?set the service user}"
R6E1R_USER_HOME="${R6E1R_USER_HOME:?set the service user's home}"
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
systemctl --user unmask \
  r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user daemon-reload
systemctl --user enable --now \
  r6e1r-shadow.service r6e1r-readonly-gateway.service
```

The backend alone may read collector/state and binds only to localhost. The
gateway uses the prepared rootless isolation and exact route/query allowlists;
it must not see collector data, analytical state/config, credentials, or user
key material.

## Verification after start

```bash
R6E1R_PYTHON="${R6E1R_PYTHON:?set the verified Python executable}"
R6E1R_GATEWAY_PORT="${R6E1R_GATEWAY_PORT:?set the rendered gateway port}"
"$R6E1R_PYTHON" -I -S -B \
  -X pycache_prefix=/dev/null deploy/r6e1r/health_readiness_check.py \
  --base-url http://127.0.0.1:18805
"$R6E1R_PYTHON" -I -S -B \
  -X pycache_prefix=/dev/null deploy/r6e1r/health_readiness_check.py \
  --base-url "http://127.0.0.1:${R6E1R_GATEWAY_PORT}"
for date in 2026-08-11 2026-08-12 2026-08-13 2026-08-18 2026-08-19 2026-08-20; do
  curl -fsS "http://127.0.0.1:${R6E1R_GATEWAY_PORT}/api/session?date=$date" | \
    jq -e --arg date "$date" \
      '.mode == "HISTORICAL_REPLAY" and .session_date == $date'
done
```

Set the rendered gateway port to the single documented selected value. Resolve
the public interface at deployment time and probe it without recording a
proposed address as verified evidence.

After-hours readiness may be HTTP 503 only for explicit benign stale/missing
market reasons. Health, checkpoint integrity, zero causal violations, and
manifest verification must still pass.

Mandatory recovery probe:

1. Confirm both services are active and gateway health is HTTP 200.
2. Send SIGKILL to the backend service's main process through systemd.
3. Confirm the gateway service remains active while returning only sanitized
   temporary-unavailability responses.
4. Confirm the backend restarts automatically and both health probes recover
   without manually restarting the gateway.

Do not intentionally kill or restart any collector or the services on ports
8803/8804.

## Operations after acceptance

These commands apply only after fresh units have been rendered, verified,
unmasked, enabled, and accepted. They are not instructions to operate the
currently masked stale definitions.

```bash
# Status and recent structured journal records
systemctl --user status \
  r6e1r-shadow.service r6e1r-readonly-gateway.service
journalctl --user \
  -u r6e1r-shadow.service -u r6e1r-readonly-gateway.service \
  --since today --no-pager

# Normal lifecycle
systemctl --user start \
  r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user restart \
  r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user stop \
  r6e1r-readonly-gateway.service r6e1r-shadow.service
```

After a start or restart, repeat both local health/readiness probes and confirm
the protected 8803/8804 PID, start-tick, invocation, and restart-counter
identities remain unchanged. A 503 readiness response is acceptable only for
the documented after-hours `STALE_DATA` reasons; process health must still be
HTTP 200.

## Host limitations to resolve during acceptance

- User-manager state was measured as active with `Linger=yes`. Recheck it at
  installation; no linger change is currently required.
- Host UFW is active with IPv4/IPv6 enabled and default inbound policy `DROP`.
  The current account lacks permission to change it and lacks provider-firewall
  authority. External ingress is therefore likely blocked even if local health
  later passes. An administrator must verify whether the single selected port
  is already allowed and, only if necessary, allow that one TCP port. Never
  open 8803–8810 as a range. A genuinely external client must still verify the
  public route.
- Cold-preload memory, public reachability, exact port exposure, service restart
  behavior, and structured-log rotation remain live measurements.
- The checked-in units mount the repository and collector read-only and hide
  collector/state/config from the gateway. Outside those namespaces, this
  same UID currently has host-level write permission to the repository and the
  collector `raw`/`oi` directories. That residual same-UID authority is an
  accepted limitation of the prepared user-service design, not permission for
  any deployment command to modify those paths. Preserve 0700 deployment
  directories and 0600 files; a future administrator may migrate the services
  to distinct locked-down users.

The host's public IPv4 observed during the read-only audit was
`200.234.39.232`. With port 8805 still free, the candidate URL is
`http://200.234.39.232:8805/`. It remains a candidate only until installation,
the single-port firewall check, an off-host health probe, and an external
browser replay all pass.

## Final deployment record

| Field | Value |
|---|---|
| Current analytical commit | `e1d67c534bea5c61b0e3d379db7f599de7e1c445` |
| Pushed report head immediately before this refresh | `c555b099ffdfbee66117b33ad4693de9f61eaaea` |
| Final report-only pushed commit | `PENDING_FINAL_PUSH` |
| Verification tag | `NOT_CREATED` |
| Candidate external port | `8805` (free at static audit; selection pending immediate pre-install recheck) |
| Analytical acceptance unit | Persistent v9 invocation `ce9595fd18b344ab8ab2765ae509f8fa`; baseline/reference matrices PASS; terminal schedules/result pending |
| Backend service active/enabled | `INACTIVE_DEAD_RUNTIME_MASKED_STALE_NOT_ACCEPTED` |
| Gateway service active/enabled | `INACTIVE_DEAD_RUNTIME_MASKED_STALE_NOT_ACCEPTED` |
| Preferred runtime worktree | `/opt/banknifty/repositories/r6e1r-runtime-e1d67c5` — final clean/identity verification pending |
| Isolated deployment root | `/opt/banknifty/research/r6e1r_live_shadow_e1d67c5_final` — not provisioned or accepted |
| Full-six preload source/manifest | `PENDING_TERMINAL_V9_VALIDATION` |
| Health | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| Readiness | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| Six replay checks | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| Backend SIGKILL/gateway continuity | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| Public-interface probe | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| External browser check | `PENDING_AUTHORIZED_HOST_EVIDENCE` |
| Candidate URL | `http://200.234.39.232:8805/` — `NOT_DEPLOYED_OR_VERIFIED` |
| Ports 8803/8804 unchanged | Static preflight PASS at PIDs `380743` / `465394`; post-deployment recheck pending |
| Collectors unchanged | No deployment operation performed; final source-hash/process-identity and post-deployment recheck pending |

Create and push `r6e1r-live-shadow-verified` only after every analytical,
regression, browser, runtime, service, recovery, and external probe passes.
