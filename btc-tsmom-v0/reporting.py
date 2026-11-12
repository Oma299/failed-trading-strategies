from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import config
from data import aggregate_daily_close, load_research_data


ROOT = Path(__file__).resolve().parent
OUTPUT_BLOCKS = ROOT / "blocks.csv"
OUTPUT_RESULTS = ROOT / "results.json"
OUTPUT_REPORT = ROOT / "report.md"
OUTPUT_MANIFEST = ROOT / "run_manifest.json"
OUTPUT_LEDGER = ROOT / "ledger.csv"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_state() -> tuple[str, bool]:
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


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _format(value: Any, decimals: int = 8) -> str:
    if value is None:
        return "null"
    return f"{float(value):.{decimals}f}"


def make_report(
    diagnostics: dict[str, Any],
    signals: pd.DataFrame,
    episodes: int,
    excluded: dict[str, Any],
    base: dict[str, Any],
    stress: dict[str, Any],
    robustness: dict[str, Any],
    placebo: dict[str, Any],
    bootstrap: dict[str, Any],
    final_decision: str,
) -> str:
    lines = [
        "# Stage 1 — диагностика входа",
        "",
        "Это диагностика входа без стопа, а не результат стратегии.",
        "",
        "## Данные",
        "",
        f"- Строк: {diagnostics['rows']}",
        f"- Минимальный open_time: {diagnostics['min_open_time']}",
        f"- Максимальный open_time: {diagnostics['max_open_time']}",
        f"- Дубликаты open_time: {diagnostics['duplicate_open_times']}",
        f"- Строгое возрастание: {diagnostics['strictly_increasing']}",
        f"- Пропущенные минуты: {diagnostics['missing_minutes']}",
        f"- Проверка cutoff: {diagnostics['cutoff_assertion']}",
        f"- Дневных строк сигнала: {len(signals)}",
        f"- ON-эпизодов на дневном календарном ряду: {episodes}",
        "",
        "## Исключённые блоки",
        "",
        f"- С неопределённым сигналом по фазам: {json.dumps(excluded['signal_undefined_by_phase'], sort_keys=True)}",
        "",
        "| Сценарий | Фаза | Нет свечи входа | Нет свечи выхода | Нет хотя бы одной свечи | Cutoff |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario, details in excluded["by_scenario"].items():
        for phase in config.PHASES:
            key = str(phase)
            lines.append(
                f"| {scenario} | {phase} | "
                f"{details['missing_entry_by_phase'][key]} | "
                f"{details['missing_exit_by_phase'][key]} | "
                f"{details['missing_any_candle_by_phase'][key]} | "
                f"{details['cutoff_by_phase'][key]} |"
            )

    for scenario, stats in (("BASE", base), ("STRESS", stress)):
        lines.extend(
            [
                "",
                f"## {scenario}",
                "",
                f"- S: {_format(stats['S'])}",
                f"- mean_ON (среднее фазовых средних): {_format(stats['mean_ON'])}",
                f"- Доля фаз с S>0: {_format(stats['positive_phase_fraction'])} "
                f"({stats['positive_phase_count']} из {len(list(config.PHASES))})",
                f"- Медиана ON-блоков на фазу: {_format(stats['median_ON_blocks_per_phase'], 2)}",
                "",
                "| Фаза | ON-блоки | OFF-блоки | mean_ON | mean_OFF | S_phase |",
                "|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in stats["phases"]:
            lines.append(
                f"| {row['phase']} | {row['blocks_on']} | {row['blocks_off']} | "
                f"{_format(row['mean_on'])} | {_format(row['mean_off'])} | "
                f"{_format(row['S_phase'])} |"
            )

    lines.extend(["", "## Покрытие по годам", ""])
    lines.extend(
        [
            "| Сценарий | Год | Фаза | Кандидаты | Валидные блоки | Неопределённый сигнал | Нет входа | Нет выхода | Cutoff | Доля покрытия |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in excluded["coverage_by_year"]:
        lines.append(
            f"| {row['scenario']} | {row['year']} | {row['phase']} | "
            f"{row['candidate_blocks']} | {row['valid_blocks']} | "
            f"{row['signal_undefined']} | {row['missing_entry']} | "
            f"{row['missing_exit']} | {row['cutoff']} | {_format(row['coverage'], 4)} |"
        )

    lines.extend(
        [
            "",
            "## Устойчивость BASE",
            "",
            f"- S без каждого года: `{json.dumps(robustness['leave_one_year_out'], sort_keys=True)}`",
            f"- S после удаления лучших 5% ON-блоков: {_format(robustness['S_after_best_5pct_removed'])}",
            f"- Удалено лучших ON-блоков: {robustness['best_5pct_removed_count']}",
            "",
            "## Плацебо BASE",
            "",
            f"- Сдвигов: {placebo['draws']}",
            f"- S_placebo >= S_obs: {placebo['S_placebo_ge_observed']}",
            f"- Неопределённых S_placebo: {placebo['undefined_draws']}",
            f"- p: {_format(placebo['p_value'])}",
            "",
            "## Bootstrap BASE",
            "",
            f"- Запрошено выборок: {bootstrap['draws_requested']}",
            f"- Выборок с определённым S: {bootstrap['draws_with_valid_S']}",
            f"- Выборок с исключёнными фазами: {bootstrap['draws_with_excluded_phases']}",
            f"- Исключений фаз (фаза × выборка): {bootstrap['excluded_phase_occurrences']}",
            f"- Выборок без валидных фаз: {bootstrap['draws_with_no_valid_phases']}",
            f"- S, 10-й перцентиль: {_format(bootstrap['percentiles']['10'])}",
            f"- S, 50-й перцентиль: {_format(bootstrap['percentiles']['50'])}",
            f"- S, 90-й перцентиль: {_format(bootstrap['percentiles']['90'])}",
            "",
            "## Решение",
            "",
            final_decision,
            "",
        ]
    )
    return "\n".join(lines)


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
    ledger_notes: str | None = None,
) -> None:
    blocks.to_csv(OUTPUT_BLOCKS, index=False, float_format="%.12g")
    OUTPUT_RESULTS.write_text(
        json.dumps(results, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    OUTPUT_REPORT.write_text(report, encoding="utf-8")
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
    }
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

    ledger_fields = [
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
    existed = OUTPUT_LEDGER.exists()
    with OUTPUT_LEDGER.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=ledger_fields)
        if not existed:
            writer.writeheader()
        elif file.tell() == 0:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "variant_id": config.VARIANT_ID,
                "config_hash": config_hash,
                "data_hash": data_hash,
                "decision": results["decision"],
                "S_base": results["BASE"]["S"],
                "p_placebo": results["placebo"]["p_value"],
                "notes": (
                    ledger_notes
                    if ledger_notes is not None
                    else json.dumps(results["excluded_blocks"], sort_keys=True)
                ),
            }
        )
