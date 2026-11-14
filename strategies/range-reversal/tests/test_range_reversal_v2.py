import unittest
from datetime import date, datetime, timedelta, timezone

from vp_bot.range_reversal_v2 import detect_v2


def iso(t): return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
def minute(t, o, h, l, c): return {"open_time": iso(t), "open": str(o), "high": str(h), "low": str(l), "close": str(c), "volume": "1", "close_time": iso(t + timedelta(minutes=1) - timedelta(microseconds=1))}
def session(post):
    start = datetime(2025, 1, 1, 4, tzinfo=timezone.utc)
    rows = [minute(start + timedelta(minutes=i), 100, 101, 99, 100) for i in range(240)]
    for i, vals in enumerate(post):
        rows.extend(minute(start + timedelta(hours=4, minutes=i*5+j), *vals) for j in range(5))
    return rows


class RangeReversalV2Tests(unittest.TestCase):
    def test_shadow_or_equal_does_not_start_v2(self):
        rows = session([(100, 102, 99, 101), (100, 100, 99, 100), (100, 100, 99, 100)])
        _, episodes, signals, _ = detect_v2(rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertEqual(episodes, [])

    def test_v2_breakout_cannot_confirm_on_same_candle(self):
        rows = session([(100, 102, 99, 102), (102, 102, 100, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_v2(rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["breakout_time"], "2025-01-01T08:00:00Z")
        self.assertEqual(signals[0]["confirmation_time"], "2025-01-01T08:05:00Z")

    def test_n1_long_and_short(self):
        long_rows = session([(100, 100, 98, 98), (98, 100, 99, 100), (100, 100, 99, 100)])
        _, _, long_signals, _ = detect_v2(long_rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        short_rows = session([(100, 102, 100, 102), (102, 102, 100, 100), (100, 100, 99, 100)])
        _, _, short_signals, _ = detect_v2(short_rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(long_signals[0]["direction"], "LONG")
        self.assertEqual(short_signals[0]["direction"], "SHORT")

    def test_n3_requires_three_consecutive_inside_closes_and_entry_after_third(self):
        rows = session([(100, 100, 98, 98), (98, 100, 99, 100), (100, 100, 99, 100), (100, 100, 99, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_v2(rows, "N3", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["confirmation_count"], "3")
        self.assertEqual(signals[0]["confirmation_3_time"], "2025-01-01T08:15:00Z")
        self.assertEqual(signals[0]["planned_entry_time"], "2025-01-01T08:20:00Z")

    def test_n3_outside_breakout_boundary_resets_count(self):
        rows = session([(100, 100, 98, 98), (98, 100, 99, 100), (100, 100, 99, 100), (100, 100, 99, 101), (101, 100, 99, 100), (100, 100, 99, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_v2(rows, "N3", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["confirmation_3_time"], "2025-01-01T08:30:00Z")

    def test_n3_boundary_close_resets_count(self):
        rows = session([(100, 100, 98, 98), (98, 100, 99, 100), (100, 100, 99, 101), (101, 100, 99, 100), (100, 100, 99, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_v2(rows, "N3", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["confirmation_3_time"], "2025-01-01T08:25:00Z")

    def test_opposite_boundary_cancels_before_confirmation(self):
        rows = session([(100, 100, 98, 98), (98, 102, 99, 100)])
        _, episodes, signals, _ = detect_v2(rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertEqual(episodes[0]["reason"], "BOTH_SIDES")

    def test_stop_uses_last_confirmation_extremum(self):
        rows = session([(100, 100, 98, 98), (98, 100, 97, 100), (100, 100, 96, 100)])
        _, _, signals, _ = detect_v2(rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["stop"], "97.0")

    def test_no_next_local_day_entry(self):
        rows = session([(100, 100, 98, 98)])
        _, episodes, signals, _ = detect_v2(rows, "N3", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertTrue(episodes)

    def test_no_repeat_after_first_confirmation(self):
        rows = session([(100, 100, 98, 98), (98, 100, 99, 100), (100, 100, 99, 100), (100, 100, 98, 98), (98, 100, 99, 100)])
        _, _, signals, _ = detect_v2(rows, "N1", date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(signals), 1)


if __name__ == "__main__": unittest.main()
