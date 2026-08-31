"""Read-only API projection over already-built browser artifacts."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

from .clock import iso_utc, parse_instant


class ProjectionReadModel:
    """Load only catalog-listed session payloads; never invoke inference."""

    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        if not (self.directory / "catalog.json").is_file():
            raise FileNotFoundError(f"browser projection is not built: {self.directory}")

    def catalog(self) -> dict[str, object]:
        row = json.loads((self.directory / "catalog.json").read_text(encoding="utf-8"))
        if not isinstance(row, dict) or not isinstance(row.get("sessions"), list):
            raise ValueError("invalid browser catalog")
        return row

    def session(self, session: str, *, as_of=None) -> dict[str, object]:
        catalog = self.catalog()
        entry = next((row for row in catalog["sessions"] if row.get("session") == session), None)
        if entry is None:
            raise KeyError(f"session is not catalogued: {session}")
        expected = f"sessions/{session}.json"
        if entry.get("payload") != expected:
            raise ValueError("catalog payload path violates the session path contract")
        payload = json.loads((self.directory / expected).read_text(encoding="utf-8"))
        if as_of is None:
            return payload
        cutoff = parse_instant(as_of, field="API as_of")
        result = deepcopy(payload)
        fields = result["price"]["fields"]
        timestamp_index = fields.index("t")
        rows = [
            row for row in result["price"]["rows"]
            if parse_instant(row[timestamp_index]) <= cutoff
        ]
        transitions = [
            row for row in result["transitions"]
            if parse_instant(row["published_at"]) <= cutoff
        ]
        result["price"]["rows"] = rows
        state_fields = result["states"]["fields"]
        state_timestamp_index = state_fields.index("t")
        result["states"]["rows"] = [
            row for row in result["states"]["rows"]
            if parse_instant(row[state_timestamp_index]) <= cutoff
        ]
        oi_block = result.get("futures_oi")
        if isinstance(oi_block, dict):
            oi_fields = oi_block.get("fields", [])
            oi_timestamp_index = oi_fields.index("t")
            oi_block["rows"] = [
                row for row in oi_block.get("rows", [])
                if parse_instant(row[oi_timestamp_index]) <= cutoff
            ]
        strike_block = result.get("option_strike_oi")
        if isinstance(strike_block, dict):
            strike_fields = strike_block.get("fields", [])
            strike_timestamp_index = strike_fields.index("t")
            strike_block["rows"] = [
                row for row in strike_block.get("rows", [])
                if parse_instant(row[strike_timestamp_index]) <= cutoff
            ]
            selection = strike_block.get("strike_selection")
            if isinstance(selection, dict) and selection.get("available") is True:
                selected_at = parse_instant(
                    selection.get("selected_at"), field="strike selection receipt timestamp"
                )
                if selected_at > cutoff:
                    strike_block["strike_selection"] = {
                        "available": False,
                        "rule": selection.get("rule"),
                        "reason": "AWAITING_FIRST_COMPLETE_CHAIN_RECEIPT",
                        "volume_retained": False,
                        "CE": [],
                        "PE": [],
                    }
                    strike_block["volume_retained"] = False
        cash_block = result.get("cash_participation")
        if isinstance(cash_block, dict):
            cash_fields = cash_block.get("fields", [])
            cash_timestamp_index = cash_fields.index("t")
            cash_block["rows"] = [
                row for row in cash_block.get("rows", [])
                if parse_instant(row[cash_timestamp_index]) <= cutoff
            ]
        intraday_block = result.get("intraday_inventory")
        if isinstance(intraday_block, dict):
            intraday_fields = intraday_block.get("fields", [])
            intraday_timestamp_index = intraday_fields.index("t")
            intraday_block["rows"] = [
                row for row in intraday_block.get("rows", [])
                if parse_instant(row[intraday_timestamp_index]) <= cutoff
            ]
        result["transitions"] = transitions
        zones = []
        for source in result.get("confirmed_zones", []):
            if parse_instant(source["confirmed_at"], field="zone confirmation time") > cutoff:
                continue
            row = dict(source)
            if row.get("ended_at") is not None and parse_instant(
                row["ended_at"], field="zone terminal time"
            ) > cutoff:
                row["ended_at"] = None
                row["terminal_state"] = None
            zones.append(row)
        result["confirmed_zones"] = zones
        summary = result["summary"]
        summary["basis_observation_count"] = len(rows)
        summary["evidence_snapshot_count"] = len(result["states"]["rows"])
        summary["transition_count"] = len(transitions)
        summary["transition_states"] = dict(sorted(Counter(
            str(row["state"]) for row in transitions
        ).items()))
        summary["first_observation"] = None if not rows else rows[0][timestamp_index]
        summary["last_observation"] = None if not rows else rows[-1][timestamp_index]
        result["availability"] = {
            "mode": "PREFIX_ONLY",
            "as_of": iso_utc(cutoff),
            "future_observations_returned": False,
            "future_futures_oi_returned": False,
            "future_option_strike_oi_returned": False,
            "future_option_strike_volume_returned": False,
            "future_cash_participation_returned": False,
            "future_intraday_inventory_returned": False,
            "future_transitions_returned": False,
        }
        return result
