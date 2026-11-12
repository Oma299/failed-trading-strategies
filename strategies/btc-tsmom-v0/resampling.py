from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

import config
from blocks import date_to_week_key


def shifted_states(
    states: np.ndarray,
    shift: int,
    minimum_circular_distance: int = config.PLACEBO_MIN_SHIFT_DAYS,
) -> np.ndarray:
    values = np.asarray(states, dtype=object)
    size = len(values)
    circular_distance = min(shift % size, (-shift) % size)
    if circular_distance < minimum_circular_distance:
        raise ValueError("Circular shift is smaller than the configured minimum")
    return np.roll(values, shift)


def sample_placebo_shifts(
    size: int,
    draws: int,
    rng: np.random.Generator,
    minimum_circular_distance: int = config.PLACEBO_MIN_SHIFT_DAYS,
) -> np.ndarray:
    if size <= 2 * minimum_circular_distance:
        raise ValueError("Signal series is too short for the configured placebo shift")
    choices = np.arange(minimum_circular_distance, size - minimum_circular_distance + 1)
    return rng.choice(choices, size=draws, replace=True)


def placebo_test(
    blocks: pd.DataFrame,
    states: np.ndarray,
    execution_dates: pd.DatetimeIndex,
    observed_s: float,
) -> dict[str, Any]:
    if not np.isfinite(observed_s):
        raise ValueError("Observed BASE S is undefined")
    shifts = sample_placebo_shifts(
        len(states),
        config.PLACEBO_DRAWS,
        np.random.default_rng(config.SEED),
    )
    date_positions = {timestamp: index for index, timestamp in enumerate(execution_dates)}
    block_positions = np.array(
        [date_positions[row] for row in blocks["execution_date"]], dtype=int
    )
    phases = blocks["phase"].to_numpy(dtype=int)
    nets = blocks["net"].to_numpy(dtype=float)
    greater_equal = 0
    undefined_draws = 0
    for shift in shifts:
        shifted = shifted_states(states, int(shift))
        states_for_blocks = shifted[block_positions]
        differences = []
        for phase in config.PHASES:
            mask = phases == phase
            phase_states = states_for_blocks[mask]
            phase_nets = nets[mask]
            on_mask = phase_states == True
            off_mask = phase_states == False
            if not on_mask.any() or not off_mask.any():
                differences = []
                break
            differences.append(
                float(phase_nets[on_mask].mean() - phase_nets[off_mask].mean())
            )
        if len(differences) != len(list(config.PHASES)):
            undefined_draws += 1
            continue
        placebo_s = float(np.mean(differences))
        if placebo_s >= observed_s:
            greater_equal += 1
    p_value = (1 + greater_equal) / (1 + config.PLACEBO_DRAWS)
    return {
        "draws": int(config.PLACEBO_DRAWS),
        "shifts": shifts.tolist(),
        "S_placebo_ge_observed": int(greater_equal),
        "undefined_draws": int(undefined_draws),
        "p_value": float(p_value),
    }


def bootstrap_week_weights(
    week_keys: list[tuple[int, int]],
    block_weeks: int,
    rng: np.random.Generator,
) -> np.ndarray:
    size = len(week_keys)
    if size == 0 or block_weeks <= 0:
        raise ValueError("Bootstrap requires weeks and a positive block length")
    starts = rng.integers(0, size, size=math.ceil(size / block_weeks))
    weights = np.zeros(size, dtype=np.int64)
    remaining = size
    for start in starts:
        take = min(block_weeks, remaining)
        positions = (int(start) + np.arange(take)) % size
        np.add.at(weights, positions, 1)
        remaining -= take
        if remaining == 0:
            break
    if int(weights.sum()) != size:
        raise AssertionError("Bootstrap weights do not sum to the number of weeks")
    return weights


def _weekly_state_aggregates(
    blocks: pd.DataFrame,
    week_keys: list[tuple[int, int]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    positions = {key: index for index, key in enumerate(week_keys)}
    on_sum = np.zeros((len(list(config.PHASES)), len(week_keys)), dtype=float)
    off_sum = np.zeros_like(on_sum)
    on_count = np.zeros_like(on_sum)
    off_count = np.zeros_like(on_sum)
    for row in blocks.itertuples(index=False):
        phase_index = int(row.phase)
        week_index = positions[date_to_week_key(row.execution_date)]
        if row.signal_on:
            on_sum[phase_index, week_index] += float(row.net)
            on_count[phase_index, week_index] += 1
        else:
            off_sum[phase_index, week_index] += float(row.net)
            off_count[phase_index, week_index] += 1
    return on_sum, off_sum, on_count, off_count


def bootstrap_s(
    blocks: pd.DataFrame,
    week_keys: list[tuple[int, int]],
) -> dict[str, Any]:
    on_sum, off_sum, on_count, off_count = _weekly_state_aggregates(blocks, week_keys)
    rng = np.random.default_rng(config.SEED + 1)
    samples = []
    excluded_phase_occurrences = 0
    draws_with_excluded_phases = 0
    draws_with_no_valid_phases = 0

    for _ in range(config.BOOT_DRAWS):
        weights = bootstrap_week_weights(week_keys, config.BOOT_BLOCK_WEEKS, rng)
        weighted_on_count = on_count @ weights
        weighted_off_count = off_count @ weights
        valid = (weighted_on_count > 0) & (weighted_off_count > 0)
        excluded_phase_occurrences += int((~valid).sum())
        if (~valid).any():
            draws_with_excluded_phases += 1
        if not valid.any():
            draws_with_no_valid_phases += 1
            continue
        mean_on = (on_sum @ weights)[valid] / weighted_on_count[valid]
        mean_off = (off_sum @ weights)[valid] / weighted_off_count[valid]
        samples.append(float(np.mean(mean_on - mean_off)))

    if not samples:
        raise ValueError("All bootstrap draws have no phase with ON and OFF weight")
    percentiles = np.percentile(samples, [10, 50, 90])
    return {
        "draws_requested": int(config.BOOT_DRAWS),
        "draws_with_valid_S": int(len(samples)),
        "draws_with_excluded_phases": int(draws_with_excluded_phases),
        "excluded_phase_occurrences": int(excluded_phase_occurrences),
        "draws_with_no_valid_phases": int(draws_with_no_valid_phases),
        "percentiles": {
            "10": float(percentiles[0]),
            "50": float(percentiles[1]),
            "90": float(percentiles[2]),
        },
    }
