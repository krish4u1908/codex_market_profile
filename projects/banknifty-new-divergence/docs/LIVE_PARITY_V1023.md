# V1.0.23 live causal-ID parity — staging release

V1.0.23 computes one authoritative causal developing profile from 09:45 IST to
the latest committed live receipt. The calculation reuses the replay projection
functions for selected-strike CE/PE OI, Futures OI, Futures cumulative-volume
deltas, signed OI-VPOCs and the BN-reference Futures-volume value area.

The live snapshot publishes current controls and the recent causal history for
each family. The central commentary worker hashes the option summary, current
inventory and divergence transition; unchanged facts reuse the stored result.
Browsers only retrieve stored commentary and never connect to the Codex worker.

This remains a research diagnostic. V0.1.3 selected no validated specialist, so
the GUI continues to display `NO_EDGE`, `LOW` confidence and no probability.

This staging release restores the causal intraday (`ID`) profile path. Frozen
prior-session 1D/2D/3D context is deliberately not claimed as complete live
parity yet; that integration remains gated on this ID path reproducing replay
for the same causal receipts.

## Safety boundary

- Collector roots are read-only.
- Live state and commentary SQLite are written only below the configured state
  root.
- Codex remains on `127.0.0.1:4500`; no UFW rule is required or permitted.
- Install and verify on a staging port before replacing the existing `8793`
  service.
