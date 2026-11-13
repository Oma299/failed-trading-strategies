# Failed Trading Strategies Archive

This repository archives trading strategies that did not pass pre-registered
validation, together with their code and a ledger of every run.
It exists to show the methodology, not profits.
To read it: start with the table below, open a strategy folder, then read
[METHODOLOGY.md](./METHODOLOGY.md) and the reference material in [docs/](./docs/).
Each strategy folder contains a README, code, tests, and reports.

| Strategy | Market | Period | Evaluation method | Verdict | Recorded failure reason |
|---|---|---|---|---|---|
| [BTC Spot TSMOM V0](./strategies/btc-tsmom-v0/) | BTCUSDT spot | 2017-08-17–2025-06-30 data; Stage 2 starts 2022-10-29 | Entry diagnostics followed by a BASE/STRESS backtest with separate weekday portfolios | V0 family closed; Stage 2 §5 criteria were not met; no Stage 2 tri-state verdict was defined | Stage 2 report records bootstrap p10 = -0.000296, annual profit concentration = 0.687666, placebo p = 0.397360, and 60 trades against a 100-trade minimum |
| [Multi-asset TSMOM V1](./strategies/multi-asset-tsmom-v1/) | Six FX pairs and five ETFs | 1993-01-29–2025-06-30 data range | Daily momentum blocks across the eleven-asset basket; placebo and ISO-week bootstrap | ABANDON | V1 report records placebo p = 0.46155384, bootstrap p10 = -0.00027954, and T after removing the best 5% = -0.00200692 |

This archive is for historical research and is **not financial advice**.

See [METHODOLOGY.md](./METHODOLOGY.md) for the evaluation and record-keeping rules.
Project notes are in [data_notes.md](./data_notes.md), and all attempts are
listed in [ledger.csv](./ledger.csv). See [LESSONS](./docs/LESSONS.md),
[GLOSSARY](./docs/GLOSSARY.md), and [TIMELINE](./docs/TIMELINE.md).

The `blocks*.csv` files and `data/` directory are intentionally not included
because they contain market prices. Results can be reproduced by running the
archived code with market data downloaded again, subject to each strategy's
closed-period cutoff.
