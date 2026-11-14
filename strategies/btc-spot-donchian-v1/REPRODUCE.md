# Reproduction guide — Donchian V1

## Safe focused tests

The copied unit tests use small synthetic in-memory bars. They do not load historical CSV data, invoke a saved historical experiment, use a network, or place orders.

From this package root, with Python 3.9 or later:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_btc_spot_donchian_v1.py' -v
```

The model, runners, and tests use the Python standard library only.

## Historical runners (not executed for staging)

Canonical Markdown reports and compact aggregate metrics/inventory/control-audit tables are saved here. Per-trade/per-signal files, dense equity series, detailed indicator rows, and gallery assets were intentionally excluded from this overlay. No historical backtest was rerun to prepare it. The required minute data is intentionally not included. For an explicitly authorized reproduction with the exact source data and hashes recorded in the configs:

```sh
# Jan–Jun 2025 only; warmup rows are prior to the requested period.
PYTHONPATH=src python3 -m vp_bot.run_btc_spot_donchian_v1 \
  --minutes /path/to/compatible_m1.csv \
  --start 2025-01-01T00:00:00 --end 2025-07-01T00:00:00 \
  --output-dir reports/reproduction_jan_jun_2025

# Corrected BASE_20D control comparison (the runner also runs the
# DAILY_REARM comparator). Segment inventory is bundled at the path expected
# by this historical runner. Its outputs keep every segment in a separate
# directory and Jan–Jun 2025 in its own jan_jun_2025 directory.
PYTHONPATH=src python3 -m vp_bot.run_btc_spot_donchian_daily_rearm \
  --minutes /path/to/recovered_m1.csv \
  --output-dir reports/reproduction_control_comparison
```

The corrected-control runner uses the preserved segment inventory at `reports/btc_spot_donchian_v1_recovery_segments/segment_inventory.csv`. Keep the pre-2025 continuous segment outputs and `jan_jun_2025` separate. Do not combine segment equity or use one segment's ending equity as the next segment's starting equity. The DAILY_REARM rows are a comparator, not BASE_20D results.

## Provenance and adaptations

The copied implementation/configuration and historical output files were not edited. Relative `data/...` names in original run configs are preserved as archival identifiers; no personal absolute paths are present in authored docs. Inputs and environment folders are excluded. The saved segment inventory is non-price metadata required by the corrected-control runner, not market data. See `STAGED_FILES.txt` for the exact path inventory and `SOURCE_SHA256.txt` for copied source/config hashes. Staging only copied saved results and documentation; it did not run backtests, modify metrics, or create orders.
