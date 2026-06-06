from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import run_backtest
from .config import BacktestConfig, OUTPUT_DIR
from .data_loader import load_benchmark_bars_from_csv, load_price_bars_from_csv
from .reporting import (
    print_summary,
    save_equity_curve,
    save_performance_summary,
    save_rebalance_log,
)
from .sample_data import generate_demo_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the MyFinances Python quant backtester."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use built-in demo data instead of a CSV file.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help=(
            "Path to a CSV file with columns: date,symbol,close and optional "
            "adjusted_close,volume,tradable,can_buy,can_sell"
        ),
    )
    parser.add_argument(
        "--benchmark-csv",
        type=str,
        help="Optional benchmark CSV with columns: date,close and optional adjusted_close,symbol",
    )
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    parser.add_argument(
        "--price-field",
        choices=["auto", "close", "adjusted_close"],
        default="auto",
    )
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--rebalance-days", type=int, default=5)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.0003)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--lookback-momentum", type=int, default=20)
    parser.add_argument("--lookback-mean-reversion", type=int, default=5)
    parser.add_argument("--lookback-volatility", type=int, default=20)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    backtest_config = BacktestConfig(
        initial_cash=args.initial_cash,
        top_n=args.top_n,
        rebalance_every_n_days=args.rebalance_days,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        price_field=args.price_field,
        lookback_momentum=args.lookback_momentum,
        lookback_mean_reversion=args.lookback_mean_reversion,
        lookback_volatility=args.lookback_volatility,
        output_dir=Path(args.output_dir),
    )

    if args.demo:
        bars = generate_demo_bars()
    elif args.csv:
        bars = load_price_bars_from_csv(args.csv)
    else:
        parser.error("Use --demo or provide --csv <path>.")
        return

    benchmark_bars = None
    if args.benchmark_csv:
        benchmark_bars = load_benchmark_bars_from_csv(args.benchmark_csv)

    result = run_backtest(bars, backtest_config, benchmark_bars=benchmark_bars)
    print_summary(
        result.equity_curve,
        result.rebalance_records,
        result.metrics,
        backtest_config,
    )
    equity_path = save_equity_curve(
        result.equity_curve,
        backtest_config.output_dir,
        result.benchmark_curve,
    )
    rebalance_path = save_rebalance_log(result.rebalance_records, backtest_config.output_dir)
    summary_path = save_performance_summary(result.metrics, backtest_config.output_dir)
    print(f"Equity curve saved to: {equity_path}")
    print(f"Rebalance log saved to: {rebalance_path}")
    print(f"Performance summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
