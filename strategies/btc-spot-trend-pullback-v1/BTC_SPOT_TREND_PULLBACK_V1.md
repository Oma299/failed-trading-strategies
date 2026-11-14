# BTC SPOT TREND PULLBACK V1

This file is the implementation record for the first-stage research run of `BTC_SPOT_TREND_PULLBACK_V1`. The source project's original Word document is not included in this archive; this record preserves the implemented rules. No neighboring configurations, optimization, live orders, or July–December 2025 data are included.

## Fixed rules

- BTCUSDT Binance Spot, long-only, one position, no leverage, averaging, pyramiding, or take-profit.
- All timestamps are UTC. M1 is used for execution and stop checks; H1 supplies RSI/ATR and signals; H4 supplies the regime.
- H4 EMA100 starts with the SMA of the first 100 complete closes, then uses the recursive EMA with `alpha=2/101`. `G = close > EMA100 and EMA100 > EMA100[-6]`; both comparisons are strict.
- H1 RSI3 uses Wilder smoothing with the first three price changes. `0/0 -> 50`, gain-only `-> 100`, loss-only `-> 0`; no RSI rounding is used for comparisons.
- H1 ATR20 is the simple mean of the last 20 true ranges, including the completed signal H1. The first ATR is available at index 20.
- Trading requires 300 consecutive complete H4 bars, i.e. 50 complete days. The two H1 bars in the RSI crossing must be in the allowed portion.
- Entry at H1 close `T` requires `G(T-1)=True`, `G(T)=True`, previous RSI `<=20`, current RSI strictly between `20` and `60`, positive ATR, no position/order, and a previous H1 close strictly after the last exit.
- One buy attempt is made at the open of minute `T+1`. The only execution-minute field used for admission and sizing is that open. The previous 60 completed minutes supply the volume limit. `abs(open - signal_close) <= 0.5*ATR` is inclusive.
- Stop is `floor((signal_close - 2*ATR)/tickSize)*tickSize` and remains fixed. Exit priority is `STOP_GAP`, scheduled sale, `STOP`; scheduled causes are `REGIME_EXIT`, `RSI_EXIT`, and exact `TIME_EXIT` at 48 hours.
- RSI exit is scheduled one minute after an H1 close with RSI `>=60`; regime exit is scheduled one minute after an H4 close with `G=False`. The 48-hour exit sells on the open of the exact deadline minute.
- Buy commission is removed from received BTC; sell commission is removed from USDT proceeds. Dust remains in the ledger and is valued at zero. Decimal arithmetic is used for money, fills, quantities, and rounding.

## Scenarios

| Scenario | Fee each side | Full spread | Slippage each side |
|---|---:|---:|---:|
| ZERO | 0% | 0% | 0% |
| FEE_ONLY | 0.10% | 0% | 0% |
| BASE | 0.10% | 0.01% | 0.02% |
| ADVERSE | 0.10% | 0.02% | 0.05% |
| STRESS | 0.15% | 0.05% | 0.10% |

Half the full spread is applied per side. These are scenario assumptions, not reconstructed historical quotes or a claim about a particular account tariff.

## Data policy

The loader reads the recovered M1 dataset only while `open_time < 2025-07-01T00:00:00Z`. Missing minutes split the data into independent continuous segments. No minute is synthesized or interpolated. Each qualifying segment starts a separate 10,000 USDT account and receives its own 300-H4 warmup. A position at an unexpected segment boundary is `RIGHT_CENSORED`, receives terminal NAV valuation, and is excluded from ordinary PF and win rate.

Historical exchange filters are not available in the recovered dataset. The first run freezes the modelling snapshot `tickSize=0.01`, `stepSize=0.000001`, `minQty=0`, `minNotional=0`; this is explicitly an assumption, not historical Binance metadata.

## Intentionally deferred protocol stages

The first stage does not run the two tail stop-slippage scenarios, the two delayed-entry scenarios, the six one-at-a-time neighboring configurations, the 5,000-block bootstrap, or the closed July–December 2025 final period. Partial fills and live order behavior are documented as a separate execution contract and are not inferred from OHLCV.
