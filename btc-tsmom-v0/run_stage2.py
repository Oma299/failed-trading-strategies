from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import config_stage2 as config
from stage2_data import candidate_execution_dates, load_stage2_data
from stage2_engine import run_scenario
from stage2_metrics import (
    bootstrap_mean_net_r,
    calculate_buy_and_hold,
    evaluate_criteria,
    placebo_test,
    summarize_scenario,
)
from stage2_reporting import (
    ROOT,
    append_failed_run,
    canonical_config_json,
    git_state,
    make_report,
    sha256_file,
    write_outputs,
)
from stage2_signal import build_execution_signals, exclusion_counts


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
def run_pipeline() -> dict[str, Any]:
    config_json = canonical_config_json()
    config_hash = _sha256_text(config_json)
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    data_hash = ""
    output_written = False
    try:
        git_hash, git_dirty = git_state()
        data_path = ROOT / config.DATA_PATH
        data_hash = sha256_file(data_path)

        minute_data, daily, diagnostics, ambiguous_minutes = load_stage2_data(data_path)
        all_dates = candidate_execution_dates(daily)
        all_signals = build_execution_signals(daily, all_dates)
        eligible_start = all_signals.index[
            all_signals["signal_defined"] & all_signals["atr_defined"]
        ]
        if eligible_start.empty:
            raise ValueError("No execution date has all required signal and ATR inputs")
        dates = all_dates[all_dates >= eligible_start[0]]
        signals = all_signals.loc[dates]
        exclusions = exclusion_counts(signals)
        exclusions["strategy_start_date"] = dates[0].isoformat()

        scenario_runs = {
            scenario: run_scenario(
                minute_data,
                ambiguous_minutes,
                dates,
                signals,
                scenario,
                collect_equity=True,
            )
            for scenario in ("BASE", "STRESS")
        }
        scenario_results = {
            scenario: summarize_scenario(scenario_runs[scenario])
            for scenario in ("BASE", "STRESS")
        }
        base_trades = scenario_runs["BASE"]["trades"]
        bootstrap = bootstrap_mean_net_r(base_trades, dates)
        placebo = placebo_test(
            scenario_runs["BASE"]["context"],
            dates,
            signals,
            scenario_results["BASE"]["mean_net_r"],
        )
        benchmarks = {
            scenario: calculate_buy_and_hold(scenario_runs[scenario], dates, signals)
            for scenario in ("BASE", "STRESS")
        }
        criteria = evaluate_criteria(
            scenario_results["BASE"],
            scenario_results["STRESS"],
            bootstrap,
            placebo,
        )
        report = make_report(
            diagnostics,
            exclusions,
            scenario_results,
            placebo,
            bootstrap,
            benchmarks,
            criteria,
        )

        blocks = pd.concat(
            [
                scenario_runs["BASE"]["trades"],
                scenario_runs["STRESS"]["trades"],
            ],
            ignore_index=True,
        )
        results = {
            "run_id": run_id,
            "timestamp": timestamp,
            "stage": config.STAGE,
            "variant_id": config.VARIANT_ID,
            "config": config.as_dict(),
            "config_hash": config_hash,
            "data_hash": data_hash,
            "git_hash": git_hash,
            "git_dirty": git_dirty,
            "data_diagnostics": diagnostics,
            "signal_exclusions": exclusions,
            "scenario_results": scenario_results,
            "execution_counters": {
                scenario: scenario_runs[scenario]["counters"]
                for scenario in ("BASE", "STRESS")
            },
            "bootstrap_base": bootstrap,
            "placebo": placebo,
            "buy_and_hold": benchmarks,
            "criteria": criteria,
        }
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
        )
        output_written = True
        return results
    finally:
        if not output_written:
            _, error, _ = sys.exc_info()
            append_failed_run(
                run_id,
                timestamp,
                config_hash,
                data_hash,
                error,
            )


if __name__ == "__main__":
    run_pipeline()
