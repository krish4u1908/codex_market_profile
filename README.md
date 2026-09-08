# BankNifty Market Profiler

Recoverable source baseline for verified BankNifty raw-market synchronization, 1D/2D/3D/intraday inventory maintenance, divergence detection, and causal lifecycle profiling.

**LIVE MARKET-PROFILING DIAGNOSTIC — NOT A BUY/SELL SIGNAL**

The repository contains source and small deterministic fixtures only. Raw market data remains external and read-only.

```bash
python scripts/run_external_validation.py \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /explicit/output/path \
  --mode stream
```

## V3 graphical workspace

The [shared BANKNIFTY/NIFTY workspace](apps/market-workspace-v3/README.md) supports the v1.0.62 and independent v2.0.0 session contracts. It includes responsive charts, replay, retained OI-VPOC levels, cumulative OI bars, independent summaries and V2 volume-climax markers for recorded ratios strictly above 4×. Existing engine semantics remain unchanged.

See the GUI package for setup, source-data import and read-only V2 database export instructions. Large archives and market recordings remain external.

## Two shared instrument cores

The [V3 core runtime](apps/market-core-v3/README.md) consolidates BANKNIFTY and NIFTY into one continuously running authority per instrument. Two separate GUI services offer v1.0.62/V2.0.0 Live and Replay views. Frozen calculation source, original publication clocks and existing collector inputs are preserved.

The [migration installer](apps/market-core-v3/DEPLOYMENT.md) copies authoritative state, imports retained replays, verifies old services are stopped, and installs four services with rollback instructions. It preserves old releases, collectors and authentication. VPS activation and market-hour validation remain operational steps; source submission does not deploy it.
