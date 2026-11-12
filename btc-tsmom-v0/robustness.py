from __future__ import annotations

"""Stage 1 phase statistics and robustness checks."""

import math
from typing import Any

import numpy as np
import pandas as pd

import config


def phase_statistics(
    blocks: pd.DataFrame,
    phases: range = config.PHASES,
) -> dict[str, Any]:
    phase_rows = []
    differences = []
    on_means = []
    complete = True
    for phase in phases:
        phase_blocks = blocks.loc[blocks["phase"] == phase]
        on = phase_blocks.loc[phase_blocks["signal_on"], "net"].to_numpy(dtype=float)
        off = phase_blocks.loc[~phase_blocks["signal_on"], "net"].to_numpy(dtype=float)
        mean_on = float(on.mean()) if on.size else None
        mean_off = float(off.mean()) if off.size else None
        difference = mean_on - mean_off if mean_on is not None and mean_off is not None else None
        if difference is None:
            complete = False
        else:
            differences.append(difference)
        if mean_on is not None:
            on_means.append(mean_on)
        phase_rows.append(
            {
                "phase": int(phase),
                "blocks_on": int(on.size),
                "blocks_off": int(off.size),
                "mean_on": mean_on,
                "mean_off": mean_off,
                "S_phase": difference,
            }
        )

    return {
        "phases": phase_rows,
        "S": float(np.mean(differences)) if complete and len(differences) == len(list(phases)) else None,
        "mean_ON": float(np.mean(on_means)) if len(on_means) == len(list(phases)) else None,
        "positive_phase_count": int(sum(value > 0 for value in differences)),
        "positive_phase_fraction": (
            float(sum(value > 0 for value in differences) / len(list(phases)))
            if len(differences) == len(list(phases))
            else None
        ),
        "median_ON_blocks_per_phase": float(
            np.median([row["blocks_on"] for row in phase_rows])
        ),
    }


def s_for_states(
    blocks: pd.DataFrame,
    states_by_date: dict[pd.Timestamp, bool | None],
    phases: range = config.PHASES,
) -> float:
    differences = []
    for phase in phases:
        phase_blocks = blocks.loc[blocks["phase"] == phase]
        on_values = []
        off_values = []
        for row in phase_blocks.itertuples(index=False):
            state = states_by_date.get(row.execution_date)
            if state is None:
                continue
            (on_values if state else off_values).append(float(row.net))
        if not on_values or not off_values:
            return float("nan")
        differences.append(float(np.mean(on_values) - np.mean(off_values)))
    return float(np.mean(differences))


def leave_one_year_out(
    blocks: pd.DataFrame,
    phases: range = config.PHASES,
) -> dict[str, float | None]:
    results = {}
    for year in sorted(int(value) for value in blocks["execution_date"].dt.year.unique()):
        remaining = blocks.loc[blocks["execution_date"].dt.year != year]
        results[str(year)] = phase_statistics(remaining, phases)["S"]
    return results


def remove_best_on_fraction(
    blocks: pd.DataFrame,
    fraction: float = config.ROBUSTNESS_TRIM_FRACTION,
    phases: range = config.PHASES,
) -> tuple[float | None, int]:
    on = blocks.loc[blocks["signal_on"]]
    remove_count = int(math.ceil(len(on) * fraction))
    if remove_count == 0:
        return phase_statistics(blocks, phases)["S"], 0
    remove_indices = on.sort_values("net", ascending=False, kind="mergesort").index[
        :remove_count
    ]
    trimmed = blocks.drop(index=remove_indices)
    return phase_statistics(trimmed, phases)["S"], remove_count
