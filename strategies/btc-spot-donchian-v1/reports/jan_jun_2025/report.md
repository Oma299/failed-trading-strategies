# BTC_SPOT_DONCHIAN_V1 research run

Period: `2025-01-01T00:00:00` — `2025-07-01T00:00:00`. Existing December 2024 data is warmup only; July–December 2025 was not analyzed.

Data: `305280` minutes, `212` UTC days, missing minutes `0`, incomplete days `0`.

## Scenarios

| Scenario | Trades | Signals | Win rate | Net PnL USDT | Return | PF | Max DD USDT | Time in market |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DIAGNOSTIC_ZERO | 2 | 2 | 0.5 | 19.01078537000000 | 0.19010785370000% | 1.380241086819484418579208720433570570928 | 63.70689348000000 | 0.2971263044812768569674647022713321055862 |
| BASE | 2 | 2 | 0.5 | 15.290651447982994253000000 | 0.152906514479829942530000% | 1.305836982242587663208868973089720312530 | 62.826816917128613304 | 0.2971263044812768569674647022713321055862 |
| STRESS | 2 | 2 | 0.5 | 13.377103019502470770000000 | 0.133771030195024707700000% | 1.267550311167115700661266317932409584091 | 62.529433127040537600 | 0.2971263044812768569674647022713321055862 |

R is defined as net trade PnL divided by the planned risk budget `0.5% × equity before entry`; this is not a guarantee of maximum loss. There is no TARGET exit in this strategy.

Exit reasons and monthly mark-to-market tables are available in the scenario CSVs and equity files. Results are descriptive and do not establish profitability.
