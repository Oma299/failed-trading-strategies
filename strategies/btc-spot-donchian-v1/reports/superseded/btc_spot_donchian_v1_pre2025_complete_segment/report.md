# BTC_SPOT_DONCHIAN_V1 research run

Period: `2023-03-25T00:00:00` — `2025-01-01T00:00:00`. Existing December 2024 data is warmup only; July–December 2025 was not analyzed.

Data: `4131199` minutes, `2875` UTC days, missing minutes `8563`, incomplete days `48`.

## Scenarios

| Scenario | Trades | Signals | Win rate | Net PnL USDT | Return | PF | Max DD USDT | Time in market |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DIAGNOSTIC_ZERO | 9 | 9 | 0.4444444444444444444444444444444444444444 | 761.84021084000000 | 7.61840210840000% | 6.107665955829234289623130565462626578477 | 329.74782776000000 | 0.4911029663923182441700960219478737997257 |
| BASE | 9 | 9 | 0.4444444444444444444444444444444444444444 | 710.744300088037565515000000 | 7.107443000880375655150000% | 5.662085008623326257517327167452507259013 | 325.469682555682656820000000 | 0.4911029663923182441700960219478737997257 |
| STRESS | 9 | 9 | 0.4444444444444444444444444444444444444444 | 684.933050143715546080000000 | 6.849330501437155460800000% | 5.443767293519244781666666052960450722839 | 323.336084876324761040000000 | 0.4911029663923182441700960219478737997257 |

R is defined as net trade PnL divided by the planned risk budget `0.5% × equity before entry`; this is not a guarantee of maximum loss. There is no TARGET exit in this strategy.

Exit reasons and monthly mark-to-market tables are available in the scenario CSVs and equity files. Results are descriptive and do not establish profitability.
