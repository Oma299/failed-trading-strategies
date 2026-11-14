import unittest
from datetime import datetime, timedelta, timezone

from vp_bot.range_reversal_delayed import annotate_signal, initial_first_return, local_pivot_stop, svg_signal


def iso(t): return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def bar(t, o, h, l, c): return {"open_time":iso(t),"close_time":iso(t+timedelta(minutes=5)-timedelta(microseconds=1)),"open":str(o),"high":str(h),"low":str(l),"close":str(c),"complete":"True"}
def signal(direction="SHORT"):
    return {"local_date":"2025-01-01","direction":direction,"range_upper":"100","range_lower":"90","breakout_time":"2025-01-01T08:00:00Z","confirmation_1_time":"2025-01-01T08:15:00Z","confirmation_2_time":"2025-01-01T08:20:00Z","confirmation_3_time":"2025-01-01T08:25:00Z","planned_entry_time":"2025-01-01T08:30:00Z","entry_open":"98","stop":"105","target_2r":"84","status":"SIGNAL","reason":""}

class DelayedTests(unittest.TestCase):
    def test_local_pivot_requires_two_bars_each_side_and_reports_known_time(self):
        t=datetime(2025,1,1,8,tzinfo=timezone.utc)
        m=[bar(t,101,105,99,101),bar(t+timedelta(minutes=5),101,104,99,101),bar(t+timedelta(minutes=10),101,110,98,101),bar(t+timedelta(minutes=15),101,103,99,101)]
        s=signal(); s["confirmation_1_time"]="2025-01-01T08:25:00Z"
        # only one right bar is available before first return, therefore no pivot
        self.assertIsNone(local_pivot_stop(s,m))
        m.append(bar(t+timedelta(minutes=20),101,102,99,101))
        self.assertIsNotNone(local_pivot_stop(s,m))
        self.assertEqual(local_pivot_stop(s,m)[2],"2025-01-01T08:24:59.999999Z")

    def test_target_is_fixed_from_e1_and_rr_is_from_e3(self):
        t=datetime(2025,1,1,8,tzinfo=timezone.utc)
        m=[bar(t,105,110,104,105),bar(t+timedelta(minutes=5),105,106,101,102),bar(t+timedelta(minutes=10),102,103,99,99),bar(t+timedelta(minutes=15),99,102,98,99),bar(t+timedelta(minutes=20),99,101,99,99),bar(t+timedelta(minutes=25),98,99,97,98)]
        s=signal(); s.update({"breakout_time":"2025-01-01T08:00:00Z","confirmation_1_time":"2025-01-01T08:05:00Z","confirmation_2_time":"2025-01-01T08:10:00Z","confirmation_3_time":"2025-01-01T08:15:00Z","stop":"110"})
        mins=[{"open_time":iso(t+timedelta(minutes=25)),"high":"99","low":"97","close":"98"}]
        out=annotate_signal(s,mins,m,"BREAKOUT_EXTREMUM_FIRST_RETURN")
        self.assertEqual(out["e1_time"],"2025-01-01T08:15:00Z"); self.assertEqual(out["e3_time"],"2025-01-01T08:20:00Z")
        self.assertNotEqual(out["target_fixed_n1"],"")

    def test_pre_entry_target_cancels_without_looking_after_e3(self):
        t=datetime(2025,1,1,8,tzinfo=timezone.utc); m=[bar(t,105,110,104,105),bar(t+timedelta(minutes=5),105,106,101,102),bar(t+timedelta(minutes=10),102,103,99,99),bar(t+timedelta(minutes=15),99,102,98,99),bar(t+timedelta(minutes=20),99,101,99,99)]
        s=signal(); s.update({"confirmation_1_time":"2025-01-01T08:05:00Z","confirmation_2_time":"2025-01-01T08:10:00Z","confirmation_3_time":"2025-01-01T08:15:00Z","e1_time":"2025-01-01T08:10:00Z","e3_time":"2025-01-01T08:20:00Z","e1_open":"102","e3_open":"100","target_fixed_n1":"86"})
        mins=[{"open_time":"2025-01-01T08:15:00Z","high":"200","low":"100","close":"150"},{"open_time":"2025-01-01T08:30:00Z","high":"1","low":"1","close":"1"}]
        out=annotate_signal(s,mins,m,"BREAKOUT_EXTREMUM_FIRST_RETURN")
        self.assertIn(out["delayed_reason"],("PRE_ENTRY_STOP","PRE_ENTRY_TARGET","PRE_ENTRY_BOTH_LEVELS"))

    def test_before_svg_scale_does_not_use_post_e1_extreme(self):
        t=datetime(2025,1,1,8,tzinfo=timezone.utc); m=[bar(t,105,110,104,105),bar(t+timedelta(minutes=5),105,106,101,102),bar(t+timedelta(minutes=10),102,103,99,101),bar(t+timedelta(minutes=15),101,102,98,100),bar(t+timedelta(minutes=20),100,101,99,100)]
        s=signal(); s.update({"confirmation_1_time":"2025-01-01T08:05:00Z","confirmation_2_time":"2025-01-01T08:10:00Z","confirmation_3_time":"2025-01-01T08:15:00Z","e1_time":"2025-01-01T08:10:00Z","e3_time":"2025-01-01T08:20:00Z","e1_open":"102","e3_open":"100","target_fixed_n1":"86"})
        rows=[{"open_time":iso(t+timedelta(minutes=25)),"high":"999999","low":"1","close":"1"}]
        a=svg_signal(s,rows,"before")
        rows[0]["high"]="2"; rows[0]["low"]="2"
        self.assertEqual(a,svg_signal(s,rows,"before"))

    def test_reset_keeps_initial_return_e1_stop_and_target(self):
        t=datetime(2025,1,1,8,tzinfo=timezone.utc)
        m=[bar(t,105,110,104,105), bar(t+timedelta(minutes=5),105,106,101,102),
           bar(t+timedelta(minutes=10),102,103,99,99),  # initial return
           bar(t+timedelta(minutes=15),101,104,99,104),  # reset
           bar(t+timedelta(minutes=20),104,105,99,101), bar(t+timedelta(minutes=25),101,103,99,99),
           bar(t+timedelta(minutes=30),99,102,98,98),  # final three inside
           bar(t+timedelta(minutes=35),98,101,97,97)]
        s=signal(); s.update({"confirmation_1_time":"2025-01-01T08:25:00Z","confirmation_2_time":"2025-01-01T08:30:00Z","confirmation_3_time":"2025-01-01T08:35:00Z"})
        first, reason=initial_first_return(s,m)
        self.assertEqual(first,"2025-01-01T08:10:00Z"); self.assertEqual(reason,"")
        out=annotate_signal(s,[],m,"BREAKOUT_EXTREMUM_FIRST_RETURN")
        self.assertEqual(out["initial_first_return_time"],first)
        self.assertEqual(out["e1_time"],"2025-01-01T08:15:00Z")

if __name__ == "__main__": unittest.main()
