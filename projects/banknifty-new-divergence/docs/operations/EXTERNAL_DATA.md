# External Data Interface

Full-data validation accepts explicit, read-only external input and separate output roots:

```bash
python scripts/run_external_validation.py \
  --data-root /opt/banknifty-collector/data-prod-v4 \
  --output-root /explicit/output/path \
  --mode stream
```

The adapter remains dormant until separately authorized. Raw JSONL and derived market data must never be copied into Git.

