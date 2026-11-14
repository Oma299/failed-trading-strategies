"""Chronological V1 execution model on existing hourly and minute OHLCV."""

import csv
from dataclasses import dataclass, asdict, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .atr import compute_wilder_atr
from .signals import EpisodeEvent, DailySignalSummary, detect_events

getcontext().prec = 40

ZERO = Decimal("0")
ONE = Decimal("1")
BUY_SLIPPAGE = Decimal("0.0002")
SELL_SLIPPAGE = Decimal("0.0002")
COMMISSION = Decimal("0.001")
RISK_FRACTION = Decimal("0.005")
INITIAL_CAPITAL = Decimal("1000")
EPSILON = Decimal("1e-24")


def dec(value) -> Decimal:
    return Decimal(str(value))


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fingerprint_config(config: Dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Trade:
    trade_id: str
    event_id: str
    signal_day: str
    profile_date: str
    profile_available_at: str
    episode_start_time: str
    confirmation_time: str
    entry_time: str
    exit_time: str
    val: Decimal
    poc: Decimal
    vah: Decimal
    atr: Decimal
    episode_low: Decimal
    stop: Decimal
    target: Decimal
    entry_base_price: Decimal
    entry_fill: Decimal
    exit_base_price: Decimal
    exit_fill: Decimal
    quantity: Decimal
    equity_before_entry: Decimal
    cash_after_entry: Decimal
    buy_fee: Decimal
    sell_fee: Decimal
    gross_pnl: Decimal
    net_pnl: Decimal
    net_r: Decimal
    slippage_cost: Decimal
    stop_net_pnl_if_triggered: Decimal
    exit_reason: str
    ambiguity: bool
    time_exit_triggered: bool
    time_exit_also_stop: bool
    time_exit_also_target: bool
    incomplete_data: bool
    profit_lock_name: str = ""
    profit_lock_activated: bool = False
    profit_lock_trigger_time: str = ""
    profit_lock_effective_at: str = ""
    profit_lock_old_stop: Decimal = ZERO
    profit_lock_new_stop: Decimal = ZERO
    expected_target_net_pnl_at_entry: Decimal = ZERO
    poc_reached: bool = False
    poc_reach_time: str = ""
    poc_protection_effective_at: str = ""
    poc_protection_stop: Decimal = ZERO


@dataclass(frozen=True)
class BacktestResult:
    events: List[Dict[str, object]]
    summaries: List[DailySignalSummary]
    trades: List[Trade]
    equity: List[Dict[str, object]]
    metrics: Dict[str, object]
    incomplete: bool
    incomplete_reasons: List[str]


def calculate_position_size(equity: Decimal, cash: Decimal, entry_fill: Decimal, stop: Decimal) -> Decimal:
    if entry_fill <= stop:
        return ZERO
    risk_quantity = RISK_FRACTION * equity / (entry_fill - stop)
    cash_quantity = cash / (entry_fill * (ONE + COMMISSION))
    return max(ZERO, min(risk_quantity, cash_quantity))


def _minute_values(row: Dict[str, str]) -> Tuple[Decimal, Decimal, Decimal, Decimal, datetime]:
    return dec(row["open"]), dec(row["high"]), dec(row["low"]), dec(row["close"]), dt(row["open_time"])


def _exit_from_minutes(minutes: Sequence[Dict[str, str]], entry_time: datetime, stop: Decimal, target: Decimal, profit_lock: Optional[Dict[str, object]] = None, entry_fill: Optional[Decimal] = None, poc_protection: Optional[Dict[str, object]] = None, entry_atr: Optional[Decimal] = None) -> Dict[str, object]:
    expected = entry_time
    current_stop = stop
    pending_stop = None
    lock_info = {"activated": False, "trigger_time": "", "effective_at": "", "old_stop": stop, "new_stop": stop}
    use_poc_protection = bool(poc_protection and poc_protection.get("enabled", True))
    if use_poc_protection and entry_atr is None:
        raise ValueError("entry_atr is required for POC protection")
    poc_info = {"reached": False, "reach_time": "", "effective_at": "", "stop": stop}
    poc_stop_active = False
    pending_poc_stop = None
    trigger = None
    if profit_lock is not None and profit_lock.get("enabled", True):
        if entry_fill is None:
            raise ValueError("entry_fill is required for profit_lock")
        distance = target - entry_fill
        trigger = entry_fill + dec(profit_lock["trigger_fraction"]) * distance
        lock_info["new_stop_candidate"] = entry_fill + dec(profit_lock["stop_fraction"]) * distance

    def result(reason, time, base, ambiguity=False, time_exit=False, time_stop=False, time_target=False, incomplete=False):
        return {"incomplete": incomplete, "reason": reason, "time": iso(time), "base": base,
                "ambiguity": ambiguity, "time_exit": time_exit, "time_stop": time_stop,
                "time_target": time_target, "profit_lock": lock_info, "poc_protection": poc_info}

    def reach_poc(open_time):
        nonlocal pending_poc_stop
        if poc_info["reached"]:
            return
        new_stop = max(current_stop, target - dec(poc_protection["buffer_atr"]) * entry_atr)
        effective_at = open_time + timedelta(minutes=1)
        poc_info.update({"reached": True, "reach_time": iso(open_time), "effective_at": iso(effective_at), "stop": new_stop})
        pending_poc_stop = {"effective_at": effective_at, "new_stop": new_stop}

    for row in minutes:
        open_price, high, low, close, open_time = _minute_values(row)
        if open_time < entry_time:
            continue
        if open_time != expected:
            return result("DATA_GAP_DURING_POSITION", expected, ZERO, incomplete=True)
        if pending_stop is not None and open_time >= pending_stop["effective_at"]:
            current_stop = pending_stop["new_stop"]
            pending_stop = None
        if pending_poc_stop is not None and open_time >= pending_poc_stop["effective_at"]:
            current_stop = pending_poc_stop["new_stop"]
            pending_poc_stop = None
            poc_stop_active = True
        time_exit = open_time >= entry_time + timedelta(hours=24)
        open_stop, open_target = open_price <= current_stop, open_price >= target
        if time_exit:
            return result("TIME_LIMIT", open_time, open_price, time_exit=True, time_stop=open_stop, time_target=open_target)
        if open_stop:
            reason = "POC_PROTECTION_STOP" if poc_stop_active else ("PROFIT_LOCK_STOP" if lock_info["activated"] else ("INITIAL_STOP" if profit_lock is not None and profit_lock.get("reason_labels", False) else "STOP"))
            return result(reason, open_time, open_price)
        if open_target:
            if use_poc_protection:
                reach_poc(open_time)
            else:
                poc_info.update({"reached": True, "reach_time": iso(open_time)})
                return result("TARGET", open_time, open_price)
        hit_stop, hit_target = low <= current_stop, high >= target
        if hit_stop:
            reason = "POC_PROTECTION_STOP" if poc_stop_active else ("PROFIT_LOCK_STOP" if lock_info["activated"] else ("INITIAL_STOP" if profit_lock is not None and profit_lock.get("reason_labels", False) else "STOP"))
            return result(reason, open_time, current_stop, ambiguity=hit_target and not poc_info["reached"])
        if hit_target and not use_poc_protection:
            poc_info.update({"reached": True, "reach_time": iso(open_time)})
            return result("TARGET", open_time, target)
        if use_poc_protection and not poc_info["reached"] and hit_target:
            reach_poc(open_time)
        if trigger is not None and not lock_info["activated"] and high >= trigger:
            new_stop = max(current_stop, lock_info["new_stop_candidate"])
            lock_info.update({"activated": True, "trigger_time": iso(open_time), "effective_at": iso(open_time + timedelta(minutes=1)), "old_stop": current_stop, "new_stop": new_stop})
            pending_stop = {"effective_at": open_time + timedelta(minutes=1), "new_stop": new_stop}
        expected += timedelta(minutes=1)
    last = minutes[-1] if minutes else None
    if last is None:
        return result("NO_MINUTE_DATA", entry_time, ZERO, incomplete=True)
    _, _, _, close, last_time = _minute_values(last)
    if last_time < entry_time:
        return result("NO_MINUTE_DATA_AFTER_ENTRY", entry_time, ZERO, incomplete=True)
    return result("END_OF_DATA", last_time, close)


def _trade_from_event(event: EpisodeEvent, entry_row: Dict[str, str], future_minutes: Sequence[Dict[str, str]], equity: Decimal, cash: Decimal, trade_id: str, profit_lock: Optional[Dict[str, object]] = None, poc_protection: Optional[Dict[str, object]] = None) -> Tuple[Optional[Trade], str]:
    if event.atr is None or event.planned_stop is None or event.planned_entry_time is None:
        return None, "ATR_OR_ENTRY_LEVEL_UNAVAILABLE"
    entry_base = dec(entry_row["open"])
    entry_fill = entry_base * (ONE + BUY_SLIPPAGE)
    val, poc, stop = dec(event.val), dec(event.poc), dec(event.planned_stop)
    if not (val < entry_fill < poc):
        return None, "ENTRY_FILL_OUTSIDE_VAL_POC"
    if not stop < entry_fill:
        return None, "STOP_NOT_BELOW_ENTRY"
    quantity = calculate_position_size(equity, cash, entry_fill, stop)
    if quantity <= 0:
        return None, "ZERO_POSITION_SIZE"
    buy_fee = quantity * entry_fill * COMMISSION
    cash_after_entry = cash - quantity * entry_fill - buy_fee
    if cash_after_entry < -EPSILON:
        return None, "NEGATIVE_CASH"
    expected_target_fill = poc * (ONE - SELL_SLIPPAGE)
    expected_target_net = quantity * (expected_target_fill - entry_fill) - buy_fee - quantity * expected_target_fill * COMMISSION
    exit_info = _exit_from_minutes(future_minutes, dt(event.planned_entry_time), stop, poc, profit_lock, entry_fill, poc_protection, dec(event.atr))
    lock = exit_info.get("profit_lock", {})
    poc_state = exit_info.get("poc_protection", {})
    if exit_info["incomplete"]:
        trade = Trade(trade_id, event.event_id, event.day, event.profile_date, event.profile_available_at, event.episode_start_time, event.confirmation_time, event.planned_entry_time, exit_info["time"], val, poc, dec(event.vah), dec(event.atr), dec(event.episode_low), stop, poc, entry_base, entry_fill, ZERO, ZERO, quantity, equity, cash_after_entry, buy_fee, ZERO, ZERO, ZERO, ZERO, ZERO, exit_info["reason"], False, False, False, False, True)
        return replace(trade, profit_lock_name=str(profit_lock["name"]) if profit_lock else "", expected_target_net_pnl_at_entry=expected_target_net, poc_reached=bool(poc_state.get("reached")), poc_reach_time=str(poc_state.get("reach_time", "")), poc_protection_effective_at=str(poc_state.get("effective_at", "")), poc_protection_stop=dec(poc_state.get("stop", stop))), exit_info["reason"]
    exit_base = dec(exit_info["base"])
    exit_fill = exit_base * (ONE - SELL_SLIPPAGE)
    sell_fee = quantity * exit_fill * COMMISSION
    gross = quantity * (exit_fill - entry_fill)
    net = gross - buy_fee - sell_fee
    denominator = quantity * (entry_fill - stop)
    net_r = net / denominator if denominator else ZERO
    stop_base = stop
    stop_fill = stop_base * (ONE - SELL_SLIPPAGE)
    stop_net = quantity * (stop_fill - entry_fill) - buy_fee - quantity * stop_fill * COMMISSION
    slippage = quantity * (entry_fill - entry_base) + quantity * (exit_base - exit_fill)
    trade = Trade(trade_id, event.event_id, event.day, event.profile_date, event.profile_available_at, event.episode_start_time, event.confirmation_time, event.planned_entry_time, exit_info["time"], val, poc, dec(event.vah), dec(event.atr), dec(event.episode_low), stop, poc, entry_base, entry_fill, exit_base, exit_fill, quantity, equity, cash_after_entry, buy_fee, sell_fee, gross, net, net_r, slippage, stop_net, exit_info["reason"], bool(exit_info["ambiguity"]), bool(exit_info["time_exit"]), bool(exit_info["time_stop"]), bool(exit_info["time_target"]), False)
    return replace(trade, profit_lock_name=str(profit_lock["name"]) if profit_lock else "", profit_lock_activated=bool(lock.get("activated")), profit_lock_trigger_time=str(lock.get("trigger_time", "")), profit_lock_effective_at=str(lock.get("effective_at", "")), profit_lock_old_stop=dec(lock.get("old_stop", stop)), profit_lock_new_stop=dec(lock.get("new_stop", stop)), expected_target_net_pnl_at_entry=expected_target_net, poc_reached=bool(poc_state.get("reached")), poc_reach_time=str(poc_state.get("reach_time", "")), poc_protection_effective_at=str(poc_state.get("effective_at", "")), poc_protection_stop=dec(poc_state.get("stop", stop))), "ENTERED"


def _serialize(value):
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, datetime): return iso(value)
    return value


def _trade_dict(trade: Trade) -> Dict[str, object]:
    return {key: _serialize(value) for key, value in asdict(trade).items()}


def monthly_equity_metrics(equity_rows: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    """Summarize PnL from first/last minute-close equity within each calendar month."""
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in equity_rows:
        month = str(row["time"])[:7]
        grouped.setdefault(month, []).append(row)
    result = {}
    for month, rows in sorted(grouped.items()):
        start_equity, end_equity = dec(rows[0]["equity"]), dec(rows[-1]["equity"])
        result[month] = {
            "start_time": rows[0]["time"], "end_time": rows[-1]["time"],
            "start_equity": start_equity, "end_equity": end_equity,
            "net_pnl": end_equity - start_equity,
        }
    return result


def simulate_backtest(hourly_rows: Sequence[Dict[str, str]], minute_rows: Sequence[Dict[str, str]], profiles: Sequence[Dict[str, str]], start_day: date = date(2025, 1, 1), end_day: date = date(2025, 1, 31), profit_lock: Optional[Dict[str, object]] = None, max_return_bars: int = 3, poc_protection: Optional[Dict[str, object]] = None) -> BacktestResult:
    hours = sorted(hourly_rows, key=lambda row: row["open_time"])
    minutes = sorted(minute_rows, key=lambda row: row["open_time"])
    atr_points = compute_wilder_atr(hours)
    events, summaries = detect_events(hours, profiles, atr_points, start_day, end_day, max_return_bars)
    minute_by_open = {dt(row["open_time"]): row for row in minutes}
    jan_minutes = [row for row in minutes if start_day <= dt(row["open_time"]).date() <= end_day]
    trades: List[Trade] = []
    journal: List[Dict[str, object]] = []
    cash = INITIAL_CAPITAL
    equity = INITIAL_CAPITAL
    blocked_until: Optional[datetime] = None
    incomplete_reasons: List[str] = []
    for event in events:
        row = {key: value for key, value in asdict(event).items()}
        row["action"] = "NO_ENTRY"
        row["skip_reason"] = ""
        event_start = dt(event.episode_start_time)
        if blocked_until is not None and event_start < blocked_until:
            row["action"] = "SUPPRESSED_POSITION"
            row["skip_reason"] = "POSITION_OPEN_AT_EVENT_START"
            journal.append(row)
            continue
        if event.status != "RETURN_CONFIRMED":
            row["skip_reason"] = "EVENT_STATUS_" + event.status
            journal.append(row)
            continue
        entry_time = dt(event.planned_entry_time) if event.planned_entry_time else None
        if entry_time is None or (blocked_until is not None and entry_time < blocked_until):
            row["skip_reason"] = "POSITION_OPEN_AT_ENTRY"
            journal.append(row)
            continue
        entry_row = minute_by_open.get(entry_time)
        if entry_row is None:
            row["skip_reason"] = "MISSING_ENTRY_MINUTE"
            journal.append(row)
            continue
        entry_fill = dec(entry_row["open"]) * (ONE + BUY_SLIPPAGE)
        if not (dec(event.val) < entry_fill < dec(event.poc)):
            row["skip_reason"] = "ENTRY_FILL_OUTSIDE_VAL_POC"
            journal.append(row)
            continue
        future_minutes = [candidate for candidate in minutes if dt(candidate["open_time"]) >= entry_time]
        trade, reason = _trade_from_event(event, entry_row, future_minutes, equity, cash, "trade-%03d" % (len(trades) + 1), profit_lock, poc_protection)
        if trade is None:
            row["skip_reason"] = reason
            journal.append(row)
            continue
        row["action"] = "ENTERED" if not trade.incomplete_data else "ENTERED_INCOMPLETE"
        row["trade_id"] = trade.trade_id
        row["skip_reason"] = ""
        journal.append(row)
        trades.append(trade)
        if trade.incomplete_data:
            incomplete_reasons.append(trade.exit_reason)
            blocked_until = datetime.max.replace(tzinfo=timezone.utc)
            continue
        cash = cash + trade.net_pnl
        equity = cash
        blocked_until = dt(trade.exit_time)
    equity_rows: List[Dict[str, object]] = []
    for row in jan_minutes:
        timestamp = dt(row["open_time"])
        position = None
        current_cash = INITIAL_CAPITAL
        for trade in trades:
            if trade.incomplete_data: continue
            entry_timestamp, exit_timestamp = dt(trade.entry_time), dt(trade.exit_time)
            if timestamp < entry_timestamp:
                break
            if entry_timestamp <= timestamp < exit_timestamp:
                position = trade
                current_cash = trade.cash_after_entry
                break
            current_cash = trade.equity_before_entry + trade.net_pnl
        mark = dec(row["close"])
        quantity = position.quantity if position else ZERO
        mark_equity = current_cash + quantity * mark
        equity_rows.append({"time": row["open_time"], "cash": current_cash, "quantity": quantity, "mark_price": mark, "equity": mark_equity, "position": position.trade_id if position else ""})
    if trades and not trades[-1].incomplete_data:
        final_equity = cash
    elif trades and trades[-1].incomplete_data:
        final_equity = equity_rows[-1]["equity"] if equity_rows else equity
    else:
        final_equity = INITIAL_CAPITAL
    values = [dec(row["equity"]) for row in equity_rows] or [INITIAL_CAPITAL]
    peak = values[0]; max_dd = ZERO; max_dd_pct = ZERO
    for value in values:
        peak = max(peak, value); drawdown = peak - value; max_dd = max(max_dd, drawdown); max_dd_pct = max(max_dd_pct, drawdown / peak if peak else ZERO)
    completed = [trade for trade in trades if not trade.incomplete_data]
    wins = [trade for trade in completed if trade.net_pnl > 0]
    losses = [trade for trade in completed if trade.net_pnl < 0]
    total_net = sum((trade.net_pnl for trade in completed), ZERO)
    metrics = {"initial_capital": INITIAL_CAPITAL, "final_capital": final_equity, "net_pnl": total_net, "net_pnl_percent": total_net / INITIAL_CAPITAL * 100, "trade_count": len(completed), "entered_trade_count": len(trades), "candidate_count": sum(event.status == "RETURN_CONFIRMED" for event in events), "event_count": len(events), "skipped_entry_count": sum(row.get("skip_reason") not in ("", None) and row.get("status") == "RETURN_CONFIRMED" for row in journal), "win_count": len(wins), "loss_count": len(losses), "zero_trade_count": sum(trade.net_pnl == 0 for trade in completed), "win_rate_net": Decimal(len(wins)) / Decimal(len(completed)) * 100 if completed else ZERO, "average_trade_net": total_net / Decimal(len(completed)) if completed else ZERO, "average_net_r": sum((trade.net_r for trade in completed), ZERO) / Decimal(len(completed)) if completed else ZERO, "max_drawdown": max_dd, "max_drawdown_percent": max_dd_pct * 100, "commissions": sum((trade.buy_fee + trade.sell_fee for trade in completed), ZERO), "slippage_cost": sum((trade.slippage_cost for trade in completed), ZERO), "gross_pnl": sum((trade.gross_pnl for trade in completed), ZERO), "stop_net_pnl_if_triggered": sum((trade.stop_net_pnl_if_triggered for trade in completed), ZERO), "profit_factor": "N/A" if not losses else sum((trade.net_pnl for trade in wins), ZERO) / abs(sum((trade.net_pnl for trade in losses), ZERO)), "exit_reasons": {reason: sum(trade.exit_reason == reason for trade in completed) for reason in sorted(set(trade.exit_reason for trade in completed))}, "profit_lock_activated_count": sum(trade.profit_lock_activated for trade in completed), "profit_lock_stop_count": sum(trade.exit_reason == "PROFIT_LOCK_STOP" for trade in completed), "poc_reached_count": sum(trade.poc_reached for trade in completed), "poc_protection_stop_count": sum(trade.exit_reason == "POC_PROTECTION_STOP" for trade in completed), "expected_target_net_pnl_nonpositive_count": sum(trade.expected_target_net_pnl_at_entry <= ZERO for trade in completed), "monthly_equity": monthly_equity_metrics(equity_rows), "incomplete": bool(incomplete_reasons), "incomplete_reasons": incomplete_reasons}
    return BacktestResult(journal, summaries, trades, equity_rows, metrics, bool(incomplete_reasons), incomplete_reasons)


def write_outputs(result: BacktestResult, output_dir: Path, config: Dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    def write_csv(name, rows, fields):
        with (output_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    event_fields = sorted({key for row in result.events for key in row}) if result.events else [field for field in EpisodeEvent.__dataclass_fields__]
    write_csv("event_journal.csv", result.events, event_fields)
    trade_rows = [_trade_dict(trade) for trade in result.trades]
    write_csv("trades.csv", trade_rows, list(trade_rows[0]) if trade_rows else list(Trade.__dataclass_fields__))
    equity_rows = [{key: _serialize(value) for key, value in row.items()} for row in result.equity]
    write_csv("equity_curve.csv", equity_rows, ["time", "cash", "quantity", "mark_price", "equity", "position"])
    summary_rows = [{key: _serialize(value) for key, value in asdict(summary).items()} for summary in result.summaries]
    write_csv("daily_signal_summary.csv", summary_rows, list(summary_rows[0]) if summary_rows else list(DailySignalSummary.__dataclass_fields__))
    metrics = {key: _serialize(value) for key, value in result.metrics.items()}
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8")
    run_config = dict(config); run_config["config_fingerprint"] = fingerprint_config(config); run_config["model"] = {"buy_slippage": str(BUY_SLIPPAGE), "sell_slippage": str(SELL_SLIPPAGE), "commission": str(COMMISSION), "risk_fraction": str(RISK_FRACTION), "initial_capital": str(INITIAL_CAPITAL), "max_holding_hours": 24, "min_notional_and_step_size": "not modeled"}
    (output_dir / "run_config.json").write_text(json.dumps(run_config, indent=2, default=str) + "\n", encoding="utf-8")
