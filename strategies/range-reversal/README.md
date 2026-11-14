# Range Reversal — BTCUSDT Spot research package

This package preserves the Range Reversal research logic and its corrected
April–June 2025 validation. It is a historical research artifact, not a
recommendation, production trading system, or claim of profitability.

## Strategy and evidence boundaries

The signal study constructs each local-day range from the first four hours
(`00:00–04:00`, fixed UTC−04:00 year-round) using minute OHLCV. It aggregates
only complete five-minute candles. The V2 detector requires a five-minute
close strictly outside the range; shadows and equality do not start an event.
For N3, three consecutive later closes strictly inside the original range
confirm the event. A close outside or on the breakout boundary resets that
count, while touching/crossing the opposite range boundary cancels the event.
Missing candles and local midnight are explicit cancellation boundaries.
At most one detector episode is allowed per local day.

The event-study layer and execution layer are deliberately separate:

1. `range_reversal_v2.py` labels ranges, episodes, cancellations, and signals.
   This is an event study, not a fill or PnL simulation.
2. `range_reversal_delayed.py` annotates N3 signals using the first inside
   close. Its two stop variants are independent: the breakout-through-first-
   return extremum, and a strict local 2×2 pivot. The corrected annotation
   variant fixes its planned 2R target from E1; it does not simulate a
   portfolio.
3. `range_reversal_backtest.py` evaluates individual annotations with minute
   OHLCV, adverse fills, fees, ambiguity handling, and exits. The corrected
   April–June validation runner selects the breakout-extremum stop and
   **re-bases the target to 2R from the actual E3 entry fill**. That is a
   separate execution-test target convention from the E1 annotation. Its
   filter is `range_width / E3_entry_fill × 100 <= 1.246290688786655202027240847`
   and breakout-to-E3 delay `<= 50 minutes`. Filter rejection does not trigger
   a second signal on that day.

The validation is a unit-size price model, not an account-equity or
portfolio-level backtest. Commission is 0%; adverse slippage is 0.02% per side
and is included in fills. SHORT outcomes are hypothetical labels on Spot
OHLCV; no borrow, funding, or short-account mechanics are modeled. The tested
period was April 1 through June 30, 2025 in the fixed local clock, with 90
complete days and one incomplete local day skipped.

See [`reports/SAVED_RESULTS.md`](reports/SAVED_RESULTS.md) for the exact saved
aggregate evidence and artifact status. Full-precision saved aggregates are in
[`reports/apr-jun-2025-corrected-metrics.json`](reports/apr-jun-2025-corrected-metrics.json).

## Package contents

- `src/vp_bot/`: copied strategy detector, annotation, per-trade execution
  model, and corrected validation runner.
- `tests/`: focused unit tests using small synthetic candles; they do not
  launch historical runs or access external data.
- `config/`: relative-path run configurations retained from the corrected
  evidence.
- `reports/`: aggregate metrics and a sanitized narrative only.
- [`REPRODUCE.md`](REPRODUCE.md): safe unit-test instructions and optional
  manual reproduction instructions for users who supply authorized data.

## Artifact status

- **Canonical executed-test evidence:** corrected April–June 2025 validation,
  using the E3-rebased 2R target and corrected local-day completeness rule.
- **Corrected event annotation:** corrected delayed-N3 annotation, with its
  E1-fixed target and separate stop variants. Its results are not merged with
  the later E3-target execution test.
- **Superseded and excluded:** the superseded April–June validation used the
  wrong E1 target mode and treated June 30 as complete. The superseded delayed
  N3 comparison also overstated string-format differences as numerical stop
  changes. Neither superseded report nor its trade-level files are included.
- V1, V2-N1 and unfiltered V2-N3 remain distinct upstream signal definitions;
  their periods and outcomes are not combined with the corrected April–June
  results.

## Staging-only adaptations

The source files and unit tests were copied into a standalone `src/vp_bot`
layout without changing strategy logic. Configs retain relative input-data
references, not machine-specific locations. Aggregate metrics were retained;
raw OHLCV, event/trade CSVs, SVGs, HTML galleries, and other per-trade outputs
were excluded. No backtest, experiment, data download, or order submission was
performed while preparing this package.
