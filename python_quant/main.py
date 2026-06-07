from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
from typing import Mapping, cast

from .backtest import run_backtest
from .config import (
    BacktestConfig,
    load_config_overrides_from_toml,
    load_sweep_overrides_from_toml,
)
from .data_loader import load_benchmark_bars_from_csv, load_price_bars_from_csv
from .models import BacktestResult, PriceBar
from .reporting import (
    print_summary,
    save_batch_chart_svg,
    save_batch_heatmap_svg,
    save_batch_rankings,
    save_batch_report_html,
    save_batch_summary,
    save_equity_chart_svg,
    save_equity_curve,
    save_performance_summary,
    save_performance_summary_json,
    save_rebalance_log,
    save_run_manifest,
    save_single_run_report_html,
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
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Run a parameter sweep using the [sweep] section in the TOML config.",
    )
    parser.add_argument(
        "--rank-by",
        type=str,
        default="annualized_return",
        help="Metric used to rank sweep results. Default: annualized_return",
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
    bars = _load_bars(args, parser)
    benchmark_bars = _load_benchmark_bars(args)

    if args.sweep:
        if not args.config:
            parser.error("--sweep requires --config with a [sweep] section.")
            return
        _run_sweep(args, bars, benchmark_bars)
        return

    backtest_config = _build_backtest_config(args)
    result = run_backtest(bars, backtest_config, benchmark_bars=benchmark_bars)
    artifact_paths = _persist_run_outputs(
        output_dir=backtest_config.output_dir,
        result=result,
        config=backtest_config,
        inputs=_build_input_metadata(args),
        print_console=True,
    )
    print(f"Equity curve saved to: {artifact_paths['equity_curve_csv']}")
    print(f"Rebalance log saved to: {artifact_paths['rebalance_log_csv']}")
    print(f"Performance summary saved to: {artifact_paths['performance_summary_csv']}")
    print(f"Performance summary JSON saved to: {artifact_paths['performance_summary_json']}")
    print(f"Run manifest saved to: {artifact_paths['run_manifest_json']}")
    print(f"Equity chart saved to: {artifact_paths['equity_curve_svg']}")
    print(f"HTML report saved to: {artifact_paths['report_html']}")


def _run_sweep(
    args: argparse.Namespace,
    bars: list[PriceBar],
    benchmark_bars: list[PriceBar] | None,
) -> None:
    base_config = _build_backtest_config(args)
    sweep_overrides = load_sweep_overrides_from_toml(args.config)
    if not sweep_overrides:
        raise ValueError("No [sweep] section found in config file.")

    batch_output_dir = base_config.output_dir / "batch_runs"
    rows: list[dict[str, object]] = []
    combinations = _expand_sweep_combinations(sweep_overrides)

    for run_number, override_values in enumerate(combinations, start=1):
        run_id = f"run_{run_number:03d}"
        run_output_dir = batch_output_dir / run_id
        config_kwargs = _config_to_kwargs(base_config)
        config_kwargs.update(override_values)
        config_kwargs["output_dir"] = run_output_dir
        run_config = _build_config_from_mapping(config_kwargs)
        result = run_backtest(bars, run_config, benchmark_bars=benchmark_bars)
        artifact_paths = _persist_run_outputs(
            output_dir=run_output_dir,
            result=result,
            config=run_config,
            inputs=_build_input_metadata(args),
            print_console=False,
        )
        rows.append(
            _build_batch_row(
                run_id=run_id,
                config=run_config,
                overrides=override_values,
                result=result,
                artifact_paths=artifact_paths,
            )
        )

    summary_csv_path, summary_json_path = save_batch_summary(rows, batch_output_dir)
    leaderboard_csv_path, leaderboard_json_path, best_run_path = save_batch_rankings(
        rows,
        batch_output_dir,
        rank_by=args.rank_by,
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
    }
    if heatmap_path is not None:
        batch_artifacts["batch_heatmap_svg"] = heatmap_path
    batch_report_path = save_batch_report_html(
        output_dir=batch_output_dir,
        rows=rows,
        rank_by=args.rank_by,
        artifacts=batch_artifacts,
    )
    print(f"Batch sweep completed: {len(rows)} runs")
    print(f"Batch summary saved to: {summary_csv_path}")
    print(f"Batch summary JSON saved to: {summary_json_path}")
    print(f"Batch leaderboard saved to: {leaderboard_csv_path}")
    print(f"Batch leaderboard JSON saved to: {leaderboard_json_path}")
    print(f"Best run summary saved to: {best_run_path}")
    print(f"Batch chart saved to: {batch_chart_path}")
    if heatmap_path is not None:
        print(f"Batch heatmap saved to: {heatmap_path}")
    print(f"Batch HTML report saved to: {batch_report_path}")


def _load_bars(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[PriceBar]:
    if args.demo:
        return generate_demo_bars()
    if args.csv:
        return load_price_bars_from_csv(args.csv)
    parser.error("Use --demo or provide --csv <path>.")
    raise AssertionError("parser.error should have exited")


def _load_benchmark_bars(args: argparse.Namespace) -> list[PriceBar] | None:
    if args.benchmark_csv:
        return load_benchmark_bars_from_csv(args.benchmark_csv)
    return None


def _persist_run_outputs(
    *,
    output_dir: Path,
    result: BacktestResult,
    config: BacktestConfig,
    inputs: dict[str, str | bool | None],
    print_console: bool,
) -> dict[str, Path]:
    if print_console:
        print_summary(
            result.equity_curve,
            result.rebalance_records,
            result.metrics,
            config,
        )
    equity_path = save_equity_curve(
        result.equity_curve,
        output_dir,
        result.benchmark_curve,
    )
    rebalance_path = save_rebalance_log(result.rebalance_records, output_dir)
    summary_path = save_performance_summary(result.metrics, output_dir)
    summary_json_path = save_performance_summary_json(result.metrics, output_dir)
    equity_chart_path = save_equity_chart_svg(
        result.equity_curve,
        output_dir,
        result.benchmark_curve,
    )
    artifact_paths = {
        "equity_curve_csv": equity_path,
        "equity_curve_svg": equity_chart_path,
        "rebalance_log_csv": rebalance_path,
        "performance_summary_csv": summary_path,
        "performance_summary_json": summary_json_path,
    }
    manifest_path = save_run_manifest(
        output_dir=output_dir,
        config=config,
        inputs=inputs,
        artifacts=artifact_paths,
        metrics=result.metrics,
    )
    artifact_paths["run_manifest_json"] = manifest_path
    report_path = save_single_run_report_html(
        output_dir=output_dir,
        config=config,
        metrics=result.metrics,
        artifacts=artifact_paths,
    )
    artifact_paths["report_html"] = report_path
    return artifact_paths


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
        factor_weights = cast(dict[str, float], config_kwargs["factor_weights"]).copy()
        factor_weights.update(_parse_factor_weight_overrides(args.factor_weight))
        config_kwargs["factor_weights"] = factor_weights

    return _build_config_from_mapping(config_kwargs)


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
        "equity_curve_csv": str(artifact_paths["equity_curve_csv"]),
        "run_manifest_json": str(artifact_paths["run_manifest_json"]),
    }
    for key, value in overrides.items():
        row[f"param_{key}"] = value
    return row


def _build_input_metadata(args: argparse.Namespace) -> dict[str, str | bool | None]:
    return {
        "demo": bool(args.demo),
        "csv": args.csv,
        "benchmark_csv": args.benchmark_csv,
        "config": args.config,
        "sweep": bool(args.sweep),
    }


def _build_config_from_mapping(config_kwargs: Mapping[str, object]) -> BacktestConfig:
    return BacktestConfig(
        initial_cash=cast(float, config_kwargs["initial_cash"]),
        top_n=cast(int, config_kwargs["top_n"]),
        lookback_momentum=cast(int, config_kwargs["lookback_momentum"]),
        lookback_mean_reversion=cast(int, config_kwargs["lookback_mean_reversion"]),
        lookback_volatility=cast(int, config_kwargs["lookback_volatility"]),
        rebalance_every_n_days=cast(int, config_kwargs["rebalance_every_n_days"]),
        commission_rate=cast(float, config_kwargs["commission_rate"]),
        slippage_rate=cast(float, config_kwargs["slippage_rate"]),
        stamp_duty_rate=cast(float, config_kwargs["stamp_duty_rate"]),
        price_field=cast(str, config_kwargs["price_field"]),
        output_dir=cast(Path, config_kwargs["output_dir"]),
        factor_weights=cast(dict[str, float], config_kwargs["factor_weights"]).copy(),
    )


def _config_to_kwargs(config: BacktestConfig) -> dict[str, object]:
    return {
        "initial_cash": config.initial_cash,
        "top_n": config.top_n,
        "lookback_momentum": config.lookback_momentum,
        "lookback_mean_reversion": config.lookback_mean_reversion,
        "lookback_volatility": config.lookback_volatility,
        "rebalance_every_n_days": config.rebalance_every_n_days,
        "commission_rate": config.commission_rate,
        "slippage_rate": config.slippage_rate,
        "stamp_duty_rate": config.stamp_duty_rate,
        "price_field": config.price_field,
        "output_dir": config.output_dir,
        "factor_weights": config.factor_weights.copy(),
    }


if __name__ == "__main__":
    main()
