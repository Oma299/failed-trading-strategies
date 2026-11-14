# Glossary

- **Momentum:** A rule that uses past price movement to define a directional
  signal.
- **Lookback:** The earlier period used to calculate a return.
- **Rank:** The fraction of historical return observations below the current
  observation.
- **ON block:** A scheduled interval for which the signal is active.
- **OFF block:** A scheduled interval for which the signal is inactive.
- **Placebo shift:** A circular shift of the signal series used as a comparison
  against the observed alignment.
- **Bootstrap:** Resampling historical groups to describe variation in a
  statistic.
- **ISO week:** A calendar week numbered according to the ISO-8601 week-date
  system.
- **Cutoff:** The last permitted boundary of the historical data period.
- **INVALID run:** An attempt affected by an implementation bug and excluded
  from the decision.
- **Profit factor:** Gross profitable trade result divided by gross losing
  trade result.
- **Candidate / signal:** A rule-generated observation. It is not necessarily a
  planned or executed trade.
- **Event study:** An analysis of outcomes after observed events without a
  complete sequential position and portfolio simulation.
- **Executed simulated trade:** A position modeled under explicit fills,
  costs, sizing, and exit rules in a backtest.
- **BASE / STRESS:** Named execution-cost scenarios. Their exact assumptions
  are strategy-specific and must be read from that strategy's report.
- **ZERO / DIAGNOSTIC_ZERO:** A diagnostic scenario without ordinary trading
  costs; it must not be presented as the BASE net result.
- **Net R:** Net result normalized by the run's documented risk unit. The
  denominator is strategy-specific.
- **Maximum drawdown:** The largest reported peak-to-trough decline. It may
  refer to trade equity, mark-to-market equity, or R; the unit and method must
  be identified.
- **N/A:** Not reported or not applicable. It must not be replaced with a
  guessed or reconstructed value.

Related references: [lessons](./LESSONS.md), [timeline](./TIMELINE.md),
[strategy coverage](./STRATEGY_COVERAGE.md), and
[methodology](../METHODOLOGY.md).
