import unittest
from datetime import date, datetime, timedelta, timezone

from vp_bot.run_range_reversal_apr_jun_validation import VALIDATION_TARGET_MODE, local_day_completeness


class AprJunValidationTests(unittest.TestCase):
    def test_validation_uses_e3_rebased_target_mode(self):
        self.assertEqual(VALIDATION_TARGET_MODE, "E3_2R")

    def test_last_local_day_requires_minutes_through_local_midnight(self):
        # 2025-06-30 UTC-04 runs from 04:00 UTC through 2025-07-01 03:59 UTC.
        start = end = date(2025, 6, 30)
        rows = [{"open_time": (datetime(2025, 6, 30, 4, tzinfo=timezone.utc) + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")} for i in range(20 * 60)]
        self.assertFalse(local_day_completeness(rows, start, end)["2025-06-30"])


if __name__ == "__main__":
    unittest.main()
