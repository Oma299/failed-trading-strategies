"""BTC_SPOT_DONCHIAN_V1: daily Donchian trend-following research model.

This module is intentionally independent from the project's older strategies.
It models one long Spot position, cash/BTC accounting, and minute execution.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
import csv, html, json, math

getcontext().prec = 40
UTC = timezone.utc
ZERO = Decimal("0")
ONE = Decimal("1")

def D(value): return Decimal(str(value))
def parse_time(value): return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
def iso(value): return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
def date_of(value): return parse_time(value).date()

@dataclass(frozen=True)
class Scenario:
    name: str
    fee_buy: Decimal
    fee_sell: Decimal
    half_spread: Decimal
    extra_slippage: Decimal

    @property
    def a(self): return self.half_spread + self.extra_slippage

SCENARIOS = (
    Scenario("DIAGNOSTIC_ZERO", D("0"), D("0"), D("0"), D("0")),
    Scenario("BASE", D("0.001"), D("0.001"), D("0.0001"), D("0.0002")),
    Scenario("STRESS", D("0.001"), D("0.001"), D("0.0002"), D("0.0008")),
)

@dataclass(frozen=True)
class Filters:
    # Conditional model values, not historical Binance filters.
    tick_size: Decimal = D("0.01")
    step_size: Decimal = D("0.000001")
    min_qty: Decimal = D("0")
    max_qty: Decimal = D("Infinity")
    min_notional: Decimal = D("0")

def floor_step(value, step):
    value, step = D(value), D(step)
    if step <= ZERO: raise ValueError("step must be positive")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

def floor_tick(value, tick): return floor_step(value, tick)

def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def aggregate_daily(minutes):
    groups = {}
    for row in minutes:
        t = parse_time(row["open_time"]); day = t.date()
        groups.setdefault(day, []).append(row)
    daily = []
    for day in sorted(groups):
        rows = sorted(groups[day], key=lambda r: r["open_time"])
        start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        expected = [start + timedelta(minutes=i) for i in range(1440)]
        actual = [parse_time(r["open_time"]) for r in rows]
        complete = actual == expected
        daily.append({
            "date": day.isoformat(), "open_time": iso(start),
            "close_time": iso(start + timedelta(days=1) - timedelta(microseconds=1)),
            "open": rows[0]["open"], "high": str(max(D(r["high"]) for r in rows)),
            "low": str(min(D(r["low"]) for r in rows)), "close": rows[-1]["close"],
            "volume": str(sum((D(r["volume"]) for r in rows), ZERO)),
            "source_minute_count": len(rows), "complete": complete,
        })
    return daily

def data_quality(minutes, daily):
    times = [parse_time(r["open_time"]) for r in minutes]
    duplicates = sum(1 for i in range(1, len(times)) if times[i] == times[i - 1])
    gaps = []
    for a, b in zip(times, times[1:]):
        cursor = a + timedelta(minutes=1)
        while cursor < b:
            gaps.append(iso(cursor)); cursor += timedelta(minutes=1)
    return {
        "minute_count": len(minutes), "minute_start": iso(times[0]) if times else None,
        "minute_end": iso(times[-1]) if times else None, "duplicate_adjacent_count": duplicates,
        "out_of_order_count": sum(a > b for a, b in zip(times, times[1:])),
        "missing_minute_count": len(gaps), "missing_minutes_sample": gaps[:20],
        "daily_count": len(daily), "incomplete_utc_days": [r["date"] for r in daily if not r["complete"]],
        "first_full_day": next((r["date"] for r in daily if r["complete"]), None),
        "last_full_day": next((r["date"] for r in reversed(daily) if r["complete"]), None),
    }

def indicators(daily, entry_window=20, exit_window=10, atr_window=20):
    out = []
    for i, row in enumerate(daily):
        item = dict(row); item.update({"upper": "", "lower": "", "tr": "", "atr": "", "b": "", "ready": False})
        history_start = i - max(entry_window, exit_window, atr_window)
        consecutive_days = all(datetime.fromisoformat(daily[j]["date"]).date() == datetime.fromisoformat(daily[j - 1]["date"]).date() + timedelta(days=1) for j in range(history_start + 1, i + 1)) if history_start >= 0 else False
        valid_history = i >= max(entry_window, exit_window, atr_window) and consecutive_days and all(daily[j]["complete"] for j in range(history_start, i + 1))
        if valid_history:
            item["upper"] = str(max(D(daily[j]["high"]) for j in range(i-entry_window, i)))
            item["lower"] = str(min(D(daily[j]["low"]) for j in range(i-exit_window, i)))
            prev_close = D(daily[i-1]["close"])
            hi, lo, cl = D(row["high"]), D(row["low"]), D(row["close"])
            item["tr"] = str(max(hi-lo, abs(hi-prev_close), abs(lo-prev_close)))
            trs = [D(daily[j]["tr"]) if daily[j].get("tr") else None for j in range(i-atr_window+1, i)]
            # Build TR directly so this function remains correct when called once.
            trs = []
            for j in range(i-atr_window+1, i+1):
                prev = D(daily[j-1]["close"])
                h, l = D(daily[j]["high"]), D(daily[j]["low"])
                trs.append(max(h-l, abs(h-prev), abs(l-prev)))
            item["atr"] = str(sum(trs, ZERO) / D(atr_window))
            item["b"] = D(row["close"]) > D(item["upper"])
            item["ready"] = True
        out.append(item)
    return out

def _empty_trade(signal, scenario):
    return {"scenario": scenario.name, "signal_date": signal.get("signal_date", ""), "status": "CANCELLED", "cancel_reason": "", "entry_time": "", "entry_fill": "", "stop": signal.get("stop", ""), "quantity_ordered": "", "btc_received": "", "quote_order_amount": "", "exit_time": "", "exit_fill": "", "exit_reason": "", "gross_pnl_usdt": "", "net_pnl_usdt": "", "risk_budget_usdt": "", "r": "", "commission_buy_btc": "", "commission_sell_usdt": "", "execution_cost_usdt": "", "duration_hours": "", "ambiguous": "False"}

def _sell(position, base_price, time, reason, scenario, stop=False, ambiguous=False):
    price = D(base_price) * (ONE - scenario.a)
    proceeds_gross = price * position["btc_received"]
    fee_sell = proceeds_gross * scenario.fee_sell
    proceeds_net = proceeds_gross - fee_sell
    net = proceeds_net - position["quote_order_amount"]
    return {"status": "CLOSED", "exit_time": iso(time), "exit_fill": str(price), "exit_base": str(base_price), "exit_reason": reason, "gross_pnl_usdt": str(proceeds_gross - position["quote_order_amount"]), "net_pnl_usdt": str(net), "commission_sell_usdt": str(fee_sell), "execution_cost_usdt": str(abs(D(base_price)-price) * position["btc_received"]), "duration_hours": str((time-position["entry_time"]).total_seconds()/3600), "r": str(net / position["risk_budget_usdt"]) if position["risk_budget_usdt"] else "", "ambiguous": str(bool(ambiguous))}

def _entry_plan(signal, minute0, minute1, cash, scenario, filters):
    if minute0 is None: return None, "MISSING_00_00_MINUTE"
    if minute1 is None: return None, "MISSING_00_01_MINUTE"
    p, volume = D(minute0["close"]), D(minute0["volume"])
    stop = floor_tick(D(signal["stop"]), filters.tick_size)
    if p <= D(signal["upper"]): return None, "P_NOT_ABOVE_UPPER"
    if p <= stop: return None, "P_NOT_ABOVE_STOP"
    phat, shat = p*(ONE+scenario.a), stop*(ONE-scenario.a)
    d = phat - (ONE-scenario.fee_buy)*(ONE-scenario.fee_sell)*shat
    if d <= ZERO: return None, "NONPOSITIVE_RISK_DENOMINATOR"
    equity = cash
    q_raw = min(D("0.005")*equity/d, D("0.99")*cash/phat, D("0.01")*volume)
    q = floor_step(q_raw, filters.step_size)
    quote = q*phat
    if q < filters.min_qty or q > filters.max_qty: return None, "QTY_FILTER"
    if quote < filters.min_notional: return None, "MIN_NOTIONAL_FILTER"
    if q <= ZERO or quote <= ZERO: return None, "ZERO_ORDER"
    return {"p": p, "volume": volume, "stop": stop, "phat": phat, "shat": shat, "d": d, "q": q, "quote": quote}, ""

def run_scenario(minutes, daily, period_start, period_end, scenario, filters=Filters(), initial_cash=D("10000"), entry_window=20, daily_rearm=False):
    by_minute = {parse_time(r["open_time"]): r for r in minutes}
    daily_i = indicators(daily, entry_window=entry_window, exit_window=10, atr_window=20)
    day_by_date = {r["date"]: r for r in daily_i}
    start = datetime.fromisoformat(period_start).replace(tzinfo=UTC); end = datetime.fromisoformat(period_end).replace(tzinfo=UTC)
    period_minutes = [r for r in minutes if start <= parse_time(r["open_time"]) < end]
    signal_rows, trades, equity_rows = [], [], []
    cash, btc = initial_cash, ZERO
    position = None; pending_signal = None; planned_exit = None; previous_b = None; last_event = "NONE"
    # The first decision in the requested period still has a prior closed D1
    # available from warmup.  Seed B_(t-1) from that day so the first allowed
    # signal is a genuine false -> true transition; do not infer it from an
    # uninitialized period-local state.
    first_period_day = start.date()
    prior_rows = [r for r in daily_i if datetime.fromisoformat(r["date"]).date() < first_period_day and r.get("ready")]
    if prior_rows:
        previous_b = bool(prior_rows[-1]["b"])
    last_time = None
    for row in period_minutes:
        t = parse_time(row["open_time"]); last_time = t
        if last_time is not None and 'previous_minute_time' in locals() and t > previous_minute_time + timedelta(minutes=1) and position is not None:
            trade = _empty_trade(position["signal"], scenario); trade.update({"status":"DATA_INCOMPLETE", "cancel_reason":"MISSING_MINUTE_DURING_POSITION", "exit_reason":"DATA_INCOMPLETE", "scenario":scenario.name, "signal_date":position["signal"]["signal_date"], "entry_time":iso(position["entry_time"]), "entry_fill":str(position["entry_fill"]), "stop":str(position["stop"]), "quantity_ordered":str(position["q"]), "btc_received":str(position["btc_received"]), "quote_order_amount":str(position["quote_order_amount"]), "commission_buy_btc":str(position["commission_buy_btc"]), "risk_budget_usdt":str(position["risk_budget_usdt"])})
            trades.append(trade)
            return {"scenario":scenario.name,"signals":signal_rows,"trades":trades,"equity":equity_rows,"final_cash":str(cash),"final_btc":str(btc),"final_equity":str(cash+btc*D(row["close"]))}
        previous_minute_time = t
        day = t.date().isoformat(); is_0000 = t.hour == 0 and t.minute == 0; is_0001 = t.hour == 0 and t.minute == 1; is_last = t.hour == 23 and t.minute == 59
        closed_this_minute = False
        # The minute 00:00 is known before the 00:01 order is sent.
        if is_0000 and pending_signal is not None:
            plan, reason = _entry_plan(pending_signal, row, by_minute.get(t + timedelta(minutes=1)), cash, scenario, filters)
            pending_signal["entry_plan_reason"] = reason
            if plan is not None: pending_signal["entry_plan"] = plan
            else:
                pending_signal["status"] = "CANCELLED"; pending_signal["cancel_reason"] = reason
                trades.append(_empty_trade(pending_signal, scenario)); pending_signal = None
                last_event = "CANCELLED:" + reason
        # Entry is sent only on 00:01, never using this minute to size it.
        if is_0001 and pending_signal is not None and pending_signal.get("entry_plan") is not None and position is None:
            plan = pending_signal["entry_plan"]; q = plan["q"]; fee_buy_btc = q*scenario.fee_buy; received = q-fee_buy_btc
            if plan["quote"] > cash: pending_signal["status"]="CANCELLED"; pending_signal["cancel_reason"]="INSUFFICIENT_CASH_AT_FILL"; trades.append(_empty_trade(pending_signal,scenario)); pending_signal=None; last_event="CANCELLED:INSUFFICIENT_CASH_AT_FILL"
            else:
                entry_fill = D(row["open"])*(ONE+scenario.a); risk_budget = D("0.005")*cash
                position = {"entry_time":t,"entry_fill":entry_fill,"stop":plan["stop"],"q":q,"btc_received":received,"quote_order_amount":plan["quote"],"commission_buy_btc":fee_buy_btc,"risk_budget_usdt":risk_budget,"signal":pending_signal}
                cash -= plan["quote"]; btc += received
                pending_signal["status"]="EXECUTED"; pending_signal["entry_time"]=iso(t); pending_signal["entry_fill"]=str(entry_fill); pending_signal["quantity_ordered"]=str(q); pending_signal["btc_received"]=str(received)
                pending_signal=None
        if position is not None:
            # A scheduled channel sale occurs at the open of its minute. If it
            # has not happened at the open, later OHLC in that minute is not
            # allowed to manufacture a second sale.
            if planned_exit is not None and t == planned_exit:
                result = _sell(position, D(row["open"]), t, "LOWER_CHANNEL_EXIT", scenario)
                cash += D(result["net_pnl_usdt"]) + position["quote_order_amount"]
                btc -= position["btc_received"]; trade = _empty_trade(position["signal"], scenario); trade.update(result); trade.update({"scenario":scenario.name,"signal_date":position["signal"]["signal_date"],"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); trades.append(trade); position=None; planned_exit=None; closed_this_minute=True; last_event="EXIT:"+result["exit_reason"]
            else:
                op, low = D(row["open"]), D(row["low"])
                open_stop = op <= position["stop"]; low_stop = low <= position["stop"]
                if open_stop or low_stop:
                    base = op if open_stop else position["stop"]; result = _sell(position, base, t, "STOP_GAP" if open_stop else "STOP", scenario, stop=True, ambiguous=False)
                    cash += D(result["net_pnl_usdt"]) + position["quote_order_amount"]; btc -= position["btc_received"]
                    trade = _empty_trade(position["signal"],scenario); trade.update(result); trade.update({"scenario":scenario.name,"signal_date":position["signal"]["signal_date"],"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); trades.append(trade); position=None; planned_exit=None; closed_this_minute=True; last_event="EXIT:"+result["exit_reason"]
                elif t >= position["entry_time"] + timedelta(days=60):
                    result = _sell(position, op, t, "TIME_EXIT", scenario)
                    cash += D(result["net_pnl_usdt"]) + position["quote_order_amount"]; btc -= position["btc_received"]
                    trade = _empty_trade(position["signal"],scenario); trade.update(result); trade.update({"scenario":scenario.name,"signal_date":position["signal"]["signal_date"],"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); trades.append(trade); position=None; planned_exit=None; closed_this_minute=True; last_event="EXIT:TIME_EXIT"
        # Daily decisions are made only after the complete 23:59 minute.
        if is_last:
            di = day_by_date.get(day)
            if di is not None and start.date() <= t.date() < end.date():
                b = di.get("b") if di.get("ready") else None
                sig = {"scenario":scenario.name,"signal_date":day,"upper":di.get("upper",""),"lower":di.get("lower",""),"atr":di.get("atr",""),"close":di.get("close",""),"b":str(b),"b_previous":str(previous_b),"b_transition":"False","entry_mode":"DAILY_REARM" if daily_rearm else "BASE_20D","prior_event":last_event,"status":"NO_SIGNAL","cancel_reason":"","decision_reason":""}
                if not di.get("ready"): sig["status"]="CANCELLED"; sig["cancel_reason"]="INSUFFICIENT_DAILY_HISTORY"
                elif closed_this_minute:
                    sig["status"]="BLOCKED_EXIT_PRIORITY"; sig["cancel_reason"]="EXIT_PRIORITY_AT_DAILY_CLOSE"
                elif position is not None:
                    sig["status"]="BLOCKED_OPEN_POSITION"; sig["cancel_reason"]="POSITION_OPEN"
                    if D(di["close"]) < D(di["lower"]):
                        planned_exit = datetime.fromisoformat(di["date"]).replace(tzinfo=UTC) + timedelta(days=1, minutes=1)
                        sig["planned_exit_time"] = iso(planned_exit); sig["channel_exit_trigger"] = "True"
                elif pending_signal is not None: sig["status"]="CANCELLED"; sig["cancel_reason"]="PENDING_ENTRY_EXISTS"
                elif b and (daily_rearm or previous_b is False):
                    if not daily_rearm: sig["b_transition"] = "True"
                    stop = D(di["close"])-D("2")*D(di["atr"])
                    if stop <= ZERO: sig["status"]="CANCELLED"; sig["cancel_reason"]="NONPOSITIVE_STOP"
                    else:
                        sig.update({"status":"SIGNAL_PENDING","stop":str(stop),"rearm_signal":"True" if daily_rearm else "False","decision_reason":"DAILY_REARM_B_TRUE" if daily_rearm else ""}); pending_signal=sig
                elif b and previous_b is True: sig["cancel_reason"]="NO_NEW_TRANSITION"
                elif not b: sig["cancel_reason"]="B_FALSE"
                sig["decision_reason"] = sig.get("decision_reason") or sig.get("cancel_reason") or sig.get("status") or "NO_SIGNAL"
                signal_rows.append(sig); previous_b = bool(b) if b is not None else None
        equity = cash + btc*D(row["close"])
        equity_rows.append({"time":iso(t),"cash_usdt":str(cash),"btc":str(btc),"close":row["close"],"equity_usdt":str(equity),"position_open":str(position is not None)})
    if position is not None:
        if last_time is None: reason = "DATA_INCOMPLETE"
        else:
            row = by_minute[last_time]; result = _sell(position, D(row["open"]), last_time, "END_OF_TEST", scenario)
            cash += D(result["net_pnl_usdt"]) + position["quote_order_amount"]; btc -= position["btc_received"]
            trade = _empty_trade(position["signal"],scenario); trade.update(result); trade.update({"scenario":scenario.name,"signal_date":position["signal"]["signal_date"],"entry_time":iso(position["entry_time"]),"entry_fill":str(position["entry_fill"]),"stop":str(position["stop"]),"quantity_ordered":str(position["q"]),"btc_received":str(position["btc_received"]),"quote_order_amount":str(position["quote_order_amount"]),"commission_buy_btc":str(position["commission_buy_btc"]),"risk_budget_usdt":str(position["risk_budget_usdt"])}); trades.append(trade); position=None
    return {"scenario":scenario.name,"signals":signal_rows,"trades":trades,"equity":equity_rows,"final_cash":str(cash),"final_btc":str(btc),"final_equity":str(cash+btc*D(period_minutes[-1]["close"])) if period_minutes else str(cash)}

def buy_and_hold(minutes, period_start, period_end, scenario, initial_cash=D("10000")):
    start, end = datetime.fromisoformat(period_start).replace(tzinfo=UTC), datetime.fromisoformat(period_end).replace(tzinfo=UTC)
    rows=[r for r in minutes if start<=parse_time(r["open_time"])<end]; first0=next((r for r in rows if parse_time(r["open_time"]).hour==0 and parse_time(r["open_time"]).minute==0),None); first1=next((r for r in rows if parse_time(r["open_time"]).hour==0 and parse_time(r["open_time"]).minute==1),None); last=rows[-1] if rows else None
    if not first0 or not first1 or not last: return {"status":"DATA_INCOMPLETE"}
    quote=initial_cash*D("0.99"); buy_fill=D(first1["open"])*(ONE+scenario.a); gross_btc=quote/buy_fill; btc=gross_btc*(ONE-scenario.fee_buy); sell_fill=D(last["open"])*(ONE-scenario.a); proceeds=btc*sell_fill*(ONE-scenario.fee_sell); final=initial_cash-quote+proceeds
    return {"status":"COMPLETE","scenario":scenario.name,"quote_buy":str(quote),"btc_received":str(btc),"sell_fill":str(sell_fill),"final_cash":str(final),"net_pnl_usdt":str(final-initial_cash),"return_pct":str((final/initial_cash-ONE)*100)}

def max_drawdown(rows):
    peak=ZERO; dd=ZERO
    for row in rows:
        equity=D(row["equity_usdt"]); peak=max(peak,equity); dd=max(dd,peak-equity)
    return dd

def scenario_metrics(result, initial_cash=D("10000")):
    trades=[t for t in result["trades"] if t.get("status")=="CLOSED"]; pnls=[D(t["net_pnl_usdt"]) for t in trades]; pos=[p for p in pnls if p>ZERO]; neg=[p for p in pnls if p<ZERO]; rs=[D(t["r"]) for t in trades if t.get("r")]
    exposure=sum((D(r["btc"])>ZERO for r in result["equity"]),0); total=len(result["equity"])
    fees_buy=sum((D(t["commission_buy_btc"])*D(t["entry_fill"]) for t in trades),ZERO); fees_sell=sum((D(t["commission_sell_usdt"]) for t in trades),ZERO)
    daily={}
    for row in result["equity"]:
        daily[row["time"][:10]]=row
    daily_rows=list(daily.values())
    monthly={}
    yearly={}
    for row in daily_rows:
        monthly[row["time"][:7]]=row
        yearly[row["time"][:4]]=row
    monthly_out={month:{"month_end_equity_usdt":row["equity_usdt"],"month_end_cash_usdt":row["cash_usdt"],"month_end_btc":row["btc"]} for month,row in monthly.items()}
    yearly_out={year:{"year_end_equity_usdt":row["equity_usdt"],"year_end_cash_usdt":row["cash_usdt"],"year_end_btc":row["btc"],"max_daily_drawdown_usdt":str(max_drawdown([r for r in daily_rows if r["time"][:4]==year]))} for year,row in yearly.items()}
    cancel_reasons={reason:sum(s.get("cancel_reason")==reason for s in result["signals"]) for reason in sorted(set(s.get("cancel_reason") for s in result["signals"]) - {""})}
    return {"scenario":result["scenario"],"trades":len(trades),"signals":sum(s["status"] in ("SIGNAL_PENDING","EXECUTED") for s in result["signals"]),"wins":sum(p>ZERO for p in pnls),"losses":sum(p<ZERO for p in pnls),"win_rate":str(D(sum(p>ZERO for p in pnls))/D(len(pnls))) if pnls else "","mean_net_pnl_usdt":str(sum(pnls,ZERO)/D(len(pnls))) if pnls else "","sum_net_pnl_usdt":str(sum(pnls,ZERO)),"profit_factor":str(sum(pos,ZERO)/abs(sum(neg,ZERO))) if neg else "","return_pct":str((D(result["final_equity"])/initial_cash-ONE)*100),"final_equity_usdt":result["final_equity"],"max_drawdown_usdt":str(max_drawdown(result["equity"])),"max_daily_drawdown_usdt":str(max_drawdown(daily_rows)),"time_in_market_fraction":str(D(exposure)/D(total)) if total else "","mean_r":str(sum(rs,ZERO)/D(len(rs))) if rs else "","sum_r":str(sum(rs,ZERO)),"commission_buy_usdt_equivalent":str(fees_buy),"commission_sell_usdt":str(fees_sell),"exit_reasons":{reason:sum(t.get("exit_reason")==reason for t in trades) for reason in sorted(set(t.get("exit_reason") for t in trades))},"cancel_reasons":cancel_reasons,"monthly_mark_to_market":monthly_out,"yearly_mark_to_market":yearly_out}

def write_csv(path, rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); fields=sorted({k for r in rows for k in r}) if rows else []
    with path.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)

def svg_trade(trade, daily, mode="full"):
    entry=date_of(trade["entry_time"]); exit_day=date_of(trade.get("exit_time") or trade["entry_time"]); start=entry-timedelta(days=30); end=exit_day+timedelta(days=10); rows=[r for r in daily if start<=datetime.fromisoformat(r["date"]).date()<=end and r.get("complete")];
    if mode=="before": rows=[r for r in rows if datetime.fromisoformat(r["date"]).date()<=entry]
    values=[D(r["high"]) for r in rows]+[D(r["low"]) for r in rows]+[D(trade["stop"]),D(trade["entry_fill"])]
    lo,hi=min(values),max(values); pad=max((hi-lo)*D("0.08"),D(1)); lo-=pad; hi+=pad; left,top,w,h=90,70,1200,430
    def x(day): return left+((day-start).total_seconds()/86400)*w/max((end-start).total_seconds()/86400,1)
    def y(v): return top+float((hi-D(v))/(hi-lo))*h
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="600" style="font-family:Arial"><rect width="100%" height="100%" fill="white"/><text x="20" y="28" font-size="18" font-weight="bold">BTC_SPOT_DONCHIAN_V1 · {html.escape(trade["scenario"])} · {html.escape(trade["exit_reason"] or "open")}</text><text x="20" y="48" font-size="11">D1 UTC · LONG Spot · no take-profit · full context by default</text><rect x="90" y="70" width="1200" height="430" fill="#fafafa" stroke="#bbb"/>']
    for r in rows:
        day=datetime.fromisoformat(r["date"]).date(); xx=x(day); color="#15803d" if D(r["close"])>=D(r["open"]) else "#b91c1c"; opacity="0.3" if mode=="full" and trade.get("exit_time") and day>exit_day else "1"; p.append(f'<g opacity="{opacity}"><line x1="{xx:.1f}" y1="{y(r["high"]):.1f}" x2="{xx:.1f}" y2="{y(r["low"]):.1f}" stroke="{color}"/><line x1="{xx:.1f}" y1="{y(r["open"]):.1f}" x2="{xx:.1f}" y2="{y(r["close"]):.1f}" stroke="{color}" stroke-width="4"/></g>')
        if r.get("upper"): p.append(f'<line x1="{xx-12:.1f}" y1="{y(r["upper"]):.1f}" x2="{xx+12:.1f}" y2="{y(r["upper"]):.1f}" stroke="#2563eb" stroke-width="2"/><line x1="{xx-12:.1f}" y1="{y(r["lower"]):.1f}" x2="{xx+12:.1f}" y2="{y(r["lower"]):.1f}" stroke="#7c3aed" stroke-width="2"/>')
    for v,label,color in ((trade["stop"],"S0","#dc2626"),(trade["entry_fill"],"entry","#111827")):
        p.append(f'<line x1="{left}" y1="{y(v)}" x2="{left+w}" y2="{y(v)}" stroke="{color}" stroke-dasharray="6 4"/><text x="{left+w-110}" y="{y(v)-4}" fill="{color}" font-size="11">{label} {D(v):.2f}</text>')
    if trade.get("exit_time") and mode=="full":
        ex=date_of(trade["exit_time"]); p.append(f'<line x1="{x(ex):.1f}" y1="{top}" x2="{x(ex):.1f}" y2="{top+h}" stroke="#111" stroke-dasharray="2 3"/>')
    p.append(f'<text x="20" y="550" font-size="11">signal {trade.get("signal_date","")} · entry {trade.get("entry_time","")} fill {trade.get("entry_fill","")} · exit {trade.get("exit_time","")} fill {trade.get("exit_fill","")} · {trade.get("exit_reason","")} · gross {trade.get("gross_pnl_usdt","")} USDT · net {trade.get("net_pnl_usdt","")} USDT · R {trade.get("r","")}</text></svg>')
    return "".join(p)

def build_gallery(trades, daily, out):
    gallery=Path(out); gallery.mkdir(parents=True,exist_ok=True); links=[]
    for i,t in enumerate(trades,1):
        stem=f"trade_{i:03d}_{t['scenario']}_{t.get('signal_date','unknown')}"; (gallery/(stem+"_full.svg")).write_text(svg_trade(t,daily,"full"),encoding="utf-8"); (gallery/(stem+"_before.svg")).write_text(svg_trade(t,daily,"before"),encoding="utf-8"); links.append((t,stem))
    page=["<!doctype html><meta charset='utf-8'><title>BTC_SPOT_DONCHIAN_V1 gallery</title><style>body{font-family:-apple-system,sans-serif;max-width:1320px;margin:auto}li{margin:22px}img{width:100%;border:1px solid #ddd}button{padding:7px 12px}</style>","<h1>BTC_SPOT_DONCHIAN_V1</h1><p>Full graph is shown by default. Before entry is an explicit toggle. No future result is shown in before mode.</p><ol>"]
    for t,s in links: page.append(f"<li><b>{t['scenario']} · signal {t.get('signal_date','')} · exit {t.get('exit_reason','')}</b><br><button data-mode='full' data-id='{s}' onclick=\"toggle(this)\">Before entry</button><span> Full graph</span><br><img id='img_{s}' src='{s}_full.svg' data-full='{s}_full.svg' data-before='{s}_before.svg' alt='Full graph'></li>")
    page.append("</ol><script>function toggle(b){const i=document.getElementById('img_'+b.dataset.id),before=b.dataset.mode==='full';i.src=before?i.dataset.before:i.dataset.full;i.alt=before?'Before entry':'Full graph';b.dataset.mode=before?'before':'full';b.textContent=before?'Full graph':'Before entry';b.nextElementSibling.textContent=before?' Before entry':' Full graph';}</script>")
    (gallery/"index.html").write_text("\n".join(page),encoding="utf-8")
