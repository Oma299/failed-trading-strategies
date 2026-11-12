from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import config_v1 as config
from v1_data import AssetData, ROOT

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
    "stage",
]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def git_state() -> tuple[str, bool]:
    git = r"C:\Program Files\Git\cmd\git.exe"
    revision = subprocess.run(
        [git, "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        [git, "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return revision, bool(status.strip())


def _format_number(value: Any, digits: int = 8) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.{digits}f}"


def make_report(
    assets: dict[str, AssetData],
    signal_diagnostics: dict[str, dict[str, Any]],
    block_counters: dict[str, dict[str, int]],
    metrics: dict[str, Any],
) -> str:
    lines = [
        "# V1 — дневная проверка моментума",
        "",
        "Источник: Yahoo Finance Chart API; daily interval.",
        f"Фактический period2: {config.PERIOD2} (exclusive).",
        f"Cutoff assertion max(date) < {config.CUTOFF_DATE}: passed.",
        "FX session-date label: Yahoo Europe/London; timezone conversion не выполнялась.",
        "",
        "## Данные и пропуски",
        "",
        "| Актив | Перв./последняя дата | Баров | Дней без строки | Пустой Open | Пустой Close | SHA256 совпал |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for asset, data in assets.items():
        diag = data.diagnostics
        lines.append(
            f"| {asset} | {diag['first_date']} / {diag['last_date']} | "
            f"{diag['daily_bars']} | {diag['no_row_days']} | "
            f"{diag['empty_open_rows']} | {diag['empty_close_rows']} | yes |"
        )

    lines.extend(["", "## Исключения и сигналы", ""])
    lines.append(
        "| Актив | Даты с Open | Сигнал undefined | ON long | ON short | OFF | "
        "Entry нет строки | Entry пустой Open | Entry пустой Close | "
        "Exit нет строки | Exit пустой Open | Exit пустой Close |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for asset in assets:
        signal = signal_diagnostics[asset]
        counters = block_counters[asset]
        lines.append(
            f"| {asset} | {counters['executable_dates']} | "
            f"{signal['signal_undefined']} | {signal['on_long']} | "
            f"{signal['on_short']} | {signal['off']} | "
            f"{counters['entry_no_row']} | {counters['entry_empty_open']} | "
            f"{counters['entry_empty_close']} | {counters['exit_no_row']} | "
            f"{counters['exit_empty_open']} | {counters['exit_empty_close']} |"
        )
    lines.extend(["", "## Результаты", ""])
    lines.extend(
        [
            f"- Исполнимых ON-блоков: {metrics['on_block_count']}",
            f"- Pooled T: {_format_number(metrics['pooled_t'])}",
            f"- Положительных T_asset: {metrics['positive_asset_count']} из 11",
            f"- Placebo p: {_format_number(metrics['placebo']['p_value'])}",
            f"- Placebo выборок без ON-блоков: "
            f"{metrics['placebo']['draws_without_on_blocks']}",
            f"- Bootstrap p10: "
            f"{_format_number(metrics['bootstrap']['percentiles']['10'])}",
            f"- Bootstrap выборок без ON-весов: "
            f"{metrics['bootstrap']['draws_without_on_blocks']}",
            f"- Bootstrap валидных выборок: {metrics['bootstrap']['draws_valid']}",
            f"- T после удаления лучших 5%: "
            f"{_format_number(metrics['robustness']['top_5_percent_removed_t'])}",
            f"- Удалено лучших блоков: "
            f"{metrics['robustness']['removed_best_block_count']}",
            f"- Решение decision_v1(): {metrics['decision']}",
            "",
            "### T_asset",
            "",
            "| Актив | Исполнимых ON-блоков | T_asset |",
            "|---|---:|---:|",
        ]
    )
    for asset in config.ASSETS:
        block_assets = metrics.get("blocks", pd.DataFrame()).get(
            "asset", pd.Series(dtype=str)
        )
        count = int((block_assets == asset).sum())
        lines.append(
            f"| {asset} | {count} | "
            f"{_format_number(metrics['t_asset'][asset])} |"
        )
    lines.extend(["", "### T без каждого года по дате E", ""])
    for year, value in metrics["robustness"]["leave_one_year_out"].items():
        lines.append(f"- Без {year}: {_format_number(value)}")
    lines.extend(
        [
            "",
            "Ограничение данных: Yahoo quote OHLC без учёта дивидендов и "
            "корпоративных действий; это может занижать long-доходность и "
            "одинаково относится к исходным и placebo-сигналам.",
        ]
    )
    return "\n".join(lines)


def append_ledger_row(row: dict[str, str]) -> None:
    path = ROOT / config.OUTPUT_LEDGER
    with path.open("r", encoding="utf-8", newline="") as file:
        fields = next(csv.reader(file), None)
    if fields != LEGACY_LEDGER_FIELDS:
        raise ValueError(f"Unexpected ledger header: {fields!r}")
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=LEGACY_LEDGER_FIELDS,
            lineterminator="\n",
        )
        writer.writerow(row)


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
    (ROOT / config.OUTPUT_BLOCKS).write_text(
        blocks.to_csv(index=False, lineterminator="\n"),
        encoding="utf-8",
    )
    (ROOT / config.OUTPUT_RESULTS).write_text(
        json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (ROOT / config.OUTPUT_REPORT).write_text(report + "\n", encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "timestamp": timestamp,
        "variant_id": config.VARIANT_ID,
        "stage": config.STAGE,
        "git_hash": git_hash,
        "git_dirty": git_dirty,
        "config_hash": config_hash,
        "config": config.as_dict(),
        "source": config.SOURCE,
        "period1": config.PERIOD1,
        "period2": config.PERIOD2,
        "cutoff_date_exclusive": config.CUTOFF_DATE,
        "data_hash": data_hash,
        "data_sha256": config.DATA_SHA256,
    }
    (ROOT / config.OUTPUT_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    p_value = results["placebo"]["p_value"]
    notes = (
        f"T={results['metrics']['pooled_t']}; "
        f"ON_blocks={results['metrics']['on_block_count']}; "
        "details=results_v1.json"
    )
    append_ledger_row(
        {
            "run_id": run_id,
            "timestamp": timestamp,
            "variant_id": config.VARIANT_ID,
            "config_hash": config_hash,
            "data_hash": data_hash,
            "decision": results["metrics"]["decision"],
            "S_base": "",
            "p_placebo": "" if p_value is None else repr(float(p_value)),
            "notes": notes,
            "stage": config.STAGE,
        }
    )
