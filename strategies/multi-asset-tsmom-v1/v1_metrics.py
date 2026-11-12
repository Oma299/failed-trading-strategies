from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

import config_v1 as config
from v1_data import AssetData


def iso_week_key(value: Any) -> tuple[int, int]:
    week = pd.Timestamp(value).isocalendar()
    return int(week.year), int(week.week)


def union_iso_weeks(assets: dict[str, AssetData]) -> list[tuple[int, int]]:
    first = min(asset.frame.index.min() for asset in assets.values())
    last = max(asset.frame.index.max() for asset in assets.values())
    first_monday = first - pd.Timedelta(days=first.weekday())
    last_monday = last - pd.Timedelta(days=last.weekday())
    mondays = pd.date_range(first_monday, last_monday, freq="7D")
    keys = [iso_week_key(day) for day in mondays]
    if len(keys) != len(set(keys)):
        raise AssertionError("ISO-week keys are not unique")
    return keys


def bootstrap_weights(
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if size <= 0:
        raise ValueError("Bootstrap requires at least one ISO week")
    weights = np.zeros(size, dtype=np.int64)
    remaining = size
    starts = rng.integers(
        0,
        size,
        size=math.ceil(size / config.BOOT_BLOCK_WEEKS),
    )
    for start in starts:
        take = min(config.BOOT_BLOCK_WEEKS, remaining)
        positions = (int(start) + np.arange(take)) % size
        np.add.at(weights, positions, 1)
        remaining -= take
        if remaining == 0:
            break
    if int(weights.sum()) != size:
        raise AssertionError("Bootstrap weights do not sum to the ISO-week count")
    return weights


def pooled_t(blocks: pd.DataFrame) -> float | None:
    if blocks.empty:
        return None
    return float(blocks["net"].mean())


def _prepare_placebo_inputs(
    opportunities: pd.DataFrame,
    signals: dict[str, pd.Series],
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    prepared = []
    for asset, series in signals.items():
        rows = opportunities.loc[opportunities["asset"] == asset]
        if rows.empty:
            continue
        prepared.append(
            (
                series.to_numpy(dtype=float),
                rows["calendar_position"].to_numpy(dtype=np.int64),
                (
                    rows["exit_open"].to_numpy(dtype=float)
                    / rows["entry_open"].to_numpy(dtype=float)
                    - 1.0
                ),
                rows["cost"].to_numpy(dtype=float),
            )
        )
    return prepared


def _placebo_stat_from_inputs(
    prepared: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    shift_days: int,
) -> float | None:
    total = 0.0
    count = 0
    for signal_values, positions, returns, costs in prepared:
        directions = signal_values[(positions - shift_days) % len(signal_values)]
        active = np.isfinite(directions) & (directions != 0)
        if not np.any(active):
            continue
        values = directions[active] * returns[active] - costs[active]
        total += float(values.sum())
        count += int(len(values))
    return total / count if count else None


def placebo_stat_for_shift(
    opportunities: pd.DataFrame,
    signals: dict[str, pd.Series],
    shift_days: int,
) -> float | None:
    return _placebo_stat_from_inputs(
        _prepare_placebo_inputs(opportunities, signals),
        shift_days,
    )


def run_placebo(
    opportunities: pd.DataFrame,
    signals: dict[str, pd.Series],
    observed_t: float | None,
    rng: np.random.Generator,
) -> dict[str, Any]:
    n_min = min(len(series) for series in signals.values())
    if n_min < 2 * config.PLACEBO_MIN_SHIFT_DAYS + 1:
        raise ValueError("The shortest asset calendar is too small for placebo shifts")

    exceed = 0
    no_on_draws = 0
    valid_values: list[float] = []
    shift_min = config.PLACEBO_MIN_SHIFT_DAYS
    shift_max = n_min - config.PLACEBO_MIN_SHIFT_DAYS
    prepared = _prepare_placebo_inputs(opportunities, signals)
    for _ in range(config.PLACEBO_DRAWS):
        shift = int(rng.integers(shift_min, shift_max + 1))
        placebo_t = _placebo_stat_from_inputs(prepared, shift)
        if placebo_t is None:
            no_on_draws += 1
            if observed_t is not None:
                exceed += 1
        else:
            valid_values.append(placebo_t)
            if observed_t is not None and placebo_t >= observed_t:
                exceed += 1

    p_value = (
        float((1 + exceed) / (1 + config.PLACEBO_DRAWS))
        if observed_t is not None
        else None
    )
    return {
        "draws_requested": config.PLACEBO_DRAWS,
        "draws_with_on_blocks": len(valid_values),
        "draws_without_on_blocks": no_on_draws,
        "exceed_count": exceed,
        "p_value": p_value,
        "observed_t": observed_t,
        "shift_days_min": shift_min,
        "shift_days_max": shift_max,
        "n_min_calendar_days": n_min,
    }


def run_bootstrap(
    blocks: pd.DataFrame,
    weeks: list[tuple[int, int]],
    rng: np.random.Generator,
) -> dict[str, Any]:
    week_positions = {key: i for i, key in enumerate(weeks)}
    sums = np.zeros(len(weeks), dtype=float)
    counts = np.zeros(len(weeks), dtype=float)
    for row in blocks.itertuples(index=False):
        key = (int(row.iso_year), int(row.iso_week))
        position = week_positions[key]
        sums[position] += float(row.net)
        counts[position] += 1.0

    samples: list[float] = []
    no_on_draws = 0
    for _ in range(config.BOOT_DRAWS):
        weights = bootstrap_weights(len(weeks), rng)
        on_weight = float(counts @ weights)
        if on_weight == 0:
            no_on_draws += 1
            continue
        samples.append(float((sums @ weights) / on_weight))

    if samples:
        p10, p50, p90 = np.percentile(
            np.asarray(samples, dtype=float),
            [10, 50, 90],
        )
        percentiles: dict[str, float | None] = {
            "10": float(p10),
            "50": float(p50),
            "90": float(p90),
        }
    else:
        percentiles = {"10": None, "50": None, "90": None}
    return {
        "draws_requested": config.BOOT_DRAWS,
        "draws_valid": len(samples),
        "draws_without_on_blocks": no_on_draws,
        "week_count": len(weeks),
        "block_weeks": config.BOOT_BLOCK_WEEKS,
        "percentiles": percentiles,
    }


def robustness(
    blocks: pd.DataFrame,
    calendar_years: list[int] | None = None,
) -> dict[str, Any]:
    years = calendar_years or (
        sorted({int(pd.Timestamp(day).year) for day in blocks["entry_date"]})
        if not blocks.empty
        else []
    )
    if blocks.empty:
        return {
            "leave_one_year_out": {str(year): None for year in years},
            "top_5_percent_removed_t": None,
            "removed_best_block_count": 0,
        }
    leave_one_year_out: dict[str, float | None] = {}
    for year in years:
        retained = blocks.loc[blocks["entry_date"].map(lambda d: d.year != year)]
        leave_one_year_out[str(year)] = pooled_t(retained)

    remove_count = int(math.ceil(config.BEST_BLOCK_FRACTION * len(blocks)))
    retained = blocks.sort_values("net", ascending=False).iloc[remove_count:]
    return {
        "leave_one_year_out": leave_one_year_out,
        "top_5_percent_removed_t": pooled_t(retained),
        "removed_best_block_count": remove_count,
    }


def decision_v1(metrics: dict[str, Any]) -> str:
    if metrics["on_block_count"] < config.MIN_ON_BLOCKS:
        return "INSUFFICIENT_DATA"

    t_value = metrics["pooled_t"]
    p_value = metrics["placebo"]["p_value"]
    positive_assets = metrics["positive_asset_count"]
    if (
        t_value is None
        or t_value <= 0
        or p_value is not None and p_value > config.ABANDON_PLACEBO_P
        or positive_assets < config.ABANDON_MIN_POSITIVE_ASSETS
    ):
        return "ABANDON"

    bootstrap_p10 = metrics["bootstrap"]["percentiles"]["10"]
    leave_year = metrics["robustness"]["leave_one_year_out"]
    leave_year_ok = bool(leave_year) and all(
        value is not None and value > 0 for value in leave_year.values()
    )
    continue_ok = (
        p_value is not None
        and p_value <= config.CONTINUE_PLACEBO_P
        and bootstrap_p10 is not None
        and bootstrap_p10 > 0
        and positive_assets >= config.CONTINUE_MIN_POSITIVE_ASSETS
        and leave_year_ok
        and metrics["robustness"]["top_5_percent_removed_t"] is not None
        and metrics["robustness"]["top_5_percent_removed_t"] > 0
    )
    return "CONTINUE" if continue_ok else "INSUFFICIENT_DATA"


def summarize_metrics(
    blocks: pd.DataFrame,
    placebo: dict[str, Any],
    bootstrap: dict[str, Any],
    calendar_years: list[int] | None = None,
) -> dict[str, Any]:
    per_asset: dict[str, float | None] = {}
    assets = list(config.ASSETS)
    for asset in assets:
        subset = blocks.loc[blocks["asset"] == asset]
        per_asset[asset] = pooled_t(subset)
    positive_asset_count = sum(
        value is not None and value > 0 for value in per_asset.values()
    )
    result: dict[str, Any] = {
        "on_block_count": int(len(blocks)),
        "pooled_t": pooled_t(blocks),
        "t_asset": per_asset,
        "positive_asset_count": int(positive_asset_count),
        "placebo": placebo,
        "bootstrap": bootstrap,
        "robustness": robustness(blocks, calendar_years),
    }
    result["decision"] = decision_v1(result)
    return result
