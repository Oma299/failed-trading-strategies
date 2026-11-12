from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import config
from blocks import build_blocks, candidate_execution_dates, week_keys_for_dates
from data import aggregate_daily_close, load_research_data
from decision import decision
from reporting import (
    ROOT,
    canonical_config_json,
    make_report,
    sha256_file,
    write_outputs,
    _git_state,
)
from resampling import bootstrap_s, placebo_test
from signals import build_execution_signals, count_on_episodes
from robustness import leave_one_year_out, phase_statistics, remove_best_on_fraction


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_pipeline(ledger_notes: str | None = None) -> dict[str, object]:
    git_hash, git_dirty = _git_state()
    input_path = ROOT / config.DATA_PATH
    data_hash = sha256_file(input_path)
    config_json = canonical_config_json()
    config_hash = _sha256_text(config_json)
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    minute_data, diagnostics = load_research_data(input_path)
    daily_close = aggregate_daily_close(minute_data)
    candidate_dates = candidate_execution_dates(daily_close)
    signals = build_execution_signals(daily_close, candidate_dates[-1])
    signals = signals.reindex(candidate_dates)
    blocks, placebo_blocks, excluded = build_blocks(
        minute_data, signals, candidate_dates
    )
    episodes = count_on_episodes(signals["signal_on"])

    base_blocks = blocks.loc[blocks["scenario"] == "BASE"].reset_index(drop=True)
    stress_blocks = blocks.loc[blocks["scenario"] == "STRESS"].reset_index(drop=True)
    base_stats = phase_statistics(base_blocks)
    stress_stats = phase_statistics(stress_blocks)

    states = signals["signal_on"].to_numpy(dtype=object)
    placebo_base_blocks = placebo_blocks.loc[
        placebo_blocks["scenario"] == "BASE"
    ].reset_index(drop=True)
    placebo = placebo_test(
        placebo_base_blocks, states, signals.index, base_stats["S"]
    )
    week_keys = week_keys_for_dates(candidate_dates)
    bootstrap = bootstrap_s(base_blocks, week_keys)
    leave_year = leave_one_year_out(base_blocks)
    trimmed_s, removed_count = remove_best_on_fraction(base_blocks)
    robustness = {
        "leave_one_year_out": leave_year,
        "S_after_best_5pct_removed": trimmed_s,
        "best_5pct_removed_count": removed_count,
        "positive_phase_fraction": base_stats["positive_phase_fraction"],
        "mean_ON_BASE": base_stats["mean_ON"],
        "mean_ON_STRESS": stress_stats["mean_ON"],
        "bootstrap_S_percentiles": bootstrap["percentiles"],
    }
    final_decision = decision(
        base_stats,
        stress_stats,
        placebo["p_value"],
        bootstrap["percentiles"]["10"],
        leave_year,
        trimmed_s,
        episodes,
    )

    results = {
        "run_id": run_id,
        "timestamp": timestamp,
        "variant_id": config.VARIANT_ID,
        "config": config.as_dict(),
        "config_hash": config_hash,
        "data_hash": data_hash,
        "git_hash": git_hash,
        "git_dirty": git_dirty,
        "data_diagnostics": diagnostics,
        "excluded_blocks": excluded,
        "on_episodes": episodes,
        "BASE": base_stats,
        "STRESS": stress_stats,
        "placebo": placebo,
        "bootstrap": bootstrap,
        "robustness": robustness,
        "decision": final_decision,
    }
    report = make_report(
        diagnostics,
        signals,
        episodes,
        excluded,
        base_stats,
        stress_stats,
        robustness,
        placebo,
        bootstrap,
        final_decision,
    )
    write_outputs(
        blocks,
        results,
        report,
        run_id,
        timestamp,
        config_hash,
        data_hash,
        git_hash,
        git_dirty,
        ledger_notes,
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger-notes")
    arguments = parser.parse_args()
    run_pipeline(arguments.ledger_notes)
