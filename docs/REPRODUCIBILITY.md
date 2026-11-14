# Reproducibility

1. Read the strategy README, configuration, report, and data policy before
   running code.
2. Obtain the exact public market-data source and date range stated for that
   strategy. No raw market data is bundled in this archive.
3. Validate timestamps, duplicates, gaps, candle completeness, and integrity
   hashes as required by the strategy's recorded protocol.
4. Install only the dependencies listed by that strategy.
5. Run its unit tests independently before invoking any historical runner.
6. Reproduce only the documented configuration and closed period. Do not
   silently alter strategy rules, execution assumptions, or cutoffs.
7. Record a new run as a separate ledger entry; do not overwrite a saved
   result.

The strategy-specific reproduction notes are authoritative for commands,
required inputs, and known environment assumptions. A successful unit-test run
does not reproduce historical performance.
