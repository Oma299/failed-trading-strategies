from __future__ import annotations

import numpy as np
import pandas as pd

import config


def build_execution_signals(
    daily_close: pd.Series,
    candidate_end: pd.Timestamp,
) -> pd.DataFrame:
    if daily_close.empty:
        raise ValueError("Daily close series is empty")

    start_day = pd.Timestamp(daily_close.index.min()).normalize()
    end_day = pd.Timestamp(candidate_end).normalize()
    start_execution = start_day + pd.Timedelta(
        days=config.RANK_WINDOW + config.LOOKBACK_DAYS + 1
    )
    if end_day < start_execution:
        raise ValueError("Insufficient calendar span for the configured signal")

    calendar = pd.date_range(start_day, end_day - pd.Timedelta(days=1), freq="D", tz="UTC")
    closes = daily_close.copy()
    closes.index = pd.DatetimeIndex(closes.index).tz_convert("UTC").normalize()
    closes = closes[~closes.index.duplicated(keep="last")].reindex(calendar)
    returns = closes.div(closes.shift(config.LOOKBACK_DAYS)).sub(1).to_numpy()

    execution_dates = pd.date_range(start_execution, end_day, freq="D", tz="UTC")
    rows = []
    first_index = config.RANK_WINDOW + config.LOOKBACK_DAYS
    for execution_date in execution_dates:
        current_index = int((execution_date - start_day).days) - 1
        historical = returns[current_index - config.RANK_WINDOW : current_index]
        current_return = returns[current_index]
        if (
            current_index < first_index
            or len(historical) != config.RANK_WINDOW
            or not np.isfinite(current_return)
            or not np.isfinite(historical).all()
        ):
            rows.append(
                {
                    "execution_date": execution_date,
                    "return": np.nan,
                    "rank": np.nan,
                    "signal_on": None,
                }
            )
            continue

        rank = float(np.mean(historical < current_return))
        rows.append(
            {
                "execution_date": execution_date,
                "return": float(current_return),
                "rank": rank,
                "signal_on": bool(
                    current_return > 0 and rank >= config.RANK_THRESHOLD
                ),
            }
        )
    return pd.DataFrame(rows).set_index("execution_date")


def count_on_episodes(signal_on: pd.Series) -> int:
    values = signal_on.to_numpy(dtype=object)
    episodes = 0
    previous_on = False
    for value in values:
        is_on = isinstance(value, (bool, np.bool_)) and bool(value)
        if is_on and not previous_on:
            episodes += 1
        previous_on = is_on
    return episodes


def circular_run_lengths(values: np.ndarray) -> tuple[int, ...]:
    flags = np.asarray(values, dtype=bool)
    if flags.size == 0 or not flags.any():
        return ()
    if flags.all():
        return (int(flags.size),)

    lengths = []
    starts = np.flatnonzero(flags & ~np.roll(flags, 1))
    for start in starts:
        length = 0
        position = int(start)
        while flags[position]:
            length += 1
            position = (position + 1) % flags.size
        lengths.append(length)
    return tuple(sorted(lengths))
