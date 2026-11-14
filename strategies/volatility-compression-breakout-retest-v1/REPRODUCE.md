# Reproducing Volatility Compression Breakout Retest V1 artifacts

## Safe focused tests

Tests use small synthetic H1 and minute candles. They check Wilder ATR,
minimum stop distance, the two-R target, stop-first ambiguity, incomplete
data, and the no-lookahead history requirement. They do not read saved
historical data or launch the historical runner.

From this directory, with Python 3.9 or later:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

Only Python standard-library modules are required.

## Optional historical reproduction

Historical one-minute input is not included. Supply an authorized normalized
BTCUSDT Spot minute OHLCV CSV containing December 2024 prehistory and data
through June 2025. The runner validates and aggregates the minutes to H1,
then writes event records, trade records, a gallery, and aggregate metrics to
the requested output directory:

```sh
PYTHONPATH=src python -m vp_bot.run_volatility_compression_breakout_retest \
  --minutes path/to/authorized/btcusdt_1m_2024-12_2025-06.csv \
  --output-dir path/to/private-run-output \
  --start 2025-01-01T00:00:00 \
  --end 2025-07-01T00:00:00
```

The source's default date window and saved settings are in
`config/saved-run-config.json`. The output contains row-level historical
artifacts; those were intentionally excluded from this package and should not
be redistributed without a separate data and privacy review. Matching the
input normalization and completeness is required for exact reproduction.

## Staging-only adaptations and non-actions

Strategy logic was copied unchanged into the standalone `src/vp_bot` layout;
the original relative import of the shared `validation` helper is preserved.
The saved configuration references only a relative input path. No historical
input data or per-event/per-trade output was staged. The aggregate metrics
remain intact. Only focused synthetic unit tests were run; no backtest,
experiment, data download, or order was run or created during this work.
