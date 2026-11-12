from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import pyarrow as pa
import pyarrow.parquet as pq

import config
from blocks import build_blocks, trade_values, week_keys_for_dates
from data import load_research_data
from resampling import bootstrap_s, bootstrap_week_weights, shifted_states
from signals import build_execution_signals, circular_run_lengths


def test_signal_is_lookahead_safe() -> None:
    dates = pd.date_range("2017-01-01", periods=1100, freq="D", tz="UTC")
    rng = np.random.default_rng(42)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates)))), index=dates)
    execution_date = dates[900] + pd.Timedelta(days=1)
    end = dates[-1] + pd.Timedelta(days=1)
    before = build_execution_signals(close, end).loc[execution_date]

    changed = close.copy()
    changed.loc[execution_date:] = rng.uniform(10, 1000, len(changed.loc[execution_date:]))
    after = build_execution_signals(changed, end).loc[execution_date]
    assert before["signal_on"] == after["signal_on"]
    assert before["return"] == pytest.approx(after["return"])
    assert before["rank"] == pytest.approx(after["rank"])


def test_trade_spends_exact_notional_including_fee() -> None:
    values = trade_values(
        30_000.0,
        30_000.0,
        config.BASE["SPREAD"],
        config.BASE["SLIP"],
    )
    assert values["spent_usdt"] == pytest.approx(config.NOTIONAL_USDT, abs=1e-10)


@pytest.mark.parametrize(
    ("costs", "expected"),
    [
        (config.BASE, -0.002497),
        (config.STRESS, -0.003195),
    ],
)
def test_flat_price_costs(costs: dict[str, float], expected: float) -> None:
    values = trade_values(100.0, 100.0, costs["SPREAD"], costs["SLIP"])
    spread = costs["SPREAD"]
    slip = costs["SLIP"]
    exact = (1 - spread / 2 - slip) * (1 - config.FEE) / (
        (1 + spread / 2 + slip) * (1 + config.FEE)
    ) - 1
    assert values["net"] == pytest.approx(exact, abs=1e-12)
    assert values["net"] == pytest.approx(expected, abs=0.00003)


@pytest.mark.parametrize("exit_open", [110.0, 90.0])
def test_block_net_uses_exit_open_for_rise_and_fall(exit_open: float) -> None:
    execution_date = pd.Timestamp("2024-01-01T00:00:00Z")
    candle_opens = []
    for costs in (config.BASE, config.STRESS):
        delay = pd.Timedelta(minutes=costs["DELAY_MIN"])
        candle_opens.extend(
            [
                (execution_date + delay, 100.0),
                (execution_date + pd.Timedelta(days=config.HOLD_DAYS) + delay, exit_open),
            ]
        )
    minute_data = pd.DataFrame(
        {
            "open_time": [timestamp for timestamp, _ in candle_opens],
            "open": [price for _, price in candle_opens],
        }
    )
    dates = pd.DatetimeIndex([execution_date])
    signals = pd.DataFrame({"signal_on": [True]}, index=dates)

    blocks, placebo_blocks, _ = build_blocks(minute_data, signals, dates)
    assert len(placebo_blocks) == 2
    for row in blocks.itertuples(index=False):
        costs = config.BASE if row.scenario == "BASE" else config.STRESS
        expected = trade_values(
            100.0,
            exit_open,
            costs["SPREAD"],
            costs["SLIP"],
        )
        assert row.net == pytest.approx(expected["net"])
        assert row.net != pytest.approx(0.0)


def test_iso_week_keys_and_bootstrap_weights() -> None:
    dates = pd.date_range("2020-12-20", "2021-02-10", freq="D", tz="UTC")
    keys = week_keys_for_dates(dates)
    assert len(keys) == len(set(keys))
    assert keys[0] == (2020, 51)
    assert keys[1] == (2020, 52)
    assert (2020, 53) in keys
    assert (2021, 1) in keys

    weights = bootstrap_week_weights(
        keys, config.BOOT_BLOCK_WEEKS, np.random.default_rng(config.SEED)
    )
    assert len(weights) == len(keys)
    assert int(weights.sum()) == len(keys)


def test_circular_shift_preserves_on_fraction_and_run_lengths() -> None:
    states = np.array([False, True, True, False, True, False, False, True, True, True])
    shifted = shifted_states(states, 4, minimum_circular_distance=2)
    assert np.mean(shifted == True) == pytest.approx(np.mean(states == True))
    assert circular_run_lengths(shifted == True) == circular_run_lengths(states == True)


def test_cutoff_rejects_future_rows_before_reading(tmp_path, monkeypatch) -> None:
    path = tmp_path / "synthetic.parquet"
    future = pd.Timestamp("2025-07-01T00:00:00Z")
    table = pa.table(
        {
            "open_time": pa.array([future.to_pydatetime()], type=pa.timestamp("us", tz="UTC")),
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
        }
    )
    pq.write_table(table, path)

    def should_not_read(*args, **kwargs):
        raise AssertionError("Parquet rows must not be read before metadata cutoff validation")

    monkeypatch.setattr(pd, "read_parquet", should_not_read)
    with pytest.raises(AssertionError, match="not before"):
        load_research_data(path)


def test_blocks_count_cutoff_and_missing_candles() -> None:
    dates = pd.date_range("2025-06-23", "2025-06-24", freq="D", tz="UTC")
    signals = pd.DataFrame(
        {"signal_on": [False, True]},
        index=dates,
    )
    minute_data = pd.DataFrame(
        {
            "open_time": [
                dates[0] + pd.Timedelta(minutes=config.STRESS["DELAY_MIN"]),
                dates[0]
                + pd.Timedelta(days=config.HOLD_DAYS, minutes=config.STRESS["DELAY_MIN"]),
            ],
            "open": [100.0, 100.0],
        }
    )
    blocks, placebo_blocks, excluded = build_blocks(minute_data, signals, dates)
    assert not blocks.empty
    assert not placebo_blocks.empty
    for scenario in ("BASE", "STRESS"):
        counts = excluded["by_scenario"][scenario]
        assert counts["cutoff_by_phase"]["1"] == 1
    assert excluded["by_scenario"]["BASE"]["missing_entry_by_phase"]["0"] == 1
    assert excluded["by_scenario"]["BASE"]["missing_exit_by_phase"]["0"] == 1
    assert excluded["by_scenario"]["STRESS"]["missing_any_candle_by_phase"]["0"] == 0


def test_bootstrap_counts_phases_excluded_for_zero_state_weight(monkeypatch) -> None:
    monkeypatch.setattr(config, "BOOT_DRAWS", 4)
    monkeypatch.setattr(config, "BOOT_BLOCK_WEEKS", 2)
    mondays = pd.date_range("2020-01-06", periods=12, freq="W-MON", tz="UTC")
    rows = []
    for monday in mondays:
        rows.extend(
            [
                {"execution_date": monday, "phase": 0, "signal_on": True, "net": 0.02},
                {
                    "execution_date": monday + pd.Timedelta(days=1),
                    "phase": 0,
                    "signal_on": False,
                    "net": -0.01,
                },
            ]
        )
    blocks = pd.DataFrame(rows)
    week_keys = week_keys_for_dates(mondays)
    result = bootstrap_s(blocks, week_keys)
    assert result["draws_with_excluded_phases"] == 4
    assert result["excluded_phase_occurrences"] == 4 * 6
    assert result["draws_with_no_valid_phases"] == 0


def test_research_dataset_and_cutoff_have_no_future_rows() -> None:
    frame, diagnostics = load_research_data()
    cutoff = pd.Timestamp(config.CUTOFF_UTC)
    assert (frame["open_time"] < cutoff).all()
    assert diagnostics["cutoff_assertion"] is True
