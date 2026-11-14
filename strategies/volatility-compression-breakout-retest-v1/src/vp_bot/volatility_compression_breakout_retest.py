"""Volatility Compression Breakout Retest V1 research model.

The module is deliberately independent of the older daily-profile and range
reversal strategies.  Short rows are a hypothetical price model on Spot data.
"""
import csv, html, json, random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path

# Match the project's existing Decimal precision without lowering it.
getcontext().prec = max(getcontext().prec, 40)
UTC = timezone.utc
SLIPPAGE = Decimal("0.0002")

def dt(v): return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(UTC)
def iso(v): return v.astimezone(UTC).isoformat().replace("+00:00", "Z")
def D(v): return Decimal(str(v))

def atr_wilder(hours, period=14):
    out, trs, prev_close, prev_time, previous = [], [], None, None, None
    for row in hours:
        t=dt(row["open_time"]); valid=row.get("complete_60_distinct_minutes", True) in (True, "True", 1, "1")
        if not valid or (prev_time is not None and t != prev_time + timedelta(hours=1)):
            trs=[]; previous=None; prev_close=None
        if not valid:
            out.append(None); prev_time=None; continue
        hi,lo,cl=map(D,(row["high"],row["low"],row["close"]))
        tr=hi-lo if prev_close is None else max(hi-lo, abs(hi-prev_close), abs(lo-prev_close))
        trs.append(tr)
        if len(trs) >= period:
            previous=sum(trs[-period:], Decimal(0))/period if previous is None else (previous*(period-1)+tr)/period
            out.append(previous)
        else: out.append(None)
        prev_close,prev_time=cl,t
    return out

def _valid_window(rows):
    return len(rows)==len(set(dt(x["open_time"]) for x in rows)) and all(x.get("complete_60_distinct_minutes",True) in (True,"True",1,"1") for x in rows) and all(dt(b["open_time"])-dt(a["open_time"])==timedelta(hours=1) for a,b in zip(rows,rows[1:]))

def _base(reason=""):
    return {"status":"CANCELLED", "reason":reason, "direction":"", "breakout_time":"", "retest_time":"", "entry_time":"", "entry_base":"", "entry_fill":"", "stop":"", "target":"", "exit_time":"", "exit_base":"", "exit_fill":"", "exit_reason":"", "ambiguous":"False", "incomplete_data":"False", "gross_pnl_usdt_1btc":"", "r":""}

def _fill(side, price): return price*(Decimal(1)+SLIPPAGE) if side=="LONG" else price*(Decimal(1)-SLIPPAGE)

def execute(signal, minutes):
    out=dict(signal); by={dt(x["open_time"]):x for x in minutes}; entry_t=dt(signal["entry_time"])
    er=by.get(entry_t)
    if er is None: out.update(status="DATA_INCOMPLETE", reason="MISSING_ENTRY_MINUTE", incomplete_data="True"); return out
    side=signal["direction"]; entry_base=D(er["open"]); entry=_fill(side,entry_base); stop=D(signal["stop"]); target=entry+D(2)*(entry-stop) if side=="LONG" else entry-D(2)*(stop-entry)
    if not ((side=="LONG" and stop<entry) or (side=="SHORT" and entry<stop)):
        out.update(status="SKIPPED", reason="INVALID_STOP_SIDE", entry_base=str(entry_base), entry_fill=str(entry), target=str(target)); return out
    if abs(entry-stop) < D("0.5")*D(signal["atr_breakout"]):
        out.update(status="SKIPPED", reason="STOP_DISTANCE_LT_0_5_ATR", entry_base=str(entry_base), entry_fill=str(entry), target=str(target)); return out
    out.update(status="TRADE", entry_base=str(entry_base), entry_fill=str(entry), target=str(target))
    for n in range(12*60+1):
        t=entry_t+timedelta(minutes=n); row=by.get(t)
        if row is None: out.update(status="DATA_INCOMPLETE", reason="DATA_INCOMPLETE", incomplete_data="True"); return out
        op,hi,lo=map(D,(row["open"],row["high"],row["low"]))
        if n==12*60:
            reason="TIME_EXIT"; base=op; fill=_fill(side,op)
            if (side=="LONG" and op<=stop) or (side=="SHORT" and op>=stop): reason="TIME_EXIT_STOP_GAP"; fill=_fill(side,op)
        else:
            stop_hit=(lo<=stop if side=="LONG" else hi>=stop); target_hit=(hi>=target if side=="LONG" else lo<=target)
            open_stop=(op<=stop if side=="LONG" else op>=stop); open_target=(op>=target if side=="LONG" else op<=target)
            if (stop_hit and target_hit) or open_stop: reason="STOP"; base=op if open_stop else stop; fill=_fill(side,base); ambiguous=stop_hit and target_hit
            elif open_target: reason="TARGET"; base=op; fill=_fill(side,op)
            elif stop_hit: reason="STOP"; base=stop; fill=_fill(side,base); ambiguous=False
            elif target_hit: reason="TARGET"; base=target; fill=_fill(side,base)
            else: continue
        gross=(fill-entry) if side=="LONG" else (entry-fill); risk=abs(entry-stop)
        out.update(exit_time=iso(t),exit_base=str(base),exit_fill=str(fill),exit_reason=reason,ambiguous=str(bool(locals().get("ambiguous",False))),gross_pnl_usdt_1btc=str(gross),r=str(gross/risk)); return out
    return out

def detect(hours, minutes, start, end):
    hours=sorted(hours,key=lambda x:x["open_time"]); minutes=sorted(minutes,key=lambda x:x["open_time"]); ats=atr_wilder(hours); result=[]; trades=[]; active_until=None; i=0
    # Precompute all 12-hour widths once; the scan otherwise repeats ~9k date
    # parses for every candidate and makes the six-month run unnecessarily slow.
    widths=[None]*len(hours)
    for q in range(11,len(hours)):
        w=hours[q-11:q+1]
        if _valid_window(w): widths[q]=(max(D(x["high"]) for x in w)-min(D(x["low"]) for x in w))/D(hours[q]["close"])*100
    start_t=datetime.fromisoformat(start).replace(tzinfo=UTC); end_t=datetime.fromisoformat(end).replace(tzinfo=UTC)
    while i<len(hours):
        t=dt(hours[i]["open_time"])
        if not (start_t<=t<end_t): i+=1; continue
        if active_until and t <= active_until: i+=1; continue
        if i<731 or widths[i] is None or ats[i] is None: i+=1; continue
        window=hours[i-11:i+1]; U=max(D(x["high"]) for x in window); L=min(D(x["low"]) for x in window); W=widths[i]
        hist=widths[i-720:i]
        if any(x is None for x in hist): i+=1; continue
        threshold=sorted(hist)[(20*len(hist)+99)//100-1]
        ep={"compression_time":iso(t),"range_upper":str(U),"range_lower":str(L),"width_pct":str(W),"percentile_20":str(threshold),"status":"COMPRESSION"}
        if W>threshold: i+=1; continue
        ep.update(_base()); ep.update(compression_time=iso(t),range_upper=str(U),range_lower=str(L),width_pct=str(W),percentile_20=str(threshold))
        breakout=None
        for k in range(1,7):
            if i+k>=len(hours) or not _valid_window(hours[i+k:i+k+1]): ep.update(reason="DATA_INCOMPLETE_BREAKOUT_WINDOW",status="CANCELLED"); break
            b=hours[i+k]; a=ats[i+k]
            if a is None: continue
            c=D(b["close"])
            if c>=U+D("0.1")*a: breakout=("LONG",i+k,a); break
            if c<=L-D("0.1")*a: breakout=("SHORT",i+k,a); break
        if breakout is None: ep.update(reason=ep.get("reason") or "NO_BREAKOUT_6",status="CANCELLED"); result.append(ep); i+=1; continue
        side,bi,bat=breakout; ep.update(direction=side,breakout_time=hours[bi]["open_time"],atr_breakout=str(bat),status="BREAKOUT")
        ret=None
        for k in range(1,4):
            ri=bi+k
            if ri>=len(hours): break
            r=hours[ri]; close=D(r["close"]); ok=(D(r["low"])<=U and close>U) if side=="LONG" else (D(r["high"])>=L and close<L)
            bad=close<=U if side=="LONG" else close>=L
            if bad: ep.update(status="CANCELLED",reason="RETEST_WRONG_SIDE_CLOSE"); break
            if ok: ret=(ri,r); break
        if ret is None:
            if ep["status"]=="BREAKOUT": ep.update(status="CANCELLED",reason="NO_RETEST_3")
            result.append(ep); i+=1; continue
        ri,r=ret; entry_t=dt(hours[ri+1]["open_time"]) if ri+1<len(hours) else None
        if entry_t is None: ep.update(status="DATA_INCOMPLETE",reason="MISSING_ENTRY_HOUR",incomplete_data="True"); result.append(ep); i+=1; continue
        stop=D(r["low"])-D("0.1")*bat if side=="LONG" else D(r["high"])+D("0.1")*bat
        ep.update(status="SIGNAL",retest_time=r["open_time"],entry_time=iso(entry_t),stop=str(stop),target="",atr_breakout=str(bat))
        tr=execute(ep,minutes); ep.update(tr); result.append(ep)
        if tr.get("status") in ("TRADE","DATA_INCOMPLETE"): active_until=dt(tr.get("exit_time") or iso(entry_t+timedelta(hours=12)))
        trades.append(ep); i=ri+1
    return result,trades

def write_csv(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True); fields=sorted({k for r in rows for k in r})
    with path.open("w",newline="",encoding="utf-8") as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def metrics(trades):
    done=[r for r in trades if r.get("status")=="TRADE"]; rs=[D(r["r"]) for r in done]; wins=[r for r in rs if r>0]; losses=[r for r in rs if r<0]; curve=Decimal(0); peak=Decimal(0); dd=Decimal(0)
    for r in rs: curve+=r; peak=max(peak,curve); dd=max(dd,peak-curve)
    def avg(x): return str(sum(x,Decimal(0))/len(x)) if x else ""
    pnl=[D(r["gross_pnl_usdt_1btc"]) for r in done]
    return {"trades":len(done),"data_incomplete":sum(r.get("status")=="DATA_INCOMPLETE" for r in trades),"win_rate":str(Decimal(len(wins))/len(rs)) if rs else "","mean_win_r":avg(wins),"mean_loss_r":avg(losses),"mean_r":avg(rs),"sum_r":str(sum(rs,Decimal(0))),"profit_factor":str(sum(wins,Decimal(0))/abs(sum(losses,Decimal(0)))) if losses else "","max_drawdown_r":str(dd),"long":sum(r["direction"]=="LONG" for r in done),"short":sum(r["direction"]=="SHORT" for r in done),"sum_gross_pnl_usdt_1btc":str(sum(pnl,Decimal(0))),"mean_gross_pnl_usdt_1btc":avg(pnl)}

def svg_trade(row, hours, minutes, mode="full"):
    entry=dt(row["entry_time"]); start=entry-timedelta(hours=12); end=entry+timedelta(hours=12); rs=[x for x in hours if start<=dt(x["open_time"])<end];
    if mode=="before": rs=[x for x in rs if dt(x["open_time"])<entry]
    vals=[D(x["high"]) for x in rs]+[D(x["low"]) for x in rs]+[D(row["range_upper"]),D(row["range_lower"]),D(row["stop"]),D(row.get("target") or row["entry_fill"])]
    lo,hi=min(vals),max(vals); pad=max((hi-lo)*D("0.08"),D(1)); lo-=pad; hi+=pad; left,top,w,h=80,70,1200,430
    def x(t): return left+(t-start).total_seconds()/86400*w
    def y(v): return top+float((hi-D(v))/(hi-lo))*h
    p=['<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="590" style="font-family:Arial"><rect width="100%" height="100%" fill="white"/>',f'<text x="20" y="28" font-size="18" font-weight="bold">Compression Breakout Retest V1 · {html.escape(row["direction"])} · {"before entry" if mode=="before" else row.get("exit_reason","")}</text>', '<rect x="80" y="70" width="1200" height="430" fill="#fafafa" stroke="#bbb"/>']
    for v,label,color in ((row["range_upper"],"U","#2563eb"),(row["range_lower"],"L","#2563eb"),(row["stop"],"stop","#dc2626"),(row.get("target") or row["entry_fill"],"target","#7c3aed")):
        p.append(f'<line x1="{left}" y1="{y(v)}" x2="{left+w}" y2="{y(v)}" stroke="{color}" stroke-dasharray="6 4"/><text x="{left+w-90}" y="{y(v)-4}" fill="{color}" font-size="11">{label} {D(v):.2f}</text>')
    for r in rs:
        xx=x(dt(r["open_time"])); color="#15803d" if D(r["close"])>=D(r["open"]) else "#b91c1c"; opacity="0.28" if mode=="full" and row.get("exit_time") and dt(r["open_time"])>dt(row["exit_time"]) else "1"; p.append(f'<g opacity="{opacity}"><line x1="{xx:.1f}" y1="{y(r["high"]):.1f}" x2="{xx:.1f}" y2="{y(r["low"]):.1f}" stroke="{color}"/><line x1="{xx:.1f}" y1="{y(r["open"]):.1f}" x2="{xx:.1f}" y2="{y(r["close"]):.1f}" stroke="{color}" stroke-width="3"/></g>')
    if mode=="full" and row.get("exit_time"):
        ex=dt(row["exit_time"]); p.append(f'<line x1="{x(ex):.1f}" y1="{top}" x2="{x(ex):.1f}" y2="{top+h}" stroke="#111" stroke-dasharray="2 3"/>')
    p.append(f'<text x="20" y="550" font-size="11">entry {row["entry_fill"]} · exit {row.get("exit_time","")} {row.get("exit_fill","")} · {row.get("exit_reason","")} · R {row.get("r","")} · hypothetical Spot SHORT model</text></svg>'); return "".join(p)

def build_gallery(trades, hours, out):
    g=out/"gallery"; g.mkdir(parents=True,exist_ok=True); randomizer=random.Random(20261109); items=[]
    for n,r in enumerate(trades,1):
        if r.get("status") not in ("TRADE","DATA_INCOMPLETE"): continue
        stem=f"trade_{n:03d}_{dt(r['entry_time']).date()}_{r['direction'].lower()}"; (g/(stem+"_before.svg")).write_text(svg_trade(r,hours,[],"before")); (g/(stem+"_full.svg")).write_text(svg_trade(r,hours,[],"full")); items.append((r,stem))
    randomizer.shuffle(items); sections=["<!doctype html><meta charset='utf-8'><title>Compression Breakout Retest V1</title><style>body{font-family:-apple-system,sans-serif;max-width:1320px;margin:auto}img{width:100%;border:1px solid #ddd}li{margin:22px}button{padding:7px 12px;border:1px solid #999;border-radius:5px;background:#fff;cursor:pointer}</style>","<h1>Volatility Compression Breakout Retest V1</h1><p>Полный график показывается по умолчанию: формирование диапазона, вход, движение сделки, выход и пост-выходной контекст. Кнопка переключает отдельный before-entry режим.</p>","<h2>Mixed trade review</h2><ol>"]
    for r,s in items: sections.append(f"<li><b>{r['direction']} · entry {r['entry_time']}</b><br><button type='button' data-trade='{s}' data-mode='full' onclick=\"toggleView(this)\">Before entry</button><span aria-live='polite'> Full graph</span><br><img id='img_{s}' src='gallery/{s}_full.svg' data-full='gallery/{s}_full.svg' data-before='gallery/{s}_before.svg' alt='Full trade graph'></li>")
    sections.append("</ol><script>function toggleView(button){const img=document.getElementById('img_'+button.dataset.trade);const before=button.dataset.mode==='full';img.src=before?img.dataset.before:img.dataset.full;img.alt=before?'Before-entry trade graph':'Full trade graph';button.dataset.mode=before?'before':'full';button.textContent=before?'Full graph':'Before entry';button.nextElementSibling.textContent=before?' Before entry':' Full graph';}</script>")
    sections.append("</ol><h2>Profitable</h2><ul>"); sections.extend(f"<li>{r['entry_time']} {r['r']}R</li>" for r,s in items if r.get('r') and D(r['r'])>0); sections.append("</ul><h2>Unprofitable</h2><ul>"); sections.extend(f"<li>{r['entry_time']} {r['r']}R</li>" for r,s in items if r.get('r') and D(r['r'])<=0); sections.append("</ul>"); (out/"index.html").write_text("\n".join(sections),encoding="utf-8")
