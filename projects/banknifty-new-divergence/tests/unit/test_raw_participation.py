from datetime import datetime,timedelta,timezone
import unittest
from banknifty_profiler.participation.raw_engine import elapsed_change,window_increment,timing_cohort,conservative_semantic,select_strikes,option_inventory_state,asof,deterministic_id

class RawParticipationTests(unittest.TestCase):
 def setUp(self):
  self.t=datetime(2026,8,20,10,0,tzinfo=timezone(timedelta(hours=5,minutes=30)))
 def test_elapsed_windows_not_offsets(self):
  rows=[{'receipt':self.t-timedelta(seconds=61),'x':10},{'receipt':self.t-timedelta(seconds=1),'x':14}]
  self.assertEqual(elapsed_change(rows,self.t,'x',1),4)
 def test_volume_open_closed_boundary(self):
  rows=[{'receipt':self.t-timedelta(minutes=5),'v':10},{'receipt':self.t-timedelta(minutes=4,seconds=59),'v':12},{'receipt':self.t,'v':20}]
  self.assertEqual(window_increment(rows,self.t,'v',5)[0],8)
 def test_reset_not_negative(self):
  rows=[{'receipt':self.t-timedelta(minutes=2),'v':100},{'receipt':self.t-timedelta(minutes=1),'v':3},{'receipt':self.t,'v':8}]
  self.assertEqual(window_increment(rows,self.t,'v',5),(5.0,'RESET'))
 def test_timing(self): self.assertEqual(timing_cohort(self.t,self.t+timedelta(seconds=61)),'NEW_WITHIN_3_MINUTES')
 def test_conservative_exception(self): self.assertEqual(conservative_semantic('GREEN','CE',-1,-1,None),'NEUTRAL_AMBIGUOUS')
 def test_expiry_isolation_and_determinism(self):
  c=[{'expiry':'25-08-2026','strike':x,'option_type':'CE'} for x in (57000,57100,57200)]+[{'expiry':'29-09-2026','strike':57100,'option_type':'CE'}]
  selected,expiry,atm=select_strikes(c,57120,100,1);self.assertEqual(expiry,'25-08-2026');self.assertEqual(atm,57100);self.assertTrue(all(x['expiry']==expiry for x in selected))
 def test_asof_never_future(self):
  rows=[{'receipt':self.t-timedelta(seconds=1),'x':1},{'receipt':self.t+timedelta(seconds=1),'x':2}]
  self.assertEqual(asof(rows,self.t)['x'],1)
 def test_missing_preserved(self): self.assertIsNone(elapsed_change([],self.t,'oi',5))
 def test_unchanged_oi_is_zero(self):
  rows=[{'receipt':self.t-timedelta(minutes=6),'oi':10},{'receipt':self.t,'oi':10}]
  self.assertEqual(elapsed_change(rows,self.t,'oi',5),0)
 def test_semantic_matrix_32_cells(self):
  for colour in ('GREEN','RED'):
   for typ in ('CE','PE'):
    for oi in (-1,1):
     for premium in (-1,1):
      for _volume_spike in (False,True):
       self.assertIn(conservative_semantic(colour,typ,oi,premium,None),{'SUPPORTIVE','CONTRADICTORY','NEUTRAL_AMBIGUOUS'})
 def test_option_state_probabilistic(self): self.assertEqual(option_inventory_state(1,-1),'PROBABLE_WRITING_OR_SUPPLY')
 def test_deterministic_participation_id(self): self.assertEqual(deterministic_id('a','b'),deterministic_id('a','b'))
if __name__=='__main__':unittest.main()
