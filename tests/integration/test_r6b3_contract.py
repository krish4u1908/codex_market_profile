import csv,json,os,unittest
from pathlib import Path

class R6B3ContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  value=os.environ.get('R6B3_OUTPUT_ROOT');cls.root=Path(value) if value else None
 def require(self):
  if self.root is None:self.skipTest('R6B3_OUTPUT_ROOT not supplied')
 def test_seals_and_prohibited_opens(self):
  self.require();a=json.loads((self.root/'runs/stream/seal.json').read_text());b=json.loads((self.root/'runs/batch/seal.json').read_text());self.assertEqual(a['futures_sha256'],b['futures_sha256']);self.assertEqual(a['options_sha256'],b['options_sha256']);self.assertEqual(a['prohibited_reference_opens'],0);self.assertEqual(b['prohibited_reference_opens'],0)
 def test_no_trading_or_outcome_fields(self):
  self.require()
  prohibited={'buy','sell','pnl','profit','outcome','target','stop'}
  for name in ('futures_participation.csv','option_participation.csv'):
   with (self.root/name).open(newline='') as f:fields={x.lower() for x in next(csv.reader(f))}
   self.assertFalse(fields & prohibited)
 def test_manual_reconciliation_minimum(self):
  self.require()
  with (self.root/'manual_reconciliation.csv').open(newline='') as f:rows=list(csv.DictReader(f))
  self.assertGreaterEqual(len(rows),150);self.assertTrue(all(r['manual_result']=='MATCH' for r in rows))
