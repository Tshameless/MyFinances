from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from .backtest import run_backtest
from .cli_config import build_backtest_config, build_config_sources
from .console_output import print_single_run_artifacts
from .data_loader import (
    load_benchmark_bars_from_csv,
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
from .data_store import (
    import_benchmark_csv_to_sqlite,
    import_factor_scores_csv_to_sqlite,
    import_price_csv_to_sqlite,
    import_stock_pool_csv_to_sqlite,
    import_symbol_groups_csv_to_sqlite,
)
from .models import PriceBar
from .run_outputs import persist_run_outputs
from .sample_data import generate_demo_bars
from .trading_rules import apply_inferred_limit_flags
from .workflows import (
    build_input_metadata as _build_input_metadata,
)
from .workflows import (
    filter_bars_by_date_range as _filter_bars_by_date_range,
)
from .workflows import (
    load_factor_scores as _load_factor_scores,
)
from .workflows import (
    load_stock_pool as _load_stock_pool,
)
from .workflows import (
    load_symbol_groups as _load_symbol_groups,
)
from .workflows import (
    run_sweep,
    run_walk_forward,
    run_walk_forward_optimization,
)

logger = logging.getLogger(__name__)


def _configure_console_encoding() -> None:
    if os.name != "nt":
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = getattr(stream, "encoding", None)
        if callable(reconfigure) and encoding and encoding.lower() != "utf-8":
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except ValueError:
                # Some wrapped streams may reject reconfiguration; keep best-effort behavior.
                pass


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
        "--custom-factors-py",
        type=str,
        help="可选自定义因子脚本 Python 文件路径。其中的因子函数使用 @register_factor 注册后可用于回测。",
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
        "--import-data-to-sqlite",
        type=str,
        help="将提供的 CSV 输入导入 SQLite 数据库路径，然后退出。",
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
    parser.add_argument(
        "--allocation-model",
        choices=["equal_weight", "score_weighted", "max_sharpe", "min_variance"],
        help="持仓分配模型：equal_weight、score_weighted、max_sharpe 或 min_variance。",
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
        help="选择交易执行价格字段；不填时默认沿用 price_field。",
    )
    parser.add_argument(
        "--execution-delay-days",
        type=int,
        help="在信号日之后延迟 N 个对齐交易 bar 执行交易。",
    )
    parser.add_argument(
        "--execution-style",
        choices=["market", "twap"],
        help="执行风格；默认 market，twap 会把成交量参与率拆分到多个切片。",
    )
    parser.add_argument(
        "--twap-slices",
        type=int,
        help="启用 --execution-style twap 时使用的 TWAP 切片数量。",
    )
    parser.add_argument(
        "--max-allowed-rebalance-changes",
        type=float,
        help="策略健康闸门允许的平均每次调仓最大进入数加退出数。",
    )
    parser.add_argument(
        "--min-allowed-holding-days",
        type=float,
        help="策略健康闸门允许的最小平均已实现持有天数。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console_encoding()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        _run_with_args(args, parser)
    except (FileNotFoundError, ModuleNotFoundError, TypeError, ValueError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    return 0


def _handle_pre_run_commands(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> bool:
    if args.import_data_to_sqlite:
        imported = _import_data_to_sqlite(args, parser)
        for label, row_count in imported:
            print(f"Imported {row_count} {label} rows into SQLite: {args.import_data_to_sqlite}")
        return True

    if args.validate_csv:
        _validate_csv_inputs(args, parser)
        return True

    return False


def _filtered_benchmark_bars(
    args: argparse.Namespace,
    *,
    start_date: date | None,
    end_date: date | None,
) -> list[PriceBar] | None:
    benchmark_bars = _load_benchmark_bars(args)
    if benchmark_bars is None:
        return None
    return _filter_bars_by_date_range(
        benchmark_bars,
        start_date=start_date,
        end_date=end_date,
    )


def _prepare_run_context(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> tuple[
    object,
    list[PriceBar],
    list[PriceBar] | None,
    dict[date, set[str]] | None,
    dict[str, str] | None,
    dict[date, dict[str, float]] | None,
]:
    backtest_config = build_backtest_config(args)
    bars = _filter_bars_by_date_range(
        _load_bars(args, parser),
        start_date=backtest_config.start_date,
        end_date=backtest_config.end_date,
    )
    bars = apply_inferred_limit_flags(bars, backtest_config)
    benchmark_bars = _filtered_benchmark_bars(
        args,
        start_date=backtest_config.start_date,
        end_date=backtest_config.end_date,
    )
    stock_pool_by_date = _load_stock_pool(backtest_config)
    symbol_groups = _load_symbol_groups(backtest_config)
    factor_scores_by_date = _load_factor_scores(backtest_config)
    return (
        backtest_config,
        bars,
        benchmark_bars,
        stock_pool_by_date,
        symbol_groups,
        factor_scores_by_date,
    )


def _dispatch_workflow(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    backtest_config: object,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
) -> bool:
    if args.sweep:
        if not args.config:
            parser.error("--sweep 需要配合 --config 使用，且配置文件中必须包含 [sweep]。")
            return True
        run_sweep(
            args,
            bars,
            benchmark_bars,
            base_config=backtest_config,
            build_config_sources=build_config_sources,
        )
        return True

    if args.walk_forward:
        run_walk_forward(
            args,
            bars,
            benchmark_bars,
            base_config=backtest_config,
            build_config_sources=build_config_sources,
        )
        return True

    if args.walk_optimize:
        if not args.config:
            parser.error("--walk-optimize 需要配合 --config 使用，且配置文件中必须包含 [sweep]。")
            return True
        run_walk_forward_optimization(
            args,
            bars,
            benchmark_bars,
            base_config=backtest_config,
            build_config_sources=build_config_sources,
        )
        return True

    return False


def _run_single_backtest(
    args: argparse.Namespace,
    *,
    backtest_config: object,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
    stock_pool_by_date: dict[date, set[str]] | None,
    symbol_groups: dict[str, str] | None,
    factor_scores_by_date: dict[date, dict[str, float]] | None,
) -> None:
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
        config_sources=build_config_sources(args),
    )
    print_single_run_artifacts(artifact_paths)


def _run_with_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if _handle_pre_run_commands(args, parser):
        return

    (
        backtest_config,
        bars,
        benchmark_bars,
        stock_pool_by_date,
        symbol_groups,
        factor_scores_by_date,
    ) = _prepare_run_context(args, parser)

    if _dispatch_workflow(
        args,
        parser,
        backtest_config=backtest_config,
        bars=bars,
        benchmark_bars=benchmark_bars,
    ):
        return

    _run_single_backtest(
        args,
        backtest_config=backtest_config,
        bars=bars,
        benchmark_bars=benchmark_bars,
        stock_pool_by_date=stock_pool_by_date,
        symbol_groups=symbol_groups,
        factor_scores_by_date=factor_scores_by_date,
    )


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


def _import_data_to_sqlite(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[tuple[str, int]]:
    if not any(
        [
            args.csv,
            args.benchmark_csv,
            args.stock_pool_csv,
            args.factor_score_csv,
            args.symbol_group_csv,
        ]
    ):
        parser.error("--import-data-to-sqlite requires at least one CSV input.")
        raise AssertionError("parser.error should have exited")
    db_path = args.import_data_to_sqlite
    imported: list[tuple[str, int]] = []
    if args.csv:
        imported.append(("price", import_price_csv_to_sqlite(args.csv, db_path)))
    if args.benchmark_csv:
        imported.append(("benchmark", import_benchmark_csv_to_sqlite(args.benchmark_csv, db_path)))
    if args.stock_pool_csv:
        imported.append(("stock_pool", import_stock_pool_csv_to_sqlite(args.stock_pool_csv, db_path)))
    if args.factor_score_csv:
        imported.append(("factor_score", import_factor_scores_csv_to_sqlite(args.factor_score_csv, db_path)))
    if args.symbol_group_csv:
        imported.append(("symbol_group", import_symbol_groups_csv_to_sqlite(args.symbol_group_csv, db_path)))
    return imported


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


if __name__ == "__main__":
    sys.exit(main())
