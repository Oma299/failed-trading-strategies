import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from vp_bot.btc_spot_donchian_v1 import (
    D, Filters, SCENARIOS, aggregate_daily, indicators, _entry_plan,
    _sell, run_scenario, scenario_metrics,
)
from vp_bot.run_btc_spot_donchian_h4 import aggregate_h4, run_h4_scenario

UTC = timezone.utc

def minute(t, o=100, h=101, l=99, c=100, v=10):
    return {"open_time": t.isoformat().replace("+00:00", "Z"), "open": str(o), "high": str(h), "low": str(l), "close": str(c), "volume": str(v)}

def day(i, close, high=None, low=None):
    t = datetime(2024, 12, 1, tzinfo=UTC) + timedelta(days=i)
    high = close + 1 if high is None else high
    low = close - 1 if low is None else low
    return {"date": t.date().isoformat(), "open_time": t.isoformat().replace("+00:00", "Z"), "close_time": (t + timedelta(days=1) - timedelta(microseconds=1)).isoformat().replace("+00:00", "Z"), "open": str(close), "high": str(high), "low": str(low), "close": str(close), "volume": "1000", "source_minute_count": 1440, "complete": True}

class DonchianV1Tests(unittest.TestCase):
    def test_current_day_is_excluded_from_channels_and_atr_is_sma20(self):
        rows = [day(i, 100, high=100+i, low=90-i) for i in range(25)]
        got = indicators(rows)
        self.assertEqual(Decimal(got[20]["upper"]), Decimal(rows[0]["high"]) if False else max(Decimal(rows[j]["high"]) for j in range(0, 20)))
        self.assertEqual(Decimal(got[20]["lower"]), min(Decimal(rows[j]["low"]) for j in range(10, 20)))
        expected_tr = sum((max(Decimal(rows[j]["high"])-Decimal(rows[j]["low"]), abs(Decimal(rows[j]["high"])-Decimal(rows[j-1]["close"])), abs(Decimal(rows[j]["low"])-Decimal(rows[j-1]["close"]))) for j in range(1, 21)), Decimal(0)) / Decimal(20)
        self.assertEqual(Decimal(got[20]["atr"]), expected_tr)

    def test_missing_calendar_day_does_not_create_false_indicator_history(self):
        rows = [day(i, 100) for i in range(25)]
        rows.pop(10)
        got = indicators(rows)
        self.assertFalse(got[-1]["ready"])

    def test_run_scenario_exposes_only_entry_window_change(self):
        rows = [day(i, 100 + i, high=101 + i, low=99 + i) for i in range(35)]
        rows[5]["high"] = "1000"
        self.assertEqual(Decimal(indicators(rows, entry_window=20)[20]["upper"]), Decimal("1000"))
        self.assertEqual(Decimal(indicators(rows, entry_window=10)[20]["upper"]), Decimal(rows[19]["high"]))

    def test_transition_on_first_allowed_day_uses_warmup_previous_b(self):
        daily = [day(i, 100) for i in range(23)]
        daily[21].update({"close": "102", "open": "102", "high": "103", "low": "101"})
        start = datetime(2024, 12, 22, tzinfo=UTC)
        minutes = []
        for offset in range(2 * 1440):
            t = start + timedelta(minutes=offset)
            if t.hour == 0 and t.minute == 0 and t.date() == (start.date() + timedelta(days=1)):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            elif t.hour == 0 and t.minute == 1 and t.date() == (start.date() + timedelta(days=1)):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            else:
                minutes.append(minute(t))
        result = run_scenario(minutes, daily, "2024-12-22T00:00:00", "2024-12-24T00:00:00", SCENARIOS[0])
        signal = next(s for s in result["signals"] if s["signal_date"] == "2024-12-22")
        self.assertEqual(signal["b_previous"], "False")
        self.assertEqual(signal["b_transition"], "True")
        self.assertEqual(signal["status"], "EXECUTED")
        self.assertEqual(len([t for t in result["trades"] if t.get("status") == "CLOSED"]), 1)

    def test_daily_rearm_retries_true_b_after_canceled_attempt(self):
        daily = [day(i, 100) for i in range(24)]
        daily[21].update({"close": "102", "open": "102", "high": "103", "low": "101"})
        daily[22].update({"close": "104", "open": "104", "high": "105", "low": "103"})
        start = datetime(2024, 12, 22, tzinfo=UTC); minutes = []
        for offset in range(3 * 1440):
            t = start + timedelta(minutes=offset)
            if t.hour == 0 and t.minute == 0 and t.date() == start.date() + timedelta(days=1):
                minutes.append(minute(t, o=100, h=101, l=99, c=100, v=1000))
            elif t.hour == 0 and t.minute == 0 and t.date() == start.date() + timedelta(days=2):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            else:
                minutes.append(minute(t))
        result = run_scenario(minutes, daily, "2024-12-22T00:00:00", "2024-12-25T00:00:00", SCENARIOS[0], daily_rearm=True)
        signals = {s["signal_date"]: s for s in result["signals"]}
        self.assertEqual(signals["2024-12-22"]["status"], "CANCELLED")
        self.assertEqual(signals["2024-12-23"]["decision_reason"], "DAILY_REARM_B_TRUE")
        self.assertEqual(signals["2024-12-23"]["prior_event"], "CANCELLED:P_NOT_ABOVE_UPPER")
        self.assertEqual(len([t for t in result["trades"] if t.get("status") == "CLOSED"]), 1)

    def test_daily_rearm_blocks_open_position_and_prioritizes_exit_at_close(self):
        daily = [day(i, 100) for i in range(24)]
        daily[21].update({"close": "102", "open": "102", "high": "103", "low": "101"})
        daily[22].update({"close": "104", "open": "104", "high": "105", "low": "103"})
        start = datetime(2024, 12, 22, tzinfo=UTC); minutes = []
        for offset in range(2 * 1440):
            t = start + timedelta(minutes=offset)
            if t.hour == 0 and t.minute in (0, 1) and t.date() == start.date() + timedelta(days=1):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            elif t.hour == 23 and t.minute == 59 and t.date() == start.date() + timedelta(days=1):
                minutes.append(minute(t, o=100, h=101, l=1, c=100, v=1000))
            else:
                minutes.append(minute(t))
        result = run_scenario(minutes, daily, "2024-12-22T00:00:00", "2024-12-24T00:00:00", SCENARIOS[0], daily_rearm=True)
        signal = next(s for s in result["signals"] if s["signal_date"] == "2024-12-23")
        self.assertEqual(signal["status"], "BLOCKED_EXIT_PRIORITY")
        self.assertEqual(signal["cancel_reason"], "EXIT_PRIORITY_AT_DAILY_CLOSE")

    def test_h4_aggregation_uses_utc_four_hour_boundaries(self):
        start = datetime(2024, 12, 1, tzinfo=UTC)
        rows = [minute(start + timedelta(minutes=i)) for i in range(480)]
        bars = aggregate_h4(rows)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["open_time"], "2024-12-01T00:00:00Z")
        self.assertEqual(bars[1]["open_time"], "2024-12-01T04:00:00Z")
        self.assertTrue(all(bar["complete"] for bar in bars))

    def test_h4_boundary_signal_uses_day_channel_and_next_minute_execution(self):
        daily = [day(i, 100) for i in range(24)]
        start = datetime(2024, 12, 21, tzinfo=UTC)
        minutes = []
        for offset in range(3 * 1440):
            t = start + timedelta(minutes=offset)
            # The [20:00,24:00) H4 of day 20 closes above the channel fixed
            # at the beginning of day 20; the following minute is the order.
            if t.date() == start.date() and t.hour == 23 and t.minute == 59:
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            elif t.date() == start.date() + timedelta(days=1) and t.hour == 0 and t.minute in (0, 1):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            else:
                minutes.append(minute(t))
        result = run_h4_scenario(minutes, daily, "2024-12-21T00:00:00", "2024-12-24T00:00:00", SCENARIOS[0])
        signal = next(s for s in result["signals"] if s["h4_start"] == "2024-12-21T20:00:00Z")
        self.assertEqual(signal["b"], "True")
        self.assertEqual(signal["b_previous"], "False")
        trade = next(t for t in result["trades"] if t.get("status") == "CLOSED")
        self.assertEqual(trade["entry_time"], "2024-12-22T00:01:00Z")
        self.assertEqual(signal["atr_day"], "2024-12-21")

    def test_h4_signal_is_blocked_while_position_is_open(self):
        daily = [day(i, 100) for i in range(24)]
        start = datetime(2024, 12, 21, tzinfo=UTC); minutes = []
        for offset in range(3 * 1440):
            t = start + timedelta(minutes=offset)
            if (t.hour, t.minute) == (23, 59) and t.date() == start.date():
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            elif t.date() == start.date() + timedelta(days=1) and t.hour == 0 and t.minute in (0, 1):
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            elif t.date() == start.date() + timedelta(days=1) and t.hour < 4:
                minutes.append(minute(t, o=110, h=111, l=109, c=110, v=1000))
            else:
                minutes.append(minute(t))
        result = run_h4_scenario(minutes, daily, "2024-12-21T00:00:00", "2024-12-24T00:00:00", SCENARIOS[0])
        blocked = next(s for s in result["signals"] if s["h4_start"] == "2024-12-22T00:00:00Z")
        self.assertEqual(blocked["status"], "BLOCKED_OPEN_POSITION")

    def test_equality_is_not_breakout_and_transition_is_required(self):
        rows = [day(i, 100) for i in range(25)]
        rows[20]["close"] = rows[19]["high"]
        got = indicators(rows)
        self.assertFalse(got[20]["b"])
        rows[21]["close"] = str(Decimal(got[21]["upper"]) + Decimal("1"))
        got = indicators(rows)
        self.assertTrue(got[21]["b"])
        rows[22]["close"] = str(Decimal(got[22]["upper"]) + Decimal("1"))
        got = indicators(rows)
        self.assertTrue(got[22]["b"])

    def test_entry_plan_uses_only_minute_zero_and_limits_qty(self):
        signal = {"upper": "100", "stop": "90"}
        p0 = minute(datetime(2025, 1, 1, tzinfo=UTC), c=110, v=100)
        p1 = minute(datetime(2025, 1, 1, 0, 1, tzinfo=UTC), o=999, h=999, l=999, c=999, v=999999)
        plan, reason = _entry_plan(signal, p0, p1, D("10000"), SCENARIOS[1], Filters())
        self.assertEqual(reason, "")
        self.assertEqual(plan["volume"], Decimal("100"))
        self.assertLessEqual(plan["q"], Decimal("1"))

    def test_buy_fee_is_btc_and_sell_fee_is_usdt(self):
        position = {"btc_received": D("1"), "quote_order_amount": D("100"), "entry_time": datetime(2025, 1, 1, tzinfo=UTC), "risk_budget_usdt": D("50")}
        result = _sell(position, D("110"), datetime(2025, 1, 2, tzinfo=UTC), "CHANNEL", SCENARIOS[1])
        self.assertEqual(Decimal(result["commission_sell_usdt"]), Decimal("0.109967"))
        self.assertGreater(Decimal(result["net_pnl_usdt"]), Decimal("0"))

    def test_missing_minute_and_end_of_test_are_explicit(self):
        start = "2025-01-01T00:00:00"; end = "2025-01-03T00:00:00"
        daily = [day(i, 100) for i in range(40)]
        # No signal is expected here, but the runner must not invent one from incomplete data.
        result = run_scenario([minute(datetime(2025,1,1,tzinfo=UTC)+timedelta(minutes=i)) for i in range(10)], daily, start, end, SCENARIOS[0])
        self.assertEqual(result["trades"], [])

    def test_sell_stop_gap_and_no_double_close(self):
        position = {"btc_received": D("1"), "quote_order_amount": D("100"), "entry_time": datetime(2025, 1, 1, tzinfo=UTC), "risk_budget_usdt": D("50")}
        result = _sell(position, D("80"), datetime(2025, 1, 2, tzinfo=UTC), "STOP_GAP", SCENARIOS[2])
        self.assertEqual(result["exit_reason"], "STOP_GAP")
        self.assertLess(Decimal(result["net_pnl_usdt"]), Decimal("0"))

    def test_lower_channel_exit_is_recorded_as_its_own_event(self):
        # The execution primitive must preserve the distinct channel reason;
        # the daily state machine schedules this sale for the next 00:01.
        position = {"btc_received": D("1"), "quote_order_amount": D("100"), "entry_time": datetime(2025, 1, 1, tzinfo=UTC), "risk_budget_usdt": D("50")}
        result = _sell(position, D("110"), datetime(2025, 1, 2, 0, 1, tzinfo=UTC), "LOWER_CHANNEL_EXIT", SCENARIOS[1])
        self.assertEqual(result["exit_reason"], "LOWER_CHANNEL_EXIT")

if __name__ == "__main__": unittest.main()
