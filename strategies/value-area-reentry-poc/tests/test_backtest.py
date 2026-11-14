import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from vp_bot.backtest import (
    _exit_from_minutes, _trade_from_event, calculate_position_size, simulate_backtest,
)
from vp_bot.signals import EpisodeEvent


def minute(time, open_price, high, low, close):
    return {"open_time": time, "open": str(open_price), "high": str(high), "low": str(low), "close": str(close)}


def event(entry="2025-01-01T01:00:00Z", stop="90", target="110"):
    return EpisodeEvent(
        "event-001", "2025-01-01", "RETURN_CONFIRMED", "RETURN_CONFIRMED", "close_inside_val_poc",
        "2024-12-31", "2025-01-01T00:00:00Z", 95.0, float(target), 115.0,
        "2025-01-01T00:59:59.999999Z", "2025-01-01T00:59:59.999999Z", 1, 95.0,
        10.0, "ready", float(stop), float(target), entry,
    )


class BacktestTests(unittest.TestCase):
    def test_next_open_not_signal_candle_and_manual_size(self):
        e = event()
        row = minute("2025-01-01T01:00:00Z", 100, 100, 99, 100)
        quantity = calculate_position_size(Decimal("1000"), Decimal("1000"), Decimal("100.02"), Decimal("90"))
        self.assertEqual(quantity, min(Decimal("5") / Decimal("10.02"), Decimal("1000") / (Decimal("100.02") * Decimal("1.001"))))
        trade, reason = _trade_from_event(e, row, [row, minute("2025-01-01T01:01:00Z", 110, 110, 110, 110)], Decimal("1000"), Decimal("1000"), "trade-001")
        self.assertEqual(reason, "ENTERED")
        self.assertEqual(trade.entry_time, "2025-01-01T01:00:00Z")
        self.assertNotEqual(trade.entry_time, e.confirmation_time)
        self.assertAlmostEqual(float(trade.net_pnl), float(trade.gross_pnl - trade.buy_fee - trade.sell_fee), places=12)

    def test_both_levels_inside_one_minute_stop_first_and_ambiguity(self):
        result = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 101, 99, 100), minute("2025-01-01T01:01:00Z", 100, 112, 88, 100)], __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertEqual(result["reason"], "STOP")
        self.assertTrue(result["ambiguity"])

    def test_stop_exit_on_open(self):
        result = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 100, 99, 100), minute("2025-01-01T01:01:00Z", 89, 100, 80, 90)], __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertEqual(result["reason"], "STOP")
        self.assertEqual(result["base"], Decimal("89"))

    def test_target_exit_on_high(self):
        result = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 100, 99, 100), minute("2025-01-01T01:01:00Z", 100, 111, 99, 105)], __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertEqual(result["reason"], "TARGET")
        self.assertEqual(result["base"], Decimal("110"))

    def test_poc_protection_activation_records_next_minute_without_exiting(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [
            minute("2025-01-01T01:00:00Z", 100, 101, 99, 100),
            minute("2025-01-01T01:01:00Z", 100, 111, 99, 107),
            minute("2025-01-01T01:02:00Z", 108.5, 109, 108.2, 108.6),
        ]
        result = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), poc_protection={"enabled": True, "buffer_atr": "0.25"}, entry_atr=Decimal("8"))
        state = result["poc_protection"]
        self.assertEqual(result["reason"], "END_OF_DATA")
        self.assertTrue(state["reached"])
        self.assertEqual(state["reach_time"], "2025-01-01T01:01:00Z")
        self.assertEqual(state["effective_at"], "2025-01-01T01:02:00Z")
        self.assertEqual(state["stop"], Decimal("108.00"))

    def test_poc_protection_stop_acts_only_after_activation_minute(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [
            minute("2025-01-01T01:00:00Z", 100, 101, 99, 100),
            minute("2025-01-01T01:01:00Z", 100, 111, 99, 107),
            minute("2025-01-01T01:02:00Z", 109, 109.5, 107, 108),
        ]
        result = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), poc_protection={"enabled": True, "buffer_atr": "0.25"}, entry_atr=Decimal("8"))
        self.assertEqual(result["reason"], "POC_PROTECTION_STOP")
        self.assertEqual(result["time"], "2025-01-01T01:02:00Z")
        self.assertEqual(result["base"], Decimal("108.00"))

    def test_poc_protection_gap_below_new_stop_fills_at_open(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [
            minute("2025-01-01T01:00:00Z", 100, 101, 99, 100),
            minute("2025-01-01T01:01:00Z", 100, 111, 99, 107),
            minute("2025-01-01T01:02:00Z", 106.5, 109, 106, 108),
        ]
        result = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), poc_protection={"enabled": True, "buffer_atr": "0.25"}, entry_atr=Decimal("8"))
        self.assertEqual(result["reason"], "POC_PROTECTION_STOP")
        self.assertEqual(result["base"], Decimal("106.5"))

    def test_poc_protection_preserves_24_hour_time_exit(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [minute((start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z"), 100, 100, 99, 100) for i in range(24 * 60 + 1)]
        rows[1].update(high="111", close="107")
        for row in rows[2:-1]:
            row.update(open="109", high="109.5", low="108.5", close="109")
        rows[-1].update(open="107", high="120", low="80", close="100")
        result = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), poc_protection={"enabled": True, "buffer_atr": "0.25"}, entry_atr=Decimal("8"))
        self.assertEqual(result["reason"], "TIME_LIMIT")
        self.assertTrue(result["time_exit"])
        self.assertEqual(result["base"], Decimal("107"))

    def test_gap_marks_position_incomplete(self):
        gap = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 101, 99, 100), minute("2025-01-01T01:02:00Z", 100, 101, 99, 100)], __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertTrue(gap["incomplete"])

    def test_time_exit_precedes_open_high_low_trigger(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = []
        for offset in range(24 * 60 + 1):
            timestamp = start + timedelta(minutes=offset)
            rows.append(minute(timestamp.isoformat().replace("+00:00", "Z"), 100, 100, 99, 100))
        rows[-1]["open"], rows[-1]["high"], rows[-1]["low"] = "80", "120", "80"
        rows.append(minute("2025-01-02T01:00:00Z", 100, 120, 80, 100))
        result = _exit_from_minutes(rows, __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertEqual(result["reason"], "TIME_LIMIT")
        self.assertTrue(result["time_stop"])

    def test_end_of_data_closes_at_last_close(self):
        result = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 100, 99, 100), minute("2025-01-01T01:01:00Z", 100, 101, 99, 100)], __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00"), Decimal("90"), Decimal("110"))
        self.assertEqual(result["reason"], "END_OF_DATA")
        self.assertEqual(result["base"], Decimal("100"))

    def test_future_minute_is_not_used_before_it_exists(self):
        now = [minute("2025-01-01T01:00:00Z", 100, 100, 99, 100), minute("2025-01-01T01:01:00Z", 100, 101, 99, 100)]
        later = now + [minute("2025-01-01T01:02:00Z", 100, 111, 99, 105)]
        start = __import__("datetime").datetime.fromisoformat("2025-01-01T01:00:00+00:00")
        self.assertEqual(_exit_from_minutes(now, start, Decimal("90"), Decimal("110"))["reason"], "END_OF_DATA")
        self.assertEqual(_exit_from_minutes(later, start, Decimal("90"), Decimal("110"))["reason"], "TARGET")

    def test_profit_lock_trigger_and_next_minute_effective_a_b(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [
            minute("2025-01-01T01:00:00Z", 100, 102, 99, 101),
            minute("2025-01-01T01:01:00Z", 101, 103, 100, 102),
            minute("2025-01-01T01:02:00Z", 102, 102, 100, 101),
            minute("2025-01-01T01:03:00Z", 100.5, 101, 100, 100.5),
        ]
        a = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), {"name": "A", "trigger_fraction": "0.30", "stop_fraction": "0.10"}, Decimal("100"))
        b = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), {"name": "B", "trigger_fraction": "0.30", "stop_fraction": "0.15"}, Decimal("100"))
        self.assertEqual(a["profit_lock"]["trigger_time"], "2025-01-01T01:01:00Z")
        self.assertEqual(a["profit_lock"]["effective_at"], "2025-01-01T01:02:00Z")
        self.assertEqual(a["profit_lock"]["new_stop"], Decimal("101.0"))
        self.assertEqual(b["profit_lock"]["new_stop"], Decimal("101.5"))
        self.assertEqual(a["reason"], "PROFIT_LOCK_STOP")
        self.assertEqual(a["time"], "2025-01-01T01:02:00Z")

    def test_no_profit_lock_before_trigger_and_baseline_is_unchanged(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        rows = [minute("2025-01-01T01:00:00Z", 100, 102, 99, 100), minute("2025-01-01T01:01:00Z", 100, 102.9, 99, 100), minute("2025-01-01T01:02:00Z", 100, 100, 99, 100)]
        baseline = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"))
        locked = _exit_from_minutes(rows, start, Decimal("90"), Decimal("110"), {"name": "A", "trigger_fraction": "0.30", "stop_fraction": "0.10"}, Decimal("100"))
        self.assertEqual(baseline["reason"], "END_OF_DATA")
        self.assertFalse(locked["profit_lock"]["activated"])

    def test_profit_lock_gap_and_stop_never_moves_down(self):
        start = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
        gap_rows = [minute("2025-01-01T01:00:00Z", 100, 103, 99, 102), minute("2025-01-01T01:01:00Z", 100, 100, 99, 99)]
        result = _exit_from_minutes(gap_rows, start, Decimal("90"), Decimal("110"), {"name": "A", "trigger_fraction": "0.30", "stop_fraction": "0.10"}, Decimal("100"))
        self.assertEqual(result["reason"], "PROFIT_LOCK_STOP")
        self.assertEqual(result["base"], Decimal("100"))
        unchanged = _exit_from_minutes([minute("2025-01-01T01:00:00Z", 100, 103, 99, 102), minute("2025-01-01T01:01:00Z", 100, 100, 99, 99)], start, Decimal("101.5"), Decimal("110"), {"name": "A", "trigger_fraction": "0.30", "stop_fraction": "0.10"}, Decimal("100"))
        self.assertEqual(unchanged["profit_lock"]["new_stop"], Decimal("101.5"))

    def test_profit_lock_fees_can_keep_net_pnl_negative(self):
        e = event(entry="2025-01-01T01:00:00Z", stop="90", target="100.1")
        row = minute("2025-01-01T01:00:00Z", 100, 100.1, 99.9, 100)
        trade, reason = _trade_from_event(e, row, [row], Decimal("1000"), Decimal("1000"), "trade-fees")
        self.assertEqual(reason, "ENTERED")
        self.assertLess(trade.net_pnl, Decimal("0"))

    def test_episode_started_during_position_is_blocked_even_if_confirmed_after_close(self):
        first = event()
        second = EpisodeEvent(
            "event-002", "2025-01-01", "RETURN_CONFIRMED", "RETURN_CONFIRMED", "close_inside_val_poc",
            "2024-12-31", "2025-01-01T00:00:00Z", 95.0, 110.0, 115.0,
            "2025-01-01T01:00:30Z", "2025-01-01T01:59:59.999999Z", 1, 95.0,
            10.0, "ready", 90.0, 110.0, "2025-01-01T02:00:00Z",
        )
        minutes = [minute("2025-01-01T01:00:00Z", 100, 100, 99, 100), minute("2025-01-01T01:01:00Z", 110, 110, 110, 110), minute("2025-01-01T01:02:00Z", 110, 110, 110, 110)]
        with patch("vp_bot.backtest.detect_events", return_value=([first, second], [])):
            result = simulate_backtest([], minutes, [], date(2025, 1, 1), date(2025, 1, 1), max_return_bars=3)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.events[1]["skip_reason"], "POSITION_OPEN_AT_EVENT_START")
        self.assertAlmostEqual(float(result.metrics["final_capital"] - result.metrics["initial_capital"]), float(result.trades[0].net_pnl), places=12)

if __name__ == "__main__":
    unittest.main()
