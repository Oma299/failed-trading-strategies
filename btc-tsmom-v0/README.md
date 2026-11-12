# BTC Spot TSMOM V0

## Idea and pre-run rules

Test a BTCUSDT spot time-series-momentum signal. Stage 1 is an entry diagnostic,
not a strategy result. The signal uses a 28-day return and a 365-day rank window;
an entry signal requires positive momentum and rank at least 2/3. The planned
holding period is 7 days. Stage 2 evaluates separate weekday portfolios under
BASE and STRESS execution assumptions, with stop-based exits.

The Stage 2 decision thresholds recorded before the run were: BASE profit factor
at least 1.25; STRESS profit factor at least 1.10; bootstrap net-R 10th
percentile above zero; at least five phases with profit factor above one; profit
factor without the best three trades above one; largest annual profit share no
more than 0.50; placebo p no more than 0.10; and at least 100 trades.

## Recorded results

Stage 1 is explicitly described in its report as an entry diagnostic without
stops, not a strategy result. The Stage 2 report records 60 trades, BASE profit
factor 2.518460, STRESS profit factor 2.517033, bootstrap net-R p10 -0.000296,
annual profit concentration 0.687666, and placebo p 0.397360. The report's
§5 table marks the bootstrap, annual concentration, placebo, and minimum-trade
criteria as not met. The V0 family was closed; no overall Stage 2 tri-state
decision was defined.

## Bug history

The initial V0 run used the entry open as the sell price instead of the exit
open. That run is marked `INVALID` in the ledger and was not used for a
decision. The sell-price bug was fixed before the corrected Stage 1 run.

`blocks*.csv` and `data/` are not included because they contain market prices.
Results can be reproduced by running the code with data downloaded again,
within the closed cutoff. The shared [ledger](../ledger.csv) and
[data notes](../data_notes.md) are in the archive root.
