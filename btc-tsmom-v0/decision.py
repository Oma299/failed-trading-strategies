from __future__ import annotations

import math
from typing import Any

import config


def decision(
    base: dict[str, Any],
    stress: dict[str, Any],
    placebo_p: float,
    bootstrap_p10: float,
    leave_one_year_out: dict[str, float | None],
    trimmed_s: float | None,
    on_episodes: int,
) -> str:
    s_base = base.get("S")
    mean_on_base = base.get("mean_ON")
    median_on_blocks = base.get("median_ON_blocks_per_phase")
    positive_phases = base.get("positive_phase_count")
    mean_on_stress = stress.get("mean_ON")

    if (
        median_on_blocks is None
        or median_on_blocks < config.MIN_ON_BLOCKS_PER_PHASE
        or on_episodes < config.MIN_ON_EPISODES
    ):
        return "INSUFFICIENT_DATA"

    if s_base is None or mean_on_base is None or positive_phases is None:
        return "INSUFFICIENT_DATA"
    if (
        s_base <= 0
        or mean_on_base <= 0
        or positive_phases <= 3
    ):
        return "ABANDON"

    robust_years = bool(leave_one_year_out) and all(
        value is not None and math.isfinite(value) and value > 0
        for value in leave_one_year_out.values()
    )
    continue_conditions = (
        placebo_p <= config.ALPHA_ONE_SIDED
        and bootstrap_p10 > 0
        and positive_phases >= 5
        and mean_on_stress is not None
        and mean_on_stress > 0
        and robust_years
        and trimmed_s is not None
        and trimmed_s > 0
    )
    return "CONTINUE" if continue_conditions else "INSUFFICIENT_DATA"
