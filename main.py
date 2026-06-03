"""
A股多因子选股量化系统 — 一键运行入口
========================================
用法：
    python main.py              # 完整流程：数据获取 → 回测 → 报告
    python main.py --skip-fetch # 跳过数据获取，使用缓存
    python main.py --top 20     # 持有 Top 20 股票

对新手友好：修改 config.py 中的参数即可定制策略。
"""

import argparse
import sys
import os
from pathlib import Path

# 修复 Windows 终端 GBK 编码问题
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
from data.fetcher import DataFetcher
from factors.calculator import FactorCalculator
from backtest.engine import BacktestEngine
from report.generator import ReportGenerator

console = Console(force_terminal=False)


def main():
    parser = argparse.ArgumentParser(description="A股多因子选股回测系统")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过数据获取，直接使用缓存")
    parser.add_argument("--top", type=int, default=None, help="持仓股票数量（覆盖 config.py）")
    parser.add_argument("--start", type=str, default=None, help="起始日期")
    parser.add_argument("--end", type=str, default=None, help="结束日期")
    args = parser.parse_args()

    # 参数覆盖
    top_n = args.top or config.TOP_N_STOCKS
    start_date = args.start or config.BACKTEST_START
    end_date = args.end or config.BACKTEST_END

    # 打印横幅
    console.print(Panel.fit(
        "[bold cyan]🚀 A 股多因子选股量化系统[/]\n"
        f"选股范围: {config.STOCK_UNIVERSE.upper()} · "
        f"持仓数: {top_n} · "
        f"调仓: {config.REBALANCE_FREQ} · "
        f"{start_date} → {end_date}",
        border_style="green",
    ))

    # ================================================================
    # 阶段一：数据获取
    # ================================================================
    console.print("\n[bold]📡 阶段一：数据获取[/]")

    fetcher = DataFetcher(
        cache_dir=config.DATA_CACHE_DIR,
        use_cache=config.USE_CACHE,
    )

    if not args.skip_fetch:
        # 1.1 成分股列表
        stock_codes = fetcher.get_stock_universe(config.STOCK_UNIVERSE)

        # 1.2 日线行情
        price_dict = fetcher.fetch_daily_prices(stock_codes, start_date, end_date)

        # 1.3 财务快照
        df_snapshot = fetcher.fetch_financial_snapshot()

        # 1.4 ROE
        roe_dict = fetcher.fetch_roe_data(stock_codes)

        # 1.5 基准指数
        console.print("[cyan]📡 获取基准指数数据...[/]")
        bench_df = fetcher.fetch_index_data(config.BENCHMARK_INDEX, start_date, end_date)
        if bench_df is None:
            console.print("[yellow]  ⚠ 基准指数数据获取失败，回测将不含基准对比[/]")
    else:
        console.print("[dim]使用缓存数据...[/]")
        stock_codes = fetcher.get_stock_universe(config.STOCK_UNIVERSE)
        price_dict = fetcher.fetch_daily_prices(stock_codes, start_date, end_date)
        df_snapshot = fetcher.fetch_financial_snapshot()
        roe_dict = fetcher.fetch_roe_data(stock_codes)
        bench_df = fetcher.fetch_index_data(config.BENCHMARK_INDEX, start_date, end_date)

    if not price_dict:
        console.print("[red]❌ 未获取到任何股票数据，请检查网络或缓存。[/]")
        return

    console.print(f"  数据就绪: {len(price_dict)} 只股票日线, {len(df_snapshot)} 只快照, "
                  f"{len(roe_dict)} 只 ROE")

    # ================================================================
    # 阶段二：因子计算 + 回测
    # ================================================================
    console.print("\n[bold]🧮 阶段二：因子计算 & 回测[/]")

    factor_calc = FactorCalculator(config.FACTOR_WEIGHTS)

    engine = BacktestEngine(
        factor_calc=factor_calc,
        price_dict=price_dict,
        df_snapshot=df_snapshot,
        roe_dict=roe_dict,
        start_date=start_date,
        end_date=end_date,
        initial_cash=config.INITIAL_CASH,
        top_n=top_n,
        rebalance_freq=config.REBALANCE_FREQ,
        rebalance_day=config.REBALANCE_DAY,
        commission_rate=config.COMMISSION_RATE,
        stamp_duty_rate=config.STAMP_DUTY_RATE,
        slippage_rate=config.SLIPPAGE_RATE,
        max_position_weight=config.MAX_POSITION_WEIGHT,
        stop_loss_ratio=config.STOP_LOSS_RATIO,
        exclude_st=config.EXCLUDE_ST,
        exclude_new_ipo=config.EXCLUDE_NEW_IPO,
    )

    result_df = engine.run()
    engine.print_summary()

    # ================================================================
    # 阶段三：生成报告
    # ================================================================
    console.print("\n[bold]📊 阶段三：生成可视化报告[/]")

    report = ReportGenerator(output_dir="output")
    metrics = engine.get_performance_metrics()
    report_path = report.generate(
        result_df=result_df,
        metrics=metrics,
        benchmark_df=bench_df,
        output_name="backtest_report.html",
    )

    # ================================================================
    # 完成
    # ================================================================
    console.print(Panel.fit(
        f"[bold green]✅ 回测完成！[/]\n\n"
        f"📄 报告: [cyan]{report_path}[/]\n"
        f"💡 修改 [yellow]config.py[/] 调整策略参数后再次运行。",
        border_style="green",
    ))

    return report_path


if __name__ == "__main__":
    main()
