# R6E1R provisional clean-start deployment

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **PROVISIONAL CLEAN-START — FULL-SIX PENDING**

This is a separate deployment package for operating the exact repaired
`a12a5864cc1cd28cf4b0c1d665d63fa623a1c69a` analytical engine while the
full-six all-nine acceptance run continues. It does not alter, bypass, or
replace `deploy/r6e1r/validate_preloaded_state.py`, the sealed final package,
or the final verification gate.

The provisional runtime starts from a newly created empty state directory and
reads only collector sessions on or after the sealed activation boundary,
2026-08-26. It does not preload the focused fixture, an obsolete equivalence
state, or any part of the active full-six output. Its state is never promoted
into the final deployment.

## Non-negotiable boundaries

- Keep `r6e1r-v2-six-a12a586-v1.service` and its process, output, checkpoints,
  invocation, CPU affinity, and limits untouched.
- Keep collectors and existing ports 8803/8804 untouched.
- Install only the two units whose names begin `r6e1r-provisional-`.
- Use a new deployment root. Do not point this package at a final or test state
  root.
- Do not create `r6e1r-live-shadow-verified` or describe this deployment as
  full-six verified.
- Do not expose filesystem paths, credentials, raw records, or write/trading
  routes.
- Historical six-session replay is not certified in this mode. The public
  gateway serves the current/latest diagnostic view; the final verified replay
  is deployed only after full-six passes.

The provisional backend conflicts only with the final `r6e1r-shadow.service`
because both use `127.0.0.1:18805`. The provisional gateway similarly
conflicts with the final gateway. Neither unit conflicts with or controls the
full-six validation service.

## Package and host preflight

Set these host-local values without committing them:

```bash
: "${R6E1R_REPO_ROOT:?set the exact provisional checkout root}"
: "${R6E1R_COLLECTOR_ROOT:?set the authoritative collector root}"
: "${PROVISIONAL_DEPLOY_ROOT:?set a new private deployment root}"
: "${R6E1R_PYTHON:?set the verified virtual-environment Python}"
: "${R6E1R_USER_HOME:?set the service account home}"
R6E1R_GATEWAY_PORT="${R6E1R_GATEWAY_PORT:-8805}"
cd "$R6E1R_REPO_ROOT"
git diff --check
sha256sum -c manifests/r6e1r_provisional_deployment_package_manifest.sha256
jq -r '.files[] | "\(.sha256)  \(.path)"' \
  manifests/r6e1r_provisional_deployment_package_manifest.json | sha256sum -c -
test "$(jq -r .engine_base_commit manifests/r6e1r_provisional_deployment_package_manifest.json)" = \
  a12a5864cc1cd28cf4b0c1d665d63fa623a1c69a
test "$(jq -r .final_equivalence_status manifests/r6e1r_provisional_deployment_package_manifest.json)" = \
  PENDING_FULL_SIX_ALL_NINE
test "$(jq -r .final_tag_authorized manifests/r6e1r_provisional_deployment_package_manifest.json)" = false
ss -ltnp
systemctl --user show r6e1r-v2-six-a12a586-v1.service \
  -p ActiveState -p SubState -p MainPID -p InvocationID -p NRestarts
```

Require the accepted full-six unit to remain active with the same invocation
and zero restarts. Require `127.0.0.1:18805` and the selected gateway port to
be unused. Prefer 8805, otherwise choose the first unused port through 8810.
Never select 8803 or 8804.

## Create the isolated empty state

The preparation validator is intentionally incompatible with preloaded state.
It refuses a pre-existing state path and creates a private empty directory plus
a path-, inode-, configuration-, engine-, activation-, and package-bound
attestation. The attestation contains no raw data or plaintext host paths.

```bash
cd "$R6E1R_REPO_ROOT"
test ! -e "$PROVISIONAL_DEPLOY_ROOT"
install -d -m 0700 "$PROVISIONAL_DEPLOY_ROOT" \
  "$PROVISIONAL_DEPLOY_ROOT/config"
install -m 0600 \
  deploy/r6e1r_provisional/r6e1r-runtime-config.json.example \
  "$PROVISIONAL_DEPLOY_ROOT/config/r6e1r-runtime-config.json"
install -m 0600 \
  deploy/r6e1r_provisional/r6e1r-activation.json.example \
  "$PROVISIONAL_DEPLOY_ROOT/config/r6e1r-activation.json"
"$R6E1R_PYTHON" -I -S -B -X pycache_prefix=/dev/null \
  deploy/r6e1r_provisional/validate_clean_start.py prepare \
  --repository-root "$R6E1R_REPO_ROOT" \
  --collector-root "$R6E1R_COLLECTOR_ROOT" \
  --deploy-root "$PROVISIONAL_DEPLOY_ROOT" \
  --state-root "$PROVISIONAL_DEPLOY_ROOT/state" \
  --runtime-config "$PROVISIONAL_DEPLOY_ROOT/config/r6e1r-runtime-config.json" \
  --activation "$PROVISIONAL_DEPLOY_ROOT/config/r6e1r-activation.json" \
  --attestation "$PROVISIONAL_DEPLOY_ROOT/config/r6e1r-provisional-clean-start-attestation.json"
```

Require JSON output with `ok:true`, `state_mode:"NEW_EMPTY_STATE"`,
`preloaded_state:false`, and `final_tag_authorized:false`. Do not manually
create, copy into, or edit the state directory after preparation.

## Render and install only the provisional units

Never install the raw tokenized templates.

```bash
cd "$R6E1R_REPO_ROOT"
UNIT_STAGE="$(mktemp -d)"
"$R6E1R_PYTHON" deploy/r6e1r_provisional/render_service_units.py \
  --repository-root "$R6E1R_REPO_ROOT" \
  --collector-root "$R6E1R_COLLECTOR_ROOT" \
  --deploy-root "$PROVISIONAL_DEPLOY_ROOT" \
  --python "$R6E1R_PYTHON" \
  --gateway-port "$R6E1R_GATEWAY_PORT" \
  --output-dir "$UNIT_STAGE"
systemd-analyze --user verify \
  "$UNIT_STAGE/r6e1r-provisional-shadow.service" \
  "$UNIT_STAGE/r6e1r-provisional-readonly-gateway.service"
install -d -m 0700 "$R6E1R_USER_HOME/.config/systemd/user"
install -m 0644 "$UNIT_STAGE/r6e1r-provisional-shadow.service" \
  "$R6E1R_USER_HOME/.config/systemd/user/r6e1r-provisional-shadow.service"
install -m 0644 "$UNIT_STAGE/r6e1r-provisional-readonly-gateway.service" \
  "$R6E1R_USER_HOME/.config/systemd/user/r6e1r-provisional-readonly-gateway.service"
systemctl --user daemon-reload
systemctl --user enable --now r6e1r-provisional-shadow.service
systemctl --user enable --now r6e1r-provisional-readonly-gateway.service
```

The backend start check re-verifies the full provisional package, deployed
configuration, attestation, state-directory identity, permissions, symlink
absence, JSON state envelopes, and SQLite health before every start. A hard
stop may leave a recognized SQLite recovery sidecar; only the authenticated
runtime may recover it. No validator deletes or repairs runtime evidence.

## Acceptance for provisional operation

```bash
systemctl --user is-active r6e1r-provisional-shadow.service
systemctl --user is-active r6e1r-provisional-readonly-gateway.service
systemctl --user show r6e1r-provisional-shadow.service \
  -p MainPID -p InvocationID -p NRestarts -p MemoryCurrent -p MemoryPeak -p Result
curl --fail --silent http://127.0.0.1:18805/api/health
curl --silent --show-error http://127.0.0.1:18805/api/readiness
curl --fail --silent "http://127.0.0.1:${R6E1R_GATEWAY_PORT}/api/health"
curl --silent --show-error "http://127.0.0.1:${R6E1R_GATEWAY_PORT}/api/readiness"
curl --fail --silent "http://127.0.0.1:${R6E1R_GATEWAY_PORT}/api/status"
systemctl --user show r6e1r-v2-six-a12a586-v1.service \
  -p ActiveState -p SubState -p MainPID -p InvocationID -p NRestarts
ss -ltnp
```

After hours, readiness may be `503 STALE_DATA` only when health is 200,
checkpoint/source-manifest integrity remains true, causality counters remain
zero, and the current/latest status endpoint works. During initial catch-up,
readiness can remain unavailable until the service has processed sufficient
post-activation collector data. This is not a failure of the long full-six
run.

Verify externally only through the selected provisional URL. Confirm POST,
PUT, PATCH, and DELETE return 405, unknown paths are sanitized, and no response
contains private paths or credentials.

## Stop or replace

To stop only the provisional deployment:

```bash
systemctl --user disable --now r6e1r-provisional-readonly-gateway.service
systemctl --user disable --now r6e1r-provisional-shadow.service
```

Do not delete its state while diagnosing a failure. Once full-six all-nine
passes, preserve the provisional state as non-acceptance evidence, stop these
two units, and deploy the final package through `deploy/r6e1r/README.md` using
only the immutable full-six incremental-A state. Never copy or merge the
provisional clean-start state into the final state root.
