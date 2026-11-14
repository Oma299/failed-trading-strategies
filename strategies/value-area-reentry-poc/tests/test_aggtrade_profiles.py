import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vp_bot.aggtrades import (
    _bin_index,
    calculate_agg_profile,
    inspect_quality,
    parse_timestamp,
)
from vp_bot.build_aggtrades_profiles import profile_row


class AggTradeProfileTests(unittest.TestCase):
    def test_timestamps_and_exact_price_bin_boundaries(self):
        self.assertEqual(
            parse_timestamp("1735689600000000").isoformat(),
            "2025-01-01T00:00:00+00:00",
        )
        self.assertEqual(_bin_index(100, 100, 105, 5), 0)
        self.assertEqual(_bin_index(101, 100, 105, 5), 1)
        self.assertEqual(_bin_index(105, 100, 105, 5), 4)

    def test_profile_uses_exact_trade_prices_and_70_percent_value_area(self):
        day = date(2025, 1, 1)
        rows = [
            ("1", "100", "1.25", "1", "1", "1735689600000000", "False", "True"),
            ("2", "101", "2.50", "2", "2", "1735689600000001", "False", "True"),
            ("3", "105", "3.25", "3", "3", "1735775999999999", "False", "True"),
        ]
        archive = Path("synthetic-archive.zip")
        archive_info = SimpleNamespace(filename="records.csv", file_size=100)

        class ArchiveHandle:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def infolist(self):
                return [archive_info]

        with patch("vp_bot.aggtrades.ZipFile", return_value=ArchiveHandle()), patch(
            "vp_bot.aggtrades._iter_rows", side_effect=lambda _path: iter(rows)
        ):
            quality = inspect_quality(archive, day)
            profile, bins = calculate_agg_profile(archive, day, quality, 5)

        self.assertTrue(profile.valid)
        self.assertEqual(profile.total_volume, 7)
        self.assertGreaterEqual(profile.value_area_fraction, 0.70)
        self.assertEqual(len(bins), 5)
        self.assertEqual(profile_row(profile)["source"], "binance_spot_aggtrades")
        self.assertEqual(profile_row(profile)["method"], "aggtrades")


if __name__ == "__main__":
    unittest.main()
