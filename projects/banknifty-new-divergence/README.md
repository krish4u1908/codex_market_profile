# BankNifty New Divergence

Causal, date-agnostic divergence replay and shadow-live diagnostic built on a
recoverable R6D source baseline. Replay and live records enter one typed event
contract and one state machine. The active Futures contract and available
exchange sessions are discovered from input metadata and verified run outputs;
neither dates nor contract years are embedded in the new runtime.

**LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

**Operational status:** completed-session replay, the persistent replay GUI,
versioned nightly 1D/2D/3D context, and checkpointed live monitoring are
available. V1.0.23 adds replay-equivalent live inventory projection and keeps
centralized, durable commentary shared by replay and
live browsers, with exact inventory shifts, transparent market-profile analysis,
Codex explanation, and a separately labelled experimental outlook. It builds on
the replay-only exact-cursor Codex boundary introduced in V1.0.19 through a
restricted local worker. Live Codex prompting remains disabled.
V1.0.24 corrects the live frame presentation without changing calculations,
commentary generation, market-data inputs, or service boundaries.
V1.0.25 aligns live monitoring with the replay workspace and explicitly
separates browser connectivity from receipt-feed freshness.
V1.0.26 corrects the remaining desktop workspace flow by keeping shifts in the
primary column rather than below the height of the snapshot rail.
V1.0.27 bounds mobile/browser bootstrap and background polling payloads and
shows transparent inventory analysis separately from Codex interpretation.
V1.0.28 adds the same auditable four-scenario directional backend contract to
replay and live. It classifies confirmed/potential long buildup, short buildup,
long trap, short trap or NO_EDGE without using option-premium assumptions, and
keeps the live backend decision independent of Codex latency.
V1.0.29 consolidates Index, Futures, basis, Futures OI and signed Futures ΔOI
onto one synchronized long market canvas in replay and live. Basis retains its
own scale in an adaptive internal lane: it occupies a verified clear corridor
between Index and Futures when one exists across the visible prefix, otherwise
it moves to a reserved top lane. Futures OI and ΔOI retain an independent
bottom participation scale. These are display-only changes.
V1.0.30 gives that adaptive basis lane a fixed 180-pixel visual budget and four
horizontal basis-scale guides. The complete lane moves between Index/Futures
only when the full height fits safely; otherwise it moves to the top without
compressing the oscillation. The combined replay/live canvas is 680 pixels
high, while calculations and data contracts remain unchanged.
V1.0.31 restores the live confirmed-divergence layers already present in
replay. Live projects zones from the complete authoritative transition ledger,
shows green/red confirmed spans and start lines with dashed terminal markers,
and updates them from new publications. Candidate states remain uncoloured.
V1.0.32 follows the compact participation overlay: active BankNifty Futures OI
is an amber linear trace over the price plot, while positive and negative ΔOI
are green/red bars around an internal lower baseline. These participation
series have independent normalization and never alter the price scale.
V1.0.35 changes only the experimental short-trap path. A 2.5x Futures-volume
climax creates a non-directional candidate; it cannot assign BUY/SELL. The
classifier reports `CONFIRMED_SHORT_TRAP`/`UP` only after later-minute price,
Futures OI, basis, and PE-control confirmation. Exact causal UTC and IST
timestamps are returned in scenario metrics. See
[`docs/SHORT_TRAP_V1035.md`](docs/SHORT_TRAP_V1035.md) and
[`docs/DEPLOYMENT_V1035.md`](docs/DEPLOYMENT_V1035.md).

The runtime is fixed at `production_weight: 0`. It publishes candidates at
their receipt time, confirms them only after later persistence evidence becomes
visible, and keeps retrospective outcomes in a separate command and file.
Horizon references are gap-safe: after missing synchronized basis data, 1m,
3m, and 5m evidence rebuild independently and at least two valid horizons are
required before a coloured divergence can exist. Replay also projects retained
Futures OI as a linear yellow trace with green/red ΔOI bars on the same
receipt-time x-domain as the main price chart. The full-width replay workspace
places current CE and PE absolute-OI snapshots in a vertical right rail. Their
horizontal bars share one CE/PE scale, print absolute OI and latest signed ΔOI,
and include a labelled current BankNifty Index reference line. Four additional
panels beneath the basis chart show signed ΔOI and incremental traded volume for
fixed CE/PE strikes 1–4. Strike 1 is the nearest common listed strike to the
last fresh synchronized BankNifty Index receipt at or before 09:45:00 IST (the
lower strike wins an exact tie). CE strikes 2–4 are the next three higher
listed strikes; PE strikes 2–4 are the next three lower listed strikes. Those
eight contracts are frozen after 09:45 and every flow panel uses the main
chart's visible receipt-time domain. The CE/PE projection itself has a hard
09:45 boundary: no earlier strike row, OI delta, volume delta, snapshot, or
prefix response is exposed. V1.0.15 restores synchronized Index/Futures,
absolute Futures OI, basis, states, transitions, and confirmed zones from the
first session observation. Futures ΔOI bars and every CE/PE OI/volume bar keep
a fresh 09:45 baseline so opening accumulation cannot dominate later bars.

V1.0.11 also derives exactly two compact parameters from the collector's
completed constituent minute file: equal-vote `cash_breadth` versus the frozen
09:45 reference and unweighted `index_participant_volume`. They are stored
under `/home/bankadmin/divergence/sessions/YYYY-MM-DD`, carry source hashes and
coverage metadata, and never enter the RED/GREEN engine.

V1.0.12 overlays verified prior-session inventory on the same BankNifty Index
price scale. It provides signed Futures/CE/PE OI-VPOCs and a
BankNifty-reference Futures-volume VPOC with a contiguous 70% VAH/VAL. The
1D/2D/3D scopes and each display family are switchable. These frozen levels are
browser context only and never enter divergence identification.

V1.0.13 adds a developing `ID (09:45→cursor)` scope beside those frozen prior
scopes. Intraday OI-VPOC and Futures-volume VPOC/VAH/VAL advance only when the
replay cursor reaches their source receipt. Every level is labelled directly
on the price chart, and both OI and volume families have effective display
masters. The existing V1.0.12 nightly-context state is intentionally reusable;
a V1.0.13 raw-plus-OI replay is needed only to retain the new Futures-volume
counter for the ID volume profile.

V1.0.14 makes every display scope independently switchable, including allowing
all scopes to be off. It also explains beside the volume controls whether the
selected scope is available, disabled at build time, or requires a V1.0.13+
raw replay. This is a GUI-only correction; the V1.0.13 retained volume artifact
and V1.0.12 nightly-context calculation remain authoritative.

V1.0.15 restores the synchronized Index, Futures, basis, state, transition,
confirmed-zone, and absolute Futures-OI history from the first session
observation. Only change bars and 09:45 analytical families remain baselined at
09:45: Futures ΔOI, CE/PE ΔOI, CE/PE incremental volume, cash participation,
and ID inventory. This prevents opening bars from dominating scale without
hiding the underlying market history.

V1.0.16 adds persistent independent visibility switches for every major replay
frame: market, basis, four CE/PE OI/volume flows, two OI snapshots, and the
inventory list. Hidden frames leave no reserved space; hiding the complete
right rail expands the remaining charts to full width. These controls affect
rendering only.

V1.0.22 replaces per-tab replay prompting with one server-side commentary
record. The server
reconstructs and hashes the exact causal prefix, accepts no free-form prompt,
and returns only validated structured diagnostic text. Requests require a
per-tab access token and run through a loopback worker with approvals disabled
and a restricted read-only sandbox. No replay, engine, or transition changes
are involved.

## Installation

Python 3.12 or newer is required. Extract the complete release archive before
running an installer; do not run an installer from inside the compressed file.

Linux or macOS:

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
banknifty-new-divergence --help
```

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\.venv\Scripts\Activate.ps1
banknifty-new-divergence --help
```

Both installers create or reuse `.venv`, install the project and its pinned
dependencies, and run a CLI smoke check. They do not start a replay, server,
service, or background process. Set `PYTHON_BIN` on Linux/macOS or pass
`-Python` on Windows to select a specific Python installation.

Install the read-only replay GUI as a persistent Linux `systemd` service:

```bash
sudo ./install_gui_service.sh --host 127.0.0.1 --port 8793
```

Install the collector-side sample generator and its 15:40 IST daily timer
files (install-only by default):

```bash
sudo ./install_sample_generator.sh \
  --user bankadmin \
  --collector-root /opt/banknifty-collector \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /home/bankadmin/divergence/sessions
```

See [the cash-sample contract](docs/CASH_SAMPLES.md) before enabling the timer.

Publish a completed collector session into that GUI:

```bash
./publish_replay.sh \
  --archive "/absolute/path/collector.tar.gz" \
  --session YYYY-MM-DD \
  --finalize
```

See [the operations guide](docs/OPERATIONS.md) for service status, logs,
direct-IP security, replay publication, and the explicit current live-mode
boundary.

Install the nightly context service and timer files without starting them:

```bash
sudo ./install_nightly_context.sh \
  --user bankadmin \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

After a manual first-run check, enable the 00:15 IST timer. See
[the nightly context guide](docs/NIGHTLY_CONTEXT.md) for the exact quality,
versioning, SQLite, immutable-snapshot, and failure contracts.

## Quick verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python -m pytest -q -p no:cacheprovider tests/new_divergence
```

## Replay a collector archive without extracting it

```bash
PYTHONPATH=src python -m banknifty_profiler.new_divergence replay-archive \
  --archive /explicit/read-only/collector.tar.gz \
  --session YYYY-MM-DD \
  --output-root /home/bankadmin/divergence/sessions
```

The command streams matching tar members, retains only normalized BankNifty
records, externally receipt-sorts bounded chunks, and atomically publishes the
completed session. Existing session output is refused rather than overwritten.

Build the calculation-free replay browser after one or more runs:

```bash
PYTHONPATH=src python -m banknifty_profiler.new_divergence build-browser \
  --run-root /home/bankadmin/divergence/sessions \
  --output-root /home/bankadmin/divergence/new-divergence-gui-v1.0.16 \
  --context-state-root /home/bankadmin/divergence/new-divergence-context-v1.0.12
```

No server is started by replay or browser construction. Local serving is a
separate explicit command and requires `--acknowledge-research-only`.

```bash
PYTHONPATH=src python -m banknifty_profiler.new_divergence verify-run \
  --run-directory /home/bankadmin/divergence/sessions/YYYY-MM-DD
```

See [the New Divergence contract](docs/NEW_DIVERGENCE_CONTRACT.md) for clocks,
states, data flow, output boundaries, and limitations.

## Frozen baseline

The repository contains source and small deterministic fixtures only. Raw market data remains external and read-only.

```bash
python scripts/run_external_validation.py \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /explicit/output/path \
  --mode stream
```

The exact recovered baseline is tagged
`baseline-r6d-offline-gui-65ae2c5`. New Divergence code lives under
`banknifty_profiler.new_divergence`; the tag retains the original R6D behavior
and fixed-date browser for audit.
