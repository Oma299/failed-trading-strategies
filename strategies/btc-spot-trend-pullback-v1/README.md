# BTC Spot Trend Pullback V1

## Status and scope

This is a research-only, long-only BTCUSDT Binance Spot strategy package. It preserves the first-stage historical implementation and saved first-stage outputs. It is not a live-trading system, investment recommendation, or evidence of expected future returns. No order placement, leverage, shorting, averaging, pyramiding, or take-profit logic is present.

The strategy is distinct from the Donchian package. It runs H4 regime, H1 signal/indicator, and M1 execution/stop logic; the Donchian strategy uses daily signals with M1 execution. Their execution assumptions and returns are not comparable or combinable.

## Historical rules preserved

- **Regime:** H4 EMA100 is seeded by the simple average of the first 100 complete closes and then updated recursively with `alpha=2/101`. A regime is true only when the close is strictly above EMA100 and EMA100 is strictly above its value six bars earlier.
- **Signal:** H1 RSI3 uses Wilder smoothing, seeded from the first three price changes. Flat gain/loss maps to 50; gain-only to 100; loss-only to 0. Entry requires the previous RSI at or below 20 and the current RSI strictly between 20 and 60, with the regime true at both H1 closes. RSI is not rounded for comparisons.
- **Volatility and readiness:** H1 ATR20 is the arithmetic mean of the last 20 true ranges, including the completed signal bar. Trading requires 300 consecutive complete H4 bars (50 days); the RSI-crossing H1 bars must also be in the allowed part of the continuous segment.
- **Entry:** One buy attempt is made at the next minute's open after the signal H1 close. Admission and sizing use that open; the previous 60 completed minutes supply the volume constraint. The open must be within an inclusive 0.5 ATR of the signal close. There can be no existing position/order; the previous H1 close must be strictly after the last exit.
- **Risk/stop:** Initial stop is `floor_tick(signal_close - 2*ATR20)` and remains fixed. No averaging, pyramiding, or take-profit is used. Money, fills, quantities, and rounding use Decimal arithmetic.
- **Exit:** Stop-gap is checked before scheduled exits, then stop. RSI exit is scheduled for one minute after an H1 close at/above 60; regime exit is scheduled one minute after an H4 close with a false regime; the time exit is on the open of the exact 48-hour deadline minute.
- **Accounting:** Buy commission reduces received BTC; sell commission reduces USDT proceeds. Dust remains in the ledger and is valued at zero.
- **Costs:** ZERO (no modeled fee/spread/slippage), FEE_ONLY (0.10% fee per side), BASE (0.10% per side, 0.01% full spread, 0.02% slippage per side), ADVERSE (0.10%, 0.02%, 0.05%), and STRESS (0.15%, 0.05%, 0.10%). These are scenario assumptions, not reconstructed historical quotes or an account-specific tariff.

The first-stage specification and its data policy are copied verbatim to [`docs/HISTORICAL_STRATEGY_SPEC.md`](docs/HISTORICAL_STRATEGY_SPEC.md). The frozen run configuration is in `configs/first-stage-run_config.json`; its source filename is an archival relative identifier, not a bundled input.

## Preserved evidence

The canonical saved first-stage Markdown report and compact evidence are under [`reports/first-stage/`](reports/first-stage/): scenario and per-segment metrics, aggregate monthly frequency/benchmarks, data quality, protocol checks, inventory, and run configuration. No historical run was repeated to create this package.

| Scenario | Closed trades | Wins / losses | Trade-weighted mean R |
|---|---:|---:|---:|
| ZERO (diagnostic only) | 847 | 617 / 230 | +0.05461920564663491247721415475307930722198 |
| FEE_ONLY | 847 | 471 / 376 | -0.08823728818771966630805893804014586052687 |
| BASE | 847 | 427 / 420 | -0.1173809429055353429429819884895337698460 |
| ADVERSE | 847 | 365 / 482 | -0.1548644171731262943385104529747305206059 |
| STRESS | 847 | 202 / 645 | -0.2559949987222451109131193007630925126640 |

**Interpretation:** ZERO is a no-cost diagnostic, not a tradable result. BASE, after the stated modeled costs, has negative trade-weighted mean R. These trade counts/means summarize the saved trades; each continuous data segment was a separate account with its own 10,000 USDT and 300-H4 warmup. Returns were not compounded across segments into a portfolio. Right-censored positions are terminal estimates and are excluded from ordinary profit-factor and win-rate calculations. The saved report notes that no historical BASE trade reached the 48-hour exit.

The research cutoff is **exclusive**: only input rows with `open_time < 2025-07-01T00:00:00Z` were eligible. July–December 2025 is not included. Missing minutes split independent segments; no bars were synthesized or interpolated. The recorded tick/step/minimum filters are modeling assumptions, not recovered historical Binance filters.

## Package adaptations and exclusions

- The implementation, runner, unit tests, first-stage run config, and saved report tree were copied without changing their contents. The specification copy has one staging-only edit replacing a link to the excluded source-project DOCX with an explanatory note; implemented rules and historical metrics were not edited or recomputed.
- Input M1 market data is intentionally absent. The relative `source`/input filename retained in the saved config identifies the historical data file but does not resolve inside this package. The runner accepts a caller-supplied path; see `REPRODUCE.md`.
- Raw M1/aggTrades/market-data CSVs, archives, virtual environments, credentials, and unrelated experiments are not included.
- Detailed per-trade/per-event CSVs, dense minute-by-minute equity series, generated plots, and gallery pages are intentionally excluded from this public overlay; original project artifacts are untouched. The full retained-file inventory is `STAGED_FILES.txt`.

## Publication overlay contents

This staged public overlay retains the canonical first-stage Markdown report, compact aggregate scenario/segment metrics, data-quality and segment-inventory tables, configuration, source, runner, and focused tests. Detailed per-trade/per-event CSVs, dense minute-by-minute equity series, generated per-segment/per-trade SVGs, and gallery HTML/index pages were intentionally excluded from the archive to avoid distributing row-level outputs and bulky plot assets. These exclusions apply only to this staging copy; original project artifacts are untouched. `STAGED_FILES.txt` lists exactly what remains.
