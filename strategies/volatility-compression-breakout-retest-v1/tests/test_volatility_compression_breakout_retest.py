import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from vp_bot.volatility_compression_breakout_retest import atr_wilder, detect, execute

UTC=timezone.utc
def h(t,o,h,l,c): return {"open_time":t.isoformat().replace("+00:00","Z"),"open":str(o),"high":str(h),"low":str(l),"close":str(c),"complete_60_distinct_minutes":"True"}
def m(t,o,h,l,c): return {"open_time":t.isoformat().replace("+00:00","Z"),"open":str(o),"high":str(h),"low":str(l),"close":str(c),"volume":"1"}

class CompressionTests(unittest.TestCase):
    def test_atr_is_wilder_and_fixed_at_breakout(self):
        rows=[h(datetime(2025,1,1,tzinfo=UTC)+timedelta(hours=i),100,102,98,100) for i in range(20)]
        a=atr_wilder(rows); self.assertEqual(a[13],Decimal(4)); self.assertEqual(a[14],Decimal(4))
    def test_execute_target_is_exactly_two_r_and_time_exit(self):
        t=datetime(2025,1,1,tzinfo=UTC); mins=[m(t+timedelta(minutes=i),100,100,100,100) for i in range(721)]
        s={"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99","atr_breakout":"1","status":"SIGNAL"}; r=execute(s,mins)
        self.assertEqual(r["exit_reason"],"TIME_EXIT"); self.assertEqual(Decimal(r["target"]),Decimal(r["entry_fill"])+2*(Decimal(r["entry_fill"])-Decimal(r["stop"])))
    def test_missing_future_data_is_incomplete(self):
        t=datetime(2025,1,1,tzinfo=UTC); s={"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99","atr_breakout":"1","status":"SIGNAL"}; r=execute(s,[m(t,100,100,100,100)])
        self.assertEqual(r["status"],"DATA_INCOMPLETE")
    def test_short_is_mirror_of_long_fill_direction(self):
        t=datetime(2025,1,1,tzinfo=UTC); rows=[m(t+timedelta(minutes=i),100,100,100,100) for i in range(721)]
        l=execute({"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99","atr_breakout":"2","status":"SIGNAL"},rows); s=execute({"direction":"SHORT","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"101","atr_breakout":"2","status":"SIGNAL"},rows)
        self.assertGreater(Decimal(l["entry_fill"]),Decimal(s["entry_fill"])); self.assertEqual(Decimal(l["r"]),Decimal(s["r"]))
    def test_minimum_stop_is_inclusive_and_smaller_is_skipped(self):
        t=datetime(2025,1,1,tzinfo=UTC); rows=[m(t+timedelta(minutes=i),100,100,100,100) for i in range(721)]
        ok=execute({"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99.5","atr_breakout":"1","status":"SIGNAL"},rows)
        skip=execute({"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99.6","atr_breakout":"1","status":"SIGNAL"},rows)
        self.assertEqual(ok["status"],"TRADE"); self.assertEqual(skip["reason"],"STOP_DISTANCE_LT_0_5_ATR")
    def test_ambiguous_minute_is_stop_first(self):
        t=datetime(2025,1,1,tzinfo=UTC); rows=[m(t,100,103,97,100)]+[m(t+timedelta(minutes=i),100,100,100,100) for i in range(1,721)]
        r=execute({"direction":"LONG","entry_time":t.isoformat().replace("+00:00","Z"),"stop":"99","atr_breakout":"1","status":"SIGNAL"},rows)
        self.assertEqual(r["exit_reason"],"STOP"); self.assertEqual(r["ambiguous"],"True")
    def test_no_future_compression_without_720_history(self):
        t=datetime(2025,1,1,tzinfo=UTC); hours=[h(t+timedelta(hours=i),100,101,99,100) for i in range(100)]; episodes,trades=detect(hours,[],"2025-01-01T00:00:00","2025-01-10T00:00:00"); self.assertEqual(episodes,[])

if __name__=="__main__": unittest.main()
