from __future__ import annotations

import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

from banknifty_profiler.gui.adapter import SESSIONS
from banknifty_profiler.shadow.api import create_server
from tests.unit.test_r6e1r_live_gui_api import (
    State,
    availability,
    crossed_clock_snapshot,
    snapshot,
)


EVIDENCE = Path("evidence/r6e1r/gui")


def complete_availability():
    value = availability()
    value["overall_state"] = "LIVE_FULL_CONTEXT"
    for component in ("index_state", "futures_state", "futures_oi_state", "ce_state", "pe_state"):
        value[component] = "AVAILABLE"
    for horizon in ("3D", "2D", "1D", "ID"):
        value["layers"][horizon] = {
            "state": "AVAILABLE", "reason": "VERIFIED_CONTEXT",
        }
    return value


def test_live_gui_browser_acceptance_and_screenshots():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    runtime = State(crossed_clock_snapshot(state=complete_availability()))
    service = create_server(runtime, "127.0.0.1", 0)
    thread = threading.Thread(target=service.serve_forever)
    thread.start()
    base = f"http://127.0.0.1:{service.server_address[1]}"
    errors = []
    try:
        with sync_playwright() as playwright:
            environment = dict(os.environ)
            local_libraries = [
                "/tmp/r6e1r-browser-deps/root/usr/lib/x86_64-linux-gnu",
                "/opt/banknifty/research/.browser_libs/root/usr/lib/x86_64-linux-gnu",
            ]
            available = [path for path in local_libraries if Path(path).is_dir()]
            if available:
                environment["LD_LIBRARY_PATH"] = ":".join(available + [environment.get("LD_LIBRARY_PATH", "")]).rstrip(":")
            browser = playwright.chromium.launch(headless=True, env=environment)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base, wait_until="networkidle")
            page.wait_for_function("window.R6E && window.R6E.state.chart && !window.R6E.state.busy")

            paths = page.evaluate("""() => {
                const r=window.R6E;
                const rows=r.unpack(r.state.chart.price);
                const index=r.segments(rows,'it','i').flat();
                const futures=r.segments(rows,'ft','f').flat();
                const basis=r.segments(rows,'t','b').flat();
                return {
                    index:index.length,
                    futures:futures.length,
                    clocksDifferent:rows.some(x=>x.it!==x.ft),
                    indexTimes:index.map(x=>x[0]),
                    futuresTimes:futures.map(x=>x[0]),
                    basisTimes:basis.map(x=>x[0]),
                    indexValues:index.map(x=>x[1]),
                    futuresValues:futures.map(x=>x[1]),
                    basisAligned:rows.every(x=>x.t===x.ft),
                    backwardAgesValid:rows.every(x=>x.it<=x.ft && x.a>=0 && x.a<=2000)
                };
            }""")
            assert paths == {
                "index": 2,
                "futures": 2,
                "clocksDifferent": True,
                "indexTimes": [1787113799500, 1787113799900],
                "futuresTimes": [1787113800000, 1787113801000],
                "basisTimes": [1787113800000, 1787113801000],
                "indexValues": [57000, 57001],
                "futuresValues": [57080, 57082],
                "basisAligned": True,
                "backwardAgesValid": True,
            }
            assert page.locator("#overallBadge").inner_text() == "LIVE FULL CONTEXT"
            inventory_families = page.evaluate("""() => {
                const rows=window.R6E.unpack(window.R6E.state.chart.inventory);
                return Object.fromEntries(['3D','2D','1D','ID'].map(horizon => [
                    horizon, [...new Set(rows.filter(row => row.horizon===horizon).map(row => row.family))].sort()
                ]));
            }""")
            for horizon in ("3D", "2D", "1D", "ID"):
                assert "BN_REF_FUT_VOLUME_VPOC" in inventory_families[horizon]
                assert any(
                    family.endswith("OI_VPOC")
                    for family in inventory_families[horizon]
                )

            divergence = page.locator("#divergencePanel").inner_text()
            assert "HYP-2026-08-19-001-GREEN" in divergence
            assert "NEW_INDEPENDENT_HYPOTHESIS" in divergence
            futures_card = page.locator('[data-participation-kind="FUTURES"]')
            ce_card = page.locator('[data-participation-kind="CE"]')
            pe_card = page.locator('[data-participation-kind="PE"]')
            assert "Price Δ 1m / 3m / 5m" in futures_card.inner_text()
            assert "0 / 6 / 10" in futures_card.inner_text()
            assert "FUTURES · LONG_BUILDUP" in futures_card.inner_text()
            assert "Premium Δ 1m / 3m / 5m" in ce_card.inner_text()
            assert "0 / 4 / 7" in ce_card.inner_text()
            assert "CE · SUPPORTIVE" in ce_card.inner_text()
            assert "CE · NEUTRAL" not in ce_card.inner_text()
            assert "-1 / -3 / -6" in pe_card.inner_text()
            assert "PE · CONTRADICTORY" in pe_card.inner_text()
            rendered_text = page.locator("body").inner_text()
            assert "undefined" not in rendered_text
            assert "null" not in rendered_text
            assert "SUCCESS" not in rendered_text
            assert "FAILURE" not in rendered_text
            page.screenshot(path=str(EVIDENCE / "complete_fixed_horizons.png"), full_page=True)

            # A master changes visibility only; the child selection survives
            # master toggles, polling, and a full browser refresh.
            assert page.is_checked('[data-child="1D|FUT_POS_OI_VPOC"]')
            page.uncheck('[data-child="1D|CE_POS_OI_VPOC"]')
            page.uncheck('[data-master="1D"]')
            page.check('[data-master="1D"]')
            assert page.is_checked('[data-child="1D|FUT_POS_OI_VPOC"]')
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
            page.evaluate("window.R6E.refresh()")
            page.wait_for_function("!window.R6E.state.busy")
            assert page.is_checked('[data-child="1D|FUT_POS_OI_VPOC"]')
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')

            # Preserve child choices while moving latest -> replay -> another
            # replay, polling each mode, and reloading the full browser page.
            replay_options = page.locator("#sessionMode option").evaluate_all(
                "options => options.map(option => option.value)"
            )
            assert replay_options == ["latest", *SESSIONS]
            visited_replays = []
            page.select_option("#sessionMode", "2026-08-11")
            page.wait_for_function("""() => !window.R6E.state.busy &&
                window.R6E.state.settings.session==='2026-08-11' &&
                window.R6E.state.chart.session_date==='2026-08-11'""")
            visited_replays.append("2026-08-11")
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
            page.evaluate("window.R6E.refresh()")
            page.wait_for_function("!window.R6E.state.busy")
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')

            page.select_option("#sessionMode", "2026-08-12")
            page.wait_for_function("""() => !window.R6E.state.busy &&
                window.R6E.state.settings.session==='2026-08-12' &&
                window.R6E.state.chart.session_date==='2026-08-12'""")
            visited_replays.append("2026-08-12")
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
            page.reload(wait_until="networkidle")
            page.wait_for_function("""() => window.R6E && !window.R6E.state.busy &&
                window.R6E.state.settings.session==='2026-08-12' &&
                window.R6E.state.chart.session_date==='2026-08-12'""")
            assert page.is_checked('[data-child="1D|FUT_POS_OI_VPOC"]')
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')

            for replay_date in SESSIONS[2:]:
                page.select_option("#sessionMode", replay_date)
                page.wait_for_function(
                    """date => !window.R6E.state.busy &&
                    window.R6E.state.settings.session===date &&
                    window.R6E.state.chart.session_date===date""",
                    arg=replay_date,
                )
                assert page.locator("#sessionMode").input_value() == replay_date
                assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
                visited_replays.append(replay_date)
            assert visited_replays == list(SESSIONS)

            page.select_option("#sessionMode", "latest")
            page.wait_for_function("""() => !window.R6E.state.busy &&
                window.R6E.state.settings.session==='latest' &&
                window.R6E.state.chart.session_date==='2026-08-19'""")
            assert page.is_checked('[data-child="1D|FUT_POS_OI_VPOC"]')
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')

            for horizon in ("3D", "2D", "ID"):
                page.uncheck(f'[data-master="{horizon}"]')
            page.check('[data-master="1D"]')
            keys = page.evaluate("""() => {
                const r=window.R6E,c=r.state.chart;
                const bounds={start:Date.parse(c.session.start),end:Date.parse(c.session.end)};
                return [...r.inventoryGroups(r.unpack(c.inventory),bounds).keys()];
            }""")
            assert keys and all(key.startswith("1D|") for key in keys)

            page.uncheck('[data-master="1D"]')
            page.check('[data-master="ID"]')
            keys = page.evaluate("""() => {
                const r=window.R6E,c=r.state.chart;
                const bounds={start:Date.parse(c.session.start),end:Date.parse(c.session.end)};
                return [...r.inventoryGroups(r.unpack(c.inventory),bounds).keys()];
            }""")
            assert keys and all(key.startswith("ID|") for key in keys)

            # Fixed horizons disappear independently; Intraday and both market
            # paths remain visible with explicit reason badges.
            degraded = availability()
            for horizon in ("3D", "2D", "1D"):
                degraded["layers"][horizon] = {
                    "state": "MISSING_PRIOR_SESSION",
                    "reason": "INSUFFICIENT_PRIOR_SESSIONS",
                }
            degraded["overall_state"] = "LIVE_INTRADAY_ONLY"
            runtime.value = snapshot(state=degraded)
            runtime.orchestrator.latest = runtime.value
            page.evaluate("window.R6E.refresh()")
            page.wait_for_function("!window.R6E.state.busy")
            assert page.locator("#overallBadge").inner_text() == "LIVE INTRADAY ONLY"
            assert page.locator('[data-master="ID"]').is_checked()
            assert "MISSING_PRIOR_SESSION" in page.locator("#availability").inner_text()
            page.screenshot(path=str(EVIDENCE / "intraday_only_degradation.png"), full_page=True)

            runtime.value = snapshot(state=complete_availability())
            runtime.orchestrator.latest = runtime.value
            page.evaluate("window.R6E.refresh()")
            page.wait_for_function("!window.R6E.state.busy")
            page.select_option("#sessionMode", "latest")
            page.screenshot(path=str(EVIDENCE / "live_latest_operational.png"), full_page=True)
            assert page.locator("#participationPanel .participation-card").count() == 3
            assert page.locator("#participationPanel .participation-card table").count() == 3
            assert page.locator("#operationalPanel").inner_text().find('"read_only": true') >= 0
            browser.close()
    finally:
        service.shutdown()
        thread.join()
        service.server_close()
    assert errors == []
