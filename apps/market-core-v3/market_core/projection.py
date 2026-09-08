"""Presentation envelopes for two GUI versions; frozen publications are retained."""
from __future__ import annotations

import json


def pack(rows, extra=None):
    rows = list(rows)
    fields = sorted({key for row in rows for key in row if not key.startswith("_")})
    return dict(fields=fields, rows=[[row.get(key) for key in fields] for row in rows], **(extra or {}))


def chart_inputs(source, snapshot, config, prior=None):
    authority, vendor = source.authority, source.vendor
    profile = snapshot["profile"]
    # Project the retained raw option receipts once for all GUI clients. This is
    # display history only: do not replace or re-score the V2 decision inputs.
    strikes = vendor.projection.option_strike_oi_rows(
        [row for event in authority.events for row in vendor.output._option_strike_rows(event)],
        max_gap_seconds=float(authority.config.participation_max_age_seconds))
    selection = profile.get("strike_selection", {})
    if selection.get("available"):
        for row in strikes:
            if str(row.get("e")) == str(selection.get("expiry")) and row.get("t") == selection.get("selected_at"):
                row["d"] = row["dv"] = None
                row["vs"] = "MISSING" if row.get("v") is None else "BASELINE"
    price = [dict(t=r["timestamp"], i=r["index_price"], f=r["futures_price"], b=r["basis"],
        age=r.get("synchronization_age_ms")) for r in snapshot["observations"]]
    return dict(session=snapshot["session"], instrument=config.instrument,
        price=pack(price), futures_oi=pack(profile.get("futures_oi", [])),
        futures_volume=pack(profile.get("futures_volume", [])), cash_vix=pack(profile.get("cash_vix", [])),
        option_strike_oi=pack(strikes, {"strike_selection": selection}),
        intraday_inventory=pack(profile.get("inventory_rows", [])),
        inventory_context=prior or {"controls": []},
        provenance={"note": "Original receipts and published controls from the single shared instrument authority."})


def baseline_payload(source, snapshot, config, inputs):
    return dict(inputs, schema="NEW_DIVERGENCE_BROWSER_PAYLOAD_V1",
        workspace_profile=config.profile("v1062"), baseline_version="1.0.62",
        engine_runtime_version=snapshot["runtime_version"],
        directional_prediction=pack(source.authority.direction_history),
        transitions=pack([r.to_dict() for r in source.authority.engine.transitions]),
        confirmed_zones=snapshot.get("confirmed_zones", []), states={"fields": [], "rows": []},
        provenance={"source": "SHARED_LIVE_AUTHORITY", "call_source": "Unmodified v1.0.62 reference rules",
            "history_note": "Live receipt history. Calls retain their actual publication times; missed live calls are not backfilled."})


def v2_payload(context, snapshot, config, inputs):
    # This runs only in the producer thread. HTTP readers never acquire the
    # calculation/context lock or open the mutable context database.
    rows = [json.loads(body) for (body,) in context.db.execute(
        "SELECT body FROM decisions WHERE day=? ORDER BY cutoff", (snapshot["session"],))]
    return dict(version="2.0.0", baseline_version="1.0.62", instrument=config.instrument,
        workspace_profile=config.profile("v200"), session=snapshot["session"],
        decisions=rows, price_history=[], chart_inputs=inputs,
        provenance={"source": "SHARED_LIVE_AUTHORITY_AND_NATIVE_V2_CONTEXT",
            "history_note": "V2 contexts keep their original input cutoffs and publication times. Charts use the shared authority's receipt history."})
