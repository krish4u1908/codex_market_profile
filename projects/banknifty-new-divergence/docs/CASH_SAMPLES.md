# Cash-participation sample contract (introduced in V1.0.11)

V1.0.11 adds a compact, date-discovered sample generator alongside the
existing production collector. It reads completed one-minute files; it does
not modify collector code, configuration, WebSocket subscriptions, output, or
running services.

## Fixed contract

The generator publishes exactly two research parameters from 09:45 IST:

| Parameter | Definition | Unit |
| --- | --- | --- |
| `cash_breadth` | `100 × (advancing − declining) / 14`, using an equal vote for each BankNifty constituent versus its frozen 09:45 reference | percent net constituents |
| `index_participant_volume` | Unweighted sum of the 14 constituents' completed one-minute traded-share volume | shares per minute |

The 09:45 constituent reference is each constituent's valid 09:44 minute-bucket
close—the close of the 09:15–09:45 warm-up window. A missing 09:44 reference
does not fall back to an older price; breadth remains `null` until the issue is
corrected at source.
The first output bucket is 09:45–09:46. It is published no earlier than the
bucket end plus the collector's finalize delay.

Coverage counts and the row `status` are audit metadata, not additional
parameters. If any required constituent is absent, the affected parameter is
`null`; the generator never rescales partial coverage. Both parameters have
`production_weight: 0`, are marked `divergence_engine_input: false`, and do not
change RED/GREEN classification.

Generation refuses non-minute-aligned or cross-session rows and re-hashes the
source after derivation. A file that changes during reading is retried; a mixed
or partially written snapshot is never published as valid.

The volume definition follows the documented
[FYERS index-volume convention](https://support.fyers.in/portal/en/kb/articles/how-is-the-volume-for-indices-calculated-in-fyers):
sum constituent traded shares without index weighting. It is not rupee
turnover, Futures volume, or a weighted index calculation.

## Source and output layout

The source remains read-only:

```text
/opt/banknifty-collector/data-prod-v4/
  metadata/startup_*.json
  minute/YYYY-MM-DD/market_1m.csv
```

Every date containing `market_1m.csv` is discovered automatically. The direct
V1.0.11 session root is:

```text
/home/bankadmin/divergence/sessions/
  catalog.json
  YYYY-MM-DD/
    cash_participation_1m.jsonl
    sample_manifest.json
    ...verified replay artifacts when that date has been replayed...
```

There is no nested `sessions/sessions` directory. A sample-only date is visible
in the catalog but is not a playable divergence replay until its raw-plus-OI
archive is replayed into the same root. Replay atomically promotes the existing
sample-only directory and preserves the verified sample files.

An August 20 production file generated 330 rows (09:45 through 15:14), about
103 KB of JSONL plus a 2 KB manifest. Thirty such sessions occupy roughly
3.2 MB before filesystem overhead.

## Install beside the collector

Install the current release first as `bankadmin`:

```bash
cd ~/divergence/releases/banknifty-new-divergence-v1.0.14
./install.sh
```

Then install the generator entry point under `/opt/banknifty-collector/app`,
its runner under `/opt/banknifty-collector/bin`, and the systemd units:

```bash
sudo ./install_sample_generator.sh \
  --user bankadmin \
  --collector-root /opt/banknifty-collector \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /home/bankadmin/divergence/sessions \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.14 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

The installer does not enable the timer by default. Run the historical
backfill once, inspect it, then enable the weekday timer:

```bash
sudo systemctl start banknifty-new-divergence-samples.service
sudo journalctl -u banknifty-new-divergence-samples.service -n 100 --no-pager

sudo systemctl enable --now banknifty-new-divergence-samples.timer
systemctl list-timers banknifty-new-divergence-samples.timer
```

The timer starts at 15:40 Asia/Kolkata every calendar day, including special
Saturday trading sessions, and is persistent across a reboot. If the collector
is still writing its final derivatives minute, the
generator returns `SOURCE_NOT_STABLE`; systemd retries five minutes later
instead of silently skipping that date. Each successful run discovers all
minute dates, regenerates only missing or source-changed samples, verifies
hashes, refreshes `catalog.json`, and rebuilds the V1.0.14 browser assets. The
sample generator contract remains V1.0.11, so already verified sample bundles
do not need regeneration solely because the GUI runtime advanced.
Re-running it with unchanged sources returns `UNCHANGED`.

Manual generation is also available:

```bash
.venv/bin/banknifty-new-divergence generate-samples \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /home/bankadmin/divergence/sessions
```

Use a repeated `--session YYYY-MM-DD` to limit a manual run. `--force` is for
an intentional rebuild; normal daily use should remain hash-idempotent.
