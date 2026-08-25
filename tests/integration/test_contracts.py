import json,unittest
from pathlib import Path
from banknifty_profiler.lifecycle.engine import SYNC_TOLERANCE_MS, STALLED_SECONDS

class ContractTests(unittest.TestCase):
    def test_frozen_counts_fixture(self):
        d=json.loads((Path(__file__).parents[1]/"fixtures/frozen_counts.json").read_text())
        self.assertEqual((d["episodes"],d["green"],d["red"],d["retriggers"]),(65,41,24,14))
    def test_clock_thresholds(self): self.assertEqual((SYNC_TOLERANCE_MS,STALLED_SECONDS),(2000.0,60.0))

if __name__ == "__main__": unittest.main()

