from __future__ import annotations

import os
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

from banknifty_profiler.shadow.api import create_server
from tests.unit.test_r6e1r_live_gui_api import State, availability, snapshot


EVIDENCE = Path("evidence/r6e1r/gui")


def complete_availability():
    value = availability()
    value["overall_state"] = "LIVE_FULL_CONTEXT"
    for horizon in ("3D", "2D", "1D", "ID"):
        value["layers"][horizon] = {
            "state": "AVAILABLE", "reason": "VERIFIED_CONTEXT",
        }
    return value


def test_live_gui_browser_acceptance_and_screenshots():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    runtime = State(snapshot(state=complete_availability()))
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
                return {
                    index:r.segments(rows,'it','i').flat().length,
                    futures:r.segments(rows,'ft','f').flat().length,
                    clocksDifferent:rows.some(x=>x.it!==x.ft)
                };
            }""")
            assert paths == {"index": 2, "futures": 2, "clocksDifferent": True}
            assert page.locator("#overallBadge").inner_text() == "LIVE FULL CONTEXT"
            page.screenshot(path=str(EVIDENCE / "complete_fixed_horizons.png"), full_page=True)

            # A master changes visibility only; the child selection survives
            # master toggles, polling, and a full browser refresh.
            page.uncheck('[data-child="1D|CE_POS_OI_VPOC"]')
            page.uncheck('[data-master="1D"]')
            page.check('[data-master="1D"]')
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
            page.evaluate("window.R6E.refresh()")
            page.wait_for_function("!window.R6E.state.busy")
            assert not page.is_checked('[data-child="1D|CE_POS_OI_VPOC"]')
            page.reload(wait_until="networkidle")
            page.wait_for_function("window.R6E && window.R6E.state.chart && !window.R6E.state.busy")
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
            assert page.locator("#operationalPanel").inner_text().find('"read_only": true') >= 0
            browser.close()
    finally:
        service.shutdown()
        thread.join()
        service.server_close()
    assert errors == []
