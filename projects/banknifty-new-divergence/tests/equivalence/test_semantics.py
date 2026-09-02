import unittest
from banknifty_profiler.lifecycle.engine import classify_resolution

class EquivalenceTests(unittest.TestCase):
    def test_native_and_compatibility_are_separate(self):
        r=classify_resolution("GREEN",100,110,100,116,0)
        self.assertEqual(r.mechanism,"BASIS_EXPANSION_CONTINUING")
        self.assertEqual(r.compatibility_label,"REMAINED_EXTREME")
    def test_basis_identity(self):
        r=classify_resolution("RED",100,110,98,106,0)
        self.assertAlmostEqual(r.signed_convergence,-(-1*r.basis_change))

if __name__ == "__main__": unittest.main()

