# Reproduction guide — Trend Pullback V1

## What can be reproduced without market data

The focused unit tests use small synthetic bars built in memory; they do not load a historical dataset, run the historical experiment, access a network, or create orders.

From this package root, with Python 3.9 or later:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_btc_spot_trend_pullback_v1.py' -v
```

The implementation and runner use only the Python standard library. No package installation is required.

## Historical runner (not executed for staging)

The canonical Markdown report and compact aggregate metrics are saved under `reports/first-stage/`; row-level trade/event/equity files and generated plots are intentionally excluded from this overlay. This task did **not** rerun the experiment or backtest. The original input market data is not distributed here. If a separate authorized reproduction is later desired, provide the exact recovered M1 input and run:

```sh
PYTHONPATH=src python3 -m vp_bot.run_btc_spot_trend_pullback_v1 \
  --minutes /path/to/compatible_recovered_m1.csv \
  --output-dir reports/reproduction
```

The runner keeps the historical exclusive cutoff at `2025-07-01T00:00:00Z`; use the exact historical input identified by the saved configuration, not later data or synthetic gap fills. Preserve continuous-segment boundaries. Do not concatenate segment equity or interpret the output as cross-segment compounded performance.

## Provenance and adaptations

The copied module and runner SHA-256 values are recorded in `SOURCE_SHA256.txt`. The saved configuration and saved result files are byte-preserving copies. Only directory placement and this publication documentation are new. No machine-specific absolute path was carried into the docs/config; the original relative input filename remains as provenance. No metrics were rounded, changed, or generated during staging.
