# BTC Spot Value Area Re-entry → POC Mean Reversion

## 1. Idea

This is a historical, long-only BTCUSDT Spot strategy. It looks for a completed
hourly close below the prior UTC day's Value Area Low (VAL), then waits up to
three following completed hourly candles for a close back inside the strict
interval `(VAL, POC)`. A confirmed return schedules a simulated long entry at
the next minute open. The prior-day Point of Control (POC) is the target.

The detector emits events; it does not place orders or manage a live position.
`backtest.py` applies the saved V1 execution model to those events. This package
is separate from every later volume-profile strategy family.

## 2. What Was Fixed Before the Run

The archived W3 run used the three-following-hourly-candle return window and
the following saved V1 settings:

- Profile: previous complete UTC day, built from Binance Spot aggTrades; 100
  equal-price bins and a 70% Value Area. The source method assigns each trade's
  quantity to the bin containing its exact trade price.
- Signal: the first valid H1 close strictly below the available D-1 VAL starts
  an episode. Only the next three valid, continuous H1 candles can confirm;
  confirmation requires `VAL < close < POC`. The initial breach candle is not
  part of the return window.
- Stop and target: episode low minus `0.25 × ATR(14)` using Wilder ATR; target
  is D-1 POC.
- Simulation: 1,000 USDT initial capital; 0.5% equity risk sizing; 0.1%
  commission per side; 0.02% modeled slippage per side; maximum holding time
  24 hours; one position at a time; stop-first handling when both stop and
  target are touched in the same minute.
- Profit lock was disabled. The optional POC-protection branch was not enabled
  in this W3 run.

The immutable run record is
[`configs/w3-2025-01-01_to_2025-03-31.run-config.json`](./configs/w3-2025-01-01_to_2025-03-31.run-config.json).
Its fingerprint is
`ac0f1af83619bef3a1f0a49cabd15c042aaefdaef7852ddc96d4daa221ebeb75`.
The original relative input paths are retained there for provenance; those
market-data files are not included.

## 3. Stages and Results

The selected saved result is the W3 baseline over
`[2025-01-01 00:00 UTC, 2025-04-01 00:00 UTC)`. The preserved artifact records
55 episodes and 19 confirmed entries/trades. It reports:

- Net PnL: `-26.94426722953006911163661014164517528781 USDT`
- Ending capital: `973.0557327704699308883633898583548247132 USDT`
- Average trade net: `-1.418119327870003637454558428507640804622 USDT`
- Average net R: `-0.3340195261913008643399810234696067395383`
- Net win rate: `52.63157894736842105263157894736842105263%`
- Profit factor: `0.4692035792913826768673720771906043582139`
- Maximum drawdown on minute-close equity: `43.1114818376241634985987315260785867108 USDT`
- Exit reasons: 8 `INITIAL_STOP`, 11 `TARGET`
- Commission: `27.94294760623356596591218756284055682104 USDT`
- Modeled slippage cost: `5.588589784737519650823097716515116872624 USDT`
- Incomplete run: `false`

These are quoted from the saved W3 metrics, not recalculated here. The exact
machine-readable artifact is
[`results/w3-2025-01-01_to_2025-03-31.metrics.json`](./results/w3-2025-01-01_to_2025-03-31.metrics.json).
The sanitized narrative report and provenance are in
[`reports/w3-jan-mar-2025.md`](./reports/w3-jan-mar-2025.md).

## 4. Why the Check Was Not Passed

The saved W3 comparison report does not define a formal pass/fail decision
matrix for this strategy. It does report negative net PnL and negative average
net R for the selected run. This package records those observations without
assigning an unsupported formal verdict or inferring future performance.

## 5. Bugs Found and Fixed

The W3 comparison identifies its baseline-control check as matching the
previously saved continuous V1 baseline: 55 events, 19 confirmations/trades,
matching net PnL and matching per-trade net PnL. It does not record a W3-specific
strategy-logic defect.

## 6. Limitations

- The evaluated interval is one historical quarter and contains 19 trades.
- The W3 maximum drawdown uses minute-close equity, not intraminute equity.
- OHLCV cannot reveal the order of intraminute price moves. The simulator applies
  the stop first when both levels are touched and records ambiguity.
- The model does not include exchange `minNotional` or `stepSize`, order-book
  depth, latency, or partial fills. Fees and slippage are fixed model inputs.
- The saved configuration names hourly/minute OHLCV inputs but does not
  reproduce their full source manifest here. The original processed files and
  all raw market data are deliberately absent.
- This is a historical simulation, not financial advice, an execution
  guarantee, or authorization to trade.

The package excludes Stage 1 research, Experiment 9R/10A, later 21-day POC/VA
research, active HVN work, raw market data, and unrelated strategies.

## 7. Reproduction

Reproduction requires the matching BTCUSDT Spot hourly/minute OHLCV inputs and
daily Binance Spot aggTrades archives. No market data is bundled. Obtain data
only if you independently choose to reproduce the saved run; verify the
published checksum sidecars and follow the input requirements in
[`REPRODUCE.md`](./REPRODUCE.md). No historical run was launched while
preparing this package.

The strategy code uses only the Python standard library. The synthetic unit
tests do not download data or invoke the historical backtest.

## 8. File List

- Signal, ATR, simulation, and CLI:
  [`src/vp_bot/__init__.py`](./src/vp_bot/__init__.py),
  [`src/vp_bot/signals.py`](./src/vp_bot/signals.py),
  [`src/vp_bot/atr.py`](./src/vp_bot/atr.py),
  [`src/vp_bot/backtest.py`](./src/vp_bot/backtest.py),
  [`src/vp_bot/run_backtest.py`](./src/vp_bot/run_backtest.py)
- Local aggTrades profile validation/calculation and profile-input builder:
  [`src/vp_bot/aggtrades.py`](./src/vp_bot/aggtrades.py),
  [`src/vp_bot/build_aggtrades_profiles.py`](./src/vp_bot/build_aggtrades_profiles.py)
- Configurations:
  [`configs/w3-2025-01-01_to_2025-03-31.run-config.json`](./configs/w3-2025-01-01_to_2025-03-31.run-config.json),
  [`configs/profile_recipe.json`](./configs/profile_recipe.json)
- Synthetic unit tests:
  [`tests/test_signals.py`](./tests/test_signals.py),
  [`tests/test_backtest.py`](./tests/test_backtest.py),
  [`tests/test_aggtrade_profiles.py`](./tests/test_aggtrade_profiles.py)
- Saved result and report:
  [`results/w3-2025-01-01_to_2025-03-31.metrics.json`](./results/w3-2025-01-01_to_2025-03-31.metrics.json),
  [`reports/w3-jan-mar-2025.md`](./reports/w3-jan-mar-2025.md)

### Packaging adaptations

- `signals.py`, `atr.py`, `backtest.py`, and `run_backtest.py` retain the
  historical strategy logic and package-relative imports.
- `aggtrades.py` retains local archive parsing, checksum verification, quality
  checks, and exact-price profile calculation. Network/download functions and
  their storage-budget helpers were removed: `StorageBudgetExceeded`,
  `DownloadInfo`, `storage_usage_bytes`, `budget_allows_download`,
  `head_content_length`, `_download_stream`, and `ensure_archive`. The added
  profile-builder module reads only user-supplied archives, requires clean
  timestamp/ID quality counters, and performs no network access.
- The package initializer's description was changed to identify this legacy
  strategy. The source `test_stage3.py` was copied as `test_signals.py` and its
  test class renamed. Parameter-variant assertions were narrowed to the
  archived three-candle setting; other signal assertions are unchanged.
- The source backtest test that writes an event-journal file under a temporary
  directory was omitted. Other copied tests are synthetic and in-memory. The
  position-blocker test was narrowed to the three-candle setting, and a
  synthetic profile test was added for the archived aggTrades calculation.
- The W3 run configuration and metrics JSON are byte-for-byte copies of the
  saved artifacts. The narrative report reproduces W3 only from the saved
  metrics/report; it omits other comparison variants and does not recalculate
  metrics.

Archive references: [methodology](../../METHODOLOGY.md),
[lessons](../../docs/LESSONS.md), [glossary](../../docs/GLOSSARY.md), and
[timeline](../../docs/TIMELINE.md).
