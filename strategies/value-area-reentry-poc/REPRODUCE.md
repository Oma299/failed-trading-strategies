# Reproduction

This procedure describes how a reader could independently recreate the
historical W3 result. It was not run during package preparation. The archive
contains code, configs, tests, and sanitized results only; it does not contain
market data, download archives, or generated profile CSVs.

## Saved run identity

- Strategy interval: `[2025-01-01T00:00:00Z, 2025-04-01T00:00:00Z)`
- Signal timeframe: completed 1-hour candles
- Execution data: 1-minute OHLCV
- Profile input: prior UTC day, Binance Spot aggTrades
- Return wait: 3 following hourly candles
- Configuration fingerprint: `ac0f1af83619bef3a1f0a49cabd15c042aaefdaef7852ddc96d4daa221ebeb75`
- Saved metrics: [`results/w3-2025-01-01_to_2025-03-31.metrics.json`](./results/w3-2025-01-01_to_2025-03-31.metrics.json)

The fingerprint is the saved run's `config_fingerprint`; it is not a checksum of
the market data. The matching original relative input names and simulation
settings are in [`configs/w3-2025-01-01_to_2025-03-31.run-config.json`](./configs/w3-2025-01-01_to_2025-03-31.run-config.json).

## 1. Obtain the required inputs separately

Use the official [Binance public data portal](https://data.binance.vision/)
for BTCUSDT Spot daily aggTrades archives and their `.CHECKSUM` sidecars.
For D-1 profiles over the W3 signal interval, the required profile days are
2024-12-31 through 2025-03-30 inclusive. Put the matching files in
`data/raw/aggtrades/` using Binance's daily archive names, for example
`BTCUSDT-aggTrades-2024-12-31.zip` and its
`BTCUSDT-aggTrades-2024-12-31.zip.CHECKSUM` sidecar.

Obtain the hourly and minute BTCUSDT OHLCV data for the same dates and the
preceding period needed to warm up ATR(14). The saved run referenced
`data/processed/btcusdt_1h_2024-12_2025-03.csv` and
`data/processed/btcusdt_1m_2024-12_2025-03.csv`; those source files are not
included. The archived W3 config does not retain a complete OHLCV provenance
manifest, so use source-verified files and preserve their own checksums if
reconstructing.

Expected input columns:

- 1-minute rows: `open_time`, `open`, `high`, `low`, `close`.
- 1-hour rows: `open_time`, `close_time`, `open`, `high`, `low`, `close`, and
  `complete_60_distinct_minutes` where available. Rows must be UTC, chronological,
  complete, and OHLC-valid.
- Daily aggTrades: Binance's eight-field Spot aggTrades CSV format inside each
  daily ZIP, with a matching checksum sidecar.

Do not use the approximate OHLCV-distributed profile as a substitute for the
aggTrades profile in this historical run.

## 2. Build the D-1 profile input

From this package root, run:

```text
PYTHONPATH=src python -m vp_bot.build_aggtrades_profiles \
  --archive-dir data/raw/aggtrades \
  --output data/processed/aggtrades_jan_mar_combined/daily_profiles.csv \
  --start-day 2024-12-31 \
  --end-day 2025-03-30 \
  --bins 100
```

The builder is offline: it reads only the archive/checksum files already
present, verifies each SHA-256 sidecar, validates timestamps and trade IDs, and
writes one daily profile row. It does not download archives. The profile uses
exact trade prices, 100 equal-price bins, a 70% Value Area, and the saved
`binance_spot_aggtrades` / `aggtrades` labels.

## 3. Run the historical W3 simulation

After arranging the hourly/minute input files under the relative names recorded
in the run config (or adjusting only those CLI input paths), run:

```text
PYTHONPATH=src python -m vp_bot.run_backtest \
  --hours data/processed/btcusdt_1h_2024-12_2025-03.csv \
  --minutes data/processed/btcusdt_1m_2024-12_2025-03.csv \
  --profiles data/processed/aggtrades_jan_mar_combined/daily_profiles.csv \
  --output-dir reports/reproduced-w3 \
  --start-day 2025-01-01 \
  --end-day 2025-03-31 \
  --max-return-bars 3 \
  --profit-lock baseline
```

Compare the generated metrics with the saved W3 result. A mismatch should first
be investigated as an input/provenance difference; do not silently overwrite
the archived metrics or label a non-matching run as a reproduction.

## Unit tests

From the package root:

```text
PYTHONPATH=src python -m unittest discover -s tests -v
```

The tests use synthetic candles, event data, and mocked archive metadata. They
do not download files or invoke a historical backtest. The event-journal
filesystem-output test from the source project is omitted from this package
copy so this test suite remains free of temporary-directory writes.
