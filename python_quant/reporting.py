from __future__ import annotations

import csv
from pathlib import Path

from .config import BacktestConfig
from .models import BacktestMetrics, BenchmarkPoint, EquityPoint, RebalanceRecord


def print_summary(
    curve: list[EquityPoint],
    rebalances: list[RebalanceRecord],
    metrics: BacktestMetrics,
    config: BacktestConfig,
) -> None:
    print("=" * 60)
    print("MyFinances Python Quant Backtest Summary")
    print(f"Periods: {metrics.periods}")
    print(f"Rebalances:   {len(rebalances)}")
    print(f"Start equity: {config.initial_cash:,.2f}")
    print(f"End equity:   {curve[-1].equity:,.2f}")
    print(f"Total return: {metrics.total_return:.2%}")
    print(f"Annualized:   {metrics.annualized_return:.2%}")
    print(f"Max drawdown: {metrics.max_drawdown:.2%}")
    print(f"Volatility:   {metrics.volatility:.2%}")
    print(f"Sharpe:       {metrics.sharpe:.3f}")
    print(f"Win rate:     {metrics.win_rate:.2%}")
    print(f"Avg turnover: {metrics.average_turnover:.2%}")
    print(f"Total cost:   {metrics.total_cost:,.2f}")
    if metrics.benchmark_total_return is not None:
        print(f"Benchmark:    {metrics.benchmark_total_return:.2%}")
        print(f"Excess return:{metrics.excess_return:.2%}")
        print(f"Info ratio:   {metrics.information_ratio:.3f}")
    print("=" * 60)


def save_equity_curve(
    curve: list[EquityPoint],
    output_dir: Path,
    benchmark_curve: list[BenchmarkPoint] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "equity_curve.csv"
    benchmark_by_date = {point.date: point for point in benchmark_curve or []}

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "equity",
                "daily_return",
                "holdings",
                "benchmark_equity",
                "benchmark_daily_return",
                "excess_daily_return",
            ]
        )
        for point in curve:
            benchmark_point = benchmark_by_date.get(point.date)
            benchmark_equity = ""
            benchmark_return = ""
            excess_daily_return = ""
            if benchmark_point is not None:
                benchmark_equity = f"{benchmark_point.equity:.2f}"
                benchmark_return = f"{benchmark_point.daily_return:.8f}"
                excess_daily_return = f"{point.daily_return - benchmark_point.daily_return:.8f}"
            writer.writerow(
                [
                    point.date.isoformat(),
                    f"{point.equity:.2f}",
                    f"{point.daily_return:.8f}",
                    "|".join(point.holdings),
                    benchmark_equity,
                    benchmark_return,
                    excess_daily_return,
                ]
            )

    return target_path


def save_rebalance_log(rebalances: list[RebalanceRecord], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "rebalance_log.csv"

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "holdings", "turnover", "cost"])
        for record in rebalances:
            writer.writerow(
                [
                    record.date.isoformat(),
                    "|".join(record.holdings),
                    f"{record.turnover:.8f}",
                    f"{record.cost:.2f}",
                ]
            )

    return target_path


def save_performance_summary(metrics: BacktestMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.csv"

    summary_items = [
        ("total_return", f"{metrics.total_return:.8f}"),
        ("annualized_return", f"{metrics.annualized_return:.8f}"),
        ("max_drawdown", f"{metrics.max_drawdown:.8f}"),
        ("volatility", f"{metrics.volatility:.8f}"),
        ("sharpe", f"{metrics.sharpe:.8f}"),
        ("win_rate", f"{metrics.win_rate:.8f}"),
        ("average_turnover", f"{metrics.average_turnover:.8f}"),
        ("total_cost", f"{metrics.total_cost:.2f}"),
        ("periods", str(metrics.periods)),
        (
            "benchmark_total_return",
            "" if metrics.benchmark_total_return is None else f"{metrics.benchmark_total_return:.8f}",
        ),
        (
            "benchmark_annualized_return",
            ""
            if metrics.benchmark_annualized_return is None
            else f"{metrics.benchmark_annualized_return:.8f}",
        ),
        ("excess_return", "" if metrics.excess_return is None else f"{metrics.excess_return:.8f}"),
        (
            "information_ratio",
            "" if metrics.information_ratio is None else f"{metrics.information_ratio:.8f}",
        ),
    ]

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(summary_items)

    return target_path
