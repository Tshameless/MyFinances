from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from datetime import date
from itertools import product
from pathlib import Path
from typing import Protocol, TypedDict, cast

from .analysis import (
    build_batch_stability_analysis,
    build_walk_forward_optimization_summary,
    build_walk_forward_summary,
    build_walk_forward_train_test_windows,
    build_walk_forward_windows,
)
from .backtest import run_backtest
from .config import BacktestConfig, load_sweep_overrides_from_toml
from .console_output import print_walk_forward_optimization_artifacts
from .data_loader import load_factor_scores_from_csv, load_stock_pool_from_csv
from .models import BacktestResult, PriceBar
from .reporting import (
    load_symbol_group_mapping,
    save_batch_chart_svg,
    save_batch_heatmap_svg,
    save_batch_rankings,
    save_batch_report_html,
    save_batch_summary,
    save_walk_forward_report_html,
)
from .reporting_csv import (
    save_batch_stability_files,
    save_walk_forward_files,
    save_walk_forward_optimization_files,
)
from .run_outputs import persist_run_outputs


class ConfigSourcesBuilder(Protocol):
    def __call__(
        self,
        args: argparse.Namespace,
        *,
        sweep_overrides: dict[str, object] | None = None,
    ) -> dict[str, object]: ...


class _TrainCandidateResult(TypedDict):
    result: BacktestResult
    artifacts: dict[str, Path]
    health_summary: dict[str, object]
    overrides: dict[str, object]


_WORKER_CTX: dict[str, object] = {}

def _init_worker(ctx: dict[str, object]) -> None:
    global _WORKER_CTX
    _WORKER_CTX = ctx

def _sweep_worker_wrapper(item: tuple[int, dict[str, object]]) -> dict[str, object]:
    global _WORKER_CTX
    return _run_sweep_case(
        args=cast("argparse.Namespace", _WORKER_CTX["args"]),
        bars=cast(list[PriceBar], _WORKER_CTX["bars"]),
        benchmark_bars=cast(list[PriceBar] | None, _WORKER_CTX["benchmark_bars"]),
        base_config=cast(BacktestConfig, _WORKER_CTX["base_config"]),
        batch_output_dir=cast(Path, _WORKER_CTX["batch_output_dir"]),
        run_number=item[0],
        override_values=item[1],
        build_config_sources=cast(ConfigSourcesBuilder, _WORKER_CTX["build_config_sources"]),
    )

def _wf_train_worker_wrapper(item: tuple[int, dict[str, object]]) -> _TrainCandidateResult:
    global _WORKER_CTX
    optimize_output_dir = cast(Path, _WORKER_CTX["optimize_output_dir"])
    window_id = cast(str, _WORKER_CTX["window_id"])
    return _run_walk_forward_train_candidate(
        args=cast("argparse.Namespace", _WORKER_CTX["args"]),
        train_bars=cast(list[PriceBar], _WORKER_CTX["train_bars"]),
        train_benchmark_bars=cast(list[PriceBar] | None, _WORKER_CTX["train_benchmark_bars"]),
        base_config=cast(BacktestConfig, _WORKER_CTX["base_config"]),
        train_output_dir=(optimize_output_dir / window_id / "train_candidates" / f"candidate_{item[0]:03d}"),
        train_start=cast("date", _WORKER_CTX["train_start"]),
        train_end=cast("date", _WORKER_CTX["train_end"]),
        override_values=item[1],
        build_config_sources=cast(ConfigSourcesBuilder, _WORKER_CTX["build_config_sources"]),
    )


def run_sweep(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig,
    build_config_sources: ConfigSourcesBuilder,
) -> None:
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("配置文件中未找到 [sweep] 配置段。")

    batch_output_dir = base_config.output_dir / "batch_runs"
    combinations = expand_sweep_combinations(sweep_overrides)

    from concurrent.futures import ProcessPoolExecutor

    items = [
        (run_number, override_values)
        for run_number, override_values in enumerate(combinations, start=1)
    ]
    if args.jobs <= 1 or len(items) <= 1:
        rows = [
            _run_sweep_case(
                args=args,
                bars=bars,
                benchmark_bars=benchmark_bars,
                base_config=base_config,
                batch_output_dir=batch_output_dir,
                run_number=item[0],
                override_values=item[1],
                build_config_sources=build_config_sources,
            )
            for item in items
        ]
    else:
        ctx = {
            "args": args,
            "bars": bars,
            "benchmark_bars": benchmark_bars,
            "base_config": base_config,
            "batch_output_dir": batch_output_dir,
            "build_config_sources": build_config_sources,
        }
        with ProcessPoolExecutor(max_workers=args.jobs, initializer=_init_worker, initargs=(ctx,)) as executor:
            rows = list(executor.map(_sweep_worker_wrapper, items))

    summary_csv_path, summary_json_path = save_batch_summary(rows, batch_output_dir)
    stability_analysis = build_batch_stability_analysis(rows, rank_by=args.rank_by)
    stability_paths = save_batch_stability_files(stability_analysis, batch_output_dir)
    stability_summary = stability_analysis.get("summary")
    recommended_parameters = (
        stability_summary.get("best_parameter_values", {})
        if isinstance(stability_summary, dict)
        else {}
    )
    leaderboard_csv_path, leaderboard_json_path, best_run_path = save_batch_rankings(
        rows,
        batch_output_dir,
        rank_by=args.rank_by,
        recommended_parameters=(
            recommended_parameters if isinstance(recommended_parameters, dict) else {}
        ),
    )
    batch_chart_path = save_batch_chart_svg(
        rows,
        batch_output_dir,
        metric=args.rank_by,
    )
    heatmap_path = None
    if len(sweep_overrides) == 2:
        heatmap_path = save_batch_heatmap_svg(
            rows,
            batch_output_dir,
            x_field=f"param_{list(sweep_overrides.keys())[0]}",
            y_field=f"param_{list(sweep_overrides.keys())[1]}",
            metric=args.rank_by,
        )
    batch_artifacts = {
        "batch_summary_csv": summary_csv_path,
        "batch_summary_json": summary_json_path,
        "batch_leaderboard_csv": leaderboard_csv_path,
        "batch_leaderboard_json": leaderboard_json_path,
        "best_run_json": best_run_path,
        "batch_chart_svg": batch_chart_path,
        "batch_stability_csv": stability_paths["batch_stability_csv"],
        "batch_stability_json": stability_paths["batch_stability_json"],
        "parameter_sensitivity_csv": stability_paths["parameter_sensitivity_csv"],
    }
    if heatmap_path is not None:
        batch_artifacts["batch_heatmap_svg"] = heatmap_path
    batch_report_path = save_batch_report_html(
        output_dir=batch_output_dir,
        rows=rows,
        rank_by=args.rank_by,
        artifacts=batch_artifacts,
    )
    print(f"批量参数扫描完成，共运行 {len(rows)} 组方案。")
    print(f"批量汇总 CSV 已保存：{summary_csv_path}")
    print(f"批量汇总 JSON 已保存：{summary_json_path}")
    print(f"排行榜 CSV 已保存：{leaderboard_csv_path}")
    print(f"排行榜 JSON 已保存：{leaderboard_json_path}")
    print(f"最佳方案摘要已保存：{best_run_path}")
    print(f"参数稳定性 CSV 已保存：{stability_paths['batch_stability_csv']}")
    print(f"参数稳定性 JSON 已保存：{stability_paths['batch_stability_json']}")
    print(f"参数敏感度 CSV 已保存：{stability_paths['parameter_sensitivity_csv']}")
    print(f"批量对比图已保存：{batch_chart_path}")
    if heatmap_path is not None:
        print(f"热力图已保存：{heatmap_path}")
    print(f"批量 HTML 报告已保存：{batch_report_path}")


def run_walk_forward(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig,
    build_config_sources: ConfigSourcesBuilder,
) -> None:
    dates = sorted({bar.date for bar in bars})
    windows = build_walk_forward_windows(
        dates,
        window_size=args.walk_window,
        step_size=args.walk_step,
    )
    if not windows:
        raise ValueError("walk-forward window settings produced no windows.")

    walk_output_dir = base_config.output_dir / "walk_forward"
    rows: list[dict[str, object]] = []
    for window_number, (start_date, end_date) in enumerate(windows, start=1):
        window_id = f"window_{window_number:03d}"
        run_output_dir = walk_output_dir / window_id
        config_kwargs = base_config.to_dict()
        config_kwargs["start_date"] = start_date
        config_kwargs["end_date"] = end_date
        config_kwargs["output_dir"] = run_output_dir
        run_config = BacktestConfig.from_dict(config_kwargs)
        window_bars = filter_bars_by_date_range(
            bars,
            start_date=start_date,
            end_date=end_date,
        )
        window_benchmark_bars = (
            None
            if benchmark_bars is None
            else filter_bars_by_date_range(
                benchmark_bars,
                start_date=start_date,
                end_date=end_date,
            )
        )
        result = run_backtest(
            window_bars,
            run_config,
            benchmark_bars=window_benchmark_bars,
            stock_pool_by_date=load_stock_pool(run_config),
            symbol_groups=load_symbol_groups(run_config),
            factor_scores_by_date=load_factor_scores(run_config),
        )
        artifact_paths = persist_run_outputs(
            output_dir=run_output_dir,
            result=result,
            config=run_config,
            inputs=build_input_metadata(args, run_config),
            print_console=False,
            config_sources=build_config_sources(args),
        )
        rows.append(
            {
                "window_id": window_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "periods": result.metrics.periods,
                "total_return": result.metrics.total_return,
                "annualized_return": result.metrics.annualized_return,
                "max_drawdown": result.metrics.max_drawdown,
                "sharpe": result.metrics.sharpe,
                "win_rate": result.metrics.win_rate,
                "total_cost": result.metrics.total_cost,
                "run_manifest_json": str(artifact_paths["run_manifest_json"]),
            }
        )

    analysis = build_walk_forward_summary(rows)
    paths = save_walk_forward_files(analysis, walk_output_dir)
    report_path = save_walk_forward_report_html(
        output_dir=walk_output_dir,
        analysis=analysis,
        artifacts={
            "walk_forward_csv": paths["walk_forward_csv"],
            "walk_forward_json": paths["walk_forward_json"],
        },
    )
    print(f"Walk-forward 验证完成，共运行 {len(rows)} 个窗口。")
    print(f"Walk-forward 汇总 CSV 已保存：{paths['walk_forward_csv']}")
    print(f"Walk-forward 汇总 JSON 已保存：{paths['walk_forward_json']}")
    print(f"Walk-forward HTML 报告已保存：{report_path}")


def run_walk_forward_optimization(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig,
    build_config_sources: ConfigSourcesBuilder,
) -> None:
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("配置文件中未找到 [sweep] 配置段。")
    combinations = expand_sweep_combinations(sweep_overrides)
    dates = sorted({bar.date for bar in bars})
    windows = build_walk_forward_train_test_windows(
        dates,
        train_size=args.walk_train_window,
        test_size=args.walk_test_window,
        step_size=args.walk_step,
    )
    if not windows:
        raise ValueError("walk-forward optimization window settings produced no windows.")

    optimize_output_dir = base_config.output_dir / "walk_forward_optimization"
    rows: list[dict[str, object]] = []
    for window in windows:
        window_id = str(window["window_id"])
        train_start = cast(date, window["train_start_date"])
        train_end = cast(date, window["train_end_date"])
        test_start = cast(date, window["test_start_date"])
        test_end = cast(date, window["test_end_date"])
        train_bars = filter_bars_by_date_range(
            bars,
            start_date=train_start,
            end_date=train_end,
        )
        test_bars = filter_bars_by_date_range(
            bars,
            start_date=test_start,
            end_date=test_end,
        )
        train_benchmark_bars = (
            None
            if benchmark_bars is None
            else filter_bars_by_date_range(
                benchmark_bars,
                start_date=train_start,
                end_date=train_end,
            )
        )
        test_benchmark_bars = (
            None
            if benchmark_bars is None
            else filter_bars_by_date_range(
                benchmark_bars,
                start_date=test_start,
                end_date=test_end,
            )
        )
        best_train_result: BacktestResult | None = None
        best_train_artifacts: dict[str, Path] | None = None
        best_train_health_summary: dict[str, object] = {}
        best_overrides: dict[str, object] | None = None
        best_metric = float("-inf")
        best_candidate_key: tuple[float, float, float, float, float, float] | None = None

        items = [
            (combo_number, override_values)
            for combo_number, override_values in enumerate(combinations, start=1)
        ]
        
        if args.jobs <= 1 or len(items) <= 1:
            candidate_results = [
                _run_walk_forward_train_candidate(
                    args=args,
                    train_bars=train_bars,
                    train_benchmark_bars=train_benchmark_bars,
                    base_config=base_config,
                    train_output_dir=(optimize_output_dir / window_id / "train_candidates" / f"candidate_{item[0]:03d}"),
                    train_start=train_start,
                    train_end=train_end,
                    override_values=item[1],
                    build_config_sources=build_config_sources,
                )
                for item in items
            ]
        else:
            from concurrent.futures import ProcessPoolExecutor
            ctx = {
                "args": args,
                "train_bars": train_bars,
                "train_benchmark_bars": train_benchmark_bars,
                "base_config": base_config,
                "optimize_output_dir": optimize_output_dir,
                "window_id": window_id,
                "train_start": train_start,
                "train_end": train_end,
                "build_config_sources": build_config_sources,
            }
            with ProcessPoolExecutor(max_workers=args.jobs, initializer=_init_worker, initargs=(ctx,)) as executor:
                candidate_results = list(executor.map(_wf_train_worker_wrapper, items))
        for candidate in candidate_results:
            train_result = candidate["result"]
            train_artifacts = candidate["artifacts"]
            health_summary = candidate["health_summary"]
            override_values = candidate["overrides"]
            metric_value = _metric_value_for_rank(train_result, args.rank_by)
            candidate_key = health_aware_rank_key(metric_value, health_summary)
            if best_candidate_key is None or candidate_key > best_candidate_key:
                best_metric = metric_value
                best_candidate_key = candidate_key
                best_train_result = train_result
                best_train_artifacts = train_artifacts
                best_train_health_summary = health_summary
                best_overrides = dict(override_values)

        if best_train_result is None or best_train_artifacts is None or best_overrides is None:
            raise ValueError(f"No train candidate completed for {window_id}.")

        test_output_dir = optimize_output_dir / window_id / "test"
        test_config_kwargs = base_config.to_dict()
        test_config_kwargs.update(best_overrides)
        test_config_kwargs["start_date"] = test_start
        test_config_kwargs["end_date"] = test_end
        test_config_kwargs["output_dir"] = test_output_dir
        test_config = BacktestConfig.from_dict(test_config_kwargs)
        test_result = run_backtest(
            test_bars,
            test_config,
            benchmark_bars=test_benchmark_bars,
            stock_pool_by_date=load_stock_pool(test_config),
            symbol_groups=load_symbol_groups(test_config),
            factor_scores_by_date=load_factor_scores(test_config),
        )
        test_artifacts = persist_run_outputs(
            output_dir=test_output_dir,
            result=test_result,
            config=test_config,
            inputs=build_input_metadata(args, test_config),
            print_console=False,
            config_sources=build_config_sources(args, sweep_overrides=best_overrides),
        )
        row: dict[str, object] = {
            "window_id": window_id,
            "train_start_date": train_start.isoformat(),
            "train_end_date": train_end.isoformat(),
            "test_start_date": test_start.isoformat(),
            "test_end_date": test_end.isoformat(),
            "selection_policy": "gate_pass_first_then_metric",
            "train_rank_metric": args.rank_by,
            "train_rank_metric_value": best_metric,
            "train_annualized_return": best_train_result.metrics.annualized_return,
            "train_sharpe": best_train_result.metrics.sharpe,
            "train_health_score": _summary_value(best_train_health_summary, "score"),
            "train_health_grade": _summary_value(best_train_health_summary, "grade"),
            "train_gate_status": _summary_value(best_train_health_summary, "gate_status"),
            "train_gate_failures": _summary_value(
                best_train_health_summary,
                "gate_failures",
            ),
            "train_health_warnings": _summary_value(
                best_train_health_summary,
                "warnings",
            ),
            "train_critical_warnings": _summary_value(
                best_train_health_summary,
                "critical_warnings",
            ),
            "test_total_return": test_result.metrics.total_return,
            "test_annualized_return": test_result.metrics.annualized_return,
            "test_max_drawdown": test_result.metrics.max_drawdown,
            "test_sharpe": test_result.metrics.sharpe,
            "test_win_rate": test_result.metrics.win_rate,
            "train_run_manifest_json": str(best_train_artifacts["run_manifest_json"]),
            "test_run_manifest_json": str(test_artifacts["run_manifest_json"]),
        }
        for key, value in best_overrides.items():
            row[f"param_{key}"] = value
        rows.append(row)

    analysis = build_walk_forward_optimization_summary(rows)
    paths = save_walk_forward_optimization_files(analysis, optimize_output_dir)
    report_path = save_walk_forward_report_html(
        output_dir=optimize_output_dir,
        analysis=analysis,
        optimization=True,
        artifacts={
            "walk_forward_optimization_csv": paths["walk_forward_optimization_csv"],
            "walk_forward_optimization_json": paths["walk_forward_optimization_json"],
        },
    )
    print_walk_forward_optimization_artifacts(
        row_count=len(rows),
        paths=paths,
        report_path=report_path,
    )


def _run_sweep_case(
    *,
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    base_config: BacktestConfig,
    batch_output_dir: Path,
    run_number: int,
    override_values: dict[str, object],
    build_config_sources: ConfigSourcesBuilder,
) -> dict[str, object]:
    run_id = f"run_{run_number:03d}"
    run_output_dir = batch_output_dir / run_id
    config_kwargs = base_config.to_dict()
    config_kwargs.update(override_values)
    config_kwargs["output_dir"] = run_output_dir
    run_config = BacktestConfig.from_dict(config_kwargs)
    result = run_backtest(
        bars,
        run_config,
        benchmark_bars=benchmark_bars,
        stock_pool_by_date=load_stock_pool(run_config),
        symbol_groups=load_symbol_groups(run_config),
        factor_scores_by_date=load_factor_scores(run_config),
    )
    artifact_paths = persist_run_outputs(
        output_dir=run_output_dir,
        result=result,
        config=run_config,
        inputs=build_input_metadata(args, run_config),
        print_console=False,
        config_sources=build_config_sources(args, sweep_overrides=override_values),
    )
    return build_batch_row(
        run_id=run_id,
        config=run_config,
        overrides=override_values,
        result=result,
        artifact_paths=artifact_paths,
    )




def _run_walk_forward_train_candidate(
    *,
    args: argparse.Namespace,
    train_bars: list[PriceBar],
    train_benchmark_bars: list[PriceBar] | None,
    base_config: BacktestConfig,
    train_output_dir: Path,
    train_start: date,
    train_end: date,
    override_values: dict[str, object],
    build_config_sources: ConfigSourcesBuilder,
) -> _TrainCandidateResult:
    config_kwargs = base_config.to_dict()
    config_kwargs.update(override_values)
    config_kwargs["start_date"] = train_start
    config_kwargs["end_date"] = train_end
    config_kwargs["output_dir"] = train_output_dir
    train_config = BacktestConfig.from_dict(config_kwargs)
    train_result = run_backtest(
        train_bars,
        train_config,
        benchmark_bars=train_benchmark_bars,
        stock_pool_by_date=load_stock_pool(train_config),
        symbol_groups=load_symbol_groups(train_config),
        factor_scores_by_date=load_factor_scores(train_config),
    )
    train_artifacts = persist_run_outputs(
        output_dir=train_output_dir,
        result=train_result,
        config=train_config,
        inputs=build_input_metadata(args, train_config),
        print_console=False,
        config_sources=build_config_sources(args, sweep_overrides=override_values),
    )
    return {
        "result": train_result,
        "artifacts": train_artifacts,
        "health_summary": _load_json_summary(train_artifacts.get("strategy_health_json")),
        "overrides": override_values,
    }


def load_stock_pool(config: BacktestConfig) -> dict[date, set[str]] | None:
    if config.stock_pool_csv is None:
        return None
    return load_stock_pool_from_csv(config.stock_pool_csv)


def load_symbol_groups(config: BacktestConfig) -> dict[str, str] | None:
    if config.symbol_group_csv is None:
        return None
    return load_symbol_group_mapping(config.symbol_group_csv)


def load_factor_scores(config: BacktestConfig) -> dict[date, dict[str, float]] | None:
    if config.factor_score_csv is None:
        return None
    return load_factor_scores_from_csv(config.factor_score_csv)


def filter_bars_by_date_range(
    bars: list[PriceBar],
    *,
    start_date: date | None,
    end_date: date | None,
) -> list[PriceBar]:
    if start_date is None and end_date is None:
        return bars
    filtered = [
        bar
        for bar in bars
        if (start_date is None or bar.date >= start_date)
        and (end_date is None or bar.date <= end_date)
    ]
    if not filtered:
        raise ValueError("No price data remains after applying date range filters.")
    return filtered


def expand_sweep_combinations(
    sweep_overrides: dict[str, list[object]],
) -> list[dict[str, object]]:
    field_names = list(sweep_overrides.keys())
    combinations = []
    for values in product(*(sweep_overrides[field_name] for field_name in field_names)):
        combinations.append(dict(zip(field_names, values, strict=True)))
    return combinations


def build_batch_row(
    *,
    run_id: str,
    config: BacktestConfig,
    overrides: dict[str, object],
    result: BacktestResult,
    artifact_paths: dict[str, Path],
) -> dict[str, object]:
    health_payload = _load_json_payload(artifact_paths.get("strategy_health_json"))
    health_summary = _summary_from_payload(health_payload)
    failed_gates = _failed_gates_from_payload(health_payload)
    row: dict[str, object] = {
        "run_id": run_id,
        "output_dir": str(config.output_dir),
        "total_return": result.metrics.total_return,
        "annualized_return": result.metrics.annualized_return,
        "max_drawdown": result.metrics.max_drawdown,
        "sharpe": result.metrics.sharpe,
        "sortino": result.metrics.sortino,
        "calmar": result.metrics.calmar,
        "win_rate": result.metrics.win_rate,
        "total_cost": result.metrics.total_cost,
        "health_score": _summary_value(health_summary, "score"),
        "health_grade": _summary_value(health_summary, "grade"),
        "gate_status": _summary_value(health_summary, "gate_status"),
        "gate_failures": _summary_value(health_summary, "gate_failures"),
        "health_warnings": _summary_value(health_summary, "warnings"),
        "critical_warnings": _summary_value(health_summary, "critical_warnings"),
        "failed_gate_categories": ";".join(_gate_field_values(failed_gates, "category")),
        "failed_gate_names": ";".join(_gate_field_values(failed_gates, "name")),
        "equity_curve_csv": str(artifact_paths["equity_curve_csv"]),
        "run_manifest_json": str(artifact_paths["run_manifest_json"]),
    }
    for key, value in overrides.items():
        row[f"param_{key}"] = value
    return row


def _load_json_summary(path: Path | None) -> dict[str, object]:
    return _summary_from_payload(_load_json_payload(path))


def _load_json_payload(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _summary_from_payload(payload: dict[str, object]) -> dict[str, object]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _failed_gates_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    gates = payload.get("gates")
    if not isinstance(gates, list):
        return []
    return [
        gate
        for gate in gates
        if isinstance(gate, dict) and gate.get("passed") is False
    ]


def _gate_field_values(gates: list[dict[str, object]], field: str) -> list[str]:
    return [
        str(gate[field])
        for gate in gates
        if field in gate and gate[field] not in (None, "")
    ]


def _summary_value(summary: dict[str, object], key: str) -> object:
    return summary.get(key, "")


def health_aware_rank_key(
    metric_value: float,
    health_summary: dict[str, object],
) -> tuple[float, float, float, float, float, float]:
    gate_status = str(health_summary.get("gate_status", "")).lower()
    if gate_status == "pass":
        gate_score = 1.0
    elif gate_status:
        gate_score = 0.0
    else:
        gate_score = 0.5
    health_score = _numeric_summary_value(health_summary, "score")
    gate_failures = _numeric_summary_value(health_summary, "gate_failures")
    critical_warnings = _numeric_summary_value(health_summary, "critical_warnings")
    warnings = _numeric_summary_value(health_summary, "warnings")
    return (
        gate_score,
        -gate_failures,
        -critical_warnings,
        -warnings,
        health_score,
        metric_value,
    )


def _numeric_summary_value(summary: dict[str, object], key: str) -> float:
    value = summary.get(key, 0.0)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _metric_value_for_rank(result: BacktestResult, rank_by: str) -> float:
    value = getattr(result.metrics, rank_by, None)
    if value is None:
        raise ValueError(f"Rank metric '{rank_by}' is not available on backtest metrics.")
    if not isinstance(value, (int, float)):
        raise ValueError(f"Rank metric '{rank_by}' must be numeric.")
    return float(value)


def build_input_metadata(
    args: argparse.Namespace,
    config: BacktestConfig,
) -> dict[str, str | bool | None]:
    return {
        "demo": bool(args.demo),
        "csv": args.csv,
        "benchmark_csv": args.benchmark_csv,
        "stock_pool_csv": None if config.stock_pool_csv is None else str(config.stock_pool_csv),
        "symbol_group_csv": None
        if config.symbol_group_csv is None
        else str(config.symbol_group_csv),
        "factor_score_csv": None
        if config.factor_score_csv is None
        else str(config.factor_score_csv),
        "config": args.config,
        "sweep": bool(args.sweep),
    }
