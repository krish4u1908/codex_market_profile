# Build all eligible NIFTY replay sessions

The converter reads the existing collector archive and creates both shared-core
profiles for every completed NIFTY date: `nifty-v1062` and `nifty-v200`.

It never writes to `/opt/nifty-collector/data-prod-nifty`, starts no service,
and never replaces a `recorded-*` replay. Rebuilt sessions use a new
content-addressed `rebuilt-*` key. Reference calls are labelled as historical
completed-minute simulations because their original live publications do not
exist.

## 1. Inspect all source dates

Run from the `nifty-replay-tools` directory extracted from
`nifty-replay-recovery-1.0.0.zip`:

```bash
/opt/market-workspace-v3/current/.venv/bin/python -B convert_nifty_replays.py plan \
  --core-root /opt/market-workspace-v3/current/core \
  --config /opt/market-workspace-v3/current/config/nifty.json \
  > nifty-replay-plan.json

python3 -m json.tool nifty-replay-plan.json | less
```

An eligible date needs raw index/futures ticks, OI reports, and one unambiguous
NIFTY futures symbol from that date's startup metadata. A date with only minute
or OI files is reported as skipped.

## 2. Build every eligible date

```bash
mkdir -p /home/bankadmin/divergence/rebuilt-nifty-replays

nice -n 10 /opt/market-workspace-v3/current/.venv/bin/python -B convert_nifty_replays.py build \
  --core-root /opt/market-workspace-v3/current/core \
  --config /opt/market-workspace-v3/current/config/nifty.json \
  --output /home/bankadmin/divergence/rebuilt-nifty-replays
```

Each date commits atomically. If interrupted, run the same command again;
verified dates become `UNCHANGED`, failed dates are retried, and the report is
written to `rebuilt-nifty-replays/conversion-report.json`.

If startup metadata is absent, create a reviewed map containing the exact
symbols and add `--futures-map /path/to/nifty-futures-map.json` to `plan` and
`build`:

```json
{
  "2026-08-27": "NSE:NIFTY26AUGFUT",
  "2026-09-10": "NSE:NIFTY26SEPFUT"
}
```

The converter rejects a map that conflicts with available startup metadata.

## 3. Verify and publish

```bash
/opt/market-workspace-v3/current/.venv/bin/python -B convert_nifty_replays.py verify \
  --core-root /opt/market-workspace-v3/current/core \
  --config /opt/market-workspace-v3/current/config/nifty.json \
  --output /home/bankadmin/divergence/rebuilt-nifty-replays

sudo /opt/market-workspace-v3/current/.venv/bin/python -B convert_nifty_replays.py publish \
  --core-root /opt/market-workspace-v3/current/core \
  --config /opt/market-workspace-v3/current/config/nifty.json \
  --output /home/bankadmin/divergence/rebuilt-nifty-replays
```

Publishing adds verified payloads under the NIFTY replay state and does not
restart a service. Refresh the cached NIFTY catalog once after publishing:

```bash
sudo systemctl restart nifty-core.service
curl -fsS 'http://127.0.0.1:8923/api/catalog?profile=nifty-v1062' | python3 -m json.tool
curl -fsS 'http://127.0.0.1:8923/api/catalog?profile=nifty-v200' | python3 -m json.tool
```

The BANKNIFTY core and both GUIs are unaffected by this catalog refresh. Apply
the GUI 3.0.11 package separately so rapid date switching cannot trigger the
old loading race.
