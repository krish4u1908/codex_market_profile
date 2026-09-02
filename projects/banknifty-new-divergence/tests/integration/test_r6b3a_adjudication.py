import csv,json,os,unittest
from pathlib import Path

class R6B3AAdjudicationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=os.environ.get('R6B3A_OUTPUT_ROOT');cls.root=Path(root) if root else None
 def require(self):
  if self.root is None:self.skipTest('R6B3A_OUTPUT_ROOT not supplied')
 def rows(self,name):
  with (self.root/name).open(newline='') as f:return list(csv.DictReader(f))
 def test_all_269_classified_with_lineage(self):
  self.require();rows=self.rows('all_difference_classification.csv');self.assertEqual(len(rows),269)
  required=('difference_id','semantic_cause','raw_lineage','reference_lineage','recommended_authority','final_decision_reason')
  self.assertTrue(all(all(r[x] for x in required) for r in rows))
 def test_unexplained_zero(self):
  self.require();self.assertFalse(any('UNEXPLAINED' in r['semantic_cause'].upper() for r in self.rows('all_difference_classification.csv')))
 def test_views_are_separate(self):
  self.require();views=self.rows('view_contract.csv');self.assertEqual(len(views),4);self.assertEqual(len({r['view'] for r in views}),4)
 def test_clocks_not_backdated(self):
  self.require();self.assertTrue(all(r['backdating_permitted']=='NO' for r in self.rows('publication_clock_decision.csv')))
 def test_manual_minimum_and_no_outcomes(self):
  self.require();rows=self.rows('manual_reconciliation.csv');self.assertGreaterEqual(len(rows),160);self.assertTrue(all(r['outcomes_used']=='NO' for r in rows))
 def test_expiry_identity_preserved(self):
  self.require();rows=[r for r in self.rows('all_difference_classification.csv') if r['component'] in ('CE','PE') and r['r6b3_semantic']]
  self.assertTrue(all(r['r6b3_expiry'] for r in rows))
 def test_no_frozen_package_paths_are_outputs(self):
  self.require();self.assertFalse(any(p.name.startswith(('raw_divergence','raw_lifecycle','inventory')) for p in self.root.iterdir()))
if __name__=='__main__':unittest.main()
