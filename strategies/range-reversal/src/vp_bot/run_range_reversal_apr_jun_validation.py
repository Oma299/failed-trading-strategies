"""Independent Apr-Jun validation of the fixed Range Reversal entry filter.

This is a per-trade unit-size price model.  It intentionally keeps all N3
episodes from the baseline run so a rejected row cannot create another daily
signal.  SHORT rows remain hypothetical Spot OHLCV labels.
"""
import argparse, csv, json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .range_reversal import write_csv
from .range_reversal import LOCAL_OFFSET, parse_time, iso
from .range_reversal_v2 import detect_v2
from .range_reversal_delayed import annotate
from .range_reversal_backtest import read_csv, run_variant, metrics, dec, build_gallery

WIDTH_LIMIT = Decimal("1.246290688786655202027240847")
DELAY_LIMIT = Decimal("50")
VALIDATION_TARGET_MODE = "E3_2R"


def episode_key(row):
    return "|".join((row.get("local_date", ""), row.get("direction", ""), row.get("breakout_time", "")))


def feature_row(row):
    """Use the exact prior diagnostic units: width / E3 entry fill * 100."""
    if row.get("delayed_status") != "ANNOTATION":
        return {"episode_key": episode_key(row), "range_width_price_pct": "", "breakout_to_e3_min": "", "filter_pass": "False", "filter_reason": "NOT_ELIGIBLE"}
    entry_fill = dec(row["e3_open"]) * (Decimal("1.0002") if row["direction"] == "LONG" else Decimal("0.9998"))
    width = dec(row["range_upper"]) - dec(row["range_lower"])
    from .range_reversal import parse_time
    delay = Decimal(str((parse_time(row["e3_time"]) - parse_time(row["breakout_time"])).total_seconds() / 60))
    width_pct = width / entry_fill * Decimal("100")
    passed = width_pct <= WIDTH_LIMIT and delay <= DELAY_LIMIT
    return {"episode_key": episode_key(row), "range_width_price_pct": str(width_pct), "breakout_to_e3_min": str(delay), "filter_pass": str(passed), "filter_reason": "PASS" if passed else "FILTER_EXCLUDED"}


def grouped(rows, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(f, "") for f in fields)].append(row)
    out = []
    for key, values in sorted(groups.items()):
        item = {f: v for f, v in zip(fields, key)}
        item.update(metrics(values)); out.append(item)
    return out


def max_drawdown_r(rows):
    curve = Decimal("0"); peak = Decimal("0"); dd = Decimal("0")
    for row in sorted(rows, key=lambda r: r.get("entry_time", r.get("e3_time", ""))):
        if row.get("outcome") in ("TARGET", "STOP", "END_OF_DAY"):
            curve += dec(row["net_r"]); peak = max(peak, curve); dd = max(dd, peak - curve)
    return str(dd)


def local_day_completeness(minutes, start, end):
    """Require all 1440 UTC minutes of each fixed UTC-04 local day."""
    minute_times = {parse_time(r["open_time"]) for r in minutes}
    result = {}
    for day in (start + timedelta(days=i) for i in range((end - start).days + 1)):
        local_midnight = datetime(day.year, day.month, day.day, tzinfo=LOCAL_OFFSET).astimezone(timezone.utc)
        result[day.isoformat()] = {local_midnight + timedelta(minutes=i) for i in range(1440)}.issubset(minute_times)
    return result


def add_r_summaries(summary, rows):
    values = [dec(r["net_r"]) for r in rows if r.get("net_r") not in (None, "")]
    wins = [x for x in values if x > 0]; losses = [x for x in values if x < 0]
    summary["mean_win_r"] = str(sum(wins, Decimal("0")) / Decimal(len(wins))) if wins else ""
    summary["mean_loss_r"] = str(sum(losses, Decimal("0")) / Decimal(len(losses))) if losses else ""
    summary["total_net_r"] = str(sum(values, Decimal("0")))
    return summary


def gallery_all(rows, minutes, out):
    """Use existing SVG renderer, but include every eligible baseline row and filter badge."""
    gallery = out / "gallery"; gallery.mkdir(parents=True, exist_ok=True)
    links = []
    from .range_reversal_backtest import svg_trade
    for i, row in enumerate(rows, 1):
        if row.get("outcome") == "CANCELLED":
            continue
        stem = "trade_%03d_%s_%s" % (i, row["local_date"], row["direction"].lower())
        name = stem + ".svg"; (gallery / name).write_text(svg_trade(row, minutes), encoding="utf-8")
        links.append((row, name))
    page = ["<!doctype html><meta charset='utf-8'><title>Apr-Jun Range Reversal validation</title>",
            "<style>body{font-family:-apple-system,sans-serif;max-width:1450px;margin:auto}li{margin:24px 0}img{width:100%;border:1px solid #ddd}.pass{color:#087f23}.excluded{color:#a33}</style>",
            "<h1>Range Reversal Apr-Jun 2025 · all baseline checked trades</h1>",
            "<p>Filter: range_width_price_pct ≤ 1.246290688786655202027240847 and breakout_to_e3_min ≤ 50. Commission 0%; adverse slippage 0.02% per side already included in fills. Rejected rows are shadow baseline outcomes and do not create another daily signal.</p><ol>"]
    for row, name in links:
        status = row.get("filter_reason", "")
        cls = "pass" if status == "PASS" else "excluded"
        page.append("<li><b>%s %s</b> · <span class='%s'>%s</span> · E3 %s · exit %s · %s<br><a href='gallery/%s'>open SVG</a><br><img src='gallery/%s'></li>" % (row["local_date"], row["direction"], cls, status, row.get("e3_time", ""), row.get("exit_time", ""), row.get("outcome_reason", ""), name, name))
    page.append("</ol>"); (out / "index.html").write_text("\n".join(page), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(); p.add_argument("--minutes", required=True); p.add_argument("--output-dir", required=True); p.add_argument("--start-day", default="2025-04-01"); p.add_argument("--end-day", default="2025-06-30"); args = p.parse_args()
    minutes = read_csv(Path(args.minutes)); start, end = date.fromisoformat(args.start_day), date.fromisoformat(args.end_day); out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    ranges, episodes, signals, m5 = detect_v2(minutes, "N3", start, end)
    complete_local_day = local_day_completeness(minutes, start, end)
    for rng in ranges:
        if not complete_local_day.get(rng["local_date"], False):
            rng["complete"] = "False"; rng["reason"] = "INCOMPLETE_LOCAL_DAY"; rng["required_local_end_utc"] = iso(datetime.fromisoformat(rng["local_date"]).replace(tzinfo=LOCAL_OFFSET) + timedelta(days=1))
    episodes = [r for r in episodes if complete_local_day.get(r.get("local_date"), False)]
    signals = [r for r in signals if complete_local_day.get(r.get("local_date"), False)]
    write_csv(out / "daily_ranges.csv", ranges); write_csv(out / "episodes_and_signals.csv", episodes); write_csv(out / "n3_signals.csv", signals)
    annotated, _ = annotate(signals, minutes); rows = annotated["BREAKOUT_EXTREMUM_FIRST_RETURN"]
    features = [feature_row(row) for row in rows]; fby = {r["episode_key"]: r for r in features}
    for row in rows: row.update(fby[episode_key(row)])
    all_trades = run_variant(rows, minutes, target_mode=VALIDATION_TARGET_MODE, commission_rate=Decimal("0"))
    for row in all_trades: row.update(fby[episode_key(row)])
    baseline = [r for r in all_trades if r.get("delayed_status") == "ANNOTATION"]
    accepted = [r for r in baseline if r["filter_reason"] == "PASS"]
    excluded = [r for r in baseline if r["filter_reason"] == "FILTER_EXCLUDED"]
    write_csv(out / "all_candidates.csv", rows); write_csv(out / "baseline_trades.csv", baseline); write_csv(out / "filtered_trades.csv", accepted); write_csv(out / "excluded_shadow_baseline.csv", excluded)
    write_csv(out / "filter_features.csv", features)
    summaries = {"baseline": metrics(baseline), "filtered": metrics(accepted), "excluded_shadow_baseline": metrics(excluded)}
    for k, vals in (("baseline", baseline), ("filtered", accepted), ("excluded_shadow_baseline", excluded)):
        add_r_summaries(summaries[k], vals)
        summaries[k]["max_drawdown_cumulative_net_r"] = max_drawdown_r(vals)
        write_csv(out / ("monthly_%s.csv" % k), grouped([dict(r, month=r["local_date"][:7]) for r in vals], ["month"]))
        write_csv(out / ("direction_%s.csv" % k), grouped(vals, ["direction"]))
    write_csv(out / "monthly_baseline.csv", grouped([dict(r, month=r["local_date"][:7]) for r in baseline], ["month"]))
    gallery_all(all_trades, minutes, out / "gallery_all_trades")
    config = {"strategy": "range_reversal_v2_delayed_N3_mode_A", "period_start_local": args.start_day, "period_end_local": args.end_day, "minutes": args.minutes, "confirmation": "N3; exact existing reset/opposite-boundary/missing-M5/local-midnight rules", "entry": "E3 open after third consecutive inside close", "stop": "BREAKOUT_EXTREMUM_FIRST_RETURN", "target": "fixed 2R from actual E3 entry fill", "commission_per_side": "0", "adverse_slippage_per_side": "0.0002", "filter": {"formula": "(range_upper - range_lower) / E3 entry_fill * 100", "range_width_price_pct_units": "percent", "range_width_price_pct_max": str(WIDTH_LIMIT), "breakout_to_e3_min_max": str(DELAY_LIMIT), "known_at": "E3"}, "daily_policy": "one detector episode per local day; filter rejection cannot search for another signal", "short_model": "hypothetical price model on Spot OHLCV; no borrowing/funding/short account", "source_data": "official Binance Spot monthly klines; March included only as prehistory; July-December not opened", "counts": {"complete_days": sum(r["complete"] == "True" for r in ranges), "skipped_days": sum(r["complete"] != "True" for r in ranges), "episodes": len(episodes), "n3_signals": len(signals), "baseline_eligible": len(baseline), "filtered_accepted": len(accepted), "excluded": len(excluded)}}
    (out / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8"); (out / "metrics.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    lines = ["# Range Reversal Apr-Jun 2025 independent validation", "", "Commission 0%; adverse slippage 0.02% per side is included once in fills. This is a unit-size price model, not account equity. SHORT is hypothetical on Spot OHLCV.", "", "|Run|eligible|TARGET|STOP|EOD|mean win R|mean loss R|mean net R|win rate|profit factor|total net R|max cumulative-R drawdown|", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ("baseline", "filtered", "excluded_shadow_baseline"):
        m = summaries[name]
        lines.append("|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|" % (name, m["checked_trades"], m["target"], m["stop"], m["end_of_day"], m["mean_win_r"], m["mean_loss_r"], m["mean_net_r"], m["win_rate_net"], m["profit_factor_net"], m["total_net_r"], m["max_drawdown_cumulative_net_r"]))
    lines += ["", "Filter is evaluated only for delayed-eligible E3 rows. Excluded shadow outcomes are descriptive and do not enter the filtered run or permit another same-day signal."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"counts": config["counts"], "metrics": summaries}, indent=2))

if __name__ == "__main__": main()
