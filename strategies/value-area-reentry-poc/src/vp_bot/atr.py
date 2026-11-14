"""Wilder ATR(14) on completed, continuous hourly candles."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Dict, Iterable, List, Optional


@dataclass(frozen=True)
class ATRPoint:
    open_time: datetime
    close_time: datetime
    tr: Optional[float]
    atr: Optional[float]
    valid_hour: bool
    reason: str


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _valid_hour(row: Dict[str, str]) -> bool:
    try:
        values = [float(row[key]) for key in ("open", "high", "low", "close")]
        complete = row.get("complete_60_distinct_minutes", "True") == "True"
    except (KeyError, TypeError, ValueError):
        return False
    return complete and all(math.isfinite(value) for value in values) and values[2] <= values[0] <= values[1] and values[2] <= values[3] <= values[1]


def compute_wilder_atr(rows: Iterable[Dict[str, str]], period: int = 14) -> List[ATRPoint]:
    """Return one ATR point per input hour; ATR never uses a future row."""
    if period <= 0:
        raise ValueError("period must be positive")
    result: List[ATRPoint] = []
    tr_buffer: List[float] = []
    previous_close: Optional[float] = None
    previous_open: Optional[datetime] = None
    previous_atr: Optional[float] = None
    for row in sorted(rows, key=lambda item: item["open_time"]):
        open_time, close_time = _dt(row["open_time"]), _dt(row["close_time"])
        if not _valid_hour(row):
            result.append(ATRPoint(open_time, close_time, None, None, False, "invalid_or_incomplete_hour"))
            tr_buffer, previous_close, previous_open, previous_atr = [], None, None, None
            continue
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        contiguous = previous_open is not None and open_time == previous_open + timedelta(hours=1)
        if not contiguous:
            tr_buffer, previous_atr = [], None
            tr = high - low
            reason_prefix = "sequence_reset"
        else:
            tr = max(high - low, abs(high - (previous_close or close)), abs(low - (previous_close or close)))
            reason_prefix = ""
        tr_buffer.append(tr)
        if len(tr_buffer) < period:
            atr, reason = None, reason_prefix + (";" if reason_prefix else "") + "warming_up"
        elif len(tr_buffer) == period or previous_atr is None:
            atr = sum(tr_buffer[-period:]) / period
            reason = reason_prefix + (";" if reason_prefix else "") + "ready"
        else:
            atr = (previous_atr * (period - 1) + tr) / period
            reason = reason_prefix + (";" if reason_prefix else "") + "ready"
        result.append(ATRPoint(open_time, close_time, tr, atr, True, reason))
        previous_close, previous_open, previous_atr = close, open_time, atr
    return result
