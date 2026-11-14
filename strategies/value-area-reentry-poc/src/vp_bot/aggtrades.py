"""Validate local Binance Spot aggTrades archives and build exact-price profiles."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, getcontext
import hashlib
import io
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from zipfile import ZipFile

getcontext().prec = 40

@dataclass(frozen=True)
class AggTradeQuality:
    day: str
    row_count: int
    first_timestamp: Optional[str]
    last_timestamp: Optional[str]
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    quantity_total: Decimal
    malformed_rows: int
    out_of_range_rows: int
    time_order_violations: int
    duplicate_aggregate_trade_ids: int
    id_order_violations: int
    id_gap_count: int
    max_id_gap: int
    csv_uncompressed_bytes: int


@dataclass(frozen=True)
class AggProfile:
    day: str
    available_at: str
    valid: bool
    reason: str
    source: str
    method: str
    day_low: Optional[Decimal] = None
    day_high: Optional[Decimal] = None
    val: Optional[Decimal] = None
    poc: Optional[Decimal] = None
    vah: Optional[Decimal] = None
    total_volume: Optional[Decimal] = None
    value_area_volume: Optional[Decimal] = None
    value_area_fraction: Optional[Decimal] = None
    bin_step: Optional[Decimal] = None


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    raw = value.strip()
    if not raw.isdigit():
        raise ValueError("timestamp is not an integer")
    epoch = int(raw)
    if len(raw) >= 16 or epoch >= 100_000_000_000_000:
        seconds, micros = divmod(epoch, 1_000_000)
    elif len(raw) >= 13 or epoch >= 100_000_000_000:
        seconds, micros = divmod(epoch, 1_000)
        micros *= 1_000
    else:
        raise ValueError("timestamp is neither milliseconds nor microseconds")
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=micros)


def verify_checksum(archive: Path, checksum: Path) -> str:
    expected = next((part for part in checksum.read_text(encoding="utf-8").split() if len(part) == 64), "")
    if not expected:
        raise ValueError("no SHA-256 digest found in %s" % checksum)
    digest_context = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest_context.update(chunk)
    digest = digest_context.hexdigest()
    if digest.lower() != expected.lower():
        raise ValueError("checksum mismatch for %s" % archive)
    return digest


def _iter_rows(archive: Path) -> Iterator[Tuple[str, ...]]:
    with ZipFile(archive) as zipped:
        members = [info for info in zipped.infolist() if info.filename.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError("expected one CSV in %s" % archive)
        with zipped.open(members[0], "r") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8", newline="")
            reader = csv.reader(text)
            for fields in reader:
                if not fields or not fields[0].strip().lstrip("-").isdigit():
                    continue
                yield tuple(field.strip() for field in fields)


def _parse_row(fields: Tuple[str, ...]) -> Dict[str, object]:
    if len(fields) < 8:
        raise ValueError("expected 8 aggTrades fields")
    agg_id, price, quantity, first_id, last_id, timestamp = fields[:6]
    try:
        parsed = {"agg_trade_id": int(agg_id), "price": Decimal(price), "quantity": Decimal(quantity), "first_trade_id": int(first_id), "last_trade_id": int(last_id), "timestamp": parse_timestamp(timestamp)}
    except (ValueError, InvalidOperation) as error:
        raise ValueError(str(error))
    if parsed["agg_trade_id"] < 0 or parsed["first_trade_id"] < 0 or parsed["last_trade_id"] < 0 or parsed["first_trade_id"] > parsed["last_trade_id"] or parsed["price"] <= 0 or parsed["quantity"] <= 0:
        raise ValueError("non-positive price/quantity or invalid IDs")
    return parsed


def inspect_quality(archive: Path, target_day: date) -> AggTradeQuality:
    start = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    row_count = malformed = out_of_range = time_violations = duplicate_ids = id_order = gaps = max_gap = 0
    first_timestamp = last_timestamp = None
    min_price = max_price = None
    quantity_total = Decimal(0)
    previous_time = None
    previous_id = None
    seen_ids = set()
    with ZipFile(archive) as zipped:
        csv_info = next(info for info in zipped.infolist() if info.filename.lower().endswith(".csv"))
        csv_size = csv_info.file_size
    for fields in _iter_rows(archive):
        try:
            row = _parse_row(fields)
        except ValueError:
            malformed += 1
            continue
        timestamp = row["timestamp"]
        if timestamp < start or timestamp >= end:
            out_of_range += 1
        if previous_time is not None and timestamp < previous_time:
            time_violations += 1
        previous_time = timestamp
        agg_id = row["agg_trade_id"]
        if agg_id in seen_ids:
            duplicate_ids += 1
        seen_ids.add(agg_id)
        if previous_id is not None:
            if agg_id < previous_id:
                id_order += 1
            elif agg_id > previous_id + 1:
                gaps += 1
                max_gap = max(max_gap, agg_id - previous_id - 1)
        previous_id = agg_id
        row_count += 1
        first_timestamp = first_timestamp or _utc_iso(timestamp)
        last_timestamp = _utc_iso(timestamp)
        min_price = row["price"] if min_price is None else min(min_price, row["price"])
        max_price = row["price"] if max_price is None else max(max_price, row["price"])
        quantity_total += row["quantity"]
    return AggTradeQuality(str(target_day), row_count, first_timestamp, last_timestamp, min_price, max_price, quantity_total, malformed, out_of_range, time_violations, duplicate_ids, id_order, gaps, max_gap, csv_size)


def _bin_index(price: Decimal, low: Decimal, high: Decimal, count: int) -> int:
    if price == high:
        return count - 1
    step = (high - low) / Decimal(count)
    index = int((price - low) / step)
    return max(0, min(count - 1, index))


def calculate_agg_profile(archive: Path, target_day: date, quality: AggTradeQuality, bin_count: int = 100) -> Tuple[AggProfile, List[Dict[str, object]]]:
    available_at = _utc_iso(datetime.combine(target_day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    if quality.row_count == 0 or quality.malformed_rows or quality.out_of_range_rows or quality.min_price is None or quality.max_price is None:
        return AggProfile(str(target_day), available_at, False, "invalid_aggtrades_quality", "binance_spot_aggTrades", "aggtrades_exact_price"), []
    if quality.quantity_total <= 0 or quality.min_price == quality.max_price:
        reason = "zero_total_quantity" if quality.quantity_total <= 0 else "degenerate_trade_price_range"
        return AggProfile(str(target_day), available_at, False, reason, "binance_spot_aggTrades", "aggtrades_exact_price"), []
    low, high = quality.min_price, quality.max_price
    step = (high - low) / Decimal(bin_count)
    volumes = [Decimal(0)] * bin_count
    day_start = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    for fields in _iter_rows(archive):
        try:
            row = _parse_row(fields)
        except ValueError:
            continue
        if day_start <= row["timestamp"] < day_end:
            volumes[_bin_index(row["price"], low, high, bin_count)] += row["quantity"]
    total = sum(volumes, Decimal(0))
    max_volume = max(volumes)
    poc_index = next(index for index, value in enumerate(volumes) if value == max_volume)
    first = last = poc_index
    selected = volumes[poc_index]
    while selected < total * Decimal("0.70") and (first > 0 or last < bin_count - 1):
        lower = volumes[first - 1] if first > 0 else None
        upper = volumes[last + 1] if last < bin_count - 1 else None
        if upper is None or (lower is not None and lower >= upper):
            first -= 1
            selected += volumes[first]
        else:
            last += 1
            selected += volumes[last]
    edges = [low + step * index for index in range(bin_count + 1)]
    bins = [{"source": "binance_spot_aggTrades", "method": "aggtrades_exact_price", "date": str(target_day), "bin_index": index, "lower": edges[index], "upper": edges[index + 1], "volume": volumes[index], "selected_for_value_area": first <= index <= last} for index in range(bin_count)]
    profile = AggProfile(str(target_day), available_at, True, "", "binance_spot_aggTrades", "aggtrades_exact_price", low, high, edges[first], (edges[poc_index] + edges[poc_index + 1]) / Decimal(2), edges[last + 1], total, selected, selected / total, step)
    return profile, bins


def write_profile(profile: AggProfile, bins: Sequence[Dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["source", "method", "date", "available_at", "valid", "reason", "day_low", "day_high", "val", "poc", "vah", "total_volume", "value_area_volume", "value_area_fraction", "bin_step"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        values = profile.__dict__.copy()
        values["date"] = values.pop("day")
        writer.writerow(values)
    bin_path = path.with_name("aggtrades_profile_bins.csv")
    bin_fields = ["source", "method", "date", "bin_index", "lower", "upper", "volume", "selected_for_value_area"]
    with bin_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=bin_fields)
        writer.writeheader()
        writer.writerows(bins)
