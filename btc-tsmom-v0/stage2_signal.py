from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import config_stage2 as config


def _atr_for_execution_date(
    daily: pd.DataFrame,
    execution_date: pd.Timestamp,
) -> float | None:
    first_full_day = execution_date - pd.Timedelta(days=config.ATR_DAYS + 1)
    window_start = execution_date - pd.Timedelta(days=config.ATR_DAYS)
    window_end = execution_date - pd.Timedelta(days=1)
    required_days = pd.date_range(
        first_full_day, window_end, freq="D", tz="UTC"
    )
    window = daily.reindex(required_days)
    if len(window) != config.ATR_DAYS + 1 or not window["full_d1"].fillna(False).all():
        return None

    previous_close = float(window.iloc[0]["close"])
    true_ranges = []
    for row in window.iloc[1:].itertuples():
        true_ranges.append(
            max(
                float(row.high) - float(row.low),
                abs(float(row.high) - previous_close),
                abs(float(row.low) - previous_close),
            )
        )
        previous_close = float(row.close)
    if len(true_ranges) != config.ATR_DAYS:
        return None
    return float(np.mean(true_ranges))


def build_execution_signals(
    daily: pd.DataFrame,
    execution_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    if daily.empty:
        raise ValueError("Daily data is empty")

    full_calendar = pd.date_range(
        pd.Timestamp(daily.index.min()).normalize(),
        pd.Timestamp(execution_dates.max()).normalize() - pd.Timedelta(days=1),
        freq="D",
        tz="UTC",
    )
    valid_closes = daily["close"].where(daily["full_d1"]).copy()
    valid_closes.index = pd.DatetimeIndex(valid_closes.index).tz_convert("UTC").normalize()
    closes = valid_closes.reindex(full_calendar)
    returns = closes.div(closes.shift(config.LOOKBACK_DAYS)).sub(1)

    rows = []
    for execution_date in execution_dates:
        current_date = execution_date - pd.Timedelta(days=1)
        history_start = execution_date - pd.Timedelta(
            days=config.RANK_WINDOW + 1
        )
        history_end = execution_date - pd.Timedelta(days=2)
        historical = returns.loc[history_start:history_end]
        current_return = returns.get(current_date, np.nan)

        current_defined = bool(np.isfinite(current_return))
        history_defined = (
            len(historical) == config.RANK_WINDOW
            and bool(np.isfinite(historical.to_numpy(dtype=float)).all())
        )
        signal_defined = current_defined and history_defined
        rank: float | None = None
        signal_on: bool | None = None
        if signal_defined:
            rank = float(np.mean(historical.to_numpy(dtype=float) < current_return))
            signal_on = bool(
                current_return > 0 and rank >= config.RANK_THRESHOLD
            )

        atr = _atr_for_execution_date(daily, execution_date)
        rows.append(
            {
                "execution_date": execution_date,
                "return": float(current_return) if current_defined else np.nan,
                "rank": rank,
                "signal_on": signal_on,
                "signal_defined": signal_defined,
                "missing_current_r": not current_defined,
                "missing_rank_history": not history_defined,
                "atr": atr,
                "atr_defined": atr is not None,
                "missing_atr_window": atr is None,
            }
        )
    return pd.DataFrame.from_records(rows).set_index("execution_date")


def exclusion_counts(signals: pd.DataFrame) -> dict[str, Any]:
    signal_missing = signals["signal_on"].isna()
    atr_missing = ~signals["atr_defined"]
    return {
        "candidate_execution_days": int(len(signals)),
        "missing_current_r_days": int(signals["missing_current_r"].sum()),
        "missing_rank_history_days": int(signals["missing_rank_history"].sum()),
        "missing_atr_window_days": int(signals["missing_atr_window"].sum()),
        "undefined_signal_days": int(signal_missing.sum()),
        "entry_ineligible_days": int((signal_missing | atr_missing).sum()),
    }
