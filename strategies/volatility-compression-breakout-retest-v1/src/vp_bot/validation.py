"""Validation and hourly aggregation for normalized one-minute klines."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import math
from typing import Dict, Iterable, List, Mapping, Union


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def validate_rows(rows: list[Mapping[str, str]]) -> dict:
    timestamps = [_dt(row["open_time"]) for row in rows]
    duplicates = [ts.isoformat() for ts, count in Counter(timestamps).items() if count > 1]
    out_of_order = sum(a > b for a, b in zip(timestamps, timestamps[1:]))
    missing = []
    for previous, current in zip(timestamps, timestamps[1:]):
        if current > previous + timedelta(minutes=1):
            cursor = previous + timedelta(minutes=1)
            while cursor < current:
                missing.append(cursor)
                cursor += timedelta(minutes=1)
    missing_by_day = Counter(ts.date().isoformat() for ts in missing)
    numeric_errors = []
    negative_volume = []
    for index, row in enumerate(rows):
        try:
            values = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume")}
            if not all(math.isfinite(value) for value in values.values()):
                numeric_errors.append({"row": index, "reason": "non-finite number"})
            if not (values["low"] <= values["open"] <= values["high"] and values["low"] <= values["close"] <= values["high"]):
                numeric_errors.append({"row": index, "reason": "low <= open/close <= high violated"})
            if values["volume"] < 0:
                negative_volume.append(index)
        except (KeyError, TypeError, ValueError):
            numeric_errors.append({"row": index, "reason": "non-numeric OHLCV"})
    return {
        "row_count": len(rows),
        "start": timestamps[0].isoformat() if timestamps else None,
        "end": timestamps[-1].isoformat() if timestamps else None,
        "duplicate_timestamps": duplicates,
        "out_of_order_pairs": out_of_order,
        "missing_minute_count": len(missing),
        "missing_by_day": dict(sorted(missing_by_day.items())),
        "numeric_errors": numeric_errors,
        "negative_volume_rows": negative_volume,
    }


def aggregate_hourly(rows: Iterable[Mapping[str, str]]) -> List[Dict[str, Union[str, int, bool]]]:
    buckets: Dict[datetime, List[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        timestamp = _dt(row["open_time"])
        hour = timestamp.replace(minute=0, second=0, microsecond=0)
        buckets[hour].append(row)
    result = []
    for hour in sorted(buckets):
        group = sorted(buckets[hour], key=lambda item: item["open_time"])
        expected = {hour + timedelta(minutes=offset) for offset in range(60)}
        actual = {_dt(row["open_time"]) for row in group}
        result.append({
            "open_time": hour.isoformat().replace("+00:00", "Z"),
            "close_time": (hour + timedelta(hours=1) - timedelta(microseconds=1)).isoformat().replace("+00:00", "Z"),
            "open": group[0]["open"], "high": str(max(float(row["high"]) for row in group)),
            "low": str(min(float(row["low"]) for row in group)), "close": group[-1]["close"],
            "volume": str(sum(float(row["volume"]) for row in group)),
            "source_minute_count": len(group), "complete_60_distinct_minutes": actual == expected,
        })
    return result
