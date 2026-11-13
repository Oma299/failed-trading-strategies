# BTC Spot TSMOM V0

## 1. Idea

This experiment tests whether BTCUSDT momentum can identify favorable spot
entries. Stage 1 evaluates the entry signal only; Stage 2 applies the specified
execution and stop rules.

## 2. What Was Fixed Before the Runs

Stage 1 settings recorded in `results.json`: 28-day return, 365-day rank window,
rank threshold 0.6666666666666666, 7-day holding period, 1000 USDT notional, and
0.001 fee. BASE execution used spread 0.0001, slippage 0.0002, and 1-minute
delay; STRESS used spread 0.0002, slippage 0.0005, and 10-minute delay.
Placebo and bootstrap each used 10,000 draws; the placebo minimum shift was
60 days, bootstrap blocks were 8 ISO weeks, and the seed was 12345.

Stage 2 settings recorded in `results_stage2.json` included initial equity
10000 USDT, risk fraction 0.005, lot size 0.00001 BTC, minimum notional
10 USDT, ATR period 14 days, ATR multiplier 2.0, 15 required full D1 days,
maximum holding period 56 days, and seven weekday portfolios.

The Stage 2 decision thresholds recorded before the run were: BASE profit
factor at least 1.25; STRESS profit factor at least 1.10; bootstrap net-R p10
above zero; at least five phases with profit factor above one; profit factor
without the best three trades above one; largest annual profit share no more
than 0.50; placebo p no more than 0.10; and at least 100 trades.

## 3. Stages and Results

The Stage 1 report describes an entry diagnostic without stops, not a strategy
result. It records 4,131,199 input rows over 2017-08-17 through 2025-06-30.

The Stage 2 report records 60 BASE trades and 60 STRESS trades. BASE profit
factor was 2.518460 and STRESS profit factor was 2.517033. BASE bootstrap net-R
p10 was -0.000296, annual profit concentration was 0.687666, and placebo p was
0.397360.

## 4. Why the Check Was Not Passed

The Stage 2 §5 table marks bootstrap net-R p10, annual profit concentration,
placebo p, and minimum trades as not met. The project notes record that the V0
family was closed. The PDF did not define an overall Stage 2 tri-state verdict.

## 5. Bugs Found and Fixed

The initial V0 run used the entry open as the sell price instead of the exit
open. The ledger marks that run `INVALID`; it was not used for a decision. The
sell-price bug was fixed before the corrected Stage 1 run.

## 6. Limitations

Stage 1 is an entry diagnostic without stops. The Stage 2 PDF specification
does not define a general tri-state decision. The cutoff is 2025-07-01; data
at or after that date are outside the experiment. Market data and trade-block
CSV files are not included in this archive.

## 7. Reproduction

Install dependencies, then run the BTCUSDT spot 1-minute data downloader for
the recorded closed period:

```text
python -m pip install -r requirements.txt
python scripts/download_data.py
python run_stage1.py
python run_stage2.py
```

The downloader uses Binance Vision. The data are not bundled; the scripts
recreate the research Parquet from newly downloaded market data.

## 8. File List

- Configuration: [config.py](./config.py), [config_stage2.py](./config_stage2.py)
- Stage 1: [data.py](./data.py), [signals.py](./signals.py), [blocks.py](./blocks.py),
  [decision.py](./decision.py), [robustness.py](./robustness.py),
  [reporting.py](./reporting.py), [resampling.py](./resampling.py),
  [run_stage1.py](./run_stage1.py)
- Stage 2: [stage2_data.py](./stage2_data.py), [stage2_signal.py](./stage2_signal.py),
  [stage2_engine.py](./stage2_engine.py), [stage2_metrics.py](./stage2_metrics.py),
  [stage2_reporting.py](./stage2_reporting.py), [run_stage2.py](./run_stage2.py)
- Data downloader: [scripts/download_data.py](./scripts/download_data.py)
- Tests: [tests/test_pipeline.py](./tests/test_pipeline.py),
  [tests/test_stage2.py](./tests/test_stage2.py)
- Reports and results: [report.md](./report.md), [results.json](./results.json),
  [report_stage2.md](./report_stage2.md), [results_stage2.json](./results_stage2.json)
- Rules: [.cursor/rules/stage1-guardrails.mdc](./.cursor/rules/stage1-guardrails.mdc),
  [.cursor/rules/stage2-guardrails.mdc](./.cursor/rules/stage2-guardrails.mdc)
- Dependencies: [requirements.txt](./requirements.txt)
- Shared records: [ledger.csv](../../ledger.csv), [data_notes.md](../../data_notes.md)

`blocks*.csv` and `data/` are not included because they contain market prices.
Reproduction requires downloading the data again within the closed cutoff.

Reference: [lessons](../../docs/LESSONS.md), [glossary](../../docs/GLOSSARY.md),
and [timeline](../../docs/TIMELINE.md).
