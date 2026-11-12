from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

import config


SCENARIOS = {"BASE": config.BASE, "STRESS": config.STRESS}


def trade_values(
    entry_open: float,
    exit_open: float,
    spread: float,
    slip: float,
) -> dict[str, float]:
    buy_price = entry_open * (1 + spread / 2 + slip)
    sell_price = exit_open * (1 - spread / 2 - slip)
    quantity = config.NOTIONAL_USDT / (buy_price * (1 + config.FEE))
    spent = quantity * buy_price * (1 + config.FEE)
    proceeds = quantity * sell_price * (1 - config.FEE)
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": quantity,
        "spent_usdt": spent,
        "proceeds_usdt": proceeds,
        "net": proceeds / config.NOTIONAL_USDT - 1,
    }


def _iso_week_key(timestamp: pd.Timestamp) -> tuple[int, int]:
    iso = timestamp.isocalendar()
    return int(iso.year), int(iso.week)


def build_blocks(
    minute_data: pd.DataFrame,
    signals: pd.DataFrame,
    candidate_dates: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cutoff = pd.Timestamp(config.CUTOFF_UTC)
    last_allowed = cutoff - pd.Timedelta(minutes=1)
    opens = minute_data.set_index("open_time")["open"]
    excluded: dict[str, Any] = {
        "signal_undefined_by_phase": {str(phase): 0 for phase in config.PHASES},
        "by_scenario": {
            scenario: {
                "missing_entry_by_phase": {str(phase): 0 for phase in config.PHASES},
                "missing_exit_by_phase": {str(phase): 0 for phase in config.PHASES},
                "missing_any_candle_by_phase": {str(phase): 0 for phase in config.PHASES},
                "cutoff_by_phase": {str(phase): 0 for phase in config.PHASES},
            }
            for scenario in SCENARIOS
        },
        "coverage_by_year": [],
    }
    yearly: dict[tuple[str, int, int], dict[str, int]] = defaultdict(
        lambda: {
            "candidate_blocks": 0,
            "signal_undefined": 0,
            "tradable_blocks": 0,
            "valid_blocks": 0,
            "missing_entry": 0,
            "missing_exit": 0,
            "cutoff": 0,
        }
    )
    records = []
    placebo_records = []

    for execution_date in candidate_dates:
        phase = int(execution_date.weekday())
        phase_key = str(phase)
        year = int(execution_date.year)
        raw_signal = signals.at[execution_date, "signal_on"]
        signal_defined = isinstance(raw_signal, (bool, np.bool_))
        if not signal_defined:
            excluded["signal_undefined_by_phase"][phase_key] += 1
        for scenario, costs in SCENARIOS.items():
            counts = yearly[(scenario, year, phase)]
            counts["candidate_blocks"] += 1
            if not signal_defined:
                counts["signal_undefined"] += 1

            delay = int(costs["DELAY_MIN"])
            entry_time = execution_date + pd.Timedelta(minutes=delay)
            exit_time = execution_date + pd.Timedelta(
                days=config.HOLD_DAYS, minutes=delay
            )
            scenario_excluded = excluded["by_scenario"][scenario]
            if exit_time > last_allowed:
                scenario_excluded["cutoff_by_phase"][phase_key] += 1
                counts["cutoff"] += 1
                continue

            entry_price = opens.get(entry_time)
            exit_price = opens.get(exit_time)
            entry_available = isinstance(entry_price, (int, float, np.number))
            exit_available = isinstance(exit_price, (int, float, np.number))
            if not entry_available:
                scenario_excluded["missing_entry_by_phase"][phase_key] += 1
                counts["missing_entry"] += 1
            if not exit_available:
                scenario_excluded["missing_exit_by_phase"][phase_key] += 1
                counts["missing_exit"] += 1
            if not entry_available or not exit_available:
                scenario_excluded["missing_any_candle_by_phase"][phase_key] += 1
                continue

            values = trade_values(
                float(entry_price),
                float(exit_price),
                float(costs["SPREAD"]),
                float(costs["SLIP"]),
            )
            block = {
                "scenario": scenario,
                "execution_date": execution_date,
                "phase": phase,
                "signal_on": bool(raw_signal) if signal_defined else None,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "entry_open": float(entry_price),
                "exit_open": float(exit_price),
                **values,
                "iso_year": _iso_week_key(execution_date)[0],
                "iso_week": _iso_week_key(execution_date)[1],
            }
            counts["tradable_blocks"] += 1
            placebo_records.append(block)
            if signal_defined:
                counts["valid_blocks"] += 1
                records.append(block)

    for (scenario, year, phase), counts in sorted(yearly.items()):
        candidates = counts["candidate_blocks"]
        valid = counts["valid_blocks"]
        excluded["coverage_by_year"].append(
            {
                "scenario": scenario,
                "year": year,
                "phase": phase,
                **counts,
                "coverage": valid / candidates if candidates else None,
            }
        )

    blocks = pd.DataFrame.from_records(records)
    placebo_blocks = pd.DataFrame.from_records(placebo_records)
    if blocks.empty:
        raise ValueError("No valid entry/exit blocks were constructed")
    return blocks, placebo_blocks, excluded


def candidate_execution_dates(
    daily_close: pd.Series,
) -> pd.DatetimeIndex:
    first_day = pd.Timestamp(daily_close.index.min()).normalize()
    last_day = (
        pd.Timestamp(config.CUTOFF_UTC) - pd.Timedelta(days=config.HOLD_DAYS)
    ).normalize()
    first_execution = first_day + pd.Timedelta(
        days=config.RANK_WINDOW + config.LOOKBACK_DAYS + 1
    )
    return pd.date_range(first_execution, last_day, freq="D", tz="UTC")


def week_keys_for_dates(
    execution_dates: pd.DatetimeIndex,
) -> list[tuple[int, int]]:
    keys = []
    seen = set()
    for timestamp in execution_dates:
        iso = timestamp.isocalendar()
        key = (int(iso.year), int(iso.week))
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def date_to_week_key(timestamp: pd.Timestamp) -> tuple[int, int]:
    iso = timestamp.isocalendar()
    return int(iso.year), int(iso.week)
