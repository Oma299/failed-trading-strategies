# Multi-asset TSMOM V1

## Idea and pre-run rules

Test the V0 momentum signal on a fixed basket of six FX pairs and five ETFs,
using daily data. Compute the 28-day return, rank against the preceding
365-day history, and require rank at least 2/3. ETFs are long-only; FX permits
long and short signals. Blocks enter at the open and exit 7 calendar days
later. The recorded round-trip costs are 0.0003 for FX and 0.0005 for ETFs.

The pre-run decision thresholds recorded in the results configuration were:
insufficient data below 300 ON blocks; ABANDON for T at or below zero, placebo
p above 0.20, or fewer than five assets with positive T; CONTINUE requires
placebo p at most 0.10, bootstrap p10 above zero, at least seven assets with
positive T, positive T after excluding each year, and positive T after removing
the best 5% of ON blocks. Placebo and bootstrap use 10,000 draws; bootstrap
resamples cyclic consecutive 8-week ISO blocks.

## Data source and recorded results

The V1 data were downloaded with a one-off script from Yahoo Finance Chart API
using `period1=0` and `period2=1751320799`; no V1 downloader script is included.
The CSV SHA256 values are recorded in [config_v1.py](./config_v1.py).

The report records 31,643 executable ON blocks, pooled T 0.00007700, placebo
p 0.46155384, bootstrap p10 -0.00027954, and T after removing the best 5%
-0.00200692. The recorded decision is **ABANDON**.

## Bug history

The first V1 run produced undefined signals for all dates because of a time-unit
bug in `v1_signal.py`. That run is marked `INVALID` in the ledger and was not
used for a decision. The time-unit bug was fixed before the recorded rerun.

`blocks*.csv` and `data/` are not included because they contain market prices.
Results can be reproduced by running the code with market data downloaded
again, within the closed cutoff. The shared [ledger](../ledger.csv) and
[data notes](../data_notes.md) are in the archive root.
