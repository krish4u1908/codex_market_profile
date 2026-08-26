# R6E1R Deployment Runbook

Classification: **LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

Status: **PREPARED — INSTALLATION PENDING FINAL ANALYTICAL GATES**

The authoritative detailed package guide is [deploy/r6e1r/README.md](deploy/r6e1r/README.md). This root-level runbook records the acceptance order and final evidence fields. It does not authorize installation before equivalence, regression, manifest, source-integrity, and browser gates pass.

## Intended isolated layout

| Component | Intended address/path | Exposure |
|---|---|---|
| Analytical backend | `127.0.0.1:18805` | Localhost only |
| Sanitized gateway | Candidate `0.0.0.0:8805` | Read-only external surface |
| Repository | `/opt/banknifty/repositories/banknifty-market-profiler` | Read-only at runtime |
| Raw collector | `/opt/banknifty-collector/data-prod-v4` | Backend read-only; hidden from gateway |
| State/config root | `/opt/banknifty/research/vpoc_oi_price_response_v2/r6e1r_final_live_shadow` | Backend state only; hidden from gateway |

Ports 8803 and 8804 were occupied by existing dashboards during preflight and are protected. The draft observed 8805-8810 unused; port availability must be rechecked immediately before installation.

Candidate URL: `http://200.234.39.232:8805/`

Verified deployed URL: `PENDING_FINAL_EVIDENCE`

## Prepared source identity

| Item | Current prepared value |
|---|---|
| Feature branch | `fix/r6e1r-final-live-shadow` |
| Pushed source head | `4d160bcc61bcebd88135ce270c17926830022deb` |
| Engine source files | 26/26 verified |
| Engine manifest SHA-256 | `7c13b44c9ae4fbc9c3317900866ddaf68800abe7b2c4d7a9f4e1749e41abc3b3` |
| Engine hash | `980b6af26e9ca5957b97bafb235474e13d268c691f2cbf3797f1d53fff011602` |
| Deployment package manifest | PASS — 34 files; manifest `ebaf193dca7f3cce82974906e05693864db087a60c7f7e3f028a6d1e7dc80ae3`; package `cecb7638566fae1a3831e1ef3fdb94559dce897aa54d89db12c882550c8dbc41` |

The current committed but uninstalled backend unit uses `MemoryHigh=8G`, `MemoryMax=10G`, `TimeoutStartSec=900s`, and a 250 ms per-attempt health-probe timeout. Static current-source unit verification and package resealing pass; analytical preload and live installation evidence remain mandatory before acceptance.

## Gate before any install

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
git diff --check
systemd-analyze --user verify deploy/r6e1r/r6e1r-shadow.service deploy/r6e1r/r6e1r-readonly-gateway.service
env PYTHONPATH=src /opt/banknifty/research/.venv/bin/python -m pytest -q deploy/r6e1r/test_deployment.py tests/unit/test_r6e1r_live_gui_api.py
ss -ltnp
loginctl show-user codexuser -p Linger -p State -p RuntimePath
```

Also verify the final allowlist manifest and explicit runtime digest, the sealed incremental-A state manifest, final source hashes, and a clean pushed feature branch. If 8805 is occupied, choose only the first unused port from 8806 through 8810. Never choose 8803 or 8804 and never open the range.

Re-resolve the public interface immediately before the external probe. `http://200.234.39.232:8805/` is a preflight candidate, not deployed or final reachability evidence.

## Provision and preload

Create the deployment root with mode 0700 and config files with mode 0600, using the committed activation/runtime templates. Do not add credentials, thresholds, fixed Futures contracts, or prospective claims.

Preload only `runs/incremental_a/state` from the passing six-session production callback run. Do not preload batch-B output, derived analytical tables, or raw JSONL. Before copying, require:

- all six replay sessions in the sealed state;
- August 17 rejection retained;
- no symlinks in source state;
- empty target state;
- both services stopped;
- a sorted SHA-256 manifest that passes after copy.

Verified preload source and manifest: `PENDING_FINAL_EVIDENCE`

## Install user services

```bash
cd /opt/banknifty/repositories/banknifty-market-profiler
install -d -m 0700 /home/codexuser/.config/systemd/user
install -m 0644 deploy/r6e1r/r6e1r-shadow.service /home/codexuser/.config/systemd/user/r6e1r-shadow.service
install -m 0644 deploy/r6e1r/r6e1r-readonly-gateway.service /home/codexuser/.config/systemd/user/r6e1r-readonly-gateway.service
systemctl --user daemon-reload
systemctl --user enable --now r6e1r-shadow.service r6e1r-readonly-gateway.service
```

The backend alone can read collector/state and binds only to localhost. The gateway uses a rootless bubblewrap mount/PID/user/IPC/UTS/cgroup boundary, a shared network namespace for localhost proxying and public bind, cleared environment, no capabilities, private keyring, and exact route/query allowlists. The gateway cannot see collector data, analytical state/config, or the user GnuPG runtime directory inside its prepared namespace.

## Routine operation

```bash
systemctl --user start r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user stop r6e1r-readonly-gateway.service r6e1r-shadow.service
systemctl --user restart r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user status r6e1r-shadow.service r6e1r-readonly-gateway.service --no-pager
systemctl --user is-enabled r6e1r-shadow.service r6e1r-readonly-gateway.service
systemctl --user is-active r6e1r-shadow.service r6e1r-readonly-gateway.service
```

Both units use automatic restart, bounded resources, SIGTERM shutdown, journald, and rate-limited structured output. Gateway access logs retain only normalized method, allowlisted route, allowlisted query-key names, and status.

## Verification after start

```bash
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://127.0.0.1:18805
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://127.0.0.1:8805
for date in 2026-08-11 2026-08-12 2026-08-13 2026-08-18 2026-08-19 2026-08-20; do
  curl -fsS "http://127.0.0.1:8805/api/session?date=$date" | jq -e --arg date "$date" '.mode == "HISTORICAL_REPLAY" and .session_date == $date'
done
/opt/banknifty/research/.venv/bin/python -B deploy/r6e1r/health_readiness_check.py --base-url http://200.234.39.232:8805
```

After-hours readiness may be HTTP 503 only for the explicit benign stale/missing-market reasons. Health, checkpoint integrity, zero future joins/synchronization violations, and manifest verification must still pass.

## Host limitations

- `Linger=no` was observed. Automatic restart works while the user manager exists, but unattended startup across logout/reboot requires administrator authorization for `loginctl enable-linger codexuser`.
- This account cannot change the host/provider firewall. If needed, an administrator may allow only the selected single TCP research port.
- Same-UID processes outside the service namespaces retain the account's ordinary filesystem authority. A future administrator can improve this residual risk with distinct locked-down service users.

## Final deployment record

| Field | Value |
|---|---|
| Selected external port | `PENDING_FINAL_EVIDENCE` |
| Backend service active/enabled | `PENDING_FINAL_EVIDENCE` |
| Gateway service active/enabled | `PENDING_FINAL_EVIDENCE` |
| Health | `PENDING_FINAL_EVIDENCE` |
| Readiness | `PENDING_FINAL_EVIDENCE` |
| Six replay checks | `PENDING_FINAL_EVIDENCE` |
| Public-interface probe | `PENDING_FINAL_EVIDENCE` |
| External browser check | `PENDING_FINAL_EVIDENCE` |
| Ports 8803/8804 unchanged | `PENDING_FINAL_EVIDENCE` |
| Collectors unchanged | `PENDING_FINAL_EVIDENCE` |
