from __future__ import annotations

import argparse
from pathlib import Path

from .backtest import run_backtest
from .config import BacktestConfig, load_config_overrides_from_toml
from .data_loader import load_benchmark_bars_from_csv, load_price_bars_from_csv
from .reporting import (
    print_summary,
    save_equity_curve,
    save_performance_summary,
    save_performance_summary_json,
    save_run_manifest,
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
    parser.add_argument(
        "--config",
        type=str,
        help="Optional TOML config file. Values in the CLI override the file.",
    )
    parser.add_argument("--output-dir", type=str)
    parser.add_argument(
        "--price-field",
        choices=["auto", "close", "adjusted_close"],
    )
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--rebalance-days", type=int)
    parser.add_argument("--initial-cash", type=float)
    parser.add_argument("--commission-rate", type=float)
    parser.add_argument("--slippage-rate", type=float)
    parser.add_argument("--stamp-duty-rate", type=float)
    parser.add_argument("--lookback-momentum", type=int)
    parser.add_argument("--lookback-mean-reversion", type=int)
    parser.add_argument("--lookback-volatility", type=int)
    parser.add_argument(
        "--factor-weight",
        action="append",
        help="Override a factor weight with name=value. Can be provided multiple times.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    backtest_config = _build_backtest_config(args)

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
    summary_json_path = save_performance_summary_json(
        result.metrics,
        backtest_config.output_dir,
    )
    manifest_path = save_run_manifest(
        output_dir=backtest_config.output_dir,
        config=backtest_config,
        inputs={
            "demo": bool(args.demo),
            "csv": args.csv,
            "benchmark_csv": args.benchmark_csv,
            "config": args.config,
        },
        artifacts={
            "equity_curve_csv": equity_path,
            "rebalance_log_csv": rebalance_path,
            "performance_summary_csv": summary_path,
            "performance_summary_json": summary_json_path,
        },
        metrics=result.metrics,
    )
    print(f"Equity curve saved to: {equity_path}")
    print(f"Rebalance log saved to: {rebalance_path}")
    print(f"Performance summary saved to: {summary_path}")
    print(f"Performance summary JSON saved to: {summary_json_path}")
    print(f"Run manifest saved to: {manifest_path}")


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
        factor_weights = dict(config_kwargs["factor_weights"])
        factor_weights.update(_parse_factor_weight_overrides(args.factor_weight))
        config_kwargs["factor_weights"] = factor_weights

    return BacktestConfig(**config_kwargs)


def _parse_factor_weight_overrides(entries: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(
                f"Invalid factor weight '{entry}'. Use the format factor_name=value."
            )
        name, raw_value = entry.split("=", 1)
        factor_name = name.strip()
        if not factor_name:
            raise ValueError("Factor weight name cannot be empty.")
        parsed[factor_name] = float(raw_value.strip())
    return parsed


if __name__ == "__main__":
    main()
