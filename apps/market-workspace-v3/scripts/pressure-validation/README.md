# Reproduce pressure-rule validation

Use Node and Python with numpy/pandas. From the supplied 15-session nifty-v200-oi-analytics(1).tar, decompress each contained JSON.gz to a directory of session JSON files. Then run:

```sh
node evaluate.mjs /absolute/path/to/session-json-directory
python summarize.py
```

The first command recomputes the rule from the full raw receipt feeds, joins it to the retained eligible study observations, and rewrites evaluation_rows.jsonl.gz. The second computes all baseline/candidate and subgroup estimates in results.json. Existing evaluation rows are also supplied so the summary can be rerun without the large raw archive. They include realized outcomes only for this offline research evaluation; no research files or future price values feed the browser direction rule.

The archive SHA256 is e12c8d15fbb806d540f933d0081837583c95b9c9143eea3f3a447a5ebae15ae2. Protocol and all tested variants are retained. This is an exploratory reuse of previously examined dates, with no fitted thresholds, untouched holdout or demonstrated forecasting edge.
