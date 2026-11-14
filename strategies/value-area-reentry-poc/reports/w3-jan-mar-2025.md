# Value Area Re-entry → POC Mean Reversion: W3 result

## Saved run and provenance

This report isolates the saved three-following-candle baseline from the
project's comparison of return-window variants. Evaluation interval:
`[2025-01-01 00:00 UTC, 2025-04-01 00:00 UTC)`.
The archived configuration used a 3-following-hourly-candle return window,
prior-UTC-day Binance Spot aggTrades profiles, and the V1 simulation settings.
Its `config_fingerprint` is
`ac0f1af83619bef3a1f0a49cabd15c042aaefdaef7852ddc96d4daa221ebeb75`.

The values below are copied from the saved W3 `metrics.json` and the
corresponding W3 paragraph/table in `window_comparison_jan_mar.md`; they were
not recalculated for this publication copy. The source `run_config.json` and
`metrics.json` are preserved as
[`../configs/w3-2025-01-01_to_2025-03-31.run-config.json`](../configs/w3-2025-01-01_to_2025-03-31.run-config.json)
and
[`../results/w3-2025-01-01_to_2025-03-31.metrics.json`](../results/w3-2025-01-01_to_2025-03-31.metrics.json).
Source artifact SHA-256 values: W3 `metrics.json`,
`a70acddbc85b73f3db9f5fb8f785c2ac786f7c732069481b75fa1816ffc2c6ca`; W3
`run_config.json`,
`6c4b9435169525a8dab18efde0288e7ed4a2c996b907ab07dce04cee7d7ba0fc`; source
`window_comparison_jan_mar.md`,
`d4edcd91809a6b093828d12ac7e47a6abcfcbcd900330e4d3ea6305f13b6d944`.

## Reported result

- Evaluation: 55 episodes; 19 candidates, entries, and completed trades; 0
  skipped entries; `incomplete=false`.
- Initial capital: `1000 USDT`.
- Final capital: `973.0557327704699308883633898583548247132 USDT`.
- Net PnL: `-26.94426722953006911163661014164517528781 USDT`
  (`-2.694426722953006911163661014164517528781%`).
- Average trade net: `-1.418119327870003637454558428507640804622 USDT`.
- Average net R: `-0.3340195261913008643399810234696067395383`.
- Net win rate: `52.63157894736842105263157894736842105263%`
  (10 wins, 9 losses, 0 zero-result trades).
- Profit factor: `0.4692035792913826768673720771906043582139`.
- Maximum drawdown: `43.1114818376241634985987315260785867108 USDT`
  (`4.242557840665130908126607628888990977518%`), measured on minute-close
  equity.
- Exit reasons: `INITIAL_STOP=8`; `TARGET=11`.
- Commissions: `27.94294760623356596591218756284055682104 USDT`.
- Modeled slippage cost: `5.588589784737519650823097716515116872624 USDT`.

The saved report records that the W3 baseline-control integration check matched
the previous continuous V1 baseline: 55 events, 19 confirmations/trades, the
same net PnL, and matching per-trade net PnL.

## Execution assumptions and limits

The saved comparison describes 1,000 USDT starting capital, Wilder ATR(14),
initial stop at episode low minus `0.25 × ATR`, D-1 POC target, `0.5%` equity
risk, `0.1%` commission and `0.02%` slippage per side, and a 24-hour holding
limit. Profit lock was disabled. The run did not model exchange
`minNotional`/`stepSize`, the order book, latency, or partial fills. OHLCV
cannot determine intraminute ordering; stop-first handling was used when both
levels were touched. Maximum drawdown is based on minute-close equity, not the
maximum intraminute drawdown.

The source report describes January–March as development data and explicitly
does not treat the result as evidence of sustained or future profitability.
The saved W3 artifacts do not define a formal pass/fail decision matrix, so this
report assigns none.
