from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import config_v1 as config
from v1_data import AssetData

def build_asset_signals(asset_data: AssetData) -> tuple[pd.Series, dict[str, Any]]:
    frame = asset_data.frame
    calendar = frame.index
    row_mask = frame["row_present"].to_numpy(dtype=bool)
    close_values = frame["close"].to_numpy(dtype=float)
    close_positions = np.flatnonzero(np.isfinite(close_values))
    close_dates = calendar[close_positions]

    r_values = np.full(len(calendar), np.nan, dtype=float)
    r_reasons = np.full(len(calendar), "", dtype=object)
    for position in np.flatnonzero(row_mask):
        current_date = calendar[position]
        ref_index = int(close_dates.searchsorted(current_date, side="left")) - 1
        if ref_index < 0:
            r_reasons[position] = "no_ref_close"
            continue
        ref_position = close_positions[ref_index]
        target_base_date = (
            calendar[ref_position] - pd.Timedelta(days=config.LOOKBACK_DAYS)
        )
        base_index = int(
            close_dates.searchsorted(target_base_date, side="right")
        ) - 1
        if base_index < 0:
            r_reasons[position] = "no_base_close"
            continue
        base_position = close_positions[base_index]
        gap_days = int((target_base_date - close_dates[base_index]).days)
        if gap_days > config.MAX_BASE_GAP_DAYS:
            r_reasons[position] = "base_gap_over_4_days"
            continue
        base_close = close_values[base_position]
        if base_close == 0:
            r_reasons[position] = "zero_base_close"
            continue
        r_values[position] = close_values[ref_position] / base_close - 1.0

    signal_values = np.full(len(calendar), np.nan, dtype=float)
    reason_counts: dict[str, int] = {}
    undefined = 0
    on_long = 0
    on_short = 0
    off = 0
    row_positions = np.flatnonzero(row_mask)
    for position in row_positions:
        current_r = r_values[position]
        if not np.isfinite(current_r):
            reason = str(r_reasons[position] or "current_r_undefined")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            undefined += 1
            continue

        start_date = calendar[position] - pd.Timedelta(days=366)
        end_date = calendar[position] - pd.Timedelta(days=2)
        start = int(calendar.searchsorted(start_date, side="left"))
        end = int(calendar.searchsorted(end_date, side="right"))
        history = r_values[start:end]
        history = history[np.isfinite(history)]
        if len(history) < config.MIN_VALID_RANK_VALUES:
            reason_counts["rank_history_below_200"] = (
                reason_counts.get("rank_history_below_200", 0) + 1
            )
            undefined += 1
            continue

        long_rank = float(np.count_nonzero(history < current_r) / len(history))
        if current_r > 0 and long_rank >= config.RANK_THRESHOLD:
            signal_values[position] = 1.0
            on_long += 1
        elif asset_data.kind == "FX" and current_r < 0:
            short_rank = float(np.count_nonzero(history > current_r) / len(history))
            if short_rank >= config.RANK_THRESHOLD:
                signal_values[position] = -1.0
                on_short += 1
            else:
                signal_values[position] = 0.0
                off += 1
        else:
            signal_values[position] = 0.0
            off += 1

    signals = pd.Series(signal_values, index=calendar, name="signal")
    diagnostics: dict[str, Any] = {
        "source_rows": int(row_mask.sum()),
        "signal_defined": int((np.isfinite(signal_values) & row_mask).sum()),
        "signal_undefined": undefined,
        "undefined_reasons": reason_counts,
        "on_long": on_long,
        "on_short": on_short,
        "off": off,
    }
    return signals, diagnostics


def build_all_signals(
    assets: dict[str, AssetData],
) -> tuple[dict[str, pd.Series], dict[str, dict[str, Any]]]:
    signals: dict[str, pd.Series] = {}
    diagnostics: dict[str, dict[str, Any]] = {}
    for asset, asset_data in assets.items():
        signals[asset], diagnostics[asset] = build_asset_signals(asset_data)
    return signals, diagnostics


def align_signals_to_calendar(
    assets: dict[str, AssetData],
    signals: dict[str, pd.Series],
) -> dict[str, pd.Series]:
    first = min(asset.frame.index.min() for asset in assets.values())
    last = max(asset.frame.index.max() for asset in assets.values())
    calendar = pd.date_range(first, last, freq="D", name="date")
    return {
        asset: series.reindex(calendar).rename("signal")
        for asset, series in signals.items()
    }
