# Research Methodology

- Define the hypothesis, asset universe, data period, execution rules, thresholds,
  and decision matrix before a run. Do not tune them after viewing results.
- Treat a pipeline execution as a recorded attempt. Record each attempt in the
  ledger with its variant and outcome; do not silently replace earlier rows.
- Use cyclic signal shifts for placebo comparisons and cyclic resampling of
  consecutive ISO-week blocks for bootstrap uncertainty.
- Keep the data period closed at the predeclared cutoff. Do not fetch or use
  observations beyond it.
- If an implementation bug invalidates a run, mark that attempt `INVALID` in
  the ledger and exclude it from decisions. Document the fix and record any
  authorized rerun as a separate attempt.
- Preserve reports and results as produced. Do not add post-hoc interpretation
  or recalculate metrics after viewing them.
- Raw market data and trade-block CSVs are excluded from this public archive.

## Evidence and run records

- Separate signal candidates, event-study observations, planned trades, and
  executed simulated trades. Never label event counts as executed trades.
- Quote metrics from saved reports or machine-readable result files. Do not
  recompute, combine, or silently replace historical results during packaging.
- Keep each run's strategy version, configuration, data period, execution
  assumptions, source report, and available hashes together.
- Mark invalidated or superseded attempts explicitly and retain their history;
  identify the corrected run used for current reporting.
- Use `N/A` when a metric was not recorded. Do not infer a verdict from a
  strategy name or from a small sample alone.

## Comparability

Results from different periods, position models, fee assumptions, or execution
rules are not directly comparable. Present variants separately and explain
the difference. In particular, diagnostic zero-cost results are not net
trading results, and disjoint time segments are not one compounded portfolio
unless the source study explicitly modeled that portfolio.

## Reproducibility

Each strategy package documents its exact historical configuration and
reproduction command. Reproduction requires the matching external market data;
the archive intentionally does not distribute raw market datasets. Historical
experiments are not rerun merely to prepare this archive.

## Research integrity

Preserve the implementation and historical parameter settings. Any packaging
adaptation must be documented and limited to path/import changes needed to run
the archived copy. Do not optimize rules or revise old results to improve
reported performance.

## Safety and scope

This archive contains historical research only. It does not include credentials
or authorize exchange access, paper orders, or live orders. Short-side Spot
price studies do not imply that short execution is available on Binance Spot.
