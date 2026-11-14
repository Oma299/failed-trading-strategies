"""Run the fixed V1 compression-breakout-retest research experiment."""
import argparse, csv, json
from pathlib import Path
from .validation import aggregate_hourly, validate_rows
from .volatility_compression_breakout_retest import detect, metrics, write_csv, build_gallery

def read(path):
    with Path(path).open(newline="",encoding="utf-8") as f: return list(csv.DictReader(f))

def main():
    p=argparse.ArgumentParser(); p.add_argument("--minutes",default="data/processed/btcusdt_1m_2024-12_2025-06.csv"); p.add_argument("--output-dir",default="reports/volatility_compression_breakout_retest_v1"); p.add_argument("--start",default="2025-01-01T00:00:00"); p.add_argument("--end",default="2025-07-01T00:00:00"); a=p.parse_args()
    mins=read(a.minutes); hours=aggregate_hourly(mins); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    quality=validate_rows(mins); first_history=hours[731]["open_time"] if len(hours)>731 else None; (out/"data_quality.json").write_text(json.dumps({"minutes":quality,"hourly_count":len(hours),"first_hour":hours[0]["open_time"],"last_hour":hours[-1]["open_time"],"first_full_30_day_history":first_history},indent=2)+"\n")
    episodes,trades=detect(hours,mins,a.start,a.end); write_csv(out/"episodes.csv",episodes); write_csv(out/"trades.csv",trades)
    m=metrics(trades)
    by_month={}; by_direction={}
    for r in trades:
        if r.get("status") != "TRADE": continue
        key=r["entry_time"][:7]; by_month.setdefault(key,[]).append(r); by_direction.setdefault(r["direction"],[]).append(r)
    m["by_month"]={k:metrics(v) for k,v in sorted(by_month.items())}; m["by_direction"]={k:metrics(v) for k,v in sorted(by_direction.items())}
    (out/"metrics.json").write_text(json.dumps(m,indent=2)+"\n")
    config={"strategy":"Volatility Compression Breakout Retest V1","symbol":"BTCUSDT","data":a.minutes,"period_start_utc":a.start,"period_end_utc":a.end,"signal":"H1 UTC; 12 closed hours; 720 prior windows; nearest-rank ceil(0.20*720)","atr":"Wilder 14 H1, fixed at breakout","breakout_bars":6,"retest_bars":3,"target":"exactly 2R from actual entry fill","holding":"12 hours, minute [T,T+12h), TIME_EXIT at open T+12h","commission":"0%","adverse_slippage":"0.02% per fill","shorts":"hypothetical Spot price model","counts":{"compressions":sum(e.get("status") in ("COMPRESSION","BREAKOUT","SIGNAL","TRADE","DATA_INCOMPLETE") for e in episodes),"breakouts":sum(bool(e.get("breakout_time")) for e in episodes),"retests":sum(bool(e.get("retest_time")) for e in episodes),"trades":m["trades"]},"metrics":m}
    (out/"run_config.json").write_text(json.dumps(config,indent=2)+"\n"); build_gallery(trades,hours,out)
    print(json.dumps({"episodes":len(episodes),"trades":m["trades"],"metrics":m},indent=2))
if __name__=="__main__": main()
