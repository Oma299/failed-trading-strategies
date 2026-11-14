"""Range Reversal V2: mandatory M5 close outside, N1/N3 confirmation."""

import csv
import html
from datetime import date, datetime, timedelta
from pathlib import Path

from .range_reversal import (LOCAL_OFFSET, _minutes_by_time, _range_for_day,
                             aggregate_m5, iso, local_label, parse_time)


def _base(day, rng, direction, first):
    return {"local_date": day.isoformat(), "direction": direction, "range_upper": rng["upper"], "range_lower": rng["lower"],
            "breakout_time": first["open_time"], "breakout_time_local": local_label(first["open_time"]),
            "confirmation_1_time": "", "confirmation_1_time_local": "", "confirmation_2_time": "", "confirmation_2_time_local": "", "confirmation_3_time": "", "confirmation_3_time_local": "",
            "confirmation_time": "", "confirmation_time_local": "", "planned_entry_time": "", "planned_entry_time_local": "", "entry_open": "", "stop": "", "target_2r": "", "status": "WAITING_CONFIRMATION", "reason": "", "episode_bars": "0", "confirmation_count": "0"}


def _finalize(ep, episode_bars, next_by_time, day_end):
    confirm = parse_time(ep["confirmation_time"])
    entry_time = confirm + timedelta(minutes=5)
    ep["planned_entry_time"], ep["planned_entry_time_local"] = iso(entry_time), local_label(iso(entry_time))
    if entry_time >= day_end:
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "NEXT_LOCAL_DAY_ENTRY_FORBIDDEN"
        return
    entry = next_by_time.get(entry_time)
    if entry is None or entry.get("complete") != "True":
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "MISSING_ENTRY_M5"
        return
    ep["entry_open"] = entry["open"]
    if not (float(ep["range_lower"]) < float(entry["open"]) < float(ep["range_upper"])):
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "ENTRY_OPEN_OUTSIDE_RANGE"
        return
    if ep["direction"] == "SHORT":
        stop = max(float(row["high"]) for row in episode_bars)
        distance = stop - float(entry["open"])
        target = float(entry["open"]) - 2 * distance
    else:
        stop = min(float(row["low"]) for row in episode_bars)
        distance = float(entry["open"]) - stop
        target = float(entry["open"]) + 2 * distance
    ep["stop"], ep["target_2r"] = str(stop), str(target)
    if distance <= 0:
        ep["status"], ep["reason"] = "SIGNAL_UNEXECUTABLE", "NONPOSITIVE_STOP_DISTANCE"
    else:
        ep["status"], ep["reason"] = "SIGNAL", ""


def detect_v2(rows, confirmation_mode="N1", start_day=date(2025, 1, 1), end_day=date(2025, 3, 31)):
    if confirmation_mode not in ("N1", "N3"):
        raise ValueError("confirmation_mode must be N1 or N3")
    rows = sorted(rows, key=lambda row: row["open_time"])
    minute_by_time = _minutes_by_time(rows)
    m5 = aggregate_m5(rows)
    by_time = {parse_time(row["open_time"]): row for row in m5}
    ranges, episodes, signals = [], [], []
    day = start_day
    while day <= end_day:
        rng = _range_for_day(day, minute_by_time); ranges.append(rng)
        if rng["complete"] != "True":
            day += timedelta(days=1); continue
        range_end = parse_time(rng["range_end_utc"])
        day_end = (datetime(day.year, day.month, day.day, tzinfo=LOCAL_OFFSET) + timedelta(days=1)).astimezone(LOCAL_OFFSET).astimezone(range_end.tzinfo)
        bars = [row for row in m5 if range_end <= parse_time(row["open_time"]) < day_end]
        active = None; day_signaled = False; previous = None
        for index, bar in enumerate(bars):
            moment = parse_time(bar["open_time"])
            if previous is not None and moment > previous + timedelta(minutes=5) and active is not None:
                active["status"], active["reason"] = "CANCELLED", "MISSING_M5"; episodes.append(active); active = None
            if bar.get("complete") != "True":
                if active is not None:
                    active["status"], active["reason"] = "CANCELLED", "MISSING_M5"; episodes.append(active); active = None
                previous = moment; continue
            high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
            up_close, down_close = close > float(rng["upper"]), close < float(rng["lower"])
            up_touch, down_touch = high >= float(rng["upper"]), low <= float(rng["lower"])
            if active is None and not day_signaled:
                # A V2 breakout requires the close outside. A single bar cannot both launch and confirm.
                if up_close and down_close:
                    episodes.append({**_base(day, rng, "BOTH_SIDES", bar), "status": "CANCELLED", "reason": "BOTH_SIDES", "episode_bars": "1"})
                elif up_close:
                    active = _base(day, rng, "SHORT", bar)
                elif down_close:
                    active = _base(day, rng, "LONG", bar)
            elif active is not None:
                active["episode_bars"] = str(int(active["episode_bars"]) + 1)
                # Opposite boundary touch/cross cancels before entry, including confirmation candidates.
                if (active["direction"] == "SHORT" and down_touch) or (active["direction"] == "LONG" and up_touch):
                    active["status"], active["reason"] = "CANCELLED", "BOTH_SIDES"; episodes.append(active); active = None; previous = moment; continue
                inside = float(rng["lower"]) < close < float(rng["upper"])
                if inside:
                    count = int(active["confirmation_count"]) + 1
                    active["confirmation_count"] = str(count)
                    slot = "confirmation_%d_time" % count
                    if count <= 3:
                        active[slot] = bar["open_time"]; active[slot.replace("_time", "_time_local")] = local_label(bar["open_time"])
                    needed = 1 if confirmation_mode == "N1" else 3
                    if count >= needed:
                        active["confirmation_time"] = bar["open_time"]; active["confirmation_time_local"] = local_label(bar["open_time"])
                        start = index - int(active["episode_bars"]) + 1
                        _finalize(active, bars[start:index + 1], by_time, day_end)
                        episodes.append(active)
                        if active["status"] in ("SIGNAL", "SIGNAL_UNEXECUTABLE"): signals.append(active)
                        active = None; day_signaled = True
                else:
                    # Close outside the original breakout boundary or on either boundary resets N3 count.
                    active["confirmation_count"] = "0"
            previous = moment
        if active is not None:
            active["status"], active["reason"] = "CANCELLED", "LOCAL_MIDNIGHT"; episodes.append(active)
        day += timedelta(days=1)
    return ranges, episodes, signals, m5


def write_csv(path, rows):
    fields = sorted({key for row in rows for key in row}) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def svg_signal(signal, minute_rows, mode="full"):
    entry = parse_time(signal["planned_entry_time"])
    local_start = entry.astimezone(LOCAL_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(entry.tzinfo)
    local_end = local_start + timedelta(days=1)
    rows = [r for r in minute_rows if local_start <= parse_time(r["open_time"]) < local_end]
    confirmation = parse_time(signal["confirmation_time"])
    if mode == "before": rows = [r for r in rows if parse_time(r["open_time"]) <= confirmation]
    bars = aggregate_m5(rows)
    values = [float(v) for r in bars for v in (r["high"], r["low"])] + [float(signal["range_upper"]), float(signal["range_lower"]), float(signal["stop"] or signal["entry_open"]), float(signal["target_2r"] or signal["entry_open"])]
    low, high = min(values), max(values); pad = max((high-low)*.08, 1); low -= pad; high += pad
    left, top, width, chart_h = 90, 90, 1240, 430
    def x(t): return left + (t-local_start).total_seconds()/86400*width
    def y(v): return top + (high-v)/(high-low)*chart_h
    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="620"><rect width="100%" height="100%" fill="white"/>', '<text x="20" y="28" font-family="Arial" font-size="18" font-weight="bold">Range Reversal V2 · %s · %s · %s</text>' % (signal["local_date"], signal["direction"], mode), '<text x="20" y="51" font-family="Arial" font-size="11">UTC and fixed UTC−04:00 · range H4 + complete M5 · confirmation candles are numbered 1–3</text>', '<rect x="%d" y="%d" width="%d" height="%d" fill="#fafafa" stroke="#bbb"/>' % (left, top, width, chart_h)]
    for value, label, color in ((float(signal["range_upper"]), "range high", "#2563eb"), (float(signal["range_lower"]), "range low", "#2563eb"), (float(signal["stop"] or signal["entry_open"]), "stop", "#dc2626"), (float(signal["target_2r"] or signal["entry_open"]), "target 2R", "#7c3aed")):
        p += ['<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-dasharray="6 4"/>' % (left, y(value), left+width, y(value), color), '<text x="%s" y="%s" text-anchor="end" fill="%s" font-family="Arial" font-size="11">%s %.2f</text>' % (left+width-4, y(value)-4, color, label, value)]
    for bar in bars:
        t, xp = parse_time(bar["open_time"]), None
        xp = x(t); color = "#15803d" if float(bar["close"]) >= float(bar["open"]) else "#b91c1c"
        p += ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>' % (xp,y(float(bar["high"])),xp,y(float(bar["low"])),color), '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3"/>' % (xp,y(float(bar["open"])),xp,y(float(bar["close"])),color)]
    events = [(parse_time(signal["breakout_time"]), "breakout", "#d97706"), (entry, "planned entry", "#111827")]
    for number in (1, 2, 3):
        value = signal.get("confirmation_%d_time" % number, "")
        if value:
            events.insert(1 + number - 1, (parse_time(value), "confirm %d" % number, "#059669"))
    events.sort(key=lambda item: item[0])
    for t, label, color in events:
        if t and (mode == "before" or t <= confirmation):
            p += ['<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-dasharray="2 3"/>' % (x(t), top, x(t), top+chart_h, color), '<text x="%.1f" y="%d" fill="%s" font-family="Arial" font-size="11">%s</text>' % (x(t)+4, top-8, color, label)]
    p += ['<text x="20" y="570" font-family="Arial" font-size="11">breakout %s / confirmation %s / entry %s · stop %s · target 2R %s · reason %s</text>' % (signal["breakout_time"], signal["confirmation_time"], signal["planned_entry_time"], signal["stop"], signal["target_2r"], signal["reason"] or "SIGNAL"), '</svg>']
    return "\n".join(p)


def build_gallery(signals, minute_rows, output_dir, mode_name):
    gallery = output_dir / "gallery"; gallery.mkdir(parents=True, exist_ok=True); links = []
    for i, signal in enumerate(signals, 1):
        stem = "signal_%03d_%s_%s" % (i, signal["local_date"], signal["direction"].lower())
        before, full = stem+"_before.svg", stem+"_full.svg"
        (gallery/before).write_text(svg_signal(signal, minute_rows, "before"), encoding="utf-8")
        (gallery/full).write_text(svg_signal(signal, minute_rows, "full"), encoding="utf-8")
        links.append((signal,before,full))
    page = ["<!doctype html><meta charset='utf-8'><title>Range Reversal V2 %s</title><style>body{font-family:-apple-system,sans-serif;max-width:1400px;margin:auto}li{margin:15px}img{width:100%%;border:1px solid #ddd}</style>" % mode_name, "<h1>Range Reversal V2 · %s</h1><p>Mandatory close outside; confirmation mode %s. Fixed UTC−04:00. Short is pattern labeling only.</p><ol>" % (mode_name, mode_name)]
    for signal,before,full in links:
        page.append("<li><b>%s %s</b> — breakout %s, confirmation %s, entry %s<br><a href='gallery/%s'>before entry</a> · <a href='gallery/%s'>full context</a><br><img src='gallery/%s'><img src='gallery/%s'></li>" % (signal["local_date"], signal["direction"], signal["breakout_time"], signal["confirmation_time"], signal["planned_entry_time"], before, full, before, full))
    page.append("</ol>"); (output_dir/"index.html").write_text("\n".join(page), encoding="utf-8")
