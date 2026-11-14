"""Per-trade research execution for corrected Range Reversal delayed entries.

This is a unit-size price-model study, not a portfolio backtest. Short rows are
explicitly hypothetical Spot OHLCV price labels.
"""
import html
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path

from .range_reversal import LOCAL_OFFSET, aggregate_m5, iso, local_label, parse_time

getcontext().prec = 40
ONE = Decimal("1")
COMMISSION = Decimal("0.001")
SLIPPAGE = Decimal("0.0002")


def dec(value):
    return Decimal(str(value))


def read_csv(path):
    import csv
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _fill(side, role, base, level):
    """Return fill after fees model's adverse slippage; target is conservative at T."""
    base, level = dec(base), dec(level)
    if role == "entry":
        return base * (ONE + SLIPPAGE) if side == "LONG" else base * (ONE - SLIPPAGE)
    if role == "stop":
        if side == "LONG":
            return (base if base <= level else level) * (ONE - SLIPPAGE)
        return (base if base >= level else level) * (ONE + SLIPPAGE)
    # Target is always executed conservatively at the target level.
    return level * (ONE - SLIPPAGE) if side == "LONG" else level * (ONE + SLIPPAGE)


def _fees(entry_fill, exit_fill, commission_rate=COMMISSION):
    """Round-trip commission for the supplied scenario rate."""
    rate = dec(commission_rate)
    return entry_fill * rate + exit_fill * rate


def _next_midnight(moment):
    local = moment.astimezone(LOCAL_OFFSET)
    next_local = (local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    return next_local.astimezone(moment.tzinfo)


def simulate_trade(signal, minute_rows, target_mode="FIXED_E1", commission_rate=COMMISSION):
    out = dict(signal)
    out.update({"outcome": "CANCELLED", "outcome_reason": signal.get("delayed_reason", ""), "entry_base": "", "entry_fill": "", "target_used": "", "target_mode": target_mode, "exit_base": "", "exit_fill": "", "exit_time": "", "gross_pnl_per_btc": "", "net_pnl_per_btc": "", "gross_r": "", "net_r": "", "commission_per_btc": "", "slippage_cost_per_btc": "", "ambiguous": "False", "incomplete_data": "False", "planned_2r_from_e1": "2.0", "actual_rr_from_e3": signal.get("actual_rr_from_e3", "")})
    if signal.get("delayed_status") != "ANNOTATION":
        return out
    side = signal["direction"]
    entry_time = parse_time(signal["e3_time"])
    stop, target = dec(signal["stop"]), dec(signal["target_fixed_n1"])
    minute_by_time = {parse_time(r["open_time"]): r for r in minute_rows}
    entry_row = minute_by_time.get(entry_time)
    if entry_row is None:
        out["outcome_reason"], out["incomplete_data"] = "MISSING_ENTRY_MINUTE", "True"
        return out
    entry_base = dec(entry_row["open"]); entry_fill = _fill(side, "entry", entry_base, entry_base)
    if target_mode == "E3_2R":
        target = entry_fill + Decimal("2") * (entry_fill - stop) if side == "LONG" else entry_fill - Decimal("2") * (stop - entry_fill)
    valid = (stop < entry_fill < target) if side == "LONG" else (target < entry_fill < stop)
    out["entry_base"], out["entry_fill"], out["target_used"], out["target_mode"] = str(entry_base), str(entry_fill), str(target), target_mode
    if not valid:
        out["outcome_reason"] = "ENTRY_FILL_ORDER_INVALID"
        return out
    end = _next_midnight(entry_time)
    expected = entry_time
    exit_time = exit_base = exit_fill = None
    reason = None; ambiguous = False
    while expected <= end:
        row = minute_by_time.get(expected)
        if row is None:
            out["outcome"], out["outcome_reason"], out["incomplete_data"] = "INCOMPLETE", "MISSING_DATA_FOR_EXIT", "True"
            return out
        op, hi, lo = dec(row["open"]), dec(row["high"]), dec(row["low"])
        if expected == end:
            reason, exit_time, exit_base = "END_OF_DAY", expected, op
            exit_fill = _fill(side, "stop", op, op)
            break
        open_stop = op <= stop if side == "LONG" else op >= stop
        open_target = op >= target if side == "LONG" else op <= target
        hit_stop = lo <= stop if side == "LONG" else hi >= stop
        hit_target = hi >= target if side == "LONG" else lo <= target
        if hit_stop and hit_target:
            reason, exit_time, exit_base = "STOP", expected, op if open_stop else stop
            exit_fill = _fill(side, "stop", op, stop)
            ambiguous = True
            break
        if open_stop:
            reason, exit_time, exit_base = "STOP", expected, op
            exit_fill = _fill(side, "stop", op, stop)
            ambiguous = bool(open_target or hit_target)
            break
        if open_target:
            reason, exit_time, exit_base = "TARGET", expected, op
            exit_fill = _fill(side, "target", op, target)
            break
        if hit_stop:
            reason, exit_time, exit_base = "STOP", expected, stop
            exit_fill = _fill(side, "stop", op, stop)
            ambiguous = bool(hit_target)
            break
        if hit_target:
            reason, exit_time, exit_base = "TARGET", expected, target
            exit_fill = _fill(side, "target", op, target)
            break
        expected += timedelta(minutes=1)
    if exit_time is None:
        out["outcome"], out["outcome_reason"], out["incomplete_data"] = "INCOMPLETE", "NO_EXIT", "True"
        return out
    gross = exit_fill - entry_fill if side == "LONG" else entry_fill - exit_fill
    fees = _fees(entry_fill, exit_fill, commission_rate)
    net = gross - fees
    risk = abs(entry_fill - stop)
    out.update({"outcome": reason, "outcome_reason": reason, "exit_time": iso(exit_time), "exit_base": str(exit_base), "exit_fill": str(exit_fill), "gross_pnl_per_btc": str(gross), "net_pnl_per_btc": str(net), "gross_r": str(gross / risk) if risk else "", "net_r": str(net / risk) if risk else "", "commission_per_btc": str(fees), "slippage_cost_per_btc": str(abs(entry_fill-entry_base) + (abs(exit_fill-exit_base) if reason != "END_OF_DAY" else abs(exit_fill-exit_base))), "ambiguous": str(ambiguous)})
    return out


def run_variant(rows, minute_rows, target_mode="FIXED_E1", commission_rate=COMMISSION):
    return [simulate_trade(row, minute_rows, target_mode=target_mode, commission_rate=commission_rate) for row in rows]


def metrics(rows):
    checked = [r for r in rows if r["outcome"] in ("TARGET", "STOP", "END_OF_DAY", "INCOMPLETE")]
    completed = [r for r in checked if r["outcome"] != "INCOMPLETE"]
    nets = [dec(r["net_pnl_per_btc"]) for r in completed]
    positives = [x for x in nets if x > 0]; negatives = [x for x in nets if x < 0]
    gross_values = [dec(r["gross_pnl_per_btc"]) for r in completed]
    return {"rows": len(rows), "checked_trades": len(checked), "cancelled": sum(r["outcome"] == "CANCELLED" for r in rows), "incomplete": sum(r["outcome"] == "INCOMPLETE" for r in rows), "ambiguous": sum(r["ambiguous"] == "True" for r in rows), "target": sum(r["outcome"] == "TARGET" for r in rows), "stop": sum(r["outcome"] == "STOP" for r in rows), "end_of_day": sum(r["outcome"] == "END_OF_DAY" for r in rows), "net_pnl_per_btc": str(sum(nets, Decimal("0"))), "mean_net_pnl_per_btc": str(sum(nets, Decimal("0")) / Decimal(len(nets))) if nets else "", "gross_pnl_per_btc": str(sum(gross_values, Decimal("0"))), "mean_gross_pnl_per_btc": str(sum(gross_values, Decimal("0")) / Decimal(len(gross_values))) if gross_values else "", "mean_gross_r": str(sum((dec(r["gross_r"]) for r in completed), Decimal("0")) / Decimal(len(completed))) if completed else "", "mean_net_r": str(sum((dec(r["net_r"]) for r in completed), Decimal("0")) / Decimal(len(completed))) if completed else "", "win_rate_net": str(Decimal(len(positives)) / Decimal(len(completed))) if completed else "", "profit_factor_net": str(sum(positives, Decimal("0")) / abs(sum(negatives, Decimal("0")))) if negatives else "", "commission_per_btc": str(sum((dec(r["commission_per_btc"]) for r in completed), Decimal("0"))), "slippage_cost_per_btc": str(sum((dec(r["slippage_cost_per_btc"]) for r in completed), Decimal("0")))}


def svg_trade(row, minute_rows):
    entry = parse_time(row["e3_time"]); local_start = entry.astimezone(LOCAL_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(entry.tzinfo); end = _next_midnight(entry)
    rs = [r for r in minute_rows if local_start <= parse_time(r["open_time"]) <= end]
    values = [dec(v) for r in rs for v in (r["high"], r["low"])]; values += [dec(row["stop"]), dec(row.get("target_used") or row["target_fixed_n1"]), dec(row["entry_fill"])]
    lo, hi = min(values), max(values); pad = max((hi-lo)*Decimal("0.08"), Decimal("1")); lo-=pad; hi+=pad
    left, top, width, height = 90, 90, 1240, 420
    x=lambda t: left+(t-local_start).total_seconds()/86400*width; y=lambda v: top+float((hi-dec(v))/(hi-lo))*height
    p=['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="650"><rect width="100%" height="100%" fill="white"/>', '<text x="20" y="28" font-family="Arial" font-size="18" font-weight="bold">Delayed trade · %s · %s · %s</text>'%(row["local_date"],row["direction"],row["outcome"]), '<text x="20" y="50" font-family="Arial" font-size="11">BTCUSDT Spot OHLCV price model · UTC / UTC−04:00 · short is hypothetical</text>', '<rect x="%d" y="%d" width="%d" height="%d" fill="#fafafa" stroke="#bbb"/>'%(left,top,width,height)]
    target_label = "T E3 2R" if row.get("target_mode") == "E3_2R" else "T fixed E1"
    for val,label,color in ((row["stop"],"S","#dc2626"),(row.get("target_used") or row["target_fixed_n1"],target_label,"#7c3aed"),(row["entry_fill"],"entry fill","#111827")):
        p += ['<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-dasharray="6 4"/>'%(left,y(val),left+width,y(val),color), '<text x="%s" y="%s" fill="%s" font-family="Arial" font-size="11">%s %.2f</text>'%(left+width-110,y(val)-4,color,label,float(dec(val)))]
    for r in rs:
        xp=x(parse_time(r["open_time"])); c="#15803d" if dec(r["close"])>=dec(r["open"]) else "#b91c1c"; p += ['<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s"/>'%(xp,y(r["high"]),xp,y(r["low"]),c), '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2"/>'%(xp,y(r["open"]),xp,y(r["close"]),c)]
    p += ['<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#111827" stroke-dasharray="2 3"/>'%(x(entry),top,x(entry),top+height), '<text x="%.1f" y="%d" font-family="Arial" font-size="11">E3</text>'%(x(entry)+4,top-8), '<text x="20" y="565" font-family="Arial" font-size="11">entry %.2f · exit %s %.2f · gross %.2f · net %.2f · reason %s%s</text>'%(float(dec(row["entry_fill"])),row.get("exit_time",""),float(dec(row["exit_fill"] or "0")),float(dec(row["gross_pnl_per_btc"] or "0")),float(dec(row["net_pnl_per_btc"] or "0")),row["outcome_reason"]," · ambiguous" if row["ambiguous"] == "True" else ""), '</svg>']
    return "\n".join(p)


def build_gallery(rows, minute_rows, out):
    gallery=Path(out)/"gallery"; gallery.mkdir(parents=True,exist_ok=True); links=[]
    for i,row in enumerate([r for r in rows if r["outcome"] != "CANCELLED"],1):
        stem="trade_%03d_%s_%s"%(i,row["local_date"],row["direction"].lower()); name=stem+".svg"; (gallery/name).write_text(svg_trade(row,minute_rows),encoding="utf-8"); links.append((row,name))
    page=["<!doctype html><meta charset='utf-8'><title>Delayed trade outcomes</title><style>body{font-family:-apple-system,sans-serif;max-width:1450px;margin:auto}img{width:100%;border:1px solid #ddd}li{margin:20px}</style>","<h1>Corrected delayed-entry trade outcomes</h1><p>Only entries that passed E3 checks are shown; short results are a hypothetical Spot OHLCV price model.</p><ol>"]
    for r,n in links: page.append("<li><b>%s %s %s</b> — E3 %s, exit %s, net %.2f per BTC%s<br><img src='gallery/%s'></li>"%(r["local_date"],r["direction"],r["outcome"],r["e3_time"],r.get("exit_time",""),float(dec(r["net_pnl_per_btc"] or "0"))," · ambiguous" if r["ambiguous"] == "True" else "",n))
    page.append("</ol>"); (Path(out)/"index.html").write_text("\n".join(page),encoding="utf-8")
