from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import config_stage2 as config
import stage2_reporting
from stage2_data import candidate_execution_dates, load_stage2_data
from stage2_engine import (
    MinuteSeries,
    Scenario,
    build_scenario_context,
    _quantity_for_risk,
    run_scenario,
    simulate_phase,
)
from stage2_metrics import (
    _bootstrap_weights,
    _profit_factor,
    bootstrap_mean_net_r,
    calculate_buy_and_hold,
    evaluate_criteria,
    placebo_test,
    summarize_scenario,
)
from stage2_signal import build_execution_signals


def _write_minute_parquet(path, timestamps, prices=None):
    if prices is None:
        prices = np.full(len(timestamps), 100.0)
    table = pa.table(
        {
            "open_time": pa.array(
                [pd.Timestamp(value).to_pydatetime() for value in timestamps],
                type=pa.timestamp("ns", tz="UTC"),
            ),
            "open": prices,
            "high": np.asarray(prices, dtype=float) + 1,
            "low": np.asarray(prices, dtype=float) - 1,
            "close": prices,
            "volume": np.ones(len(timestamps)),
        }
    )
    pq.write_table(table, path)


def _daily_frame(days: int, start="2020-01-01"):
    dates = pd.date_range(start, periods=days, freq="D", tz="UTC")
    closes = np.linspace(100.0, 200.0, days)
    return pd.DataFrame(
        {
            "open": closes - 0.5,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(days, 1440.0),
            "unique_minutes": np.full(days, 1440),
            "full_d1": np.ones(days, dtype=bool),
        },
        index=dates,
    )


def _signals(dates, signal_values, atr_values=None):
    if atr_values is None:
        atr_values = [1.0] * len(dates)
    return pd.DataFrame(
        {
            "signal_on": signal_values,
            "signal_defined": [value is not None for value in signal_values],
            "atr": atr_values,
            "atr_defined": [value is not None for value in atr_values],
        },
        index=dates,
    )


def _simulate(minute_data, dates, signal_values, ambiguous=None, atr_values=None):
    signals = _signals(dates, signal_values, atr_values)
    scenario = Scenario("BASE", config.BASE["SPREAD"], config.BASE["SLIP"], 1)
    minute = MinuteSeries(minute_data, ambiguous)
    return simulate_phase(
        minute,
        dates,
        signals,
        scenario,
        phase=0,
    )


def test_loader_floors_minutes_and_removes_both_ambiguous_rows(tmp_path):
    day = pd.Timestamp("2024-01-01T00:00:00Z")
    times = list(pd.date_range(day + pd.Timedelta(minutes=1), periods=1439, freq="min"))
    times.extend([day + pd.Timedelta(seconds=10), day + pd.Timedelta(seconds=20)])
    path = tmp_path / "synthetic.parquet"
    _write_minute_parquet(path, times)

    minute_data, daily, diagnostics, ambiguous = load_stage2_data(path)

    assert diagnostics["ambiguous_minute_buckets"] == 1
    assert diagnostics["rows_removed_from_ambiguous_minutes"] == 2
    assert len(minute_data) == 1439
    assert day in ambiguous
    assert not bool(daily.iloc[0]["full_d1"])
    assert daily.iloc[0]["unique_minutes"] == 1439


def test_loader_rejects_future_metadata_before_reading(tmp_path, monkeypatch):
    path = tmp_path / "future.parquet"
    _write_minute_parquet(
        path,
        [pd.Timestamp("2025-07-01T00:00:00Z")],
    )

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Parquet rows must not be read before cutoff validation")

    monkeypatch.setattr(pd, "read_parquet", forbidden_read)
    with pytest.raises(AssertionError, match="not before"):
        load_stage2_data(path)


def test_loader_counts_missing_calendar_days(tmp_path):
    first = pd.date_range("2024-01-01T00:00:00Z", periods=1440, freq="min")
    third = pd.date_range("2024-01-03T00:00:00Z", periods=1440, freq="min")
    path = tmp_path / "calendar-gap.parquet"
    _write_minute_parquet(path, list(first) + list(third))

    _, daily, diagnostics, _ = load_stage2_data(path)

    assert len(daily) == 3
    assert diagnostics["missing_d1_calendar_days"] == 1
    assert not bool(daily.iloc[1]["full_d1"])


def test_approved_parquet_loads_only_minutes_before_cutoff():
    minute_data, daily, diagnostics, ambiguous = load_stage2_data()
    cutoff = pd.Timestamp(config.CUTOFF_UTC)
    dates = candidate_execution_dates(daily)
    signals = build_execution_signals(daily, dates)

    assert not minute_data.empty
    assert (minute_data["open_time"] < cutoff).all()
    assert daily.index.is_monotonic_increasing
    assert diagnostics["cutoff_assertion"] is True
    assert diagnostics["ambiguous_minute_buckets"] == len(ambiguous)
    assert (signals["signal_defined"] & signals["atr_defined"]).any()


def test_atr_requires_15_consecutive_full_daily_bars():
    daily = _daily_frame(16)
    daily["close"] = 100.0
    daily["high"] = 101.0
    daily["low"] = 99.0
    execution_date = daily.index[15]
    signals = build_execution_signals(daily, pd.DatetimeIndex([execution_date]))

    assert signals.loc[execution_date, "atr"] == pytest.approx(2.0)
    daily.loc[daily.index[0], "full_d1"] = False
    signals = build_execution_signals(daily, pd.DatetimeIndex([execution_date]))
    assert pd.isna(signals.loc[execution_date, "atr"])


def test_signal_is_lookahead_safe_with_stage1_missing_day_semantics():
    daily = _daily_frame(450)
    dates = pd.DatetimeIndex([daily.index[400]])
    before = build_execution_signals(daily, dates).iloc[0]

    changed = daily.copy()
    changed.loc[changed.index >= dates[0], "close"] = np.linspace(
        500.0, 900.0, int((changed.index >= dates[0]).sum())
    )
    after = build_execution_signals(changed, dates).iloc[0]

    assert before["signal_on"] == after["signal_on"]
    assert before["return"] == pytest.approx(after["return"])
    assert before["rank"] == pytest.approx(after["rank"])


def test_missing_d1_in_rank_history_makes_signal_undefined():
    daily = _daily_frame(450)
    execution_date = daily.index[400]
    missing_day = execution_date - pd.Timedelta(days=100)
    daily.loc[missing_day, "full_d1"] = False
    signals = build_execution_signals(
        daily, pd.DatetimeIndex([execution_date])
    )
    assert pd.isna(signals.loc[execution_date, "signal_on"])
    assert bool(signals.loc[execution_date, "missing_rank_history"])


def test_quantity_rounds_down_to_lot_size_and_min_notional_excludes_fee():
    quantity = _quantity_for_risk(10_000.0, 10_000.0, 100.0, 98.0)
    assert quantity / config.LOT_SIZE_BTC == pytest.approx(
        round(quantity / config.LOT_SIZE_BTC)
    )
    assert quantity * 100.0 >= config.MIN_NOTIONAL_USDT


def test_planned_exit_open_precedes_same_minute_stop():
    first = pd.Timestamp("2024-01-01T00:01:00Z")
    second = pd.Timestamp("2024-01-08T00:01:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [first, second],
            "open": [100.0, 110.0],
            "high": [101.0, 111.0],
            "low": [99.0, 80.0],
            "close": [100.0, 109.0],
        }
    )
    dates = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-08T00:00:00Z")]
    )

    result = _simulate(minute_data, dates, [True, False])

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["exit_reason"] == "SIGNAL_OFF"
    assert trade["exit_open"] == 110.0
    assert trade["net_pnl_usdt"] > 0


def test_stop_uses_next_available_minute_and_counts_gap():
    entry = pd.Timestamp("2024-01-01T00:01:00Z")
    stop_bar = pd.Timestamp("2024-01-01T00:03:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [entry, stop_bar],
            "open": [100.0, 90.0],
            "high": [101.0, 91.0],
            "low": [99.0, 89.0],
            "close": [100.0, 90.0],
        }
    )
    dates = pd.DatetimeIndex([pd.Timestamp("2024-01-01T00:00:00Z")])

    result = _simulate(minute_data, dates, [True])

    assert result["trades"][0]["exit_reason"] == "STOP"
    assert result["trades"][0]["exit_open"] == 90.0
    assert result["counters"]["delayed_stop_check"] == 1


def test_missing_planned_exit_uses_first_available_open_and_counts_delay():
    entry = pd.Timestamp("2024-01-01T00:01:00Z")
    delayed_exit = pd.Timestamp("2024-01-08T00:02:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [entry, delayed_exit],
            "open": [100.0, 105.0],
            "high": [101.0, 106.0],
            "low": [99.0, 104.0],
            "close": [100.0, 105.0],
        }
    )
    dates = pd.DatetimeIndex(
        [pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-01-08T00:00:00Z")]
    )

    result = _simulate(minute_data, dates, [True, False])

    assert result["trades"][0]["exit_time"] == delayed_exit
    assert result["trades"][0]["exit_reason"] == "SIGNAL_OFF"
    assert result["counters"]["missing_planned_exit"] == 1
    assert result["counters"]["delayed_planned_exit"] == 1


def test_stop_requires_off_before_reentry():
    dates = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-01T00:00:00Z"),
            pd.Timestamp("2024-01-08T00:00:00Z"),
            pd.Timestamp("2024-01-15T00:00:00Z"),
            pd.Timestamp("2024-01-22T00:00:00Z"),
        ]
    )
    entry1 = dates[0] + pd.Timedelta(minutes=1)
    stop_bar = dates[0] + pd.Timedelta(minutes=2)
    entry2 = dates[3] + pd.Timedelta(minutes=1)
    minute_data = pd.DataFrame(
        {
            "open_time": [entry1, stop_bar, entry2],
            "open": [100.0, 90.0, 100.0],
            "high": [101.0, 91.0, 101.0],
            "low": [99.0, 89.0, 99.0],
            "close": [100.0, 90.0, 100.0],
        }
    )

    result = _simulate(minute_data, dates, [True, True, False, True])

    assert [trade["entry_decision_date"] for trade in result["trades"]] == [
        dates[0],
        dates[3],
    ]
    assert result["trades"][0]["exit_reason"] == "STOP"


def test_missing_entry_ambiguous_minute_is_skipped_and_counted():
    scheduled = pd.Timestamp("2024-01-01T00:01:00Z")
    next_minute = pd.Timestamp("2024-01-01T00:02:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [next_minute],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.0],
        }
    )
    dates = pd.DatetimeIndex([pd.Timestamp("2024-01-01T00:00:00Z")])

    result = _simulate(minute_data, dates, [True], {scheduled})

    assert result["trades"] == []
    assert result["counters"]["ambiguous_entry_minute"] == 1


def test_forced_end_uses_last_open_before_strict_cutoff():
    minute_data = pd.DataFrame(
        {
            "open_time": pd.to_datetime(
                [
                    "2025-06-30T23:58:00Z",
                    "2025-06-30T23:59:00Z",
                ],
                utc=True,
            ),
            "open": [100.0, 200.0],
            "high": [101.0, 201.0],
            "low": [99.0, 199.0],
            "close": [100.0, 200.0],
        }
    )
    minute = MinuteSeries(minute_data)

    assert minute.forced_end_index == 0


def test_forced_end_closes_at_last_allowed_candle_close():
    decision_date = pd.Timestamp("2025-06-23T00:00:00Z")
    entry = decision_date + pd.Timedelta(minutes=1)
    last_allowed = pd.Timestamp("2025-06-30T23:58:00Z")
    cutoff_minute = pd.Timestamp("2025-06-30T23:59:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [entry, last_allowed, cutoff_minute],
            "open": [100.0, 105.0, 999.0],
            "high": [101.0, 106.0, 1000.0],
            "low": [99.0, 104.0, 998.0],
            "close": [100.0, 105.0, 999.0],
        }
    )

    result = _simulate(minute_data, pd.DatetimeIndex([decision_date]), [True])

    trade = result["trades"][0]
    assert trade["FORCED_END"] is True
    assert trade["exit_time"] == last_allowed
    assert trade["exit_open"] == 105.0


def test_maximum_hold_exits_at_56_calendar_days():
    first_decision = pd.Timestamp("2024-01-01T00:00:00Z")
    dates = pd.date_range(first_decision, periods=9, freq="7D")
    entry = first_decision + pd.Timedelta(minutes=1)
    exit_decision = first_decision + pd.Timedelta(days=56)
    exit_open = exit_decision + pd.Timedelta(minutes=1)
    minute_data = pd.DataFrame(
        {
            "open_time": [entry, exit_open],
            "open": [100.0, 105.0],
            "high": [101.0, 106.0],
            "low": [99.0, 104.0],
            "close": [100.0, 105.0],
        }
    )

    result = _simulate(minute_data, dates, [True] * len(dates))

    assert result["trades"][0]["exit_reason"] == "MAX_HOLD"
    assert result["trades"][0]["days_held"] == 56


def test_min_notional_failure_is_counted():
    entry = pd.Timestamp("2024-01-01T00:01:00Z")
    minute_data = pd.DataFrame(
        {
            "open_time": [entry],
            "open": [2_000_000_000.0],
            "high": [2_000_000_001.0],
            "low": [2_000_000_000.0],
            "close": [2_000_000_000.0],
        }
    )
    dates = pd.DatetimeIndex([pd.Timestamp("2024-01-01T00:00:00Z")])

    result = _simulate(minute_data, dates, [True])

    assert result["trades"] == []
    assert result["counters"]["below_min_notional"] == 1


def test_bootstrap_week_weights_sum_to_unique_week_count():
    dates = pd.date_range("2020-12-20", "2021-02-10", freq="D", tz="UTC")
    keys = list(dict.fromkeys((int(day.isocalendar().year), int(day.isocalendar().week)) for day in dates))
    weights = _bootstrap_weights(len(keys), np.random.default_rng(config.SEED))
    assert len(weights) == len(keys)
    assert weights.sum() == len(keys)


def test_criteria_map_only_explicit_pf_to_stress():
    base = {
        "profit_factor": 1.3,
        "phase_pf_above_one_count": 5,
        "profit_factor_without_best_three": 1.1,
        "net_pnl_usdt": 100.0,
        "max_annual_profit_share": 0.4,
        "trade_count": 120,
    }
    stress = {"profit_factor": 1.11}
    bootstrap = {"percentiles": {"10": 0.01}}
    placebo = {"p_value": 0.05}

    criteria = evaluate_criteria(base, stress, bootstrap, placebo)

    assert criteria["pf_base"]["scenario"] == "BASE"
    assert criteria["pf_stress"]["scenario"] == "STRESS"
    for name in (
        "bootstrap_net_r_p10",
        "phases_pf_above_one",
        "pf_without_best_three",
        "annual_profit_concentration",
        "placebo_p",
        "minimum_trades",
    ):
        assert criteria[name]["scenario"] == "BASE"


def test_profit_factor_without_losses_is_positive_infinity():
    trades = pd.DataFrame({"net_pnl_usdt": [10.0, 0.0]})
    assert _profit_factor(trades) == float("inf")


def test_scenario_metrics_placebo_benchmarks_report_and_ledger(
    tmp_path, monkeypatch
):
    dates = pd.date_range("2024-01-01", periods=130, freq="D", tz="UTC")
    signals = pd.DataFrame(
        {
            "signal_on": [True] + [False] * 6 + [False] * (len(dates) - 7),
            "signal_defined": True,
            "atr": 1.0,
            "atr_defined": True,
            "missing_current_r": False,
            "missing_rank_history": False,
            "missing_atr_window": False,
        },
        index=dates,
    )
    entry = dates[0] + pd.Timedelta(minutes=1)
    exit_time = dates[7] + pd.Timedelta(minutes=1)
    final = dates[-1] + pd.Timedelta(hours=23)
    minute_data = pd.DataFrame(
        {
            "open_time": [entry, exit_time, final],
            "open": [100.0, 110.0, 110.0],
            "high": [101.0, 111.0, 111.0],
            "low": [99.0, 80.0, 109.0],
            "close": [100.0, 109.0, 110.0],
        }
    )
    context = build_scenario_context(
        minute_data, set(), dates, signals, "BASE"
    )
    run = run_scenario(
        minute_data,
        set(),
        dates,
        signals,
        "BASE",
        context=context,
    )
    metrics = summarize_scenario(run)
    monkeypatch.setattr(config, "BOOT_DRAWS", 4)
    monkeypatch.setattr(config, "PLACEBO_DRAWS", 2)
    bootstrap = bootstrap_mean_net_r(run["trades"], dates)
    placebo = placebo_test(context, dates, signals, metrics["mean_net_r"])
    benchmark = calculate_buy_and_hold(run, dates, signals)
    criteria = evaluate_criteria(
        metrics,
        {"profit_factor": 1.0},
        bootstrap,
        placebo,
    )
    report = stage2_reporting.make_report(
        {
            "source_rows": 3,
            "usable_minute_rows": 3,
            "ambiguous_minute_buckets": 0,
            "rows_removed_from_ambiguous_minutes": 0,
            "incomplete_d1_days": 0,
            "missing_d1_calendar_days": 0,
            "incomplete_d1_days_by_year": {},
            "full_d1_days": 0,
            "min_open_time": entry.isoformat(),
            "max_open_time": final.isoformat(),
            "cutoff_assertion": True,
        },
        {"candidate_execution_days": len(dates)},
        {"BASE": metrics, "STRESS": metrics},
        placebo,
        bootstrap,
        {"BASE": benchmark, "STRESS": benchmark},
        criteria,
    )
    monkeypatch.setattr(stage2_reporting, "ROOT", tmp_path)
    legacy = stage2_reporting.LEGACY_LEDGER_FIELDS
    with (tmp_path / "ledger.csv").open("w", encoding="utf-8", newline="") as file:
        writer = __import__("csv").DictWriter(
            file, fieldnames=legacy + ["stage"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerow(
            {
                **{field: f"legacy-{field}" for field in legacy},
                "stage": "1",
            }
        )
    old_values = ["legacy-" + field for field in legacy]
    stage2_reporting.write_outputs(
        run["trades"],
        {"placebo": {"p_value": placebo["p_value"]}, "pf": float("inf")},
        report,
        "new-run",
        "2026-01-01T00:00:00+00:00",
        "config-hash",
        "data-hash",
        "git-hash",
        True,
    )

    with (tmp_path / "ledger.csv").open("r", encoding="utf-8", newline="") as file:
        ledger_rows = list(__import__("csv").DictReader(file))
    assert [ledger_rows[0][field] for field in legacy] == old_values
    assert ledger_rows[1]["stage"] == "2"
    assert ledger_rows[1]["S_base"] == ""
    assert ledger_rows[1]["decision"] == ""
    assert ledger_rows[1]["p_placebo"] == str(placebo["p_value"])
    assert (tmp_path / config.OUTPUT_REPORT).read_text(encoding="utf-8") == report
    assert '"pf": "+inf"' in (
        tmp_path / config.OUTPUT_RESULTS
    ).read_text(encoding="utf-8")
