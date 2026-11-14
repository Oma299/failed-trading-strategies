"""Run the V1 chronological backtest without downloading data."""

import argparse
import csv
import json
from pathlib import Path
from datetime import date

from .backtest import simulate_backtest, write_outputs


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", default="data/processed/btcusdt_1h_2024-12_2025-01.csv")
    parser.add_argument("--minutes", default="data/processed/btcusdt_1m_2024-12_2025-01.csv")
    parser.add_argument("--profiles", default="data/processed/aggtrades_january/daily_profiles.csv")
    parser.add_argument("--output-dir", default="reports/backtest_v1_january")
    parser.add_argument("--start-day", default="2025-01-01")
    parser.add_argument("--end-day", default="2025-01-31")
    parser.add_argument("--profit-lock", choices=("baseline", "A", "B"), default="baseline")
    parser.add_argument("--max-return-bars", type=int, default=3)
    parser.add_argument("--poc-protection", action="store_true", help="keep the position open at POC and activate the fixed post-POC stop")
    args = parser.parse_args()
    start_day, end_day = date.fromisoformat(args.start_day), date.fromisoformat(args.end_day)
    lock_config = {"name": "baseline", "enabled": False, "reason_labels": True} if args.profit_lock == "baseline" else {"name": args.profit_lock, "enabled": True, "trigger_fraction": "0.30", "stop_fraction": "0.10" if args.profit_lock == "A" else "0.15", "reason_labels": True}
    if args.max_return_bars < 1:
        parser.error("--max-return-bars must be at least 1")
    if args.poc_protection and args.profit_lock != "baseline":
        parser.error("--poc-protection cannot be combined with profit_lock A/B")
    poc_config = {"enabled": True, "buffer_atr": "0.25", "stop_effective": "next_minute_open"} if args.poc_protection else None
    result = simulate_backtest(read_csv(Path(args.hours)), read_csv(Path(args.minutes)), read_csv(Path(args.profiles)), start_day, end_day, lock_config, args.max_return_bars, poc_config)
    result.metrics["return_window_bars"] = args.max_return_bars
    config = {"hours": args.hours, "minutes": args.minutes, "profiles": args.profiles, "period_start": "%sT00:00:00Z" % start_day, "period_end_exclusive": "%sT00:00:00Z" % (end_day.fromordinal(end_day.toordinal() + 1)), "profile_source": "binance_spot_aggtrades", "profile_method": "aggtrades", "max_return_bars": args.max_return_bars, "profit_lock": lock_config}
    if poc_config is not None:
        config["poc_protection"] = poc_config
    write_outputs(result, Path(args.output_dir), config)
    print("events=%d candidates=%d entered=%d trades=%d skipped=%d incomplete=%s net_pnl=%s final_capital=%s" % (result.metrics["event_count"], result.metrics["candidate_count"], result.metrics["entered_trade_count"], result.metrics["trade_count"], result.metrics["skipped_entry_count"], result.incomplete, result.metrics["net_pnl"], result.metrics["final_capital"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
