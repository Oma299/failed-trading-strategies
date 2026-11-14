# Failed Trading Strategies Archive

This repository is a quantitative research archive of historical trading
systems, validation attempts, and their limitations. It preserves evidence,
including negative and inconclusive results; it is not a strategy marketplace.

> **Research disclaimer:** This material is for research and educational use
> only, not financial advice or a recommendation to trade. Historical results
> do not establish future performance. No archive package authorizes live
> trading. Spot short-side signals are analytical and do not imply that
> short-selling is available on Binance Spot.

## Strategies

| Strategy | Market | Type | Historical period / sample | Trades (or events) | Win rate | Net result / PF | Evidence status |
|---|---|---|---|---:|---|---|---|
| [BTC Spot TSMOM V0](./strategies/btc-tsmom-v0/) | BTCUSDT Spot | Trend-following | Data 2017-08-17–2025-06-30; Stage 2 from 2022-10-29 | 60 trades in Stage 2 | N/A | N/A | V0 family closed; Stage 2 criteria not met |
| [Multi-asset TSMOM V1](./strategies/multi-asset-tsmom-v1/) | 6 FX pairs + 5 ETFs | Multi-asset momentum | 1993-01-29–2025-06-30 data range | N/A | N/A | N/A | ABANDON |
| [Value Area Re-entry → POC](./strategies/value-area-reentry-poc/) | BTCUSDT Spot | Long-only mean reversion | 2025 Q1 saved window | 19 trades in W3 | 52.63% in W3 | W3 net PnL -26.94426722953006911163661014164517528781 USDT; PF 0.4692035792913826768673720771906043582139 | Limited historical evidence |
| [BTC Spot Trend Pullback V1](./strategies/btc-spot-trend-pullback-v1/) | BTCUSDT Spot | Long-only trend pullback | 2017-08-17–2025-06-30, segmented | 847 completed BASE trades | N/A | BASE mean trade R: -0.11738 | Not validated after costs |
| [BTC Spot Donchian V1](./strategies/btc-spot-donchian-v1/) | BTCUSDT Spot | Long-only breakout | Jan–Jun 2025; separate corrected segment Mar 2023–Dec 2024 | 2; 9 in the cited separate segment | 50% in Jan–Jun 2025 | BASE net PnL +15.29065 USDT / PF 1.3058 in Jan–Jun 2025; separate segment +710.7443 USDT | Inconclusive; small samples |
| [Range Reversal](./strategies/range-reversal/) | BTCUSDT Spot price study | Reversal / false-breakout variants | Apr–Jun 2025 corrected validation | 68 trades | 25% | Mean net R -0.350353 / PF 0.551717 | Negative saved execution sample; variants are not one portfolio |
| [Volatility Compression Breakout Retest V1](./strategies/volatility-compression-breakout-retest-v1/) | BTCUSDT Spot | Breakout/retest | Jan–Jun 2025 | 39 trades | 20.51% | Mean R -0.4770365 / PF 0.3639245 | Negative saved sample; not proof of universal failure |

`N/A` means the metric was not reported in the cited run. Rows use different
periods, trade models, and reporting conventions; they are descriptive and
must not be ranked as if they were one comparable portfolio. Range Reversal
signal counts are explicitly separated from executed simulated trades; its
other delayed-entry and stop variants are not pooled with the cited 68-trade
validation.

## Conclusions at a glance

- The saved BASE Trend Pullback and Compression Breakout samples are negative
  after their recorded costs.
- The Value Area strategy's saved W3 aggregate is negative; its report treats
  Q1 as development data, not evidence of sustained or future profitability.
- Donchian's reported positive segments have very few trades and do not
  establish robust performance. Corrected and superseded results are kept
  distinct.
- Range Reversal includes event-detection studies and separate execution
  experiments; its event counts are not trade counts.
- These conclusions are bounded by each report's sample, assumptions, and
  evaluation design.

The existing archive's TSMOM evidence is retained in this proposed summary:
BTC Spot TSMOM V0 Stage 2 reported bootstrap p10 `-0.000296`, annual profit
concentration `0.687666`, placebo p `0.397360`, and 60 trades against a
100-trade minimum; Multi-asset TSMOM V1 reported placebo p `0.46155384`,
bootstrap p10 `-0.00027954`, and `T = -0.00200692` after removing the best 5%.
See the existing strategy reports for full definitions and context.

## Repository methodology

Read [METHODOLOGY.md](./METHODOLOGY.md) before interpreting results. Each
strategy directory documents its hypothesis, rules, configuration, tests,
saved evidence, limitations, and reproduction steps. The [ledger](./ledger.csv)
records available historical attempts; `N/A` is used instead of inventing
missing IDs or metrics.

## Data policy

Raw market datasets, aggTrades archives, ZIPs containing price data, large
generated datasets, credentials, and local environment files are not included.
See [DATA_POLICY.md](./docs/DATA_POLICY.md) and
[data_notes.md](./data_notes.md) for provenance and external data instructions.

## Reproducibility

Start with each strategy's `REPRODUCE.md`. Reproduction requires separately
obtained public market data matching the documented source and cutoff. Run
unit tests before invoking a historical runner; a test pass does not reproduce
reported performance. See [REPRODUCIBILITY.md](./docs/REPRODUCIBILITY.md).

## Repository structure

```text
strategies/
  btc-tsmom-v0/                         # Existing
  multi-asset-tsmom-v1/                 # Existing
  value-area-reentry-poc/               # Proposed addition
  btc-spot-trend-pullback-v1/           # Proposed addition
  btc-spot-donchian-v1/                 # Proposed addition
  range-reversal/                       # Proposed addition
  volatility-compression-breakout-retest-v1/ # Proposed addition
docs/                                   # Existing docs plus proposed references
ledger.csv                              # Existing; unchanged
data_notes.md                           # Existing; unchanged
LICENSE                                 # Existing; unchanged
```

The five proposed strategy packages contain code, tests, saved configurations,
and compact reports/aggregate evidence. Raw market data, detailed trade/event
rows, and bulky generated plots are excluded.

## Reference material

- [Glossary](./docs/GLOSSARY.md)
- [Lessons](./docs/LESSONS.md)
- [Timeline](./docs/TIMELINE.md)
- [Strategy coverage](./docs/STRATEGY_COVERAGE.md)
- [Data policy](./docs/DATA_POLICY.md)
- [Reproducibility](./docs/REPRODUCIBILITY.md)
