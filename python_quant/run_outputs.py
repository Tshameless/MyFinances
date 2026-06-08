from __future__ import annotations

from pathlib import Path

from .attribution_analysis import build_return_attribution_analysis
from .config import BacktestConfig
from .cost_analysis import build_cost_attribution_analysis
from .data_quality import (
    build_factor_score_quality_report,
    build_price_data_quality_report,
    save_data_quality_report,
    save_factor_score_quality_report,
)
from .execution_analysis import build_execution_quality_analysis
from .exposure_analysis import build_exposure_analysis, build_group_exposure_analysis
from .factor_analysis import (
    build_factor_correlation_analysis,
    build_factor_decay_analysis,
    build_factor_group_return_analysis,
    build_factor_ic_analysis,
)
from .health_analysis import build_strategy_health_analysis
from .ledger_analysis import build_pnl_ledger_analysis
from .models import BacktestResult
from .reporting import (
    load_symbol_group_mapping,
    load_symbol_name_mapping,
    print_summary,
    save_equity_chart_svg,
    save_equity_curve,
    save_factor_scores,
    save_performance_summary,
    save_positions,
    save_rebalance_log,
    save_trade_attempts,
    save_trades,
)
from .reporting_html import save_single_run_report_html
from .reporting_json import (
    save_config_sources,
    save_effective_config,
    save_performance_summary_json,
    save_run_manifest,
)
from .reporting_csv import (
    save_cost_attribution_files,
    save_drawdown_files,
    save_execution_quality_files,
    save_exposure_files,
    save_factor_correlation_files,
    save_factor_decay_files,
    save_factor_group_return_files,
    save_factor_ic_files,
    save_group_exposure_files,
    save_monthly_return_files,
    save_pnl_ledger_files,
    save_relative_performance_files,
    save_return_attribution_files,
    save_rolling_risk_files,
    save_strategy_health_files,
    save_suspension_analysis_files,
    save_turnover_analysis_files,
)
from .risk_analysis import (
    build_drawdown_analysis,
    build_monthly_return_analysis,
    build_relative_performance_analysis,
    build_rolling_risk_analysis,
    build_split_performance,
)
from .suspension_analysis import build_suspension_analysis
from .turnover_analysis import build_turnover_analysis


def persist_run_outputs(
    *,
    output_dir: Path,
    result: BacktestResult,
    config: BacktestConfig,
    inputs: dict[str, str | bool | None],
    print_console: bool,
    config_sources: dict[str, object] | None = None,
) -> dict[str, Path]:
    symbol_names = load_symbol_name_mapping(config.symbol_name_csv)
    symbol_groups = load_symbol_group_mapping(config.symbol_group_csv)
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
        symbol_names=symbol_names,
    )
    rebalance_path = save_rebalance_log(
        result.rebalance_records,
        output_dir,
        symbol_names=symbol_names,
    )
    positions_path = save_positions(
        result.positions or [],
        output_dir,
        symbol_names=symbol_names,
    )
    trades_path = save_trades(
        result.trades or [],
        output_dir,
        symbol_names=symbol_names,
    )
    trade_attempts_path = save_trade_attempts(
        result.trade_attempts or [],
        output_dir,
        symbol_names=symbol_names,
    )
    factor_scores_path = save_factor_scores(
        result.factor_scores or [],
        output_dir,
        symbol_names=symbol_names,
    )
    price_data_quality_report = build_price_data_quality_report(
        result.price_bars or [],
        execution_price_field=config.execution_price_field_effective,
    )
    price_data_quality_paths = save_data_quality_report(
        price_data_quality_report,
        output_dir,
        prefix="price_data_quality",
    )
    factor_score_quality_report = (
        None
        if config.factor_score_csv is None
        else build_factor_score_quality_report(
            config.factor_score_csv,
            expected_symbols={bar.symbol for bar in result.price_bars or []},
            expected_dates={bar.date for bar in result.price_bars or []},
        )
    )
    factor_score_quality_paths = (
        {}
        if factor_score_quality_report is None
        else save_factor_score_quality_report(factor_score_quality_report, output_dir)
    )
    factor_ic_paths = save_factor_ic_files(
        build_factor_ic_analysis(
            result.factor_scores or [],
            result.positions or [],
            result.price_bars,
            price_field=config.price_field,
        ),
        output_dir,
    )
    factor_group_return_paths = save_factor_group_return_files(
        build_factor_group_return_analysis(
            result.factor_scores or [],
            result.positions or [],
            price_bars=result.price_bars,
            price_field=config.price_field,
        ),
        output_dir,
    )
    factor_decay_analysis = build_factor_decay_analysis(result.factor_scores or [])
    factor_decay_paths = save_factor_decay_files(factor_decay_analysis, output_dir)
    factor_correlation_analysis = build_factor_correlation_analysis(result.factor_scores or [])
    factor_correlation_paths = save_factor_correlation_files(factor_correlation_analysis, output_dir)
    drawdown_analysis = build_drawdown_analysis(result.equity_curve)
    drawdown_paths = save_drawdown_files(drawdown_analysis, output_dir)
    monthly_return_paths = save_monthly_return_files(
        build_monthly_return_analysis(result.equity_curve),
        output_dir,
    )
    rolling_risk_analysis = build_rolling_risk_analysis(
        result.equity_curve,
        window=config.rolling_risk_window,
    )
    rolling_risk_paths = save_rolling_risk_files(rolling_risk_analysis, output_dir)
    relative_performance_analysis = build_relative_performance_analysis(
        result.equity_curve,
        result.benchmark_curve,
    )
    relative_performance_paths = save_relative_performance_files(
        relative_performance_analysis,
        output_dir,
    )
    execution_quality_analysis = build_execution_quality_analysis(
        result.trades or [],
        result.trade_attempts or [],
    )
    execution_quality_paths = save_execution_quality_files(execution_quality_analysis, output_dir)
    exposure_analysis = build_exposure_analysis(result.positions or [])
    exposure_paths = save_exposure_files(exposure_analysis, output_dir)
    group_exposure_analysis = build_group_exposure_analysis(result.positions or [], symbol_groups)
    group_exposure_paths = save_group_exposure_files(
        group_exposure_analysis,
        output_dir,
    )
    return_attribution_analysis = build_return_attribution_analysis(
        equity_curve=result.equity_curve,
        positions=result.positions or [],
        price_bars=result.price_bars,
        trades=result.trades or [],
        symbol_groups=symbol_groups,
        price_field=config.price_field,
    )
    return_attribution_paths = save_return_attribution_files(
        return_attribution_analysis,
        output_dir,
    )
    cost_attribution_analysis = build_cost_attribution_analysis(
        result.trades or [],
        symbol_groups,
    )
    cost_attribution_paths = save_cost_attribution_files(cost_attribution_analysis, output_dir)
    pnl_ledger_analysis = build_pnl_ledger_analysis(
        result.equity_curve,
        result.positions or [],
        result.trades or [],
    )
    pnl_ledger_paths = save_pnl_ledger_files(pnl_ledger_analysis, output_dir)
    suspension_analysis = build_suspension_analysis(result.price_bars)
    suspension_paths = save_suspension_analysis_files(suspension_analysis, output_dir)
    turnover_analysis = build_turnover_analysis(
        result.rebalance_records,
        result.trades or [],
    )
    turnover_paths = save_turnover_analysis_files(turnover_analysis, output_dir)
    strategy_health_paths = save_strategy_health_files(
        build_strategy_health_analysis(
            metrics=result.metrics,
            drawdown_summary=_analysis_summary(drawdown_analysis),
            rolling_risk_summary=_analysis_summary(rolling_risk_analysis),
            relative_summary=_analysis_summary(relative_performance_analysis),
            execution_summary=_analysis_summary(execution_quality_analysis),
            data_quality_summary=price_data_quality_report.summary,
            factor_score_quality_summary=(
                {} if factor_score_quality_report is None else factor_score_quality_report.summary
            ),
            exposure_summary=_analysis_summary(exposure_analysis),
            group_exposure_summary=_analysis_summary(group_exposure_analysis),
            return_attribution_summary=_analysis_summary(return_attribution_analysis),
            cost_attribution_summary=_analysis_summary(cost_attribution_analysis),
            pnl_ledger_summary=_analysis_summary(pnl_ledger_analysis),
            factor_correlation_summary=_analysis_summary(factor_correlation_analysis),
            turnover_summary=_analysis_summary(turnover_analysis),
            gate_thresholds={
                "max_allowed_drawdown": config.max_allowed_drawdown,
                "max_allowed_daily_var": config.max_allowed_daily_var,
                "min_allowed_rolling_return": config.min_allowed_rolling_return,
                "min_allowed_information_ratio": config.min_allowed_information_ratio,
                "min_allowed_fill_rate": config.min_allowed_fill_rate,
                "min_allowed_execution_price_coverage": config.min_allowed_execution_price_coverage,
                "min_allowed_factor_score_coverage": config.min_allowed_factor_score_coverage,
                "max_allowed_market_constraint_rate": config.max_allowed_market_constraint_rate,
                "max_allowed_position_weight": config.max_allowed_position_weight,
                "max_allowed_group_weight": config.max_allowed_group_weight,
                "max_allowed_attribution_residual": config.max_allowed_attribution_residual,
                "max_allowed_factor_correlation": config.max_allowed_factor_correlation,
                "max_allowed_rebalance_changes": config.max_allowed_rebalance_changes,
                "min_allowed_holding_days": config.min_allowed_holding_days,
            },
        ),
        output_dir,
    )
    summary_path = save_performance_summary(result.metrics, output_dir)
    summary_json_path = save_performance_summary_json(
        result.metrics,
        output_dir,
        extra_payload={"split_performance": build_split_performance(result.equity_curve)},
    )
    equity_chart_path = save_equity_chart_svg(
        result.equity_curve,
        output_dir,
        result.benchmark_curve,
    )
    effective_config_path = save_effective_config(output_dir=output_dir, config=config)
    config_sources_path = (
        None
        if config_sources is None
        else save_config_sources(output_dir=output_dir, config_sources=config_sources)
    )
    artifact_paths = {
        "equity_curve_csv": equity_path,
        "equity_curve_svg": equity_chart_path,
        "rebalance_log_csv": rebalance_path,
        "positions_csv": positions_path,
        "trades_csv": trades_path,
        "trade_attempts_csv": trade_attempts_path,
        "factor_scores_csv": factor_scores_path,
        "price_data_quality_report_csv": price_data_quality_paths["price_data_quality_report_csv"],
        "price_data_quality_report_json": price_data_quality_paths["price_data_quality_report_json"],
        "factor_ic_csv": factor_ic_paths["factor_ic_csv"],
        "factor_ic_json": factor_ic_paths["factor_ic_json"],
        "factor_group_returns_csv": factor_group_return_paths["factor_group_returns_csv"],
        "factor_group_returns_json": factor_group_return_paths["factor_group_returns_json"],
        "factor_decay_csv": factor_decay_paths["factor_decay_csv"],
        "factor_decay_json": factor_decay_paths["factor_decay_json"],
        "factor_correlation_csv": factor_correlation_paths["factor_correlation_csv"],
        "factor_correlation_json": factor_correlation_paths["factor_correlation_json"],
        "drawdown_csv": drawdown_paths["drawdown_csv"],
        "drawdown_json": drawdown_paths["drawdown_json"],
        "monthly_returns_csv": monthly_return_paths["monthly_returns_csv"],
        "monthly_returns_json": monthly_return_paths["monthly_returns_json"],
        "rolling_risk_csv": rolling_risk_paths["rolling_risk_csv"],
        "rolling_risk_json": rolling_risk_paths["rolling_risk_json"],
        "relative_performance_csv": relative_performance_paths["relative_performance_csv"],
        "relative_performance_json": relative_performance_paths["relative_performance_json"],
        "execution_quality_csv": execution_quality_paths["execution_quality_csv"],
        "execution_quality_json": execution_quality_paths["execution_quality_json"],
        "exposure_csv": exposure_paths["exposure_csv"],
        "exposure_json": exposure_paths["exposure_json"],
        "group_exposure_csv": group_exposure_paths["group_exposure_csv"],
        "group_exposure_json": group_exposure_paths["group_exposure_json"],
        "return_attribution_csv": return_attribution_paths["return_attribution_csv"],
        "return_attribution_json": return_attribution_paths["return_attribution_json"],
        "cost_attribution_csv": cost_attribution_paths["cost_attribution_csv"],
        "cost_attribution_json": cost_attribution_paths["cost_attribution_json"],
        "pnl_ledger_csv": pnl_ledger_paths["pnl_ledger_csv"],
        "pnl_ledger_json": pnl_ledger_paths["pnl_ledger_json"],
        "suspension_analysis_csv": suspension_paths["suspension_analysis_csv"],
        "suspension_daily_csv": suspension_paths["suspension_daily_csv"],
        "suspension_analysis_json": suspension_paths["suspension_analysis_json"],
        "turnover_analysis_csv": turnover_paths["turnover_analysis_csv"],
        "holding_periods_csv": turnover_paths["holding_periods_csv"],
        "turnover_analysis_json": turnover_paths["turnover_analysis_json"],
        "strategy_health_csv": strategy_health_paths["strategy_health_csv"],
        "strategy_health_gates_csv": strategy_health_paths["strategy_health_gates_csv"],
        "strategy_health_json": strategy_health_paths["strategy_health_json"],
        "performance_summary_csv": summary_path,
        "performance_summary_json": summary_json_path,
        "config_effective_json": effective_config_path,
    }
    if config_sources_path is not None:
        artifact_paths["config_sources_json"] = config_sources_path
    artifact_paths.update(factor_score_quality_paths)
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
        latest_holdings=result.equity_curve[-1].holdings if result.equity_curve else (),
        latest_rebalance=result.rebalance_records[-1] if result.rebalance_records else None,
        symbol_names=symbol_names,
        equity_curve=result.equity_curve,
        benchmark_curve=result.benchmark_curve,
    )
    artifact_paths["report_html"] = report_path
    return artifact_paths


def _analysis_summary(analysis: dict[str, object]) -> dict[str, object]:
    summary = analysis.get("summary")
    return summary if isinstance(summary, dict) else {}
