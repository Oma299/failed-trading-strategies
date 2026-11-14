# Reproducing Range Reversal artifacts

## Safe focused tests

The packaged tests use synthetic fixtures and exercise the detector,
annotation, execution mechanics, and local-day completeness checks. They do
not load saved historical data or invoke the historical validation runner.
From this directory, with Python 3.9 or later:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Only Python standard-library modules are required.

## Optional historical reproduction

Historical input data is intentionally not bundled. To reproduce the saved
April–June 2025 corrected validation, provide an authorized normalized
one-minute BTCUSDT Spot OHLCV CSV covering the required March prehistory and
the complete local days in the test window. The source runner accepts the
dataset and output directory explicitly:

```sh
PYTHONPATH=src python -m vp_bot.run_range_reversal_apr_jun_validation \
  --minutes path/to/authorized/btcusdt_1m_2025-03_2025-06.csv \
  --output-dir path/to/private-run-output \
  --start-day 2025-04-01 \
  --end-day 2025-06-30
```

The runner writes event-level, trade-level, and gallery outputs to the chosen
output directory. Those outputs are intentionally absent from this package;
do not treat them as publication-ready without sanitizing them. The saved
aggregate report in `reports/` is the authoritative evidence staged here.
Dataset normalization, completeness, and exact input version must match the
saved run to expect identical results.

## Research layers and incompatible conventions

- For signal events only, use `vp_bot.range_reversal_v2.detect_v2` with
  `confirmation_mode="N3"`. This does not execute trades.
- For delayed-entry annotations, use `vp_bot.range_reversal_delayed.annotate`.
  The corrected annotation’s target is fixed from E1, not E3.
- The corrected validation runner then invokes per-trade execution with
  `target_mode="E3_2R"` and 0% commission. Do not mix its results with the
  E1-fixed annotation convention, V1, N1, other periods, or superseded runs.
- The saved filtered outcomes include only baseline-eligible annotations
  passing the preregistered width and delay criteria. Excluded shadow outcomes
  are descriptive only and do not create replacement signals.

## Staging-only adaptations and non-actions

Only package files were created in this staging directory. Strategy source
and tests are direct copies; package layout is `src/vp_bot` so the original
relative imports continue to work. Historical inputs and per-event/per-trade
outputs were deliberately omitted. The run configurations use relative paths
and contain no personal absolute paths. Only synthetic tests were run for
validation; no historical backtest, experiment, download, or order was run or
created during staging.
