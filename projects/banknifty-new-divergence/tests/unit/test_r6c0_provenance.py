import ast
import unittest
from pathlib import Path

import pandas as pd

from banknifty_profiler.divergence.detector import MATCH_MS,causal_basis
from banknifty_profiler.inventory.context import context_at


class R6C0ProvenanceTests(unittest.TestCase):
    def frame(self,index_time,futures_time):
        return pd.DataFrame([
            {"symbol":"INDEX","receipt_timestamp":pd.Timestamp(index_time),"last_price":100.0,"source_file":"raw","source_row":1},
            {"symbol":"FUT","receipt_timestamp":pd.Timestamp(futures_time),"last_price":110.0,"source_file":"raw","source_row":2},
        ])

    def test_frozen_sync_limit(self):self.assertEqual(MATCH_MS,2000)
    def test_backward_join_valid(self):
        rows=causal_basis(self.frame("2026-08-11T09:15:00+05:30","2026-08-11T09:15:01+05:30"),"2026-08-11","INDEX","FUT")
        self.assertEqual((rows[0]["basis_value"],rows[0]["validity_status"]),(10.0,"VALID"))
    def test_future_join_never_used(self):
        rows=causal_basis(self.frame("2026-08-11T09:15:02+05:30","2026-08-11T09:15:01+05:30"),"2026-08-11","INDEX","FUT")
        self.assertEqual(rows[0]["validity_status"],"UNMATCHED_NO_PRIOR_INDEX")
    def test_over_tolerance_rejected(self):
        rows=causal_basis(self.frame("2026-08-11T09:15:00+05:30","2026-08-11T09:15:03+05:30"),"2026-08-11","INDEX","FUT")
        self.assertEqual(rows[0]["validity_status"],"UNMATCHED_TOLERANCE_EXCEEDED")
    def test_context_is_causal(self):
        controls=[{"evaluation_date":"2026-08-11","horizon":"ID","family":"FUT_POS_OI_VPOC","control_value":100,"control_effective_timestamp":"2026-08-11T10:00:00+05:30"},{"evaluation_date":"2026-08-11","horizon":"ID","family":"FUT_POS_OI_VPOC","control_value":200,"control_effective_timestamp":"2026-08-11T10:02:00+05:30"}]
        result=context_at(controls,"2026-08-11","2026-08-11T10:01:00+05:30",101)
        self.assertEqual(result["nearest_control"]["value"],100)
    def test_runtime_module_has_no_dynamic_import(self):
        root=Path(__file__).parents[2]/"src"/"banknifty_profiler"
        for path in root.rglob("*.py"):
            tree=ast.parse(path.read_text())
            calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
            self.assertFalse(any(isinstance(node.func,ast.Attribute) and node.func.attr in {"spec_from_file_location","SourceFileLoader"} for node in calls),path)


if __name__=="__main__":unittest.main()
