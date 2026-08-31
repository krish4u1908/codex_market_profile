# Changelog

## 1.0.22

- Replaced the tall commentary report with a compact shift/read/outcome/levels
  card and collapsed Codex/rule details.
- Added inventory-migration direction and a wide-basis contract verification
  warning to the transparent analysis.
- Moved replay Codex work into a single bounded server queue: one worker, 30
  jobs/hour, 256 pending jobs, exact-cursor deduplication.
- Public replay requests can retrieve or enqueue a verified cursor but never
  execute Codex in the HTTP request thread; clients poll `PENDING` to `STORED`.
- Made the live commentary endpoint retrieval-only; its existing background
  worker remains the only live generator.
- Removed the obsolete instruction to expose the internal token to browser tabs.
- Bumped commentary generation revision to 3 while preserving older SQLite
  records immutably.

## 1.0.21

- Declared the validator's exact string and array limits in the Codex structured
  output schema, preventing oversized `evidence_trace` responses.
- Increased the central client deadline from 45 to 90 seconds; the reproduced
  server turn completed in approximately 22 seconds.
- Stored a bounded safe Codex failure detail for operations diagnostics.
- Added commentary generation revision 2 so failed V1.0.20 fallback records are
  retained immutably while corrected V1.0.21 attempts receive new identities.
- Reuses only records whose `codex_status` is `AVAILABLE`; failed fallbacks can
  be retried without deleting the SQLite database.

## 1.0.20

- Added an immutable SQLite commentary store shared by every replay/live browser.
- Added deterministic CE/PE/Futures/BN-reference inventory-shift extraction.
- Added a separately labelled, transparent market-profile interpretation block.
- Added compact support/resistance, confirmation and invalidation fields.
- Kept direction `NO_EDGE`, confidence `LOW`, and probability absent because the
  V0.1.3 validation gate selected no eligible horizon specialist.
- Updated Codex app-server 0.149.1 read-only policy payloads.
- Kept the Codex worker loopback-only and preserved all causal-prefix checks.

## New Divergence V1.0.16

- Added independent display switches for the market, basis, CE ΔOI, PE ΔOI,
  CE ΔVolume, PE ΔVolume, CE OI snapshot, PE OI snapshot, and inventory-list
  frames. Every frame remains enabled by default.
- Persisted frame visibility in browser-local storage and removed hidden frames
  from layout flow. When all three right-side frames are hidden, the left chart
  column expands to the full replay width without an empty rail.
- Kept the V1.0.15 projection boundary, every replay payload, inventory
  calculation, and RED/GREEN transition unchanged. Frame switches are
  rendering-only and do not alter source or output artifacts.

## New Divergence V1.0.15

- Restored synchronized Index, Futures, basis, divergence-state, transition,
  confirmed-zone, and absolute Futures-OI history from the first session
  observation instead of clipping the entire browser at 09:45 IST.
- Kept Futures ΔOI bars blank before 09:45 and recalculated the post-09:45
  deltas from a fresh baseline, preventing opening accumulation from
  dominating later bars.
- Kept CE/PE strike ΔOI, CE/PE incremental volume, cash participation, and the
  developing ID inventory profile strictly baselined at 09:45. The fixed
  09:45-close ATM selection and all RED/GREEN engine outputs are unchanged.

## New Divergence V1.0.14

- Removed the browser guard that forcibly reselected the last enabled
  inventory scope. `ID`, `1D`, `2D`, and `3D` are now independent display
  flags and all four may be off, producing zero inventory overlays.
- Added a scope-aware Futures-volume status beside its controls. It explicitly
  distinguishes available levels, build-time disablement, absent verified
  context, and an older run that needs a V1.0.13-or-later raw replay for the
  intraday cumulative-volume artifact.
- Kept the V1.0.13 profile calculations, retained artifacts, V1.0.12 nightly
  context, and the RED/GREEN divergence engine unchanged.

## New Divergence V1.0.13

- Added a developing `ID (09:45→cursor)` inventory scope. Its signed
  Futures/CE/PE OI-VPOCs and Futures-volume VPOC/VAH/VAL use only receipts
  visible at the replay cursor; the 1D/2D/3D controls remain frozen prior-day
  context.
- Retained the active Futures cumulative-volume counter as a new hashed run
  artifact. Its first post-09:45 value, counter resets, missing values, and
  material gaps are baselines rather than fabricated traded volume.
- Fixed browser-restored checkbox state that could leave every scope off while
  family switches appeared enabled. At least one available scope is now kept
  selected, and family controls are disabled when the selected scope has no
  corresponding data.
- Added a true Futures-volume master switch, an always-visible plotted-level
  count, higher-contrast level lines, and collision-managed on-chart labels.
- Kept the nightly inventory calculation identity at V1.0.12 because its
  algorithm is unchanged, allowing the verified existing context database and
  immutable snapshots to be reused without re-reading raw prior sessions.
- Kept all inventory controls outside divergence identification. Retaining
  Futures volume produces an identical RED/GREEN transition ledger.

## New Divergence V1.0.12

- Integrated frozen prior-session inventory controls into the replay price
  chart on the causal BankNifty Index-reference coordinate. Signed Futures,
  CE, and PE positive/negative OI-VPOCs remain separate families.
- Added a deterministic 70% contiguous value area for the canonical
  BankNifty-reference Futures-volume profile. VAH and VAL expand from the
  aggregate VPOC by adjacent 25-point bins; 2D/3D profiles sum source bins and
  never average daily winners.
- Added independent build flags for OI-VPOC and volume-profile publication,
  plus GUI switches for 1D/2D/3D scope, Futures/CE/PE OI families, and volume
  VPOC/VAH/VAL.
- Added verified immutable-context selection to browser construction. A replay
  can use only the newest complete source cutoff strictly before its session;
  missing, future, corrupted, or rejected context fails closed in the GUI.
- Kept inventory and value-area controls display-only with
  `divergence_engine_input: false`. The gap-safe RED/GREEN state machine,
  thresholds, transitions, and production weight remain unchanged.
- Preserved the V1.0.11 cash-sample contract so existing verified breadth and
  participant-volume files do not require regeneration for this GUI release.

## New Divergence V1.0.11

- Standardized all new replay and sample output under one direct session root:
  `/home/bankadmin/divergence/sessions/YYYY-MM-DD`; the historical nested
  `RUN_ROOT/sessions/YYYY-MM-DD` contract is no longer used by this release.
- Added an idempotent, hash-verified generator for exactly two 09:45+ cash
  participation parameters: equal-vote constituent breadth versus the frozen
  09:45 reference and unweighted constituent one-minute share volume.
- Installed the generator alongside the existing collector without changing
  collector subscriptions or runtime logic, with a hardened daily 15:40 IST
  systemd timer and automatic browser-catalog refresh.
- Made every browser series begin at 09:45 IST while retaining the complete
  immutable engine run for audit. No pre-09:45 price, OI, volume, state,
  transition, or cash-participation row enters the replay projection.
- Kept both new cash parameters outside the divergence engine with explicit
  `production_weight: 0`, coverage metadata, source hashes, and fail-closed
  missing-data values. The RED/GREEN methodology remains unchanged.

## New Divergence V1.0.10

- Replaced the overlapping full-session CE/PE ΔOI bubble maps with current
  replay-receipt absolute-OI bar snapshots. Both panels share one linear OI
  scale, print compact absolute OI and signed latest ΔOI, and show a labelled
  current BankNifty Index reference line against clearly identified strikes.
- Moved the fixed strike reference from the 09:15 day open to the close of the
  09:15–09:45 warm-up window: the last synchronized BankNifty Index receipt at
  or before 09:45:00 IST, subject to the existing 2-second match tolerance.
- Kept the lower flow selection deterministic: nearest common listed ATM with
  lower-strike tie-break; CE uses ATM plus three higher strikes and PE uses ATM
  plus three lower strikes, frozen after 09:45.
- Made the first complete option-chain receipt after 09:45 a baseline. Its OI
  and volume deltas are blank, preventing pre-09:45 movement from entering the
  displayed flow panels.
- Enforced 09:45 as the server-side CE/PE projection boundary: pre-09:45 strike
  rows are absent from snapshots, flow panels, and prefix API responses rather
  than merely being hidden in the browser.
- Reused verified V1.0.9 run artifacts without raw replay and kept every
  RED/GREEN divergence transition and methodology parameter unchanged.

## New Divergence V1.0.9

- Added four vertically stacked, receipt-time-aligned flow panels: CE signed
  ΔOI, PE signed ΔOI, CE incremental volume, and PE incremental volume.
- Defined strike 1 from the BankNifty Index day open using the nearest common
  listed CE/PE strike with a deterministic lower-strike tie-break. CE strikes
  2–4 are the next three higher listed strikes; PE strikes 2–4 are the next
  three lower listed strikes, and all eight contracts remain fixed all day.
- Added a hashed session-open reference and fail-closed selection: the first
  valid Index receipt must arrive within 60 seconds of 09:15 IST, and a complete
  selected-expiry chain must be visible before strike identities are shown.
- Retained cumulative option volume in the compact per-strike artifact and
  projected only non-negative successive volume increments. Feed resets,
  missing volume, and stale gaps produce a blank rather than a false bar.
- Kept the V1.0.4 gap-safe divergence methodology and all RED/GREEN transition
  calculations unchanged. A full raw-plus-OI replay is required to populate
  the new V1.0.9 panels.

## New Divergence V1.0.8

- Left-justified the replay workspace across the full viewport with no unused
  desktop gutters; the existing combined market/OI and basis panels remain in
  the main left column.
- Added a vertical strike-OI rail on the right: CE first and PE directly below,
  with a single-column responsive fallback on narrower displays.
- Retained selected-expiry, per-contract option OI in a dedicated verified
  artifact and projected causal successive ΔOI bubbles on the same visible
  receipt-time domain as the main chart.
- Reset per-contract ΔOI after stale gaps, excluded the dense strike map from
  repeated engine evidence snapshots, and hid future strike receipts from
  prefix API responses.
- Kept the V1.0.4 gap-safe divergence methodology and every RED/GREEN
  classification parameter unchanged. Older compatible runs remain usable but
  need one raw-plus-OI archive replay to populate the new strike panels.

## New Divergence V1.0.7

- Corrected the V1.0.6 layout after clarification: merged Index, Futures,
  absolute OI, and positive/negative ΔOI into the first chart panel.
- Removed the separate duplicated Futures/OI panel; the basis and confirmed
  divergence chart remains the second independent panel.
- Preserved confirmed-zone markers, missing-basis gaps, shared receipt-time
  coordinates, and gap-safe OI behavior in the combined first panel.
- Kept the divergence methodology and analytical parameters unchanged; no
  replay is required for a compatible run that already retained Futures OI.

## New Divergence V1.0.6

- Added a full-width Futures participation panel with a white Futures-price
  trace, linear yellow absolute-OI trace, green positive-ΔOI bars, and red
  negative-ΔOI bars.
- Aligned that panel to the Index/Futures chart's exact visible receipt-time
  domain and shared left/right plot margins.
- Deduplicated OI repeated across evidence snapshots and calculated successive
  ΔOI in the server-side projection, resetting the delta after a stale gap.
- Added OI receipt age and freshness readouts and an explicit unavailable state
  when a verified run retained no Futures OI.
- Kept the V1.0.4 gap-safe RED-zone methodology and all analytical parameters
  unchanged; a compatible run that retained OI does not require another replay.

## New Divergence V1.0.5

- Fixed replay canvases shrinking or growing on every refresh by separating
  immutable CSS chart height from the device-pixel-ratio backing store.
- Versioned every browser build and made the service reject stale GUI assets,
  preventing a new service binary from silently serving an older replay page.
- Added runtime, browser-build, and required-methodology identity to `/healthz`
  so the installed page and RED-zone engine generation can be verified.
- Kept the V1.0.4 gap-safe RED-zone methodology and all analytical parameters
  unchanged; compatible V1.0.4 run bundles do not require another replay.

## New Divergence V1.0.4

- Prevented post-gap observations from reusing one stale pre-gap row as
  independent 1m/3m/5m evidence.
- Added per-horizon continuous-history warm-up and a 15-second reference/gap
  tolerance; fewer than two valid horizons now produces `UNKNOWN_GAP`.
- Moved every replay series to one receipt-time x-axis and stopped drawing
  market lines across missing-basis intervals.
- Replaced raw candidate/`NO_EDGE` chart stripes with shaded intervals that
  begin only at `CONFIRMED`; the complete transition ledger remains available.
- Marked older-methodology run bundles as `Replay required` so installation of
  the new GUI cannot silently present stale pre-fix classifications.

## New Divergence V1.0.3

- Added an incremental, single-instance nightly analyzer for completed raw/OI
  collector sessions with strict stability and continuity gates.
- Added versioned SQLite session bins and immutable 1D/2D/3D context bundles;
  multi-day controls recompute combined raw inventory instead of averaging
  daily VPOCs.
- Added a hardened 00:15 Asia/Kolkata systemd timer, an install-only-by-default
  installer, a cron-compatible wrapper, integrity inspection, and operations
  documentation.
- Kept all divergence thresholds, weights, and production behavior unchanged.

## New Divergence V1.0.2

- Added an idempotent `systemd` installer for the read-only replay GUI.
- Added a one-command archive replay, verification, and GUI publication script.
- Documented the operational distinction between completed replay support and
  the not-yet-wired live collector boundary.

## New Divergence V1.0.1

- Added idempotent Linux/macOS and Windows PowerShell installers.
- Added Python-version, archive-layout, virtual-environment, and CLI smoke
  checks without starting any service or background process.

## New Divergence V1

- Added a strict UTC event contract with IST exchange-session projection.
- Added one receipt-ordered engine shared by replay and shadow-live adapters.
- Preserved R6D 2-second synchronization, materiality, 1/3/5-minute support,
  and P60/N5 confirmation thresholds as explicit configuration.
- Added dynamic symbol/session discovery, streaming collector archive input,
  atomic run publication, and a hash-chained transition ledger.
- Added a calculation-free dynamic replay browser and a separately invoked
  zero-weight retrospective outcome evaluator.
- Kept the recovered R6D source at an immutable baseline tag.

## R6C0V — frozen runtime-invariant repair

- Canonical divergence and participation entrypoints now require timezone
  `Asia/Kolkata` and integer synchronization tolerance `2000` exactly.
- Invalid aliases, offsets, missing values, alternate types, and runtime
  tolerance values are refused before raw processing.
- Analytical calculations and frozen outputs are unchanged.

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
## 1.0.19

- Added replay-only Codex explanations at an exact synchronized receipt with
  four allow-listed diagnostic questions and no free-form prompt surface.
- Displayed a concise Analysis summary and evidence trace alongside the answer,
  without requesting or exposing private chain-of-thought.
- Reconstruct and hash the verified prefix on the server; reject non-exact
  cursors, future-data flags, malformed model output, and cursor mismatches.
- Added a per-tab access token, one-request concurrency, rate limits,
  structured-output validation, restricted read-only Codex turns, and
  best-effort deletion of every diagnostic thread.
- Kept live prompting disabled and preserved all divergence calculations,
  thresholds, replay artifacts, and transition ledgers.

## 1.0.18

- Added a separate, localhost-only Codex app-server systemd worker boundary.
- Added a read-only `/api/v1/codex/status` probe and live-GUI worker-status badge.
- Kept prompting and production-data access explicitly disabled for this first
  integration checkpoint.
- Changed the live CLI and installer default port to the deployed port 8793.

## 1.0.17

- Added a single authoritative, checkpointed live calculation process that
  tails collector raw/OI JSONL files read-only.
- Added monotonic snapshot/SSE delivery with reconnect sequence recovery,
  bounded per-window pause buffering, and fail-closed health reporting.
- Added per-window frame preferences and maximize/restore support to replay
  and live browser panels.
- Added an isolated port-8794 systemd service and 09:05 IST rollover timer;
  replay remains isolated on port 8793.
- Preserved the V1.0.16 engine, 09:45 boundaries, strike selection, projection
  calculations, thresholds, and methodology version unchanged.
