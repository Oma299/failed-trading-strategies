from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import config_v1 as config

ROOT = Path(__file__).resolve().parent
REQUIRED_COLUMNS = {"date", "open", "high", "low", "close", "volume"}
CUTOFF = pd.Timestamp(config.CUTOFF_DATE)


@dataclass
class AssetData:
    asset: str
    ticker: str
    kind: str
    timezone: str
    frame: pd.DataFrame
    data_hash: str
    diagnostics: dict[str, object]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_v1_data(root: Path = ROOT) -> dict[str, AssetData]:
    if set(config.ASSETS) != set(config.DATA_SHA256):
        raise ValueError("Asset list and configured SHA256 keys differ")

    assets: dict[str, AssetData] = {}
    for asset, metadata in config.ASSETS.items():
        path = root / config.DATA_DIR / str(metadata["filename"])
        if not path.is_file():
            raise FileNotFoundError(f"V1 data file is missing: {path}")
        file_hash = sha256_file(path)
        if file_hash != config.DATA_SHA256[asset]:
            raise ValueError(f"SHA256 mismatch for {asset}: {file_hash}")

        header = set(pd.read_csv(path, nrows=0).columns)
        if header != REQUIRED_COLUMNS:
            raise ValueError(f"Unexpected columns in {path.name}: {sorted(header)}")
        raw = pd.read_csv(path, usecols=["date", "open", "close"])
        dates = pd.to_datetime(raw.pop("date"), format="%Y-%m-%d", errors="raise")
        if dates.duplicated().any():
            raise ValueError(f"Duplicate Yahoo session dates in {path.name}")
        if not dates.is_monotonic_increasing:
            raise ValueError(f"Dates are not strictly increasing in {path.name}")
        if dates.empty:
            raise ValueError(f"No daily rows in {path.name}")
        if dates.max() >= CUTOFF:
            raise AssertionError(
                f"V1 cutoff violation in {path.name}: max date {dates.max().date()}"
            )

        raw.index = pd.DatetimeIndex(dates, name="date")
        for column in ("open", "close"):
            raw[column] = pd.to_numeric(raw[column], errors="raise")
        calendar = pd.date_range(raw.index.min(), raw.index.max(), freq="D", name="date")
        row_present = pd.Series(True, index=raw.index).reindex(
            calendar, fill_value=False
        )
        frame = raw.reindex(calendar)
        frame["row_present"] = row_present.astype(bool)

        diagnostics: dict[str, object] = {
            "first_date": raw.index.min().date().isoformat(),
            "last_date": raw.index.max().date().isoformat(),
            "daily_bars": int(len(raw)),
            "calendar_days": int(len(calendar)),
            "no_row_days": int((~frame["row_present"]).sum()),
            "empty_open_rows": int(
                (frame["row_present"] & frame["open"].isna()).sum()
            ),
            "empty_close_rows": int(
                (frame["row_present"] & frame["close"].isna()).sum()
            ),
            "sha256": file_hash,
        }
        assets[asset] = AssetData(
            asset=asset,
            ticker=str(metadata["ticker"]),
            kind=str(metadata["kind"]),
            timezone=str(metadata["timezone"]),
            frame=frame,
            data_hash=file_hash,
            diagnostics=diagnostics,
        )
    return assets
