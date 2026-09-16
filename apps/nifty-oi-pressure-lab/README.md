# NIFTY CE/PE OI Pressure Lab — GUI prototype v0.1.2

Standalone, research-only replay GUI. It is independent of the Market Workspace V3 core/GUI services; installing or running this code does not modify either production engine.

## Features

- Expiry and normal-session replay, with a signed OI regime score (-100 to +100).
- Expiry confirmation layers: fixed-four 1m, dynamic near-ATM-four 5m, whole-chain 10m.
- Normal-session bullish/bearish research layers.
- Active signal and **all triggering layer names inside the main signal frame**, including simultaneous multi-layer confirmations.
- Price/OI disagreement and prototype persistence/reset states.
- Slower playback (0.22–4 seconds per market minute), previous/next buttons, keyboard arrows, automatic pause when score changes.
- Historical future returns are displayed **for retrospective research only**; they do not calculate the current score.

## Clone and run

```bash
git clone --branch feature/nifty-oi-pressure-gui-v0.1.2 https://github.com/krish4u1908/codex_market_profile.git
cd codex_market_profile/apps/nifty-oi-pressure-lab
```

**Data is intentionally not committed to this public repository.** Copy the following two generated research timelines from your previously downloaded `nifty-oi-pressure-gui-prototype-v0.1.2.zip` (folder `data/`) into this checkout's `data/` directory:

```text
data/expiry_oi_pressure_timeline.csv
data/normal_oi_pressure_timeline.csv
```

Optionally copy `data/expiry_ensemble_events.csv` and `data/oi_pressure_research_report.md` for your local research records. The server reads the two timeline CSVs at startup and cannot operate without them; the clone **is code-only, not a self-contained data package**.

```bash
python3 server.py --host 127.0.0.1 --port 8920
```

For intentional remote viewing on your VPS, bind to `0.0.0.0` and ensure access to port 8920 is appropriately restricted. `Ctrl+C` stops the server. No systemd service or background process is created. No pip packages are required.

## Research limitations

Scores/timelines are frozen exploratory research from a small session sample. The prototype loads precomputed scores; it is **not** a live calculation engine or validated trading system. The observed 10/10 strong expiry result is not a true 100% probability; the rules were developed using these sessions and need fresh forward validation. Option OI decreases alone cannot identify short covering versus long liquidation without option premium/trade information. Do not interpret this GUI as trade instructions.

## Version history

v0.1.2: tags active signal and individual triggering layers in the main signal frame. v0.1.1: playback speed selector and pause/step controls. Signal scores and underlying data remain unchanged.