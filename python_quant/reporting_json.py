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
        "artifacts": _build_artifact_file_metadata(artifacts),
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
    target_path = output_dir / "effective_config.json"
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


def save_batch_summary(rows: list[dict[str, object]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "batch_summary.csv"
    json_path = output_dir / "batch_summary.json"

    if not rows:
        csv_path.write_text("无有效参数扫描结果\n", encoding=_HUMAN_READABLE_ENCODING)
        json_path.write_text("{}", encoding="utf-8")
        return csv_path, json_path

    headers = _build_batch_export_headers(rows)
    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([display_label(header) for header in headers])
        for index, row in enumerate(rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, index))

    payload = _build_batch_json_summary(rows)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return csv_path, json_path


def save_batch_rankings(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    rank_by: str,
    recommended_parameters: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"batch_leaderboard_{rank_by}.csv"
    json_path = output_dir / f"batch_leaderboard_{rank_by}.json"
    best_run_path = output_dir / "best_run_summary.json"

    if not rows:
        csv_path.write_text("无有效参数扫描结果\n", encoding=_HUMAN_READABLE_ENCODING)
        json_path.write_text("{}", encoding="utf-8")
        best_run_path.write_text("{}", encoding="utf-8")
        return csv_path, json_path, best_run_path

    from .reporting_rank import sort_rows_by_metric, validate_rank_metric
    validate_rank_metric(rows, rank_by)
    sorted_rows = sort_rows_by_metric(rows, rank_by)

    if recommended_parameters:
        _attach_batch_leaderboard_diagnostics(sorted_rows, recommended_parameters)

    headers = _build_batch_export_headers(sorted_rows)
    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([display_label(header) for header in headers])
        for index, row in enumerate(sorted_rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, index))

    json_payload = _build_ranked_batch_json_summary(sorted_rows, rank_by)
    json_path.write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    best_payload = _build_best_run_json_summary(sorted_rows[0], rank_by)
    best_run_path.write_text(
        json.dumps(best_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return csv_path, json_path, best_run_path


def _build_batch_export_headers(rows: list[dict[str, object]]) -> list[str]:
    headers: list[str] = ["scheme_label", "run_id"]
    param_keys = sorted({key for row in rows for key in row if key.startswith("param_")})
    headers.extend(param_keys)
    metric_keys = [
        "gate_status",
        "health_score",
        "gate_failures",
        "failed_gate_categories",
        "failed_gate_names",
        "total_return",
        "annualized_return",
        "max_drawdown",
        "sharpe",
        "sortino",
        "calmar",
        "win_rate",
        "total_cost",
    ]
    for key in metric_keys:
        if any(key in row for row in rows):
            headers.append(key)
    diagnostic_keys = [
        "matches_recommended_parameters",
        "health_warnings",
        "critical_warnings",
        "equity_curve_csv",
        "run_manifest_json",
        "output_dir",
    ]
    for key in diagnostic_keys:
        if any(key in row for row in rows):
            headers.append(key)
    return headers


def _attach_batch_leaderboard_diagnostics(
    rows: list[dict[str, object]],
    recommended_parameters: dict[str, object],
) -> None:
    for row in rows:
        row["matches_recommended_parameters"] = _recommended_parameter_match(row, recommended_parameters)


def _split_delimited_text(value: object) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _failed_gate_summary(row: dict[str, object]) -> dict[str, object] | None:
    gate_status = str(row.get("gate_status", "")).lower()
    if gate_status == "pass":
        return None
    categories = _split_delimited_text(row.get("failed_gate_categories"))
    names = _split_delimited_text(row.get("failed_gate_names"))
    return {
        "status": row.get("gate_status"),
        "failures": row.get("gate_failures"),
        "categories": categories,
        "names": names,
    }


def _recommended_parameter_match(
    row: dict[str, object],
    recommended_parameters: dict[str, object],
) -> bool:
    if not recommended_parameters:
        return False
    for key, recommended_value in recommended_parameters.items():
        row_value = row.get(f"param_{key}")
        if row_value is None:
            return False
        if str(row_value) != str(recommended_value):
            return False
    return True


def _build_batch_json_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    from .reporting_html import _format_run_label
    return {
        "run_count": len(rows),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runs": [
            {
                "scheme_label": _format_run_label(row, index),
                "run_id": row.get("run_id"),
                "total_return": float_metric(row, "total_return"),
                "annualized_return": float_metric(row, "annualized_return"),
                "max_drawdown": float_metric(row, "max_drawdown"),
                "sharpe": float_metric(row, "sharpe"),
                "gate_status": row.get("gate_status"),
                "health_score": float_metric(row, "health_score"),
                "gate_failures": row.get("gate_failures"),
            }
            for index, row in enumerate(rows, start=1)
        ],
    }


def _build_ranked_batch_json_summary(
    sorted_rows: list[dict[str, object]],
    rank_by: str,
) -> dict[str, object]:
    from .reporting_html import _format_run_label
    payload = _build_batch_json_summary(sorted_rows)
    payload["rank_by"] = rank_by
    payload["runs"] = [
        {
            "rank": index,
            "scheme_label": _format_run_label(row, index),
            "run_id": row.get("run_id"),
            "rank_metric_value": float_metric(row, rank_by),
            "gate_status": row.get("gate_status"),
            "health_score": float_metric(row, "health_score"),
            "gate_failures": row.get("gate_failures"),
            "matches_recommended_parameters": row.get("matches_recommended_parameters"),
            "failed_gates": _failed_gate_summary(row),
        }
        for index, row in enumerate(sorted_rows, start=1)
    ]
    return payload


def _build_best_run_json_summary(
    best_row: dict[str, object],
    rank_by: str,
) -> dict[str, object]:
    from .reporting_html import _format_run_label
    return {
        "scheme_label": _format_run_label(best_row, 1),
        "run_id": best_row.get("run_id"),
        "rank_by": rank_by,
        "rank_metric_value": float_metric(best_row, rank_by),
        "total_return": float_metric(best_row, "total_return"),
        "annualized_return": float_metric(best_row, "annualized_return"),
        "max_drawdown": float_metric(best_row, "max_drawdown"),
        "sharpe": float_metric(best_row, "sharpe"),
        "gate_status": best_row.get("gate_status"),
        "health_score": float_metric(best_row, "health_score"),
        "gate_failures": best_row.get("gate_failures"),
        "failed_gates": _failed_gate_summary(best_row),
        "matches_recommended_parameters": best_row.get("matches_recommended_parameters"),
        "parameters": {
            key.removeprefix("param_"): value
            for key, value in best_row.items()
            if key.startswith("param_")
        },
    }


def _build_batch_export_row(
    row: dict[str, object],
    headers: list[str],
    row_index: int,
) -> list[object]:
    from .reporting_html import _build_batch_display_value
    return [_build_batch_display_value(row, header, row_index) for header in headers]


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
