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
