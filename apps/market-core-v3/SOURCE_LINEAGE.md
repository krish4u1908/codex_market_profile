# Captured source reconciliation

Input: `market-active-sources.zip`, created 2026-09-08T18:12:07Z by the source
capture helper. All 865 captured source-file hashes matched its manifest.
Installed package source matched project source for BANKNIFTY v1.0.53 (63
files), BANKNIFTY v1.0.62 (66) and NIFTY v1.0.62 (67). The archive includes
pre-cleanup service state; it does not prove that services were stopped.

| Instrument | Frozen implementation used |
| --- | --- |
| BANKNIFTY | Captured `banknifty-v200/v2_engine`, `analyze.py`, `live_context.py`, `chart_history.py` |
| NIFTY | Captured `nifty-v200/v2_engine`, `analyze.py`, `live_context.py` with its installed September 7 changes |

For each instrument, v1.0.62 and independent V2 share byte-identical authority,
engine, directional prediction, contracts, collector and clock implementations.
Relevant packaging differences are the runtime provenance version, V2 retaining
full futures OI/volume history instead of the v1 profile's last 120 rows, and
namespace changes in nightly imports. NIFTY's old v1 projection also contains
a minute-chart presentation policy absent from its V2 projection. These are not
used to alter the frozen scoring or clocks.

The reference call rules therefore run once in each instrument's V2 authority;
the native V2 context consumes that same snapshot. The new wrapper exports the
reference call history to v1.0.62 and native contexts to V2.0.0 without rewriting
them. BANKNIFTY's previous v1.0.53 live engine is retired; its different version's
call history is not relabelled as v1.0.62.

`VENDOR_MANIFEST.json` lists all 62 vendored source files and their hashes.
They are byte-identical to the supplied active sources, with this documented
recovery: the capture helper excluded directories named `runtime`, including
Python packages. Four missing files (two per instrument) were recovered from
the previously supplied source packages and matched the exact installed-file
hashes in `market-migration-info.zip`:

| File | Verified SHA-256 |
| --- | --- |
| `v2_engine/runtime/__init__.py` | `32cbb5ec2063778516f9fe57d00c11ecce7fc2931e332acd1251efe3eb8de8ef` |
| `v2_engine/runtime/timestamps.py` | `794b730e0b1f3c8e6bc7714e6524d14eb049057c813f0e377e2a32f9bde352b7` |

The bundled capture helper now retains Python runtime packages. Frozen vendor
files were not edited. Dependency pins match the captured NIFTY requirements
and the local verification environment: NumPy 2.3.5 and pandas 2.2.3.

The repository's CONTRIBUTING.md remains authoritative: causal rules and frozen
semantics must be preserved; research changes need a separately named revision.
New live transport, state copying and presentation code live under
`market_core/`, outside the frozen packages.
