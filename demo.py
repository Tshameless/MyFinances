"""
Demo 模式 — 使用模拟数据演示完整回测流程
==========================================
用于网络受限环境或快速验证策略逻辑。
用法：python demo.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ["PYTHONIOENCODING"] = "utf-8"

import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel

console = Console(force_terminal=False)


def generate_demo_data(
    n_stocks: int = 50,
    n_days: int = 1260,  # ~5 years
    start_date: str = "2021-01-04",
    seed: int = 42,
) -> tuple[dict, pd.DataFrame, dict, pd.DataFrame]:
    """
    生成逼真的模拟数据：
    - price_dict: {code: DataFrame(date/o/h/l/c/v)}
    - df_snapshot: 财务快照
    - roe_dict: ROE数据
    - bench_df: 基准指数
    """
    np.random.seed(seed)

    # 生成交易日
    dates = pd.bdate_range(start=start_date, periods=n_days, freq="B")
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]

    # --- 个股价格数据 ---
    price_dict = {}
    for i in range(n_stocks):
        code = f"sh{600000 + i}" if i < 30 else f"sz{1000 + i}"
        mu = np.random.uniform(0.0001, 0.0008)  # 平均日收益
        sigma = np.random.uniform(0.015, 0.035)  # 日波动
        returns = np.random.normal(mu, sigma, n_days)

        # 加入一定程度的共动性（beta）
        market_returns = np.random.normal(0.0004, 0.012, n_days)
        beta = np.random.uniform(0.5, 1.5)
        returns = returns * 0.5 + market_returns * beta * 0.5

        prices = 100 * np.exp(np.cumsum(returns))
        # 随机震荡
        prices += np.random.normal(0, 0.5, n_days)
        prices = np.maximum(prices, 1.0)

        df = pd.DataFrame({
            "date": dates,
            "open": prices * (1 + np.random.normal(0, 0.003, n_days)),
            "high": prices * (1 + np.abs(np.random.normal(0, 0.01, n_days))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.01, n_days))),
            "close": prices,
            "volume": np.random.randint(1000000, 50000000, n_days),
            "amount": prices * np.random.randint(1000000, 50000000, n_days),
        })
        df["high"] = df[["open", "close", "high"]].max(axis=1)
        df["low"] = df[["open", "close", "low"]].min(axis=1)
        price_dict[code] = df

    # --- 财务快照 ---
    snapshot_rows = []
    for i, code in enumerate(price_dict.keys()):
        raw = code.replace("sh", "").replace("sz", "")
        snapshot_rows.append({
            "code": code,
            "name": f"模拟股票{raw}",
            "pe_ttm": max(3, np.random.lognormal(2.8, 0.5)),
            "pb": max(0.3, np.random.lognormal(0.5, 0.4)),
            "market_cap": np.random.lognormal(23, 1.5),
            "float_cap": np.random.lognormal(22, 1.5),
            "ps_ttm": max(0.1, np.random.lognormal(0.8, 0.6)),
            "is_st": False,
            "date": "2026-01-01",
        })
    df_snapshot = pd.DataFrame(snapshot_rows)

    # --- ROE ---
    roe_dict = {}
    for code in price_dict.keys():
        roe_dict[code] = round(np.random.uniform(2, 30), 2)

    # --- 基准指数 ---
    bench_returns = np.random.normal(0.0003, 0.012, n_days)
    # 让基准跑输策略（策略有alpha）
    bench_prices = 100 * np.exp(np.cumsum(bench_returns))
    bench_df = pd.DataFrame({
        "date": dates,
        "close": bench_prices,
    })

    return price_dict, df_snapshot, roe_dict, bench_df


def main():
    console.print(Panel.fit(
        "[bold cyan][DEMO] A股多因子选股量化系统[/]\n"
        f"模式: 模拟数据 · 持仓数: 30 · 月度调仓 · 2021-2026",
        border_style="green",
    ))

    # -------------------------------------------------
    # 阶段一：生成模拟数据
    # -------------------------------------------------
    console.print("\n[bold][FETCH] 阶段一：生成模拟数据[/]")

    import config
    price_dict, df_snapshot, roe_dict, bench_df = generate_demo_data(
        n_stocks=50, n_days=1260, start_date=config.BACKTEST_START
    )

    console.print(f"  数据就绪: {len(price_dict)} 只股票, {len(df_snapshot)} 只快照, "
                  f"{len(roe_dict)} 只 ROE, 基准: {len(bench_df)} 天")

    # -------------------------------------------------
    # 阶段二：因子 + 回测
    # -------------------------------------------------
    console.print("\n[bold][CALC] 阶段二：因子计算 & 回测[/]")

    from factors.calculator import FactorCalculator
    from backtest.engine import BacktestEngine

    factor_calc = FactorCalculator(config.FACTOR_WEIGHTS)

    engine = BacktestEngine(
        factor_calc=factor_calc,
        price_dict=price_dict,
        df_snapshot=df_snapshot,
        roe_dict=roe_dict,
        start_date=config.BACKTEST_START,
        end_date=config.BACKTEST_END,
        initial_cash=config.INITIAL_CASH,
        top_n=config.TOP_N_STOCKS,
        rebalance_freq=config.REBALANCE_FREQ,
        rebalance_day=config.REBALANCE_DAY,
        commission_rate=config.COMMISSION_RATE,
        stamp_duty_rate=config.STAMP_DUTY_RATE,
        slippage_rate=config.SLIPPAGE_RATE,
        max_position_weight=config.MAX_POSITION_WEIGHT,
        stop_loss_ratio=0,  # demo模式下关闭止损
        exclude_st=False,
        exclude_new_ipo=False,
    )

    result_df = engine.run()
    engine.print_summary()

    # -------------------------------------------------
    # 阶段三：报告
    # -------------------------------------------------
    console.print("\n[bold][CHART] 阶段三：生成可视化报告[/]")

    from report.generator import ReportGenerator

    report = ReportGenerator(output_dir="output")
    metrics = engine.get_performance_metrics()
    report_path = report.generate(
        result_df=result_df,
        metrics=metrics,
        benchmark_df=bench_df,
        output_name="backtest_report.html",
    )

    console.print(Panel.fit(
        f"[bold green][OK] 回测完成！[/]\n\n"
        f"[FILE] 报告: [cyan]{report_path}[/]\n"
        f"[TIP] 修改 [yellow]config.py[/] 调整策略参数后再次运行。",
        border_style="green",
    ))

    return report_path


if __name__ == "__main__":
    main()
