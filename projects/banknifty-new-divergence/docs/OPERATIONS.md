# New Divergence operations

## What runs and what does not

| Mode | Input | Operation | Result | Available now |
| --- | --- | --- | --- | --- |
| Replay | Completed collector `.tar.gz` | Process one selected exchange session once | Verified run plus refreshed replay GUI | Yes |
| GUI service | Generated browser directory | Serve verified replay projections continuously | Browser UI that survives reboot | Yes |
| Replay Codex | Exact replay cursor plus one fixed question | Server rebuilds/hash-verifies the causal prefix, then requests structured text | Read-only diagnostic explanation | Yes (V1.0.22) |
| Cash samples | Completed constituent `market_1m.csv` | Derive two compact 09:45+ parameters | Direct per-date sample files plus refreshed GUI catalog | Yes |
| Nightly context | Completed raw/OI session directories | Version and recompute 1D/2D/3D OI/volume controls and value area | SQLite index plus immutable snapshots | Yes |
| Live | Growing collector raw/OI files | Tail read-only, normalize, checkpoint and publish continuously | Shared-clock snapshot/SSE causal GUI | Yes (V1.0.18) |

V1.0.17 added an operational collector tailer, durable recovery journals and a
continuously updating browser publisher. It remains research-only and fails
closed if source or recovery integrity cannot be verified.

## V1.0.22 causal replay explanations

V1.0.22 enables Codex only in the completed-session replay service. The browser
submits the catalogued session, the exact synchronized cursor receipt, and one
allow-listed question identifier. It cannot submit free-form prompts, market
rows, file paths, or shell instructions. The replay server independently
reconstructs the prefix, refuses a non-exact receipt, verifies every future-data
flag is false, hashes the compact fact bundle, and validates the structured
answer before returning it. The GUI displays a concise Analysis section and an
evidence trace derived from those visible facts; private chain-of-thought is
neither requested nor exposed.

The Codex turn uses `approvalPolicy: never`, a restricted read-only sandbox, a
dedicated worker directory, one in-flight request, rate limits, and a thread
that is deleted after the answer. Any command or tool item interrupts the turn
and the answer is refused. The worker receives no collector or run-root
path. This does not alter replay calculations, the transition ledger, or live
monitoring. Live prompting remains disabled for this incremental release.

Install V1.0.22 as the normal account and keep the existing loopback worker
from V1.0.18 running:

```bash
cd ~/divergence/releases/banknifty-new-divergence-v1.0.22
./install.sh

sudo systemctl start banknifty-new-divergence-codex.service
```

Install the V1.0.22 replay GUI on port 8794. No raw-data replay is required:

```bash
sudo ./install_gui_service.sh \
  --user bankadmin \
  --run-root /home/bankadmin/divergence/sessions \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.22 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12 \
  --host 0.0.0.0 \
  --port 8794 \
  --codex-host 127.0.0.1 \
  --codex-port 4500 \
  --codex-cwd /home/codexuser/banknifty-codex-worker
```

The installer creates or preserves a 256-bit access token and prints the
command used to read it. Check both boundaries:

```bash
curl -s http://127.0.0.1:8794/healthz | python3 -m json.tool
curl -s http://127.0.0.1:8794/api/v1/codex/status | python3 -m json.tool
sudo cat /etc/banknifty-new-divergence-codex-gui.token
```

Open the replay page, paste that token in the per-tab field, choose one fixed
question, and press **Explain visible receipt**. The token is kept only in
`sessionStorage`, so separate browser tabs remain independent. When port 8794
is exposed publicly, restrict the firewall to trusted source addresses or put
the service behind an authenticated HTTPS reverse proxy; plain HTTP does not
protect the token in transit.

## V1.0.18 restricted Codex connectivity checkpoint

V1.0.18 adds only the first Codex integration boundary. A separate service can
run the installed Codex app-server under `codexuser`, bound to loopback. The
live GUI can report whether that socket is reachable. It cannot send prompts,
read production data, modify files, or change divergence calculations.

Install the release and build a fresh live browser directory first:

```bash
cd ~/divergence/releases/banknifty-new-divergence-v1.0.18
./install.sh

.venv/bin/banknifty-new-divergence build-live-browser \
  --output-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.18
```

Locate the Codex executable as `codexuser`; do not guess its path:

```bash
sudo -u codexuser -H sh -lc 'command -v codex && codex --version'
```

Use the absolute path printed by that command:

```bash
sudo ./install_codex_worker.sh \
  --user codexuser \
  --codex-bin /absolute/path/printed/above

sudo systemctl start banknifty-new-divergence-codex.service
sudo systemctl status banknifty-new-divergence-codex.service --no-pager --full
```

Reinstall the live service against the V1.0.18 browser, preserving the existing
collector and authority state roots:

```bash
sudo ./install_live_service.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-live-state-v1.0.17 \
  --browser-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.18 \
  --host 0.0.0.0 \
  --port 8793 \
  --codex-host 127.0.0.1 \
  --codex-port 4500

sudo systemctl restart banknifty-new-divergence-live.service
```

Verify the application and the non-prompting worker boundary:

```bash
curl -s http://127.0.0.1:8793/healthz | python3 -m json.tool
curl -s http://127.0.0.1:8793/api/v1/codex/status | python3 -m json.tool
```

The Codex status must say `REACHABLE_UNVERIFIED`, `prompting_enabled: false`,
and `production_data_access: false`. Stopping the Codex service must change the
status to `OFFLINE` without interrupting the live market monitor.

## Install the nightly 1D/2D/3D context builder

Install its systemd files without enabling or starting the timer:

```bash
sudo ./install_nightly_context.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

Run and verify the first build, then enable the 00:15 IST timer:

```bash
sudo systemctl start banknifty-new-divergence-nightly.service
.venv/bin/banknifty-new-divergence context-status \
  --state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
sudo systemctl enable --now banknifty-new-divergence-nightly.timer
```

See [the nightly context contract](NIGHTLY_CONTEXT.md) for source quality gates,
SQLite tables, immutable snapshots, failure behavior, and cron-compatible use.

## Install the replay GUI service

Run the package installer first as the normal project owner:

```bash
./install.sh
```

Install and start the GUI service:

```bash
sudo ./install_gui_service.sh --host 127.0.0.1 --port 8793
```

The V1.0.22 defaults, derived from the service account home, are:

- Sessions: `/home/bankadmin/divergence/sessions`
- Browser: `/home/bankadmin/divergence/new-divergence-gui-v1.0.22`
- Inventory context: `/home/bankadmin/divergence/new-divergence-context-v1.0.12`
- Service: `banknifty-new-divergence-gui.service`

The installer derives the service account from the `sudo` caller instead of
hard-coding `bankadmin`. Override paths with `--run-root`, `--browser-root`,
and `--context-state-root`.

## Install the V1.0.16 cash-sample/GUI refresh service

The generator is an additive read-only consumer of the collector minute tree.
It does not patch or restart the collector:

```bash
sudo ./install_sample_generator.sh \
  --user bankadmin \
  --collector-root /opt/banknifty-collector \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /home/bankadmin/divergence/sessions \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.16 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12

sudo systemctl start banknifty-new-divergence-samples.service
sudo systemctl enable --now banknifty-new-divergence-samples.timer
```

The first start backfills every date with a completed `minute/YYYY-MM-DD/market_1m.csv`.
Later starts are source-hash idempotent. The timer starts daily at 15:40 IST,
including special trading Saturdays, and retries five minutes later if the
collector minute file is still active. See
[the cash-sample contract](CASH_SAMPLES.md).

Binding to `127.0.0.1` is the safe default for an authenticated reverse proxy.
For temporary direct-IP access, use `--host 0.0.0.0`; the application itself
does not authenticate users, so firewall restriction is required.

## Publish one replay session

Run this as the normal project owner, never with `sudo`:

```bash
./publish_replay.sh \
  --archive "/absolute/path/complete_20_08.tar(1).gz" \
  --session 2026-08-20 \
  --run-root /home/bankadmin/divergence/sessions \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.16 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12 \
  --finalize
```

The publisher performs these operations in order:

1. Streams the selected archive session without extracting the raw tree.
2. Writes a new session to the append-only run root.
3. Verifies every run artifact and the hash-chained transition ledger.
4. Rebuilds the calculation-free browser projection.

An already published session is refused rather than overwritten. A running GUI
service reads the refreshed files automatically; no service restart is needed.

The run directory is directly
`/home/bankadmin/divergence/sessions/YYYY-MM-DD`; V1.0.16 never creates a
nested `sessions/sessions` tree. If the sample generator created that date
first, replay atomically preserves its two verified sample files while adding
the divergence run artifacts.

## V1.0.16 current deployment

V1.0.16 retains the V1.0.15 market-history and 09:45 bar boundaries and adds
persistent, independent frame-visibility switches. Hidden frames leave no
reserved layout space, and hiding every right-rail frame expands the left
column to full width. The verified V1.0.12 nightly context root remains the
context calculation authority. Old release run roots are not scanned or tested
by this deployment.

```bash
cd ~/divergence/releases/banknifty-new-divergence-v1.0.16
./install.sh

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/sessions \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.16 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

Both inventory families are included by default. To omit one family from the
published browser payload, add `--disable-oi-vpoc` or
`--disable-volume-profile` to `install_gui_service.sh`, `publish_replay.sh`, or
`install_sample_generator.sh`. When published, the replay page still provides
interactive flags for ID/1D/2D/3D, Futures/CE/PE OI-VPOC, and volume
VPOC/VAH/VAL. Every scope can be switched off; those switches affect rendering
only. A V1.0.13-or-later replay is
required to populate ID Futures volume; older verified runs still provide ID
OI and all eligible frozen prior levels.

The remaining version sections below are historical migration notes only; they
are not V1.0.16 paths or acceptance targets.

## Upgrade to the V1.0.4 gap-safe RED-zone methodology

V1.0.4 does not rewrite or relabel an older immutable run. Older sessions are
shown as `Replay required`. Install the package as the normal project owner and
replay source data into a new versioned run root:

```bash
./install.sh

./publish_replay.sh \
  --archive "/absolute/path/collector.tar.gz" \
  --session YYYY-MM-DD \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.4 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.4 \
  --finalize

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 127.0.0.1 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.4 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.4
```

The pre-V1.0.4 run and browser directories remain unchanged for audit. Binding
to `0.0.0.0` instead requires the firewall/reverse-proxy precautions described
above.

## Upgrade to the V1.0.5 stable-chart GUI

V1.0.5 changes only browser sizing and deployment identity. It keeps the
V1.0.4 gap-safe methodology, so a verified V1.0.4 run root can be reused. Build
the GUI into a new directory and point the service at it:

```bash
./install.sh

.venv/bin/banknifty-new-divergence build-browser \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.4 \
  --output-root /home/bankadmin/divergence/new-divergence-gui-v1.0.5

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.4 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.5
```

If the catalog marks that run root `Replay required`, it was produced before
the V1.0.4 gap-safe methodology and must be replayed using the V1.0.4 upgrade
procedure above. After installation, `/healthz` must report runtime and browser
runtime `1.0.5` plus methodology
`NEW_DIVERGENCE_V1_1_GAP_SAFE_HORIZONS`.

## Upgrade to the V1.0.6 aligned Futures OI GUI

V1.0.6 changes only the browser projection and GUI. It keeps the V1.0.4
gap-safe methodology, so the existing compatible run root can be reused and no
RED-zone replay is required. Build a fresh browser directory and repoint the
service:

```bash
./install.sh

.venv/bin/banknifty-new-divergence build-browser \
  --run-root /home/bankadmin/divergence/banknifty-new-divergence-v1.0.4 \
  --output-root /home/bankadmin/divergence/new-divergence-gui-v1.0.6

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/banknifty-new-divergence-v1.0.4 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.6
```

The new OI panel is populated from `futures_oi` records already retained in
the verified evidence snapshots. If the compatible run was originally made
from an archive without OI files, the panel explicitly reports that OI was not
retained; only that case requires replaying a complete raw-plus-OI archive.

## Upgrade to the V1.0.7 combined market/OI panel

V1.0.7 corrects only the V1.0.6 panel arrangement. Index, Futures, absolute OI,
and ΔOI now share the first panel; basis/divergence remains the second panel.
The compatible V1.0.4 run root is reused without replay:

```bash
./install.sh

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/banknifty-new-divergence-v1.0.4 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.7
```

## Upgrade to the V1.0.8 vertical CE/PE strike-OI rail

V1.0.8 uses the full browser width, keeps the combined market/OI and basis
charts in the left column, and places CE above PE in a right-side strike-OI
rail. RED/GREEN classification is unchanged. Existing compatible runs still
open, but runs made before V1.0.8 do not contain the dedicated per-strike
artifact and will show `Replay required` in both strike panels.

Replay the complete raw-plus-OI archive once into a new immutable run root,
then install the service against that root:

```bash
./install.sh

.venv/bin/banknifty-new-divergence replay-archive \
  --archive /absolute/path/complete-session.tar.gz \
  --session YYYY-MM-DD \
  --finalize \
  --output-root /home/bankadmin/divergence/new-divergence-runs-v1.0.8

.venv/bin/banknifty-new-divergence verify-run \
  --run-directory /home/bankadmin/divergence/new-divergence-runs-v1.0.8/sessions/YYYY-MM-DD

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.8 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.8
```

`option_strike_oi.jsonl` stores one compact selected-expiry row per contract
and chain receipt. The browser shows only records visible at the current replay
clock. A stale receipt gap resets ΔOI instead of connecting unrelated changes.

## Upgrade to the V1.0.9 fixed day-open strike-flow panels

V1.0.9 adds four vertically stacked panels below the basis chart: CE signed
ΔOI, PE signed ΔOI, CE incremental volume, and PE incremental volume. Strike
1 is the nearest common listed strike to the first valid BankNifty Index tick
within 60 seconds of the 09:15 IST open; an exact tie chooses the lower strike.
CE strikes 2–4 are the next three higher listed strikes and PE strikes 2–4 are
the next three lower listed strikes. The eight contracts are fixed for the
whole session.

Runs created before V1.0.9 do not retain both the hashed day-open reference and
option volume. Replay the complete raw-plus-OI collector archive into a new
immutable root:

```bash
./install.sh

.venv/bin/banknifty-new-divergence replay-archive \
  --archive /absolute/path/complete-session.tar.gz \
  --session YYYY-MM-DD \
  --finalize \
  --output-root /home/bankadmin/divergence/new-divergence-runs-v1.0.9

.venv/bin/banknifty-new-divergence verify-run \
  --run-directory /home/bankadmin/divergence/new-divergence-runs-v1.0.9/sessions/YYYY-MM-DD

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.9 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.9
```

The replay fails closed when the Index day-open receipt is missing or more than
60 seconds late. Negative cumulative-volume differences are treated as feed
resets and are not rendered as negative traded volume. This visualization path
does not alter RED/GREEN classification or transition publication.

## Upgrade to the V1.0.10 09:45-close reference and OI snapshots

V1.0.10 uses the last fresh synchronized BankNifty Index receipt at or before
09:45:00 IST as the fixed ATM reference. The first complete option-chain receipt
after 09:45 becomes a baseline; subsequent changes alone enter the four lower
flow panels. The CE/PE right rail now shows current absolute OI bars, printed
signed ΔOI, and a labelled current BN Index line instead of overlapping
full-session bubbles. All CE/PE strike rows before 09:45 are excluded from the
browser projection and prefix API; the main market, Futures OI, basis, and
divergence replay remains full-session.

A verified V1.0.9 run already contains all required basis, per-strike OI, and
volume rows. Reuse it without replaying the raw archive:

```bash
./install.sh

.venv/bin/banknifty-new-divergence verify-run \
  --run-directory /home/bankadmin/divergence/new-divergence-runs-v1.0.9/sessions/YYYY-MM-DD

.venv/bin/banknifty-new-divergence build-browser \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.9 \
  --output-root /home/bankadmin/divergence/new-divergence-gui-v1.0.10

sudo ./install_gui_service.sh \
  --user bankadmin \
  --host 0.0.0.0 \
  --port 8793 \
  --run-root /home/bankadmin/divergence/new-divergence-runs-v1.0.9 \
  --browser-root /home/bankadmin/divergence/new-divergence-gui-v1.0.10
```

Only runs lacking the V1.0.9 per-strike volume artifact require another
raw-plus-OI replay. The divergence engine, transition ledger, and
`NEW_DIVERGENCE_V1_1_GAP_SAFE_HORIZONS` methodology are unchanged.

## Check operation

```bash
curl http://127.0.0.1:8793/healthz
sudo systemctl status banknifty-new-divergence-gui.service --no-pager
sudo journalctl -u banknifty-new-divergence-gui.service -n 100 --no-pager
```

Expected health response:

```json
{"browser_runtime_version":"1.0.16","mode":"read-only-research","required_methodology":"NEW_DIVERGENCE_V1_1_GAP_SAFE_HORIZONS","runtime_version":"1.0.16","status":"ok"}
```

To stop the GUI without deleting any replay data:

```bash
sudo systemctl disable --now banknifty-new-divergence-gui.service
```

## Replay versus live

Replay has a finite input archive and creates an immutable result for a known
session. The GUI is a read-only player over that result. Live operation instead
needs a long-running process that follows the collector's active JSONL files,
persists causal engine checkpoints, survives log rotation and restarts, and
publishes browser-safe snapshots without exposing future records. That process
is the remaining implementation boundary; the GUI service in this release does
not manufacture live data.
## V1.0.17 live monitoring

Live monitoring is a separate read-only service on port `8794`; replay remains
on `8793`. One server authority tails complete collector JSONL records, applies
the same normalization and divergence engine as replay, and publishes a
monotonic sequence to every browser through snapshot plus SSE.

Build the live assets as `bankadmin`:

```bash
.venv/bin/banknifty-new-divergence build-live-browser \
  --output-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.17
```

Install the service without starting it:

```bash
sudo ./install_live_service.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-live-state-v1.0.17 \
  --browser-root /home/bankadmin/divergence/new-divergence-live-gui-v1.0.17 \
  --host 0.0.0.0 \
  --port 8794
```

Start and verify explicitly:

```bash
sudo systemctl start banknifty-new-divergence-live.service
curl -s http://127.0.0.1:8794/healthz | python3 -m json.tool
```

The service selects the current Asia/Kolkata date at process start. Restart it
before the next session. Collector storage is mounted read-only by systemd;
only the live state root is writable. A partial line is never consumed. Source
rotation/truncation, an invalid journal, or an event older than the committed
watermark changes health to `LIVE_RECOVERY_REQUIRED` and stops publication.

Every browser receives the same authority sequence. Pause and frame layout are
per window; a short pause buffers at most 2,000 publications, while resuming
after overflow obtains a fresh verified snapshot. `Esc` restores a maximized
frame.
