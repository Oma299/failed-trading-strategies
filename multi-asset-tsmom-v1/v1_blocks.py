from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

import config_v1 as config
from v1_data import AssetData

BLOCK_COLUMNS = [
    "asset",
    "kind",
    "entry_date",
    "exit_date",
    "direction",
    "entry_open",
    "exit_open",
    "gross_net_return",
    "price_return",
    "cost",
    "net",
    "iso_year",
    "iso_week",
    "calendar_position",
]


def _week_key(day: pd.Timestamp) -> tuple[int, int]:
    iso = day.isocalendar()
    return int(iso.year), int(iso.week)


def build_blocks(
    assets: dict[str, AssetData],
    signals: dict[str, pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, int]]]:
    opportunities: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    counters: dict[str, dict[str, int]] = {}

    for asset, asset_data in assets.items():
        frame = asset_data.frame
        signal = signals[asset]
        asset_counters = {
            "executable_dates": 0,
            "undefined_signal_dates": 0,
            "off_signal_dates": 0,
            "on_candidates": 0,
            "entry_no_row": 0,
            "entry_empty_open": 0,
            "entry_empty_close": 0,
            "exit_no_row": 0,
            "exit_empty_open": 0,
            "exit_empty_close": 0,
        }
        decision_positions = np.flatnonzero(
            frame["row_present"].to_numpy(dtype=bool)
        )
        asset_counters["executable_dates"] = int(
            (
                frame["row_present"].to_numpy(dtype=bool)
                & frame["open"].notna().to_numpy(dtype=bool)
            ).sum()
        )

        for position in decision_positions:
            entry_date = frame.index[position]
            direction = signal.get(entry_date, np.nan)
            if not np.isfinite(direction):
                asset_counters["undefined_signal_dates"] += 1
                is_on = False
            elif direction == 0:
                asset_counters["off_signal_dates"] += 1
                is_on = False
            else:
                asset_counters["on_candidates"] += 1
                is_on = True

            if pd.isna(frame.iloc[position]["open"]):
                if is_on:
                    asset_counters["entry_empty_open"] += 1
                continue
            if pd.isna(frame.iloc[position]["close"]):
                if is_on:
                    asset_counters["entry_empty_close"] += 1
                continue

            exit_date = entry_date + timedelta(days=config.HOLD_DAYS)
            if exit_date not in frame.index or not bool(
                frame.at[exit_date, "row_present"]
            ):
                if is_on:
                    asset_counters["exit_no_row"] += 1
                continue
            exit_open = frame.at[exit_date, "open"]
            exit_close = frame.at[exit_date, "close"]
            if pd.isna(exit_open):
                if is_on:
                    asset_counters["exit_empty_open"] += 1
            if pd.isna(exit_close):
                if is_on:
                    asset_counters["exit_empty_close"] += 1
            if pd.isna(exit_open) or pd.isna(exit_close):
                continue

            entry_open = float(frame.at[entry_date, "open"])
            exit_open = float(exit_open)
            cost = (
                config.FX_ROUND_TRIP_COST
                if asset_data.kind == "FX"
                else config.ETF_ROUND_TRIP_COST
            )
            iso_year, iso_week = _week_key(entry_date)
            price_return = exit_open / entry_open - 1.0
            calendar_position = signal.index.get_loc(entry_date)
            opportunity = {
                "asset": asset,
                "kind": asset_data.kind,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "direction": int(direction) if is_on else 0,
                "entry_open": entry_open,
                "exit_open": exit_open,
                "gross_net_return": (
                    float(direction) * price_return if is_on else 0.0
                ),
                "price_return": price_return,
                "cost": cost,
                "net": (
                    float(direction) * price_return - cost if is_on else 0.0
                ),
                "iso_year": iso_year,
                "iso_week": iso_week,
                "calendar_position": int(calendar_position),
            }
            opportunities.append(opportunity)
            if is_on:
                blocks.append(opportunity.copy())
        counters[asset] = asset_counters

    opportunities_frame = pd.DataFrame(opportunities, columns=BLOCK_COLUMNS)
    blocks_frame = pd.DataFrame(blocks, columns=BLOCK_COLUMNS)
    return blocks_frame, opportunities_frame, counters
