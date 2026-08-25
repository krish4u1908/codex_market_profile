import unittest
from banknifty_profiler.lifecycle.engine import classify_resolution, deterministic_transition_id, valid_synchronized_age

class LifecycleTests(unittest.TestCase):
    def test_index_catch_up(self):
        self.assertEqual(classify_resolution("GREEN", 100, 110, 106, 110, 0).mechanism, "INDEX_CATCH_UP")
    def test_index_catch_down(self):
        self.assertEqual(classify_resolution("RED", 100, 110, 94, 110, 0).mechanism, "INDEX_CATCH_DOWN")
    def test_futures_reversal(self):
        self.assertEqual(classify_resolution("GREEN", 100, 110, 100, 104, 0).mechanism, "FUTURES_REVERSED_TO_INDEX")
    def test_stalled_overrides(self):
        self.assertEqual(classify_resolution("GREEN", 100, 110, 100, 110, 60).mechanism, "BASIS_EXTREME_STALLED")
    def test_sync_boundary(self):
        self.assertTrue(valid_synchronized_age(2000)); self.assertFalse(valid_synchronized_age(2000.001)); self.assertFalse(valid_synchronized_age(-0.1))
    def test_deterministic_id(self):
        a=deterministic_transition_id("E1","2026-08-20T10:00:00+05:30","WAITING_FOR_PRICE_RESPONSE",1)
        self.assertEqual(a, deterministic_transition_id("E1","2026-08-20T10:00:00+05:30","WAITING_FOR_PRICE_RESPONSE",1))

if __name__ == "__main__": unittest.main()

