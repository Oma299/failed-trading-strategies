from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import config_stage2 as config


ROOT = Path(__file__).resolve().parent
REQUIRED_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]


def _as_utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _metadata_max_open_time(path: Path) -> pd.Timestamp:
    parquet_file = pq.ParquetFile(path)
    schema_names = parquet_file.schema_arrow.names
    if "open_time" not in schema_names:
        raise ValueError("Parquet is missing required column 'open_time'")
    column_index = schema_names.index("open_time")
    maxima = []
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        statistics = parquet_file.metadata.row_group(row_group_index).column(
            column_index
        ).statistics
        if statistics is None or not statistics.has_min_max or statistics.max is None:
            raise ValueError(
                "Parquet open_time maximum is unavailable; refusing to read rows "
                "before cutoff validation"
            )
        maxima.append(_as_utc(statistics.max))
    if not maxima:
        raise ValueError("Parquet contains no row groups")
    return max(maxima)


def load_stage2_data(
    path: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], set[pd.Timestamp]]:
    data_path = Path(path) if path is not None else ROOT / config.DATA_PATH
    if not data_path.is_absolute():
        data_path = ROOT / data_path
    cutoff = pd.Timestamp(config.CUTOFF_UTC)
    metadata_max = _metadata_max_open_time(data_path)
    if metadata_max >= cutoff:
        raise AssertionError(
            f"Parquet metadata maximum {metadata_max} is not before {cutoff}"
        )

    frame = pd.read_parquet(data_path, columns=REQUIRED_COLUMNS)
    if frame.empty:
        raise ValueError("Research Parquet has no rows")
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    if frame["open_time"].max() >= cutoff:
        raise AssertionError("Loaded rows include open_time at or after the cutoff")

    frame = frame.sort_values("open_time", kind="mergesort").reset_index(drop=True)
    frame["minute"] = frame["open_time"].dt.floor("min")
    minute_sizes = frame.groupby("minute", sort=False)["minute"].transform("size")
    ambiguous_mask = minute_sizes.gt(1)
    ambiguous_minutes = set(frame.loc[ambiguous_mask, "minute"].drop_duplicates())
    ambiguous_rows = int(ambiguous_mask.sum())
    usable = frame.loc[~ambiguous_mask].copy()
    usable["open_time"] = usable["minute"]
    usable = usable.drop(columns="minute").reset_index(drop=True)
    usable = usable.sort_values("open_time", kind="mergesort").reset_index(drop=True)

    utc_day = usable["open_time"].dt.floor("D")
    daily = (
        usable.assign(utc_day=utc_day)
        .groupby("utc_day", sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            unique_minutes=("open_time", "nunique"),
        )
    )
    daily.index = pd.DatetimeIndex(daily.index).tz_convert("UTC")
    daily_calendar = pd.date_range(
        daily.index.min(), daily.index.max(), freq="D", tz="UTC"
    )
    daily = daily.reindex(daily_calendar)
    daily["unique_minutes"] = daily["unique_minutes"].fillna(0).astype("int64")
    daily["full_d1"] = daily["unique_minutes"].eq(1440)
    incomplete = ~daily["full_d1"]
    daily.loc[incomplete, ["open", "high", "low", "close", "volume"]] = np.nan

    incomplete_daily = daily.loc[incomplete]
    incomplete_by_year = {
        str(int(year)): int(count)
        for year, count in incomplete_daily.groupby(
            incomplete_daily.index.year
        ).size().items()
    }
    diagnostics: dict[str, Any] = {
        "source_rows": int(len(frame)),
        "usable_minute_rows": int(len(usable)),
        "ambiguous_minute_buckets": int(len(ambiguous_minutes)),
        "rows_removed_from_ambiguous_minutes": ambiguous_rows,
        "incomplete_d1_days": int(incomplete.sum()),
        "missing_d1_calendar_days": int(daily["unique_minutes"].eq(0).sum()),
        "incomplete_d1_days_by_year": incomplete_by_year,
        "full_d1_days": int(daily["full_d1"].sum()),
        "min_open_time": usable["open_time"].min().isoformat(),
        "max_open_time": usable["open_time"].max().isoformat(),
        "cutoff_assertion": True,
        "timestamps_floored_to_utc_minute": True,
    }
    return usable, daily, diagnostics, ambiguous_minutes


def candidate_execution_dates(
    daily: pd.DataFrame,
) -> pd.DatetimeIndex:
    if daily.empty:
        raise ValueError("Daily data is empty")
    first_day = pd.Timestamp(daily.index.min()).normalize()
    last_day = pd.Timestamp(config.FORCED_END_BEFORE_UTC).normalize()
    if first_day > last_day:
        raise ValueError("No execution dates are available before forced end")
    return pd.date_range(first_day, last_day, freq="D", tz="UTC")
