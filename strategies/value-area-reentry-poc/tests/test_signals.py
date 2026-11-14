import unittest
from datetime import date, datetime, timedelta, timezone

from vp_bot.atr import compute_wilder_atr
from vp_bot.signals import detect_events


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def hour_rows(closes, start=datetime(2025, 1, 1, tzinfo=timezone.utc), highs=None, lows=None):
    highs = highs or [110] * len(closes)
    lows = lows or [90] * len(closes)
    rows = []
    for index, close in enumerate(closes):
        opened = start + timedelta(hours=index)
        rows.append({
            "open_time": iso(opened), "close_time": iso(opened + timedelta(hours=1) - timedelta(microseconds=1)),
            "open": str(close), "high": str(highs[index]), "low": str(lows[index]), "close": str(close),
            "volume": "1", "source_minute_count": "60", "complete_60_distinct_minutes": "True",
        })
    return rows


def profile_row(available_at="2025-01-01T00:00:00Z"):
    return {"date": "2024-12-31", "available_at": available_at, "valid": "True", "reason": "", "val": "100", "poc": "110", "vah": "120"}


class ValueAreaSignalTests(unittest.TestCase):
    def test_wilder_atr_manual_values_and_gap(self):
        rows = hour_rows([9] + [11] * 13 + [14], start=datetime(2024, 12, 1, tzinfo=timezone.utc), highs=[10] + [12] * 13 + [15], lows=[8] + [10] * 13 + [14])
        points = compute_wilder_atr(rows)
        self.assertIsNone(points[12].atr)
        self.assertAlmostEqual(points[13].atr, 29 / 14, places=12)
        self.assertAlmostEqual(points[14].tr, 4.0, places=12)  # gap from previous close 11 to high 15
        self.assertAlmostEqual(points[14].atr, (13 * (29 / 14) + 4) / 14, places=12)

    def test_atr_warmup_resets_after_incomplete_hour(self):
        rows = hour_rows([10] * 15, highs=[12] * 15, lows=[8] * 15)
        rows[5]["complete_60_distinct_minutes"] = "False"
        points = compute_wilder_atr(rows)
        self.assertFalse(points[5].valid_hour)
        self.assertTrue(all(point.atr is None for point in points[6:]))
        rows.extend(hour_rows([10] * 13, start=datetime(2025, 1, 1, 15, tzinfo=timezone.utc), highs=[12] * 13, lows=[8] * 13))
        points = compute_wilder_atr(rows)
        self.assertIsNotNone(points[-1].atr)

    def test_return_on_first_candle(self):
        events, summaries = detect_events(hour_rows([90, 105, 95]), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "ATR_UNAVAILABLE")
        self.assertEqual(events[0].return_candle_number, 1)
        self.assertEqual(summaries[0].outcome, "ATR_UNAVAILABLE")

    def test_return_on_third_candle(self):
        events, _ = detect_events(hour_rows([90, 100, 110, 105]), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(events[0].return_candle_number, 3)

    def test_w3_return_window_boundary(self):
        for return_bar, is_return_in_window in ((3, True), (4, False)):
            with self.subTest(return_bar=return_bar):
                closes = [90] + [100] * (return_bar - 1) + [105]
                events, _ = detect_events(hour_rows(closes), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1), 3)
                self.assertEqual(events[0].status == "EXPIRED", not is_return_in_window)
                if is_return_in_window:
                    self.assertEqual(events[0].return_candle_number, return_bar)

    def test_first_matching_return_is_used_without_waiting_for_window_end(self):
        events, _ = detect_events(hour_rows([90, 105, 105, 105, 105]), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1), 3)
        self.assertEqual(events[0].return_candle_number, 1)
        self.assertEqual(events[0].confirmation_time, "2025-01-01T01:59:59.999999Z")

    def test_later_return_episode_low_includes_confirmation_bar(self):
        rows = hour_rows([90, 100, 100, 105], lows=[85, 80, 75, 60])
        events, _ = detect_events(rows, [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1), 3)
        self.assertEqual(events[0].return_candle_number, 3)
        self.assertEqual(events[0].episode_low, 60)

    def test_wick_does_not_confirm_and_boundaries_do_not_confirm(self):
        events, _ = detect_events(hour_rows([90, 90, 100, 110], highs=[110, 110, 110, 110]), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(events[0].status, "EXPIRED")

    def test_second_same_day_episode_does_not_start_after_first_expires(self):
        events, _ = detect_events(hour_rows([90, 100, 100, 100, 90, 105]), [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1), 3)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].status, "EXPIRED")

    def test_day_change_cancels_and_no_second_episode(self):
        rows = hour_rows([90], start=datetime(2025, 1, 1, 23, tzinfo=timezone.utc))
        rows.extend(hour_rows([105], start=datetime(2025, 1, 2, 0, tzinfo=timezone.utc)))
        events, summaries = detect_events(rows, [profile_row()], [], date(2025, 1, 1), date(2025, 1, 2), 9)
        self.assertEqual(events[0].status, "CANCELLED_DAY_CHANGE")
        self.assertEqual(len(events), 1)
        self.assertEqual(summaries[0].outcome, "CANCELLED_DAY_CHANGE")

    def test_missing_hour_cancels_waiting_episode(self):
        rows = hour_rows([90, 105])
        rows[1]["open_time"] = iso(datetime(2025, 1, 1, 2, tzinfo=timezone.utc))
        events, _ = detect_events(rows, [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(events[0].status, "CANCELLED_DATA_QUALITY")

    def test_profile_cannot_be_used_before_available_at(self):
        rows = hour_rows([90, 90, 105])
        events, summaries = detect_events(rows, [profile_row("2025-01-01T02:00:00Z")], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(len(events), 0)
        self.assertEqual(summaries[0].outcome, "NO_EVENT")

    def test_future_rows_do_not_change_signal_or_atr(self):
        rows = hour_rows([90, 105, 105])
        first_events, _ = detect_events(rows, [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        future = hour_rows([1, 1, 1], start=datetime(2025, 1, 2, tzinfo=timezone.utc), highs=[2, 2, 2], lows=[0, 0, 0])
        second_events, _ = detect_events(rows + future, [profile_row()], [], date(2025, 1, 1), date(2025, 1, 1))
        self.assertEqual(first_events, second_events)


if __name__ == "__main__":
    unittest.main()
