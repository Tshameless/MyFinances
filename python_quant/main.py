from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from itertools import product
from pathlib import Path
from typing import Mapping, TypedDict, TypeVar, cast

logger = logging.getLogger(__name__)

from .analysis import (
    build_batch_stability_analysis,
    build_walk_forward_optimization_summary,
    build_walk_forward_summary,
    build_walk_forward_train_test_windows,
    build_walk_forward_windows,
)
from .backtest import run_backtest
from .config import (
    BacktestConfig,
    load_config_overrides_from_toml,
    load_sweep_overrides_from_toml,
)
from .data_loader import (
    load_benchmark_bars_from_csv,
    load_factor_scores_from_csv,
    load_price_bars_from_csv,
    load_stock_pool_from_csv,
)
from .data_quality import (
    build_benchmark_quality_report,
    build_factor_score_quality_report,
    build_price_data_quality_report,
    build_stock_pool_quality_report,
    build_symbol_group_quality_report,
    save_benchmark_quality_report,
    save_data_quality_report,
    save_factor_score_quality_report,
    save_mapping_quality_report,
    save_stock_pool_quality_report,
)
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
from .sample_data import generate_demo_bars
from .trading_rules import apply_inferred_limit_flags

T = TypeVar("T")
R = TypeVar("R")


class _TrainCandidateResult(TypedDict):
    result: BacktestResult
    artifacts: dict[str, Path]
    health_summary: dict[str, object]
    overrides: dict[str, object]


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
            "adjusted_close、volume、tradable、can_buy、can_sell、is_st、limit_rate。"
            "symbol 必须为 6 位 A 股代码。"
        ),
    )
    parser.add_argument(
        "--benchmark-csv",
        type=str,
        help="可选基准 CSV 路径。必填列为 date、close；可选列为 adjusted_close。",
    )
    parser.add_argument(
        "--stock-pool-csv",
        type=str,
        help="可选股票池 CSV 路径。必填列为 date、symbol；调仓时仅在有效股票池内开新仓。",
    )
    parser.add_argument(
        "--symbol-group-csv",
        type=str,
        help="可选代码分组 CSV 路径。必填列为 symbol、group；用于行业/板块暴露分析。",
    )
    parser.add_argument(
        "--factor-score-csv",
        type=str,
        help="可选外部因子评分 CSV 路径。必填列为 date、symbol、score；调仓日优先使用外部分数选股。",
    )
    parser.add_argument(
        "--validate-csv",
        action="store_true",
        help="只校验 --csv、--benchmark-csv、--stock-pool-csv 和 --symbol-group-csv 指定的数据文件，不执行回测。",
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
        "--walk-forward",
        action="store_true",
        help="按滚动时间窗口执行 walk-forward 回测稳定性验证。",
    )
    parser.add_argument(
        "--walk-optimize",
        action="store_true",
        help="读取 TOML [sweep] 参数网格，在训练窗口选参并在后续测试窗口验证。",
    )
    parser.add_argument(
        "--walk-window",
        type=int,
        default=30,
        help="walk-forward 每个窗口包含的交易日数量，默认 30。",
    )
    parser.add_argument(
        "--walk-step",
        type=int,
        default=10,
        help="walk-forward 窗口向前滚动的交易日步长，默认 10。",
    )
    parser.add_argument(
        "--walk-train-window",
        type=int,
        default=40,
        help="walk-forward 优化训练窗口交易日数量，默认 40。",
    )
    parser.add_argument(
        "--walk-test-window",
        type=int,
        default=20,
        help="walk-forward 优化测试窗口交易日数量，默认 20。",
    )
    parser.add_argument(
        "--rank-by",
        type=str,
        default="annualized_return",
        help="批量扫描结果的排序指标，默认值为 annualized_return。",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="批量扫描和 walk-forward 优化的并行任务数，默认 1 表示串行。",
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
    parser.add_argument(
        "--selection-mode",
        choices=["top", "bottom"],
        help="选股方向：top 选择高分标的，bottom 选择低分标的，默认 top。",
    )
    parser.add_argument(
        "--score-source",
        choices=["auto", "builtin", "external"],
        help="评分来源：auto 有外部评分时优先使用，builtin 只用内置因子，external 要求调仓日必须有外部评分。",
    )
    parser.add_argument("--max-group-positions", type=int, help="每个代码分组最多入选股票数量；需配合 symbol_group_csv。")
    parser.add_argument("--lot-size", type=int, help="每手股数，A 股默认使用 100。")
    parser.add_argument("--rebalance-days", type=int, help="调仓间隔天数。")
    parser.add_argument("--initial-cash", type=float, help="回测初始资金。")
    parser.add_argument("--commission-rate", type=float, help="买卖双边佣金费率。")
    parser.add_argument("--buy-commission-rate", type=float, help="买入佣金费率；不填则沿用 commission_rate。")
    parser.add_argument("--sell-commission-rate", type=float, help="卖出佣金费率；不填则沿用 commission_rate。")
    parser.add_argument("--slippage-rate", type=float, help="交易滑点费率。")
    parser.add_argument("--market-impact-coefficient", type=float, help="成交量参与率冲击成本系数；0 表示关闭。")
    parser.add_argument("--market-impact-exponent", type=float, help="成交量参与率冲击成本指数，默认 1.0。")
    parser.add_argument("--stamp-duty-rate", type=float, help="卖出印花税费率。")
    parser.add_argument("--lookback-momentum", type=int, help="动量因子的回看天数。")
    parser.add_argument("--rolling-risk-window", type=int, help="滚动风险分析窗口期数，默认 20。")
    parser.add_argument("--max-allowed-drawdown", type=float, help="策略风险闸门：最大允许回撤，默认 0.20。")
    parser.add_argument("--max-allowed-daily-var", type=float, help="策略风险闸门：最大允许 95%% 日 VaR，默认 0.05。")
    parser.add_argument("--min-allowed-rolling-return", type=float, help="策略风险闸门：最差滚动收益下限，默认 -0.10。")
    parser.add_argument("--min-allowed-information-ratio", type=float, help="策略风险闸门：最低信息比率，默认 0.0。")
    parser.add_argument("--min-allowed-fill-rate", type=float, help="策略风险闸门：最低成交率，默认 0.70。")
    parser.add_argument("--min-allowed-execution-price-coverage", type=float, help="策略风险闸门：最低执行价字段覆盖率，默认 1.00。")
    parser.add_argument("--min-allowed-factor-score-coverage", type=float, help="策略风险闸门：最低外部评分覆盖率，默认 0.95。")
    parser.add_argument("--max-allowed-market-constraint-rate", type=float, help="策略风险闸门：最大市场约束拒单占比，默认 0.50。")
    parser.add_argument("--max-allowed-position-weight", type=float, help="策略风险闸门：最大单票权重，默认 0.50。")
    parser.add_argument("--max-allowed-group-weight", type=float, help="策略风险闸门：最大分组/行业权重，默认 0.60。")
    parser.add_argument("--max-allowed-attribution-residual", type=float, help="策略风险闸门：最大收益归因残差，默认 0.05。")
    parser.add_argument("--max-allowed-factor-correlation", type=float, help="策略风险闸门：最大平均因子相关性绝对值，默认 0.90。")
    parser.add_argument("--min-commission", type=float, help="单笔最低佣金。")
    parser.add_argument("--transfer-fee-rate", type=float, help="买卖双边过户费率。")
    parser.add_argument("--target-cash-weight", type=float, help="目标现金权重，默认 0。")
    parser.add_argument("--max-position-weight", type=float, help="单只股票目标权重上限，默认 1.0。")
    parser.add_argument("--infer-limit-flags", action="store_true", help="根据涨跌幅自动推断涨停不可买、跌停不可卖。")
    parser.add_argument("--forward-fill-suspended-bars", action="store_true", help="对缺失行情用前值补不可交易停牌估值条。")
    parser.add_argument("--limit-up-down-rate", type=float, help="涨跌停推断阈值，普通 A 股默认 0.10。")
    parser.add_argument("--st-limit-up-down-rate", type=float, help="ST 股票涨跌停推断阈值，默认 0.05。")
    parser.add_argument("--growth-limit-up-down-rate", type=float, help="创业板/科创板涨跌停推断阈值，默认 0.20。")
    parser.add_argument("--bse-limit-up-down-rate", type=float, help="北交所涨跌停推断阈值，默认 0.30。")
    parser.add_argument("--infer-limit-rate-by-symbol", action="store_true", help="根据证券代码自动推断创业板、科创板和北交所涨跌停阈值。")
    parser.add_argument("--max-volume-participation", type=float, help="单日最多参与成交量比例，默认 1.0。")
    parser.add_argument("--start-date", type=str, help="回测开始日期，格式为 YYYY-MM-DD。")
    parser.add_argument("--end-date", type=str, help="回测结束日期，格式为 YYYY-MM-DD。")
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
    parser.add_argument(
        "--execution-price-field",
        choices=["close", "adjusted_close", "open", "vwap"],
        help="Select the trade execution price field. Defaults to price_field when omitted.",
    )
    parser.add_argument(
        "--execution-delay-days",
        type=int,
        help="Delay trade execution by N aligned trading bars after the signal date.",
    )
    parser.add_argument(
        "--max-allowed-rebalance-changes",
        type=float,
        help="Maximum average entries plus exits per rebalance allowed by the strategy health gate.",
    )
    parser.add_argument(
        "--min-allowed-holding-days",
        type=float,
        help="Minimum average realized holding days allowed by the strategy health gate.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _run_with_args(args, parser)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0


def _run_with_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.validate_csv:
        _validate_csv_inputs(args, parser)
        return

    backtest_config = _build_backtest_config(args)
    bars = _filter_bars_by_date_range(
        _load_bars(args, parser),
        start_date=backtest_config.start_date,
        end_date=backtest_config.end_date,
    )
    bars = apply_inferred_limit_flags(bars, backtest_config)
    benchmark_bars = _load_benchmark_bars(args)
    stock_pool_by_date = _load_stock_pool(backtest_config)
    symbol_groups = _load_symbol_groups(backtest_config)
    factor_scores_by_date = _load_factor_scores(backtest_config)
    if benchmark_bars is not None:
        benchmark_bars = _filter_bars_by_date_range(
            benchmark_bars,
            start_date=backtest_config.start_date,
            end_date=backtest_config.end_date,
        )

    if args.sweep:
        if not args.config:
            parser.error("--sweep 需要配合 --config 使用，且配置文件中必须包含 [sweep]。")
            return
        _run_sweep(args, bars, benchmark_bars, base_config=backtest_config)
        return

    if args.walk_forward:
        _run_walk_forward(args, bars, benchmark_bars, base_config=backtest_config)
        return

    if args.walk_optimize:
        if not args.config:
            parser.error("--walk-optimize 需要配合 --config 使用，且配置文件中必须包含 [sweep]。")
            return
        _run_walk_forward_optimization(args, bars, benchmark_bars, base_config=backtest_config)
        return

    result = run_backtest(
        bars,
        backtest_config,
        benchmark_bars=benchmark_bars,
        stock_pool_by_date=stock_pool_by_date,
        symbol_groups=symbol_groups,
        factor_scores_by_date=factor_scores_by_date,
    )
    artifact_paths = persist_run_outputs(
        output_dir=backtest_config.output_dir,
        result=result,
        config=backtest_config,
        inputs=_build_input_metadata(args, backtest_config),
        print_console=True,
        config_sources=_build_config_sources(args),
    )
    print(f"净值曲线 CSV 已保存：{artifact_paths['equity_curve_csv']}")
    logger.info("调仓日志 CSV: %s", artifact_paths['rebalance_log_csv'])
    logger.info("每日持仓账本 CSV: %s", artifact_paths['positions_csv'])
    logger.info("逐笔交易明细 CSV: %s", artifact_paths['trades_csv'])
    logger.info("未成交原因 CSV: %s", artifact_paths['trade_attempts_csv'])
    logger.info("因子评分明细 CSV: %s", artifact_paths['factor_scores_csv'])
    logger.info("因子 IC 分析 CSV: %s", artifact_paths['factor_ic_csv'])
    logger.info("因子分组收益 CSV: %s", artifact_paths['factor_group_returns_csv'])
    logger.info("因子衰减分析 CSV: %s", artifact_paths['factor_decay_csv'])
    logger.info("因子相关性矩阵 CSV: %s", artifact_paths['factor_correlation_csv'])
    logger.info("回撤序列 CSV: %s", artifact_paths['drawdown_csv'])
    logger.info("月度收益 CSV: %s", artifact_paths['monthly_returns_csv'])
    logger.info("滚动风险 CSV: %s", artifact_paths['rolling_risk_csv'])
    logger.info("相对基准表现 CSV: %s", artifact_paths['relative_performance_csv'])
    logger.info("执行质量 CSV: %s", artifact_paths['execution_quality_csv'])
    logger.info("持仓暴露 CSV: %s", artifact_paths['exposure_csv'])
    logger.info("分组暴露 CSV: %s", artifact_paths['group_exposure_csv'])
    logger.info("收益归因 CSV: %s", artifact_paths['return_attribution_csv'])
    logger.info("成本归因 CSV: %s", artifact_paths['cost_attribution_csv'])
    logger.info("盈亏对账 CSV: %s", artifact_paths['pnl_ledger_csv'])
    logger.info("策略健康诊断 CSV: %s", artifact_paths['strategy_health_csv'])
    logger.info("策略风险闸门 CSV: %s", artifact_paths['strategy_health_gates_csv'])
    logger.info("绩效摘要 CSV: %s", artifact_paths['performance_summary_csv'])
    logger.info("绩效摘要 JSON: %s", artifact_paths['performance_summary_json'])
    logger.info("最终生效配置 JSON: %s", artifact_paths['config_effective_json'])
    logger.info("配置来源 JSON: %s", artifact_paths['config_sources_json'])
    logger.info("运行清单 JSON: %s", artifact_paths['run_manifest_json'])
    print(f"净值图 SVG 已保存：{artifact_paths['equity_curve_svg']}")
    print(f"HTML 报告已保存：{artifact_paths['report_html']}")
    logger.info("停牌分析 CSV: %s", artifact_paths['suspension_analysis_csv'])
    logger.info("停牌日汇总 CSV: %s", artifact_paths['suspension_daily_csv'])


def _run_sweep(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig | None = None,
) -> None:
    base_config = base_config or _build_backtest_config(args)
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("配置文件中未找到 [sweep] 配置段。")

    batch_output_dir = base_config.output_dir / "batch_runs"
    rows: list[dict[str, object]] = []
    combinations = _expand_sweep_combinations(sweep_overrides)

    rows = _map_jobs(
        [
            (run_number, override_values)
            for run_number, override_values in enumerate(combinations, start=1)
        ],
        lambda item: _run_sweep_case(
            args=args,
            bars=bars,
            benchmark_bars=benchmark_bars,
            base_config=base_config,
            batch_output_dir=batch_output_dir,
            run_number=item[0],
            override_values=item[1],
        ),
        jobs=args.jobs,
    )

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


def _run_walk_forward(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig,
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
        window_bars = _filter_bars_by_date_range(
            bars,
            start_date=start_date,
            end_date=end_date,
        )
        window_benchmark_bars = (
            None
            if benchmark_bars is None
            else _filter_bars_by_date_range(
                benchmark_bars,
                start_date=start_date,
                end_date=end_date,
            )
        )
        result = run_backtest(
            window_bars,
            run_config,
            benchmark_bars=window_benchmark_bars,
            stock_pool_by_date=_load_stock_pool(run_config),
            symbol_groups=_load_symbol_groups(run_config),
            factor_scores_by_date=_load_factor_scores(run_config),
        )
        artifact_paths = persist_run_outputs(
            output_dir=run_output_dir,
            result=result,
            config=run_config,
            inputs=_build_input_metadata(args, run_config),
            print_console=False,
            config_sources=_build_config_sources(args),
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


def _run_sweep_case(
    *,
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    base_config: BacktestConfig,
    batch_output_dir: Path,
    run_number: int,
    override_values: dict[str, object],
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
        stock_pool_by_date=_load_stock_pool(run_config),
        symbol_groups=_load_symbol_groups(run_config),
        factor_scores_by_date=_load_factor_scores(run_config),
    )
    artifact_paths = persist_run_outputs(
        output_dir=run_output_dir,
        result=result,
        config=run_config,
        inputs=_build_input_metadata(args, run_config),
        print_console=False,
        config_sources=_build_config_sources(args, sweep_overrides=override_values),
    )
    return _build_batch_row(
        run_id=run_id,
        config=run_config,
        overrides=override_values,
        result=result,
        artifact_paths=artifact_paths,
    )


def _map_jobs(
    items: list[T],
    worker: Callable[[T], R],
    *,
    jobs: int,
) -> list[R]:
    if jobs <= 1 or len(items) <= 1:
        return [worker(item) for item in items]
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        return list(executor.map(worker, items))


def _run_walk_forward_optimization(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    *,
    base_config: BacktestConfig,
) -> None:
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("配置文件中未找到 [sweep] 配置段。")
    combinations = _expand_sweep_combinations(sweep_overrides)
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
        train_bars = _filter_bars_by_date_range(
            bars,
            start_date=train_start,
            end_date=train_end,
        )
        test_bars = _filter_bars_by_date_range(
            bars,
            start_date=test_start,
            end_date=test_end,
        )
        train_benchmark_bars = (
            None
            if benchmark_bars is None
            else _filter_bars_by_date_range(
                benchmark_bars,
                start_date=train_start,
                end_date=train_end,
            )
        )
        test_benchmark_bars = (
            None
            if benchmark_bars is None
            else _filter_bars_by_date_range(
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
        candidate_results: list[_TrainCandidateResult] = _map_jobs(
            [
                (combo_number, override_values)
                for combo_number, override_values in enumerate(combinations, start=1)
            ],
            lambda item: _run_walk_forward_train_candidate(
                args=args,
                train_bars=train_bars,
                train_benchmark_bars=train_benchmark_bars,
                base_config=base_config,
                train_output_dir=optimize_output_dir / window_id / "train_candidates" / f"candidate_{item[0]:03d}",
                train_start=train_start,
                train_end=train_end,
                override_values=item[1],
            ),
            jobs=args.jobs,
        )
        for candidate in candidate_results:
            train_result = candidate["result"]
            train_artifacts = candidate["artifacts"]
            health_summary = candidate["health_summary"]
            override_values = candidate["overrides"]
            metric_value = _metric_value_for_rank(train_result, args.rank_by)
            candidate_key = _health_aware_rank_key(metric_value, health_summary)
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
            stock_pool_by_date=_load_stock_pool(test_config),
            symbol_groups=_load_symbol_groups(test_config),
            factor_scores_by_date=_load_factor_scores(test_config),
        )
        test_artifacts = persist_run_outputs(
            output_dir=test_output_dir,
            result=test_result,
            config=test_config,
            inputs=_build_input_metadata(args, test_config),
            print_console=False,
            config_sources=_build_config_sources(args, sweep_overrides=best_overrides),
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
            "train_gate_failures": _summary_value(best_train_health_summary, "gate_failures"),
            "train_health_warnings": _summary_value(best_train_health_summary, "warnings"),
            "train_critical_warnings": _summary_value(best_train_health_summary, "critical_warnings"),
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
    logger.info(f"Walk-forward 优化完成，共运行 {len(rows)} 个训练/测试窗口。")
    logger.info(f"Walk-forward 优化 CSV 已保存：{paths['walk_forward_optimization_csv']}")
    logger.info(f"Walk-forward 优化 JSON 已保存：{paths['walk_forward_optimization_json']}")
    logger.info(f"Walk-forward 优化 HTML 报告已保存：{report_path}")


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
        stock_pool_by_date=_load_stock_pool(train_config),
        symbol_groups=_load_symbol_groups(train_config),
        factor_scores_by_date=_load_factor_scores(train_config),
    )
    train_artifacts = persist_run_outputs(
        output_dir=train_output_dir,
        result=train_result,
        config=train_config,
        inputs=_build_input_metadata(args, train_config),
        print_console=False,
        config_sources=_build_config_sources(args, sweep_overrides=override_values),
    )
    return {
        "result": train_result,
        "artifacts": train_artifacts,
        "health_summary": _load_json_summary(train_artifacts.get("strategy_health_json")),
        "overrides": override_values,
    }


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


def _load_stock_pool(config: BacktestConfig) -> dict[date, set[str]] | None:
    if config.stock_pool_csv is None:
        return None
    return load_stock_pool_from_csv(config.stock_pool_csv)


def _load_symbol_groups(config: BacktestConfig) -> dict[str, str] | None:
    if config.symbol_group_csv is None:
        return None
    return load_symbol_group_mapping(config.symbol_group_csv)


def _load_factor_scores(config: BacktestConfig) -> dict[date, dict[str, float]] | None:
    if config.factor_score_csv is None:
        return None
    return load_factor_scores_from_csv(config.factor_score_csv)


def _filter_bars_by_date_range(
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


def _validate_csv_inputs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    loaded_any = False
    output_dir = Path(args.output_dir) if args.output_dir else Path("output") / "data_quality"
    price_symbols: set[str] | None = None
    price_dates: set[date] | None = None
    if args.csv:
        bars = load_price_bars_from_csv(args.csv)
        symbols = sorted({bar.symbol for bar in bars})
        price_symbols = set(symbols)
        dates = sorted({bar.date for bar in bars})
        price_dates = set(dates)
        price_report = build_price_data_quality_report(bars)
        report_paths = save_data_quality_report(price_report, output_dir, prefix="price_data_quality")
        loaded_any = True
        print(
            "行情 CSV 校验通过："
            f"{len(bars)} 行，{len(symbols)} 只标的，"
            f"{dates[0].isoformat()} 至 {dates[-1].isoformat()}。"
        )
        print(f"行情数据质量 CSV 已保存：{report_paths['price_data_quality_report_csv']}")
        print(f"行情数据质量 JSON 已保存：{report_paths['price_data_quality_report_json']}")
    if args.benchmark_csv:
        benchmark_bars = load_benchmark_bars_from_csv(args.benchmark_csv)
        dates = [bar.date for bar in benchmark_bars]
        benchmark_report = build_benchmark_quality_report(
            benchmark_bars,
            expected_dates=price_dates,
        )
        benchmark_report_paths = save_benchmark_quality_report(
            benchmark_report,
            output_dir,
        )
        loaded_any = True
        print(
            "基准 CSV 校验通过："
            f"{len(benchmark_bars)} 行，"
            f"{dates[0].isoformat()} 至 {dates[-1].isoformat()}。"
        )
        print(f"基准质量 CSV 已保存：{benchmark_report_paths['benchmark_quality_report_csv']}")
        print(f"基准质量 JSON 已保存：{benchmark_report_paths['benchmark_quality_report_json']}")
    if args.stock_pool_csv:
        stock_pool = load_stock_pool_from_csv(args.stock_pool_csv)
        dates = sorted(stock_pool)
        symbol_count = len({symbol for symbols in stock_pool.values() for symbol in symbols})
        row_count = sum(len(symbols) for symbols in stock_pool.values())
        pool_report = build_stock_pool_quality_report(
            Path(args.stock_pool_csv),
            expected_symbols=price_symbols,
        )
        pool_report_paths = save_stock_pool_quality_report(pool_report, output_dir)
        loaded_any = True
        print(
            "股票池 CSV 校验通过："
            f"{row_count} 行，{symbol_count} 只标的，"
            f"{dates[0].isoformat()} 至 {dates[-1].isoformat()}。"
        )
        print(f"股票池质量 CSV 已保存：{pool_report_paths['stock_pool_quality_report_csv']}")
        print(f"股票池质量 JSON 已保存：{pool_report_paths['stock_pool_quality_report_json']}")
    if args.symbol_group_csv:
        group_report = build_symbol_group_quality_report(
            Path(args.symbol_group_csv),
            expected_symbols=price_symbols,
        )
        report_paths = save_mapping_quality_report(group_report, output_dir)
        loaded_any = True
        print(
            "分组映射 CSV 校验完成："
            f"{group_report.summary['row_count']} 行，"
            f"{group_report.summary['mapped_symbol_count']} 只标的，"
            f"{group_report.summary['group_count']} 个分组。"
        )
        print(f"分组映射质量 CSV 已保存：{report_paths['symbol_group_quality_report_csv']}")
        print(f"分组映射质量 JSON 已保存：{report_paths['symbol_group_quality_report_json']}")
    if args.factor_score_csv:
        score_report = build_factor_score_quality_report(
            Path(args.factor_score_csv),
            expected_symbols=price_symbols,
            expected_dates=price_dates,
        )
        score_report_paths = save_factor_score_quality_report(score_report, output_dir)
        loaded_any = True
        print(
            "外部因子评分 CSV 校验完成："
            f"{score_report.summary['row_count']} 行，"
            f"{score_report.summary['scored_symbol_count']} 只标的，"
            f"{score_report.summary['date_count']} 个评分日。"
        )
        print(f"外部因子评分质量 CSV 已保存：{score_report_paths['factor_score_quality_report_csv']}")
        print(f"外部因子评分质量 JSON 已保存：{score_report_paths['factor_score_quality_report_json']}")
        print(f"外部因子评分每日分布 CSV 已保存：{score_report_paths['factor_score_quality_distribution_by_date_csv']}")
    if not loaded_any:
        parser.error("--validate-csv 需要配合 --csv、--benchmark-csv、--stock-pool-csv、--symbol-group-csv 或 --factor-score-csv 使用。")


def _build_backtest_config(args: argparse.Namespace) -> BacktestConfig:
    default_config = BacktestConfig()
    config_kwargs: dict[str, object] = {
        "initial_cash": default_config.initial_cash,
        "top_n": default_config.top_n,
        "selection_mode": default_config.selection_mode,
        "score_source": default_config.score_source,
        "lot_size": default_config.lot_size,
        "max_group_positions": default_config.max_group_positions,
        "lookback_momentum": default_config.lookback_momentum,
        "lookback_mean_reversion": default_config.lookback_mean_reversion,
        "lookback_volatility": default_config.lookback_volatility,
        "rolling_risk_window": default_config.rolling_risk_window,
        "execution_delay_days": default_config.execution_delay_days,
        "max_allowed_drawdown": default_config.max_allowed_drawdown,
        "max_allowed_daily_var": default_config.max_allowed_daily_var,
        "min_allowed_rolling_return": default_config.min_allowed_rolling_return,
        "min_allowed_information_ratio": default_config.min_allowed_information_ratio,
        "min_allowed_fill_rate": default_config.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": default_config.min_allowed_execution_price_coverage,
        "min_allowed_factor_score_coverage": default_config.min_allowed_factor_score_coverage,
        "max_allowed_market_constraint_rate": default_config.max_allowed_market_constraint_rate,
        "max_allowed_position_weight": default_config.max_allowed_position_weight,
        "max_allowed_group_weight": default_config.max_allowed_group_weight,
        "max_allowed_attribution_residual": default_config.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": default_config.max_allowed_factor_correlation,
        "max_allowed_rebalance_changes": default_config.max_allowed_rebalance_changes,
        "min_allowed_holding_days": default_config.min_allowed_holding_days,
        "rebalance_every_n_days": default_config.rebalance_every_n_days,
        "commission_rate": default_config.commission_rate,
        "buy_commission_rate": default_config.buy_commission_rate,
        "sell_commission_rate": default_config.sell_commission_rate,
        "slippage_rate": default_config.slippage_rate,
        "market_impact_coefficient": default_config.market_impact_coefficient,
        "market_impact_exponent": default_config.market_impact_exponent,
        "stamp_duty_rate": default_config.stamp_duty_rate,
        "min_commission": default_config.min_commission,
        "transfer_fee_rate": default_config.transfer_fee_rate,
        "target_cash_weight": default_config.target_cash_weight,
        "max_position_weight": default_config.max_position_weight,
        "limit_up_down_rate": default_config.limit_up_down_rate,
        "st_limit_up_down_rate": default_config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": default_config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": default_config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": default_config.infer_limit_rate_by_symbol,
        "max_volume_participation": default_config.max_volume_participation,
        "infer_limit_flags": default_config.infer_limit_flags,
        "forward_fill_suspended_bars": default_config.forward_fill_suspended_bars,
        "price_field": default_config.price_field,
        "execution_price_field": default_config.execution_price_field,
        "start_date": default_config.start_date,
        "end_date": default_config.end_date,
        "output_dir": default_config.output_dir,
        "symbol_name_csv": default_config.symbol_name_csv,
        "stock_pool_csv": default_config.stock_pool_csv,
        "symbol_group_csv": default_config.symbol_group_csv,
        "factor_score_csv": default_config.factor_score_csv,
        "factor_weights": default_config.factor_weights.copy(),
    }

    has_explicit_output_dir = False
    if args.config:
        config_overrides = load_config_overrides_from_toml(args.config)
        has_explicit_output_dir = "output_dir" in config_overrides
        config_kwargs.update(config_overrides)

    cli_overrides = _cli_config_overrides(args)
    for key, value in cli_overrides.items():
        if value is not None:
            config_kwargs[key] = value

    if args.output_dir is not None:
        config_kwargs["output_dir"] = Path(args.output_dir)
        has_explicit_output_dir = True

    if args.stock_pool_csv is not None:
        config_kwargs["stock_pool_csv"] = Path(args.stock_pool_csv)

    if args.symbol_group_csv is not None:
        config_kwargs["symbol_group_csv"] = Path(args.symbol_group_csv)

    factor_score_csv = getattr(args, "factor_score_csv", None)
    if factor_score_csv is not None:
        config_kwargs["factor_score_csv"] = Path(factor_score_csv)

    if args.factor_weight:
        factor_weights = cast(dict[str, float], config_kwargs["factor_weights"]).copy()
        factor_weights.update(_parse_factor_weight_overrides(args.factor_weight))
        config_kwargs["factor_weights"] = factor_weights

    if not has_explicit_output_dir:
        config_kwargs["output_dir"] = _build_default_run_output_dir(config_kwargs)

    return BacktestConfig.from_dict(config_kwargs)


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


def _cli_config_overrides(args: argparse.Namespace) -> dict[str, object | None]:
    return {
        "initial_cash": args.initial_cash,
        "top_n": args.top_n,
        "selection_mode": getattr(args, "selection_mode", None),
        "score_source": getattr(args, "score_source", None),
        "lot_size": args.lot_size,
        "max_group_positions": args.max_group_positions,
        "lookback_momentum": args.lookback_momentum,
        "lookback_mean_reversion": args.lookback_mean_reversion,
        "lookback_volatility": args.lookback_volatility,
        "rolling_risk_window": args.rolling_risk_window,
        "execution_delay_days": args.execution_delay_days,
        "max_allowed_drawdown": args.max_allowed_drawdown,
        "max_allowed_daily_var": getattr(args, "max_allowed_daily_var", None),
        "min_allowed_rolling_return": args.min_allowed_rolling_return,
        "min_allowed_information_ratio": getattr(args, "min_allowed_information_ratio", None),
        "min_allowed_fill_rate": args.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": getattr(args, "min_allowed_execution_price_coverage", None),
        "min_allowed_factor_score_coverage": getattr(args, "min_allowed_factor_score_coverage", None),
        "max_allowed_market_constraint_rate": getattr(args, "max_allowed_market_constraint_rate", None),
        "max_allowed_position_weight": args.max_allowed_position_weight,
        "max_allowed_group_weight": getattr(args, "max_allowed_group_weight", None),
        "max_allowed_attribution_residual": args.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": getattr(args, "max_allowed_factor_correlation", None),
        "max_allowed_rebalance_changes": getattr(args, "max_allowed_rebalance_changes", None),
        "min_allowed_holding_days": getattr(args, "min_allowed_holding_days", None),
        "rebalance_every_n_days": args.rebalance_days,
        "commission_rate": args.commission_rate,
        "buy_commission_rate": args.buy_commission_rate,
        "sell_commission_rate": args.sell_commission_rate,
        "slippage_rate": args.slippage_rate,
        "market_impact_coefficient": getattr(args, "market_impact_coefficient", None),
        "market_impact_exponent": getattr(args, "market_impact_exponent", None),
        "stamp_duty_rate": args.stamp_duty_rate,
        "min_commission": args.min_commission,
        "transfer_fee_rate": args.transfer_fee_rate,
        "target_cash_weight": args.target_cash_weight,
        "max_position_weight": args.max_position_weight,
        "limit_up_down_rate": args.limit_up_down_rate,
        "st_limit_up_down_rate": args.st_limit_up_down_rate,
        "growth_limit_up_down_rate": args.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": args.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": True if args.infer_limit_rate_by_symbol else None,
        "max_volume_participation": args.max_volume_participation,
        "infer_limit_flags": True if args.infer_limit_flags else None,
        "forward_fill_suspended_bars": True if args.forward_fill_suspended_bars else None,
        "price_field": args.price_field,
        "execution_price_field": args.execution_price_field,
        "start_date": _parse_cli_date(args.start_date, "start_date"),
        "end_date": _parse_cli_date(args.end_date, "end_date"),
    }


def _build_config_sources(
    args: argparse.Namespace,
    *,
    sweep_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    toml_overrides = load_config_overrides_from_toml(args.config) if args.config else {}
    cli_overrides = {
        key
        for key, value in _cli_config_overrides(args).items()
        if value is not None
    }
    if args.output_dir is not None:
        cli_overrides.add("output_dir")
    if args.stock_pool_csv is not None:
        cli_overrides.add("stock_pool_csv")
    if args.symbol_group_csv is not None:
        cli_overrides.add("symbol_group_csv")
    if getattr(args, "factor_score_csv", None) is not None:
        cli_overrides.add("factor_score_csv")
    if args.factor_weight:
        cli_overrides.add("factor_weights")

    field_sources: dict[str, str] = {}
    field_names = sorted(set(BacktestConfig().to_dict().keys()) | set(toml_overrides) | cli_overrides)
    for field_name in field_names:
        if sweep_overrides and field_name in sweep_overrides:
            field_sources[field_name] = "sweep_override"
        elif field_name in cli_overrides:
            field_sources[field_name] = "cli"
        elif field_name in toml_overrides:
            field_sources[field_name] = "toml"
        else:
            field_sources[field_name] = "default"
    if args.output_dir is None and "output_dir" not in toml_overrides:
        field_sources["output_dir"] = "derived_default"
    return {
        "config_file": args.config,
        "field_sources": field_sources,
    }


def _parse_cli_date(raw_value: str | None, field_name: str) -> date | None:
    if raw_value in ("", None):
        return None
    value = str(raw_value)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format.") from exc


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


def _health_aware_rank_key(
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


def _build_input_metadata(
    args: argparse.Namespace,
    config: BacktestConfig,
) -> dict[str, str | bool | None]:
    return {
        "demo": bool(args.demo),
        "csv": args.csv,
        "benchmark_csv": args.benchmark_csv,
        "stock_pool_csv": None if config.stock_pool_csv is None else str(config.stock_pool_csv),
        "symbol_group_csv": None if config.symbol_group_csv is None else str(config.symbol_group_csv),
        "factor_score_csv": None if config.factor_score_csv is None else str(config.factor_score_csv),
        "config": args.config,
        "sweep": bool(args.sweep),
    }


def _build_config_from_mapping(config_kwargs: Mapping[str, object]) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=cast(float, config_kwargs["initial_cash"]),
        top_n=cast(int, config_kwargs["top_n"]),
        selection_mode=cast(str, config_kwargs["selection_mode"]),
        score_source=cast(str, config_kwargs["score_source"]),
        lot_size=cast(int, config_kwargs["lot_size"]),
        max_group_positions=cast(int | None, config_kwargs["max_group_positions"]),
        lookback_momentum=cast(int, config_kwargs["lookback_momentum"]),
        lookback_mean_reversion=cast(int, config_kwargs["lookback_mean_reversion"]),
        lookback_volatility=cast(int, config_kwargs["lookback_volatility"]),
        rolling_risk_window=cast(int, config_kwargs["rolling_risk_window"]),
        execution_delay_days=cast(int, config_kwargs["execution_delay_days"]),
        max_allowed_drawdown=cast(float, config_kwargs["max_allowed_drawdown"]),
        max_allowed_daily_var=cast(float, config_kwargs["max_allowed_daily_var"]),
        min_allowed_rolling_return=cast(float, config_kwargs["min_allowed_rolling_return"]),
        min_allowed_information_ratio=cast(float, config_kwargs["min_allowed_information_ratio"]),
        min_allowed_fill_rate=cast(float, config_kwargs["min_allowed_fill_rate"]),
        min_allowed_execution_price_coverage=cast(float, config_kwargs["min_allowed_execution_price_coverage"]),
        min_allowed_factor_score_coverage=cast(float, config_kwargs["min_allowed_factor_score_coverage"]),
        max_allowed_market_constraint_rate=cast(float, config_kwargs["max_allowed_market_constraint_rate"]),
        max_allowed_position_weight=cast(float, config_kwargs["max_allowed_position_weight"]),
        max_allowed_group_weight=cast(float, config_kwargs["max_allowed_group_weight"]),
        max_allowed_attribution_residual=cast(float, config_kwargs["max_allowed_attribution_residual"]),
        max_allowed_factor_correlation=cast(float, config_kwargs["max_allowed_factor_correlation"]),
        max_allowed_rebalance_changes=cast(float, config_kwargs["max_allowed_rebalance_changes"]),
        min_allowed_holding_days=cast(float, config_kwargs["min_allowed_holding_days"]),
        rebalance_every_n_days=cast(int, config_kwargs["rebalance_every_n_days"]),
        commission_rate=cast(float, config_kwargs["commission_rate"]),
        buy_commission_rate=cast(float | None, config_kwargs["buy_commission_rate"]),
        sell_commission_rate=cast(float | None, config_kwargs["sell_commission_rate"]),
        slippage_rate=cast(float, config_kwargs["slippage_rate"]),
        market_impact_coefficient=cast(float, config_kwargs["market_impact_coefficient"]),
        market_impact_exponent=cast(float, config_kwargs["market_impact_exponent"]),
        stamp_duty_rate=cast(float, config_kwargs["stamp_duty_rate"]),
        min_commission=cast(float, config_kwargs["min_commission"]),
        transfer_fee_rate=cast(float, config_kwargs["transfer_fee_rate"]),
        target_cash_weight=cast(float, config_kwargs["target_cash_weight"]),
        max_position_weight=cast(float, config_kwargs["max_position_weight"]),
        limit_up_down_rate=cast(float, config_kwargs["limit_up_down_rate"]),
        st_limit_up_down_rate=cast(float, config_kwargs["st_limit_up_down_rate"]),
        growth_limit_up_down_rate=cast(float, config_kwargs["growth_limit_up_down_rate"]),
        bse_limit_up_down_rate=cast(float, config_kwargs["bse_limit_up_down_rate"]),
        infer_limit_rate_by_symbol=cast(bool, config_kwargs["infer_limit_rate_by_symbol"]),
        max_volume_participation=cast(float, config_kwargs["max_volume_participation"]),
        infer_limit_flags=cast(bool, config_kwargs["infer_limit_flags"]),
        forward_fill_suspended_bars=cast(bool, config_kwargs["forward_fill_suspended_bars"]),
        price_field=cast(str, config_kwargs["price_field"]),
        execution_price_field=cast(str | None, config_kwargs["execution_price_field"]),
        start_date=cast(date | None, config_kwargs["start_date"]),
        end_date=cast(date | None, config_kwargs["end_date"]),
        output_dir=cast(Path, config_kwargs["output_dir"]),
        symbol_name_csv=cast(Path | None, config_kwargs["symbol_name_csv"]),
        stock_pool_csv=cast(Path | None, config_kwargs["stock_pool_csv"]),
        symbol_group_csv=cast(Path | None, config_kwargs["symbol_group_csv"]),
        factor_score_csv=cast(Path | None, config_kwargs["factor_score_csv"]),
        factor_weights=cast(dict[str, float], config_kwargs["factor_weights"]).copy(),
    )


def _build_default_run_output_dir(config_kwargs: Mapping[str, object]) -> Path:
    timestamp = os.environ.get("MYFINANCES_RUN_TIMESTAMP")
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("output") / "runs" / f"{timestamp}-{_config_hash(config_kwargs)}"


def _config_hash(config_kwargs: Mapping[str, object]) -> str:
    payload = {
        key: _jsonable_config_value(value)
        for key, value in sorted(config_kwargs.items())
        if key != "output_dir"
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:10]


def _jsonable_config_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _jsonable_config_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _config_to_kwargs(config: BacktestConfig) -> dict[str, object]:
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
        "max_allowed_market_constraint_rate": config.max_allowed_market_constraint_rate,
        "max_allowed_position_weight": config.max_allowed_position_weight,
        "max_allowed_group_weight": config.max_allowed_group_weight,
        "max_allowed_attribution_residual": config.max_allowed_attribution_residual,
        "max_allowed_factor_correlation": config.max_allowed_factor_correlation,
        "max_allowed_rebalance_changes": config.max_allowed_rebalance_changes,
        "min_allowed_holding_days": config.min_allowed_holding_days,
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
        "limit_up_down_rate": config.limit_up_down_rate,
        "st_limit_up_down_rate": config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": config.infer_limit_rate_by_symbol,
        "max_volume_participation": config.max_volume_participation,
        "infer_limit_flags": config.infer_limit_flags,
        "forward_fill_suspended_bars": config.forward_fill_suspended_bars,
        "price_field": config.price_field,
        "execution_price_field": config.execution_price_field,
        "start_date": config.start_date,
        "end_date": config.end_date,
        "output_dir": config.output_dir,
        "symbol_name_csv": config.symbol_name_csv,
        "stock_pool_csv": config.stock_pool_csv,
        "symbol_group_csv": config.symbol_group_csv,
        "factor_score_csv": config.factor_score_csv,
        "factor_weights": config.factor_weights.copy(),
    }


if __name__ == "__main__":
    sys.exit(main())
