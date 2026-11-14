"""Run the fixed BASE_20D control against the DAILY_REARM variant."""
import argparse, json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .btc_spot_donchian_v1 import (SCENARIOS, aggregate_daily, read_csv, run_scenario,
    scenario_metrics, write_csv, Filters, parse_time)
from .run_btc_spot_donchian_entry10d import attribution, closed, build_pair_gallery

UTC = timezone.utc
VARIANTS = (("BASE_20D", False), ("DAILY_REARM", True))

def turnover(trades):
    return sum((Decimal(t.get("quote_order_amount") or 0) + Decimal(t.get("exit_base") or 0) * Decimal(t.get("btc_received") or 0) for t in closed(trades)), Decimal("0"))

def loss_streak(trades):
    current = best = 0; rows = []
    for t in sorted(closed(trades), key=lambda x: x.get("entry_time", "")):
        if Decimal(t.get("net_pnl_usdt") or 0) < 0:
            current += 1; best = max(best, current); rows.append({"signal_date":t.get("signal_date",""),"r":t.get("r",""),"streak_length":current})
        else: current = 0
    return best, rows

def run_case(minutes, daily, start, end, out, name):
    case = Path(out) / name; results = {}; rows = []
    for variant, rearm in VARIANTS:
        for scenario in SCENARIOS:
            result = run_scenario(minutes, daily, start, end, scenario, Filters(), daily_rearm=rearm)
            results[(variant, scenario.name)] = result
            dest = case / variant / scenario.name; dest.mkdir(parents=True, exist_ok=True)
            write_csv(dest/"signals.csv", result["signals"]); write_csv(dest/"trades.csv", result["trades"]); write_csv(dest/"equity.csv", result["equity"])
            m = scenario_metrics(result); m.update({"case":name,"variant":variant,"turnover_usdt":str(turnover(result["trades"]))})
            rows.append(m)
            if variant == "DAILY_REARM":
                write_csv(dest/"rearm_entries.csv", [{k:v for k,v in s.items() if k in ("signal_date","prior_event","decision_reason","status","entry_time","entry_fill","stop","b","b_previous")} for s in result["signals"] if s.get("rearm_signal")=="True"])
                best, streak = loss_streak(result["trades"]); (dest/"loss_streak.json").write_text(json.dumps({"max_consecutive_losing_closed_trades":best,"sequence":streak},indent=2)+"\n",encoding="utf-8")
    case.mkdir(parents=True, exist_ok=True); write_csv(case/"metrics.csv", rows)
    for scenario in SCENARIOS: write_csv(case/(scenario.name+"_attribution.csv"), attribution(results[("BASE_20D",scenario.name)]["trades"], results[("DAILY_REARM",scenario.name)]["trades"]))
    base = closed(results[("BASE_20D","BASE")]["trades"]); rearm = closed(results[("DAILY_REARM","BASE")]["trades"]); pairs=[]
    for t in base: pairs.append((t,next((x for x in rearm if x.get("entry_time")==t.get("entry_time")),None)))
    for t in rearm:
        if not any(p[1] and p[1].get("entry_time")==t.get("entry_time") for p in pairs): pairs.append((None,t))
    build_pair_gallery(pairs,daily,case/"comparative_gallery",labels=("BASE_20D","DAILY_REARM"))
    return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument("--minutes",default="data/processed/btcusdt_1m_2017-08_2025-06_recovered.csv"); p.add_argument("--output-dir",default="reports/btc_spot_donchian_daily_rearm_comparison"); args=p.parse_args()
    minutes=read_csv(args.minutes); daily=aggregate_daily(minutes); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); all_rows=[]
    inventory=read_csv("reports/btc_spot_donchian_v1_recovery_segments/segment_inventory.csv")
    for rec in inventory:
        if rec.get("qualifies_with_20_day_warmup")!="True" or date.fromisoformat(rec["start"])>=date(2025,1,1): continue
        sd,ed=date.fromisoformat(rec["start"]),date.fromisoformat(rec["end"]); d=[r for r in daily if sd<=date.fromisoformat(r["date"])<=ed]; rows=[r for r in minutes if sd<=parse_time(r["open_time"]).date()<=ed]
        all_rows += run_case(rows,d,f"{sd}T00:00:00",f"{ed+timedelta(days=1)}T00:00:00",out,f"segment_{int(rec['segment']):03d}_{sd}_{ed}")
    jd=[r for r in daily if date.fromisoformat(r["date"])<=date(2025,6,30)]; jr=[r for r in minutes if date(2024,12,1)<=parse_time(r["open_time"]).date()<=date(2025,6,30)]
    all_rows += run_case(jr,jd,"2025-01-01T00:00:00","2025-07-01T00:00:00",out,"jan_jun_2025")
    write_csv(out/"comparison_metrics.csv",all_rows)
    (out/"run_config.json").write_text(json.dumps({"strategy":"BTC_SPOT_DONCHIAN_DAILY_REARM","control":"BASE_20D","variant":"DAILY_REARM","only_change":"remove B_(t-1)=False gate; one attempt per daily close; canceled attempt expires; exit priority","input":args.minutes,"periods":"all prior qualifying segments plus Jan-Jun 2025; July-Dec 2025 excluded","scenarios":"same ZERO/BASE/STRESS; same observations, not independent samples"},indent=2)+"\n",encoding="utf-8")
    links=[f"<li><a href='{p.name}/comparative_gallery/gallery/index.html'>{p.name}</a></li>" for p in sorted(out.iterdir()) if p.is_dir() and (p/"comparative_gallery/gallery/index.html").exists()]
    (out/"index.html").write_text("<!doctype html><meta charset='utf-8'><title>BASE_20D vs DAILY_REARM</title><h1>BASE_20D vs DAILY_REARM</h1><p>Only the daily rearm rule changes. Full graph is the default.</p><a href='comparison_metrics.csv'>Metrics</a><ul>"+"".join(links)+"</ul>",encoding="utf-8")
if __name__=="__main__": main()
