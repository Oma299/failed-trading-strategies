from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

import config_stage2 as config
from stage2_engine import (
    ScenarioContext,
    _costed_buy,
    _costed_sell,
    simulate_phase,
)


def _profit_factor(trades: pd.DataFrame) -> float | None:
    if trades.empty:
        return None
    values = trades["net_pnl_usdt"].to_numpy(dtype=float)
    wins = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses == 0:
        return math.inf
    return wins / losses


def _iso_week_key(value: Any) -> tuple[int, int]:
    week = pd.Timestamp(value).isocalendar()
    return int(week.year), int(week.week)


def _week_keys(dates: pd.DatetimeIndex) -> list[tuple[int, int]]:
    keys: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for date in dates:
        key = _iso_week_key(date)
        if key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def _bootstrap_weights(
    size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if size == 0:
        raise ValueError("Bootstrap requires at least one ISO week")
    block_size = config.BOOT_BLOCK_WEEKS
    starts = rng.integers(0, size, size=math.ceil(size / block_size))
    weights = np.zeros(size, dtype=np.int64)
    remaining = size
    for start in starts:
        take = min(block_size, remaining)
        positions = (int(start) + np.arange(take)) % size
        np.add.at(weights, positions, 1)
        remaining -= take
        if remaining == 0:
            break
    if int(weights.sum()) != size:
        raise AssertionError("Bootstrap weights do not sum to the number of weeks")
    return weights


def bootstrap_mean_net_r(
    trades: pd.DataFrame,
    dates: pd.DatetimeIndex,
) -> dict[str, Any]:
    weeks = _week_keys(dates)
    week_position = {key: index for index, key in enumerate(weeks)}
    sums = np.zeros(len(weeks), dtype=float)
    counts = np.zeros(len(weeks), dtype=float)
    if not trades.empty:
        for row in trades.itertuples(index=False):
            if row.net_r is None or not np.isfinite(row.net_r):
                continue
            index = week_position[_iso_week_key(row.entry_decision_date)]
            sums[index] += float(row.net_r)
            counts[index] += 1

    rng = np.random.default_rng(config.SEED + 1)
    samples = []
    undefined = 0
    for _ in range(config.BOOT_DRAWS):
        weights = _bootstrap_weights(len(weeks), rng)
        total_count = float(counts @ weights)
        if total_count == 0:
            undefined += 1
            continue
        samples.append(float((sums @ weights) / total_count))
    if not samples:
        percentiles = {"10": None, "50": None, "90": None}
    else:
        values = np.percentile(samples, [10, 50, 90])
        percentiles = {
            "10": float(values[0]),
            "50": float(values[1]),
            "90": float(values[2]),
        }
    return {
        "draws_requested": config.BOOT_DRAWS,
        "draws_valid": len(samples),
        "draws_without_trades": undefined,
        "week_count": len(weeks),
        "block_weeks": config.BOOT_BLOCK_WEEKS,
        "percentiles": percentiles,
    }


def placebo_test(
    context: ScenarioContext,
    dates: pd.DatetimeIndex,
    signals: pd.DataFrame,
    observed_mean_net_r: float | None,
) -> dict[str, Any]:
    states = signals["signal_on"].to_numpy(dtype=object)
    size = len(states)
    minimum = config.PLACEBO_MIN_SHIFT_DAYS
    if size <= 2 * minimum:
        raise ValueError("Signal series is too short for the configured placebo shift")
    rng = np.random.default_rng(config.SEED)
    shifts = rng.choice(
        np.arange(minimum, size - minimum + 1),
        size=config.PLACEBO_DRAWS,
        replace=True,
    )
    greater_equal = 0
    undefined = 0
    for shift in shifts:
        shifted_states = np.roll(states, int(shift))
        draw_r = []
        for phase in config.PHASES:
            result = simulate_phase(
                context.minute,
                dates,
                signals,
                context.scenario,
                phase,
                signal_states=shifted_states,
                opportunities=context.opportunities,
                phase_positions=context.phase_positions[phase],
                decision_events=context.decision_events,
                collect_equity=False,
            )
            draw_r.extend(
                trade["net_r"]
                for trade in result["trades"]
                if trade["net_r"] is not None
                and np.isfinite(trade["net_r"])
            )
        if not draw_r:
            undefined += 1
            continue
        if observed_mean_net_r is not None and float(np.mean(draw_r)) >= observed_mean_net_r:
            greater_equal += 1
    return {
        "draws": config.PLACEBO_DRAWS,
        "minimum_shift_days": minimum,
        "shift_range_inclusive": [minimum, size - minimum],
        "observed_pooled_mean_net_r": observed_mean_net_r,
        "placebo_ge_observed": greater_equal,
        "undefined_draws": undefined,
        "p_value": (1 + greater_equal) / (1 + config.PLACEBO_DRAWS),
        "shifts": shifts.tolist(),
    }


def summarize_scenario(run: dict[str, Any]) -> dict[str, Any]:
    trades = run["trades"]
    net = trades["net_pnl_usdt"].to_numpy(dtype=float) if not trades.empty else np.array([])
    gross = trades["gross_pnl_usdt"].to_numpy(dtype=float) if not trades.empty else np.array([])
    total_net = float(net.sum()) if len(net) else 0.0
    total_gross = float(gross.sum()) if len(gross) else 0.0
    mean_net_r = (
        float(trades["net_r"].mean())
        if not trades.empty and trades["net_r"].notna().any()
        else None
    )
    best_sorted = (
        trades.sort_values("net_pnl_usdt", ascending=False, kind="mergesort")
        if not trades.empty
        else trades
    )
    best_contribution = {}
    for count in (1, 3, 5):
        best_contribution[str(count)] = (
            float(best_sorted.head(count)["net_pnl_usdt"].sum() / total_net)
            if total_net > 0 and not best_sorted.empty
            else None
        )
    without_three = (
        best_sorted.iloc[3:] if len(best_sorted) > 3 else trades.iloc[0:0]
    )

    annual: dict[str, float] = {}
    if not trades.empty:
        realized_year = pd.to_datetime(trades["exit_time"], utc=True).dt.year
        annual_values = trades.assign(realized_year=realized_year).groupby(
            "realized_year"
        )["net_pnl_usdt"].sum()
        annual = {str(int(year)): float(value) for year, value in annual_values.items()}
    if total_net > 0:
        annual_shares = {
            year: value / total_net for year, value in annual.items()
        }
        max_annual_share = max(annual_shares.values(), default=None)
    else:
        annual_shares = {year: None for year in annual}
        max_annual_share = None

    phase_rows = []
    for phase in run["phases"]:
        phase_trades = trades.loc[trades["phase"] == phase["phase"]] if not trades.empty else trades
        phase_rows.append(
            {
                "phase": int(phase["phase"]),
                "trade_count": int(len(phase_trades)),
                "gross_pnl_usdt": float(phase_trades["gross_pnl_usdt"].sum()) if len(phase_trades) else 0.0,
                "net_pnl_usdt": float(phase_trades["net_pnl_usdt"].sum()) if len(phase_trades) else 0.0,
                "profit_factor": _profit_factor(phase_trades),
                "mean_net_r": (
                    float(phase_trades["net_r"].mean())
                    if len(phase_trades) and phase_trades["net_r"].notna().any()
                    else None
                ),
                "max_drawdown_usdt": phase["drawdown"]["max_drawdown_usdt"],
                "max_drawdown_fraction": phase["drawdown"]["max_drawdown_fraction"],
                "ending_equity": phase["drawdown"]["ending_equity"],
            }
        )
    phase_pf_count = sum(
        row["profit_factor"] is not None and row["profit_factor"] > 1
        for row in phase_rows
    )

    monthly: dict[str, int] = {}
    if not trades.empty:
        entry_month = pd.to_datetime(trades["entry_time"], utc=True).dt.strftime("%Y-%m")
        monthly = {
            str(month): int(count)
            for month, count in trades.assign(entry_month=entry_month)
            .groupby("entry_month")
            .size()
            .items()
        }
    return {
        "trade_count": int(len(trades)),
        "gross_pnl_usdt": total_gross,
        "net_pnl_usdt": total_net,
        "ending_equity_mean_by_phase": float(
            np.mean([phase["drawdown"]["ending_equity"] for phase in run["phases"]])
        ),
        "profit_factor": _profit_factor(trades),
        "mean_net_r": mean_net_r,
        "best_trade_net_pnl_usdt": (
            [float(value) for value in best_sorted.head(5)["net_pnl_usdt"]]
            if not best_sorted.empty
            else []
        ),
        "best_trade_profit_contribution": best_contribution,
        "profit_factor_without_best_three": _profit_factor(without_three),
        "annual_net_profit_usdt": annual,
        "annual_profit_share": annual_shares,
        "max_annual_profit_share": max_annual_share,
        "phase_pf_above_one_count": int(phase_pf_count),
        "phases": phase_rows,
        "trades_by_entry_month": monthly,
        "drawdown_max_usdt_mean_by_phase": float(
            np.mean([phase["drawdown"]["max_drawdown_usdt"] for phase in run["phases"]])
        ),
        "drawdown_max_fraction_mean_by_phase": float(
            np.mean([phase["drawdown"]["max_drawdown_fraction"] for phase in run["phases"]])
        ),
        "execution_counters": run["counters"],
    }


def _benchmark_quantity(cash: float, entry_fill: float) -> float:
    raw_quantity = cash / (entry_fill * (1 + config.FEE))
    lots = math.floor(raw_quantity / config.LOT_SIZE_BTC + 1e-12)
    return float(lots * config.LOT_SIZE_BTC)


def calculate_buy_and_hold(
    run: dict[str, Any],
    dates: pd.DatetimeIndex,
    signals: pd.DataFrame,
) -> dict[str, Any]:
    context: ScenarioContext = run["context"]
    minute = context.minute
    scenario = context.scenario
    eligible = signals["signal_defined"] & signals["atr_defined"]
    if not eligible.any():
        return {"full_period": None, "in_market": None}
    start_date = pd.Timestamp(signals.index[eligible.to_numpy()][0])
    start_time = start_date + pd.Timedelta(minutes=scenario.delay_min)
    start_index = minute.first_available_index(start_time)
    if start_index is None:
        return {"full_period": None, "in_market": None}
    force_index = minute.forced_end_index
    initial_cash = config.INITIAL_EQUITY_USDT
    start_open = float(minute.open[start_index])
    full_entry_fill = _costed_buy(start_open, scenario)
    full_qty = _benchmark_quantity(initial_cash, full_entry_fill)
    full_end_raw = float(minute.close[force_index])
    full_exit_fill = _costed_sell(full_end_raw, scenario)
    full_ending_cash = (
        initial_cash
        - full_qty * full_entry_fill * (1 + config.FEE)
        + full_qty * full_exit_fill * (1 - config.FEE)
    )

    phase_rows = []
    for phase in config.PHASES:
        cash = initial_cash
        trades = run["phases"][phase]["trades"]
        for trade in trades:
            entry_fill = _costed_buy(float(trade["entry_open"]), scenario)
            quantity = _benchmark_quantity(cash, entry_fill)
            if quantity * entry_fill < config.MIN_NOTIONAL_USDT:
                continue
            cost = quantity * entry_fill * (1 + config.FEE)
            exit_fill = _costed_sell(float(trade["exit_open"]), scenario)
            cash += -cost + quantity * exit_fill * (1 - config.FEE)
        phase_rows.append(
            {
                "phase": int(phase),
                "trade_count": int(len(trades)),
                "ending_equity": float(cash),
                "net_return": float(cash / initial_cash - 1),
            }
        )
    return {
        "start_date": start_date,
        "full_period": {
            "entry_time": minute.timestamp(start_index),
            "exit_time": minute.timestamp(force_index),
            "ending_equity": float(full_ending_cash),
            "net_return": float(full_ending_cash / initial_cash - 1),
        },
        "in_market": {
            "phases": phase_rows,
            "mean_ending_equity": float(
                np.mean([row["ending_equity"] for row in phase_rows])
            ),
            "mean_net_return": float(
                np.mean([row["net_return"] for row in phase_rows])
            ),
        },
    }


def evaluate_criteria(
    base: dict[str, Any],
    stress: dict[str, Any],
    bootstrap: dict[str, Any],
    placebo: dict[str, Any],
) -> dict[str, Any]:
    base_pf = base["profit_factor"]
    stress_pf = stress["profit_factor"]
    phase_pf = base["phase_pf_above_one_count"]
    annual_ok = (
        base["net_pnl_usdt"] > 0
        and base["max_annual_profit_share"] is not None
        and base["max_annual_profit_share"] <= config.MAX_ANNUAL_PROFIT_SHARE
    )
    p10 = bootstrap["percentiles"]["10"]
    return {
        "pf_base": {
            "scenario": "BASE",
            "operator": ">=",
            "threshold": config.MIN_PF_BASE,
            "value": base_pf,
            "passed": base_pf is not None and base_pf >= config.MIN_PF_BASE,
        },
        "pf_stress": {
            "scenario": "STRESS",
            "operator": ">=",
            "threshold": config.MIN_PF_STRESS,
            "value": stress_pf,
            "passed": stress_pf is not None and stress_pf >= config.MIN_PF_STRESS,
        },
        "bootstrap_net_r_p10": {
            "scenario": "BASE",
            "operator": ">",
            "threshold_exclusive": config.MIN_BOOTSTRAP_NET_R_P10,
            "value": p10,
            "passed": p10 is not None and p10 > config.MIN_BOOTSTRAP_NET_R_P10,
        },
        "phases_pf_above_one": {
            "scenario": "BASE",
            "operator": ">=",
            "threshold": config.MIN_PF_PHASES_ABOVE_ONE,
            "value": phase_pf,
            "passed": phase_pf >= config.MIN_PF_PHASES_ABOVE_ONE,
        },
        "pf_without_best_three": {
            "scenario": "BASE",
            "operator": ">",
            "threshold_exclusive": config.MIN_PF_WITHOUT_BEST_THREE,
            "value": base["profit_factor_without_best_three"],
            "passed": (
                base["profit_factor_without_best_three"] is not None
                and base["profit_factor_without_best_three"]
                > config.MIN_PF_WITHOUT_BEST_THREE
            ),
        },
        "annual_profit_concentration": {
            "scenario": "BASE",
            "operator": "<=",
            "threshold": config.MAX_ANNUAL_PROFIT_SHARE,
            "value": base["max_annual_profit_share"],
            "passed": annual_ok,
        },
        "placebo_p": {
            "scenario": "BASE",
            "operator": "<=",
            "threshold": config.MAX_PLACEBO_P_VALUE,
            "value": placebo["p_value"],
            "passed": placebo["p_value"] <= config.MAX_PLACEBO_P_VALUE,
        },
        "minimum_trades": {
            "scenario": "BASE",
            "operator": ">=",
            "threshold": config.MIN_TRADES,
            "value": base["trade_count"],
            "passed": base["trade_count"] >= config.MIN_TRADES,
        },
    }
