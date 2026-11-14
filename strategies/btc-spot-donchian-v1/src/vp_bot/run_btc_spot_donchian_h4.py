"""BASE_20D versus H4_CONFIRM_D1_CHANNEL research run."""
import argparse, json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .btc_spot_donchian_v1 import (SCENARIOS, Filters, D, _empty_trade, _entry_plan,
    _sell, aggregate_daily, indicators, iso, parse_time, read_csv, run_scenario,
    scenario_metrics, write_csv)
from .run_btc_spot_donchian_entry10d import attribution, closed, build_pair_gallery

UTC=timezone.utc

def aggregate_h4(minutes):
    groups={}
    for row in minutes:
        t=parse_time(row["open_time"]); start=t.replace(hour=(t.hour//4)*4, minute=0, second=0, microsecond=0)
        groups.setdefault(start,[]).append(row)
    out=[]
    for start in sorted(groups):
        rows=sorted(groups[start],key=lambda r:r["open_time"]); expected=[start+timedelta(minutes=i) for i in range(240)]; actual=[parse_time(r["open_time"]) for r in rows]
        out.append({"open_time":iso(start),"close_time":iso(start+timedelta(hours=4)),"date":start.date().isoformat(),"open":rows[0]["open"],"high":str(max(D(r["high"]) for r in rows)),"low":str(min(D(r["low"]) for r in rows)),"close":rows[-1]["close"],"volume":str(sum((D(r["volume"]) for r in rows),Decimal("0"))),"complete":actual==expected,"minute_count":len(rows)})
    return out

def _trade(position, result, scenario):
    trade=_empty_trade(position["signal"],scenario); trade.update(result); trade.update({"scenario":scenario.name,"signal_date":position["signal"].get("signal_date",position["signal"].get("h4_close_time","")),"h4_signal_start":position["signal"].get("h4_start",""),"h4_signal_close":position["signal"].get("h4_close_time",""),"upper":position["signal"].get("upper",""),"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); return trade

def run_h4_scenario(minutes,daily,period_start,period_end,scenario,filters=Filters()):
    start=datetime.fromisoformat(period_start).replace(tzinfo=UTC); end=datetime.fromisoformat(period_end).replace(tzinfo=UTC); by_minute={parse_time(r["open_time"]):r for r in minutes}; daily_i=indicators(daily); daily_by={r["date"]:r for r in daily_i}; h4=aggregate_h4(minutes)
    contexts=[]; prev_b=None
    for bar in h4:
        d=date.fromisoformat(bar["date"]); close_t=parse_time(bar["close_time"]); atr_day=(close_t-timedelta(microseconds=1)).date().isoformat(); di=daily_by.get(bar["date"]); ai=daily_by.get(atr_day); ready=bool(di and ai and di.get("ready") and ai.get("ready") and bar.get("complete")); upper=di.get("upper","") if ready else ""; b=(D(bar["close"])>D(upper)) if ready else None
        contexts.append({"bar":bar,"upper":upper,"atr":ai.get("atr","") if ready else "","lower":ai.get("lower","") if ready else "","b":b,"b_previous":prev_b,"ready":ready,"atr_day":atr_day}); prev_b=b if b is not None else prev_b
    context_by_close={parse_time(x["bar"]["close_time"]):x for x in contexts}; signal_rows=[]; trades=[]; equity=[]; cash=D("10000"); btc=D("0"); position=None; pending=None; planned_exit=None; last_time=None; previous_minute=None; last_event="NONE"; period_minutes=[r for r in minutes if start<=parse_time(r["open_time"])<end]
    for row in period_minutes:
        t=parse_time(row["open_time"]); last_time=t
        if previous_minute is not None and t>previous_minute+timedelta(minutes=1) and position is not None:
            tr=_empty_trade(position["signal"],scenario); tr.update({"status":"DATA_INCOMPLETE","exit_reason":"DATA_INCOMPLETE","signal_date":position["signal"].get("h4_close_time",""),"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); trades.append(tr); return {"scenario":scenario.name,"signals":signal_rows,"trades":trades,"equity":equity,"final_cash":str(cash),"final_btc":str(btc),"final_equity":str(cash+D(row["close"])*btc)}
        previous_minute=t; is_0000=t.hour==0 and t.minute==0; is_0001=t.hour==0 and t.minute==1; is_last=t.hour==23 and t.minute==59; is_h4_close=t.minute==0 and t.hour in (0,4,8,12,16,20); is_h4_entry_minute=t.minute==1 and t.hour in (0,4,8,12,16,20)
        if is_0000 and position is not None:
            prev_day=(t-timedelta(microseconds=1)).date().isoformat(); di=daily_by.get(prev_day)
            if di and di.get("ready") and D(di["close"])<D(di["lower"]): planned_exit=t+timedelta(minutes=1)
        ctx=context_by_close.get(t)
        if ctx is not None and start<=t<end:
            b=ctx["b"]; sig={"scenario":scenario.name,"signal_date":ctx["bar"]["date"],"h4_start":ctx["bar"]["open_time"],"h4_close_time":ctx["bar"]["close_time"],"upper":ctx["upper"],"lower":ctx["lower"],"atr":ctx["atr"],"atr_day":ctx["atr_day"],"close":ctx["bar"]["close"],"b":str(b),"b_previous":str(ctx["b_previous"]),"b_transition":"False","status":"NO_SIGNAL","cancel_reason":"","decision_reason":"","prior_event":last_event}
            if not ctx["ready"]: sig.update({"status":"CANCELLED","cancel_reason":"INSUFFICIENT_H4_DAILY_HISTORY"})
            elif planned_exit is not None or position is not None: sig.update({"status":"BLOCKED_OPEN_POSITION","cancel_reason":"POSITION_OPEN_OR_EXIT_PENDING"})
            elif pending is not None: sig.update({"status":"CANCELLED","cancel_reason":"PENDING_ENTRY_EXISTS"})
            elif b and ctx["b_previous"] is False:
                stop=D(ctx["bar"]["close"])-D("2")*D(ctx["atr"]); sig["b_transition"]="True"
                if stop<=0: sig.update({"status":"CANCELLED","cancel_reason":"NONPOSITIVE_STOP"})
                else: sig.update({"status":"SIGNAL_PENDING","stop":str(stop),"decision_reason":"NEW_H4_TRANSITION"}); pending=sig
            elif b: sig["cancel_reason"]="NO_NEW_TRANSITION"
            else: sig["cancel_reason"]="B_FALSE"
            sig["decision_reason"]=sig.get("decision_reason") or sig.get("cancel_reason") or sig.get("status") or "NO_SIGNAL"; signal_rows.append(sig)
        if is_h4_close and pending is not None:
            plan,reason=_entry_plan(pending,row,by_minute.get(t+timedelta(minutes=1)),cash,scenario,filters); pending["entry_plan_reason"]=reason
            if plan is not None: pending["entry_plan"]=plan
            else: pending["status"]="CANCELLED"; pending["cancel_reason"]=reason; trades.append(_empty_trade(pending,scenario)); last_event="CANCELLED:"+reason; pending=None
        if is_h4_entry_minute and pending is not None and pending.get("entry_plan") is not None and position is None:
            plan=pending["entry_plan"]
            if plan["quote"]>cash: pending["status"]="CANCELLED"; pending["cancel_reason"]="INSUFFICIENT_CASH_AT_FILL"; trades.append(_empty_trade(pending,scenario)); last_event="CANCELLED:INSUFFICIENT_CASH_AT_FILL"; pending=None
            else:
                entry_fill=D(row["open"])*(D("1")+scenario.a); q=plan["q"]; fee=q*scenario.fee_buy; received=q-fee; position={"entry_time":t,"entry_fill":entry_fill,"stop":plan["stop"],"q":q,"btc_received":received,"quote_order_amount":plan["quote"],"commission_buy_btc":fee,"risk_budget_usdt":D("0.005")*cash,"signal":pending}; cash-=plan["quote"]; btc+=received; pending["status"]="EXECUTED"; pending["entry_time"]=iso(t); pending["entry_fill"]=str(entry_fill); pending["quantity_ordered"]=str(q); pending["btc_received"]=str(received); pending=None
        if position is not None:
            if planned_exit is not None and t==planned_exit:
                result=_sell(position,D(row["open"]),t,"LOWER_CHANNEL_EXIT",scenario); cash+=D(result["net_pnl_usdt"])+position["quote_order_amount"]; btc-=position["btc_received"]; trades.append(_trade(position,result,scenario)); position=None; planned_exit=None; last_event="EXIT:LOWER_CHANNEL_EXIT"
            else:
                op,low=D(row["open"]),D(row["low"]); open_stop=op<=position["stop"]; low_stop=low<=position["stop"]
                if open_stop or low_stop: result=_sell(position,op if open_stop else position["stop"],t,"STOP_GAP" if open_stop else "STOP",scenario); cash+=D(result["net_pnl_usdt"])+position["quote_order_amount"]; btc-=position["btc_received"]; trades.append(_trade(position,result,scenario)); position=None; planned_exit=None; last_event="EXIT:"+result["exit_reason"]
                elif t>=position["entry_time"]+timedelta(days=60): result=_sell(position,op,t,"TIME_EXIT",scenario); cash+=D(result["net_pnl_usdt"])+position["quote_order_amount"]; btc-=position["btc_received"]; trades.append(_trade(position,result,scenario)); position=None; planned_exit=None; last_event="EXIT:TIME_EXIT"
        equity.append({"time":iso(t),"cash_usdt":str(cash),"btc":str(btc),"close":row["close"],"equity_usdt":str(cash+btc*D(row["close"])),"position_open":str(position is not None)})
    if position is not None and last_time is not None:
        row=by_minute[last_time]; result=_sell(position,D(row["open"]),last_time,"END_OF_TEST",scenario); cash+=D(result["net_pnl_usdt"])+position["quote_order_amount"]; btc-=position["btc_received"]; trades.append(_trade(position,result,scenario))
    return {"scenario":scenario.name,"signals":signal_rows,"trades":trades,"equity":equity,"final_cash":str(cash),"final_btc":str(btc),"final_equity":str(cash+btc*D(period_minutes[-1]["close"])) if period_minutes else str(cash)}

def run_case(minutes,daily,start,end,out,name):
    case=Path(out)/name; results={}; rows=[]
    for variant in ("BASE_20D","H4_CONFIRM_D1_CHANNEL"):
        for scenario in SCENARIOS:
            result=run_scenario(minutes,daily,start,end,scenario,Filters()) if variant=="BASE_20D" else run_h4_scenario(minutes,daily,start,end,scenario,Filters()); results[(variant,scenario.name)]=result; dest=case/variant/scenario.name; dest.mkdir(parents=True,exist_ok=True); write_csv(dest/"signals.csv",result["signals"]); write_csv(dest/"trades.csv",result["trades"]); write_csv(dest/"equity.csv",result["equity"])
            m=scenario_metrics(result); m.update({"case":name,"variant":variant,"turnover_usdt":str(sum((D(t.get("quote_order_amount") or 0)+D(t.get("exit_base") or 0)*D(t.get("btc_received") or 0) for t in closed(result["trades"])),Decimal("0")))}) ; rows.append(m)
            if variant=="H4_CONFIRM_D1_CHANNEL": write_csv(dest/"h4_entries.csv",[s for s in result["signals"] if s.get("status") in ("SIGNAL_PENDING","EXECUTED")])
    case.mkdir(parents=True,exist_ok=True); write_csv(case/"metrics.csv",rows)
    for s in SCENARIOS: write_csv(case/(s.name+"_attribution.csv"),attribution(results[("BASE_20D",s.name)]["trades"],results[("H4_CONFIRM_D1_CHANNEL",s.name)]["trades"]))
    b=closed(results[("BASE_20D","BASE")]["trades"]); h=closed(results[("H4_CONFIRM_D1_CHANNEL","BASE")]["trades"]); pairs=[(t,next((x for x in h if x.get("entry_time")==t.get("entry_time")),None)) for t in b]
    for t in h:
        if not any(p[1] and p[1].get("entry_time")==t.get("entry_time") for p in pairs): pairs.append((None,t))
    build_pair_gallery(pairs,daily,case/"comparative_gallery",labels=("BASE_20D","H4_CONFIRM_D1_CHANNEL")); return rows

def main():
    p=argparse.ArgumentParser(); p.add_argument("--minutes",default="data/processed/btcusdt_1m_2017-08_2025-06_recovered.csv"); p.add_argument("--output-dir",default="reports/btc_spot_donchian_h4_confirm_comparison"); args=p.parse_args(); minutes=read_csv(args.minutes); daily=aggregate_daily(minutes); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); all_rows=[]; inventory=read_csv("reports/btc_spot_donchian_v1_recovery_segments/segment_inventory.csv")
    for rec in inventory:
        if rec.get("qualifies_with_20_day_warmup")!="True" or date.fromisoformat(rec["start"])>=date(2025,1,1): continue
        sd,ed=date.fromisoformat(rec["start"]),date.fromisoformat(rec["end"]); d=[r for r in daily if sd<=date.fromisoformat(r["date"])<=ed]; rows=[r for r in minutes if sd<=parse_time(r["open_time"]).date()<=ed]; all_rows+=run_case(rows,d,f"{sd}T00:00:00",f"{ed+timedelta(days=1)}T00:00:00",out,f"segment_{int(rec['segment']):03d}_{sd}_{ed}")
    jd=[r for r in daily if date.fromisoformat(r["date"])<=date(2025,6,30)]; jr=[r for r in minutes if date(2024,12,1)<=parse_time(r["open_time"]).date()<=date(2025,6,30)]; all_rows+=run_case(jr,jd,"2025-01-01T00:00:00","2025-07-01T00:00:00",out,"jan_jun_2025"); write_csv(out/"comparison_metrics.csv",all_rows)
    (out/"run_config.json").write_text(json.dumps({"strategy":"H4_CONFIRM_D1_CHANNEL","control":"BASE_20D","daily_channel":"U=max high previous 20 complete D1; fixed at UTC day start for all six H4 bars","h4_signal":"close_H4>U(day) and previous H4 b false; previous H4 uses own U","atr":"SMA ATR20 from latest complete D1 at H4 close","execution":"first complete minute after H4 close checked, next minute open executed","exit":"same daily lower-10 channel, fixed stop, 60 calendar days, END_OF_TEST","periods":"all qualifying pre-2025 segments plus Jan-Jun 2025; July-Dec 2025 excluded","scenarios":"same ZERO/BASE/STRESS; same observations, not independent samples"},indent=2)+"\n",encoding="utf-8"); links=[f"<li><a href='{p.name}/comparative_gallery/gallery/index.html'>{p.name}</a></li>" for p in sorted(out.iterdir()) if p.is_dir() and (p/"comparative_gallery/gallery/index.html").exists()]; (out/"index.html").write_text("<!doctype html><meta charset='utf-8'><title>BASE_20D vs H4_CONFIRM_D1_CHANNEL</title><h1>BASE_20D vs H4_CONFIRM_D1_CHANNEL</h1><p>Full graph is default; daily channel and H4 confirmation are shown.</p><a href='comparison_metrics.csv'>Metrics</a><ul>"+"".join(links)+"</ul>",encoding="utf-8")
if __name__=="__main__": main()
