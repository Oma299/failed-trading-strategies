"""Range Reversal V1 signal detector on minute BTCUSDT OHLCV.

The session clock is deliberately fixed at UTC-04:00.  This module only
labels price patterns; it does not model long or short order execution.
"""

import csv
import html
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


FIXED_OFFSET = timedelta(hours=-4)
UTC = timezone.utc
LOCAL_OFFSET = timezone(FIXED_OFFSET, name="UTC-04")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def local_day(value):
    return parse_time(value).astimezone(LOCAL_OFFSET).date()


def local_label(value):
    return parse_time(value).astimezone(LOCAL_OFFSET).isoformat()


def _minutes_by_time(rows):
    return {parse_time(row["open_time"]): row for row in rows}


def _m5_bucket(moment):
    return moment.replace(minute=(moment.minute // 5) * 5, second=0, microsecond=0)


def aggregate_m5(rows):
    """Aggregate only complete five-minute buckets; incomplete buckets remain visible as breaks."""
    grouped = {}
    for row in rows:
        moment = parse_time(row["open_time"])
        grouped.setdefault(_m5_bucket(moment), []).append(row)
    result = []
    for start in sorted(grouped):
        bucket = sorted(grouped[start], key=lambda row: row["open_time"])
        moments = [parse_time(row["open_time"]) for row in bucket]
        expected = [start + timedelta(minutes=i) for i in range(5)]
        complete = moments == expected
        item = {"open_time": iso(start), "close_time": iso(start + timedelta(minutes=5) - timedelta(microseconds=1)),
                "open": bucket[0]["open"], "high": max(row["high"] for row in bucket),
                "low": min(row["low"] for row in bucket), "close": bucket[-1]["close"],
                "volume": str(sum(float(row["volume"]) for row in bucket)),
                "source_minute_count": str(len(bucket)), "complete": str(complete)}
        result.append(item)
    return result


def _range_for_day(day, minute_by_time):
    local_midnight = datetime(day.year, day.month, day.day, tzinfo=LOCAL_OFFSET)
    start = local_midnight.astimezone(UTC)
    end = start + timedelta(hours=4)
    rows = [minute_by_time.get(start + timedelta(minutes=i)) for i in range(240)]
    missing = sum(row is None for row in rows)
    if missing:
        return {"local_date": day.isoformat(), "range_start_utc": iso(start), "range_end_utc": iso(end),
                "range_start_local": start.astimezone(LOCAL_OFFSET).isoformat(), "range_end_local": end.astimezone(LOCAL_OFFSET).isoformat(),
                "upper": "", "lower": "", "complete": "False", "reason": "INCOMPLETE_INITIAL_RANGE", "source_minute_count": str(240 - missing)}
    return {"local_date": day.isoformat(), "range_start_utc": iso(start), "range_end_utc": iso(end),
            "range_start_local": start.astimezone(LOCAL_OFFSET).isoformat(), "range_end_local": end.astimezone(LOCAL_OFFSET).isoformat(),
            "upper": max(row["high"] for row in rows), "lower": min(row["low"] for row in rows), "complete": "True", "reason": "", "source_minute_count": "240"}


def _episode_base(day, rng, direction, first):
    return {"local_date": day.isoformat(), "direction": direction, "range_upper": rng["upper"], "range_lower": rng["lower"],
            "breakout_time": first["open_time"], "breakout_time_local": local_label(first["open_time"]),
            "confirmation_time": "", "confirmation_time_local": "", "planned_entry_time": "", "planned_entry_time_local": "",
            "entry_open": "", "stop": "", "target_2r": "", "status": "WAITING_CONFIRMATION", "reason": "", "episode_bars": "0"}


def _finalize_episode(ep, bars, next_by_time):
    confirm = parse_time(ep["confirmation_time"])
    next_start = confirm + timedelta(minutes=5)
    entry = next_by_time.get(next_start)
    ep["planned_entry_time"] = iso(next_start)
    ep["planned_entry_time_local"] = local_label(iso(next_start))
    if entry is None or entry.get("complete") != "True":
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "MISSING_ENTRY_M5"
        return
    ep["entry_open"] = entry["open"]
    if not (float(ep["range_lower"]) < float(entry["open"]) < float(ep["range_upper"])):
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "ENTRY_OPEN_OUTSIDE_RANGE"
        return
    if ep["direction"] == "SHORT":
        stop = max(float(row["high"]) for row in bars)
        distance = stop - float(entry["open"])
        target = float(entry["open"]) - 2 * distance
    else:
        stop = min(float(row["low"]) for row in bars)
        distance = float(entry["open"]) - stop
        target = float(entry["open"]) + 2 * distance
    ep["stop"], ep["target_2r"] = str(stop), str(target)
    if distance <= 0:
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "NONPOSITIVE_STOP_DISTANCE"
    else:
        ep["status"], ep["reason"] = "SIGNAL", ""


def detect_range_reversal(rows, start_day=date(2025, 1, 1), end_day=date(2025, 3, 31)):
    rows = sorted(rows, key=lambda row: row["open_time"])
    minute_by_time = _minutes_by_time(rows)
    m5 = aggregate_m5(rows)
    m5_by_time = {parse_time(row["open_time"]): row for row in m5}
    ranges, episodes, signals = [], [], []
    day = start_day
    while day <= end_day:
        rng = _range_for_day(day, minute_by_time)
        ranges.append(rng)
        if rng["complete"] != "True":
            day += timedelta(days=1)
            continue
        range_end = parse_time(rng["range_end_utc"])
        local_next = datetime(day.year, day.month, day.day, tzinfo=LOCAL_OFFSET) + timedelta(days=1)
        day_end = local_next.astimezone(UTC)
        bars = [row for row in m5 if range_end <= parse_time(row["open_time"]) < day_end]
        active = None
        day_signaled = False
        for index, bar in enumerate(bars):
            if bar.get("complete") != "True":
                if active is not None:
                    active["status"], active["reason"] = "CANCELLED", "MISSING_M5"
                    episodes.append(active)
                    active = None
                continue
            high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            outside_up, outside_down = high > float(rng["upper"]), low < float(rng["lower"])
            if active is None and not day_signaled:
                if outside_up and outside_down:
                    episodes.append({"local_date": day.isoformat(), "direction": "BOTH_SIDES", "range_upper": rng["upper"], "range_lower": rng["lower"], "breakout_time": bar["open_time"], "breakout_time_local": local_label(bar["open_time"],), "confirmation_time": "", "confirmation_time_local": "", "planned_entry_time": "", "planned_entry_time_local": "", "entry_open": "", "stop": "", "target_2r": "", "status": "CANCELLED", "reason": "BOTH_SIDES", "episode_bars": "1"})
                    day_signaled = True
                    continue
                if outside_up:
                    active = _episode_base(day, rng, "SHORT", bar)
                elif outside_down:
                    active = _episode_base(day, rng, "LONG", bar)
            if active is not None:
                active["episode_bars"] = str(int(active["episode_bars"]) + 1)
                if active["direction"] == "SHORT" and outside_down:
                    active["status"], active["reason"] = "CANCELLED", "BOTH_SIDES"
                    episodes.append(active); active = None; day_signaled = True; continue
                if active["direction"] == "LONG" and outside_up:
                    active["status"], active["reason"] = "CANCELLED", "BOTH_SIDES"
                    episodes.append(active); active = None; day_signaled = True; continue
                inside = float(rng["lower"]) < close < float(rng["upper"])
                if inside:
                    active["confirmation_time"] = bar["open_time"]
                    active["confirmation_time_local"] = local_label(bar["open_time"])
                    _finalize_episode(active, bars[index - int(active["episode_bars"]) + 1:index + 1], m5_by_time)
                    episodes.append(active)
                    if active["status"] in ("SIGNAL", "SIGNAL_UNEXECUTABLE"):
                        signals.append(active)
                    active = None; day_signaled = True
        if active is not None:
            active["status"], active["reason"] = "CANCELLED", "LOCAL_MIDNIGHT"
            episodes.append(active)
        day += timedelta(days=1)
    return ranges, episodes, signals, m5


def write_csv(path, rows):
    fields = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def svg_signal(signal, minute_rows, mode="full"):
    entry = parse_time(signal["planned_entry_time"])
    local_start = entry.astimezone(LOCAL_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    local_end = local_start + timedelta(days=1)
    rows = [r for r in minute_rows if local_start <= parse_time(r["open_time"]) < local_end]
    confirm = parse_time(signal["confirmation_time"])
    if mode == "before":
        rows = [r for r in rows if parse_time(r["open_time"]) <= confirm]
    # Plot one point per M5 bucket using existing minute OHLC; no future rows enter before-view scale.
    m5 = aggregate_m5(rows)
    values = [float(v) for r in m5 for v in (r["high"], r["low"])] + [float(signal["range_upper"]), float(signal["range_lower"]), float(signal["stop"] or signal["entry_open"]), float(signal["target_2r"] or signal["entry_open"])]
    lo, hi = min(values), max(values); pad = max((hi - lo) * .08, 1); lo -= pad; hi += pad
    width, height, left, top, chart_w, chart_h = 1200, 600, 80, 70, 1080, 430
    def x(t): return left + (t - local_start).total_seconds() / 86400 * chart_w
    def y(v): return top + (hi - v) / (hi - lo) * chart_h
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600"><rect width="100%" height="100%" fill="white"/>']
    parts.append('<text x="20" y="28" font-family="Arial" font-size="18" font-weight="bold">Range Reversal V1 · %s · %s · %s</text>' % (signal["local_date"], signal["direction"], "before entry" if mode == "before" else "full context"))
    parts.append('<text x="20" y="50" font-family="Arial" font-size="11">BTCUSDT Binance Spot · timestamps UTC and fixed UTC−04:00 · M5 from complete five-minute buckets</text>')
    parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#fafafa" stroke="#bbb"/>' % (left, top, chart_w, chart_h))
    for value, label, color in ((float(signal["range_upper"]), "range high", "#2563eb"), (float(signal["range_lower"]), "range low", "#2563eb"), (float(signal["stop"] or signal["entry_open"]), "stop", "#dc2626"), (float(signal["target_2r"] or signal["entry_open"]), "target 2R", "#7c3aed")):
        parts.append('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-dasharray="6 4"/>' % (left, y(value), left + chart_w, y(value), color))
        parts.append('<text x="%s" y="%s" fill="%s" font-family="Arial" font-size="10">%s %.2f</text>' % (left + chart_w - 5, y(value) - 4, color, label, value))
    for bar in m5:
        t = parse_time(bar["open_time"]); xp = x(t); color = "#15803d" if float(bar["close"]) >= float(bar["open"]) else "#b91c1c"
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (xp, y(float(bar["high"])), xp, y(float(bar["low"])), color))
        parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3"/>' % (xp, y(float(bar["open"])), xp, y(float(bar["close"])), color))
    for t, label, color in ((parse_time(signal["breakout_time"]), "breakout", "#d97706"), (confirm, "confirmation", "#059669"), (entry, "planned entry", "#111827")):
        if mode == "before" or t <= confirm:
            parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-dasharray="2 3"/>' % (x(t), top, x(t), top + chart_h, color))
            parts.append('<text x="%.1f" y="%d" fill="%s" font-family="Arial" font-size="10">%s</text>' % (x(t) + 3, top - 7, color, label))
    parts.append('<text x="20" y="570" font-family="Arial" font-size="11">%s UTC · %s local | planned entry %s | stop %s | target 2R %s | reason %s</text>' % (signal["planned_entry_time"], signal["planned_entry_time_local"], signal["entry_open"], signal["stop"], signal["target_2r"], signal["reason"] or "SIGNAL"))
    parts.append('</svg>'); return "\n".join(parts)


def build_gallery(signals, minute_rows, output_dir):
    gallery = output_dir / "gallery"; gallery.mkdir(parents=True, exist_ok=True)
    links = []
    for index, signal in enumerate(signals, 1):
        stem = "signal_%03d_%s_%s" % (index, signal["local_date"], signal["direction"].lower())
        before, full = stem + "_before.svg", stem + "_full.svg"
        (gallery / before).write_text(svg_signal(signal, minute_rows, "before"), encoding="utf-8")
        (gallery / full).write_text(svg_signal(signal, minute_rows, "full"), encoding="utf-8")
        links.append((signal, before, full))
    page = ["<!doctype html><meta charset='utf-8'><title>Range Reversal V1 signals</title><style>body{font-family:-apple-system,sans-serif;max-width:1200px;margin:auto}li{margin:12px}img{width:100%;border:1px solid #ddd}</style>", "<h1>Range Reversal V1 · all signals</h1>", "<p>Fixed UTC−04:00 assumption. Long/short are pattern labels; no portfolio execution is simulated.</p>", "<ol>"]
    for signal, before, full in links:
        page.append("<li><b>%s %s</b> — %s UTC / %s<br><a href='gallery/%s'>before entry</a> · <a href='gallery/%s'>full context</a><br><img src='gallery/%s'><img src='gallery/%s'></li>" % (signal["local_date"], signal["direction"], signal["confirmation_time"], signal["confirmation_time_local"], before, full, before, full))
    page.append("</ol>"); (output_dir / "index.html").write_text("\n".join(page), encoding="utf-8")
