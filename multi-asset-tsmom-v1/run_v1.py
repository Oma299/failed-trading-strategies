from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

import config_v1 as config
from v1_blocks import build_blocks
from v1_data import load_v1_data
from v1_metrics import (
    run_bootstrap,
    run_placebo,
    summarize_metrics,
    union_iso_weeks,
)
from v1_reporting import (
    git_state,
    hash_json,
    make_report,
    write_outputs,
)
from v1_signal import align_signals_to_calendar, build_all_signals


def run_pipeline() -> dict[str, Any]:
    assets = load_v1_data()
    signals, signal_diagnostics = build_all_signals(assets)
    signals = align_signals_to_calendar(assets, signals)
    blocks, opportunities, block_counters = build_blocks(assets, signals)

    observed_t = float(blocks["net"].mean()) if not blocks.empty else None
    rng = np.random.default_rng(config.SEED)
    placebo = run_placebo(opportunities, signals, observed_t, rng)
    weeks = union_iso_weeks(assets)
    bootstrap = run_bootstrap(blocks, weeks, rng)
    calendar_years = list(
        range(
            min(asset.frame.index.min().year for asset in assets.values()),
            max(asset.frame.index.max().year for asset in assets.values()) + 1,
        )
    )
    metrics = summarize_metrics(blocks, placebo, bootstrap, calendar_years)
    metrics["blocks"] = blocks

    data_hashes = {asset: data.data_hash for asset, data in assets.items()}
    config_hash = hash_json(config.as_dict())
    data_hash = hash_json(data_hashes)
    git_hash, git_dirty = git_state()
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    diagnostics = {
        asset: data.diagnostics for asset, data in assets.items()
    }
    results = {
        "run_id": run_id,
        "timestamp": timestamp,
        "variant_id": config.VARIANT_ID,
        "stage": config.STAGE,
        "config": config.as_dict(),
        "config_hash": config_hash,
        "data_hash": data_hash,
        "data_sha256": data_hashes,
        "git_hash": git_hash,
        "git_dirty": git_dirty,
        "data_diagnostics": diagnostics,
        "signal_diagnostics": signal_diagnostics,
        "block_exclusions": block_counters,
        "metrics": {
            key: value
            for key, value in metrics.items()
            if key != "blocks"
        },
        "placebo": placebo,
        "bootstrap": bootstrap,
    }
    report = make_report(
        assets,
        signal_diagnostics,
        block_counters,
        metrics,
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
    )
    return results


if __name__ == "__main__":
    run_pipeline()
