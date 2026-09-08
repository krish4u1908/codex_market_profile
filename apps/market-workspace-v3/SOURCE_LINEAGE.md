# Source lineage

The GUI is derived from the BANKNIFTY V3 v1.0.62 workspace, source commit `228866cd6bd60a51a380ff0b42c23f4e95e5d405`. That interface supplies the charts, responsive layout, replay controls, workers, OI ladder and range displays. This package removes its hosting-specific shell and adds portable instrument/version adapters.

The adapter contracts were checked against these supplied independent-engine packages. They are references, not vendored runtimes or redistributed replay archives:

| Source package | SHA-256 |
| --- | --- |
| `banknifty-v2.0.0-independent.tar.gz` | `319db0d4cb8425028ad9e9c445ad19a66bad7346c0df61c134e201505da50e6f` |
| `nifty-v1062-v200-cash-vix-bundle.tar.gz` | `f992c4c865ba049f850b2a41121d721f7a0782bc08d4bd8484cd3660af3a2372` |
| `banknifty-v2.0.0-replay-converter.tar.gz` | `278bd127aedbe1c214264f1583630f04c0253a43563c622b3d46d0bfe426f4ac` |
| `banknifty-v2.0.0-morning-history-fix.tar.gz` | `60aae30243219e020c2d1908225fe069cb7961fbba0ea50fde26ffa3c2a01de5` |
| `nifty-v2.0.0-update-20260907.tar.gz` | `9f13b4a3033d1bdbc2a1ae5e84e4f9f3ad2d9212bab96f167406ac0c2b7e5563` |

The NIFTY source uses a 50-point strike grid and 25-point profile bins. BANKNIFTY uses a 100-point strike grid and 25-point bins. These adapters validate retained selections and display published levels; they do not recompute either grid or bin allocations.

The shared-core runtime reuses each instrument's frozen V2 authority and native context, retaining the verified v1.0.62 reference semantics. Shared GUI components and shared read-only market inputs do not turn v1 calls into V2 calls. Changes to causal rules require a separately named research revision, as specified by the repository's CONTRIBUTING.md.

Local regression inputs were the BANKNIFTY 28 August v1.0.62 interface export, NIFTY 3 September v1.0.62 and V2 exports, BANKNIFTY 28 August V2 September-contract conversion, and the recorded BANKNIFTY V2 session of 7 September. The 3 September NIFTY data are historical minute/OI reconstruction without retained VIX/cash. The 7 September V2 session includes reconstructed morning charts with actual later context publications. Those distinctions remain visible in the adapters.

Third-party packages remain dependencies in package-lock.json. The retained shadcn stylesheet includes its original license in `vendor/`.

The live integration uses the active VPS source capture reconciled in [the core source lineage](../market-core-v3/SOURCE_LINEAGE.md). GUI startup configuration restricts each deployed service to its own instrument. The static preview continues to support all four recorded workspace profiles.
