# Clean-Worktree Test Report

## V1.0.35 causal short-trap staging release

- **12/12** detector and scenario tests passed through direct assertions:
  inclusive 2.5x, 2.499x rejection, current-minute exclusion, gap/reset
  rejection, non-directional candidate, same-minute confirmation rejection,
  later-minute confirmation and timestamp ordering, legacy route removal, and
  unchanged long/short buildup and long-trap behavior.
- **3/3** integration assertions passed: Futures-volume replay prefix filtering,
  compact replay facts under 96 KB, and compact live facts under 96 KB.
- Python compilation, replay/live JavaScript syntax, shell syntax, rendered
  staging systemd-unit verification, CLI import/runtime identity, and live
  browser build identity `1.0.35` passed.
- `pytest` was not installed in the build environment. No full historical
  outcome evaluation or live deployment was represented as completed.
- The supplied V1.0.32 archive is the source baseline. Existing production
  services, state, data, and ports were not modified.

## V1.0.32 price/OI/ΔOI overlay

- New Divergence portable suite: **112 passed, 0 failed**.
- Replay and live JavaScript syntax checks, Python compilation, shell syntax
  checks and the live-browser build smoke test passed; the emitted browser
  manifest reports runtime `1.0.32`.
- Replay and live static contracts verify the amber OI line and signed green/red
  ΔOI bars share the price plot while retaining independent normalization.
- The removed lower participation-lane coordinates are rejected by regression
  tests, and the 680-pixel adaptive basis/price canvas remains stable.
- No calculation, data-retention, service, collector, Codex or production-weight
  rule changed.

## V1.0.31 live confirmed-zone parity

- New Divergence portable suite: **112 passed, 0 failed**.
- Replay and live JavaScript syntax checks passed.
- Authority tests verify that live `confirmed_zones` are projected from the
  complete transition history and retain confirmation/terminal timestamps.
- Browser tests verify causal zone creation, incremental live closure, green
  and red start lines, and neutral dashed terminal markers.
- No candidate state is rendered as a coloured divergence layer. No engine,
  collector, scenario, commentary or production-weight rule changed.

## V1.0.30 expanded adaptive basis lane

- New Divergence portable suite: **111 passed, 0 failed**.
- Replay and live JavaScript syntax checks passed.
- Deterministic canvas harnesses verified all display modes: a globally clear
  same-sign corridor selects `BETWEEN`, a narrow/crossing corridor selects
  `TOP`, and the visibility control selects `HIDDEN`.
- Static browser tests verify one market canvas, no separate basis canvas,
  an independent 180-pixel basis lane with four reference guides, independent
  Futures-OI lane, signed ΔOI bars, placement status, persistent visibility,
  and identical replay/live structure.
- The broader repository suite reached **207 passed and 20 expected skips**;
  its remaining 14 failures and 16 setup errors require absent sealed
  `/opt/banknifty/research/...` inputs or the intentionally excluded legacy R6D
  static page. These are unrelated to New Divergence and were not represented
  as V1.0.30 failures.
- No scenario calculation, replay artifact, market-data payload, commentary,
  service, collector, port or production weight changed.

## V1.0.28 transparent four-scenario engine

- One pure causal classifier is used by exact-cursor replay commentary and the
  live scenario endpoint.
- Synthetic causal tests cover true long buildup, true short buildup, long
  trap, short trap and insufficient-history abstention.
- Trap tests require an observed Futures-OI buildup followed by liquidation and
  a failed/reclaimed CE/PE control; option-premium evidence is never invented.
- Live GUI tests verify independent five-second backend scenario refresh and
  side-by-side backend/Codex presentation.
- Opening and closing decision-window filters remain explicit and replay/live
  transport behavior is otherwise unchanged.

## V1.0.27 bounded live delivery

- Live bootstrap returns one current synchronized observation, establishes SSE
  immediately, and progressively backfills exact historical observations in
  bounded device-aware chunks. Replay delivery is unchanged.
  observations with no raw event payload; status/profile/commentary paths use
  purpose-specific snapshots.
- Commentary visibly separates transparent inventory rules and Codex output.

## V1.0.26 live workspace flow correction

- Material shifts and optional transitions now follow Basis in the primary
  column; the desktop snapshot rail no longer creates blank left-column space.
- Desktop rail width was increased for full inventory values and controls.

## V1.0.25 replay-aligned live workspace

- Replaced the live card wall with replay-aligned market, basis, CE/PE snapshot,
  inventory, shift and transition frames.
- Added separate browser/feed state, intentional chart breaks across stale
  intervals, inventory overlays and signed option/Futures OI presentation.
- Added live asset and structure regression coverage.

## V1.0.24 live presentation correction

- Corrected the live inventory row contract: two rendered cells now map to two
  CSS grid columns, eliminating the 12-pixel label compression and overlap.
- Added a live-only responsive stylesheet emitted by `build-live-browser`.
- Inventory controls, selected option strikes and transitions use compact card
  grids; standard market and basis chart heights were reduced.
- Python compilation, JavaScript syntax and live-browser build smoke checks
  passed. Calculation and service behavior are unchanged from V1.0.23.

## V1.0.23 live causal-ID parity regression

- Portable New Divergence tests: **105 passed, 0 failed**.
- Live profile projection now reuses the replay strike-selection, Futures OI,
  Futures-volume and intraday inventory functions.
- Live Codex prefix tests verify non-empty CE/PE option deltas, current inventory
  controls and causal shift history.
- Live browser tests verify the inventory frame and compact SHIFT commentary.
- Python compilation, replay/live JavaScript syntax, shell syntax and live
  browser runtime identity `1.0.23` passed.
- No service, port, collector, replay output, SQLite store or Codex worker was
  modified during package verification.

## V1.0.22 central commentary regression

- Portable tests: **189 passed, 20 expected skips, 0 failed**.
- Two legacy external-fixture suites were excluded because their sealed
  `/opt/banknifty/research/...` inputs are not present in this build workspace.
- New central-commentary tests: exact shift detection, separate transparent
  analysis, absent unvalidated probability, immutable SQLite records and live
  prefix hashing all passed.
- Bounded central-queue execution and pending-work deduplication passed.
- Python compilation, replay/live JavaScript syntax, CLI smoke tests and shell
  syntax passed.
- Codex app-server request uses the 0.149.1 read-only policy shape with network
  disabled.
- No service, port, replay process, worker, learning run or holdout was changed.

- Environment: isolated Python virtual environment with verified system packages.
- Editable install: passed.
- Package import: `banknifty_profiler 0.1.0` passed.
- Unit tests: 6 passed.
- Integration tests: 2 passed.
- Equivalence tests: 2 passed.
- Total: **10 passed, 0 failed**.
- Deterministic transition ID: passed.
- Frozen 65/41/24 episodes and 14 retriggers fixture: passed.
- 2,000 ms synchronization boundary: passed.
- 60-second stalled precedence: passed.
- Native versus compatibility mechanism separation: passed.

Full multi-GB equivalence remains an explicit external-data operation and was not run during repository creation.

## V1.0.14 release regression

- New Divergence tests: **79 passed, 0 failed**.
- Portable repository tests: **174 passed, 20 expected skips, 4 external
  sealed-audit checks deselected**; the absent legacy R6D GUI fixture was
  excluded as a whole.
- JavaScript syntax, Python source compilation, shell syntax, and diff
  whitespace checks: passed.
- Functional control harness: `ID` remains off when unchecked, zero selected
  scopes are allowed, an older ID run reports the raw-replay requirement, and
  selecting an eligible prior scope re-enables its Futures-volume controls.
- V1.0.13 profile calculations and retained artifacts, V1.0.12 nightly context,
  and the divergence state machine are unchanged.

## V1.0.13 release regression

- New Divergence tests: **79 passed, 0 failed**.
- Portable repository tests: **174 passed, 20 expected skips, 4 external
  sealed-audit checks deselected**; the absent legacy R6D GUI fixture was
  excluded as a whole.
- JavaScript syntax, Python source compilation, shell syntax, and diff
  whitespace checks: passed.
- Functional control harness: ID is restored when browser state contains no
  scope, the Futures-volume master removes all three volume levels, and the
  last available scope cannot silently disappear.
- Verified V1.0.11 August 28 run compatibility: passed; its 2,114-record ledger
  remained valid and produced 36 causal ID OI control changes. ID Futures
  volume correctly reports unavailable because that older run has no retained
  Futures counter.
- Synthetic V1.0.13 replay retained and verified the Futures counter, produced
  a cursor-filtered ID VPOC/VAH/VAL, and generated a byte-identical divergence
  transition ledger with and without the additional volume field.
- Verified V1.0.12 context producer identity is intentionally reused because
  the nightly context algorithm and parameters are unchanged.
- Full rendered-browser acceptance remains the deployment-VPS checkpoint; the
  local Playwright package has no installed Chromium executable.

## V1.0.12 release regression

- New Divergence tests: **74 passed, 0 failed**.
- Portable repository tests: **169 passed, 20 expected skips, 4 external
  sealed-audit checks deselected**.
- JavaScript syntax: passed.
- Python source compilation: passed.
- Installer and runtime shell syntax: passed.
- Verified V1.0.11 August 28 run compatibility: passed; 2,114-record ledger
  valid and 32,844 synchronized observations projected under runtime 1.0.12.
- Prior-context causality and hash verification: passed.
- OI-VPOC build flags and GUI display flags: passed.
- Futures-volume VPOC plus deterministic 70% VAH/VAL: passed.
- Full rendered-browser acceptance: pending on the deployment VPS because the
  cloud browser could not access the workspace-local preview.
