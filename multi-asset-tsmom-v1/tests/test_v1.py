from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import config_v1 as config
from v1_blocks import build_blocks
from v1_data import AssetData, load_v1_data
from v1_metrics import (
    bootstrap_weights,
    decision_v1,
    placebo_stat_for_shift,
    run_bootstrap,
    run_placebo,
    summarize_metrics,
    union_iso_weeks,
)
from v1_reporting import LEGACY_LEDGER_FIELDS, append_ledger_row
from v1_signal import align_signals_to_calendar, build_asset_signals


def _asset(
    dates: pd.DatetimeIndex,
    opens: list[float | None],
    closes: list[float | None],
    kind: str = "ETF",
    asset: str = "SPY",
) -> AssetData:
    frame = pd.DataFrame(
        {
            "open": opens,
            "close": closes,
            "row_present": True,
        },
        index=dates,
    )
    return AssetData(
        asset=asset,
        ticker=asset,
        kind=kind,
        timezone="America/New_York",
        frame=frame,
        data_hash="0" * 64,
        diagnostics={},
    )


def _business_day_trend(
    asset: str = "SPY",
    kind: str = "ETF",
    direction: int = 1,
    missing_rows: tuple[int, ...] = (),
    missing_closes: tuple[int, ...] = (),
) -> AssetData:
    business_dates = pd.bdate_range("2018-01-01", periods=780)
    calendar = pd.date_range(
        business_dates.min(),
        business_dates.max(),
        freq="D",
        name="date",
    )
    steps = np.arange(len(business_dates), dtype=float)
    close_values = np.exp(direction * (0.003 * steps + 0.000005 * steps**2))
    frame = pd.DataFrame(index=calendar)
    frame["open"] = np.nan
    frame["close"] = np.nan
    frame["row_present"] = False
    frame.loc[business_dates, "open"] = close_values
    frame.loc[business_dates, "close"] = close_values
    frame.loc[business_dates, "row_present"] = True
    for index in missing_rows:
        day = business_dates[index]
        frame.loc[day, ["open", "close"]] = np.nan
        frame.loc[day, "row_present"] = False
    for index in missing_closes:
        frame.loc[business_dates[index], "close"] = np.nan
    return AssetData(
        asset,
        asset,
        kind,
        "America/New_York",
        frame,
        "0" * 64,
        {},
    )


def _test_metrics(
    on_block_count: int = 300,
    t: float = 0.01,
    p: float = 0.05,
    p10: float = 0.001,
    positive_assets: int = 7,
    leave_year: dict[str, float] | None = None,
    top5: float = 0.001,
) -> dict:
    return {
        "on_block_count": on_block_count,
        "pooled_t": t,
        "positive_asset_count": positive_assets,
        "placebo": {"p_value": p},
        "bootstrap": {"percentiles": {"10": p10}},
        "robustness": {
            "leave_one_year_out": leave_year or {"2024": 0.001},
            "top_5_percent_removed_t": top5,
        },
    }


def test_v1_real_data_hashes_and_cutoff():
    assets = load_v1_data()
    assert set(assets) == set(config.ASSETS)
    for data in assets.values():
        assert data.data_hash == config.DATA_SHA256[data.asset]
        assert data.frame.index.max() < pd.Timestamp(config.CUTOFF_DATE)


def test_signal_uses_only_pre_entry_rows():
    dates = pd.date_range("2020-01-01", periods=900, freq="D")
    closes = [100.0 + i * 0.1 for i in range(len(dates))]
    opens = closes.copy()
    asset = _asset(dates, opens, closes)
    signals_before, _ = build_asset_signals(asset)

    changed = closes.copy()
    t = dates[-20]
    for i, d in enumerate(dates):
        if d > t:
            changed[i] = 100_000.0 - i
    altered = _asset(dates, opens, changed)
    signals_after, _ = build_asset_signals(altered)

    assert signals_before.loc[:t].equals(signals_after.loc[:t])


def test_three_year_uptrend_has_defined_signals_and_long_entries():
    asset = _business_day_trend()
    signals, diagnostics = build_asset_signals(asset)
    assert diagnostics["signal_defined"] > len(asset.frame) // 3
    assert diagnostics["on_long"] > 0
    assert diagnostics["on_short"] == 0


def test_three_year_downtrend_has_fx_short_entries():
    asset = _business_day_trend("EURUSD", "FX", direction=-1)
    _, diagnostics = build_asset_signals(asset)
    assert diagnostics["signal_defined"] > len(asset.frame) // 3
    assert diagnostics["on_short"] > 0


def test_weekends_and_missing_rows_do_not_make_all_signals_undefined():
    asset = _business_day_trend(
        missing_rows=tuple(range(300, 305)),
        missing_closes=(450, 600),
    )
    _, diagnostics = build_asset_signals(asset)
    assert (~asset.frame["row_present"]).any()
    assert diagnostics["signal_defined"] > 0
    assert diagnostics["signal_undefined"] < diagnostics["source_rows"]


def test_real_spy_data_has_defined_signals_without_reporting_prices():
    path = (
        Path(__file__).resolve().parents[1]
        / config.DATA_DIR
        / config.ASSETS["SPY"]["filename"]
    )
    raw = pd.read_csv(path, usecols=["date", "open", "close"])
    dates = pd.to_datetime(raw.pop("date"), format="%Y-%m-%d", errors="raise")
    raw.index = pd.DatetimeIndex(dates, name="date")
    for column in ("open", "close"):
        raw[column] = pd.to_numeric(raw[column], errors="raise")
    calendar = pd.date_range(raw.index.min(), raw.index.max(), freq="D", name="date")
    row_present = pd.Series(True, index=raw.index).reindex(
        calendar, fill_value=False
    )
    frame = raw.reindex(calendar)
    frame["row_present"] = row_present.astype(bool)
    asset = AssetData(
        "SPY",
        config.ASSETS["SPY"]["ticker"],
        "ETF",
        config.ASSETS["SPY"]["timezone"],
        frame,
        "",
        {},
    )
    _, diagnostics = build_asset_signals(asset)
    assert diagnostics["signal_defined"] > 0


def test_placebo_signals_align_to_one_shared_calendar():
    first_dates = pd.date_range("2020-01-01", periods=5, freq="D")
    second_dates = pd.date_range("2020-01-03", periods=5, freq="D")
    first = _asset(first_dates, [100.0] * 5, [100.0] * 5, asset="SPY")
    second = _asset(
        second_dates, [100.0] * 5, [100.0] * 5, asset="EFA"
    )
    aligned = align_signals_to_calendar(
        {"SPY": first, "EFA": second},
        {
            "SPY": pd.Series([1.0, 0.0, -1.0, 0.0, 1.0], index=first_dates),
            "EFA": pd.Series([1.0, 0.0, -1.0, 0.0, 1.0], index=second_dates),
        },
    )
    assert aligned["SPY"].index.equals(aligned["EFA"].index)
    assert len(aligned["SPY"]) == 7
    assert pd.isna(aligned["EFA"].iloc[0])
    assert pd.isna(aligned["SPY"].iloc[-1])


@pytest.mark.parametrize(
    ("kind", "direction", "entry", "exit", "expected_gross_sign"),
    [
        ("ETF", 1, 100.0, 110.0, 1),
        ("ETF", 1, 110.0, 100.0, -1),
        ("FX", -1, 100.0, 90.0, 1),
        ("FX", -1, 90.0, 100.0, -1),
    ],
)
def test_long_short_sign_and_round_trip_cost(
    kind, direction, entry, exit, expected_gross_sign
):
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    opens = [entry] + [100.0] * 6 + [exit]
    closes = [100.0] * len(dates)
    asset = _asset(dates, opens, closes, kind=kind)
    signals = pd.Series(0.0, index=dates)
    signals.iloc[0] = direction

    blocks, _, _ = build_blocks({asset.asset: asset}, {asset.asset: signals})

    assert len(blocks) == 1
    block = blocks.iloc[0]
    gross = direction * (exit / entry - 1)
    cost = config.FX_ROUND_TRIP_COST if kind == "FX" else config.ETF_ROUND_TRIP_COST
    assert np.sign(gross) == expected_gross_sign
    assert block["net"] == pytest.approx(gross - cost)


def test_missing_exit_row_and_empty_values_are_counted_separately():
    dates = pd.date_range("2024-01-01", periods=15, freq="D")
    opens: list[float | None] = [100.0] * len(dates)
    closes: list[float | None] = [100.0] * len(dates)
    opens[7] = None
    opens[4] = None
    closes[8] = None
    closes[9] = None
    closes[5] = None
    row_present = [True] * len(dates)
    row_present[10] = False
    frame = pd.DataFrame(
        {"open": opens, "close": closes, "row_present": row_present},
        index=dates,
    )
    asset = AssetData("SPY", "SPY", "ETF", "America/New_York", frame, "0" * 64, {})
    signals = pd.Series(0.0, index=dates)
    signals.iloc[0] = 1.0
    signals.iloc[1] = 1.0
    signals.iloc[2] = 1.0
    signals.iloc[3] = 1.0
    signals.iloc[4] = 1.0
    signals.iloc[5] = 1.0

    blocks, _, counters = build_blocks({"SPY": asset}, {"SPY": signals})

    assert blocks.empty
    assert counters["SPY"]["exit_empty_open"] == 1
    assert counters["SPY"]["exit_empty_close"] == 2
    assert counters["SPY"]["exit_no_row"] == 1
    assert counters["SPY"]["entry_empty_open"] == 1
    assert counters["SPY"]["entry_empty_close"] == 1


def test_opportunities_include_off_and_undefined_signal_dates():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    asset = _asset(dates, [100.0] * 10, [100.0] * 10)
    signals = pd.Series(0.0, index=dates)
    signals.iloc[0] = 1.0
    signals.iloc[2] = np.nan

    blocks, opportunities, _ = build_blocks(
        {"SPY": asset},
        {"SPY": signals},
    )

    assert len(blocks) == 1
    assert len(opportunities) == 3


def _cyclic_on_runs(values: np.ndarray) -> list[int]:
    on = values == 1
    if not np.any(on):
        return []
    if np.all(on):
        return [len(on)]
    start = int(np.flatnonzero(~on)[0])
    ordered = np.roll(on, -start - 1)
    runs: list[int] = []
    length = 0
    for value in ordered:
        if value:
            length += 1
        elif length:
            runs.append(length)
            length = 0
    if length:
        runs.append(length)
    return sorted(runs)


def test_cyclic_shift_preserves_on_share_and_run_lengths():
    values = np.array([0, 1, 1, 0, np.nan, 1, 0, 1, 1, 1], dtype=float)
    shifted = np.roll(values, 4)
    assert np.count_nonzero(values == 1) == np.count_nonzero(shifted == 1)
    assert _cyclic_on_runs(values) == _cyclic_on_runs(shifted)


def test_iso_week_union_is_unique_and_bootstrap_weights_sum_to_weeks():
    dates = pd.date_range("2019-12-29", periods=20, freq="D")
    asset = _asset(dates, [100.0] * len(dates), [100.0] * len(dates))
    weeks = union_iso_weeks({"SPY": asset})
    assert len(weeks) == len(set(weeks))
    weights = bootstrap_weights(len(weeks), np.random.default_rng(10))
    assert int(weights.sum()) == len(weeks)


def test_placebo_seed_is_reproducible_and_zero_shift_matches_observed():
    dates = pd.date_range("2024-01-01", periods=180, freq="D")
    signals = pd.Series(0.0, index=dates)
    signals.iloc[[20, 80, 150]] = 1.0
    opportunities = pd.DataFrame(
        {
            "asset": ["SPY"] * len(dates),
            "calendar_position": np.arange(len(dates)),
            "entry_open": [100.0] * len(dates),
            "exit_open": [102.0] * len(dates),
            "cost": [config.ETF_ROUND_TRIP_COST] * len(dates),
        }
    )
    t_obs = placebo_stat_for_shift(
        opportunities,
        {"SPY": signals},
        0,
    )
    assert t_obs is not None
    original_draws = config.PLACEBO_DRAWS
    config.PLACEBO_DRAWS = 12
    try:
        a = run_placebo(
            opportunities,
            {"SPY": signals},
            t_obs,
            np.random.default_rng(config.SEED),
        )
        b = run_placebo(
            opportunities,
            {"SPY": signals},
            t_obs,
            np.random.default_rng(config.SEED),
        )
    finally:
        config.PLACEBO_DRAWS = original_draws
    assert a == b
    assert t_obs == pytest.approx(0.02 - config.ETF_ROUND_TRIP_COST)


def test_placebo_empty_draws_count_as_exceedances():
    dates = pd.date_range("2023-01-01", periods=180, freq="D")
    signals = pd.Series(0.0, index=dates)
    opportunities = pd.DataFrame(
        {
            "asset": ["SPY"] * len(dates),
            "calendar_position": np.arange(len(dates)),
            "entry_open": [100.0] * len(dates),
            "exit_open": [101.0] * len(dates),
            "cost": [config.ETF_ROUND_TRIP_COST] * len(dates),
        }
    )
    original_draws = config.PLACEBO_DRAWS
    config.PLACEBO_DRAWS = 5
    try:
        result = run_placebo(
            opportunities,
            {"SPY": signals},
            0.01,
            np.random.default_rng(config.SEED),
        )
    finally:
        config.PLACEBO_DRAWS = original_draws
    assert result["draws_without_on_blocks"] == 5
    assert result["exceed_count"] == 5
    assert result["p_value"] == 1.0


def test_bootstrap_skips_zero_on_weight_samples():
    dates = pd.date_range("2024-01-01", periods=14, freq="D")
    asset = _asset(dates, [100.0] * 14, [100.0] * 14)
    weeks = union_iso_weeks({"SPY": asset})
    blocks = pd.DataFrame(
        columns=[
            "asset",
            "entry_date",
            "exit_date",
            "direction",
            "entry_open",
            "exit_open",
            "gross_net_return",
            "cost",
            "net",
            "iso_year",
            "iso_week",
            "calendar_position",
        ]
    )
    original = config.BOOT_DRAWS
    config.BOOT_DRAWS = 5
    try:
        result = run_bootstrap(blocks, weeks, np.random.default_rng(config.SEED))
    finally:
        config.BOOT_DRAWS = original
    assert result["draws_without_on_blocks"] == 5
    assert result["percentiles"]["10"] is None


def test_decision_v1_matrix_boundaries():
    assert decision_v1(_test_metrics(on_block_count=299)) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(t=0)) == "ABANDON"
    assert decision_v1(_test_metrics(p=0.20001)) == "ABANDON"
    assert decision_v1(_test_metrics(positive_assets=4)) == "ABANDON"
    assert decision_v1(_test_metrics()) == "CONTINUE"
    assert decision_v1(_test_metrics(p=0.15)) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(p=0.20)) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(positive_assets=6)) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(p10=0)) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(leave_year={"2023": 0})) == "INSUFFICIENT_DATA"
    assert decision_v1(_test_metrics(top5=0)) == "INSUFFICIENT_DATA"


def test_ledger_append_preserves_legacy_row(tmp_path: Path, monkeypatch):
    import v1_reporting

    ledger = tmp_path / "ledger.csv"
    legacy = {key: f"old-{key}" for key in LEGACY_LEDGER_FIELDS}
    with ledger.open("w", encoding="utf-8", newline="") as file:
        writer = __import__("csv").DictWriter(
            file,
            fieldnames=LEGACY_LEDGER_FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerow(legacy)
    monkeypatch.setattr(v1_reporting, "ROOT", tmp_path)
    monkeypatch.setattr(config, "OUTPUT_LEDGER", "ledger.csv")
    new = {key: f"new-{key}" for key in LEGACY_LEDGER_FIELDS}
    v1_reporting.append_ledger_row(new)
    with ledger.open(encoding="utf-8", newline="") as file:
        rows = list(__import__("csv").DictReader(file))
    assert rows[0] == legacy
    assert rows[1] == new


def test_block_exit_is_exactly_seven_calendar_days():
    dates = pd.date_range("2024-01-01", periods=8, freq="D")
    asset = _asset(dates, [100.0] * 8, [100.0] * 8)
    signals = pd.Series(0.0, index=dates)
    signals.iloc[0] = 1.0
    blocks, _, _ = build_blocks({"SPY": asset}, {"SPY": signals})
    assert len(blocks) == 1
    assert blocks.iloc[0]["exit_date"] - blocks.iloc[0]["entry_date"] == timedelta(days=7)


def test_manifest_config_has_all_observed_data_hashes():
    assert set(config.DATA_SHA256) == set(config.ASSETS)
    assert config.PERIOD2 == 1751320799
    assert config.SOURCE == "Yahoo Finance Chart API"
