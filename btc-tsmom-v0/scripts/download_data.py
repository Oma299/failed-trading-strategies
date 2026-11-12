from __future__ import annotations

import hashlib
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_zips"
OUTPUT_PATH = ROOT / "data" / "btcusdt_m1_research.parquet"
BASE_URL = (
    "https://data.binance.vision/data/spot/monthly/klines/"
    "BTCUSDT/1m/BTCUSDT-1m-"
)
START_YEAR = 2017
START_MONTH = 8
END_YEAR = 2025
END_MONTH = 6
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT_SECONDS = 60
CSV_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
OUTPUT_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]
CUTOFF = pd.Timestamp("2025-07-01T00:00:00Z")


def months_in_range() -> list[tuple[int, int]]:
    months = []
    year, month = START_YEAR, START_MONTH
    while (year, month) <= (END_YEAR, END_MONTH):
        months.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha256(checksum_path: Path) -> str:
    text = checksum_path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not match:
        raise ValueError(f"No SHA256 digest found in {checksum_path.name}")
    return match.group(1).lower()


def fetch_file(session: requests.Session, url: str, destination: Path) -> None:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    destination.write_bytes(response.content)


def download_month(session: requests.Session, year: int, month: int) -> Path:
    month_id = f"{year:04d}-{month:02d}"
    filename = f"BTCUSDT-1m-{year:04d}-{month:02d}.zip"
    zip_path = RAW_DIR / filename
    checksum_path = RAW_DIR / f"{filename}.CHECKSUM"
    zip_url = f"{BASE_URL}{year:04d}-{month:02d}.zip"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if not checksum_path.exists():
                fetch_file(session, f"{zip_url}.CHECKSUM", checksum_path)
            if not zip_path.exists():
                fetch_file(session, zip_url, zip_path)

            expected = expected_sha256(checksum_path)
            actual = sha256_file(zip_path)
            if actual != expected:
                zip_path.unlink(missing_ok=True)
                raise ValueError(
                    f"SHA256 mismatch for {month_id}: expected {expected}, got {actual}"
                )
            print(f"{month_id}: downloaded and SHA256 verified")
            return zip_path
        except (OSError, requests.RequestException, ValueError, zipfile.BadZipFile) as exc:
            zip_path.unlink(missing_ok=True)
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Failed to download/verify month {month_id} "
                    f"after {MAX_ATTEMPTS} attempts: {exc}"
                ) from exc
            time.sleep(attempt)

    raise AssertionError("Unreachable")


def read_month(zip_path: Path) -> tuple[pd.DataFrame, str]:
    with zipfile.ZipFile(zip_path) as archive:
        csv_files = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"Expected one CSV in {zip_path.name}, found {len(csv_files)}")
        with archive.open(csv_files[0]) as csv_file:
            frame = pd.read_csv(
                csv_file,
                header=None,
                names=CSV_COLUMNS,
                usecols=CSV_COLUMNS[:6],
                dtype={"open_time": "int64"},
            )

    timestamp_unit = (
        "microseconds" if bool((frame["open_time"] > 1e14).any()) else "milliseconds"
    )
    micros = frame["open_time"] > 1e14
    frame.loc[micros, "open_time"] = frame.loc[micros, "open_time"] // 1000
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    for column in OUTPUT_COLUMNS[1:]:
        frame[column] = frame[column].astype("float64")
    return frame[OUTPUT_COLUMNS], timestamp_unit


def report_checks(frame: pd.DataFrame) -> None:
    times = frame["open_time"]
    duplicate_count = int(times.duplicated().sum())
    strictly_increasing = bool(times.is_monotonic_increasing and not times.duplicated().any())
    assert times.max() < CUTOFF, (
        f"Maximum open_time {times.max()} is not before {CUTOFF}"
    )

    deltas = times.diff().dt.total_seconds().div(60)
    missing_per_gap = (deltas - 1).where(deltas > 1, 0)
    total_missing = int(missing_per_gap.sum())
    gaps = []
    for index in missing_per_gap[missing_per_gap > 0].index:
        missing_count = int(missing_per_gap.loc[index])
        right = times.loc[index]
        left = times.loc[index - 1]
        gaps.append((missing_count, left + pd.Timedelta(minutes=1), right - pd.Timedelta(minutes=1)))
    gaps.sort(key=lambda gap: gap[0], reverse=True)

    print(f"Rows: {len(frame)}")
    print(f"Minimum open_time: {times.min()}")
    print(f"Maximum open_time: {times.max()}")
    print(f"Duplicate open_time rows: {duplicate_count}")
    print(f"Strictly increasing open_time: {strictly_increasing}")
    print(f"Missing minutes: {total_missing}")
    print("10 longest gaps (missing minutes, first missing minute, last missing minute):")
    for gap in gaps[:10]:
        print(f"  {gap[0]}, {gap[1]}, {gap[2]}")
    if not gaps:
        print("  None")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames = []
    units_by_year: dict[int, set[str]] = {}
    with requests.Session() as session:
        for year, month in months_in_range():
            zip_path = download_month(session, year, month)
            frame, timestamp_unit = read_month(zip_path)
            frames.append(frame)
            units_by_year.setdefault(year, set()).add(timestamp_unit)

    data = pd.concat(frames, ignore_index=True)
    data = data.sort_values("open_time", kind="mergesort").reset_index(drop=True)

    for year in sorted(units_by_year):
        print(f"Year {year}: detected timestamp unit: {', '.join(sorted(units_by_year[year]))}")

    report_checks(data)
    data.to_parquet(OUTPUT_PATH, index=False, engine="pyarrow")
    print(f"Parquet: {OUTPUT_PATH}")
    print(f"Parquet SHA256: {sha256_file(OUTPUT_PATH)}")
    shutil.rmtree(RAW_DIR)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
