from __future__ import annotations

import csv
from pathlib import Path

from . import config
from .models import BacktestMetrics, EquityPoint


def print_summary(curve: list[EquityPoint], metrics: BacktestMetrics) -> None:
    print("=" * 60)
    print("Python Quant Backtest Summary")
    print(f"Periods: {len(curve)}")
    print(f"Start equity: {config.INITIAL_CASH:,.2f}")
    print(f"End equity:   {curve[-1].equity:,.2f}")
    print(f"Total return: {metrics.total_return:.2%}")
    print(f"Annualized:   {metrics.annualized_return:.2%}")
    print(f"Max drawdown: {metrics.max_drawdown:.2%}")
    print(f"Volatility:   {metrics.volatility:.2%}")
    print(f"Sharpe:       {metrics.sharpe:.3f}")
    print("=" * 60)


def save_equity_curve(curve: list[EquityPoint], output_dir: Path | None = None) -> Path:
    target_dir = output_dir or config.OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "equity_curve.csv"

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "equity"])
        for point in curve:
            writer.writerow([point.date, f"{point.equity:.2f}"])

    return target_path
