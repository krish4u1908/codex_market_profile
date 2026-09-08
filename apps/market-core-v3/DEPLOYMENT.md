# Install the two-core market workspace

This package targets the source and service layout captured from `srv1913330`.
It has not been executed on the VPS from this workspace. Keep the existing
source, data and state until the replacement has passed a live market session.

## Result

| Component | Location |
| --- | --- |
| Versioned code and isolated Python environment | `/opt/market-workspace-v3/releases/3.0.0-<timestamp>/` |
| Current release | `/opt/market-workspace-v3/current` |
| BANKNIFTY state | `/var/lib/market-workspace-v3/banknifty/` |
| NIFTY state | `/var/lib/market-workspace-v3/nifty/` |
| Installation and rollback record | `/opt/market-workspace-v3/install-records/<timestamp>.json` |

There are exactly four new services: `banknifty-core`, `nifty-core`,
`banknifty-gui`, `nifty-gui`. Each GUI offers v1.0.62 and V2.0.0, Live and Replay.
Core APIs listen on loopback ports 8922/8923. GUIs listen on 8920/8921.

## Before installing

The installer needs Python 3.11+ with `venv`, `systemctl`, `runuser`, `ss`, the
existing `bankadmin` account and `marketdata` group. The captured VPS uses Python
3.12. The isolated environment installs the two pinned dependencies with pip;
Node is not needed when using this prebuilt ZIP. Allow disk space for a copy of
both existing V2 state trees, prepared replay imports and future recordings.

It reads the collector directories; no broker credentials are needed. It copies:

| Instrument | Existing authoritative state |
| --- | --- |
| BANKNIFTY | `/var/lib/banknifty-v200-independent` |
| NIFTY | `/home/codexuser/nifty-upgrade-bundle-v1062-v200/runtime/v200-independent` |

The NIFTY path is the actual captured user-service path. No `/var/lib/nifty-*`
state path is assumed. Collector paths, replay roots and the BANKNIFTY prior
context path are recorded in `core/deploy/deployment.json` inside the ZIP.

## Commands

Copy `market-workspace-v3.zip` to `/home/bankadmin` on the VPS, then:

```sh
cd /home/bankadmin
unzip market-workspace-v3.zip
cd market-workspace-v3
sudo python3 core/deploy/install.py check
```

`check` is read-only. If it reports active/enabled old services, and you have not
already stopped them with the supplied cleanup helper, run:

```sh
sudo python3 core/deploy/market_cleanup.py stop-old
sudo python3 core/deploy/install.py check
```

The helper captures source and a `restore.json`, then stops/disables the fixed
old GUI, analytics and rollover/nightly/sample unit list. It addresses NIFTY's
services through the existing **codexuser user manager**. Collectors, FYERS
authentication/bot, collector cron, Codex worker, SSH, nginx and user managers
are preserved. It does not delete source, state, research or market data.
If cleanup was already done, keep the original restore record; do not repeat
cleanup merely to obtain a newer record.

When `check` has an empty `problems` list:

```sh
sudo python3 core/deploy/install.py install
sudo python3 core/deploy/install.py status
```

You can add `--cleanup-record /home/bankadmin/market-cleanup-<timestamp>/restore.json`
to `install` to retain the exact former-service restore path in its record.
Replace the timestamp with the path printed by the earlier cleanup helper.

Installation creates an isolated Python environment, copies and verifies the
authoritative state, imports replay, writes four units, then starts and enables
them. Old journals remain in place. SQLite backup includes committed WAL data.
Links/special files in old state are rejected for inspection. Existing new
state/unit names are never overwritten. Skipped historical replay imports are
listed in each new state's `migration.json`.

Open BANKNIFTY at port 8920 and NIFTY at port 8921 on your VPS address. Select the
version in the GUI. Existing port/firewall/reverse-proxy configuration is not
rewritten by this installer; the core ports stay private.

## Verify during the next live session

```sh
systemctl is-active banknifty-core nifty-core banknifty-gui nifty-gui
curl -s http://127.0.0.1:8922/health
curl -s http://127.0.0.1:8923/health
```

Check each instrument's session, price age, `authority_instances:1` after
metadata loads, and absence of recovery/V2-context errors. Initial history
recovery can take time. Before the first receipt or outside a current session,
waiting is expected. BANKNIFTY and NIFTY keep their own metadata and futures
contracts; missing contracts are not guessed.

Open both version views and use Market Summary, Options and Replay while prices
update. A summary stays attached to its requested snapshot. Replay reads saved
publications and does not move the live core clock. Confirm VPOC levels, totals,
cumulative flows and ratio labels against the retained session.

To verify GUI independence, note the core PIDs, restart only the GUIs, then
confirm the core PIDs and receipt sequence continue:

```sh
systemctl show banknifty-core nifty-core --property=MainPID
sudo systemctl restart banknifty-gui nifty-gui
systemctl show banknifty-core nifty-core --property=MainPID
```

No new rollover timers are needed. Each core changes session on the IST date
boundary and waits for matching metadata. Prior-context maintenance runs inside
the core overnight. NIFTY's old first-observed cash/VIX records are copied; values
not present in its collector remain unavailable.

## Rollback or failed installation

The installer prints its record path before making changes. If activation fails,
it attempts to stop the four new services and records any stop failure. If
preparation fails, it leaves its copied files and progress record for inspection.
It does not erase incomplete copies or overwrite them on a later run.

To stop/disable the replacements, use the actual record path:

```sh
sudo python3 core/deploy/install.py rollback --record /opt/market-workspace-v3/install-records/<timestamp>.json
```

Rollback retains the new release, configuration, unit files and state. It does
not automatically start the former GUIs. To restore them after replacements
are stopped, run the cleanup helper with the **original** restore record:

```sh
sudo python3 core/deploy/market_cleanup.py restore /home/bankadmin/market-cleanup-<timestamp>/restore.json
```

Use only paths that exist on the VPS. A restored old engine recovers using its
original state and collectors; do not copy new publication files back into old
state. Do not start old and new authorities together. Permanent removal of old
release directories is a later task after live verification.
