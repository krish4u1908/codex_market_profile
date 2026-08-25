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

