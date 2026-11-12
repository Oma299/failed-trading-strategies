from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

import numpy as np
import pandas as pd

import config_stage2 as config


def _as_naive_utc(value: pd.Timestamp) -> np.datetime64:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_datetime64()


@dataclass(frozen=True)
class Scenario:
    name: str
    spread: float
    slip: float
    delay_min: int


def scenario_from_config(name: str) -> Scenario:
    values = config.BASE if name == "BASE" else config.STRESS
    if name not in ("BASE", "STRESS"):
        raise ValueError(f"Unknown scenario: {name}")
    return Scenario(
        name=name,
        spread=float(values["SPREAD"]),
        slip=float(values["SLIP"]),
        delay_min=int(values["DELAY_MIN"]),
    )


class MinuteSeries:
    def __init__(
        self,
        minute_data: pd.DataFrame,
        ambiguous_minutes: set[pd.Timestamp] | None = None,
    ) -> None:
        ordered = minute_data.sort_values("open_time", kind="mergesort")
        self.times = pd.DatetimeIndex(ordered["open_time"]).tz_convert("UTC").tz_localize(None).to_numpy()
        self.open = ordered["open"].to_numpy(dtype=float)
        self.high = ordered["high"].to_numpy(dtype=float)
        self.low = ordered["low"].to_numpy(dtype=float)
        self.close = ordered["close"].to_numpy(dtype=float)
        self.ambiguous = {
            pd.Timestamp(value).tz_convert("UTC").value
            for value in (ambiguous_minutes or set())
        }
        cutoff = _as_naive_utc(pd.Timestamp(config.FORCED_END_BEFORE_UTC))
        self.forced_end_index = int(np.searchsorted(self.times, cutoff, side="left")) - 1
        if self.forced_end_index < 0:
            raise ValueError("No M1 candle is available before the forced-end cutoff")

    def exact_index(self, timestamp: pd.Timestamp) -> int | None:
        target = _as_naive_utc(timestamp)
        index = int(np.searchsorted(self.times, target, side="left"))
        if index < len(self.times) and self.times[index] == target:
            if index <= self.forced_end_index:
                return index
        return None

    def first_available_index(self, timestamp: pd.Timestamp) -> int | None:
        target = _as_naive_utc(timestamp)
        index = int(np.searchsorted(self.times, target, side="left"))
        if index <= self.forced_end_index:
            return index
        return None

    def is_ambiguous(self, timestamp: pd.Timestamp) -> bool:
        return pd.Timestamp(timestamp).tz_convert("UTC").floor("min").value in self.ambiguous

    def timestamp(self, index: int) -> pd.Timestamp:
        return pd.Timestamp(self.times[index], tz="UTC")


class FirstCrossingTree:
    def __init__(self, values: np.ndarray) -> None:
        self.length = len(values)
        self.size = 1
        while self.size < self.length:
            self.size *= 2
        self.tree = np.full(self.size * 2, np.inf, dtype=float)
        self.tree[self.size : self.size + self.length] = values
        for index in range(self.size - 1, 0, -1):
            self.tree[index] = min(self.tree[index * 2], self.tree[index * 2 + 1])

    def first_at_most(
        self,
        threshold: float,
        start: int,
        end_exclusive: int,
    ) -> int | None:
        return self._find(1, 0, self.size, start, end_exclusive, threshold)

    def _find(
        self,
        node: int,
        left: int,
        right: int,
        query_left: int,
        query_right: int,
        threshold: float,
    ) -> int | None:
        if (
            right <= query_left
            or query_right <= left
            or self.tree[node] > threshold
        ):
            return None
        if right - left == 1:
            return left if left < self.length else None
        middle = (left + right) // 2
        found = self._find(
            node * 2,
            left,
            middle,
            query_left,
            query_right,
            threshold,
        )
        if found is not None:
            return found
        return self._find(
            node * 2 + 1,
            middle,
            right,
            query_left,
            query_right,
            threshold,
        )


def _quantity_for_risk(
    equity: float,
    cash: float,
    entry_fill: float,
    stop: float,
) -> float:
    risk_per_btc = entry_fill - stop
    if risk_per_btc <= 0 or entry_fill <= 0 or cash <= 0 or equity <= 0:
        return 0.0
    risk_quantity = equity * config.RISK_FRACTION / risk_per_btc
    cash_quantity = cash / (entry_fill * (1 + config.FEE))
    raw_quantity = min(risk_quantity, cash_quantity)
    lots = floor(raw_quantity / config.LOT_SIZE_BTC + 1e-12)
    return float(lots * config.LOT_SIZE_BTC)


def _costed_buy(raw_open: float, scenario: Scenario) -> float:
    return raw_open * (1 + scenario.spread / 2 + scenario.slip)


def _costed_sell(raw_price: float, scenario: Scenario) -> float:
    return raw_price * (1 - scenario.spread / 2 - scenario.slip)


def _opportunities(
    minute: MinuteSeries,
    daily_signals: pd.DataFrame,
    dates: pd.DatetimeIndex,
    scenario: Scenario,
) -> list[dict[str, Any] | None]:
    crossing_tree = FirstCrossingTree(minute.low)
    opportunities: list[dict[str, Any] | None] = []
    for execution_date in dates:
        signal = daily_signals.loc[execution_date]
        atr = signal["atr"]
        if not bool(signal["atr_defined"]) or pd.isna(atr):
            opportunities.append(None)
            continue
        scheduled_entry = execution_date + pd.Timedelta(minutes=scenario.delay_min)
        entry_index = minute.exact_index(scheduled_entry)
        if entry_index is None:
            opportunities.append(
                {
                    "entry_index": None,
                    "entry_ambiguous": minute.is_ambiguous(scheduled_entry),
                    "scheduled_entry": scheduled_entry,
                }
            )
            continue
        entry_open = float(minute.open[entry_index])
        entry_fill = _costed_buy(entry_open, scenario)
        stop = entry_fill - config.ATR_K * float(atr)
        stop_index = crossing_tree.first_at_most(
            stop, entry_index, minute.forced_end_index + 1
        )
        opportunities.append(
            {
                "entry_index": entry_index,
                "entry_open": entry_open,
                "entry_fill": entry_fill,
                "stop": stop,
                "stop_index": stop_index,
                "scheduled_entry": scheduled_entry,
            }
        )
    return opportunities


def _scheduled_event(
    minute: MinuteSeries,
    execution_date: pd.Timestamp,
    scenario: Scenario,
) -> tuple[int | None, bool, bool]:
    scheduled = execution_date + pd.Timedelta(minutes=scenario.delay_min)
    exact = minute.exact_index(scheduled)
    if exact is not None:
        return exact, False, False
    if _as_naive_utc(scheduled) > minute.times[minute.forced_end_index]:
        return None, False, False
    return (
        minute.first_available_index(scheduled),
        True,
        minute.is_ambiguous(scheduled),
    )


def _make_trade(
    minute: MinuteSeries,
    scenario: Scenario,
    position: dict[str, Any],
    exit_index: int,
    exit_price: float,
    exit_reason: str,
    exit_decision_date: pd.Timestamp,
    forced_end: bool = False,
) -> dict[str, Any]:
    exit_fill = _costed_sell(exit_price, scenario)
    proceeds = position["quantity"] * exit_fill * (1 - config.FEE)
    net_pnl = proceeds - position["entry_cost"]
    gross_pnl = position["quantity"] * (exit_price - position["entry_open"])
    risk_amount = position["quantity"] * (
        position["entry_fill"] - position["stop"]
    )
    entry_date = position["entry_date"]
    return {
        "scenario": scenario.name,
        "phase": position["phase"],
        "entry_decision_date": entry_date,
        "entry_time": minute.timestamp(position["entry_index"]),
        "exit_decision_date": exit_decision_date,
        "exit_time": minute.timestamp(exit_index),
        "entry_open": position["entry_open"],
        "exit_open": float(exit_price),
        "entry_fill": position["entry_fill"],
        "entry_atr": position["atr"],
        "entry_signal_on": True,
        "exit_fill": exit_fill,
        "stop": position["stop"],
        "quantity": position["quantity"],
        "entry_cost_usdt": position["entry_cost"],
        "proceeds_usdt": proceeds,
        "gross_pnl_usdt": gross_pnl,
        "net_pnl_usdt": net_pnl,
        "net_r": net_pnl / risk_amount if risk_amount > 0 else None,
        "days_held": int(
            (pd.Timestamp(exit_decision_date).date() - pd.Timestamp(entry_date).date()).days
        ),
        "exit_reason": exit_reason,
        "FORCED_END": forced_end,
        "entry_iso_year": int(entry_date.isocalendar().year),
        "entry_iso_week": int(entry_date.isocalendar().week),
    }


def simulate_phase(
    minute: MinuteSeries,
    dates: pd.DatetimeIndex,
    daily_signals: pd.DataFrame,
    scenario: Scenario,
    phase: int,
    signal_states: np.ndarray | None = None,
    opportunities: list[dict[str, Any] | None] | None = None,
    phase_positions: list[int] | None = None,
    decision_events: list[tuple[int | None, bool, bool]] | None = None,
    collect_equity: bool = True,
) -> dict[str, Any]:
    if len(dates) != len(daily_signals):
        raise ValueError("Execution dates must match the signal index")
    if signal_states is None:
        signal_states = daily_signals["signal_on"].to_numpy(dtype=object)
    if len(signal_states) != len(dates):
        raise ValueError("Signal-state array has the wrong length")
    if opportunities is None:
        opportunities = _opportunities(minute, daily_signals, dates, scenario)

    if phase_positions is None:
        phase_positions = [
            index for index, value in enumerate(dates) if int(value.weekday()) == phase
        ]
    counters = {
        "candidate_decisions": len(phase_positions),
        "undefined_signal": 0,
        "missing_atr": 0,
        "missing_entry_candle": 0,
        "ambiguous_entry_minute": 0,
        "below_min_notional": 0,
        "missing_planned_exit": 0,
        "ambiguous_planned_exit": 0,
        "delayed_planned_exit": 0,
        "delayed_stop_check": 0,
        "stop_exits": 0,
        "signal_exits": 0,
        "max_hold_exits": 0,
        "forced_end_exits": 0,
        "reentry_blocked": 0,
    }
    cash = config.INITIAL_EQUITY_USDT
    position: dict[str, Any] | None = None
    stop_blocked = False
    trades: list[dict[str, Any]] = []
    cash_events: list[tuple[int, float]] = []
    quantity_events: list[tuple[int, float]] = []
    in_market_intervals: list[tuple[int, int]] = []

    def close_position(
        exit_index: int,
        raw_exit_price: float,
        reason: str,
        decision_date: pd.Timestamp,
        forced: bool = False,
    ) -> None:
        nonlocal cash, position
        if position is None:
            return
        trade = _make_trade(
            minute,
            scenario,
            position,
            exit_index,
            raw_exit_price,
            reason,
            decision_date,
            forced,
        )
        cash += float(trade["proceeds_usdt"])
        cash_events.append((exit_index, float(trade["proceeds_usdt"])))
        quantity_events.append((exit_index, -float(position["quantity"])))
        in_market_intervals.append((int(position["entry_index"]), exit_index))
        trades.append(trade)
        position = None

    for date_index in phase_positions:
        execution_date = dates[date_index]
        raw_state = signal_states[date_index]
        signal_defined = isinstance(raw_state, (bool, np.bool_))
        state = bool(raw_state) if signal_defined else None
        if not signal_defined:
            counters["undefined_signal"] += 1
        if decision_events is None:
            scheduled_index, exit_missing, exit_ambiguous = _scheduled_event(
                minute, execution_date, scenario
            )
        else:
            scheduled_index, exit_missing, exit_ambiguous = decision_events[date_index]

        if position is not None:
            days_held = (execution_date.date() - position["entry_date"].date()).days
            max_hold_reached = days_held >= config.MAX_HOLD_DAYS
            should_exit = state is False or max_hold_reached
            stop_index = position["stop_index"]

            if should_exit:
                if exit_missing:
                    counters["missing_planned_exit"] += 1
                if exit_ambiguous:
                    counters["ambiguous_planned_exit"] += 1
                if scheduled_index is None:
                    if exit_missing:
                        counters["delayed_planned_exit"] += 1
                    if stop_index is not None and stop_index <= minute.forced_end_index:
                        stop_open = float(minute.open[stop_index])
                        stop_price = float(position["stop"])
                        entry_index = int(position["entry_index"])
                        close_position(
                            stop_index,
                            min(stop_price, stop_open),
                            "STOP",
                            execution_date,
                        )
                        counters["stop_exits"] += 1
                        if stop_index > entry_index and (
                            minute.times[stop_index] - minute.times[stop_index - 1]
                            > np.timedelta64(1, "m")
                        ):
                            counters["delayed_stop_check"] += 1
                        stop_blocked = state is not False
                    else:
                        close_position(
                            minute.forced_end_index,
                            float(minute.close[minute.forced_end_index]),
                            "FORCED_END",
                            pd.Timestamp(config.FORCED_END_BEFORE_UTC).normalize(),
                            True,
                        )
                        counters["forced_end_exits"] += 1
                    continue
                if exit_missing:
                    counters["delayed_planned_exit"] += 1
                if stop_index is not None and stop_index < scheduled_index:
                    stop_open = float(minute.open[stop_index])
                    stop_price = float(position["stop"])
                    entry_index = int(position["entry_index"])
                    close_position(
                        stop_index,
                        min(stop_price, stop_open),
                        "STOP",
                        execution_date,
                    )
                    counters["stop_exits"] += 1
                    if stop_index > entry_index and (
                        minute.times[stop_index] - minute.times[stop_index - 1]
                        > np.timedelta64(1, "m")
                    ):
                        counters["delayed_stop_check"] += 1
                    stop_blocked = True
                else:
                    reason = "SIGNAL_OFF" if state is False else "MAX_HOLD"
                    close_position(
                        scheduled_index,
                        float(minute.open[scheduled_index]),
                        reason,
                        execution_date,
                    )
                    counters[
                        "signal_exits" if reason == "SIGNAL_OFF" else "max_hold_exits"
                    ] += 1
                if stop_blocked and state is False:
                    stop_blocked = False
                continue

            if stop_index is not None and scheduled_index is not None and stop_index <= scheduled_index:
                stop_open = float(minute.open[stop_index])
                stop_price = float(position["stop"])
                entry_index = int(position["entry_index"])
                close_position(
                    stop_index,
                    min(stop_price, stop_open),
                    "STOP",
                    execution_date,
                )
                counters["stop_exits"] += 1
                if stop_index > entry_index and (
                    minute.times[stop_index] - minute.times[stop_index - 1]
                    > np.timedelta64(1, "m")
                ):
                    counters["delayed_stop_check"] += 1
                stop_blocked = state is not False
                if state is False:
                    stop_blocked = False
            continue

        if stop_blocked:
            if state is False:
                stop_blocked = False
            else:
                if state is True:
                    counters["reentry_blocked"] += 1
                continue
        if state is not True:
            continue

        opportunity = opportunities[date_index]
        if opportunity is None:
            counters["missing_atr"] += 1
            continue
        entry_index = opportunity["entry_index"]
        if entry_index is None:
            if opportunity["entry_ambiguous"]:
                counters["ambiguous_entry_minute"] += 1
            else:
                counters["missing_entry_candle"] += 1
            continue
        entry_fill = float(opportunity["entry_fill"])
        stop = float(opportunity["stop"])
        quantity = _quantity_for_risk(
            cash,
            cash,
            entry_fill,
            stop,
        )
        if quantity <= 0 or quantity * entry_fill < config.MIN_NOTIONAL_USDT:
            counters["below_min_notional"] += 1
            continue
        entry_cost = quantity * entry_fill * (1 + config.FEE)
        if entry_cost > cash + 1e-8:
            raise AssertionError("Position sizing exceeded available cash")
        cash -= entry_cost
        cash_events.append((entry_index, -entry_cost))
        quantity_events.append((entry_index, quantity))
        position = {
            "phase": phase,
            "entry_date": execution_date,
            "entry_index": int(entry_index),
            "entry_open": float(opportunity["entry_open"]),
            "entry_fill": entry_fill,
            "atr": float(daily_signals.iloc[date_index]["atr"]),
            "stop": stop,
            "stop_index": opportunity["stop_index"],
            "quantity": quantity,
            "entry_cost": entry_cost,
        }

    if position is not None:
        stop_index = position["stop_index"]
        forced_index = minute.forced_end_index
        if stop_index is not None and stop_index <= forced_index:
            stop_open = float(minute.open[stop_index])
            stop_price = float(position["stop"])
            entry_index = int(position["entry_index"])
            close_position(
                stop_index,
                min(stop_price, stop_open),
                "STOP",
                pd.Timestamp(config.FORCED_END_BEFORE_UTC).normalize(),
            )
            counters["stop_exits"] += 1
            if stop_index > entry_index and (
                minute.times[stop_index] - minute.times[stop_index - 1]
                > np.timedelta64(1, "m")
            ):
                counters["delayed_stop_check"] += 1
        else:
            close_position(
                forced_index,
                float(minute.close[forced_index]),
                "FORCED_END",
                pd.Timestamp(config.FORCED_END_BEFORE_UTC).normalize(),
                True,
            )
            counters["forced_end_exits"] += 1

    equity = None
    drawdown = None
    if collect_equity:
        cash_delta = np.zeros(len(minute.times), dtype=float)
        quantity_delta = np.zeros(len(minute.times), dtype=float)
        for index, value in cash_events:
            cash_delta[index] += value
        for index, value in quantity_events:
            quantity_delta[index] += value
        cash_curve = config.INITIAL_EQUITY_USDT + np.cumsum(cash_delta)
        quantity_curve = np.cumsum(quantity_delta)
        equity = cash_curve + quantity_curve * minute.close
        peaks = np.maximum.accumulate(equity)
        drawdown = {
            "max_drawdown_usdt": float(np.max(peaks - equity)),
            "max_drawdown_fraction": float(
                np.max(np.divide(peaks - equity, peaks, out=np.zeros_like(peaks), where=peaks != 0))
            ),
            "ending_equity": float(equity[minute.forced_end_index]),
        }
    else:
        equity = None

    return {
        "phase": phase,
        "trades": trades,
        "counters": counters,
        "equity_curve": None,
        "drawdown": drawdown,
        "in_market_intervals": in_market_intervals,
        "ending_cash": cash,
    }


@dataclass
class ScenarioContext:
    minute: MinuteSeries
    scenario: Scenario
    opportunities: list[dict[str, Any] | None]
    phase_positions: dict[int, list[int]]
    decision_events: list[tuple[int | None, bool, bool]]


TRADE_COLUMNS = [
    "scenario",
    "phase",
    "entry_decision_date",
    "entry_time",
    "exit_decision_date",
    "exit_time",
    "entry_open",
    "exit_open",
    "entry_fill",
    "entry_atr",
    "entry_signal_on",
    "exit_fill",
    "stop",
    "quantity",
    "entry_cost_usdt",
    "proceeds_usdt",
    "gross_pnl_usdt",
    "net_pnl_usdt",
    "net_r",
    "days_held",
    "exit_reason",
    "FORCED_END",
    "entry_iso_year",
    "entry_iso_week",
]


def build_scenario_context(
    minute_data: pd.DataFrame,
    ambiguous_minutes: set[pd.Timestamp],
    dates: pd.DatetimeIndex,
    signals: pd.DataFrame,
    scenario_name: str,
) -> ScenarioContext:
    scenario = scenario_from_config(scenario_name)
    minute = MinuteSeries(minute_data, ambiguous_minutes)
    opportunities = _opportunities(minute, signals, dates, scenario)
    phase_positions = {
        phase: [
            index for index, value in enumerate(dates) if int(value.weekday()) == phase
        ]
        for phase in config.PHASES
    }
    decision_events = [
        _scheduled_event(minute, date, scenario) for date in dates
    ]
    return ScenarioContext(
        minute,
        scenario,
        opportunities,
        phase_positions,
        decision_events,
    )


def run_scenario(
    minute_data: pd.DataFrame,
    ambiguous_minutes: set[pd.Timestamp],
    dates: pd.DatetimeIndex,
    signals: pd.DataFrame,
    scenario_name: str,
    signal_states: np.ndarray | None = None,
    collect_equity: bool = True,
    context: ScenarioContext | None = None,
) -> dict[str, Any]:
    if context is None:
        context = build_scenario_context(
            minute_data, ambiguous_minutes, dates, signals, scenario_name
        )
    scenario = context.scenario
    minute = context.minute
    opportunities = context.opportunities
    if not dates.equals(signals.index):
        raise ValueError("Execution dates must match the signal index")
    phases = [
        simulate_phase(
            minute,
            dates,
            signals,
            scenario,
            phase,
            signal_states=signal_states,
            opportunities=opportunities,
            phase_positions=context.phase_positions[phase],
            decision_events=context.decision_events,
            collect_equity=collect_equity,
        )
        for phase in config.PHASES
    ]
    all_trades = [trade for phase in phases for trade in phase["trades"]]
    return {
        "scenario": scenario_name,
        "phases": phases,
        "trades": pd.DataFrame.from_records(all_trades, columns=TRADE_COLUMNS),
        "counters": {
            str(phase["phase"]): phase["counters"] for phase in phases
        },
        "minute_series": minute,
        "context": context,
        "in_market_intervals": {
            int(phase["phase"]): phase["in_market_intervals"] for phase in phases
        },
    }
