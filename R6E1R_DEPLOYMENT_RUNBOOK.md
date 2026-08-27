# R6E1R Deployment Runbook

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **SEALED PACKAGE PREPARED — HOSTINGER ACCEPTANCE AND INSTALLATION PENDING**

The authoritative package guide is
[deploy/r6e1r/README.md](deploy/r6e1r/README.md). This root-level runbook records
the acceptance order and unfilled deployment evidence. It does not authorize
installation before equivalence, regression, source-integrity, browser,
runtime-file-open, systemd, and package gates pass.

No R6E1R service is currently verified as installed, no external URL is
verified, and no R6E1R verification tag has been created.

## Intended isolated layout

| Component | Intended address/path | Exposure |
|---|---|---|
| Analytical backend | `127.0.0.1:18805` | Localhost only |
| Sanitized gateway | Prefer `0.0.0.0:8805` if free | Read-only external surface |
| Repository | `<HOST_REPOSITORY_ROOT>` | Read-only at runtime |
| Raw collector | `<HOST_RAW_ROOT>` | Backend read-only; hidden from gateway |
| State/config root | `<HOST_STATE_ROOT>` | Backend state only; hidden from gateway |

Ports 8803 and 8804 are protected and must not be modified or restarted. Resolve
listeners with `ss -ltnp` immediately before installation. If 8805 is occupied,
select only the first unused port from 8806 through 8810 and document that one
port; never open the range.

## Sealed source and package identity

| Item | Required value |
|---|---|
| Feature branch | `fix/r6e1r-final-live-shadow` |
| Exact pushed commit | `PENDING_FINAL_PUSH` |
| Clean remote worktree | `PENDING_HOSTINGER_EVIDENCE` |
| Engine source files | PASS — 38/38 |
| Engine manifest/companion SHA-256 | `715a82b48e7bffe68f749f94c29b6d0e098bfe0e55f24d91e00db690e38827b3` |
| Engine aggregate hash | `021935bc0722b16a16e3af52deb7a7f26ef1aa6b4983aa3442420596bc00725d` |
| Deployment package files | PASS — 47/47 |
| Deployment manifest/companion SHA-256 | `7dcd1d15b36f4b84f367153f5842bd02a94da75bff06e5aae1ca7466a91c9af1` |
| Deployment package aggregate hash | `d68f22217f1dfb75817ebb9b7cb6af0d21306cf1081b7d222c6ecca130978380` |
| Runtime configuration hash | `5ce1058763ecc47494f9bdf231439117c6a4fb64c2e491d70395b4be0c50b031` |

Hostinger must fetch the exact final commit, fast-forward only, start from a clean
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
4. Require exact canonical artifact equality, frozen reference equality, five
   periodic refreshes where specified, zero future joins, zero timestamp
   backdating, zero duplicate analytical IDs, zero prohibited runtime opens,
   zero source mutations, and deterministic restart/checkpoint behavior.
5. Run the complete repository regression suite, including host-only sealed
   comparison-package tests.
6. Run Hostinger Chromium/Playwright browser and geometry tests, including
   fixed-horizon and Intraday-only graceful degradation.
7. Run the Hostinger ptrace/strace file-open audit and prove the runtime opens no
   prohibited source.
8. Verify both user-systemd units with the real Hostinger user manager and run
   the bubblewrap/namespace/refusal probes.
9. Prove the largest public chart response remains below the gateway's 8 MiB
   per-response ceiling.

These gates are all `PENDING_HOSTINGER_EVIDENCE`. The user-supplied August 20
archive is an auxiliary parser/replay diagnostic only and must not replace the
canonical full-six collector inputs.

Suggested pre-install checks include:

```bash
R6E1R_REPO_ROOT="${R6E1R_REPO_ROOT:?set the private repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${DEPLOY_ROOT:?set the isolated deployment root}"
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
failure on Hostinger.

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

Verified preload source and manifest: `PENDING_HOSTINGER_EVIDENCE`

## Install user services

Run only after every preceding gate passes:

```bash
R6E1R_REPO_ROOT="${R6E1R_REPO_ROOT:?set the private repository root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${DEPLOY_ROOT:?set the isolated deployment root}"
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

## Host limitations to resolve during acceptance

- User-manager linger/startup state must be measured on Hostinger. If
  `Linger=no`, administrator authorization may be required for unattended
  startup across logout/reboot.
- Host/provider firewall changes are outside this source package. If required,
  allow only the selected single TCP research port.
- Cold-preload memory, public reachability, exact port exposure, service restart
  behavior, and structured-log rotation remain live measurements.

## Final deployment record

| Field | Value |
|---|---|
| Final pushed commit | `PENDING_FINAL_PUSH` |
| Verification tag | `NOT_CREATED` |
| Selected external port | `PENDING_HOSTINGER_EVIDENCE` |
| Backend service active/enabled | `PENDING_HOSTINGER_EVIDENCE` |
| Gateway service active/enabled | `PENDING_HOSTINGER_EVIDENCE` |
| Health | `PENDING_HOSTINGER_EVIDENCE` |
| Readiness | `PENDING_HOSTINGER_EVIDENCE` |
| Six replay checks | `PENDING_HOSTINGER_EVIDENCE` |
| Backend SIGKILL/gateway continuity | `PENDING_HOSTINGER_EVIDENCE` |
| Public-interface probe | `PENDING_HOSTINGER_EVIDENCE` |
| External browser check | `PENDING_HOSTINGER_EVIDENCE` |
| Verified external URL | `NOT_DEPLOYED` |
| Ports 8803/8804 unchanged | `PENDING_HOSTINGER_EVIDENCE` |
| Collectors unchanged | `PENDING_HOSTINGER_EVIDENCE` |

Create and push `r6e1r-live-shadow-verified` only after every analytical,
regression, browser, runtime, service, recovery, and external probe passes.
