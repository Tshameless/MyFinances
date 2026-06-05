from __future__ import annotations

import argparse

from .backtest import run_backtest
from .data_loader import load_price_bars_from_csv
from .reporting import print_summary, save_equity_curve
from .sample_data import generate_demo_bars


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Python quant research skeleton."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use built-in demo data instead of a CSV file.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Path to a CSV file with columns: date,symbol,close",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.demo:
        bars = generate_demo_bars()
    elif args.csv:
        bars = load_price_bars_from_csv(args.csv)
    else:
        parser.error("Use --demo or provide --csv <path>.")
        return

    curve, metrics = run_backtest(bars)
    print_summary(curve, metrics)
    output_path = save_equity_curve(curve)
    print(f"Equity curve saved to: {output_path}")


if __name__ == "__main__":
    main()
