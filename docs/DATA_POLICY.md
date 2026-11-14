# Data Policy

## What the archive includes

The archive may include source code, configuration, tests, small metadata
manifests, and reviewed historical reports. Any included result must identify
the data source, covered period, cutoff, and relevant data-quality limitations
when those facts are preserved by the original study.

## What it excludes

Do not include raw Binance candles, aggTrade records, reconstructed market
price CSVs, trade-block datasets, ZIP archives containing market data, large
generated datasets, virtual environments, caches, temporary files, credentials,
API keys, `.env` files, private notes, or machine-specific personal paths.

Do not include data merely because it exists in a local project directory.
Retain only the source and checksums needed to document provenance, not the
underlying market-data payload.

## Reproduction data

Reproduction instructions should point readers to the exchange's public data
source, specify the required format and date range, and explain any validation
or integrity checks. Downloads and historical runs are the reader's separate
actions; packaging this archive must not fetch or regenerate market data.

## Verification before publication

Review the staged tree for forbidden data formats and large files, credentials,
private filesystem paths, `.venv`, `__pycache__`, and temporary artifacts.
Report exclusions and any remaining uncertainty in the staging manifest.
