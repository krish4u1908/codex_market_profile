# NIFTY V3.0.18 — independent pressure direction

GUI release `3.0.18-gui-pressure-direction`, based on V3.0.17. Prepared for the same existing installation; not deployed.

## Requested changes

**Model P(up)** and **Realized next 10-minute move** have been removed, together with their display switches and browser calculations. The logistic coefficients are no longer served. The main workspace tab is now **OI Direction**.

The tab has five frames, each individually switchable in **Custom display**:

1. Existing main price chart with its current overlays.
2. Raw fixed-four pressure: dashed cyan 1m and yellow 5m, −100 to +100.
3. Independent pressure direction: **UP / DOWN / NEUTRAL**, available as each OI receipt arrives.
4. India VIX, dashed, with labelled archived-report fallback for older sessions.
5. Futures basis in points.

Existing price/pressure/VIX/basis display preferences migrate from V3.0.17. Direction defaults to visible. Show all frames restores all five. Choices persist in the same browser. The existing Market, Options, Inventory, Events and OI Research tabs remain.

## Independent rule — explicit and unfitted

The new rule uses only the existing fixed 09:45 four-CE/four-PE gross OI quantities and previous receipt state. It has no probability-model, price, VIX, basis or future-outcome inputs.

For each 1m and 5m window:

- CE net = CE additions − CE removals; PE net = PE additions − PE removals.
- Quantity balance = 100 × (PE net − CE net) / total gross additions and removals.
- 5m bull alignment: CE net < 0 and PE net > 0. 5m bear alignment: CE net > 0 and PE net < 0.

The direction rules are:

| Current 5m context | Additional requirement | Output |
| --- | --- | --- |
| Bull alignment | 1m quantity balance > 0 | UP |
| Bear alignment | 1m quantity balance < 0 | DOWN |
| Mixed episode that began after bull alignment | 1m balance < 0 and 5m balance falling from previous receipt | DOWN, reversal candidate |
| Mixed episode that began after bear alignment | 1m balance > 0 and 5m balance rising from previous receipt | UP, reversal candidate |
| Other complete inputs | No agreed direction | NEUTRAL |
| Incomplete inputs | Cannot calculate | UNAVAILABLE |

A mixed episode remembers the aligned state immediately preceding that continuous mixed episode. Missing windows, a receipt gap over 90 seconds, or no-flow clear that memory. The rule does not assume a mixed reading automatically continues the previous direction. Hover any point for the quantities, previous state and exact reason.

The display window is 09:50 to before 15:00 IST. It does not wait ten minutes or repaint earlier directions using later prices. A receipt more than 90 seconds old is not displayed as current. NEUTRAL means no agreed directional hypothesis, not a prediction of unchanged price.

## Historical findings — no forecasting edge established

Rules were written before this candidate evaluation and were not tuned to improve its results. Fifteen previously studied sessions and 4,633 eligible observations were checked; this is exploratory, not untouched forward validation. The 17 September live screenshot was not used to fit or score the rule.

The candidate issued a direction on 2,884 observations (62.2% coverage):

- Next 5m direction correct: **50.6%**.
- Next 10m direction correct: **49.3%**, exploratory whole-session bootstrap interval **46.1–52.8%**.
- With directional observations spaced at least 10 actual minutes apart: **48.2%** over 413 observations.
- Agreement with the preceding 5m move: **57.9%** over 2,882 readings with that history available.

The pattern tracks recent movement more clearly than it forecasts future movement in this sample. The separate UP/DOWN display should therefore be treated as an experimental pressure interpretation, not an established improvement or a trade signal. Full results include raw-5m and quantity baselines, first-five/later-ten dates, and normal/expiry sessions; no winning subgroup was selected. No trade P&L or costs are estimated.

## Live, replay and installation

Live and old-session replay use the same receipt-only rule. It also works for the first five study dates, because it needs no earlier-trained probability model. Old JSON/JSON.gz files with retained raw reports are supported. Catalog replay loads archived reports through the existing API without moving the cursor. Missing inputs remain unavailable; there is no synthetic fallback.

Use **INSTALL_EXISTING.md** to update the existing shared GUI. Same NIFTY port 8921; no new service or port. The existing updater briefly restarts both GUI services, checks both core PIDs are unchanged, and supports rollback. This package has not been applied to the VPS.

Rebuild:

```sh
cd source
npm ci
npm test
npm run build
```

`gui/` contains prebuilt assets, `source/` the complete source, and `validation/` the test logs, native chart render, historical research protocol/results and source patch. Research reproduction inputs and scripts are under `source/scripts/pressure-validation/`; they are not served to the browser. BUILD_STATUS.json records the checks and limits. Browser DOM interactions and native ECharts rendering were checked; a full production-browser/live-core verification was not performed.
