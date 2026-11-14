"""Build D-1 profile input from locally supplied, checksummed daily archives."""

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

from .aggtrades import (
    AggProfile,
    AggTradeQuality,
    calculate_agg_profile,
    inspect_quality,
    verify_checksum,
)


PROFILE_FIELDS = [
    "source",
    "method",
    "date",
    "available_at",
    "valid",
    "reason",
    "day_low",
    "day_high",
    "val",
    "poc",
    "vah",
    "total_volume",
    "value_area_volume",
    "value_area_fraction",
    "bin_step",
]


def profile_row(profile: AggProfile) -> Dict[str, object]:
    row = profile.__dict__.copy()
    row["date"] = row.pop("day")
    row["source"] = "binance_spot_aggtrades"
    row["method"] = "aggtrades"
    return row


def _require_clean_quality(quality: AggTradeQuality) -> None:
    counters = {
        "empty archive": quality.row_count == 0,
        "malformed rows": quality.malformed_rows,
        "out-of-range rows": quality.out_of_range_rows,
        "timestamp ordering violations": quality.time_order_violations,
        "duplicate aggregate-trade IDs": quality.duplicate_aggregate_trade_ids,
        "ID ordering violations": quality.id_order_violations,
        "aggregate-trade ID gaps": quality.id_gap_count,
    }
    failures = [name for name, value in counters.items() if value]
    if failures:
        raise ValueError("aggTrades quality check failed: " + ", ".join(failures))


def build_profiles(
    archive_dir: Path,
    output_path: Path,
    start_day: date,
    end_day: date,
    bin_count: int = 100,
) -> List[Dict[str, object]]:
    if end_day < start_day:
        raise ValueError("end day must not precede start day")
    rows = []
    current_day = start_day
    while current_day <= end_day:
        stem = "BTCUSDT-aggTrades-%s.zip" % current_day.isoformat()
        archive = archive_dir / stem
        checksum = archive.with_name(archive.name + ".CHECKSUM")
        verify_checksum(archive, checksum)
        quality = inspect_quality(archive, current_day)
        _require_clean_quality(quality)
        profile, _ = calculate_agg_profile(archive, current_day, quality, bin_count)
        if not profile.valid:
            raise ValueError("invalid profile for %s: %s" % (current_day, profile.reason))
        rows.append(profile_row(profile))
        current_day += timedelta(days=1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROFILE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", default="data/raw/aggtrades")
    parser.add_argument("--output", default="data/processed/w3_daily_profiles.csv")
    parser.add_argument("--start-day", default="2024-12-31")
    parser.add_argument("--end-day", default="2025-03-30")
    parser.add_argument("--bins", type=int, default=100)
    args = parser.parse_args()
    rows = build_profiles(
        Path(args.archive_dir),
        Path(args.output),
        date.fromisoformat(args.start_day),
        date.fromisoformat(args.end_day),
        args.bins,
    )
    valid = sum(row["valid"] is True for row in rows)
    print("days=%d valid=%d invalid=%d" % (len(rows), valid, len(rows) - valid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
