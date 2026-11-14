# BTC Spot Donchian V1

## Status and scope

This package preserves the historical BTCUSDT Binance Spot, long-only daily Donchian research model, its runner, tests, configurations, and saved results. It is research evidence, not a live system, investment recommendation, or forecast. No order creation, leverage, shorting, pyramiding, or take-profit is implemented.

This model is separate from Trend Pullback V1. Donchian signals use completed UTC daily bars and minute-level entry/stop simulation. Trend Pullback uses H4 regime, H1 signals, and M1 execution. Their cost/execution models differ; do not compare or combine their equity as though they shared an execution model.

## Historical rules preserved

- On completed UTC day `t`, the entry upper channel is the maximum high of the preceding 20 complete days; the exit lower channel is the minimum low of the preceding 10 complete days. Both exclude day `t`.
- True range uses the current high/low and previous close. ATR20 is the simple mean (not Wilder), including current completed day `t`.
- `B_t = close_t > upper_t`; a signal requires a false-to-true `B` transition, no open position, and adequate consecutive complete-day history. Equality is not a breakout. The standard BASE_20D control does not rearm on a continuing true breakout after a canceled attempt.
- The next entry check uses the completed `00:00` minute's close and base volume; execution is modeled at `00:01` open with the scenario's adverse adjustment. `00:01` data does not set size.
- Initial stop is `floor_tick(close_t - 2*ATR20)` and does not trail. Quantity is constrained by planned risk, available cash, and the `00:00` minute volume, then rounded down to step size. Buy fee is accounted in received BTC; sell fee in USDT proceeds.
- Exit is the fixed stop, a completed-day close below the prior-10-day lower channel sold on the next `00:01` open, the exact 60-day time limit, or end of test. Stop-gap and stop/timed-exit ordering follow the implementation. There is no take-profit.
- DIAGNOSTIC_ZERO has no modeled costs. BASE uses 0.10% fee per side, 0.01% half-spread, and 0.02% extra slippage; STRESS uses 0.10%, 0.02%, and 0.08%, respectively. The resulting total adverse price adjustment is applied as implemented. These are assumptions, not historical quotes or a specific account tariff.
- Tick `0.01`, step `0.000001`, zero minimum quantity/notional are conditional model values, not reconstructed historical exchange filters.

The original (Russian-language) strategy record is preserved verbatim in [`docs/HISTORICAL_STRATEGY_SPEC.ru.md`](docs/HISTORICAL_STRATEGY_SPEC.ru.md). Constants live in the copied model module; the exact saved run configurations are in `configs/`.

## Canonical corrected control and saved results

### Corrected pre-2025 BASE_20D control

The retained `reports/control_reproduction_audit_all_segments/comparison_metrics.csv` preserves compact metric rows by segment, variant, and scenario; `control_reproduction.csv` retains the saved old-vs-corrected aggregate audit. The pre-2025 rows remain identified per segment and end at 2024-12-31; the final Jan–Jun 2025 row is separate, not combined with those segments. Detailed per-segment trade, signal, and equity CSVs were intentionally excluded from this overlay. There is no combined or compounded segment-equity result. Do not sum segment returns.

For orientation, the saved corrected control's `segment_031_2023-03-25_2024-12-31` BASE row contains 9 closed trades and net PnL `710.744300088037565515000000` USDT (the precise saved values remain in the audit/comparison files). This is one segment only, not a whole-history or portfolio result. The all-segment control reproduction audit and paired comparison table are isolated under `reports/control_reproduction_audit_all_segments/`; that audit includes the separate Jan–Jun 2025 row. `control_reproduction.csv` reports no closed-trade changes between the compared control snapshots; inspect the saved rows rather than treating an all-window table as an equity aggregation.

### Jan–Jun 2025 kept separate

`reports/jan_jun_2025/` contains the canonical saved report and compact aggregate output for `2025-01-01T00:00:00` through (exclusive) `2025-07-01T00:00:00`, with December 2024 warmup. The paired BASE_20D control metrics appear in the separately labeled Jan–Jun row of `reports/control_reproduction_audit_all_segments/comparison_metrics.csv`; detailed paired-control rows were excluded. Jan–Jun is not part of the pre-2025 segment folder and is not added to pre-2025 segment equity.

Saved main-run BASE evidence for this six-month period: 2 closed trades (1 win, 1 loss), net PnL `15.290651447982994253000000` USDT, return `0.152906514479829942530000%`, profit factor `1.305836982242587663208868973089720312530`, and maximum daily drawdown `62.826816917128613304` USDT. These are the saved result metrics for two trades, not evidence of a stable edge. ZERO is a diagnostic only. The original exact metrics and full precision are in `reports/jan_jun_2025/metrics.json` and `report.md`.

### Superseded snapshots

`reports/superseded/` retains only the original `report.md`, `run_config.json`, and `metrics.json` from the earlier `btc_spot_donchian_v1_pre2025` and `btc_spot_donchian_v1_pre2025_complete_segment` snapshots. They are preserved for provenance, explicitly **not canonical control results**. Use the per-segment `BASE_20D` files above as the corrected pre-2025 control. Do not merge superseded metrics, equity, or trades into either corrected pre-2025 or Jan–Jun 2025 results.

## Data, missingness, and limitations

The historical runs use recovered minute OHLCV and complete daily windows. Missing minutes split observations/segments; no missing candle is synthesized. The main Jan–Jun report records 305,280 minutes, 212 complete UTC days, zero missing minutes, and no incomplete days. The pre-2025 output is saved per qualifying continuous segment, not as one uninterrupted account. Historical exchange filters, order-book depth, partial fills, and bid/ask quotes are not reconstructed by this OHLCV model.

## Package adaptations and exclusions

- Copied code, unit tests, source strategy document, saved configurations, and selected historical outputs are byte-preserving. Metrics were not recalculated, rounded, or edited.
- Jan–Jun 2025 canonical report/metrics are physically separate from the pre-2025 BASE_20D metric rows; the all-window audit is isolated because it also includes a Jan–Jun row. Detailed row-level result files and visualizations were intentionally excluded from this archive overlay; original project artifacts are untouched.
- The two superseded snapshots retain their source report/config/metrics only; they are not promoted to canonical evidence.
- Raw market data, M1/aggTrades CSV inputs, archives, virtual environments, credentials, and unrelated strategies are excluded. Relative source filenames remain in the archived configs as historical identifiers, not as bundled datasets.
- `STAGED_FILES.txt` is the exact staged file inventory.

## Execution details

The sizing reference is `P = close(00:00)` and `V = base volume(00:00)`; both are the only minute fields used for order admission/sizing. With `a = half_spread + extra_slippage`, the model uses `P_hat=P(1+a)`, `S_hat=S0(1-a)`, and `d=P_hat-(1-f_buy)(1-f_sell)S_hat`; raw quantity is the minimum of `0.5% × equity/d`, `99% × free_USDT/P_hat`, and `1% × V`, then rounded down to step size. The modeled buy fill is the `00:01` open adjusted by `a`. Planned risk `R` is net trade PnL divided by `0.5% × equity immediately before entry`; it is not a guarantee of maximum loss.

For an exit minute, a previously scheduled lower-channel sale on the `00:01` open has priority over later movement in that minute. Otherwise an open at/below the stop is a `STOP_GAP` from the open; if the open is above the stop but the low touches it, the stop is filled from the fixed stop. The exact 60×24-hour time exit is on its deadline minute's open after stop handling. An unexpected missing minute while a position is open is recorded as `DATA_INCOMPLETE`; candles are not synthesized. Monthly tables are mark-to-market, and positions are not force-closed at month boundaries.

## Publication overlay contents

This staged public overlay retains the canonical Markdown reports, compact aggregate metrics, control-comparison and segment-inventory tables, data-quality summaries, source, configs, and focused tests. Detailed per-trade/per-signal CSVs, dense equity time-series CSVs, daily-indicator series, trade-level audit/diff tables, and generated per-segment/per-trade SVGs or gallery HTML/index pages were intentionally excluded from the archive. This cleanup affects only the staging copy; original project artifacts are untouched. Saved metric summaries remain separate by segment/scenario, and the Jan–Jun 2025 evidence remains distinct from pre-2025 BASE_20D control evidence. `STAGED_FILES.txt` lists exactly what remains.
