from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
from typing import Mapping, cast

from .backtest import run_backtest
from .config import (
    BacktestConfig,
    load_config_overrides_from_toml,
    load_sweep_overrides_from_toml,
)
from .data_loader import load_benchmark_bars_from_csv, load_price_bars_from_csv
from .models import BacktestResult, PriceBar
from .reporting import (
    load_symbol_name_mapping,
    print_summary,
    save_batch_chart_svg,
    save_batch_heatmap_svg,
    save_batch_rankings,
    save_batch_report_html,
    save_batch_summary,
    save_equity_chart_svg,
    save_equity_curve,
    save_performance_summary,
    save_performance_summary_json,
    save_rebalance_log,
    save_run_manifest,
    save_single_run_report_html,
)
from .sample_data import generate_demo_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行 MyFinances A 股量化回测工具。"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用内置演示数据，不从 CSV 文件读取行情。",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help=(
            "A 股行情 CSV 路径。必填列为 date、symbol、close；可选列为 "
            "adjusted_close、volume、tradable、can_buy、can_sell。"
            "symbol 必须为 6 位 A 股代码。"
        ),
    )
    parser.add_argument(
        "--benchmark-csv",
        type=str,
        help="可选基准 CSV 路径。必填列为 date、close；可选列为 adjusted_close。",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="可选 TOML 配置文件。命令行参数会覆盖文件中的同名配置。",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="读取 TOML 中的 [sweep] 配置并执行批量参数扫描。",
    )
    parser.add_argument(
        "--rank-by",
        type=str,
        default="annualized_return",
        help="批量扫描结果的排序指标，默认值为 annualized_return。",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="指定结果输出目录，默认使用配置中的 output_dir。",
    )
    parser.add_argument(
        "--price-field",
        choices=["close", "adjusted_close"],
        help="选择回测使用的价格字段，可选 close 或 adjusted_close。",
    )
    parser.add_argument("--top-n", type=int, help="每次调仓选取的股票数量。")
    parser.add_argument("--rebalance-days", type=int, help="调仓间隔天数。")
    parser.add_argument("--initial-cash", type=float, help="回测初始资金。")
    parser.add_argument("--commission-rate", type=float, help="买卖双边佣金费率。")
    parser.add_argument("--slippage-rate", type=float, help="交易滑点费率。")
    parser.add_argument("--stamp-duty-rate", type=float, help="卖出印花税费率。")
    parser.add_argument("--lookback-momentum", type=int, help="动量因子的回看天数。")
    parser.add_argument(
        "--lookback-mean-reversion",
        type=int,
        help="均值回归因子的回看天数。",
    )
    parser.add_argument(
        "--lookback-volatility",
        type=int,
        help="低波动因子的回看天数。",
    )
    parser.add_argument(
        "--factor-weight",
        action="append",
        help=(
            "使用 name=value 覆盖因子权重，可重复传入多次。"
            "当前仅支持 momentum、mean_reversion、low_volatility。"
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    bars = _load_bars(args, parser)
    benchmark_bars = _load_benchmark_bars(args)

    if args.sweep:
        if not args.config:
            parser.error("--sweep 需要配合 --config 使用，且配置文件中必须包含 [sweep]。")
            return
        _run_sweep(args, bars, benchmark_bars)
        return

    backtest_config = _build_backtest_config(args)
    result = run_backtest(bars, backtest_config, benchmark_bars=benchmark_bars)
    artifact_paths = _persist_run_outputs(
        output_dir=backtest_config.output_dir,
        result=result,
        config=backtest_config,
        inputs=_build_input_metadata(args),
        print_console=True,
    )
    print(f"净值曲线 CSV 已保存：{artifact_paths['equity_curve_csv']}")
    print(f"调仓日志 CSV 已保存：{artifact_paths['rebalance_log_csv']}")
    print(f"绩效摘要 CSV 已保存：{artifact_paths['performance_summary_csv']}")
    print(f"绩效摘要 JSON 已保存：{artifact_paths['performance_summary_json']}")
    print(f"运行清单 JSON 已保存：{artifact_paths['run_manifest_json']}")
    print(f"净值图 SVG 已保存：{artifact_paths['equity_curve_svg']}")
    print(f"HTML 报告已保存：{artifact_paths['report_html']}")


def _run_sweep(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
) -> None:
    base_config = _build_backtest_config(args)
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("配置文件中未找到 [sweep] 配置段。")

    batch_output_dir = base_config.output_dir / "batch_runs"
    rows: list[dict[str, object]] = []
    combinations = _expand_sweep_combinations(sweep_overrides)

    for run_number, override_values in enumerate(combinations, start=1):
        run_id = f"run_{run_number:03d}"
        run_output_dir = batch_output_dir / run_id
        config_kwargs = _config_to_kwargs(base_config)
        config_kwargs.update(override_values)
        config_kwargs["output_dir"] = run_output_dir
        run_config = _build_config_from_mapping(config_kwargs)
        result = run_backtest(bars, run_config, benchmark_bars=benchmark_bars)
        artifact_paths = _persist_run_outputs(
            output_dir=run_output_dir,
            result=result,
            config=run_config,
            inputs=_build_input_metadata(args),
            print_console=False,
        )
        rows.append(
            _build_batch_row(
                run_id=run_id,
                config=run_config,
                overrides=override_values,
                result=result,
                artifact_paths=artifact_paths,
            )
        )

    summary_csv_path, summary_json_path = save_batch_summary(rows, batch_output_dir)
    leaderboard_csv_path, leaderboard_json_path, best_run_path = save_batch_rankings(
        rows,
        batch_output_dir,
        rank_by=args.rank_by,
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
    print(f"批量对比图已保存：{batch_chart_path}")
    if heatmap_path is not None:
        print(f"热力图已保存：{heatmap_path}")
    print(f"批量 HTML 报告已保存：{batch_report_path}")


def _load_bars(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[PriceBar]:
    if args.demo:
        return generate_demo_bars()
    if args.csv:
        return load_price_bars_from_csv(args.csv)
    parser.error("请使用 --demo，或通过 --csv <path> 提供行情文件。")
    raise AssertionError("parser.error 应已终止程序")


def _load_benchmark_bars(args: argparse.Namespace) -> list[PriceBar] | None:
    if args.benchmark_csv:
        return load_benchmark_bars_from_csv(args.benchmark_csv)
    return None


def _persist_run_outputs(
    *,
    output_dir: Path,
    result: BacktestResult,
    config: BacktestConfig,
    inputs: dict[str, str | bool | None],
    print_console: bool,
) -> dict[str, Path]:
    symbol_names = load_symbol_name_mapping(config.symbol_name_csv)
    if print_console:
        print_summary(
            result.equity_curve,
            result.rebalance_records,
            result.metrics,
            config,
        )
    equity_path = save_equity_curve(
        result.equity_curve,
        output_dir,
        result.benchmark_curve,
        symbol_names=symbol_names,
    )
    rebalance_path = save_rebalance_log(
        result.rebalance_records,
        output_dir,
        symbol_names=symbol_names,
    )
    summary_path = save_performance_summary(result.metrics, output_dir)
    summary_json_path = save_performance_summary_json(result.metrics, output_dir)
    equity_chart_path = save_equity_chart_svg(
        result.equity_curve,
        output_dir,
        result.benchmark_curve,
    )
    artifact_paths = {
        "equity_curve_csv": equity_path,
        "equity_curve_svg": equity_chart_path,
        "rebalance_log_csv": rebalance_path,
        "performance_summary_csv": summary_path,
        "performance_summary_json": summary_json_path,
    }
    manifest_path = save_run_manifest(
        output_dir=output_dir,
        config=config,
        inputs=inputs,
        artifacts=artifact_paths,
        metrics=result.metrics,
    )
    artifact_paths["run_manifest_json"] = manifest_path
    report_path = save_single_run_report_html(
        output_dir=output_dir,
        config=config,
        metrics=result.metrics,
        artifacts=artifact_paths,
        latest_holdings=result.equity_curve[-1].holdings if result.equity_curve else (),
        latest_rebalance=result.rebalance_records[-1] if result.rebalance_records else None,
        symbol_names=symbol_names,
    )
    artifact_paths["report_html"] = report_path
    return artifact_paths


def _build_backtest_config(args: argparse.Namespace) -> BacktestConfig:
    default_config = BacktestConfig()
    config_kwargs: dict[str, object] = {
        "initial_cash": default_config.initial_cash,
        "top_n": default_config.top_n,
        "lookback_momentum": default_config.lookback_momentum,
        "lookback_mean_reversion": default_config.lookback_mean_reversion,
        "lookback_volatility": default_config.lookback_volatility,
        "rebalance_every_n_days": default_config.rebalance_every_n_days,
        "commission_rate": default_config.commission_rate,
        "slippage_rate": default_config.slippage_rate,
        "stamp_duty_rate": default_config.stamp_duty_rate,
        "price_field": default_config.price_field,
        "output_dir": default_config.output_dir,
        "symbol_name_csv": default_config.symbol_name_csv,
        "factor_weights": default_config.factor_weights.copy(),
    }

    if args.config:
        config_kwargs.update(load_config_overrides_from_toml(args.config))

    cli_overrides = {
        "initial_cash": args.initial_cash,
        "top_n": args.top_n,
        "lookback_momentum": args.lookback_momentum,
        "lookback_mean_reversion": args.lookback_mean_reversion,
        "lookback_volatility": args.lookback_volatility,
        "rebalance_every_n_days": args.rebalance_days,
        "commission_rate": args.commission_rate,
        "slippage_rate": args.slippage_rate,
        "stamp_duty_rate": args.stamp_duty_rate,
        "price_field": args.price_field,
    }
    for key, value in cli_overrides.items():
        if value is not None:
            config_kwargs[key] = value

    if args.output_dir is not None:
        config_kwargs["output_dir"] = Path(args.output_dir)

    if args.factor_weight:
        factor_weights = cast(dict[str, float], config_kwargs["factor_weights"]).copy()
        factor_weights.update(_parse_factor_weight_overrides(args.factor_weight))
        config_kwargs["factor_weights"] = factor_weights

    return _build_config_from_mapping(config_kwargs)


def _parse_factor_weight_overrides(entries: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(
                f"无效的因子权重配置：'{entry}'。请使用 factor_name=value 格式。"
            )
        name, raw_value = entry.split("=", 1)
        factor_name = name.strip()
        if not factor_name:
            raise ValueError("因子权重名称不能为空。")
        parsed[factor_name] = float(raw_value.strip())
    return parsed


def _expand_sweep_combinations(sweep_overrides: dict[str, list[object]]) -> list[dict[str, object]]:
    field_names = list(sweep_overrides.keys())
    combinations = []
    for values in product(*(sweep_overrides[field_name] for field_name in field_names)):
        combinations.append(dict(zip(field_names, values, strict=True)))
    return combinations


def _build_batch_row(
    *,
    run_id: str,
    config: BacktestConfig,
    overrides: dict[str, object],
    result: BacktestResult,
    artifact_paths: dict[str, Path],
) -> dict[str, object]:
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
        "equity_curve_csv": str(artifact_paths["equity_curve_csv"]),
        "run_manifest_json": str(artifact_paths["run_manifest_json"]),
    }
    for key, value in overrides.items():
        row[f"param_{key}"] = value
    return row


def _build_input_metadata(args: argparse.Namespace) -> dict[str, str | bool | None]:
    return {
        "demo": bool(args.demo),
        "csv": args.csv,
        "benchmark_csv": args.benchmark_csv,
        "config": args.config,
        "sweep": bool(args.sweep),
    }


def _build_config_from_mapping(config_kwargs: Mapping[str, object]) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=cast(float, config_kwargs["initial_cash"]),
        top_n=cast(int, config_kwargs["top_n"]),
        lookback_momentum=cast(int, config_kwargs["lookback_momentum"]),
        lookback_mean_reversion=cast(int, config_kwargs["lookback_mean_reversion"]),
        lookback_volatility=cast(int, config_kwargs["lookback_volatility"]),
        rebalance_every_n_days=cast(int, config_kwargs["rebalance_every_n_days"]),
        commission_rate=cast(float, config_kwargs["commission_rate"]),
        slippage_rate=cast(float, config_kwargs["slippage_rate"]),
        stamp_duty_rate=cast(float, config_kwargs["stamp_duty_rate"]),
        price_field=cast(str, config_kwargs["price_field"]),
        output_dir=cast(Path, config_kwargs["output_dir"]),
        symbol_name_csv=cast(Path | None, config_kwargs["symbol_name_csv"]),
        factor_weights=cast(dict[str, float], config_kwargs["factor_weights"]).copy(),
    )


def _config_to_kwargs(config: BacktestConfig) -> dict[str, object]:
    return {
        "initial_cash": config.initial_cash,
        "top_n": config.top_n,
        "lookback_momentum": config.lookback_momentum,
        "lookback_mean_reversion": config.lookback_mean_reversion,
        "lookback_volatility": config.lookback_volatility,
        "rebalance_every_n_days": config.rebalance_every_n_days,
        "commission_rate": config.commission_rate,
        "slippage_rate": config.slippage_rate,
        "stamp_duty_rate": config.stamp_duty_rate,
        "price_field": config.price_field,
        "output_dir": config.output_dir,
        "symbol_name_csv": config.symbol_name_csv,
        "factor_weights": config.factor_weights.copy(),
    }


if __name__ == "__main__":
    main()
