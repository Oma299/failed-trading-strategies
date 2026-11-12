from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import config


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _parquet_max_open_time(path: Path) -> pd.Timestamp:
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
                "Parquet open_time maximum is unavailable in row-group metadata; "
                "refusing to read rows before cutoff validation"
            )
        maxima.append(_utc_timestamp(statistics.max))
    if not maxima:
        raise ValueError("Parquet contains no row groups")
    return max(maxima)


def _missing_minute_count(times: pd.Series) -> int:
    floored = times.dt.floor("min")
    gaps = floored.diff().dt.total_seconds().div(60)
    return int(np.maximum(np.rint(gaps.fillna(1).to_numpy()) - 1, 0).sum())


def load_research_data(
    path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    data_path = Path(path) if path is not None else Path(config.DATA_PATH)
    cutoff = pd.Timestamp(config.CUTOFF_UTC)
    metadata_max = _parquet_max_open_time(data_path)
    if metadata_max >= cutoff:
        raise AssertionError(
            f"Parquet metadata maximum {metadata_max} is not before {cutoff}"
        )

    frame = pd.read_parquet(data_path, columns=["open_time", "open", "high", "low", "close", "volume"])
    frame["open_time"] = pd.to_datetime(frame["open_time"], utc=True)
    assert not frame.empty, "Research Parquet has no rows"
    maximum = frame["open_time"].max()
    assert maximum < cutoff, f"Maximum open_time {maximum} is not before {cutoff}"

    times = frame["open_time"]
    diagnostics: dict[str, object] = {
        "rows": int(len(frame)),
        "min_open_time": times.min().isoformat(),
        "max_open_time": maximum.isoformat(),
        "duplicate_open_times": int(times.duplicated().sum()),
        "strictly_increasing": bool(
            times.is_monotonic_increasing and not times.duplicated().any()
        ),
        "missing_minutes": _missing_minute_count(times),
        "cutoff_assertion": True,
    }
    return frame, diagnostics


def aggregate_daily_close(frame: pd.DataFrame) -> pd.Series:
    utc_days = frame["open_time"].dt.floor("D")
    return frame.groupby(utc_days, sort=True)["close"].last().astype("float64")
