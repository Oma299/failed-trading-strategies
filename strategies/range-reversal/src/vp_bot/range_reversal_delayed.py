"""Delayed-entry / fixed-N1-target annotations for Range Reversal V2-N3.

This module is deliberately an annotation only.  It does not simulate a portfolio.
The two stop definitions are kept in separate rows and outputs.
"""
import html
from datetime import timedelta
from pathlib import Path

from .range_reversal import LOCAL_OFFSET, aggregate_m5, iso, local_label, parse_time


def _episode_bars(signal, m5, first_return_time=None):
    b = parse_time(signal["breakout_time"])
    c1 = parse_time(first_return_time or signal["confirmation_1_time"])
    return [x for x in m5 if b <= parse_time(x["open_time"]) <= c1]


def initial_first_return(signal, m5):
    """Return the first inside close after breakout, before any N3 reset."""
    b = parse_time(signal["breakout_time"])
    end = parse_time(signal["confirmation_3_time"])
    bars = [x for x in m5 if b <= parse_time(x["open_time"]) <= end]
    previous = None
    for row in bars:
        moment = parse_time(row["open_time"])
        if previous is not None and moment != previous + timedelta(minutes=5):
            return None, "MISSING_M5"
        previous = moment
        if row.get("complete") != "True":
            return None, "MISSING_M5"
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        if (signal["direction"] == "SHORT" and low <= float(signal["range_lower"])) or (signal["direction"] == "LONG" and high >= float(signal["range_upper"])):
            return None, "BOTH_SIDES"
        if float(signal["range_lower"]) < close < float(signal["range_upper"]):
            return row["open_time"], ""
    return None, "NO_INITIAL_FIRST_RETURN"


def _extreme_stop(signal, bars):
    direction = signal["direction"]
    value = max(float(x["high"]) for x in bars) if direction == "SHORT" else min(float(x["low"]) for x in bars)
    candidates = [x for x in bars if (float(x["high"]) == value if direction == "SHORT" else float(x["low"]) == value)]
    source = candidates[0]
    return value, source["open_time"], bars[-1]["close_time"], "breakout_through_first_return"


def local_pivot_stop(signal, m5):
    bars = _episode_bars(signal, m5)
    # A pivot needs two completed bars on each side, all known by first return.
    found = []
    for i in range(2, len(bars) - 2):
        center = bars[i]
        left, right = bars[i - 2:i], bars[i + 1:i + 3]
        if signal["direction"] == "SHORT":
            h = float(center["high"])
            if all(h > float(x["high"]) for x in left + right):
                found.append((i, h, center, right[-1]))
        else:
            lo = float(center["low"])
            if all(lo < float(x["low"]) for x in left + right):
                found.append((i, lo, center, right[-1]))
    if not found:
        return None
    _, value, center, known = found[-1]
    return value, center["open_time"], known["close_time"], "local_pivot_2x2"


def _base(signal, variant, stop_info):
    out = dict(signal)
    out.update({"stop_variant": variant, "stop": "", "stop_source_time": "", "stop_known_at": "",
                "current_v2_n3_stop": signal.get("stop", ""), "current_v2_n3_stop_known_at": signal.get("confirmation_3_time", ""),
                "stop_rule": "", "e1_time": "", "e1_time_local": "", "e1_open": "",
                "e3_time": "", "e3_time_local": "", "e3_open": "", "target_fixed_n1": "",
                "actual_rr_from_e3": "", "delayed_status": "CANCELLED", "delayed_reason": ""})
    if stop_info:
        out["stop"], out["stop_source_time"], out["stop_known_at"], out["stop_rule"] = stop_info
    return out


def annotate_signal(signal, minute_rows, m5, variant):
    first_return, initial_reason = initial_first_return(signal, m5)
    c3 = parse_time(signal["confirmation_3_time"])
    if first_return is None:
        out = _base(signal, variant, None)
        out["delayed_reason"] = initial_reason
        return out
    initial = dict(signal)
    initial["confirmation_1_time"] = first_return
    stop_info = _extreme_stop(initial, _episode_bars(initial, m5, first_return)) if variant == "BREAKOUT_EXTREMUM_FIRST_RETURN" else local_pivot_stop(initial, m5)
    out = _base(signal, variant, stop_info)
    out["initial_first_return_time"] = first_return
    out["initial_first_return_time_local"] = local_label(first_return)
    if not stop_info:
        out["delayed_reason"] = "NO_LOCAL_PIVOT"
        return out
    c1 = parse_time(first_return)
    e1, e3 = c1 + timedelta(minutes=5), c3 + timedelta(minutes=5)
    out["e1_time"], out["e1_time_local"] = iso(e1), local_label(iso(e1))
    out["e3_time"], out["e3_time_local"] = iso(e3), local_label(iso(e3))
    m5by = {parse_time(x["open_time"]): x for x in m5}
    e1bar, e3bar = m5by.get(e1), m5by.get(e3)
    if e1bar is None or e3bar is None or e1bar.get("complete") != "True" or e3bar.get("complete") != "True":
        out["delayed_reason"] = "MISSING_E1_OR_E3_M5"; return out
    e1o, stop = float(e1bar["open"]), float(out["stop"])
    target = e1o - 2 * (stop - e1o) if signal["direction"] == "SHORT" else e1o + 2 * (e1o - stop)
    out["e1_open"], out["target_fixed_n1"] = e1bar["open"], str(target)
    # Minute data from E1 onward and strictly before E3: no lookahead past entry.
    pre = [r for r in minute_rows if e1 <= parse_time(r["open_time"]) < e3]
    for r in pre:
        hi, lo = float(r["high"]), float(r["low"])
        hit_s = hi >= stop if signal["direction"] == "SHORT" else lo <= stop
        hit_t = lo <= target if signal["direction"] == "SHORT" else hi >= target
        if hit_s and hit_t: out["delayed_reason"] = "PRE_ENTRY_BOTH_LEVELS"; return out
        if hit_s: out["delayed_reason"] = "PRE_ENTRY_STOP"; return out
        if hit_t: out["delayed_reason"] = "PRE_ENTRY_TARGET"; return out
    out["e3_open"] = e3bar["open"]
    eo = float(out["e3_open"])
    valid = (stop < eo < target) if signal["direction"] == "LONG" else (target < eo < stop)
    if not valid:
        out["delayed_reason"] = "E3_OPEN_ORDER_INVALID"; return out
    rr = (target - eo) / (eo - stop) if signal["direction"] == "LONG" else (eo - target) / (stop - eo)
    out["actual_rr_from_e3"], out["delayed_status"], out["delayed_reason"] = str(rr), "ANNOTATION", ""
    return out


def annotate(signals, minute_rows):
    m5 = aggregate_m5(minute_rows)
    rows = {"BREAKOUT_EXTREMUM_FIRST_RETURN": [], "LOCAL_PIVOT_2X2": []}
    for s in signals:
        for variant in rows:
            rows[variant].append(annotate_signal(s, minute_rows, m5, variant))
    return rows, m5


def svg_signal(row, minute_rows, mode="full"):
    e1 = parse_time(row["e1_time"] or row["confirmation_1_time"])
    local_start = e1.astimezone(LOCAL_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(e1.tzinfo)
    local_end = local_start + timedelta(days=1)
    rs = [r for r in minute_rows if local_start <= parse_time(r["open_time"]) < local_end]
    if mode == "before": rs = [r for r in rs if parse_time(r["open_time"]) < e1]
    bars = aggregate_m5(rs)
    vals = [float(x) for b in bars for x in (b["high"], b["low"]) ]
    keys = ("range_upper", "range_lower", "stop", "target_fixed_n1", "e1_open")
    if mode == "full": keys = keys + ("e3_open",)
    for key in keys:
        if row.get(key): vals.append(float(row[key]))
    lo, hi = min(vals), max(vals); pad = max((hi-lo)*.08, 1); lo -= pad; hi += pad
    left, top, w, h = 90, 90, 1240, 420
    x = lambda t: left + (t-local_start).total_seconds()/86400*w
    y = lambda v: top + (hi-v)/(hi-lo)*h
    p = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="650"><rect width="100%" height="100%" fill="white"/>', '<text x="20" y="28" font-family="Arial" font-size="18" font-weight="bold">Delayed entry · %s · %s · %s</text>' % (row["local_date"], row["direction"], mode), '<text x="20" y="50" font-family="Arial" font-size="11">V2-N3 annotation · fixed N1 target from E1 · UTC / UTC−04:00</text>', '<rect x="%d" y="%d" width="%d" height="%d" fill="#fafafa" stroke="#bbb"/>' % (left,top,w,h)]
    for k, label, color in (("range_upper","range high","#2563eb"),("range_lower","range low","#2563eb"),("stop","S","#dc2626"),("target_fixed_n1","T fixed N1","#7c3aed")):
        if row.get(k):
            p += ['<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-dasharray="6 4"/>'%(left,y(float(row[k])),left+w,y(float(row[k])),color), '<text x="%s" y="%s" fill="%s" font-family="Arial" font-size="11">%s %.2f</text>'%(left+w-100,y(float(row[k]))-4,color,label,float(row[k]))]
    for b in bars:
        xp=x(parse_time(b["open_time"])); c="#15803d" if float(b["close"])>=float(b["open"]) else "#b91c1c"
        p += ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'%(xp,y(float(b["high"])),xp,y(float(b["low"])),c), '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="3"/>'%(xp,y(float(b["open"])),xp,y(float(b["close"])),c)]
    events = [(row["breakout_time"],"breakout"),(row["confirmation_1_time"],"C1"),(row["confirmation_2_time"],"C2"),(row["confirmation_3_time"],"C3"),(row["e1_time"],"E1"),(row["e3_time"],"E3")]
    for event_index, (tv, lab) in enumerate(events):
        if not tv: continue
        t=parse_time(tv)
        if mode == "before" and t >= e1: continue
        label_y = top - 8 - (event_index % 3) * 14
        p += ['<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#059669" stroke-dasharray="2 3"/>'%(x(t),top,x(t),top+h), '<text x="%.1f" y="%d" fill="#111827" font-family="Arial" font-size="11">%s</text>'%(x(t)+3,label_y,lab)]
    fmt = lambda value: ("%.2f" % float(value)) if value not in (None, "") else ""
    p += ['<text x="20" y="565" font-family="Arial" font-size="11">E1 %s open=%s · E3 %s open=%s · S=%s · T=%s · RR(E3)=%s · %s</text>'%(row.get("e1_time",""),fmt(row.get("e1_open")),row.get("e3_time",""),fmt(row.get("e3_open")),fmt(row.get("stop")),fmt(row.get("target_fixed_n1")),fmt(row.get("actual_rr_from_e3")),row.get("delayed_reason") or "ANNOTATION"), '</svg>']
    return "\n".join(p)


def build_gallery(rows, minute_rows, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True); gallery=output_dir/"gallery"; gallery.mkdir(exist_ok=True)
    links=[]
    for i,row in enumerate(rows,1):
        stem="signal_%03d_%s_%s"%(i,row["local_date"],row["direction"].lower()); b=stem+"_before.svg"; f=stem+"_full.svg"
        (gallery/b).write_text(svg_signal(row,minute_rows,"before"),encoding="utf-8"); (gallery/f).write_text(svg_signal(row,minute_rows,"full"),encoding="utf-8"); links.append((row,b,f))
    page=["<!doctype html><meta charset='utf-8'><title>Delayed entry</title><style>body{font-family:-apple-system,sans-serif;max-width:1450px;margin:auto}img{width:100%;border:1px solid #ddd}li{margin:20px}</style>","<h1>Delayed entry / fixed-N1 target</h1><p>All V2-N3 candidates; before view excludes data at and after E1.</p><ol>"]
    fmt = lambda value: ("%.2f" % float(value)) if value not in (None, "") else ""
    for r,b,f in links: page.append("<li><b>%s %s</b> — E1 %s, E3 %s, S %s, T %s, %s<br><a href='gallery/%s'>before</a> · <a href='gallery/%s'>full</a><br><img src='gallery/%s'><img src='gallery/%s'></li>"%(r["local_date"],r["direction"],r.get("e1_time",""),r.get("e3_time",""),fmt(r.get("stop")),fmt(r.get("target_fixed_n1")),r.get("delayed_reason") or "ANNOTATION",b,f,b,f))
    page.append("</ol>"); (output_dir/"index.html").write_text("\n".join(page),encoding="utf-8")
