"""Event-only Value Area return detector; no execution or position state."""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .atr import ATRPoint, compute_wilder_atr


@dataclass(frozen=True)
class EpisodeEvent:
    event_id: str
    day: str
    status: str
    state: str
    reason: str
    profile_date: str
    profile_available_at: str
    val: Optional[float]
    poc: Optional[float]
    vah: Optional[float]
    episode_start_time: str
    confirmation_time: str
    return_candle_number: Optional[int]
    episode_low: float
    atr: Optional[float]
    atr_reason: str
    planned_stop: Optional[float]
    target: Optional[float]
    planned_entry_time: Optional[str]


@dataclass(frozen=True)
class DailySignalSummary:
    day: str
    outcome: str
    reason: str
    profile_date: str
    profile_available_at: str
    event_id: str
    episode_start_time: str
    confirmation_time: str


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hour_is_valid(row: Dict[str, str]) -> bool:
    try:
        values = [float(row[key]) for key in ("open", "high", "low", "close")]
        return row.get("complete_60_distinct_minutes", "True") == "True" and all(math.isfinite(value) for value in values) and values[2] <= values[0] <= values[1] and values[2] <= values[3] <= values[1]
    except (KeyError, TypeError, ValueError):
        return False


def _profile_available(profile: Dict[str, str], decision_time: datetime) -> bool:
    return profile.get("valid") == "True" and _dt(profile["available_at"]) <= decision_time


def _make_event(event_id: str, day: date, profile: Dict[str, str], initial: Dict[str, str], confirmation: Optional[Dict[str, str]], status: str, state: str, reason: str, return_number: Optional[int], episode_low: float, atr_point: Optional[ATRPoint]) -> EpisodeEvent:
    confirmation_time = _iso(_dt(confirmation["close_time"])) if confirmation else ""
    atr = atr_point.atr if atr_point else None
    atr_reason = atr_point.reason if atr_point else "atr_not_available_at_confirmation"
    planned_stop = episode_low - 0.25 * atr if atr is not None else None
    planned_entry = _iso(_dt(confirmation["open_time"]) + timedelta(hours=1)) if confirmation else None
    if status == "RETURN_CONFIRMED" and atr is None:
        status = "ATR_UNAVAILABLE"
    return EpisodeEvent(
        event_id=event_id, day=str(day), status=status, state=state, reason=reason,
        profile_date=profile["date"], profile_available_at=profile["available_at"],
        val=float(profile["val"]), poc=float(profile["poc"]), vah=float(profile["vah"]),
        episode_start_time=_iso(_dt(initial["close_time"])), confirmation_time=confirmation_time,
        return_candle_number=return_number, episode_low=episode_low, atr=atr,
        atr_reason=atr_reason, planned_stop=planned_stop, target=float(profile["poc"]), planned_entry_time=planned_entry,
    )


def detect_events(hourly_rows: Iterable[Dict[str, str]], profiles: Iterable[Dict[str, str]], atr_points: Iterable[ATRPoint], start_day: date = date(2025, 1, 1), end_day: date = date(2025, 1, 31), max_return_bars: int = 3) -> Tuple[List[EpisodeEvent], List[DailySignalSummary]]:
    if max_return_bars < 1:
        raise ValueError("max_return_bars must be at least 1")
    rows = sorted(hourly_rows, key=lambda row: row["open_time"])
    profile_map = {row["date"]: row for row in profiles}
    atr_map = {point.open_time: point for point in atr_points}
    events: List[EpisodeEvent] = []
    summaries: List[DailySignalSummary] = []
    event_counter = 0
    days = sorted({ _dt(row["open_time"]).date() for row in rows if start_day <= _dt(row["open_time"]).date() <= end_day })
    for day in days:
        profile = profile_map.get(str(day - timedelta(days=1)))
        day_rows = [row for row in rows if _dt(row["open_time"]).date() == day]
        if profile is None or profile.get("valid") != "True":
            summaries.append(DailySignalSummary(str(day), "NO_PROFILE", "missing_or_invalid_previous_profile", profile["date"] if profile else "", profile["available_at"] if profile else "", "", "", ""))
            continue
        waiting = False
        started = False
        initial: Optional[Dict[str, str]] = None
        episode_low = 0.0
        waiting_rows: List[Dict[str, str]] = []
        event_id = ""
        outcome = "NO_EVENT"
        reason = "no_close_below_previous_val"
        for row in day_rows:
            row_open, row_close = _dt(row["open_time"]), _dt(row["close_time"])
            expected_open = _dt(initial["open_time"]) + timedelta(hours=len(waiting_rows) + 1) if waiting and initial else None
            if waiting and (not _hour_is_valid(row) or row_open != expected_open):
                event_counter += 1
                event_id = "event-%03d" % event_counter
                event = _make_event(event_id, day, profile, initial, None, "CANCELLED_DATA_QUALITY", "CANCELLED", "invalid_or_missing_hour_during_wait", None, episode_low, None)
                events.append(event)
                outcome, reason = event.status, event.reason
                waiting = False
                break
            if not _hour_is_valid(row):
                continue
            if waiting:
                waiting_rows.append(row)
                episode_low = min(episode_low, float(row["low"]))
                candle_number = len(waiting_rows)
                close = float(row["close"])
                if float(profile["val"]) < close < float(profile["poc"]):
                    event_counter += 1
                    event_id = "event-%03d" % event_counter
                    event = _make_event(event_id, day, profile, initial, row, "RETURN_CONFIRMED", "RETURN_CONFIRMED", "close_inside_val_poc", candle_number, episode_low, atr_map.get(row_open))
                    events.append(event)
                    outcome, reason = event.status, event.reason
                    waiting = False
                    break
                if candle_number == max_return_bars:
                    event_counter += 1
                    event_id = "event-%03d" % event_counter
                    event = _make_event(event_id, day, profile, initial, None, "EXPIRED", "EXPIRED", "%d_following_hours_without_return" % max_return_bars, None, episode_low, None)
                    events.append(event)
                    outcome, reason = event.status, event.reason
                    waiting = False
                    break
                continue
            if not started and _profile_available(profile, row_close) and float(row["close"]) < float(profile["val"]):
                started = True
                waiting = True
                initial = row
                episode_low = float(row["low"])
                waiting_rows = []
                outcome, reason = "WAIT_RETURN", "first_close_below_previous_val"
        if waiting:
            event_counter += 1
            event_id = "event-%03d" % event_counter
            event = _make_event(event_id, day, profile, initial, None, "CANCELLED_DAY_CHANGE", "CANCELLED", "unfinished_episode_at_utc_day_change", None, episode_low, None)
            events.append(event)
            outcome, reason = event.status, event.reason
        elif outcome == "WAIT_RETURN":
            outcome, reason = "NO_EVENT", "no_complete_following_hours"
        if outcome == "RETURN_CONFIRMED":
            outcome = "RETURN_CONFIRMED"
        summaries.append(DailySignalSummary(str(day), outcome, reason, profile["date"], profile["available_at"], event_id, event.episode_start_time if events and events[-1].event_id == event_id else "", event.confirmation_time if events and events[-1].event_id == event_id else ""))
    return events, summaries


def write_signal_outputs(events: Sequence[EpisodeEvent], summaries: Sequence[DailySignalSummary], atr_points: Sequence[ATRPoint], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    event_fields = list(EpisodeEvent.__dataclass_fields__)
    with (output_dir / "episode_events.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=event_fields)
        writer.writeheader()
        writer.writerows({field: getattr(event, field) for field in event_fields} for event in events)
    summary_fields = list(DailySignalSummary.__dataclass_fields__)
    with (output_dir / "daily_signal_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows({field: getattr(summary, field) for field in summary_fields} for summary in summaries)
    with (output_dir / "hourly_atr.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["open_time", "close_time", "tr", "atr", "valid_hour", "reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for point in atr_points:
            writer.writerow({"open_time": _iso(point.open_time), "close_time": _iso(point.close_time), "tr": point.tr, "atr": point.atr, "valid_hour": point.valid_hour, "reason": point.reason})
