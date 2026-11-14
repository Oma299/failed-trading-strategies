"""Compare the fixed BASE_20D control with the preselected ENTRY_10D variant.

The only strategy parameter changed here is the entry Donchian lookback.  Each
continuous historical segment is run independently; segment PnL is never
concatenated into a portfolio result.
"""
import argparse, csv, hashlib, html, json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .btc_spot_donchian_v1 import (SCENARIOS, aggregate_daily, indicators,
    read_csv, run_scenario, scenario_metrics, write_csv, Filters, D, parse_time)
from .run_btc_spot_donchian_segments import segments

UTC = timezone.utc
VARIANTS = (("BASE_20D", 20), ("ENTRY_10D", 10))

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()

def closed(rows):
    return [r for r in rows if r.get("status") == "CLOSED"]

def interval(t):
    return parse_time(t["entry_time"]), parse_time(t["exit_time"])

def overlaps(a, b):
    ae, ax = interval(a); be, bx = interval(b)
    return ae <= bx and be <= ax

def attribution(base, variant):
    """Return PDF-defined common/additional/only/changed episode rows."""
    base, variant = closed(base), closed(variant)
    used_b, used_v = set(), set(); rows = []
    for bi, b in enumerate(base):
        for vi, v in enumerate(variant):
            if bi not in used_b and vi not in used_v and b["entry_time"] == v["entry_time"] and b["exit_time"] == v["exit_time"]:
                used_b.add(bi); used_v.add(vi)
                rows.append({"group":"COMMON", "base_index":bi, "variant_index":vi, "base_signal_date":b.get("signal_date",""), "variant_signal_date":v.get("signal_date",""), "base_net_pnl_usdt":b["net_pnl_usdt"], "variant_net_pnl_usdt":v["net_pnl_usdt"], "delta_net_pnl_usdt":str(D(v["net_pnl_usdt"])-D(b["net_pnl_usdt"])), "base_r":b.get("r",""), "variant_r":v.get("r","")})
                break
    for vi, v in enumerate(variant):
        if vi not in used_v and not any(overlaps(v, b) for b in base):
            used_v.add(vi); rows.append({"group":"ONLY_VARIANT", "base_index":"", "variant_index":vi, "base_signal_date":"", "variant_signal_date":v.get("signal_date",""), "base_net_pnl_usdt":"0", "variant_net_pnl_usdt":v["net_pnl_usdt"], "delta_net_pnl_usdt":v["net_pnl_usdt"], "base_r":"", "variant_r":v.get("r","")})
    for bi, b in enumerate(base):
        if bi not in used_b and not any(overlaps(b, v) for v in variant):
            used_b.add(bi); rows.append({"group":"ONLY_BASE", "base_index":bi, "variant_index":"", "base_signal_date":b.get("signal_date",""), "variant_signal_date":"", "base_net_pnl_usdt":b["net_pnl_usdt"], "variant_net_pnl_usdt":"0", "delta_net_pnl_usdt":str(-D(b["net_pnl_usdt"])), "base_r":b.get("r",""), "variant_r":""})
    remaining_b = [i for i in range(len(base)) if i not in used_b]
    remaining_v = [i for i in range(len(variant)) if i not in used_v]
    # Connected components of overlapping unmatched intervals are one changed episode.
    nodes = [("b", i) for i in remaining_b] + [("v", i) for i in remaining_v]
    while nodes:
        component = [nodes.pop(0)]; changed = True
        while changed:
            changed = False
            for node in list(nodes):
                item = base[node[1]] if node[0] == "b" else variant[node[1]]
                if any(overlaps(item, base[j] if other[0] == "b" else variant[j]) for other, j in ((n, n[1]) for n in component)):
                    component.append(node); nodes.remove(node); changed = True
        bs = [base[i] for k, i in component if k == "b"]; vs = [variant[i] for k, i in component if k == "v"]
        bp = sum((D(x["net_pnl_usdt"]) for x in bs), Decimal("0")); vp = sum((D(x["net_pnl_usdt"]) for x in vs), Decimal("0"))
        rows.append({"group":"CHANGED_EPISODE", "base_index":";".join(str(i) for k,i in component if k=="b"), "variant_index":";".join(str(i) for k,i in component if k=="v"), "base_signal_date":";".join(x.get("signal_date","") for x in bs), "variant_signal_date":";".join(x.get("signal_date","") for x in vs), "base_net_pnl_usdt":str(bp), "variant_net_pnl_usdt":str(vp), "delta_net_pnl_usdt":str(vp-bp), "base_r":";".join(x.get("r","") for x in bs), "variant_r":";".join(x.get("r","") for x in vs)})
    return rows

def comparison_svg(pair, daily, mode="full", labels=("BASE_20D", "ENTRY_10D")):
    vals = [D(r[x]) for r in daily for x in ("high", "low")]
    for t in pair:
        if t:
            vals += [D(t["entry_fill"]), D(t["stop"])]
            if t.get("exit_fill"): vals.append(D(t["exit_fill"]))
    lo, hi = min(vals), max(vals); pad = max((hi-lo)*D("0.08"), D("1")); lo -= pad; hi += pad
    start = datetime.fromisoformat(daily[0]["date"]).date(); end = datetime.fromisoformat(daily[-1]["date"]).date()
    left, top, width, panel_h = 80, 55, 1180, 250
    def x(d): return left + (d-start).total_seconds()/max((end-start).total_seconds(), 86400)*width
    def y(v, panel): return top + panel*(panel_h+45) + float((hi-D(v))/(hi-lo))*panel_h
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="700" style="font-family:Arial"><rect width="100%" height="100%" fill="white"/>']
    for panel, label, trade in ((0, labels[0], pair[0]), (1, labels[1], pair[1])):
        out.append(f'<text x="20" y="{top+panel*(panel_h+45)-20}" font-weight="bold">{label}</text><rect x="80" y="{y(hi,panel)}" width="1180" height="250" fill="#fafafa" stroke="#bbb"/>')
        exit_day = parse_time(trade["exit_time"]).date() if trade else None
        for r in daily:
            d = date.fromisoformat(r["date"]); opacity="0.3" if mode=="full" and exit_day and d>exit_day else "1"; color="#15803d" if D(r["close"])>=D(r["open"]) else "#b91c1c"; xx=x(d)
            out.append(f'<g opacity="{opacity}"><line x1="{xx:.1f}" y1="{y(r["high"],panel):.1f}" x2="{xx:.1f}" y2="{y(r["low"],panel):.1f}" stroke="{color}"/><line x1="{xx:.1f}" y1="{y(r["open"],panel):.1f}" x2="{xx:.1f}" y2="{y(r["close"],panel):.1f}" stroke="{color}" stroke-width="4"/></g>')
            if r.get("lower"): out.append(f'<line x1="{xx-10:.1f}" y1="{y(r["lower"],panel):.1f}" x2="{xx+10:.1f}" y2="{y(r["lower"],panel):.1f}" stroke="#7c3aed" stroke-width="2"/>')
        if trade:
            for val, lab, color in ((trade["entry_fill"],"entry","#111827"),(trade["stop"],"stop","#dc2626")):
                out.append(f'<line x1="80" y1="{y(val,panel):.1f}" x2="1260" y2="{y(val,panel):.1f}" stroke="{color}" stroke-dasharray="6 4"/><text x="1100" y="{y(val,panel)-4}" fill="{color}" font-size="11">{lab} {D(val):.2f}</text>')
            if trade.get("exit_time") and mode=="full": out.append(f'<line x1="{x(parse_time(trade["exit_time"]).date()):.1f}" y1="{y(hi,panel):.1f}" x2="{x(parse_time(trade["exit_time"]).date()):.1f}" y2="{y(lo,panel):.1f}" stroke="#111" stroke-dasharray="2 3"/>')
            out.append(f'<text x="20" y="{top+panel*(panel_h+45)+panel_h+20}" font-size="11">entry {html.escape(trade["entry_time"])} {html.escape(trade["entry_fill"])} · exit {html.escape(trade.get("exit_time",""))} {html.escape(trade.get("exit_fill",""))} · {html.escape(trade.get("exit_reason",""))} · R {html.escape(trade.get("r",""))}</text>')
        else: out.append(f'<text x="20" y="{top+panel*(panel_h+45)+panel_h+20}" font-size="11">No trade in this variant for this attribution episode</text>')
    return ''.join(out) + '</svg>'

def build_pair_gallery(pairs, daily, out, labels=("BASE_20D", "ENTRY_10D")):
    out = Path(out); (out/"gallery").mkdir(parents=True, exist_ok=True); cards=[]
    for i, pair in enumerate(pairs, 1):
        stem = f"episode_{i:03d}"; (out/"gallery"/(stem+"_full.svg")).write_text(comparison_svg(pair, daily, "full", labels), encoding="utf-8"); (out/"gallery"/(stem+"_before.svg")).write_text(comparison_svg(pair, daily, "before", labels), encoding="utf-8")
        cards.append(f"<li><b>{stem}</b> <button data-mode='full' data-id='{stem}' onclick='toggle(this)'>Before entry</button><span> Full graph</span><br><img id='img_{stem}' src='{stem}_full.svg' data-full='{stem}_full.svg' data-before='{stem}_before.svg'></li>")
    page = f"<!doctype html><meta charset='utf-8'><title>{labels[0]} vs {labels[1]}</title><style>body{{font-family:-apple-system,sans-serif;max-width:1320px;margin:auto}}img{{width:100%;border:1px solid #ddd}}li{{margin:24px}}button{{padding:7px 12px}}</style><h1>{labels[0]} vs {labels[1]}</h1><p>Full graph is the default. Before entry is a separate toggle. Both panels use the same price scale.</p><ol>"+''.join(cards)+"</ol><script>function toggle(b){{const i=document.getElementById('img_'+b.dataset.id),before=b.dataset.mode==='full';i.src=before?i.dataset.before:i.dataset.full;b.dataset.mode=before?'before':'full';b.textContent=before?'Full graph':'Before entry';b.nextElementSibling.textContent=before?' Before entry':' Full graph';}}</script>"
    (out/"gallery"/"index.html").write_text(page, encoding="utf-8")

def run_case(minutes, daily, start, end, out, case_name):
    case = Path(out)/case_name; case.mkdir(parents=True, exist_ok=True); results={}
    for variant, window in VARIANTS:
        for scenario in SCENARIOS:
            result=run_scenario(minutes,daily,start,end,scenario,Filters(),entry_window=window); results[(variant,scenario.name)]=result
            dest=case/variant/scenario.name; dest.mkdir(parents=True, exist_ok=True)
            write_csv(dest/"signals.csv",result["signals"]); write_csv(dest/"trades.csv",result["trades"]); write_csv(dest/"equity.csv",result["equity"])
    rows=[]
    for variant,_ in VARIANTS:
        for scenario in SCENARIOS:
            m=scenario_metrics(results[(variant,scenario.name)]); rows.append({"case":case_name,"variant":variant,**m})
    write_csv(case/"metrics.csv",rows)
    for scenario in SCENARIOS:
        a=attribution(results[("BASE_20D",scenario.name)]["trades"],results[("ENTRY_10D",scenario.name)]["trades"]); write_csv(case/(scenario.name+"_attribution.csv"),a)
    pairs=[]; base=closed(results[("BASE_20D","BASE")]["trades"]); var=closed(results[("ENTRY_10D","BASE")]["trades"])
    for t in base: pairs.append((t, next((v for v in var if v.get("entry_time")==t.get("entry_time")), None)))
    for t in var:
        if not any(t.get("entry_time")==p[1].get("entry_time") for p in pairs if p[1]): pairs.append((None,t))
    build_pair_gallery(pairs,daily,case/"comparative_gallery")
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument("--minutes",default="data/processed/btcusdt_1m_2017-08_2025-06_recovered.csv"); p.add_argument("--output-dir",default="reports/btc_spot_donchian_entry10d_comparison"); args=p.parse_args()
    minutes=read_csv(args.minutes); daily=aggregate_daily(minutes); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); all_rows=[]
    inventory=read_csv("reports/btc_spot_donchian_v1_recovery_segments/segment_inventory.csv")
    for rec in inventory:
        if rec.get("qualifies_with_20_day_warmup")!="True" or date.fromisoformat(rec["start"])>=date(2025,1,1): continue
        sd,ed=date.fromisoformat(rec["start"]),date.fromisoformat(rec["end"]); d=[r for r in daily if sd<=date.fromisoformat(r["date"])<=ed]; rows=[r for r in minutes if sd<=parse_time(r["open_time"]).date()<=ed]
        all_rows += run_case(rows,d,f"{sd}T00:00:00",f"{ed+timedelta(days=1)}T00:00:00",out,f"segment_{int(rec['segment']):03d}_{sd}_{ed}")
    jan_daily=[r for r in daily if date.fromisoformat(r["date"])<=date(2025,6,30)]; jan_rows=[r for r in minutes if date(2025,1,1)<=parse_time(r["open_time"]).date()<=date(2025,6,30) or date(2024,12,1)<=parse_time(r["open_time"]).date()<date(2025,1,1)]
    all_rows += run_case(jan_rows,jan_daily,"2025-01-01T00:00:00","2025-07-01T00:00:00",out,"jan_jun_2025")
    write_csv(out/"comparison_metrics.csv",all_rows)
    (out/"run_config.json").write_text(json.dumps({"strategy_control":"BASE_20D","strategy_variant":"ENTRY_10D","entry_windows":{"BASE_20D":20,"ENTRY_10D":10},"unchanged":"D1 UTC, transition false->true, SMA ATR20, fixed 2x ATR stop, lower 10D exit, 60-day limit, risk 0.5%, one position, ZERO/BASE/STRESS","input":args.minutes,"sha256":sha256(args.minutes),"periods":"all prior qualifying continuous segments through 2024-12-31 plus 2025-01-01..2025-06-30; July-December 2025 excluded","attribution":"PDF interval-overlap categories; scenario runs share the same historical observations and are not independent samples"},indent=2)+"\n",encoding="utf-8")
    (out/"index.html").write_text("<!doctype html><meta charset='utf-8'><title>Donchian comparison</title><h1>BASE_20D vs ENTRY_10D</h1><p>Only the entry channel changes. Each segment is independent.</p><a href='comparison_metrics.csv'>Comparison metrics</a><ul>"+''.join(f"<li><a href='{p.name}/comparative_gallery/gallery/index.html'>{p.name}</a></li>" for p in sorted(out.iterdir()) if p.is_dir() and (p/"comparative_gallery/gallery/index.html").exists())+"</ul>",encoding="utf-8")

if __name__=="__main__": main()
