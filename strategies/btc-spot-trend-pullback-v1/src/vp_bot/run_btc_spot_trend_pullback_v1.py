"""First-stage research runner for BTC_SPOT_TREND_PULLBACK_V1."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .btc_spot_trend_pullback_v1 import (
    D, SCENARIOS, Filters, aggregate_h1, aggregate_h4, ema_h4_regime,
    ZERO, iso, parse_time, prepare_segment, read_csv, run_segment, scenario_metrics,
    sha256, split_continuous_minutes, write_csv, _buy_price, _sell_price,
    floor_step,
)

UTC = timezone.utc
CUTOFF = datetime(2025, 7, 1, tzinfo=UTC)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _mfe_mae(trade, minutes, minute_times=None):
    if trade.get("status") != "CLOSED" or not trade.get("entry_time") or not trade.get("exit_time"):
        return trade
    entry = parse_time(trade["entry_time"]); exit_time = parse_time(trade["exit_time"]); fill = D(trade["entry_fill"])
    minute_times = minute_times or [parse_time(r["open_time"]) for r in minutes]
    window = minutes[bisect_left(minute_times, entry):bisect_right(minute_times, exit_time)]
    highs = [D(r["high"]) for r in window]
    lows = [D(r["low"]) for r in window]
    trade["mfe_price"] = str(max(highs) - fill) if highs else ""
    trade["mae_price"] = str(fill - min(lows)) if lows else ""
    return trade


def _svg_episode(index, signal, trade, h1, rsi, regime, mode):
    signal_time = parse_time(signal["signal_time"]); end_time = signal_time + timedelta(hours=1)
    if mode == "full":
        if trade and trade.get("exit_time"):
            end_time = parse_time(trade["exit_time"]) + timedelta(hours=12)
        else:
            end_time = signal_time + timedelta(hours=48)
    start_time = signal_time - timedelta(hours=24)
    bars = [b for b in h1 if start_time <= parse_time(b["open_time"]) < end_time]
    if not bars:
        bars = h1[-80:]
    values = [D(b["high"]) for b in bars] + [D(b["low"]) for b in bars]
    for key in ("signal_close", "stop", "entry_base", "exit_base"):
        if signal.get(key): values.append(D(signal[key]))
        if trade and trade.get(key): values.append(D(trade[key]))
    lo, hi = min(values), max(values); pad = max((hi - lo) * D("0.08"), D("1")); lo -= pad; hi += pad
    width, height, left, top, chart_h = 1500, 820, 70, 50, 500
    step = max(D("1"), D(width - left - 30) / D(max(len(bars), 1))); candle_w = max(D("2"), step * D("0.6"))
    def y(price): return float(top + (hi - D(price)) / (hi - lo) * D(chart_h))
    def x(i): return float(left + D(i) * step + step / D("2"))
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}'><style>text{{font-family:Arial,sans-serif;font-size:14px}}.grid{{stroke:#e5e7eb}}.up{{stroke:#15803d;fill:#86efac}}.down{{stroke:#b91c1c;fill:#fca5a5}}.level{{stroke:#2563eb;stroke-dasharray:7 5}}.stop{{stroke:#dc2626;stroke-dasharray:5 4}}.entry{{stroke:#16a34a;stroke-width:2}}.exit{{stroke:#7c3aed;stroke-width:2}}</style><rect width='100%' height='100%' fill='white'/><text x='70' y='25' font-size='20'>{html.escape(f'BTC_SPOT_TREND_PULLBACK_V1 episode {index:03d} — {mode.upper()}')}</text>"]
    for j in range(6):
        yy = top + j * chart_h / 5; parts.append(f"<line class='grid' x1='{left}' x2='{width-30}' y1='{yy}' y2='{yy}'/><text x='5' y='{yy+5}'>{hi - (hi-lo)*D(j)/D(5):.2f}</text>")
    for i, bar in enumerate(bars):
        xx = x(i); op, cl, high, low = (D(bar[k]) for k in ("open", "close", "high", "low")); color = "up" if cl >= op else "down"; y1, y2 = y(op), y(cl)
        parts.append(f"<line class='{color}' x1='{xx}' x2='{xx}' y1='{y(high)}' y2='{y(low)}'/><rect class='{color}' x='{xx-float(candle_w)/2}' y='{min(y1,y2)}' width='{float(candle_w)}' height='{max(1,abs(y2-y1))}'/>")
    def level(key, cls, label, source):
        value = source.get(key) if source else None
        if value: parts.append(f"<line class='{cls}' x1='{left}' x2='{width-30}' y1='{y(value)}' y2='{y(value)}'/><text x='{width-330}' y='{y(value)-5}'>{label} {D(value):.2f}</text>")
    level("signal_close", "level", "signal close", signal); level("stop", "stop", "stop", trade or signal); level("entry_base", "entry", "entry", trade or signal); level("exit_base", "exit", "exit", trade or signal)
    if trade and trade.get("entry_time"):
        entry_i = next((i for i,b in enumerate(bars) if parse_time(b["open_time"]) <= parse_time(trade["entry_time"]) < parse_time(b["open_time"]) + timedelta(hours=1)), None)
        if entry_i is not None: parts.append(f"<circle cx='{x(entry_i)}' cy='{y(trade['entry_base'])}' r='6' fill='#16a34a'/>")
    rsi_top = 625; parts.append(f"<line class='grid' x1='{left}' x2='{width-30}' y1='{rsi_top}' y2='{rsi_top}'/><text x='5' y='{rsi_top+5}'>RSI3</text><line x1='{left}' x2='{width-30}' y1='{rsi_top+50}' y2='{rsi_top+50}' stroke='#f59e0b' stroke-dasharray='4 4'/><text x='5' y='{rsi_top+55}'>20</text><line x1='{left}' x2='{width-30}' y1='{rsi_top}' y2='{rsi_top}' stroke='#f59e0b' stroke-dasharray='4 4'/><text x='5' y='{rsi_top+15}'>60</text>")
    pts=[]
    for i, bar in enumerate(bars):
        pos = next((j for j,b in enumerate(h1) if b["open_time"] == bar["open_time"]), None)
        value = rsi[pos] if pos is not None and pos < len(rsi) else None
        if value is not None: pts.append(f"{x(i)},{rsi_top + 100 - float(value)}")
    if pts: parts.append(f"<polyline points='{' '.join(pts)}' fill='none' stroke='#f59e0b'/>")
    status = signal.get("status", ""); reason = trade.get("exit_reason", "") if trade else signal.get("cancel_reason", "")
    regime_text = "H4 regime: " + str(signal.get("regime", ""))
    details = [regime_text, f"signal {signal.get('signal_time','')} close={signal.get('signal_close','')}", f"entry {trade.get('entry_time','')} fill={trade.get('entry_fill','')}" if trade else "entry not executed", f"exit {trade.get('exit_time','')} fill={trade.get('exit_fill','')} reason={reason}" if trade else f"status={status} reason={reason}", f"net PnL={trade.get('net_pnl_usdt','')} USDT trade_R={trade.get('trade_R','')}" if trade else ""]
    for j, text in enumerate(details): parts.append(f"<text x='70' y='{700+j*22}'>{html.escape(text)}</text>")
    return "".join(parts) + "</svg>"


def build_gallery(result, minutes, out):
    h1 = [r for r in aggregate_h1(minutes) if r["complete"]]; rsi = __import__("vp_bot.btc_spot_trend_pullback_v1", fromlist=["rsi_wilder"]).rsi_wilder(h1)
    out = Path(out); gallery = out / "gallery"; gallery.mkdir(parents=True, exist_ok=True); cards=[]
    trades_by_signal = {t.get("signal_time"): t for t in result["trades"]}
    for index, signal in enumerate(result["signals"], 1):
        trade = trades_by_signal.get(signal.get("signal_time")); stem=f"episode_{index:04d}"
        (gallery/(stem+"_full.svg")).write_text(_svg_episode(index, signal, trade, h1, rsi, None, "full"), encoding="utf-8")
        (gallery/(stem+"_before.svg")).write_text(_svg_episode(index, signal, trade, h1, rsi, None, "before"), encoding="utf-8")
        title = html.escape(f"{signal.get('signal_time','')} — {signal.get('status','')} — {trade.get('exit_reason','') if trade else signal.get('cancel_reason','')}")
        cards.append(f"<article><h2>{index:04d} {title}</h2><button onclick=toggle(this)>Before entry</button><span> Full graph</span><br><img src='gallery/{stem}_full.svg' data-before='gallery/{stem}_before.svg' style='max-width:100%'></article>")
    page = "<!doctype html><meta charset='utf-8'><title>BTC_SPOT_TREND_PULLBACK_V1 gallery</title><style>body{font-family:Arial;margin:24px}article{margin:30px 0;border-bottom:1px solid #ddd;padding-bottom:24px}button{padding:6px 12px}</style><script>function toggle(b){const i=b.parentElement.querySelector('img');const before=i.src.endsWith('_before.svg');i.src=before?i.dataset.full||i.src.replace('_before.svg','_full.svg'):i.dataset.before;b.textContent=before?'Before entry':'Full graph'}</script>"+"".join(cards)
    (out/"index.html").write_text(page, encoding="utf-8")


def benchmark_rows(minutes, prepared, start, end, scenario):
    start, end = parse_time(start), parse_time(end); allowed = prepared["warmup_end"]
    rows = [r for r in minutes if start <= parse_time(r["open_time"]) < end]; cash=D("10000"); buy=None
    if allowed:
        first = next((r for r in rows if parse_time(r["open_time"]) >= allowed), None)
        if first:
            fill = _buy_price(first["open"], scenario); q=floor_step(D("0.95")*cash/fill, D("0.000001")); received=q*(D("1")-scenario.fee); cash -= q*fill; buy=(q, received)
    end_close=D(rows[-1]["close"]) if rows else D("0"); bh_nav=cash + (buy[1]*_sell_price(end_close, scenario) if buy else D("0"))
    # Simple H4 trend orientation: 95% exposure while G is true, sold on
    # the next minute after G becomes false.  It is a benchmark, not V1.
    cash, btc, pending = D("10000"), ZERO, None
    h4_by_end = prepared["h4_by_end"]; regime = prepared["regime"]
    for row in rows:
        t=parse_time(row["open_time"])
        if pending is not None and pending["time"] == t:
            if pending["side"] == "BUY" and btc == ZERO:
                fill=_buy_price(row["open"], scenario); q=floor_step(D("0.95")*cash/fill,D("0.000001")); received=q*(D("1")-scenario.fee); cash-=q*fill; btc=received
            elif pending["side"] == "SELL" and btc > ZERO:
                cash += btc*_sell_price(row["open"],scenario)*(D("1")-scenario.fee); btc=ZERO
            pending=None
        h4i=h4_by_end.get(t)
        if h4i is not None and regime[h4i] is not None:
            if regime[h4i] and btc == ZERO: pending={"time":t+timedelta(minutes=1),"side":"BUY"}
            if regime[h4i] is False and btc > ZERO: pending={"time":t+timedelta(minutes=1),"side":"SELL"}
    trend_nav=cash + btc*_sell_price(end_close,scenario)
    return {"scenario":scenario.name,"cash_return_pct":"0","buy_hold_return_pct":str((bh_nav/D("10000")-D("1"))*D("100")),"trend_return_pct":str((trend_nav/D("10000")-D("1"))*D("100")),"benchmark_note":"cash 100%; buy-and-hold 95% first allowed minute; H4 trend 95% while G=True, next-minute exits"}


def inventory(minutes, output):
    segments = split_continuous_minutes(minutes, CUTOFF); rows=[]
    for i, segment in enumerate(segments, 1):
        h4=[r for r in aggregate_h4(segment) if r["complete"]]; prepared=prepare_segment(segment); warm=prepared["warmup_end"]
        rows.append({"segment_id":f"m1_{i:03d}","start":segment[0]["open_time"],"end":segment[-1]["open_time"],"minute_count":len(segment),"full_h4_count":len(h4),"warmup_end":str(warm or ""),"qualifies_warmup":str(bool(warm)),"reserved_cutoff":"2025-07-01T00:00:00Z","reason":"OK" if warm else "INSUFFICIENT_WARMUP"})
    write_csv(Path(output)/"inventory.csv", rows); return segments, rows


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--minutes",default="data/processed/btcusdt_1m_2017-08_2025-06_recovered.csv"); parser.add_argument("--output-dir",default="reports/btc_spot_trend_pullback_v1"); args=parser.parse_args()
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); minutes=read_csv(args.minutes); segments, inv=inventory(minutes,out)
    source_hash=sha256(args.minutes); code_hash=sha256(Path(__file__))
    _write_json(out/"run_config.json", {"strategy":"BTC_SPOT_TREND_PULLBACK_V1","source":args.minutes,"source_sha256":source_hash,"runner_sha256":code_hash,"cutoff":"2025-07-01T00:00:00Z","warmup_h4":300,"capital_usdt":"10000","risk":"0.5%","filters_assumption":"tickSize=0.01, stepSize=0.000001, minQty/minNotional=0; historical exchangeInfo unavailable; values are modelling assumptions, not reconstructed Binance filters","scenarios":[s.__dict__ for s in SCENARIOS],"unrun_document_stages":["tail-stop slippage +25/+50bp","signal delays +3/+5 minutes","six one-at-a-time neighbors","5000-block bootstrap","closed Jul-Dec 2025 final period","live/partial-fill replay"]})
    _write_json(out/"data_quality.json", {"cutoff":"2025-07-01T00:00:00Z","source_quality":__import__("vp_bot.btc_spot_trend_pullback_v1",fromlist=["quality_report"]).quality_report(minutes),"segment_count":len(segments),"qualifying_segments":sum(1 for r in inv if r["qualifies_warmup"]=="True")})
    metrics=[]; benchmarks=[]
    for i, segment in enumerate(segments, 1):
        prepared=prepare_segment(segment); if_warm=prepared["warmup_end"]; minute_times=[parse_time(r["open_time"]) for r in segment]
        if not if_warm: continue
        seg_start=segment[0]["open_time"]
        natural_end=parse_time(segment[-1]["open_time"])+timedelta(minutes=1)
        seg_end_dt=min(natural_end, datetime(2025, 1, 1, tzinfo=UTC)) if parse_time(segment[0]["open_time"]) < datetime(2025, 1, 1, tzinfo=UTC) else natural_end
        seg_end=iso(seg_end_dt)
        name=f"m1_{i:03d}_{segment[0]['open_time'][:10]}_{(seg_end_dt-timedelta(minutes=1)).date().isoformat()}"; case=out/name; case.mkdir(parents=True,exist_ok=True)
        for scenario in SCENARIOS:
            result=run_segment(segment,seg_start,seg_end,scenario,Filters(),prepared=prepared)
            for trade in result["trades"]: _mfe_mae(trade,segment,minute_times)
            dest=case/scenario.name; dest.mkdir(exist_ok=True); write_csv(dest/"decision_log.csv",result["decision_log"]); write_csv(dest/"signals.csv",result["signals"]); write_csv(dest/"trades.csv",result["trades"]); write_csv(dest/"equity.csv",result["equity"]); write_csv(dest/"daily_equity.csv",result["daily_equity"]); _write_json(dest/"metrics.json",scenario_metrics(result)); build_gallery(result,segment,dest/"gallery")
            metrics.append({"segment_id":name,**scenario_metrics(result)}); benchmarks.append({"segment_id":name,**benchmark_rows(segment,prepared,seg_start,seg_end,scenario)})
        # A separately bounded Jan-Jun view uses the same continuous segment and its own account.
        jan_start=datetime(2025,1,1,tzinfo=UTC); jan_end=datetime(2025,7,1,tzinfo=UTC)
        if parse_time(segment[-1]["open_time"]) >= jan_start and parse_time(segment[0]["open_time"]) < jan_end:
            name2="jan_jun_2025"; case2=out/name2; case2.mkdir(exist_ok=True)
            for scenario in SCENARIOS:
                result=run_segment(segment,jan_start,jan_end,scenario,Filters(),prepared=prepared)
                for trade in result["trades"]: _mfe_mae(trade,segment,minute_times)
                dest=case2/scenario.name; dest.mkdir(exist_ok=True); write_csv(dest/"decision_log.csv",result["decision_log"]); write_csv(dest/"signals.csv",result["signals"]); write_csv(dest/"trades.csv",result["trades"]); write_csv(dest/"equity.csv",result["equity"]); write_csv(dest/"daily_equity.csv",result["daily_equity"]); _write_json(dest/"metrics.json",scenario_metrics(result)); build_gallery(result,segment,dest/"gallery"); metrics.append({"segment_id":name2,**scenario_metrics(result)}); benchmarks.append({"segment_id":name2,**benchmark_rows(segment,prepared,jan_start,jan_end,scenario)})
    write_csv(out/"metrics.csv",metrics); write_csv(out/"benchmarks.csv",benchmarks); (out/"index.html").write_text("<!doctype html><meta charset='utf-8'><title>BTC_SPOT_TREND_PULLBACK_V1</title><h1>BTC_SPOT_TREND_PULLBACK_V1</h1><p>Full graph is the default. Each scenario has a separate gallery; Before entry is a button.</p><a href='inventory.csv'>Inventory</a> | <a href='metrics.csv'>Metrics</a><ul>"+"".join(f"<li><a href='{p.name}/BASE/gallery/index.html'>{p.name}</a></li>" for p in sorted(out.iterdir()) if p.is_dir() and (p/"BASE/gallery/index.html").exists())+"</ul>",encoding="utf-8")
    print(json.dumps({"segments":len(segments),"qualifying":sum(1 for r in inv if r["qualifies_warmup"]=="True"),"metrics":len(metrics),"output":str(out)},ensure_ascii=False))


if __name__ == "__main__": main()
