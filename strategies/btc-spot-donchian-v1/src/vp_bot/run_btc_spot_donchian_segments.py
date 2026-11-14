"""Inventory and run every qualifying continuous complete-day segment separately."""
import argparse
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .btc_spot_donchian_v1 import SCENARIOS, aggregate_daily, read_csv, run_scenario, scenario_metrics, write_csv, Filters, build_gallery

UTC = timezone.utc


def segments(daily):
    result, current, previous = [], [], None
    for row in daily:
        day = date.fromisoformat(row["date"])
        if row["complete"] and (previous is None or day == previous + timedelta(days=1)):
            current.append(row)
        else:
            if current: result.append(current)
            current = [row] if row["complete"] else []
        previous = day
    if current: result.append(current)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", default="data/processed/btcusdt_1m_2017-08_2025-06_recovered.csv")
    parser.add_argument("--output-dir", default="reports/btc_spot_donchian_v1_recovery_segments")
    parser.add_argument("--period-end", default="2025-01-01T00:00:00")
    args = parser.parse_args()
    minutes = read_csv(args.minutes)
    daily = aggregate_daily(minutes)
    all_segments = segments(daily)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    inventory = []
    summary = []
    yearly_summary = []
    gallery_links = []
    end = datetime.fromisoformat(args.period_end).replace(tzinfo=UTC)
    for index, daily_segment in enumerate(all_segments, 1):
        daily_segment = [row for row in daily_segment if date.fromisoformat(row["date"]) < end.date()]
        if not daily_segment: continue
        start_day = date.fromisoformat(daily_segment[0]["date"])
        end_day = date.fromisoformat(daily_segment[-1]["date"])
        rows = [row for row in minutes if start_day <= datetime.fromisoformat(row["open_time"].replace("Z", "+00:00")).date() <= end_day and datetime.fromisoformat(row["open_time"].replace("Z", "+00:00")) < end]
        qualifies = len(daily_segment) >= 21 and end_day >= date(2017, 8, 18)
        record = {"segment": index, "start": str(start_day), "end": str(end_day), "complete_days": len(daily_segment), "qualifies_with_20_day_warmup": qualifies, "rows": len(rows)}
        inventory.append(record)
        if not qualifies or start_day >= date(2025, 1, 1): continue
        segment_dir = out / ("segment_%03d_%s_%s" % (index, start_day, end_day)); segment_dir.mkdir(parents=True, exist_ok=True)
        for scenario in SCENARIOS:
            result = run_scenario(rows, daily_segment, "%sT00:00:00" % start_day, min(args.period_end, "%sT00:00:00" % (end_day + timedelta(days=1))), scenario, Filters())
            metrics = scenario_metrics(result)
            write_csv(segment_dir / (scenario.name + "_trades.csv"), result["trades"])
            write_csv(segment_dir / (scenario.name + "_signals.csv"), result["signals"])
            write_csv(segment_dir / (scenario.name + "_equity.csv"), result["equity"])
            build_gallery([trade for trade in result["trades"] if trade.get("status") == "CLOSED"], daily_segment, segment_dir / "gallery" / scenario.name)
            gallery_links.append("<li><a href='%s/gallery/%s/index.html'>segment %03d · %s · %s · %s</a></li>" % (segment_dir.name, scenario.name, index, start_day, end_day, scenario.name))
            summary.append({"segment": index, "start": str(start_day), "end": str(end_day), **metrics})
            for year, yearly in metrics["yearly_mark_to_market"].items():
                yearly_summary.append({"segment": index, "start": str(start_day), "end": str(end_day), "scenario": scenario.name, "year": year, **yearly})
    write_csv(out / "segment_inventory.csv", inventory)
    write_csv(out / "segment_metrics.csv", summary)
    write_csv(out / "segment_yearly_metrics.csv", yearly_summary)
    (out / "run_config.json").write_text(json.dumps({"strategy": "BTC_SPOT_DONCHIAN_V1", "input": args.minutes, "period_end": args.period_end, "method": "Each maximal run of consecutive complete UTC days is run separately; no PnL is concatenated; segments shorter than 21 days are inventory-only.", "synthetic_rows_added": 0}, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text("<!doctype html><meta charset='utf-8'><title>BTC_SPOT_DONCHIAN_V1 recovery segments</title><h1>BTC_SPOT_DONCHIAN_V1 recovery segments</h1><p>Each segment is independent. Full graph is the default in each scenario gallery.</p><ul>" + "".join(gallery_links) + "</ul>", encoding="utf-8")
    print(json.dumps({"segments": inventory, "qualifying_segment_count": sum(row["qualifies_with_20_day_warmup"] for row in inventory), "run_count": len(summary)}, indent=2))


if __name__ == "__main__": main()
