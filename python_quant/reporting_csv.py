from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import cast

from .models import FactorScoreRecord, TradeAttemptRecord, TradeRecord

_HUMAN_READABLE_ENCODING = "utf-8-sig"


def save_trades_csv(
    trades: list[TradeRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
    format_money,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "trades.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("side"),
                display_label("shares"),
                display_label("price"),
                display_label("gross_value"),
                "成交金额展示 / gross_value_display",
                display_label("commission"),
                display_label("slippage"),
                display_label("fixed_slippage"),
                display_label("market_impact"),
                display_label("transfer_fee"),
                display_label("stamp_duty"),
                display_label("total_cost"),
                "总成本展示 / total_cost_display",
                display_label("cash_change"),
                "现金变化展示 / cash_change_display",
                display_label("reason"),
            ]
        )
        for trade in trades:
            writer.writerow(
                [
                    trade.date.isoformat(),
                    trade.symbol,
                    format_symbol(trade.symbol),
                    trade.side,
                    str(trade.shares),
                    f"{trade.price:.4f}",
                    f"{trade.gross_value:.2f}",
                    format_money(trade.gross_value),
                    f"{trade.commission:.2f}",
                    f"{trade.slippage:.2f}",
                    f"{trade.fixed_slippage:.2f}",
                    f"{trade.market_impact:.2f}",
                    f"{trade.transfer_fee:.2f}",
                    f"{trade.stamp_duty:.2f}",
                    f"{trade.total_cost:.2f}",
                    format_money(trade.total_cost),
                    f"{trade.cash_change:.2f}",
                    format_money(trade.cash_change),
                    trade.reason,
                ]
            )

    return target_path


def save_trade_attempts_csv(
    attempts: list[TradeAttemptRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
    format_money,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "trade_attempts.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("side"),
                display_label("target_shares"),
                display_label("price"),
                display_label("cash"),
                "现金展示 / cash_display",
                display_label("reason"),
            ]
        )
        for attempt in attempts:
            writer.writerow(
                [
                    attempt.date.isoformat(),
                    attempt.symbol,
                    format_symbol(attempt.symbol),
                    attempt.side,
                    str(attempt.target_shares),
                    f"{attempt.price:.4f}",
                    f"{attempt.cash:.2f}",
                    format_money(attempt.cash),
                    attempt.reason,
                ]
            )

    return target_path


def save_factor_scores_csv(
    records: list[FactorScoreRecord],
    output_dir: Path,
    *,
    format_symbol,
    display_label,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "factor_scores.csv"

    # Identify all factor names dynamically from raw_scores
    dynamic_factors: set[str] = set()
    for record in records:
        if record.raw_scores:
            dynamic_factors.update(record.raw_scores.keys())

    standard_factors = ["momentum", "mean_reversion", "low_volatility"]
    custom_factors = sorted(list(dynamic_factors - set(standard_factors)))
    all_raw_factors = standard_factors + custom_factors

    headers = [
        display_label("date"),
        display_label("symbol"),
        "代码展示 / symbol_display",
    ]
    for factor in all_raw_factors:
        headers.append(display_label(factor))
    for factor in all_raw_factors:
        headers.append(display_label(f"normalized_{factor}"))
    headers.extend([
        display_label("total_score"),
        display_label("selected"),
    ])

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for record in records:
            row = [
                record.date.isoformat(),
                record.symbol,
                format_symbol(record.symbol),
            ]
            for factor in all_raw_factors:
                if factor == "momentum":
                    val = record.momentum
                elif factor == "mean_reversion":
                    val = record.mean_reversion
                elif factor == "low_volatility":
                    val = record.low_volatility
                else:
                    val = record.raw_scores.get(factor, 0.0)
                row.append(f"{val:.8f}")

            for factor in all_raw_factors:
                if factor == "momentum":
                    val = record.normalized_momentum
                elif factor == "mean_reversion":
                    val = record.normalized_mean_reversion
                elif factor == "low_volatility":
                    val = record.normalized_low_volatility
                else:
                    val = record.normalized_scores.get(factor, 0.0)
                row.append(f"{val:.8f}")

            row.extend([
                f"{record.total_score:.8f}",
                "1" if record.selected else "0",
            ])
            writer.writerow(row)

    return target_path


def save_factor_ic_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "factor_ic.csv"
    json_path = output_dir / "factor_ic.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "next_date", "factor", "ic", "rank_ic", "sample_size"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"factor_ic_csv": csv_path, "factor_ic_json": json_path}


def save_factor_group_return_files(
    analysis: dict[str, object],
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "factor_group_returns.csv"
    json_path = output_dir / "factor_group_returns.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "next_date",
                "factor",
                "group",
                "group_count",
                "sample_size",
                "average_factor_value",
                "average_forward_return",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "factor_group_returns_csv": csv_path,
        "factor_group_returns_json": json_path,
    }


def save_factor_decay_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "factor_decay.csv"
    json_path = output_dir / "factor_decay.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "next_date",
                "factor",
                "score_correlation",
                "rank_correlation",
                "sample_size",
                "selected_count",
                "selected_retention_rate",
                "selected_turnover_rate",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "factor_decay_csv": csv_path,
        "factor_decay_json": json_path,
    }


def save_factor_correlation_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "factor_correlation.csv"
    json_path = output_dir / "factor_correlation.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "factor",
                "compared_factor",
                "correlation",
                "rank_correlation",
                "sample_size",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "factor_correlation_csv": csv_path,
        "factor_correlation_json": json_path,
    }


def save_drawdown_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "drawdown.csv"
    json_path = output_dir / "drawdown.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "equity",
                "peak_date",
                "peak_equity",
                "drawdown",
                "is_underwater",
                "underwater_days",
                "underwater_start_date",
                "daily_return",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"drawdown_csv": csv_path, "drawdown_json": json_path}


def save_monthly_return_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "monthly_returns.csv"
    json_path = output_dir / "monthly_returns.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "start_date",
                "end_date",
                "periods",
                "starting_equity",
                "ending_equity",
                "monthly_return",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"monthly_returns_csv": csv_path, "monthly_returns_json": json_path}


def save_rolling_risk_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "rolling_risk.csv"
    json_path = output_dir / "rolling_risk.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "start_date",
                "end_date",
                "window",
                "periods",
                "rolling_return",
                "rolling_annualized_return",
                "rolling_volatility",
                "rolling_sharpe",
                "rolling_max_drawdown",
                "rolling_win_rate",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"rolling_risk_csv": csv_path, "rolling_risk_json": json_path}


def save_relative_performance_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "relative_performance.csv"
    json_path = output_dir / "relative_performance.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "strategy_daily_return",
                "benchmark_daily_return",
                "active_return",
                "cumulative_strategy_equity",
                "cumulative_benchmark_equity",
                "active_equity",
                "cumulative_active_return",
                "active_drawdown",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "relative_performance_csv": csv_path,
        "relative_performance_json": json_path,
    }


def save_execution_quality_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "execution_quality.csv"
    json_path = output_dir / "execution_quality.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category",
                "key",
                "orders",
                "filled_orders",
                "rejected_orders",
                "fill_rate",
                "filled_shares",
                "rejected_target_shares",
                "gross_value",
                "total_cost",
                "cost_bps",
                "average_trade_value",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "execution_quality_csv": csv_path,
        "execution_quality_json": json_path,
    }


def save_exposure_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "exposure.csv"
    json_path = output_dir / "exposure.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "holding_count",
                "stock_weight",
                "cash_weight",
                "largest_position_weight",
                "hhi_concentration",
                "effective_position_count",
                "largest_risk_contribution_symbol",
                "largest_risk_contribution_share",
                "total_equity",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"exposure_csv": csv_path, "exposure_json": json_path}


def save_group_exposure_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "group_exposure.csv"
    json_path = output_dir / "group_exposure.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "group",
                "holding_count",
                "weight",
                "market_value",
                "risk_contribution_share",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"group_exposure_csv": csv_path, "group_exposure_json": json_path}


def save_return_attribution_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "return_attribution.csv"
    json_path = output_dir / "return_attribution.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "previous_date",
                "symbol",
                "group",
                "previous_weight",
                "asset_return",
                "return_contribution",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"return_attribution_csv": csv_path, "return_attribution_json": json_path}


def save_cost_attribution_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "cost_attribution.csv"
    json_path = output_dir / "cost_attribution.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "symbol",
                "group",
                "side",
                "reason",
                "component",
                "amount",
                "gross_value",
                "cost_bps",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"cost_attribution_csv": csv_path, "cost_attribution_json": json_path}


def save_pnl_ledger_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "pnl_ledger.csv"
    json_path = output_dir / "pnl_ledger.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "starting_equity",
                "ending_equity",
                "equity_change",
                "daily_return",
                "gross_buy_value",
                "gross_sell_value",
                "net_cash_flow",
                "total_cost",
                "market_pnl",
                "ending_cash",
                "ending_market_value",
                "ledger_equity",
                "reconciliation_difference",
                "trade_count",
                "holding_count",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"pnl_ledger_csv": csv_path, "pnl_ledger_json": json_path}


def save_strategy_health_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "strategy_health.csv"
    gates_csv_path = output_dir / "strategy_health_gates.csv"
    json_path = output_dir / "strategy_health.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))
    gates = cast(list[dict[str, object]], analysis.get("gates", []))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category",
                "name",
                "score",
                "weight",
                "severity",
                "message",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with gates_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "category",
                "actual",
                "threshold",
                "passed",
                "message",
            ],
        )
        writer.writeheader()
        for gate in gates:
            writer.writerow(gate)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "strategy_health_csv": csv_path,
        "strategy_health_gates_csv": gates_csv_path,
        "strategy_health_json": json_path,
    }


def save_suspension_analysis_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    symbol_csv_path = output_dir / "suspension_analysis.csv"
    daily_csv_path = output_dir / "suspension_daily.csv"
    json_path = output_dir / "suspension_analysis.json"
    symbol_rows = cast(list[dict[str, object]], analysis.get("symbols", []))
    daily_rows = cast(list[dict[str, object]], analysis.get("daily", []))

    with symbol_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "suspended_days",
                "first_suspended_date",
                "last_suspended_date",
            ],
        )
        writer.writeheader()
        for row in symbol_rows:
            writer.writerow(row)

    with daily_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "suspended_symbol_count",
                "symbols",
            ],
        )
        writer.writeheader()
        for row in daily_rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "suspension_analysis_csv": symbol_csv_path,
        "suspension_daily_csv": daily_csv_path,
        "suspension_analysis_json": json_path,
    }


def save_turnover_analysis_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rebalance_csv_path = output_dir / "turnover_analysis.csv"
    holding_csv_path = output_dir / "holding_periods.csv"
    json_path = output_dir / "turnover_analysis.json"
    rebalance_rows = cast(list[dict[str, object]], analysis.get("rebalance_rows", []))
    holding_rows = cast(list[dict[str, object]], analysis.get("holding_period_rows", []))

    with rebalance_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "holding_count",
                "entries",
                "exits",
                "retained",
                "entry_symbols",
                "exit_symbols",
                "retained_symbols",
                "buy_turnover",
                "sell_turnover",
                "turnover",
                "cost",
            ],
        )
        writer.writeheader()
        for row in rebalance_rows:
            writer.writerow(row)

    with holding_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "symbol",
                "entry_date",
                "exit_date",
                "shares",
                "entry_price",
                "exit_price",
                "holding_days",
                "exit_reason",
            ],
        )
        writer.writeheader()
        for row in holding_rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "turnover_analysis_csv": rebalance_csv_path,
        "holding_periods_csv": holding_csv_path,
        "turnover_analysis_json": json_path,
    }


def save_batch_stability_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "batch_stability.csv"
    json_path = output_dir / "batch_stability.json"
    sensitivity_csv_path = output_dir / "parameter_sensitivity.csv"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))
    fieldnames = _ordered_fieldnames(rows)

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    sensitivity_rows = _parameter_sensitivity_rows(analysis)
    with sensitivity_csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        fieldnames = [
            "parameter",
            "value",
            "run_count",
            "average_metric",
            "best_metric",
            "average_composite_score",
            "gate_passing_run_count",
            "gate_passing_rate",
            "worst_max_drawdown",
            "is_recommended",
            "is_best_by_metric",
            "is_best_by_composite",
            "recommendation_reason",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sensitivity_rows:
            writer.writerow(row)

    return {
        "batch_stability_csv": csv_path,
        "batch_stability_json": json_path,
        "parameter_sensitivity_csv": sensitivity_csv_path,
    }


def _parameter_sensitivity_rows(analysis: dict[str, object]) -> list[dict[str, object]]:
    summary = analysis.get("summary")
    if not isinstance(summary, dict):
        return []
    sensitivity = summary.get("parameter_sensitivity")
    if not isinstance(sensitivity, dict):
        return []
    best_parameter_values = summary.get("best_parameter_values")
    if not isinstance(best_parameter_values, dict):
        best_parameter_values = {}
    rationale = summary.get("parameter_recommendation_rationale")
    if not isinstance(rationale, dict):
        rationale = {}
    rows: list[dict[str, object]] = []
    for parameter, parameter_payload in sorted(sensitivity.items()):
        if not isinstance(parameter_payload, dict):
            continue
        values = parameter_payload.get("values")
        if not isinstance(values, dict):
            continue
        for value, stats in sorted(values.items()):
            if not isinstance(stats, dict):
                continue
            row = {"parameter": parameter, "value": value}
            row.update(stats)
            is_recommended = str(best_parameter_values.get(parameter, "")) == str(value)
            row["is_recommended"] = is_recommended
            row["is_best_by_metric"] = str(parameter_payload.get("best_value_by_metric", "")) == str(value)
            row["is_best_by_composite"] = str(parameter_payload.get("best_value_by_composite", "")) == str(value)
            parameter_rationale = rationale.get(parameter)
            if is_recommended and isinstance(parameter_rationale, dict):
                row["recommendation_reason"] = parameter_rationale.get("reason", "")
            else:
                row["recommendation_reason"] = ""
            rows.append(row)
    return rows


def save_walk_forward_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "walk_forward.csv"
    json_path = output_dir / "walk_forward.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))
    fieldnames = _ordered_walk_forward_fieldnames(rows)

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {"walk_forward_csv": csv_path, "walk_forward_json": json_path}


def save_walk_forward_optimization_files(analysis: dict[str, object], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "walk_forward_optimization.csv"
    json_path = output_dir / "walk_forward_optimization.json"
    rows = cast(list[dict[str, object]], analysis.get("rows", []))
    fieldnames = _ordered_walk_forward_optimization_fieldnames(rows)

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis, handle, ensure_ascii=False, indent=2)

    return {
        "walk_forward_optimization_csv": csv_path,
        "walk_forward_optimization_json": json_path,
    }


def _ordered_fieldnames(rows: list[dict[str, object]]) -> list[str]:
    if not rows:
        return ["run_id", "is_robust_region", "composite_score", "risk_penalty"]
    preferred = ["run_id", "is_robust_region", "composite_score", "risk_penalty"]
    all_fields = sorted({key for row in rows for key in row})
    return preferred + [field for field in all_fields if field not in preferred]


def _ordered_walk_forward_fieldnames(rows: list[dict[str, object]]) -> list[str]:
    preferred = [
        "window_id",
        "start_date",
        "end_date",
        "periods",
        "total_return",
        "annualized_return",
        "max_drawdown",
        "sharpe",
        "win_rate",
        "total_cost",
        "run_manifest_json",
    ]
    if not rows:
        return preferred
    all_fields = sorted({key for row in rows for key in row})
    return preferred + [field for field in all_fields if field not in preferred]


def _ordered_walk_forward_optimization_fieldnames(rows: list[dict[str, object]]) -> list[str]:
    preferred = [
        "window_id",
        "train_start_date",
        "train_end_date",
        "test_start_date",
        "test_end_date",
        "selection_policy",
        "train_rank_metric",
        "train_rank_metric_value",
        "train_annualized_return",
        "train_sharpe",
        "train_health_score",
        "train_health_grade",
        "train_gate_status",
        "train_gate_failures",
        "train_health_warnings",
        "train_critical_warnings",
        "test_total_return",
        "test_annualized_return",
        "train_test_annualized_gap",
        "test_to_train_efficiency",
        "is_degraded_out_of_sample",
        "test_max_drawdown",
        "test_sharpe",
        "test_win_rate",
        "train_run_manifest_json",
        "test_run_manifest_json",
    ]
    if not rows:
        return preferred
    all_fields = sorted({key for row in rows for key in row})
    return preferred + [field for field in all_fields if field not in preferred]
