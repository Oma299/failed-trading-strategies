# Volatility Compression Breakout Retest V1 — BTCUSDT Spot research package

This standalone package preserves a fixed H1 volatility-compression,
breakout-and-retest research model and its saved January–June 2025 results. It
is a historical research artifact, not a recommendation, production system,
or claim of profitability.

## Strategy definition

All decision candles are completed UTC H1 candles. At each candidate hour the
model forms a range from the latest 12 closed hours and compares that range's
width (as a percentage of the latest close) with the nearest-rank
`ceil(0.20 × 720)` threshold from the preceding 720 valid 12-hour widths. A
width equal to the threshold qualifies. There are no future candles in the
compression comparison.

After a qualifying compression, the 12-hour upper and lower boundaries are
frozen. A close must break either boundary by at least `0.1 × ATR(14)`,
calculated using Wilder's method and fixed at the breakout. A breakout may
occur within the next six H1 candles. The first valid retest is sought within
the next three H1 candles: LONG requires `low <= upper` and `close > upper`;
SHORT is mirrored at the lower boundary. A close on the wrong side cancels
the episode.

Entry is the next hour's open with 0.02% adverse slippage. Stop is the retest
candle's low/high offset by 0.1 ATR from the breakout. An entry is skipped if
stop distance is less than 0.5 ATR; equality is permitted. The target is
exactly 2R from the actual entry fill. Exits are checked on one-minute OHLCV
from the entry minute onward, with stop-first handling when both levels are
touched in one minute. Holding is limited to 12 hours. Missing future data is
reported as `DATA_INCOMPLETE`, not treated as an ordinary time exit.

Only one position and one attempt per range are allowed; new ranges do not
accumulate while a range or position is active. Commission is 0%. SHORT is a
hypothetical price model on Spot data: there is no borrowing, funding, or
short-account model. The saved window is January 1 through July 1, 2025 UTC,
with December 2024 history. It is not an independent final test.

## Event study versus executed-trade test

`detect()` in `src/vp_bot/volatility_compression_breakout_retest.py` creates
the compression, breakout, retest, and signal-event records and calls the
minute-level execution model for signaled entries. Its `episodes` and `trades`
outputs are separate. The published 39-trade metrics are from the execution
records, not from counting all candidate events as trades. The model is a
per-trade price simulation, not a portfolio or account-equity backtest.

Exact saved aggregate results are in
[`reports/SAVED_RESULTS.md`](reports/SAVED_RESULTS.md) and
[`reports/saved-aggregate-metrics.json`](reports/saved-aggregate-metrics.json).

## Package contents

- `src/vp_bot/`: original strategy model, its hourly validation/aggregation
  helper, and the historical runner.
- `tests/`: focused synthetic unit tests; they do not access historical data
  or launch the experiment.
- `config/`: saved run settings and data-quality summary, with only relative
  dataset references.
- `reports/`: aggregate metrics and sanitized narrative only.
- [`REPRODUCE.md`](REPRODUCE.md): test and optional manual reproduction
  instructions.

## Artifact status and staging-only adaptations

The saved `metrics.json` and `run_config.json` from
`reports/volatility_compression_breakout_retest_v1` are the canonical
on-disk aggregate results and settings included here. No alternate periods or
strategy variants are merged. The source and test files were copied into a
standalone `src/vp_bot` package without changing their logic. Input OHLCV and
per-event/per-trade CSVs, galleries, HTML, and SVGs were excluded; only
aggregate metrics and non-row-level data-quality metadata were retained.
There are no machine-specific absolute paths. No historical backtest,
experiment, download, or order submission was performed while staging.
