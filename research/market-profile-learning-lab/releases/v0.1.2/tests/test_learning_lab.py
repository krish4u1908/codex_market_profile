from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from banknifty_market_profile_lab.candidates import (
    create_seed_candidates,
    generate_codex_candidates,
    seed_specs,
    validate_agent_spec,
    validate_structured_output_schema,
)
from banknifty_market_profile_lab.dataset import build_dataset
from banknifty_market_profile_lab.io_utils import (
    atomic_json,
    atomic_jsonl,
    canonical_json,
    iso_utc,
    sha256_file,
)
from banknifty_market_profile_lab.profiles import Contribution, developing_rows
from banknifty_market_profile_lab.report import generate_report, verify_learning_run
from banknifty_market_profile_lab.scoring import evaluate_split


def pack(rows: list[dict[str, object]], fields: list[str]) -> dict[str, object]:
    return {"fields": fields, "rows": [[row.get(field) for field in fields] for row in rows]}


class LearningLabEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run_root = self.root / "runs"
        self.gui_root = self.root / "gui"
        self.run_root.mkdir()
        (self.gui_root / "sessions").mkdir(parents=True)
        self.sessions = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
        for index, session in enumerate(self.sessions):
            self._write_session(session, index)
        atomic_json(self.gui_root / "catalog.json", {
            "schema": "NEW_DIVERGENCE_DYNAMIC_SESSION_CATALOG_V2",
            "sessions": [
                {
                    "session": session,
                    "eligible": True,
                    "payload": f"sessions/{session}.json",
                    "run_integrity": {"valid": True},
                }
                for session in self.sessions
            ],
        })
        self.config = self.root / "learning.json"
        atomic_json(self.config, {
            "schema": "BANKNIFTY_MARKET_PROFILE_LEARNING_CONFIG_V1",
            "experiment_name": "synthetic-test",
            "classification": "RESEARCH_ONLY_NOT_A_TRADING_SIGNAL",
            "splits": {
                "train": self.sessions[:2],
                "validation": [self.sessions[2]],
                "holdout": [self.sessions[3]],
            },
            "horizons_minutes": [5, 15, 30],
            "direction_threshold_points": 25.0,
            "direction_sensitivity_points": [15.0, 25.0, 40.0],
            "profile_bin_points": 25,
            "value_area_fraction": 0.7,
            "max_index_age_seconds": 5.0,
            "episode_merge_seconds": 0.0,
            "level_touch_tolerance_points": 15.0,
            "level_reaction_points": 25.0,
            "level_breach_points": 15.0,
            "maximum_levels_each_side": 2,
            "minimum_training_sessions": 1,
            "minimum_validation_sessions": 1,
            "minimum_holdout_sessions": 1,
        })

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_session(self, session: str, index: int) -> None:
        directory = self.run_root / session
        directory.mkdir()
        start = datetime.fromisoformat(session).replace(tzinfo=timezone.utc) + timedelta(hours=4, minutes=15)
        # Alternate trends so all three direction classes appear in the fixture.
        trend = (1.5, -1.5, 0.2, 2.0)[index]
        base = 50000.0 + index * 100
        observations = []
        for second in range(0, 2401, 5):
            timestamp = start + timedelta(seconds=second)
            if second < 10:
                price = base
            elif second < 20:
                price = base + 25
            else:
                price = base + trend * (second - 20) / 5
            observations.append({
                "timestamp": iso_utc(timestamp),
                "index_receipt_timestamp": iso_utc(timestamp),
                "index_price": price,
                "futures_price": price + 40,
                "basis": 40.0,
            })
        basis_path = directory / "basis_observations.jsonl"
        atomic_jsonl(basis_path, observations)

        volume_times = [start, start + timedelta(seconds=5), start + timedelta(seconds=10)]
        futures_market = [
            {
                "t": iso_utc(timestamp),
                "p": base + 40 + position * 25,
                "v": (100.0, 110.0, 250.0)[position],
                "symbol": "NSE:BANKNIFTYFUT",
                "event_id": f"vol-{session}-{position}",
            }
            for position, timestamp in enumerate(volume_times)
        ]
        futures_market_path = directory / "futures_market.jsonl"
        atomic_jsonl(futures_market_path, futures_market)

        t1, t2, t3, t4 = (
            start + timedelta(seconds=5),
            start + timedelta(seconds=10),
            start + timedelta(seconds=15),
            start + timedelta(seconds=20),
        )
        futures_oi = [
            {"t": iso_utc(t1), "oi": 1000, "d": 10, "p": base + 40, "symbol": "NSE:BANKNIFTYFUT", "event_id": f"foi-{session}-1"},
            {"t": iso_utc(t2), "oi": 1100, "d": 100, "p": base + 65, "symbol": "NSE:BANKNIFTYFUT", "event_id": f"foi-{session}-2"},
            {"t": iso_utc(t3), "oi": 1090, "d": -10, "p": base + 65, "symbol": "NSE:BANKNIFTYFUT", "event_id": f"foi-{session}-3"},
            {"t": iso_utc(t4), "oi": 990, "d": -100, "p": base + 40, "symbol": "NSE:BANKNIFTYFUT", "event_id": f"foi-{session}-4"},
        ]
        option_rows = []
        for option_type, symbol in (("CE", "NSE:TESTCE"), ("PE", "NSE:TESTPE")):
            for position, (timestamp, delta, price_offset) in enumerate(
                ((t1, 10, 0), (t2, 100, 25), (t3, -10, 25), (t4, -100, 0)), 1
            ):
                option_rows.append({
                    "t": iso_utc(timestamp),
                    "e": "2026-01-29",
                    "k": option_type,
                    "s": base,
                    "oi": 1000 + delta,
                    "d": delta,
                    "p": 100 - position,
                    "v": 1000 + position * 10,
                    "dv": 10,
                    "vs": "VALID",
                    "symbol": symbol,
                    "event_id": f"opt-{session}-{option_type}-{position}",
                })

        contributions = []
        for row in futures_oi:
            timestamp = datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
            price = next(item["index_price"] for item in observations if item["timestamp"] == row["t"])
            contributions.append(Contribution(
                timestamp=timestamp,
                family="FUT_POS_OI_VPOC" if row["d"] > 0 else "FUT_NEG_OI_VPOC",
                index_price=float(price),
                weight=abs(float(row["d"])),
                source_id=str(row["event_id"]),
                session=session,
            ))
        for row in option_rows:
            timestamp = datetime.fromisoformat(str(row["t"]).replace("Z", "+00:00"))
            price = next(item["index_price"] for item in observations if item["timestamp"] == row["t"])
            contributions.append(Contribution(
                timestamp=timestamp,
                family=f"{row['k']}_{'POS' if row['d'] > 0 else 'NEG'}_OI_VPOC",
                index_price=float(price),
                weight=abs(float(row["d"])),
                source_id=f"{row['event_id']}:{row['symbol']}",
                session=session,
            ))
        for position, timestamp in enumerate(volume_times[1:], 1):
            price = next(item["index_price"] for item in observations if item["timestamp"] == iso_utc(timestamp))
            delta = (10.0, 140.0)[position - 1]
            contributions.append(Contribution(
                timestamp=timestamp,
                family="BN_REF_FUT_VOLUME_VPOC",
                index_price=float(price),
                weight=delta,
                source_id=f"vol-{session}-{position}",
                session=session,
            ))
        inventory = developing_rows(
            contributions,
            session=session,
            bin_points=25,
            value_area_fraction=0.7,
        )
        inventory_fields = [
            "t", "scope", "family", "status", "control_value",
            "value_area_low", "value_area_high", "value_area_target_fraction",
            "value_area_achieved_fraction", "total_weight", "evidence_count",
            "source_sessions", "tie_break_reason",
        ]
        # Trigger ids are a lab-only reconstruction field and are not published
        # by the v1.0.19 browser payload.
        published_inventory = [
            {key: value for key, value in row.items() if key != "trigger_source_ids"}
            for row in inventory
        ]
        states = [
            {"t": iso_utc(start), "s": "NEUTRAL_BLUE", "n": 1},
            {"t": iso_utc(start + timedelta(minutes=10)), "s": "GREEN", "n": 2},
        ]
        payload = {
            "schema": "NEW_DIVERGENCE_BROWSER_PAYLOAD_V1",
            "session": session,
            "config": {"participation_max_age_seconds": 120.0},
            "intraday_inventory": {
                "analysis_start": iso_utc(start),
                **pack(published_inventory, inventory_fields),
            },
            "futures_oi": pack(futures_oi, ["t", "oi", "d", "p", "symbol", "event_id"]),
            "option_strike_oi": {
                **pack(option_rows, ["t", "e", "k", "s", "oi", "d", "p", "v", "dv", "vs", "symbol", "event_id"]),
                "strike_selection": {
                    "available": True,
                    "selected_at": iso_utc(start),
                    "CE": [{"symbol": "NSE:TESTCE"}],
                    "PE": [{"symbol": "NSE:TESTPE"}],
                },
            },
            "states": pack(states, ["t", "s", "n"]),
        }
        atomic_json(self.gui_root / "sessions" / f"{session}.json", payload)
        files = {
            "basis": basis_path.name,
            "futures_market": futures_market_path.name,
        }
        summary = {
            "schema": "NEW_DIVERGENCE_RUN_V1",
            "session": session,
            "files": files,
            "artifact_sha256": {
                key: sha256_file(directory / relative) for key, relative in files.items()
            },
        }
        atomic_json(directory / "summary.json", summary)

    def _remove_optional_futures_market_artifact(
        self, session: str, *, remove_published_volume: bool = True
    ) -> None:
        directory = self.run_root / session
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["files"].pop("futures_market")
        summary["artifact_sha256"].pop("futures_market")
        atomic_json(summary_path, summary)
        (directory / "futures_market.jsonl").unlink()

        if remove_published_volume:
            payload_path = self.gui_root / "sessions" / f"{session}.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            inventory = payload["intraday_inventory"]
            family_position = inventory["fields"].index("family")
            inventory["rows"] = [
                row for row in inventory["rows"]
                if row[family_position] != "BN_REF_FUT_VOLUME_VPOC"
            ]
            inventory["futures_market_retained"] = False
            atomic_json(payload_path, payload)

    def test_end_to_end_and_holdout_freeze(self) -> None:
        learning_run = self.root / "learning-run"
        manifest = build_dataset(
            run_root=self.run_root,
            gui_root=self.gui_root,
            config_path=self.config,
            output_root=learning_run,
        )
        self.assertEqual(manifest["counts"]["train"]["sessions"], 2)
        self.assertGreater(manifest["counts"]["train"]["episodes"], 0)
        created = create_seed_candidates(learning_run)
        self.assertEqual(len(created), 3)
        train = evaluate_split(learning_run, split="train")
        validation = evaluate_split(learning_run, split="validation")
        self.assertTrue(train["scores"])
        self.assertTrue(validation["scores"])
        with self.assertRaises(RuntimeError):
            evaluate_split(learning_run, split="holdout")
        holdout = evaluate_split(learning_run, split="holdout", open_holdout=True)
        self.assertTrue(holdout["scores"])
        with self.assertRaises(RuntimeError):
            create_seed_candidates(learning_run)
        report = generate_report(learning_run)
        self.assertIn("Holdout: **OPENED**", report.read_text(encoding="utf-8"))
        verification = verify_learning_run(learning_run)
        self.assertTrue(verification["valid"], verification["reasons"])

    def test_candidate_specs_validate(self) -> None:
        learning_run = self.root / "learning-run"
        build_dataset(
            run_root=self.run_root,
            gui_root=self.gui_root,
            config_path=self.config,
            output_root=learning_run,
        )
        for row in create_seed_candidates(learning_run):
            spec = json.loads(
                (Path(row["path"]) / "references" / "agent-spec.json").read_text()
            )
            self.assertEqual(validate_agent_spec(spec)["schema"], "BANKNIFTY_MARKET_PROFILE_AGENT_SPEC_V1")

    def test_optional_futures_market_artifact_can_be_absent(self) -> None:
        legacy_session = self.sessions[-1]
        self._remove_optional_futures_market_artifact(legacy_session)
        learning_run = self.root / "learning-run"
        build_dataset(
            run_root=self.run_root,
            gui_root=self.gui_root,
            config_path=self.config,
            output_root=learning_run,
        )
        audit = json.loads(
            (learning_run / "metadata/session_audit.json").read_text(encoding="utf-8")
        )
        row = next(item for item in audit["sessions"] if item["session"] == legacy_session)
        self.assertFalse(row["futures_market_retained"])
        self.assertFalse(row["bn_reference_futures_volume_available"])
        self.assertEqual(row["inventory_equivalence"], "PASS")

    def test_missing_futures_market_cannot_silently_accept_published_volume(self) -> None:
        legacy_session = self.sessions[-1]
        self._remove_optional_futures_market_artifact(
            legacy_session, remove_published_volume=False
        )
        with self.assertRaisesRegex(ValueError, "reconstructed inventory count"):
            build_dataset(
                run_root=self.run_root,
                gui_root=self.gui_root,
                config_path=self.config,
                output_root=self.root / "learning-run",
            )

    def test_response_schemas_meet_strict_object_and_type_rules(self) -> None:
        release_root = Path(__file__).resolve().parents[1]
        for name in ("agent-spec.schema.json", "forecast.schema.json"):
            schema = json.loads(
                (release_root / "schemas" / name).read_text(encoding="utf-8")
            )
            self.assertEqual(validate_structured_output_schema(schema)["type"], "object")
        with self.assertRaisesRegex(ValueError, "enum/const declaration lacks type"):
            validate_structured_output_schema({
                "type": "object",
                "additionalProperties": False,
                "required": ["schema"],
                "properties": {"schema": {"const": "BROKEN"}},
            })

    def test_candidate_generation_resumes_after_preserved_failed_workspace(self) -> None:
        learning_run = self.root / "learning-run"
        build_dataset(
            run_root=self.run_root,
            gui_root=self.gui_root,
            config_path=self.config,
            output_root=learning_run,
        )
        atomic_json(
            learning_run / "metadata/codex_profile_verified.json",
            {"outside_read": "DENIED"},
        )
        failed_workspace = learning_run / "candidate_workspaces/codex-01"
        failed_workspace.mkdir()
        (failed_workspace / "stdout.txt").write_text("failed\n", encoding="utf-8")

        responses = []
        for index, source in enumerate(seed_specs(), 1):
            spec = dict(source)
            spec["name"] = f"codex-resume-test-{index}"
            responses.append(json.dumps(spec))

        completed = [
            subprocess.CompletedProcess(
                args=["codex"], returncode=0, stdout=response, stderr=""
            )
            for response in responses
        ]
        schema = Path(__file__).resolve().parents[1] / "schemas/agent-spec.schema.json"
        with (
            patch(
                "banknifty_market_profile_lab.candidates._codex_config_preflight",
                return_value={"profile": "test"},
            ),
            patch(
                "banknifty_market_profile_lab.candidates.subprocess.run",
                side_effect=completed,
            ) as run_mock,
        ):
            first = generate_codex_candidates(
                learning_run,
                schema_path=schema,
                codex_bin=Path("/fake/codex"),
                profile="banknifty-learning",
                count=3,
            )
            second = generate_codex_candidates(
                learning_run,
                schema_path=schema,
                codex_bin=Path("/fake/codex"),
                profile="banknifty-learning",
                count=3,
            )

        self.assertEqual(run_mock.call_count, 3)
        self.assertEqual(first, second)
        self.assertTrue(failed_workspace.is_dir())
        self.assertFalse((failed_workspace / "generation-result.json").exists())
        self.assertTrue(
            (learning_run / "candidate_workspaces/codex-01-attempt-02/generation-result.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
