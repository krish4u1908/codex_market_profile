import csv,json,os,unittest
from datetime import datetime
from pathlib import Path

def dt(v):return datetime.fromisoformat(v.replace(' ','T'))
class R6B3RViewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  value=os.environ.get('R6B3R_OUTPUT_ROOT');cls.root=Path(value) if value else None
 def require(self):
  if self.root is None:self.skipTest('R6B3R_OUTPUT_ROOT not supplied')
 def rows(self,name):
  with (self.root/name).open(newline='') as f:return list(csv.DictReader(f))
 def test_dense_partition_byte_identity(self):
  self.require();rows=self.rows('deterministic_run_comparison.csv');parts=[r for r in rows if r.get('source_rows')]
  self.assertEqual(len(parts),2);self.assertTrue(all(r['byte_identical']=='True' and r['difference_count']=='0' for r in parts))
 def test_exactly_65_summaries(self):self.require();self.assertEqual(len(self.rows('episode_participation_summary.csv')),65)
 def test_transition_ids_unique(self):
  self.require();rows=self.rows('transition_participation_ledger.csv');self.assertEqual(len(rows),len({r['transition_id'] for r in rows}))
 def test_joint_clock_is_max_constituent(self):
  self.require()
  for r in self.rows('episode_participation_summary.csv'):
   values=[r[k] for k in ('first_futures_qualifying_timestamp','first_ce_qualifying_timestamp','first_pe_qualifying_timestamp','first_breadth_timestamp') if r[k]]
   self.assertEqual(dt(r['first_joint_participation_timestamp']),max(map(dt,values)))
 def test_no_transition_backdating(self):
  self.require();self.assertTrue(all(dt(r['effective_timestamp'])<=dt(r['calculation_timestamp']) for r in self.rows('transition_participation_ledger.csv')))
 def test_compatibility_snapshot_not_backdated(self):
  self.require()
  for r in self.rows('legacy_compatibility_snapshot.csv'):
   clocks=[r['confirmation_time_futures_snapshot'],r['futures_effective_timestamp'],r['option_joint_effective_timestamp']]
   clocks=[dt(x) for x in clocks if x];self.assertGreaterEqual(dt(r['snapshot_timestamp']),max(clocks))
   self.assertIn('LOSSY, NOT RAW AUTHORITY',r['compatibility_label'])
 def test_stream_batch_identity(self):
  self.require();rows=[r for r in self.rows('deterministic_run_comparison.csv') if r.get('comparison_type')=='STREAM_BATCH'];self.assertEqual(len(rows),5);self.assertTrue(all(r['byte_identical']=='True' for r in rows))
 def test_prohibited_ab_opens_zero(self):
  self.require();rows=self.rows('file_open_audit.csv');self.assertFalse(any(r['phase']=='A_B_CANONICAL_INPUT' and ('clean_combined_profiler_r4' in r['path'] or 'clean_combined_profiler_r5' in r['path']) for r in rows))
 def test_no_unexplained(self):self.require();self.assertTrue(all(r['unexplained_remainder']=='0' for r in self.rows('compatibility_reconciliation.csv')))
 def test_no_trading_fields(self):
  self.require();bad={'buy','sell','pnl','profit','outcome','target','stop'}
  for name in ('dense_participation_view.csv','transition_participation_ledger.csv','episode_participation_summary.csv','legacy_compatibility_snapshot.csv'):
   with (self.root/name).open(newline='') as f:self.assertFalse({x.lower() for x in next(csv.reader(f))}&bad)
