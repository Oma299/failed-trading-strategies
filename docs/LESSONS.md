# Research Lessons

These are documentation principles supported by the archived studies, not
claims that any strategy is profitable.

- Strong BTC price growth may mask the absence of a predictive signal.
- Placebo shifts are used to screen for asset drift.
- Freeze rules and decision criteria before a run.
- Do not hide implementation bugs; mark affected runs `INVALID` in the ledger.
- A detection event is not a trade. Report event-study counts separately from
  planned entries and completed simulated trades.
- Execution costs can reverse a diagnostic result. Present the saved BASE
  scenario separately from ZERO-cost diagnostics.
- Small samples remain inconclusive even when headline metrics look favorable.
  State trade counts next to every result.
- Data gaps, incomplete candles, and holding-period limits can materially
  change results. Preserve corrected and superseded attempts rather than
  silently replacing them.
- Do not concatenate independent historical segments into a portfolio return
  unless the original run explicitly modeled a shared account and capital path.
- Reproducibility requires the exact data period, configuration, execution
  assumptions, and provenance—not just a strategy source file.

Related references: [glossary](./GLOSSARY.md), [timeline](./TIMELINE.md), and
[methodology](../METHODOLOGY.md).
