# V1.0.35 staging deployment

V1.0.35 is built from the supplied V1.0.32 source archive. Deploy it beside the
current service. Do not replace or promote the existing service until the
historical and live acceptance checks pass.

## 1. Extract and verify

```bash
mkdir -p /home/bankadmin/divergence/releases
cd /home/bankadmin/divergence/releases
tar -xzf banknifty-new-divergence-v1.0.35.tar.gz
cd banknifty-new-divergence-v1.0.35
grep -E 'version = "1.0.35"' pyproject.toml
grep 'RUNTIME_VERSION = "1.0.35"' src/banknifty_profiler/new_divergence/provenance.py
```

Compare the archive SHA-256 with the value delivered with the release before
installing.

## 2. Install without starting a service

```bash
cd /home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.35
chmod +x install.sh install_v1035_staging.sh run_live.sh
sudo -u bankadmin -H ./install.sh
sudo -u bankadmin -H .venv/bin/banknifty-new-divergence --help
```

## 3. Run the detector assertions

The release includes a dependency-free verification runner:

```bash
sudo -u bankadmin -H .venv/bin/python scripts/verify_v1035.py
```

If `pytest` is available:

```bash
sudo -u bankadmin -H .venv/bin/python -m pytest -q \
  tests/new_divergence/test_short_trap_v1035.py \
  tests/new_divergence/test_scenario_v1028.py
```

Required acceptance: exact 2.5x passes; 2.499x fails; gap/reset baselines fail;
candidate direction is `NO_EDGE`; same-minute reversal cannot confirm; the
confirmation timestamp is later than the climax timestamp.

## 4. Build isolated live assets and state

```bash
sudo -u bankadmin -H .venv/bin/banknifty-new-divergence build-live-browser \
  --output-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.35
```

Do not reuse the production state or browser directories.

## 5. Install a separate loopback staging service

```bash
sudo ./install_v1035_staging.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-live-state-v1.0.35 \
  --browser-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.35 \
  --host 127.0.0.1 \
  --port 8797
```

This writes only
`banknifty-new-divergence-v1035-staging.service`. It does not overwrite the
existing `banknifty-new-divergence-live.service`.

## 6. Start and verify staging

```bash
sudo systemctl start banknifty-new-divergence-v1035-staging.service
sudo systemctl status banknifty-new-divergence-v1035-staging.service --no-pager --full
curl -fsS http://127.0.0.1:8797/healthz | python3 -m json.tool
sudo journalctl -u banknifty-new-divergence-v1035-staging.service -n 100 --no-pager
```

Verify runtime `1.0.35`, monotonic authority sequence, no recovery-required
state, and no future records. Enable commentary only after deterministic
staging is healthy; re-run the installer with `--enable-commentary` and restart
the staging service.

## 7. Historical acceptance before promotion

Replay the same eligible sessions used for the V1.0.33/V1.0.34 comparison into
a new output root. Export every candidate and confirmation with its UTC/IST
climax and signal receipts. Report at minimum:

- candidates, confirmed signals, expiries, and deduplicated episode counts;
- success/failed/ambiguous outcomes anchored at the signal receipt, not T0;
- distribution of volume ratios for each outcome;
- climax-to-signal receipt latency;
- rejected gap/reset/missing/non-positive-baseline counts;
- explicit comparison with the legacy 19 short-trap events.

Do not select or tune the threshold using those outcomes. Use a later,
untouched session set for any edge claim.

## 8. Stop or roll back staging

```bash
sudo systemctl disable --now banknifty-new-divergence-v1035-staging.service
```

This leaves the V1.0.35 state, logs, browser assets, and current production
service intact for audit. Production promotion requires a separate explicit
approval and change window.
