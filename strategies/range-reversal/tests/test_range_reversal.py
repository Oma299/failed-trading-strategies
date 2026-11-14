import unittest
from datetime import date, datetime, timedelta, timezone

from vp_bot.range_reversal import aggregate_m5, detect_range_reversal, local_day


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def minute(moment, op, hi, lo, cl):
    return {"open_time": iso(moment), "open": str(op), "high": str(hi), "low": str(lo), "close": str(cl), "volume": "1", "close_time": iso(moment + timedelta(minutes=1) - timedelta(microseconds=1))}


def session(post):
    start = datetime(2025, 1, 1, 4, tzinfo=timezone.utc)
    rows = [minute(start + timedelta(minutes=i), 100, 101, 99, 100) for i in range(240)]
    for offset, values in enumerate(post):
        moment = start + timedelta(hours=4, minutes=offset * 5)
        rows.extend(minute(moment + timedelta(minutes=j), *values) for j in range(5))
    return rows


class RangeReversalTests(unittest.TestCase):
    def test_fixed_utc_minus_four_local_day(self):
        self.assertEqual(local_day("2025-01-01T04:00:00Z"), date(2025, 1, 1))
        self.assertEqual(local_day("2025-01-02T03:59:00Z"), date(2025, 1, 1))
        self.assertEqual(local_day("2025-01-02T04:00:00Z"), date(2025, 1, 2))

    def test_m5_requires_five_minutes(self):
        rows = session([(100, 102, 99, 100)])
        rows.pop(242)
        buckets = aggregate_m5(rows)
        self.assertEqual(buckets[0]["complete"], "True")
        self.assertIn("False", [row["complete"] for row in buckets])

    def test_range_is_unavailable_before_four_hours_and_incomplete_range_skips(self):
        rows = session([])[:-1]
        ranges, episodes, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(ranges[0]["reason"], "INCOMPLETE_INITIAL_RANGE")
        self.assertEqual(episodes, [])
        self.assertEqual(signals, [])

    def test_long_breakout_and_same_bar_return(self):
        ranges, episodes, signals, _ = detect_range_reversal(session([(100, 100, 98, 100), (100, 100, 99, 100)]), date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["direction"], "LONG")
        self.assertEqual(signals[0]["status"], "SIGNAL")

    def test_short_breakout_and_same_bar_return(self):
        rows = session([(100, 102, 100, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["direction"], "SHORT")

    def test_touch_and_equal_close_are_not_signals(self):
        rows = session([(100, 101, 99, 100), (100, 102, 99, 101)])
        _, episodes, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertEqual(episodes[0]["reason"], "LOCAL_MIDNIGHT")

    def test_stop_uses_full_episode_extremum(self):
        rows = session([(100, 104, 100, 102), (100, 106, 100, 100), (100, 100, 99, 100)])
        _, _, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals[0]["stop"], "106.0")

    def test_both_sides_cancels_without_signal(self):
        _, episodes, signals, _ = detect_range_reversal(session([(100, 102, 98, 100)]), date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(episodes[0]["reason"], "BOTH_SIDES")
        self.assertEqual(signals, [])

    def test_midnight_cancels_waiting_episode(self):
        rows = session([(100, 102, 100, 101)])
        _, episodes, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertEqual(episodes[0]["reason"], "LOCAL_MIDNIGHT")

    def test_entry_is_next_m5_and_no_repeat_signal(self):
        rows = session([(100, 100, 98, 100), (100, 101, 99, 100), (100, 100, 98, 100), (100, 101, 99, 100), (100, 101, 99, 100)])
        _, episodes, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["planned_entry_time"], "2025-01-01T08:05:00Z")
        self.assertEqual(len(episodes), 1)

    def test_missing_m5_breaks_episode(self):
        rows = session([(100, 100, 98, 101), (100, 101, 99, 100)])
        rows = [row for row in rows if row["open_time"] != "2025-01-01T08:05:00Z"]
        _, episodes, signals, _ = detect_range_reversal(rows, date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(signals, [])
        self.assertEqual(episodes[0]["reason"], "MISSING_M5")


if __name__ == "__main__":
    unittest.main()
