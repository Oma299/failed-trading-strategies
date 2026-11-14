import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from vp_bot.btc_spot_trend_pullback_v1 import (
    D, SCENARIOS, Filters, aggregate_h1, aggregate_h4, ema_h4_regime,
    rsi_wilder, run_segment, size_order, sma_atr,
)

UTC = timezone.utc


def minute(t, value=100, volume=10, low=None, high=None):
    low = value - 1 if low is None else low
    high = value + 1 if high is None else high
    return {"open_time": t.isoformat().replace("+00:00", "Z"), "open": str(value), "high": str(high), "low": str(low), "close": str(value), "volume": str(volume)}


def h1(t, close):
    return {"open_time": t.isoformat().replace("+00:00", "Z"), "close_time": (t + timedelta(hours=1)).isoformat().replace("+00:00", "Z"), "open": str(close), "high": str(close + 1), "low": str(close - 1), "close": str(close), "volume": "100", "complete": True}


class TrendPullbackTests(unittest.TestCase):
    def protection_fixture(self, values, lows=None, highs=None, closes=None):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        lows = lows or {}; highs = highs or {}; closes = closes or {}
        rows = [minute(start + timedelta(minutes=i), value=110, volume=100) for i in range(-60, 0)]
        for i, value in enumerate(values):
            t = start + timedelta(minutes=i)
            rows.append(minute(t, value=value, volume=100, low=lows.get(i, value - 1), high=highs.get(i, value + 1)))
            if i in closes: rows[-1]["close"] = str(closes[i])
        h4_prev = h1(start - timedelta(hours=4), 100)
        h4_prev["close_time"] = (start - timedelta(hours=0)).isoformat().replace("+00:00", "Z")
        h4_old = h1(start - timedelta(hours=8), 100)
        h4_old["close_time"] = (start - timedelta(hours=4)).isoformat().replace("+00:00", "Z")
        h4_rows = [h4_old, h4_prev]
        h1_rows = [h1(start - timedelta(hours=1), 100), h1(start, 110)]
        prepared = {"h1": h1_rows, "h4": h4_rows, "atr": [None, D("1")], "rsi": [D("10"), D("30")],
                    "ema": [D("100"), D("100")], "regime": [True, True],
                    "h4_by_end": {start - timedelta(hours=4): 0, start: 1}, "h4_end_times": [start - timedelta(hours=4), start],
                    "h1_by_end": {start: 1}, "warmup_end": start}
        return start, rows, prepared

    def test_sma_atr20_and_rsi3_control_values(self):
        rows = [h1(datetime(2025, 1, 1, tzinfo=UTC) + timedelta(hours=i), 100 + i) for i in range(25)]
        atr = sma_atr(rows)
        self.assertEqual(atr[20], Decimal("2"))
        rsi = rsi_wilder(rows[:5])
        self.assertEqual(rsi[3], Decimal("100"))
        self.assertEqual(rsi[4], Decimal("100"))

    def test_h4_ema_initial_sma_and_strict_regime(self):
        rows = [h1(datetime(2025, 1, 1, tzinfo=UTC) + timedelta(hours=4*i), 100) for i in range(106)]
        ema, regime = ema_h4_regime(rows)
        self.assertEqual(ema[99], Decimal("100"))
        self.assertFalse(regime[105])
        rows[105]["close"] = "101"
        ema2, regime2 = ema_h4_regime(rows)
        self.assertNotEqual(ema2[105], ema[105])
        self.assertTrue(regime2[105])

    def test_prefix_indicators_do_not_change_when_future_changes(self):
        rows = [h1(datetime(2025, 1, 1, tzinfo=UTC) + timedelta(hours=i), 100 + (i % 3)) for i in range(120)]
        ema_a, regime_a = ema_h4_regime(rows)
        rsi_a = rsi_wilder(rows)
        atr_a = sma_atr(rows)
        future = list(rows)
        for row in future[80:]:
            row["close"] = "10000"; row["high"] = "10001"; row["low"] = "9999"
        ema_b, regime_b = ema_h4_regime(future)
        rsi_b = rsi_wilder(future); atr_b = sma_atr(future)
        for i in range(80):
            self.assertEqual(ema_a[i], ema_b[i]); self.assertEqual(regime_a[i], regime_b[i]); self.assertEqual(rsi_a[i], rsi_b[i]); self.assertEqual(atr_a[i], atr_b[i])

    def test_aggregate_h1_h4_requires_complete_minutes(self):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        rows = [minute(start + timedelta(minutes=i)) for i in range(240)]
        rows.pop(17)
        self.assertFalse(aggregate_h1(rows)[0]["complete"])
        self.assertFalse(aggregate_h4(rows)[0]["complete"])

    def test_size_uses_fee_in_btc_dust_and_volume_limit(self):
        plan = size_order(100, 90, 1000, D("10000"), SCENARIOS[2], Filters())
        self.assertIsNotNone(plan)
        self.assertEqual(plan["q_received"], plan["q_sell"] + plan["dust"])
        self.assertLessEqual(plan["q_gross"], D("10"))
        self.assertLessEqual(plan["loss_plan"], D("50"))

    def test_exact_48_hour_exit_is_executed_not_terminal(self):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        minutes = [minute(start + timedelta(minutes=i), value=100, volume=100) for i in range(51 * 60 + 5)]
        h4_rows = [{"open_time": (start - timedelta(hours=4*(299-i))).isoformat().replace("+00:00", "Z"), "close_time": (start - timedelta(hours=4*(299-i)) + timedelta(hours=4)).isoformat().replace("+00:00", "Z"), "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1", "complete": True} for i in range(300)]
        h1_rows = [h1(start, 100), h1(start + timedelta(hours=1), 100)]
        prepared = {"h1": h1_rows, "h4": h4_rows, "atr": [None, D("1")], "rsi": [D("10"), D("30")], "ema": [D("100")]*300, "regime": [True]*300, "h4_by_end": {datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")): i for i,x in enumerate(h4_rows)}, "h4_end_times": [datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")) for x in h4_rows], "h1_by_end": {datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")): i for i,x in enumerate(h1_rows)}, "warmup_end": start}
        result = run_segment(minutes, start.isoformat(), (start + timedelta(hours=51)).isoformat(), SCENARIOS[0], prepared=prepared)
        closed = [t for t in result["trades"] if t.get("status") == "CLOSED"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["exit_reason"], "TIME_EXIT")
        self.assertAlmostEqual(float(closed[0]["duration_hours"]), 48.0)

    def test_no_rsi_exit_ignores_threshold_but_control_closes(self):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        minutes = [minute(start + timedelta(minutes=i), value=100, volume=100) for i in range(51 * 60 + 5)]
        h4_rows = [{"open_time": (start - timedelta(hours=4*(299-i+1))).isoformat().replace("+00:00", "Z"), "close_time": (start - timedelta(hours=4*(299-i))).isoformat().replace("+00:00", "Z"), "open": "100", "high": "101", "low": "99", "close": "100", "volume": "1", "complete": True} for i in range(300)]
        h1_rows = [h1(start - timedelta(hours=1), 100), h1(start, 100), h1(start + timedelta(hours=1), 100)]
        prepared = {"h1": h1_rows, "h4": h4_rows, "atr": [None, D("1"), D("1")], "rsi": [D("10"), D("30"), D("60")], "ema": [D("100")]*300, "regime": [True]*300, "h4_by_end": {datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")): i for i,x in enumerate(h4_rows)}, "h4_end_times": [datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")) for x in h4_rows], "h1_by_end": {datetime.fromisoformat(x["close_time"].replace("Z", "+00:00")): i for i,x in enumerate(h1_rows)}, "warmup_end": start}
        control = run_segment(minutes, start.isoformat(), (start + timedelta(hours=51)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=True)
        variant = run_segment(minutes, start.isoformat(), (start + timedelta(hours=51)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False)
        control_closed = [t for t in control["trades"] if t.get("status") == "CLOSED"]
        variant_closed = [t for t in variant["trades"] if t.get("status") == "CLOSED"]
        self.assertEqual(control_closed[0]["exit_reason"], "RSI_EXIT")
        self.assertEqual(variant_closed[0]["exit_reason"], "TIME_EXIT")
        self.assertTrue(any(x["decision"] == "RSI_EXIT_IGNORED" for x in variant["decision_log"]))

    def test_scenario_rates_are_fixed(self):
        self.assertEqual(SCENARIOS[2].fee, Decimal("0.001"))
        self.assertEqual(SCENARIOS[2].full_spread, Decimal("0.0001"))
        self.assertEqual(SCENARIOS[2].slippage, Decimal("0.0002"))
        self.assertEqual(SCENARIOS[4].fee, Decimal("0.0015"))

    def test_one_shot_protection_requires_close_and_activates_after_full_minute(self):
        start, rows, prepared = self.protection_fixture([110, 110, 110, 110, 110, 110], closes={1: 113, 2: 114})
        result = run_segment(rows, start.isoformat(), (start + timedelta(minutes=6)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=True)
        events = result["protection_log"]
        self.assertEqual(events[0]["event"], "PENDING")
        self.assertEqual(events[0]["signal_time"], (start + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"))
        self.assertEqual(events[0]["activation_time"], (start + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"))

    def test_high_touch_without_close_does_not_arm(self):
        start, rows, prepared = self.protection_fixture([110, 110, 110, 110], highs={2: 114}, closes={2: 113})
        result = run_segment(rows, start.isoformat(), (start + timedelta(minutes=4)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=True)
        self.assertFalse(result["protection_log"])

    def test_protected_stop_gap_is_from_open_and_has_stop_type(self):
        start, rows, prepared = self.protection_fixture([110, 110, 110, 112, 107], lows={3: 112}, closes={1: 114})
        result = run_segment(rows, start.isoformat(), (start + timedelta(minutes=5)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=True)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "STOP_GAP")
        self.assertEqual(trade["stop_type"], "PROTECTED_STOP")
        self.assertEqual(Decimal(trade["exit_base"]), Decimal("107"))

    def test_initial_stop_remains_active_during_signal_and_waiting_minutes(self):
        start, rows, prepared = self.protection_fixture([110, 110, 107, 112], lows={2: 107}, closes={1: 114})
        result = run_segment(rows, start.isoformat(), (start + timedelta(minutes=4)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=True)
        trade = result["trades"][0]
        self.assertEqual(trade["stop_type"], "INITIAL_STOP")
        self.assertEqual(trade["exit_reason"], "STOP_GAP")
        self.assertFalse(any(e["event"] == "ACTIVATED" for e in result["protection_log"]))

    def test_protection_stop_is_one_shot_and_never_weaker_than_initial(self):
        start, rows, prepared = self.protection_fixture([110, 110, 112, 112, 112, 112], closes={1: 114, 2: 115, 3: 116})
        result = run_segment(rows, start.isoformat(), (start + timedelta(minutes=6)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=True)
        pending = [e for e in result["protection_log"] if e["event"] == "PENDING"]
        activated = [e for e in result["protection_log"] if e["event"] == "ACTIVATED"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(activated), 1)
        self.assertGreaterEqual(Decimal(pending[0]["protected_stop"]), Decimal(pending[0]["initial_stop"]))

    def test_disabled_protection_is_exactly_the_no_rsi_control_path(self):
        start, rows, prepared = self.protection_fixture([110, 110, 110, 110], closes={1: 114})
        a = run_segment(rows, start.isoformat(), (start + timedelta(minutes=4)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False)
        b = run_segment(rows, start.isoformat(), (start + timedelta(minutes=4)).isoformat(), SCENARIOS[0], prepared=prepared, rsi_exit=False, one_shot_protection=False)
        self.assertEqual(a["trades"], b["trades"])
        self.assertEqual(a["signals"], b["signals"])


if __name__ == "__main__":
    unittest.main()
