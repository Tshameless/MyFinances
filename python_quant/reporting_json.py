from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .config import BacktestConfig
from .models import BacktestMetrics
from .reporting_labels import display_label
from .reporting_rank import float_metric

_HUMAN_READABLE_ENCODING = "utf-8-sig"


def save_performance_summary_json(
    metrics: BacktestMetrics,
    output_dir: Path,
    *,
    extra_payload: dict[str, object] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.json"
    
    # We use dynamic module loading here to avoid circular dependencies with reporting_html
    from .reporting_html import _build_performance_summary_items

    summary_items = _build_performance_summary_items(metrics)
    summary_dict = {
        name: {
            "chinese_label": chinese_label,
            "explanation": explanation,
            "value": str(value),
        }
        for name, chinese_label, explanation, value in summary_items
    }
    payload: dict[str, object] = {
        "summary": summary_dict,
        "metrics": asdict(metrics),
    }
    if extra_payload is not None:
        payload.update(extra_payload)

    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_path


def save_run_manifest(
    *,
    output_dir: Path,
    config: BacktestConfig,
    inputs: dict[str, str | bool | None],
    artifacts: dict[str, Path],
    metrics: BacktestMetrics | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "run_manifest.json"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "environment": _build_environment_metadata(),
        "git": _build_git_metadata(),
        "inputs": inputs,
        "input_files": _build_input_file_metadata(inputs),
        "config": _serialize_config(config),
        "artifacts": {name: str(path) for name, path in artifacts.items()},
        "artifact_files": _build_artifact_file_metadata(artifacts),
    }
    if metrics is not None:
        payload["metrics"] = asdict(metrics)
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_path


def save_effective_config(config: BacktestConfig, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "config_effective.json"
    target_path.write_text(
        json.dumps(_serialize_config(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_path


def save_config_sources(
    config_sources: dict[str, object],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "config_sources.json"
    target_path.write_text(
        json.dumps(config_sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target_path


def save_batch_summary(
    rows: list[dict[str, object]],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "batch_summary.csv"
    json_path = output_dir / "batch_summary.json"

    if not rows:
        headers = ["scheme_label", "run_id"]
    else:
        headers = _build_batch_export_headers(list(rows[0].keys()))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([display_label(header) for header in headers])
        for row_index, row in enumerate(rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, row_index))

    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reader_friendly": _build_batch_json_summary(rows),
        "rows": rows,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, ensure_ascii=False, indent=2)

    return csv_path, json_path


def save_batch_rankings(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    rank_by: str = "annualized_return",
    recommended_parameters: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    from .reporting_rank import sort_rows_by_metric, validate_rank_metric
    validate_rank_metric(rows, rank_by)
    ranked_rows = sort_rows_by_metric(rows, rank_by)
    for index, row in enumerate(ranked_rows, start=1):
        row["rank"] = index
        _attach_batch_leaderboard_diagnostics(row, recommended_parameters or {})

    csv_path = output_dir / "batch_leaderboard.csv"
    json_path = output_dir / "batch_leaderboard.json"
    best_run_path = output_dir / "best_run.json"

    headers = _build_batch_export_headers(list(ranked_rows[0].keys())) if ranked_rows else ["rank", "scheme_label", "run_id"]
    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([display_label(header) for header in headers])
        for row_index, row in enumerate(ranked_rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, row_index))

    leaderboard_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rank_by": rank_by,
        "ranking_policy": "gate_pass_first_then_metric",
        "reader_friendly": _build_ranked_batch_json_summary(ranked_rows, rank_by),
        "rows": ranked_rows,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(leaderboard_payload, handle, ensure_ascii=False, indent=2)

    best_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rank_by": rank_by,
        "ranking_policy": "gate_pass_first_then_metric",
        "reader_friendly": _build_best_run_json_summary(ranked_rows[0] if ranked_rows else None, rank_by),
        "best_run": ranked_rows[0] if ranked_rows else None,
    }
    with best_run_path.open("w", encoding="utf-8") as handle:
        json.dump(best_payload, handle, ensure_ascii=False, indent=2)

    return csv_path, json_path, best_run_path


def _build_batch_export_headers(headers: list[str]) -> list[str]:
    ordered_headers = [header for header in headers if header != "run_id"]
    insert_at = ordered_headers.index("rank") + 1 if "rank" in ordered_headers else 0
    ordered_headers[insert_at:insert_at] = ["scheme_label", "run_id"]
    return ordered_headers


def _attach_batch_leaderboard_diagnostics(
    row: dict[str, object],
    recommended_parameters: dict[str, object],
) -> None:
    failed_categories = _split_delimited_text(row.get("failed_gate_categories"))
    failed_names = _split_delimited_text(row.get("failed_gate_names"))
    row["failed_gate_count"] = max(len(failed_names), float_metric(row, "gate_failures", default=0.0))
    row["primary_failed_gate_category"] = failed_categories[0] if failed_categories else ""
    row["primary_failed_gate_name"] = failed_names[0] if failed_names else ""
    row["failed_gate_summary"] = _failed_gate_summary(failed_categories, failed_names)
    matches, mismatches = _recommended_parameter_match(row, recommended_parameters)
    row["matches_recommended_parameters"] = matches
    row["recommended_parameter_mismatch"] = "; ".join(mismatches)


def _split_delimited_text(value: object) -> list[str]:
    if value in (None, ""):
        return []
    return [
        item.strip()
        for item in str(value).split(";")
        if item.strip()
    ]


def _failed_gate_summary(categories: list[str], names: list[str]) -> str:
    if not categories and not names:
        return ""
    category_text = ",".join(categories) if categories else "-"
    name_text = ",".join(names) if names else "-"
    return f"{category_text} | {name_text}"


def _recommended_parameter_match(
    row: dict[str, object],
    recommended_parameters: dict[str, object],
) -> tuple[bool, list[str]]:
    if not recommended_parameters:
        return False, []
    mismatches = []
    matched_any = False
    for parameter, recommended_value in sorted(recommended_parameters.items()):
        row_value = row.get(parameter)
        if row_value is None:
            mismatches.append(f"{parameter}=<missing> expected {recommended_value}")
            continue
        if str(row_value) == str(recommended_value):
            matched_any = True
            continue
        mismatches.append(f"{parameter}={row_value} expected {recommended_value}")
    return matched_any and not mismatches, mismatches


def _build_batch_json_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    from .reporting_html import _format_run_label
    return {
        "trial_count": len(rows),
        "trial_labels": [
            _format_run_label(row, row_index)
            for row_index, row in enumerate(rows, start=1)
        ],
        "notes": "rows 字段保留完整机器可读结果；reader_friendly 字段用于直接阅读。",
    }


def _build_ranked_batch_json_summary(
    ranked_rows: list[dict[str, object]],
    rank_by: str,
) -> dict[str, object]:
    from .reporting_html import _format_run_label
    best_row = ranked_rows[0] if ranked_rows else None
    worst_row = ranked_rows[-1] if ranked_rows else None
    return {
        "rank_metric": display_label(rank_by),
        "best_scheme": None if best_row is None else _format_run_label(best_row, 1),
        "best_internal_id": None if best_row is None else str(best_row.get("run_id", "")),
        "best_gate_status": None if best_row is None else str(best_row.get("gate_status", "")),
        "best_health_score": None if best_row is None else _format_metric_value_helper(
            "health_score", best_row.get("health_score")
        ),
        "best_metric_value": None if best_row is None else _format_metric_value_helper(
            rank_by, best_row.get(rank_by)
        ),
        "worst_scheme": None if worst_row is None else _format_run_label(worst_row, len(ranked_rows)),
        "worst_internal_id": None if worst_row is None else str(worst_row.get("run_id", "")),
        "worst_gate_status": None if worst_row is None else str(worst_row.get("gate_status", "")),
        "worst_metric_value": None if worst_row is None else _format_metric_value_helper(
            rank_by, worst_row.get(rank_by)
        ),
        "notes": "rows 字段按排序后的完整结果保留。",
    }


def _build_best_run_json_summary(
    best_row: dict[str, object] | None,
    rank_by: str,
) -> dict[str, object]:
    from .reporting_html import _format_run_label
    if best_row is None:
        return {
            "best_scheme": None,
            "best_internal_id": None,
            "best_gate_status": None,
            "best_health_score": None,
            "rank_metric": display_label(rank_by),
            "best_metric_value": None,
        }
    return {
        "best_scheme": _format_run_label(best_row, 1),
        "best_internal_id": str(best_row.get("run_id", "")),
        "best_gate_status": str(best_row.get("gate_status", "")),
        "best_health_score": _format_metric_value_helper("health_score", best_row.get("health_score")),
        "rank_metric": display_label(rank_by),
        "best_metric_value": _format_metric_value_helper(rank_by, best_row.get(rank_by)),
    }


def _build_batch_export_row(
    row: dict[str, object],
    headers: list[str],
    row_index: int,
) -> list[object]:
    return [_build_batch_display_value(row, header, row_index) for header in headers]


def _build_batch_display_value(row: dict[str, object], header: str, row_index: int) -> object:
    from .reporting_html import _format_run_label
    if header == "scheme_label":
        return _format_run_label(row, row_index)
    return row.get(header, "")


def _format_metric_value_helper(metric: str, value: object) -> str:
    from .reporting_html import _format_metric_value
    return _format_metric_value(metric, value)


def _serialize_config(config: BacktestConfig) -> dict[str, object]:
    return {
        "initial_cash": config.initial_cash,
        "top_n": config.top_n,
        "selection_mode": config.selection_mode,
        "score_source": config.score_source,
        "lot_size": config.lot_size,
        "max_group_positions": config.max_group_positions,
        "lookback_momentum": config.lookback_momentum,
        "lookback_mean_reversion": config.lookback_mean_reversion,
        "lookback_volatility": config.lookback_volatility,
        "rolling_risk_window": config.rolling_risk_window,
        "execution_delay_days": config.execution_delay_days,
        "max_allowed_drawdown": config.max_allowed_drawdown,
        "max_allowed_daily_var": config.max_allowed_daily_var,
        "min_allowed_rolling_return": config.min_allowed_rolling_return,
        "min_allowed_information_ratio": config.min_allowed_information_ratio,
        "min_allowed_fill_rate": config.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": config.min_allowed_execution_price_coverage,
        "min_allowed_factor_score_coverage": config.min_allowed_factor_score_coverage,
        "max_allowed_position_weight": config.max_allowed_position_weight,
        "max_allowed_group_weight": config.max_allowed_group_weight,
        "max_allowed_attribution_residual": config.max_allowed_attribution_residual,
        "rebalance_every_n_days": config.rebalance_every_n_days,
        "commission_rate": config.commission_rate,
        "buy_commission_rate": config.buy_commission_rate,
        "sell_commission_rate": config.sell_commission_rate,
        "slippage_rate": config.slippage_rate,
        "market_impact_coefficient": config.market_impact_coefficient,
        "market_impact_exponent": config.market_impact_exponent,
        "stamp_duty_rate": config.stamp_duty_rate,
        "min_commission": config.min_commission,
        "transfer_fee_rate": config.transfer_fee_rate,
        "target_cash_weight": config.target_cash_weight,
        "max_position_weight": config.max_position_weight,
        "infer_limit_flags": config.infer_limit_flags,
        "forward_fill_suspended_bars": config.forward_fill_suspended_bars,
        "limit_up_down_rate": config.limit_up_down_rate,
        "st_limit_up_down_rate": config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": config.infer_limit_rate_by_symbol,
        "max_volume_participation": config.max_volume_participation,
        "price_field": config.price_field,
        "execution_price_field": config.execution_price_field,
        "execution_price_field_effective": config.execution_price_field_effective,
        "start_date": None if config.start_date is None else config.start_date.isoformat(),
        "end_date": None if config.end_date is None else config.end_date.isoformat(),
        "output_dir": str(config.output_dir),
        "symbol_name_csv": None if config.symbol_name_csv is None else str(config.symbol_name_csv),
        "stock_pool_csv": None if config.stock_pool_csv is None else str(config.stock_pool_csv),
        "symbol_group_csv": None if config.symbol_group_csv is None else str(config.symbol_group_csv),
        "factor_score_csv": None if config.factor_score_csv is None else str(config.factor_score_csv),
        "custom_factors_py": None if config.custom_factors_py is None else str(config.custom_factors_py),
        "factor_weights": config.factor_weights,
    }


def _build_input_file_metadata(
    inputs: dict[str, str | bool | None],
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for key in ("csv", "benchmark_csv", "stock_pool_csv", "symbol_group_csv", "factor_score_csv", "config"):
        raw_path = inputs.get(key)
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        metadata[key] = _file_metadata(path)
    return metadata


def _build_artifact_file_metadata(
    artifacts: dict[str, Path],
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for name, path in artifacts.items():
        if path.exists() and path.is_file():
            metadata[name] = _file_metadata(path)
    return metadata


def _build_environment_metadata() -> dict[str, str]:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def _build_git_metadata() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        commit = _run_git_command(repo_root, "rev-parse", "HEAD")
        branch = _run_git_command(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        status_short = _run_git_command(repo_root, "status", "--short")
    except (OSError, subprocess.SubprocessError):
        return {"available": False}

    return {
        "available": True,
        "commit": commit,
        "branch": branch,
        "is_dirty": bool(status_short),
        "status_short": status_short.splitlines(),
    }


def _run_git_command(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _file_metadata(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
