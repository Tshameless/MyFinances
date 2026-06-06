from __future__ import annotations

import csv
from pathlib import Path

from .config import BacktestConfig
from .models import BacktestMetrics, EquityPoint, RebalanceRecord


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
    print("=" * 60)


def save_equity_curve(curve: list[EquityPoint], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "equity_curve.csv"

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "equity", "daily_return", "holdings"])
        for point in curve:
            writer.writerow(
                [
                    point.date.isoformat(),
                    f"{point.equity:.2f}",
                    f"{point.daily_return:.8f}",
                    "|".join(point.holdings),
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
