# Changelog

## R6C0

- Removed historical research, replay, manifest, and derived-table reads from
  the divergence runtime.
- Added explicit raw data/output interfaces and a causal inventory adapter.
- Added repository-native dependency grouping and provenance tests without
  changing frozen analytical thresholds.

## Verified baseline

- Imported verified raw I/O and divergence primitives.
- Preserved canonical BankNifty-reference inventory semantics.
- Added repaired raw lifecycle/resolution implementation and causal contracts.
- Added deterministic local verification tests.
# R6C0I

- Replaced the inventory wrapper with a repository-native raw-only implementation.
- Removed hard-coded production roots, research imports, `sys.path` mutation, fixed date/chain dictionaries, minute fallback, and implicit output writes.
- Added deterministic explicit-root CLI, continuity discovery, causal BN-reference mapping, and provenance tests.
# R6C0T

- Removed embedded participation collector roots and derived-anchor runtime inputs.
- Added a typed, validated repository-generated episode-anchor contract.
- Added a portable explicit-root full-stack participation processor and repository-native four-view builder.
- Isolated historical R6B3A/R6B3R reconciliation utilities under `tools/historical_audit/`.
