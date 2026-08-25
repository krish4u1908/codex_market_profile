# R3 Field Lineage

Executable trace, not documentation inference:

- `clean_combined_profiler_r3/src/build_r3.py:64-79` reads the frozen detector episodes, outcome-bearing master, and the previously derived state decomposition, maps legacy state episode IDs by confirmation timestamp, and substitutes frozen canonical episode IDs.
- `build_r3.py:91-105` copies first favourable/adverse response timestamps from the master and emits them when their own timestamps become causally eligible.
- `build_r3.py:101-109` projects every eligible derived basis update into R3's lifecycle and decomposition outputs.
- `build_r3.py:112-114` assigns opposite-divergence or unresolved terminal states using the frozen lifecycle end.

Therefore R3 is not one homogeneous raw-regenerated engine. It is a causal projection combining frozen detector identity, copied response/lifecycle fields, and calculated states from a derived synchronized-basis dataset. Exact per-field lineage is in `r3_field_lineage.csv`.

The adjudicator identified the outcome-bearing master from source inspection but did not open it. Response timestamps were independently reconstructed from raw Index receipts and compared with R3 ledger emissions.
