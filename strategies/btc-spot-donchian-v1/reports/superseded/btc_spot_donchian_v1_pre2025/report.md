# BTC_SPOT_DONCHIAN_V1 research run

Period: `2017-08-17T00:00:00` — `2025-01-01T00:00:00`. Existing December 2024 data is warmup only; July–December 2025 was not analyzed.

Data: `4131199` minutes, `2875` UTC days, missing minutes `8563`, incomplete days `48`.

## Scenarios

| Scenario | Trades | Signals | Win rate | Net PnL USDT | Return | PF | Max DD USDT | Time in market |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DIAGNOSTIC_ZERO | 1 | 2 | 1 | 1.68688653000000 | 0.14309932570000% |  | 2.13744124000000 | 0.5320226813206673368650529193163976460223 |
| BASE | 1 | 2 | 1 | 1.670337926654390041000000 | 0.142688542964563900410000% |  | 2.135303798760000000000000 | 0.5320226813206673368650529193163976460223 |
| STRESS | 1 | 2 | 1 | 1.662338994426063470000000 | 0.142544441050660634700000% |  | 2.135303798760000000000000 | 0.5320226813206673368650529193163976460223 |

R is defined as net trade PnL divided by the planned risk budget `0.5% × equity before entry`; this is not a guarantee of maximum loss. There is no TARGET exit in this strategy.

Exit reasons and monthly mark-to-market tables are available in the scenario CSVs and equity files. Results are descriptive and do not establish profitability.
