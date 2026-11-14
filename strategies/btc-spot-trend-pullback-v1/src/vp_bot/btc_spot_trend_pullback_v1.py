"""BTC_SPOT_TREND_PULLBACK_V1 research model.

The implementation is deliberately isolated from the Donchian and reversal
strategies.  It uses complete UTC M1/H1/H4 bars, Decimal accounting, and one
long Spot position per continuous data segment.
"""
from __future__ import annotations

import csv
import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path

getcontext().prec = 40
UTC = timezone.utc
ZERO = Decimal("0")
ONE = Decimal("1")


def D(value):
    return Decimal(str(value))


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def floor_step(value, step):
    value, step = D(value), D(step)
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


@dataclass(frozen=True)
class Scenario:
    name: str
    fee: Decimal
    full_spread: Decimal
    slippage: Decimal

    @property
    def half_spread(self):
        return self.full_spread / D("2")

    @property
    def adverse(self):
        return self.half_spread + self.slippage


SCENARIOS = (
    Scenario("ZERO", D("0"), D("0"), D("0")),
    Scenario("FEE_ONLY", D("0.001"), D("0"), D("0")),
    Scenario("BASE", D("0.001"), D("0.0001"), D("0.0002")),
    Scenario("ADVERSE", D("0.001"), D("0.0002"), D("0.0005")),
    Scenario("STRESS", D("0.0015"), D("0.0005"), D("0.001")),
)


@dataclass(frozen=True)
class Filters:
    tick_size: Decimal = D("0.01")
    step_size: Decimal = D("0.000001")
    min_qty: Decimal = D("0")
    max_qty: Decimal = D("Infinity")
    min_notional: Decimal = D("0")


def aggregate_bars(minutes, hours):
    """Aggregate only complete UTC bars; incomplete bars are retained as such."""
    interval_minutes = int(hours * 60)
    groups = {}
    for row in minutes:
        t = parse_time(row["open_time"])
        minute_of_day = t.hour * 60 + t.minute
        start_minute = minute_of_day // interval_minutes * interval_minutes
        start = t.replace(
            hour=start_minute // 60, minute=start_minute % 60,
            second=0, microsecond=0,
        )
        groups.setdefault(start, []).append(row)
    result = []
    for start in sorted(groups):
        rows = sorted(groups[start], key=lambda r: r["open_time"])
        expected = [start + timedelta(minutes=i) for i in range(interval_minutes)]
        actual = [parse_time(r["open_time"]) for r in rows]
        result.append({
            "open_time": iso(start), "close_time": iso(start + timedelta(minutes=interval_minutes)),
            "date": start.date().isoformat(), "open": rows[0]["open"],
            "high": str(max(D(r["high"]) for r in rows)),
            "low": str(min(D(r["low"]) for r in rows)), "close": rows[-1]["close"],
            "volume": str(sum((D(r["volume"]) for r in rows), ZERO)),
            "complete": actual == expected, "minute_count": len(rows),
        })
    return result


def aggregate_h1(minutes):
    return aggregate_bars(minutes, 1)


def aggregate_h4(minutes):
    return aggregate_bars(minutes, 4)


def aggregate_m15(minutes):
    return aggregate_bars(minutes, 0.25)


def m15_channel_candidate(m15, by_start, current_index, entry_time):
    """Return a strict eight-bar wick-low breakout after a full post-entry bar."""
    entry_time = parse_time(entry_time)
    if current_index is None:
        return None
    current = m15[current_index]
    if not current["complete"]:
        return None
    current_start = parse_time(current["open_time"])
    if current_start < entry_time:
        return None
    prior = []
    for offset in range(8, 0, -1):
        start = current_start - timedelta(minutes=15 * offset)
        index = by_start.get(start)
        if index is None or not m15[index]["complete"]:
            return None
        prior.append(m15[index])
    if any(
        parse_time(left["close_time"]) != parse_time(right["open_time"])
        for left, right in zip(prior, prior[1:])
    ) or parse_time(prior[-1]["close_time"]) != current_start:
        return None
    channel_low = min(D(row["low"]) for row in prior)
    if D(current["close"]) >= channel_low:
        return None
    return {"current": current, "prior": prior, "channel_low": channel_low}


def _bar_tr(row, previous_close):
    high, low = D(row["high"]), D(row["low"])
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def sma_atr(h1, window=20):
    out = [None] * len(h1)
    for i in range(1, len(h1)):
        if i < window or not all(h1[j]["complete"] for j in range(i - window + 1, i + 1)):
            continue
        trs = [_bar_tr(h1[j], D(h1[j - 1]["close"])) for j in range(i - window + 1, i + 1)]
        out[i] = sum(trs, ZERO) / D(window)
    return out


def rsi_wilder(h1, period=3):
    out = [None] * len(h1)
    if len(h1) <= period or not all(h1[i]["complete"] for i in range(period + 1)):
        return out
    gains = [max(D(h1[i]["close"]) - D(h1[i - 1]["close"]), ZERO) for i in range(1, period + 1)]
    losses = [max(D(h1[i - 1]["close"]) - D(h1[i]["close"]), ZERO) for i in range(1, period + 1)]
    avg_gain, avg_loss = sum(gains, ZERO) / D(period), sum(losses, ZERO) / D(period)

    def value(gain, loss):
        if gain == ZERO and loss == ZERO:
            return D("50")
        if loss == ZERO:
            return D("100")
        if gain == ZERO:
            return ZERO
        return D("100") * gain / (gain + loss)

    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(h1)):
        if not h1[i]["complete"]:
            continue
        gain = max(D(h1[i]["close"]) - D(h1[i - 1]["close"]), ZERO)
        loss = max(D(h1[i - 1]["close"]) - D(h1[i]["close"]), ZERO)
        avg_gain = (D(period - 1) * avg_gain + gain) / D(period)
        avg_loss = (D(period - 1) * avg_loss + loss) / D(period)
        out[i] = value(avg_gain, avg_loss)
    return out


def ema_h4_regime(h4, period=100, lag=6):
    ema = [None] * len(h4); regime = [None] * len(h4)
    if len(h4) < period:
        return ema, regime
    ema[period - 1] = sum((D(h4[i]["close"]) for i in range(period)), ZERO) / D(period)
    for i in range(period, len(h4)):
        ema[i] = D("2") / D(period + 1) * D(h4[i]["close"]) + (ONE - D("2") / D(period + 1)) * ema[i - 1]
    for i in range(period - 1 + lag, len(h4)):
        regime[i] = D(h4[i]["close"]) > ema[i] and ema[i] > ema[i - lag]
    return ema, regime


def quality_report(minutes):
    times = [parse_time(r["open_time"]) for r in minutes]
    gaps = []
    for a, b in zip(times, times[1:]):
        if b != a + timedelta(minutes=1):
            cursor = a + timedelta(minutes=1)
            while cursor < b:
                gaps.append(iso(cursor)); cursor += timedelta(minutes=1)
    return {
        "minute_count": len(minutes), "start": iso(times[0]) if times else None,
        "end": iso(times[-1]) if times else None,
        "duplicate_count": len(times) - len(set(times)),
        "out_of_order_count": sum(a >= b for a, b in zip(times, times[1:])),
        "missing_minute_count": len(gaps), "missing_minutes_sample": gaps[:20],
    }


def split_continuous_minutes(minutes, cutoff=datetime(2025, 7, 1, tzinfo=UTC)):
    """Split before the reserved cutoff; never bridge an absent minute."""
    segments, current, previous = [], [], None
    for row in minutes:
        t = parse_time(row["open_time"])
        if t >= cutoff:
            break
        if previous is not None and t != previous + timedelta(minutes=1):
            if current: segments.append(current)
            current = []
        current.append(row); previous = t
    if current: segments.append(current)
    return segments


def _sell_price(base, scenario):
    return D(base) * (ONE - scenario.adverse)


def _buy_price(base, scenario):
    return D(base) * (ONE + scenario.adverse)


def size_order(signal_close, stop, volume_60, cash, scenario, filters):
    """Return the largest valid gross quantity on the lot grid."""
    pb = _buy_price(signal_close, scenario); ps = _sell_price(stop, scenario)
    q_limit = min(D("0.01") * D(volume_60), D("0.95") * cash / pb)
    risk_budget = D("0.005") * cash
    unit_loss = pb - ps * (ONE - scenario.fee) * (ONE - scenario.fee)
    if unit_loss <= ZERO:
        return None
    q_limit = min(q_limit, risk_budget / unit_loss)
    q = floor_step(q_limit, filters.step_size)
    while q > ZERO:
        received = q * (ONE - scenario.fee)
        sell_qty = floor_step(received, filters.step_size)
        loss_plan = q * pb - sell_qty * ps * (ONE - scenario.fee)
        quote = q * pb
        if (sell_qty > ZERO and loss_plan <= risk_budget and quote <= cash and
                q >= filters.min_qty and q <= filters.max_qty and quote >= filters.min_notional):
            return {"q_gross": q, "q_received": received, "q_sell": sell_qty,
                    "dust": received - sell_qty, "buy_fill": pb,
                    "stop_fill": ps, "quote": quote, "risk_budget": risk_budget,
                    "loss_plan": loss_plan}
        q -= filters.step_size
    return None


def _trade_record(position, result, scenario):
    row = dict(position["signal"])
    row.update(result)
    row.update({"scenario": scenario.name, "status": result.get("status", "CLOSED"),
                "entry_time": iso(position["entry_time"]), "entry_fill": str(position["buy_fill"]),
                "stop": str(position["stop"]), "quantity_ordered": str(position["q_gross"]),
                "btc_received": str(position["q_sell"]), "dust_btc": str(position["dust"]),
                "quote_order_amount": str(position["quote"]),
                "commission_buy_btc": str(position["q_gross"] * scenario.fee),
                "risk_budget_usdt": str(position["risk_budget"]),
                "trade_R": result.get("trade_R", "")})
    return row


def _close_position(position, base_price, t, reason, scenario, ambiguous=False, stop_type=""):
    fill = _sell_price(base_price, scenario)
    gross_proceeds = position["q_sell"] * fill
    fee_sell = gross_proceeds * scenario.fee
    net = gross_proceeds - fee_sell - position["quote"]
    result = {"status": "CLOSED", "exit_time": iso(t), "exit_base": str(base_price),
              "exit_fill": str(fill), "exit_reason": reason,
              "gross_pnl_usdt": str(gross_proceeds - position["quote"]),
              "net_pnl_usdt": str(net), "commission_sell_usdt": str(fee_sell),
              "execution_cost_usdt": str(abs(D(base_price) - fill) * position["q_sell"]),
              "duration_hours": str((t - position["entry_time"]).total_seconds() / 3600),
              "ambiguous": str(bool(ambiguous)),
              "stop_type": stop_type,
              "trade_R": str(net / position["risk_budget"]) if position["risk_budget"] else ""}
    return result


def _daily_snapshots(equity_rows):
    result = {}
    for row in equity_rows:
        result[row["time"][:10]] = row
    return [result[key] for key in sorted(result)]


def prepare_segment(minutes, warmup_h4=300, include_m15=False):
    h1 = [r for r in aggregate_h1(minutes) if r["complete"]]
    h4 = [r for r in aggregate_h4(minutes) if r["complete"]]
    m15 = aggregate_m15(minutes) if include_m15 else []
    atr = sma_atr(h1); rsi = rsi_wilder(h1); ema, regime = ema_h4_regime(h4)
    h4_by_end = {parse_time(r["close_time"]): i for i, r in enumerate(h4)}
    h4_end_times = sorted(h4_by_end)
    h1_by_end = {parse_time(r["close_time"]): i for i, r in enumerate(h1)}
    m15_by_end = {parse_time(r["close_time"]): i for i, r in enumerate(m15)}
    m15_by_start = {parse_time(r["open_time"]): i for i, r in enumerate(m15)}
    warmup_end = parse_time(h4[warmup_h4 - 1]["close_time"]) if len(h4) >= warmup_h4 else None
    return {"h1": h1, "h4": h4, "m15": m15, "m15_by_end": m15_by_end,
            "m15_by_start": m15_by_start, "atr": atr, "rsi": rsi, "ema": ema,
            "regime": regime, "h4_by_end": h4_by_end, "h4_end_times": h4_end_times,
            "h1_by_end": h1_by_end, "warmup_end": warmup_end}


def run_segment(minutes, start, end, scenario, filters=Filters(), warmup_h4=300, prepared=None,
                rsi_exit=True, one_shot_protection=False, m15_channel_exit_n8=False):
    """Run one continuous segment with a separate account and warmup."""
    start, end = parse_time(start), parse_time(end)
    by_minute = {parse_time(r["open_time"]): r for r in minutes}
    prepared = prepared or prepare_segment(minutes, warmup_h4, include_m15=m15_channel_exit_n8)
    if m15_channel_exit_n8 and not prepared.get("m15"):
        m15 = aggregate_m15(minutes)
        prepared["m15"] = m15
        prepared["m15_by_end"] = {parse_time(r["close_time"]): i for i, r in enumerate(m15)}
        prepared["m15_by_start"] = {parse_time(r["open_time"]): i for i, r in enumerate(m15)}
    h1, h4 = prepared["h1"], prepared["h4"]
    m15 = prepared.get("m15", [])
    m15_by_end = prepared.get("m15_by_end", {})
    m15_by_start = prepared.get("m15_by_start", {})
    atr, rsi, ema, regime = prepared["atr"], prepared["rsi"], prepared["ema"], prepared["regime"]
    h4_by_end, h4_end_times = prepared["h4_by_end"], prepared["h4_end_times"]
    h1_by_end, warmup_end = prepared["h1_by_end"], prepared["warmup_end"]
    allowed_start = max(start, warmup_end) if warmup_end else None
    period_rows = [r for r in minutes if start <= parse_time(r["open_time"]) < end]
    if not warmup_end:
        return {"status": "INSUFFICIENT_WARMUP", "scenario": scenario.name, "signals": [], "trades": [], "decision_log": [], "equity": [], "daily_equity": [], "final_nav": str(D("10000")), "terminal_status": "NONE", "warmup_end": ""}

    cash, btc = D("10000"), ZERO; position = None; pending = None; scheduled = None; last_exit = None
    protection_pending = None; protection_log = []
    m15_pending = None; m15_signal_log = []
    signals, decisions, trades, equity = [], [], [], []; previous_minute = None; terminal_status = "NONE"
    for row in period_rows:
        t = parse_time(row["open_time"])
        if previous_minute is not None and t != previous_minute + timedelta(minutes=1):
            if position is not None:
                if m15_channel_exit_n8 and m15_pending is not None:
                    m15_pending["status"] = "CANCELLED_DATA_GAP"
                    m15_pending["cancelled_time"] = iso(t)
                    m15_pending["actual_reason"] = "MISSING_MINUTE_BEFORE_EXECUTION"
                    m15_pending = None
                terminal_status = "RIGHT_CENSORED"; break
            pending = None
            if m15_pending is not None:
                m15_pending["status"] = "CANCELLED_DATA_GAP"
                m15_pending["cancelled_time"] = iso(t)
                m15_pending["actual_reason"] = "MISSING_MINUTE_BEFORE_EXECUTION"
                m15_pending = None
        previous_minute = t

        # Existing position events happen before any new signal at this timestamp.
        if position is not None:
            if m15_channel_exit_n8:
                due_reasons = []
                if scheduled is not None and scheduled["time"] == t:
                    due_reasons.append(scheduled["primary"])
                if m15_pending is not None and m15_pending["execution_time"] == t:
                    due_reasons.append("M15_CHANNEL_EXIT")
                if t == position["entry_time"] + timedelta(hours=48):
                    due_reasons.append("TIME_EXIT")
                open_price = D(row["open"])
                stop_gap = open_price <= position["initial_stop"]
                if stop_gap:
                    reason = "STOP_GAP"
                    result = _close_position(
                        position, open_price, t, reason, scenario,
                        stop_type="INITIAL_STOP",
                    )
                elif due_reasons:
                    priority = {"REGIME_EXIT": 0, "M15_CHANNEL_EXIT": 1, "TIME_EXIT": 2}
                    reason = min(due_reasons, key=lambda value: priority[value])
                    result = _close_position(position, open_price, t, reason, scenario)
                elif D(row["low"]) <= position["initial_stop"]:
                    reason = "STOP"
                    result = _close_position(
                        position, position["initial_stop"], t, reason, scenario,
                        stop_type="INITIAL_STOP",
                    )
                else:
                    result = None
                if result and due_reasons:
                    result["coincident_reasons"] = json.dumps(
                        sorted(set(due_reasons + [reason])), separators=(",", ":"),
                    )
                if m15_pending is not None and m15_pending["execution_time"] == t:
                    m15_pending["actual_time"] = iso(t)
                    m15_pending["actual_reason"] = reason if result else ""
                    if result and reason == "M15_CHANNEL_EXIT":
                        m15_pending["status"] = "EXECUTED"
                        m15_pending["actual_exit_fill"] = result["exit_fill"]
                        m15_pending["coincident_reasons"] = json.dumps(
                            sorted(set(due_reasons)), separators=(",", ":"),
                        )
                    elif result:
                        m15_pending["status"] = "OVERRIDDEN_BY_" + reason
                        m15_pending["actual_exit_fill"] = result["exit_fill"]
                        m15_pending["coincident_reasons"] = json.dumps(
                            sorted(set(due_reasons + [reason])), separators=(",", ":"),
                        )
                    else:
                        m15_pending["status"] = "NOT_EXECUTED_POSITION_OPEN"
                    m15_pending = None
            else:
                if (one_shot_protection and protection_pending is not None and
                        t >= protection_pending["activation_time"]):
                    position["active_stop"] = max(position["active_stop"], D(protection_pending["protected_stop"]))
                    position["protection_state"] = "ACTIVE"
                    protection_log.append({**protection_pending, "event": "ACTIVATED", "actual_activation_time": iso(t)})
                    protection_pending = None
                active_stop = position.get("active_stop", position["stop"])
                stop_type = "PROTECTED_STOP" if position.get("protection_state") == "ACTIVE" else "INITIAL_STOP"
                stop_gap = D(row["open"]) <= active_stop
                if stop_gap:
                    result = _close_position(position, D(row["open"]), t, "STOP_GAP", scenario, stop_type=stop_type)
                elif scheduled is not None and scheduled["time"] == t:
                    result = _close_position(position, D(row["open"]), t, scheduled["primary"], scenario)
                elif t == position["entry_time"] + timedelta(hours=48):
                    result = _close_position(position, D(row["open"]), t, "TIME_EXIT", scenario)
                elif D(row["low"]) <= active_stop:
                    result = _close_position(position, active_stop, t, "STOP", scenario, stop_type=stop_type)
                else:
                    result = None
            if result:
                cash += position["quote"] + D(result["net_pnl_usdt"]); btc -= position["q_sell"]
                trades.append(_trade_record(position, result, scenario)); last_exit = t; position = None; scheduled = None
                if m15_channel_exit_n8 and m15_pending is not None:
                    m15_pending["status"] = "CANCELLED_POSITION_CLOSED_BEFORE_EXECUTION"
                    m15_pending["cancelled_time"] = iso(t)
                    m15_pending["actual_reason"] = result["exit_reason"]
                    m15_pending["actual_exit_fill"] = result["exit_fill"]
                    m15_pending = None
                if one_shot_protection and protection_pending is not None:
                    protection_pending["cancel_reason"] = "POSITION_CLOSED_BEFORE_ACTIVATION"
                    protection_log.append({**protection_pending, "event": "CANCELLED"})
                    protection_pending = None

        # A pending entry is single-shot and uses only T+1 open and prior 60m volume.
        if pending is not None and pending["execution_time"] == t:
            fill_base = D(row["open"])
            plan = size_order(fill_base, pending["stop"], pending["volume_60"], cash, scenario, filters)
            if plan is None:
                pending["status"] = "CANCELLED"; pending["cancel_reason"] = "SIZE_OR_FILTER_REJECT"; signals.append(pending); pending = None
            else:
                if abs(fill_base - pending["signal_close"]) > D("0.5") * pending["atr"]:
                    pending["status"] = "CANCELLED"; pending["cancel_reason"] = "GAP_GUARD"; signals.append(pending); pending = None
                elif fill_base <= pending["stop"] or pending["stop"] <= ZERO:
                    pending["status"] = "CANCELLED"; pending["cancel_reason"] = "EXECUTION_REJECT"; signals.append(pending); pending = None
                else:
                    pending["status"] = "EXECUTED"; pending["entry_time"] = iso(t); pending["entry_base"] = str(fill_base); signals.append(pending)
                    entry_fill = _buy_price(fill_base, scenario)
                    position = dict(plan); position.update({"entry_time": t, "buy_fill": entry_fill, "stop": pending["stop"],
                        "initial_stop": pending["stop"], "active_stop": pending["stop"],
                        "protection_state": "NOT_ARMED", "signal": pending})
                    cash -= plan["quote"]; btc += plan["q_sell"]; pending = None
                    if D(row["low"]) <= position["stop"]:
                        result = _close_position(position, position["active_stop"], t, "STOP", scenario, stop_type="INITIAL_STOP")
                        cash += position["quote"] + D(result["net_pnl_usdt"]); btc -= position["q_sell"]; trades.append(_trade_record(position, result, scenario)); last_exit = t; position = None

        # H1 decision at the closed-bar boundary.
        i = h1_by_end.get(t)
        if i is not None and allowed_start is not None and t >= allowed_start:
            prior_rsi = rsi[i - 1] if i else None; current_rsi = rsi[i]
            now_pos = bisect_right(h4_end_times, t) - 1
            prev_pos = bisect_right(h4_end_times, t - timedelta(hours=1)) - 1
            h4_now = h4_by_end[h4_end_times[now_pos]] if now_pos >= 0 else None
            h4_prev = h4_by_end[h4_end_times[prev_pos]] if prev_pos >= 0 else None
            g_now = regime[h4_now] if h4_now is not None else None; g_prev = regime[h4_prev] if h4_prev is not None else None
            reason = "NO_SIGNAL"
            if position is not None or scheduled is not None: reason = "POSITION_OPEN"
            elif prior_rsi is None or current_rsi is None or atr[i] is None: reason = "INDICATOR_UNAVAILABLE"
            elif last_exit is not None and t <= last_exit: reason = "OLD_EPISODE"
            elif not (g_prev is True and g_now is True): reason = "REGIME_FALSE"
            elif not (prior_rsi <= D("20") and D("20") < current_rsi < D("60")): reason = "NO_CROSS"
            else:
                signal_close = D(h1[i]["close"]); stop = floor_step(signal_close - D("2") * atr[i], filters.tick_size)
                # The previous 60 completed minutes are a fixed-size window.
                # This is equivalent to filtering all by_minute items, but
                # avoids an O(H1 * segment_minutes) scan on long segments.
                vol = ZERO
                for offset in range(60, 0, -1):
                    minute_row = by_minute.get(t - timedelta(minutes=offset))
                    if minute_row is not None:
                        vol += D(minute_row["volume"])
                pending = {"signal_time": iso(t), "execution_time": t + timedelta(minutes=1), "signal_close": signal_close, "atr": atr[i], "stop": stop, "rsi_prev": prior_rsi, "rsi_now": current_rsi, "regime": str(g_now), "h4_end_time": iso(parse_time(h4[h4_now]["close_time"])) if h4_now is not None else "", "ema": ema[h4_now] if h4_now is not None else "", "ema_lag6": ema[h4_now - 6] if h4_now is not None and h4_now >= 6 else "", "volume_60": vol, "status": "PENDING", "cancel_reason": ""}; reason = "SIGNAL"
            decisions.append({"time": iso(t), "rsi_prev": str(prior_rsi) if prior_rsi is not None else "", "rsi_now": str(current_rsi) if current_rsi is not None else "", "atr": str(atr[i]) if atr[i] is not None else "", "g_prev": str(g_prev), "g_now": str(g_now), "position_open": str(position is not None), "decision": reason})

        # H1/H4 exits are scheduled only after the close, for the next minute.
        if position is not None and i is not None and current_rsi is not None and current_rsi >= D("60"):
            decisions.append({"time": iso(t), "rsi_prev": str(prior_rsi) if i else "", "rsi_now": str(current_rsi), "atr": str(atr[i]) if atr[i] is not None else "", "g_prev": "", "g_now": "", "position_open": "True", "decision": "RSI_EXIT_SCHEDULED" if rsi_exit else "RSI_EXIT_IGNORED"})
            if rsi_exit:
                scheduled = {"time": t + timedelta(minutes=1), "primary": "RSI_EXIT"}
        h4i = h4_by_end.get(t)
        if position is not None and h4i is not None and regime[h4i] is False:
            scheduled = {"time": t + timedelta(minutes=1), "primary": "REGIME_EXIT"}
        if position is not None and t == position["entry_time"] + timedelta(hours=48):
            scheduled = {"time": t, "primary": "TIME_EXIT"}

        if (m15_channel_exit_n8 and position is not None and
                allowed_start is not None and t >= allowed_start):
            current_index = m15_by_end.get(t)
            candidate = m15_channel_candidate(
                m15, m15_by_start, current_index, position["entry_time"],
            )
            if candidate is not None:
                current = candidate["current"]
                prior = candidate["prior"]
                channel_low = candidate["channel_low"]
                signal_close = D(current["close"])
                if signal_close < channel_low:
                    signal = {
                                "signal_start_time": current["open_time"],
                                "signal_end_time": current["close_time"],
                                "signal_close": str(signal_close),
                                **{
                                    f"channel_low_{index + 1}": str(bar["low"])
                                    for index, bar in enumerate(prior)
                                },
                                "channel_low": str(channel_low),
                                "assigned_exit_time": iso(t + timedelta(minutes=1)),
                                "actual_time": "",
                                "actual_reason": "",
                                "actual_exit_fill": "",
                                "coincident_reasons": "[]",
                                "status": "SIGNAL",
                    }
                    if m15_pending is None:
                        signal["status"] = "PENDING"
                        signal["execution_time"] = t + timedelta(minutes=1)
                        m15_pending = signal
                    else:
                        signal["status"] = "DUPLICATE_PENDING"
                    m15_signal_log.append(signal)

        # Protection is decided only from the completed M1 close.  It becomes
        # effective at the open after one full minute of waiting.
        if (one_shot_protection and position is not None and
                position["protection_state"] == "NOT_ARMED" and protection_pending is None):
            entry_fill = position["buy_fill"]
            distance = entry_fill - position["initial_stop"]
            if distance <= ZERO:
                raise ValueError("one-shot protection requires entry_fill > initial_stop")
            threshold = entry_fill + D("2") * distance
            if D(row["close"]) >= threshold:
                pending_stop = max(position["active_stop"], floor_step(entry_fill + D("0.5") * distance, filters.tick_size))
                protection_pending = {"signal_time": iso(t), "signal_close": str(D(row["close"])),
                    "threshold": str(threshold), "initial_stop": str(position["initial_stop"]),
                    "protected_stop": str(pending_stop), "activation_time": t + timedelta(minutes=2),
                    "cancel_reason": "", "actual_activation_time": ""}
                position["protection_state"] = "PENDING"
                protection_log.append({**protection_pending, "activation_time": iso(protection_pending["activation_time"]), "event": "PENDING"})

        equity.append({"time": iso(t), "cash_usdt": str(cash), "btc": str(btc), "close": row["close"], "nav_usdt": str(cash + btc * _sell_price(row["close"], scenario)), "position_open": str(position is not None)})

    if pending is not None:
        pending["status"] = "CANCELLED"; pending["cancel_reason"] = "MISSING_EXECUTION_MINUTE"; signals.append(pending)
    if position is not None and terminal_status == "NONE":
        terminal_status = "RIGHT_CENSORED"
    final_close = D(period_rows[-1]["close"]) if period_rows else ZERO
    final_nav = cash + btc * _sell_price(final_close, scenario)
    if one_shot_protection and protection_pending is not None:
        protection_pending["cancel_reason"] = "MISSING_ACTIVATION_MINUTE"
        protection_log.append({**protection_pending, "event": "CANCELLED"})
    if m15_channel_exit_n8 and m15_pending is not None:
        m15_pending["status"] = "RIGHT_CENSORED_PENDING"
        m15_pending["actual_reason"] = terminal_status
    return {"status": "OK", "scenario": scenario.name, "signals": signals, "trades": trades, "decision_log": decisions, "protection_log": protection_log, "m15_signal_log": m15_signal_log, "equity": equity, "daily_equity": _daily_snapshots(equity), "final_cash": str(cash), "final_btc": str(btc), "final_nav": str(final_nav), "terminal_status": terminal_status, "warmup_end": iso(warmup_end), "available_minutes": max(0, int((end - allowed_start).total_seconds() / 60))}


def scenario_metrics(result):
    closed = [t for t in result["trades"] if t.get("status") == "CLOSED"]
    wins = [D(t["net_pnl_usdt"]) for t in closed if D(t["net_pnl_usdt"]) > ZERO]
    losses = [D(t["net_pnl_usdt"]) for t in closed if D(t["net_pnl_usdt"]) < ZERO]
    eq = [D(r["nav_usdt"]) for r in result["daily_equity"]]; peak = D("10000"); max_dd = ZERO
    for value in eq:
        peak = max(peak, value); max_dd = max(max_dd, peak - value)
    hold = [D(t["duration_hours"]) for t in closed]
    return {"scenario": result["scenario"], "status": result["status"], "trades": len(closed), "wins": len(wins), "losses": len(losses), "exit_reasons": json.dumps({k: sum(t.get("exit_reason") == k for t in closed) for k in sorted({t.get("exit_reason") for t in closed})}), "return_nav_pct": str((D(result["final_nav"]) / D("10000") - ONE) * D("100")), "realized_pnl_usdt": str(sum((D(t["net_pnl_usdt"]) for t in closed), ZERO)), "terminal_status": result["terminal_status"], "terminal_btc": result["final_btc"], "profit_factor": str(sum(wins, ZERO) / abs(sum(losses, ZERO))) if losses else "", "mean_trade_r": str(sum((D(t["trade_R"]) for t in closed), ZERO) / D(len(closed))) if closed else "", "median_hold_hours": str(sorted(hold)[len(hold)//2]) if hold else "", "max_daily_drawdown_usdt": str(max_dd), "entry_count": len([s for s in result["signals"] if s.get("status") == "EXECUTED"]), "cancel_count": len([s for s in result["signals"] if s.get("status") == "CANCELLED"]), "commission_buy_btc": str(sum((D(t.get("commission_buy_btc", "0")) for t in closed), ZERO)), "commission_sell_usdt": str(sum((D(t.get("commission_sell_usdt", "0")) for t in closed), ZERO))}


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()
