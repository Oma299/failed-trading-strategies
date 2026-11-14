"""Reproducible BTC_SPOT_DONCHIAN_V1 research run."""
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from .btc_spot_donchian_v1 import (Filters, SCENARIOS, aggregate_daily, buy_and_hold,
    data_quality, indicators, max_drawdown, read_csv, run_scenario, scenario_metrics,
    write_csv, build_gallery)

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--minutes",default="data/processed/btcusdt_1m_2024-12_2025-06.csv"); p.add_argument("--output-dir",default="reports/btc_spot_donchian_v1"); p.add_argument("--start",default="2025-01-01T00:00:00"); p.add_argument("--end",default="2025-07-01T00:00:00"); args=p.parse_args()
    minutes=read_csv(args.minutes); daily=aggregate_daily(minutes); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    quality=data_quality(minutes,daily); (out/"data_quality.json").write_text(json.dumps(quality,indent=2,ensure_ascii=False)+"\n")
    ind=indicators(daily); write_csv(out/"daily_indicators.csv",ind)
    filters=Filters(); config={"strategy":"BTC_SPOT_DONCHIAN_V1","symbol":"BTCUSDT","spot":"LONG only, no leverage, no shorts, no pyramiding","data_file":args.minutes,"data_sha256":sha256(args.minutes),"period_start_utc":args.start,"period_end_utc":args.end,"warmup":"All rows before the requested period are warmup only; signals require 20 complete prior days and ATR20 including the current complete day; no July-December 2025 data","initial_cash_usdt":"10000","signal":"D1 UTC; U=max high previous 20 complete days; D=min low previous 10 complete days; ATR=SMA20 TR including current day; B=close>U; entry only B false to true","entry":"P=00:00 close, V=00:00 base volume, execute 00:01 open with a","exit":"fixed S0 or close<D planned for next day 00:01 or 60*24h or END_OF_TEST; no take-profit","filters":{"tick_size":"0.01","step_size":"0.000001","min_qty":"0","max_qty":"Infinity","min_notional":"0","note":"conditional model values, not reconstructed historical Binance filters"},"scenarios":[{"name":s.name,"fee_buy":str(s.fee_buy),"fee_sell":str(s.fee_sell),"half_spread":str(s.half_spread),"extra_slippage":str(s.extra_slippage),"a":str(s.a)} for s in SCENARIOS]}
    (out/"run_config.json").write_text(json.dumps(config,indent=2,ensure_ascii=False)+"\n")
    all_metrics=[]; all_trades=[]; all_signals=[]; all_equity=[]
    for s in SCENARIOS:
        result=run_scenario(minutes,daily,args.start,args.end,s,filters)
        write_csv(out/(s.name+"_signals.csv"),result["signals"]); write_csv(out/(s.name+"_trades.csv"),result["trades"]); write_csv(out/(s.name+"_equity.csv"),result["equity"])
        m=scenario_metrics(result); m["buy_and_hold"]=buy_and_hold(minutes,args.start,args.end,s); all_metrics.append(m)
        daily_rows={row["time"][:10]:row for row in result["equity"]}
        write_csv(out/(s.name+"_daily_equity.csv"),list(daily_rows.values()))
        all_trades.extend(result["trades"]); all_signals.extend(result["signals"]); all_equity.extend([{**r,"scenario":s.name} for r in result["equity"]])
        valid=[t for t in result["trades"] if t.get("status")=="CLOSED"]
        build_gallery(valid,daily,out/"gallery"/s.name)
    write_csv(out/"signals.csv",all_signals); write_csv(out/"trades.csv",all_trades); write_csv(out/"equity.csv",all_equity)
    write_csv(out/"balance_reconciliation.csv",[{"scenario":m["scenario"],"initial_cash_usdt":"10000","final_equity_usdt":m["final_equity_usdt"],"sum_net_pnl_usdt":m["sum_net_pnl_usdt"],"max_drawdown_usdt":m["max_drawdown_usdt"],"max_daily_drawdown_usdt":m["max_daily_drawdown_usdt"],"commission_buy_usdt_equivalent":m["commission_buy_usdt_equivalent"],"commission_sell_usdt":m["commission_sell_usdt"],"time_in_market_fraction":m["time_in_market_fraction"]} for m in all_metrics])
    (out/"gallery"/"index.html").write_text("<!doctype html><meta charset='utf-8'><title>BTC_SPOT_DONCHIAN_V1 galleries</title><h1>BTC_SPOT_DONCHIAN_V1 galleries</h1><ul>" + "".join(f"<li><a href='{s.name}/index.html'>{s.name}</a></li>" for s in SCENARIOS) + "</ul>", encoding="utf-8")
    report={"strategy":"BTC_SPOT_DONCHIAN_V1","period":{"start":args.start,"end":args.end},"data_quality":quality,"scenarios":all_metrics,"comparison":{"cash_hold_usdt":"10000","buy_and_hold_definition":"99% initial quote allocation at 00:01 with scenario costs; sell at last minute open"},"limitations":["January-June 2025 is an already researched period, not an independent validation.","July-December 2025 was not loaded or analyzed.","Historical Binance filters are not reconstructed; conditional tick/step values are recorded in run_config.","OHLCV cannot reconstruct bid/ask depth or intraminute order beyond the specified stop convention."]}
    (out/"metrics.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    lines=["# BTC_SPOT_DONCHIAN_V1 research run", "", f"Period: `{args.start}` — `{args.end}`. Existing December 2024 data is warmup only; July–December 2025 was not analyzed.", "", f"Data: `{quality['minute_count']}` minutes, `{quality['daily_count']}` UTC days, missing minutes `{quality['missing_minute_count']}`, incomplete days `{len(quality['incomplete_utc_days'])}`.", "", "## Scenarios", "", "| Scenario | Trades | Signals | Win rate | Net PnL USDT | Return | PF | Max DD USDT | Time in market |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for m in all_metrics: lines.append(f"| {m['scenario']} | {m['trades']} | {m['signals']} | {m['win_rate']} | {m['sum_net_pnl_usdt']} | {m['return_pct']}% | {m['profit_factor']} | {m['max_daily_drawdown_usdt']} | {m['time_in_market_fraction']} |")
    lines += ["", "R is defined as net trade PnL divided by the planned risk budget `0.5% × equity before entry`; this is not a guarantee of maximum loss. There is no TARGET exit in this strategy.", "", "Exit reasons and monthly mark-to-market tables are available in the scenario CSVs and equity files. Results are descriptive and do not establish profitability."]
    (out/"report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"data_quality":quality,"scenarios":all_metrics},indent=2,ensure_ascii=False))
if __name__=="__main__": main()
