# New Divergence acceptance evidence

## V1.0.32 price/OI/ΔOI overlay acceptance

- Replay and live place the active BankNifty Futures OI linear trace inside the
  synchronized Index/Futures price plot using an independent OI scale.
- Positive and negative Futures ΔOI bars use an internal lower baseline in the
  same plot, with green bars above and red bars below.
- The former separate participation lane is absent. Basis remains independently
  scaled and adaptive; confirmed divergence layers remain causally identical.
- OI, ΔOI and price retain their existing receipt-time gap rules and do not
  change engine, inventory, scenario or commentary calculations.

## V1.0.31 live confirmed-zone parity acceptance

- Replay and live now consume the same confirmed-zone contract derived from
  authoritative episode transitions.
- Live zone projection uses the complete transition ledger even though the
  transition-card display remains bounded to the most recent 50 records.
- Functional tests verify that one confirmed green episode produces one live
  zone with its causal confirmation and resolution times.
- Live SSE handling adds a zone only on `CONFIRMED` and closes it only on
  `RESOLVED`, `ROTATION`, or `EXPIRED`; candidate states remain uncoloured.
- The live market canvas draws confirmed green/red spans, solid confirmation
  lines and dashed terminal lines without changing engine calculations.

## V1.0.30 expanded adaptive basis-lane acceptance

- Replay and live each publish one synchronized long market canvas containing
  BankNifty Index, active Futures, basis, active Futures OI and signed Futures
  ΔOI without sharing incompatible Y-axis units.
- A deterministic visible-prefix harness verified `BETWEEN`, `TOP`, and
  `HIDDEN` basis-lane modes in replay; the live renderer independently verified
  `BETWEEN` and `TOP` with equivalent geometry.
- A basis corridor is accepted only when the visible prefix has one stable
  basis sign and at least 180 safe pixels between the complete Index and
  Futures paths after insets. A narrow corridor or price-line crossing moves
  the complete 180-pixel basis lane to the reserved top position.
- Four horizontal basis-scale reference guides are present in both replay and
  live, and the combined market canvas is 680 pixels high so the basis trace is
  not compressed into a header strip.
- The complete New Divergence suite passed: 111 tests. Both JavaScript assets
  passed syntax checks. Runtime calculations and causal records are unchanged.

## Recovered baseline

- Upstream R6D commit: `65ae2c5cb7793ec32a3ae515e3a0aa6365ad2c14`
- Local sealed baseline commit: `325c61ff64729e1f3757e0d0bc08d026252b1112`
- Baseline tag: `baseline-r6d-offline-gui-65ae2c5`
- Recovered source archive SHA-256:
  `c77abcbcf9c017fb8abaf1b69c86c4c4888d824c666534e92b5372e78b2735a1`
- Baseline manifest after recovery: 105 files present, 0 hash mismatches
- Portable baseline tests before New Divergence: 84 passed, 20 skipped
- Final combined portable suite: 111 passed, 20 skipped

## Attached collector archive acceptance

- Input filename: `complete_20_08.tar(1).gz`
- Input SHA-256:
  `1e021b9e3526e01a62dd57058170b854ad4a82663ea507274436ff91ec719f49`
- Compressed size: 375,014,172 bytes
- Read-only window: 2026-08-20 10:00:00–10:07:00 IST
- Selected members: `oi_10.jsonl`, `events_10.jsonl`
- Raw archive tree extracted: no
- Source JSONL rows scanned: 674,319
- Invalid JSONL rows: 0
- Explicitly excluded target-symbol non-price updates: 3,889 Futures records
- Metadata-selected Index: `NSE:NIFTYBANK-INDEX`
- Metadata-selected Futures: `NSE:BANKNIFTY26AUGFUT`
- Normalized records: 840 Index ticks, 570 Futures ticks, 7 Futures-OI
  snapshots, 7 option-pressure snapshots
- Valid synchronized basis observations: 569
- Dense classified evidence snapshots: 569
- Causal refusal: 1 Futures tick with no prior visible Index tick
- Transitions: 3 candidates and 3 `NO_EDGE` closures
- Confirmed episodes: 0
- Transition ledger: 6 records, SHA-256 chain valid
- Retrospective outcome rows: 0, correctly reflecting no confirmed episode
- Independent repeat replay: byte-identical
- Basis output SHA-256:
  `a72de58d658e07a0009e1618b67f877a624539597a2c4ee67627cacff9600aab`
- Transition output SHA-256:
  `7c154155289b08f2eedd874eba04a24f77e9ede91325bd5770079fbefbd04cbe`
- Evidence output SHA-256:
  `e15f58e08850f2e0ca46afc9c4b2a07964f22b8ad6c6f96e49157d07d403c280`
- Runtime source-tree SHA-256 recorded by the authoritative run:
  `4c926b56f85adce687739e5d41bdc096ad09d6b858d988355b41f2211d067dd6`
- Complete run verification: valid (`OK`)

This real-data acceptance run was produced by V1.0.0. V1.0.1 changes only
installer scripts, installation documentation, and version metadata; it does
not change the engine, archive adapter, causal rules, or output calculations.
V1.0.2 adds replay publication and GUI-service operations only; it likewise
does not change the engine or calculated outputs.

## V1.0.3 nightly-context acceptance

- Portable suite: 133 passed, 20 skipped, 4 external-audit tests deselected.
- The deselected tests require the absent `R6C0I_AUDIT_ROOT`; the separate
  sealed R6D GUI tests likewise require an absent fixed
  `/opt/banknifty/research/...` tree. No V1.0.3 failure was hidden by the
  portable selection.
- Nightly-specific synthetic acceptance covers three complete sessions,
  available 1D/2D/3D controls for all seven canonical families, exact combined
  bin totals, deterministic unchanged reruns, append-only changed-source
  revisions, current-session cutoff exclusion, malformed JSON rejection, and
  unstable-source refusal.
- Rendered systemd service and timer templates pass `systemd-analyze verify`.
- The V1.0.3 wheel contains the nightly context module and matching 1.0.3
  package metadata. Wheel SHA-256:
  `f6cd884be5da2565d421aa8a13219001e2c27a9f898c44eba51c3370484b3f33`.
- A read-only OI subset from the attached collector archive was extracted only
  to a disposable validation directory (the raw tree was not extracted).
  Parsing produced 27,265 BankNifty rows across Call, Put, and Futures classes,
  dynamically selected `NSE:BANKNIFTY26AUGFUT`, selected Futures and option
  expiry `2026-08-25`, and observed 385 receipt minutes from 09:15:55 through
  15:39:55 IST. Within the 09:15–15:29 quality window the selected Futures had
  zero missing minutes and the selected option expiry had one missing minute,
  both within the checked-in five-minute limit.
- V1.0.3 adds derived context only. The intraday engine configuration,
  divergence thresholds, confirmation rules, and `production_weight: 0`
  remain unchanged.

The bounded real-data result is acceptance evidence for parsing, metadata
selection, receipt ordering, backward matching, state publication, and ledger
integrity. It is not evidence that a divergence has predictive value.

## V1.0.11 cash-sample and direct-root acceptance

- Source archive minute dates exercised: 2026-08-18, 2026-08-19, and
  2026-08-20.
- Each date produced 330 rows from 09:45 through 15:14 IST with 330 `VALID`
  statuses, full 14-constituent breadth coverage, and full volume coverage.
- Sample JSONL sizes were 103,454; 103,041; and 103,398 bytes respectively;
  each independent manifest was about 2.36 KB.
- Deterministic sample SHA-256 values were
  `5ded76c8b35977e087a21a92180d29b9a0cc347b38ca92d69aa5a65674f27669`,
  `73023f3958ae161bc636dbc58b8bfdebcfbe9a52305ff10516e4809d06c19cdd`,
  and `33448f44592bbadb2448260c7d26010ab98d0fb831e4b27ab444f33e3f94a74b`.
- An unchanged second generation returned `UNCHANGED` for all three dates.
- A sample-only August 20 directory was atomically promoted by archive replay;
  both sample files remained valid and the complete run passed ledger and
  artifact verification.
- The V1.0.11 browser payload began every series no earlier than
  `2026-08-20T04:15:00Z` (09:45 IST) and retained 330 cash rows beginning at
  the causally safe 09:46:08 publication time.
- A like-for-like replay through 10:10 IST produced 212 transition records
  byte-identical to the accepted prior ledger, SHA-256
  `df42382d62dfebf5f111418055324dca76d6df781767296769424a218b588c3a`.
- V1.0.11-focused New Divergence suite: 71 passed. Final portable repository
  suite: 166 passed, 20 expected skips, and four unavailable sealed-audit
  checks deselected. The legacy R6D GUI fixture file remains external and was
  excluded as a whole.

This acceptance establishes data-contract, idempotence, direct-root,
promotion, browser-boundary, and engine-invariance behavior. It does not assign
predictive value or production weight to either cash parameter.

## V1.0.14 inventory-control hotfix acceptance

- New Divergence suite: 79 passed.
- Portable repository suite: 174 passed, 20 expected skips, and four
  unavailable sealed-audit checks deselected; the external legacy R6D GUI
  fixture was excluded as a whole.
- `ID`, `1D`, `2D`, and `3D` remain independently unchecked, including a valid
  zero-scope state with zero inventory overlays.
- Scope-aware Futures-volume feedback distinguishes an available selected
  scope from an older ID run lacking the V1.0.13 cumulative-volume artifact.
- No profile calculation, retained artifact, prior-context contract, or
  RED/GREEN divergence transition changed.

## V1.0.13 developing-inventory display acceptance

- New Divergence suite: 79 passed.
- Portable repository suite: 174 passed, 20 expected skips, and four
  unavailable sealed-audit checks deselected; the external legacy R6D GUI
  fixture was excluded as a whole.
- ID scope begins at 09:45, publishes only the latest control state visible at
  the replay cursor, and keeps all seven inventory families outside the
  divergence engine.
- Futures-volume retention tests cover the 09:45 baseline, missing counters,
  counter resets, gaps, exact synchronized Index coordinates, VPOC, and
  contiguous 70% VAH/VAL.
- GUI tests and the functional JavaScript harness cover the no-scope browser
  restoration defect, scope-aware family availability, the volume master,
  plotted-level count, and direct on-chart labels.
- A verified V1.0.11 August 28 run produced all six signed ID OI families with
  36 display transitions. Its missing ID Futures-volume profile was explicit;
  a V1.0.13 replay is required for that new artifact only.
- The synthetic transition ledger was byte-identical with and without retained
  Futures volume. No RED/GREEN threshold, horizon, confirmation, transition,
  or production weight changed.

## V1.0.12 inventory-profile display acceptance

- New Divergence suite: 74 passed.
- Portable repository suite: 169 passed, 20 expected skips, and four
  unavailable sealed-audit checks deselected. The external legacy R6D GUI
  fixture file remains absent and was excluded as a whole.
- Deterministic synthetic raw/OI acceptance published all seven canonical
  families for 1D/2D/3D, recomputed multi-day controls from summed 25-point
  bins, and published a contiguous value area containing at least 70% of the
  aggregate Futures-volume profile.
- Value-area tests cover heavier-side expansion, exact adjacent-bin ties,
  `VAL <= VPOC <= VAH`, and null VAH/VAL for signed OI families.
- Context tests cover V1-to-V2 SQLite migration, immutable repeat reuse,
  changed-source revisioning, same-day cutoff refusal, rejected-source
  fail-closed behavior, build-family filtering, and a bootstrap boundary of
  only the latest three contributing sessions.
- The verified V1.0.11 August 28 run remained reusable without raw replay:
  ledger validation passed for all 2,114 records, and V1.0.12 rebuilt a
  32,844-row 09:45+ browser payload while retaining all 330 verified cash
  sample rows.
- JavaScript syntax, Python compilation, shell syntax, fixed canvas structure,
  package identity, and browser-payload feature flags passed. The cloud browser
  could not reach the local preview, so rendered visual acceptance remains the
  deployment-server checkpoint.
- Inventory context is explicitly `divergence_engine_input: false`; no
  threshold, horizon, confirmation rule, transition record, or production
  weight is changed.
