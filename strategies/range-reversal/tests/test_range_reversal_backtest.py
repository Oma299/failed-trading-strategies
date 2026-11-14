import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from vp_bot.range_reversal_backtest import simulate_trade


def iso(t): return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def minute(t, o, h, l, c): return {"open_time":iso(t),"open":str(o),"high":str(h),"low":str(l),"close":str(c),"volume":"1"}
def signal(direction="LONG"):
    return {"local_date":"2025-01-01","direction":direction,"breakout_time":"2025-01-01T08:00:00Z","initial_first_return_time":"2025-01-01T08:05:00Z","confirmation_1_time":"2025-01-01T08:10:00Z","confirmation_2_time":"2025-01-01T08:15:00Z","confirmation_3_time":"2025-01-01T08:20:00Z","e1_time":"2025-01-01T08:10:00Z","e3_time":"2025-01-01T08:25:00Z","stop":"95","target_fixed_n1":"110","actual_rr_from_e3":"2","delayed_status":"ANNOTATION","delayed_reason":""}

class RangeReversalBacktestTests(unittest.TestCase):
    def test_long_target_and_commission_slippage(self):
        s=signal(); rows=[minute(datetime(2025,1,1,8,25,tzinfo=timezone.utc),100,111,99,108)]
        r=simulate_trade(s,rows)
        self.assertEqual(r["outcome"],"TARGET"); self.assertEqual(r["ambiguous"],"False")
        self.assertGreater(Decimal(r["commission_per_btc"]), Decimal("0")); self.assertGreater(Decimal(r["slippage_cost_per_btc"]), Decimal("0"))

    def test_short_target_uses_adverse_fills(self):
        s=signal("SHORT"); s.update({"stop":"105","target_fixed_n1":"90"})
        r=simulate_trade(s,[minute(datetime(2025,1,1,8,25,tzinfo=timezone.utc),100,101,89,90)])
        self.assertEqual(r["outcome"],"TARGET"); self.assertLess(Decimal(r["entry_fill"]), Decimal("100")); self.assertGreater(Decimal(r["exit_fill"]), Decimal("90"))

    def test_stop_gap_executes_at_open(self):
        s=signal(); t=datetime(2025,1,1,8,25,tzinfo=timezone.utc); r=simulate_trade(s,[minute(t,100,100,99,100),minute(t+timedelta(minutes=1),94,100,93,95)])
        self.assertEqual(r["outcome"],"STOP"); self.assertEqual(Decimal(r["exit_base"]), Decimal("94"))

    def test_same_minute_stop_target_stop_first_ambiguous(self):
        s=signal(); r=simulate_trade(s,[minute(datetime(2025,1,1,8,25,tzinfo=timezone.utc),100,111,94,100)])
        self.assertEqual(r["outcome"],"STOP"); self.assertEqual(r["ambiguous"],"True")

    def test_target_open_with_later_stop_touch_is_still_stop_first(self):
        s=signal(); r=simulate_trade(s,[minute(datetime(2025,1,1,8,25,tzinfo=timezone.utc),109,112,94,100)])
        self.assertEqual(r["outcome"],"STOP"); self.assertEqual(r["ambiguous"],"True")

    def test_rebased_target_uses_actual_entry_fill_and_fixed_stop(self):
        s=signal(); s["stop"]="95"; s["target_fixed_n1"]="110"
        t=datetime(2025,1,1,8,25,tzinfo=timezone.utc)
        r=simulate_trade(s,[minute(t,100,111,99,108)],target_mode="E3_2R")
        # Long entry fill is 100.02; B target is 2R from that fill: 110.06.
        self.assertEqual(r["target_mode"],"E3_2R")
        self.assertEqual(Decimal(r["target_used"]), Decimal("110.06"))
        self.assertEqual(r["outcome"],"TARGET")

    def test_rebased_target_can_change_target_outcome(self):
        s=signal(); s["stop"]="95"; s["target_fixed_n1"]="110"
        t=datetime(2025,1,1,8,25,tzinfo=timezone.utc)
        r=simulate_trade(s,[minute(t,100,110.04,99,108)],target_mode="E3_2R")
        self.assertEqual(r["outcome"],"INCOMPLETE")

    def test_entry_order_after_slippage_can_cancel(self):
        s=signal(); s["stop"]="99.99"; s["target_fixed_n1"]="100.01"
        r=simulate_trade(s,[minute(datetime(2025,1,1,8,25,tzinfo=timezone.utc),100,100,100,100)])
        self.assertEqual(r["outcome_reason"],"ENTRY_FILL_ORDER_INVALID")

    def test_end_of_day_exit(self):
        s=signal(); start=datetime(2025,1,2,3,55,tzinfo=timezone.utc)
        rows=[minute(start+timedelta(minutes=i),100,101,99,100) for i in range(6)]
        s["e3_time"]="2025-01-02T03:55:00Z"; r=simulate_trade(s,rows)
        self.assertEqual(r["outcome"],"END_OF_DAY")

    def test_missing_exit_data_is_incomplete(self):
        s=signal(); s["e3_time"]="2025-01-01T08:25:00Z"; r=simulate_trade(s,[])
        self.assertEqual(r["outcome"],"CANCELLED"); self.assertEqual(r["outcome_reason"],"MISSING_ENTRY_MINUTE")

if __name__ == "__main__": unittest.main()
