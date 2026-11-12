# Multi-asset TSMOM V1

## 1. Idea

This experiment tests the V0 momentum signal on a fixed basket of six FX pairs
and five ETFs using daily bars. ETFs use long signals only; FX can be long or
short.

## 2. What Was Fixed Before the Run

The results configuration records a 28-day return, a 365-day rank window, rank
threshold 0.6666666666666666, at least 200 valid rank observations, and a
7-calendar-day holding period. Round-trip costs were 0.0003 for FX and 0.0005
for ETFs. The fixed basket was EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF,
SPY, EFA, EEM, TLT, and GLD.

Placebo and bootstrap each used 10,000 draws with seed 12345. The placebo
minimum shift was 60 days; bootstrap used cyclic consecutive 8-week ISO blocks.
The decision matrix required at least 300 ON blocks. ABANDON applied for T at
or below zero, placebo p above 0.20, or fewer than five assets with positive T.
CONTINUE required placebo p at most 0.10, bootstrap p10 above zero, at least
seven assets with positive T, positive T after excluding each year, and
positive T after removing the best 5% of ON blocks.

## 3. Stages and Results

The V1 report records 31,643 executable ON blocks, pooled T 0.00007700,
positive T for seven of eleven assets, placebo p 0.46155384, bootstrap p10
-0.00027954, and T after removing the best 5% of ON blocks -0.00200692. The
recorded decision is **ABANDON**.

## 4. Why the Check Was Not Passed

The recorded placebo p is above the ABANDON threshold. The report also records
bootstrap p10 below zero and T below zero after removing the best 5% of ON
blocks.

## 5. Bugs Found and Fixed

The first V1 run produced undefined signals for all dates because `v1_signal.py`
treated the datetime index unit as nanoseconds when it was in microseconds. The
ledger marks that run `INVALID`; it was not used for a decision. The time-unit
bug was fixed before the recorded rerun. The initial V0 sell-price run is also
marked `INVALID` in the shared ledger.

## 6. Limitations

Yahoo quote OHLC does not include dividends or corporate actions, as stated in
the report. The data period is closed at 2025-07-01. Market data and
trade-block CSV files are not included.

## 7. Reproduction

V1 data were obtained with a one-off script from Yahoo Finance Chart API using
`period1=0` and `period2=1751320799`; no V1 downloader script is included.
The CSV SHA256 values are recorded in [config_v1.py](./config_v1.py). To
reproduce the run, obtain the same daily ticker data again, place the CSV files
under `data/v1/`, verify their SHA256 values against the configuration, install
dependencies, and run:

```text
python -m pip install -r requirements.txt
python run_v1.py
```

## 8. File List

- Configuration and runner: [config_v1.py](./config_v1.py), [run_v1.py](./run_v1.py)
- Code: [v1_data.py](./v1_data.py), [v1_signal.py](./v1_signal.py),
  [v1_blocks.py](./v1_blocks.py), [v1_metrics.py](./v1_metrics.py),
  [v1_reporting.py](./v1_reporting.py)
- Tests: [tests/test_v1.py](./tests/test_v1.py)
- Report and results: [report_v1.md](./report_v1.md), [results_v1.json](./results_v1.json)
- Rule: [.cursor/rules/v1-guardrails.mdc](./.cursor/rules/v1-guardrails.mdc)
- Dependencies: [requirements.txt](./requirements.txt)
- Shared records: [ledger.csv](../../ledger.csv), [data_notes.md](../../data_notes.md)

`blocks*.csv` and `data/` are not included because they contain market prices.
Reproduction requires obtaining market data again within the closed cutoff.
