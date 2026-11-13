# Methodology

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

Strategy documentation:

- [BTC Spot TSMOM V0](./strategies/btc-tsmom-v0/README.md)
- [Multi-asset TSMOM V1](./strategies/multi-asset-tsmom-v1/README.md)
- [Attempt ledger](./ledger.csv)
- [Project data notes](./data_notes.md)
- [Lessons](./docs/LESSONS.md)
- [Glossary](./docs/GLOSSARY.md)
- [Timeline](./docs/TIMELINE.md)
