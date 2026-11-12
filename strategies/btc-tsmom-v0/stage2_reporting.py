from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config_stage2 as config


ROOT = Path(__file__).resolve().parent
LEGACY_LEDGER_FIELDS = [
    "run_id",
    "timestamp",
    "variant_id",
    "config_hash",
    "data_hash",
    "decision",
    "S_base",
    "p_placebo",
    "notes",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state() -> tuple[str, bool]:
    git_executable = shutil.which("git")
    if git_executable is None:
        fallback = Path("C:/Program Files/Git/cmd/git.exe")
        if not fallback.exists():
            raise FileNotFoundError("Git executable was not found")
        git_executable = str(fallback)
    commit = subprocess.run(
        [git_executable, "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        [git_executable, "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def canonical_config_json() -> str:
    return json.dumps(config.as_dict(), sort_keys=True, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        if math.isnan(numeric):
            return None
        if math.isinf(numeric):
            return "+inf" if numeric > 0 else "-inf"
        return numeric
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if value is pd.NA:
        return None
    return value


def _fmt(value: Any, decimals: int = 6) -> str:
    if value is None or value is pd.NA:
        return "N/A"
    if isinstance(value, (float, np.floating)) and math.isinf(float(value)):
        return "+inf" if float(value) > 0 else "-inf"
    if isinstance(value, (float, np.floating)) and math.isnan(float(value)):
        return "N/A"
    if isinstance(value, (bool, np.bool_)):
        return str(bool(value))
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{decimals}f}"
    return str(value)


def make_report(
    diagnostics: dict[str, Any],
    signal_exclusions: dict[str, Any],
    scenario_results: dict[str, dict[str, Any]],
    placebo: dict[str, Any],
    bootstrap: dict[str, Any],
    benchmarks: dict[str, Any],
    criteria: dict[str, Any],
) -> str:
    lines = [
        "# Stage 2 — V0",
        "",
        "Исторический бэктест BTCUSDT Spot; 7 независимых weekday-портфелей.",
        "",
        "## Данные",
        "",
        f"- Исходных строк Parquet: {diagnostics['source_rows']}",
        f"- Минутных строк после исключения неоднозначных минут: {diagnostics['usable_minute_rows']}",
        f"- Исключено неоднозначных минутных bucket: {diagnostics['ambiguous_minute_buckets']}",
        f"- Исключено строк из неоднозначных минут: {diagnostics['rows_removed_from_ambiguous_minutes']}",
        f"- Неполных D1: {diagnostics['incomplete_d1_days']}",
        f"- Дней без строк M1 в календарном диапазоне: {diagnostics['missing_d1_calendar_days']}",
        f"- Неполных D1 по годам: `{json.dumps(diagnostics['incomplete_d1_days_by_year'], sort_keys=True)}`",
        f"- Полных D1: {diagnostics['full_d1_days']}",
        f"- Минимальный нормализованный open_time: {diagnostics['min_open_time']}",
        f"- Максимальный нормализованный open_time: {diagnostics['max_open_time']}",
        f"- Проверка cutoff: {diagnostics['cutoff_assertion']}",
        "",
        "## Исключённые дни и сигналы",
        "",
    ]
    for key, value in signal_exclusions.items():
        lines.append(f"- {key}: {_fmt(value)}")

    for scenario in ("BASE", "STRESS"):
        result = scenario_results[scenario]
        lines.extend(
            [
                "",
                f"## {scenario}",
                "",
                f"- Сделок: {result['trade_count']}",
                f"- Gross PnL USDT: {_fmt(result['gross_pnl_usdt'])}",
                f"- Net PnL USDT: {_fmt(result['net_pnl_usdt'])}",
                f"- Profit factor: {_fmt(result['profit_factor'])}",
                f"- Средний net R: {_fmt(result['mean_net_r'])}",
                f"- Средняя по фазам максимальная просадка USDT: {_fmt(result['drawdown_max_usdt_mean_by_phase'])}",
                f"- Средняя по фазам максимальная просадка долей: {_fmt(result['drawdown_max_fraction_mean_by_phase'])}",
                f"- Средняя конечная equity по фазам: {_fmt(result['ending_equity_mean_by_phase'])}",
                f"- Доли прибыли лучших 1/3/5 сделок: `{json.dumps(_json_safe(result['best_trade_profit_contribution']), sort_keys=True)}`",
                f"- PF без трёх лучших: {_fmt(result['profit_factor_without_best_three'])}",
                f"- Доля чистой прибыли по годам: `{json.dumps(_json_safe(result['annual_profit_share']), sort_keys=True)}`",
                "",
                "| Фаза | Сделок | Gross PnL USDT | Net PnL USDT | PF | Mean net R | Max DD USDT | Max DD fraction | Ending equity |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in result["phases"]:
            lines.append(
                f"| {row['phase']} | {row['trade_count']} | "
                f"{_fmt(row['gross_pnl_usdt'])} | {_fmt(row['net_pnl_usdt'])} | "
                f"{_fmt(row['profit_factor'])} | {_fmt(row['mean_net_r'])} | "
                f"{_fmt(row['max_drawdown_usdt'])} | "
                f"{_fmt(row['max_drawdown_fraction'])} | "
                f"{_fmt(row['ending_equity'])} |"
            )
        lines.extend(
            [
                "",
                "| Месяц входа UTC | Сделок |",
                "|---|---:|",
            ]
        )
        for month, count in sorted(result["trades_by_entry_month"].items()):
            lines.append(f"| {month} | {count} |")
        lines.extend(
            [
                "",
                "| Год реализации UTC | Net PnL USDT | Profit share |",
                "|---:|---:|---:|",
            ]
        )
        for year in sorted(result["annual_net_profit_usdt"]):
            lines.append(
                f"| {year} | {_fmt(result['annual_net_profit_usdt'][year])} | "
                f"{_fmt(result['annual_profit_share'].get(year))} |"
            )
        lines.extend(["", "### Исполнение по фазам", ""])
        lines.extend(
            [
                "| Фаза | Кандидат-решения | Signal undefined | ATR missing | Entry missing | Entry ambiguous | Min notional | Planned exit missing | Planned exit ambiguous | Delayed stop checks | Delayed planned exits | Stop exits | Signal exits | Max hold exits | Forced end exits | Re-entry blocked |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for phase in range(7):
            counts = result["execution_counters"][str(phase)]
            lines.append(
                f"| {phase} | {counts['candidate_decisions']} | "
                f"{counts['undefined_signal']} | {counts['missing_atr']} | "
                f"{counts['missing_entry_candle']} | {counts['ambiguous_entry_minute']} | "
                f"{counts['below_min_notional']} | {counts['missing_planned_exit']} | "
                f"{counts['ambiguous_planned_exit']} | {counts['delayed_stop_check']} | "
                f"{counts['delayed_planned_exit']} | "
                f"{counts['stop_exits']} | {counts['signal_exits']} | "
                f"{counts['max_hold_exits']} | {counts['forced_end_exits']} | "
                f"{counts['reentry_blocked']} |"
            )

    lines.extend(
        [
            "",
            "## Bootstrap BASE",
            "",
            f"- Запрошено выборок: {bootstrap['draws_requested']}",
            f"- Валидных выборок: {bootstrap['draws_valid']}",
            f"- Выборок без сделок: {bootstrap['draws_without_trades']}",
            f"- ISO-недель: {bootstrap['week_count']}",
            f"- Длина блока, недель: {bootstrap['block_weeks']}",
            f"- Net R, 10-й перцентиль: {_fmt(bootstrap['percentiles']['10'])}",
            f"- Net R, 50-й перцентиль: {_fmt(bootstrap['percentiles']['50'])}",
            f"- Net R, 90-й перцентиль: {_fmt(bootstrap['percentiles']['90'])}",
            "",
            "## Placebo BASE",
            "",
            f"- Выборок: {placebo['draws']}",
            f"- Сдвиг дней: [{placebo['shift_range_inclusive'][0]}, {placebo['shift_range_inclusive'][1]}]",
            f"- Наблюдаемый pooled mean net R: {_fmt(placebo['observed_pooled_mean_net_r'])}",
            f"- Placebo >= observed: {placebo['placebo_ge_observed']}",
            f"- Неопределённых выборок: {placebo['undefined_draws']}",
            f"- p: {_fmt(placebo['p_value'])}",
            "",
            "## Buy-and-hold (справочно)",
            "",
        ]
    )
    for scenario in ("BASE", "STRESS"):
        benchmark = benchmarks[scenario]
        full = benchmark["full_period"]
        in_market = benchmark["in_market"]
        lines.extend(
            [
                f"### {scenario}",
                "",
                f"- Полный период: вход {full['entry_time']}, выход {full['exit_time']}, "
                f"ending equity {_fmt(full['ending_equity'])}, net return {_fmt(full['net_return'])}",
                f"- Только время в рынке, среднее по фазам: ending equity {_fmt(in_market['mean_ending_equity'])}, "
                f"net return {_fmt(in_market['mean_net_return'])}",
                "",
                "| Фаза | Сделок стратегии | Ending equity | Net return |",
                "|---:|---:|---:|---:|",
            ]
        )
        for row in in_market["phases"]:
            lines.append(
                f"| {row['phase']} | {row['trade_count']} | "
                f"{_fmt(row['ending_equity'])} | {_fmt(row['net_return'])} |"
            )

    lines.extend(
        [
            "",
            "## Критерии §5",
            "",
            "| Критерий | Сценарий | Значение | Порог | Выполнен |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for name, criterion in criteria.items():
        threshold = criterion.get("threshold")
        if threshold is None:
            threshold = criterion.get("threshold_exclusive")
        comparator = ">" if "threshold_exclusive" in criterion else ">="
        lines.append(
            f"| {name} | {criterion['scenario']} | {_fmt(criterion['value'])} | "
            f"{criterion['operator']} {_fmt(threshold)} | {criterion['passed']} |"
        )
    lines.append("")
    return "\n".join(lines)


def append_ledger_row(row: dict[str, Any]) -> None:
    ledger_path = ROOT / config.OUTPUT_LEDGER
    expected = LEGACY_LEDGER_FIELDS + ["stage"]
    with ledger_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        fields = next(reader, None)
    if fields != expected:
        raise ValueError(
            f"Unexpected migrated ledger header: {fields!r}; expected {expected!r}"
        )
    with ledger_path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=expected, lineterminator="\n")
        writer.writerow(row)


def append_failed_run(
    run_id: str,
    timestamp: str,
    config_hash: str,
    data_hash: str,
    error: BaseException | None,
) -> None:
    detail = (
        "Stage 2 failed before output completion"
        if error is None
        else f"FAILED: {type(error).__name__}: {error}"
    )
    append_ledger_row(
        {
            "run_id": run_id,
            "timestamp": timestamp,
            "variant_id": config.VARIANT_ID,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "decision": "",
            "S_base": "",
            "p_placebo": "",
            "notes": detail,
            "stage": str(config.STAGE),
        }
    )


def write_outputs(
    blocks: pd.DataFrame,
    results: dict[str, Any],
    report: str,
    run_id: str,
    timestamp: str,
    config_hash: str,
    data_hash: str,
    git_hash: str,
    git_dirty: bool,
) -> None:
    blocks.to_csv(
        ROOT / config.OUTPUT_BLOCKS,
        index=False,
        float_format="%.12g",
        encoding="utf-8",
    )
    (ROOT / config.OUTPUT_RESULTS).write_text(
        json.dumps(_json_safe(results), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    (ROOT / config.OUTPUT_REPORT).write_text(report, encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "timestamp": timestamp,
        "git_hash": git_hash,
        "git_dirty": git_dirty,
        "config": config.as_dict(),
        "config_hash": config_hash,
        "data_path": config.DATA_PATH,
        "data_hash": data_hash,
        "variant_id": config.VARIANT_ID,
        "stage": config.STAGE,
    }
    (ROOT / config.OUTPUT_MANIFEST).write_text(
        json.dumps(_json_safe(manifest), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )

    append_ledger_row(
        {
            "run_id": run_id,
            "timestamp": timestamp,
            "variant_id": config.VARIANT_ID,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "decision": "",
            "S_base": "",
            "p_placebo": results["placebo"]["p_value"],
            "notes": "Stage 2 results in results_stage2.json",
            "stage": str(config.STAGE),
        }
    )
