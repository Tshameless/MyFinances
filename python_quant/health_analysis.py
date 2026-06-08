from __future__ import annotations

from .models import BacktestMetrics

DEFAULT_RISK_GATE_THRESHOLDS = {
    "max_allowed_drawdown": 0.20,
    "max_allowed_daily_var": 0.05,
    "min_allowed_rolling_return": -0.10,
    "min_allowed_information_ratio": 0.0,
    "min_allowed_fill_rate": 0.70,
    "min_allowed_execution_price_coverage": 1.0,
    "max_allowed_market_constraint_rate": 0.50,
    "max_allowed_position_weight": 0.50,
    "max_allowed_group_weight": 0.60,
    "max_allowed_attribution_residual": 0.05,
    "max_allowed_factor_correlation": 0.90,
    "max_allowed_rebalance_changes": 3.0,
    "min_allowed_holding_days": 3.0,
    "min_allowed_factor_score_coverage": 0.95,
}


def build_strategy_health_analysis(
    *,
    metrics: BacktestMetrics,
    drawdown_summary: dict[str, object],
    rolling_risk_summary: dict[str, object],
    relative_summary: dict[str, object],
    execution_summary: dict[str, object],
    exposure_summary: dict[str, object],
    return_attribution_summary: dict[str, object],
    cost_attribution_summary: dict[str, object],
    pnl_ledger_summary: dict[str, object],
    data_quality_summary: dict[str, object] | None = None,
    factor_score_quality_summary: dict[str, object] | None = None,
    factor_correlation_summary: dict[str, object] | None = None,
    turnover_summary: dict[str, object] | None = None,
    group_exposure_summary: dict[str, object] | None = None,
    gate_thresholds: dict[str, float] | None = None,
) -> dict[str, object]:
    thresholds = {
        **DEFAULT_RISK_GATE_THRESHOLDS,
        **(gate_thresholds or {}),
    }
    checks = [
        _score_total_return(metrics.total_return),
        _score_drawdown(metrics.max_drawdown),
        _score_tail_risk(drawdown_summary),
        _score_sharpe(metrics.sharpe),
        _score_rolling_return(rolling_risk_summary),
        _score_rolling_drawdown(rolling_risk_summary),
        _score_information_ratio(relative_summary),
        _score_execution(execution_summary),
        _score_execution_price_coverage(data_quality_summary or {}),
        _score_factor_score_coverage(factor_score_quality_summary or {}),
        _score_market_constraints(execution_summary),
        _score_concentration(exposure_summary),
        _score_group_concentration(group_exposure_summary or {}),
        _score_costs(cost_attribution_summary),
        _score_turnover(turnover_summary or {}),
        _score_holding_period(turnover_summary or {}),
        _score_factor_correlation(factor_correlation_summary or {}),
        _score_attribution(return_attribution_summary),
        _score_reconciliation(pnl_ledger_summary),
    ]
    total_weighted_score = sum(_row_float(row, "score") * _row_float(row, "weight") for row in checks)
    total_weight = sum(_row_float(row, "weight") for row in checks)
    total_score = 0.0 if total_weight == 0.0 else total_weighted_score / total_weight
    warnings = [
        {
            "category": row["category"],
            "severity": row["severity"],
            "message": row["message"],
        }
        for row in checks
        if row["severity"] in {"warning", "critical"}
    ]
    gates = _build_risk_gates(
        metrics=metrics,
        drawdown_summary=drawdown_summary,
        rolling_risk_summary=rolling_risk_summary,
        relative_summary=relative_summary,
        execution_summary=execution_summary,
        data_quality_summary=data_quality_summary or {},
        factor_score_quality_summary=factor_score_quality_summary or {},
        exposure_summary=exposure_summary,
        group_exposure_summary=group_exposure_summary or {},
        return_attribution_summary=return_attribution_summary,
        pnl_ledger_summary=pnl_ledger_summary,
        factor_correlation_summary=factor_correlation_summary or {},
        turnover_summary=turnover_summary or {},
        thresholds=thresholds,
    )
    gate_failures = [gate for gate in gates if gate["passed"] is False]
    summary = {
        "score": round(total_score, 2),
        "grade": _grade(total_score),
        "status": _status(total_score, warnings, gate_failures),
        "gate_status": "pass" if not gate_failures else "fail",
        "gate_failures": len(gate_failures),
        "warnings": len(warnings),
        "critical_warnings": sum(1 for item in warnings if item["severity"] == "critical"),
        "max_drawdown_date": drawdown_summary.get("max_drawdown_date"),
        "tail_risk_confidence": drawdown_summary.get("tail_risk_confidence"),
        "daily_var": drawdown_summary.get("daily_var"),
        "daily_expected_shortfall": drawdown_summary.get("daily_expected_shortfall"),
        "worst_daily_return": drawdown_summary.get("worst_daily_return"),
        "rolling_window": rolling_risk_summary.get("window"),
        "worst_rolling_return": rolling_risk_summary.get("worst_rolling_return"),
        "has_benchmark": relative_summary.get("has_benchmark"),
        "active_win_rate": relative_summary.get("active_win_rate"),
        "information_ratio": relative_summary.get("information_ratio"),
        "annualized_alpha": relative_summary.get("annualized_alpha"),
        "total_active_return": relative_summary.get("total_active_return"),
        "market_constraint_rate": execution_summary.get("market_constraint_rate"),
        "dominant_constraint_category": execution_summary.get("dominant_constraint_category"),
        "execution_price_field": (data_quality_summary or {}).get("execution_price_field"),
        "execution_price_coverage_rate": (data_quality_summary or {}).get("execution_price_coverage_rate"),
        "missing_execution_price_rows": (data_quality_summary or {}).get("missing_execution_price_rows"),
        "factor_score_coverage_rate": (factor_score_quality_summary or {}).get("score_coverage_rate"),
        "factor_score_missing_expected_dates": (factor_score_quality_summary or {}).get("missing_expected_dates"),
        "factor_score_missing_expected_symbols": (factor_score_quality_summary or {}).get("missing_expected_symbols"),
        "factor_score_invalid_rows": _factor_score_invalid_rows(factor_score_quality_summary or {}),
        "max_largest_group_weight": (group_exposure_summary or {}).get("max_largest_group_weight"),
        "max_group_risk_contribution_group": (group_exposure_summary or {}).get("max_group_risk_contribution_group"),
        "max_group_risk_contribution_share": (group_exposure_summary or {}).get("max_group_risk_contribution_share"),
        "average_entries_per_rebalance": (turnover_summary or {}).get("average_entries_per_rebalance"),
        "average_exits_per_rebalance": (turnover_summary or {}).get("average_exits_per_rebalance"),
        "average_realized_holding_days": (turnover_summary or {}).get("average_realized_holding_days"),
        "strongest_factor_correlation": _strongest_factor_correlation(factor_correlation_summary or {}),
        "strongest_factor_correlation_pair": _strongest_factor_pair_label(factor_correlation_summary or {}),
    }
    return {"rows": checks, "warnings": warnings, "gates": gates, "summary": summary}


def _score_total_return(total_return: float) -> dict[str, object]:
    if total_return >= 0.15:
        return _check("return", "累计收益", 100.0, 1.2, "ok", "累计收益表现较强。")
    if total_return >= 0.0:
        score = 70.0 + total_return / 0.15 * 25.0
        return _check("return", "累计收益", score, 1.2, "ok", "累计收益为正。")
    score = max(0.0, 50.0 + total_return * 200.0)
    return _check("return", "累计收益", score, 1.2, "critical", "累计收益为负，需要复核策略方向。")


def _score_drawdown(max_drawdown: float) -> dict[str, object]:
    drawdown = abs(max_drawdown)
    if drawdown <= 0.05:
        return _check("risk", "最大回撤", 100.0, 1.4, "ok", "最大回撤控制良好。")
    if drawdown <= 0.15:
        score = 95.0 - (drawdown - 0.05) / 0.10 * 30.0
        return _check("risk", "最大回撤", score, 1.4, "warning", "最大回撤进入关注区间。")
    score = max(0.0, 65.0 - (drawdown - 0.15) / 0.20 * 45.0)
    return _check("risk", "最大回撤", score, 1.4, "critical", "最大回撤偏高，需降低风险暴露。")


def _score_tail_risk(summary: dict[str, object]) -> dict[str, object]:
    daily_var = _float(summary, "daily_var", default=0.0)
    if daily_var <= 0.02:
        return _check("risk", "Daily VaR", 100.0, 0.9, "ok", "Daily tail loss is controlled.")
    if daily_var <= 0.05:
        score = 95.0 - (daily_var - 0.02) / 0.03 * 30.0
        return _check("risk", "Daily VaR", score, 0.9, "warning", "Daily tail loss needs monitoring.")
    score = max(0.0, 65.0 - (daily_var - 0.05) / 0.10 * 45.0)
    return _check("risk", "Daily VaR", score, 0.9, "critical", "Daily tail loss is too high.")


def _score_sharpe(sharpe: float) -> dict[str, object]:
    if sharpe >= 1.5:
        return _check("risk_adjusted", "夏普比率", 100.0, 1.1, "ok", "风险调整后收益较强。")
    if sharpe >= 0.5:
        score = 70.0 + (sharpe - 0.5) / 1.0 * 25.0
        return _check("risk_adjusted", "夏普比率", score, 1.1, "ok", "夏普比率可接受。")
    score = max(0.0, 50.0 + sharpe * 40.0)
    return _check("risk_adjusted", "夏普比率", score, 1.1, "warning", "夏普比率偏低。")


def _score_rolling_return(summary: dict[str, object]) -> dict[str, object]:
    worst_return = _float(summary, "worst_rolling_return", default=0.0)
    if worst_return >= 0.0:
        return _check("stability", "最差滚动收益", 100.0, 1.0, "ok", "所有滚动窗口收益均非负。")
    if worst_return >= -0.05:
        score = 95.0 + worst_return / 0.05 * 25.0
        return _check("stability", "最差滚动收益", score, 1.0, "warning", "部分滚动窗口收益为负。")
    score = max(0.0, 65.0 + (worst_return + 0.05) / 0.15 * 45.0)
    return _check("stability", "最差滚动收益", score, 1.0, "critical", "最差滚动窗口亏损较大。")


def _score_rolling_drawdown(summary: dict[str, object]) -> dict[str, object]:
    drawdown = abs(_float(summary, "worst_rolling_drawdown", default=0.0))
    if drawdown <= 0.03:
        return _check("stability", "滚动最大回撤", 100.0, 1.0, "ok", "滚动回撤较低。")
    if drawdown <= 0.10:
        score = 95.0 - (drawdown - 0.03) / 0.07 * 30.0
        return _check("stability", "滚动最大回撤", score, 1.0, "warning", "滚动回撤进入关注区间。")
    score = max(0.0, 65.0 - (drawdown - 0.10) / 0.20 * 45.0)
    return _check("stability", "滚动最大回撤", score, 1.0, "critical", "滚动回撤偏高。")


def _score_information_ratio(summary: dict[str, object]) -> dict[str, object]:
    if summary.get("has_benchmark") is not True:
        return _check("relative", "Information ratio", 85.0, 0.6, "ok", "Benchmark is not provided; relative gate is skipped.")
    information_ratio = _float(summary, "information_ratio", default=0.0)
    if information_ratio >= 0.5:
        return _check("relative", "Information ratio", 100.0, 0.6, "ok", "Relative performance is strong.")
    if information_ratio >= 0.0:
        score = 70.0 + information_ratio / 0.5 * 25.0
        return _check("relative", "Information ratio", score, 0.6, "warning", "Relative performance needs monitoring.")
    score = max(0.0, 65.0 + information_ratio * 35.0)
    return _check("relative", "Information ratio", score, 0.6, "critical", "Relative performance is weak versus benchmark.")


def _score_execution(summary: dict[str, object]) -> dict[str, object]:
    fill_rate = _float(summary, "fill_rate", default=1.0)
    if fill_rate >= 0.95:
        return _check("execution", "成交率", 100.0, 0.8, "ok", "成交率良好。")
    if fill_rate >= 0.75:
        score = 70.0 + (fill_rate - 0.75) / 0.20 * 25.0
        return _check("execution", "成交率", score, 0.8, "warning", "存在一定比例未成交。")
    score = max(0.0, fill_rate / 0.75 * 70.0)
    return _check("execution", "成交率", score, 0.8, "critical", "未成交比例偏高。")


def _score_execution_price_coverage(summary: dict[str, object]) -> dict[str, object]:
    coverage = _float(summary, "execution_price_coverage_rate", default=1.0)
    if coverage >= 1.0:
        return _check("data", "Execution price coverage", 100.0, 0.8, "ok", "Execution price field is fully covered.")
    if coverage >= 0.95:
        score = 70.0 + (coverage - 0.95) / 0.05 * 25.0
        return _check("data", "Execution price coverage", score, 0.8, "warning", "Execution price field has limited missing rows.")
    score = max(0.0, coverage / 0.95 * 70.0)
    return _check("data", "Execution price coverage", score, 0.8, "critical", "Execution price field coverage is too low.")


def _score_factor_score_coverage(summary: dict[str, object]) -> dict[str, object]:
    if not summary:
        return _check("data", "External factor score coverage", 100.0, 0.4, "ok", "External factor score file is not configured.")
    coverage = _float(summary, "score_coverage_rate", default=1.0)
    invalid_rows = _factor_score_invalid_rows(summary)
    if coverage >= 0.95 and invalid_rows == 0:
        return _check("data", "External factor score coverage", 100.0, 0.4, "ok", "External factor scores are well covered.")
    if coverage >= 0.80 and invalid_rows == 0:
        score = 70.0 + (coverage - 0.80) / 0.15 * 25.0
        return _check("data", "External factor score coverage", score, 0.4, "warning", "External factor scores have limited coverage gaps.")
    score = max(0.0, coverage / 0.80 * 70.0)
    return _check("data", "External factor score coverage", score, 0.4, "critical", "External factor score coverage is too low or contains invalid rows.")


def _score_market_constraints(summary: dict[str, object]) -> dict[str, object]:
    constraint_rate = _float(summary, "market_constraint_rate", default=0.0)
    if constraint_rate <= 0.20:
        return _check("execution", "Market constraint rate", 100.0, 0.7, "ok", "Market microstructure constraints are limited.")
    if constraint_rate <= 0.50:
        score = 95.0 - (constraint_rate - 0.20) / 0.30 * 30.0
        return _check("execution", "Market constraint rate", score, 0.7, "warning", "Market constraints are blocking a meaningful share of rejected orders.")
    score = max(0.0, 65.0 - (constraint_rate - 0.50) / 0.50 * 45.0)
    return _check("execution", "Market constraint rate", score, 0.7, "critical", "Market constraints dominate rejected orders; execution feasibility is weak.")


def _score_concentration(summary: dict[str, object]) -> dict[str, object]:
    largest_weight = _float(summary, "max_largest_position_weight", default=0.0)
    if largest_weight <= 0.25:
        return _check("exposure", "最大单票权重", 100.0, 0.8, "ok", "单票集中度较低。")
    if largest_weight <= 0.45:
        score = 95.0 - (largest_weight - 0.25) / 0.20 * 30.0
        return _check("exposure", "最大单票权重", score, 0.8, "warning", "单票集中度需要关注。")
    score = max(0.0, 65.0 - (largest_weight - 0.45) / 0.35 * 45.0)
    return _check("exposure", "最大单票权重", score, 0.8, "critical", "单票集中度偏高。")


def _score_group_concentration(summary: dict[str, object]) -> dict[str, object]:
    largest_weight = _float(summary, "max_largest_group_weight", default=0.0)
    if largest_weight <= 0.35:
        return _check("exposure", "Group concentration", 100.0, 0.6, "ok", "Group exposure is diversified.")
    if largest_weight <= 0.60:
        score = 95.0 - (largest_weight - 0.35) / 0.25 * 30.0
        return _check("exposure", "Group concentration", score, 0.6, "warning", "Group exposure concentration needs review.")
    score = max(0.0, 65.0 - (largest_weight - 0.60) / 0.40 * 45.0)
    return _check("exposure", "Group concentration", score, 0.6, "critical", "Group exposure concentration is too high.")


def _score_costs(summary: dict[str, object]) -> dict[str, object]:
    cost_bps = _float(summary, "cost_bps", default=0.0)
    if cost_bps <= 10.0:
        return _check("cost", "成本 bps", 100.0, 0.7, "ok", "交易成本较低。")
    if cost_bps <= 50.0:
        score = 95.0 - (cost_bps - 10.0) / 40.0 * 30.0
        return _check("cost", "成本 bps", score, 0.7, "warning", "交易成本进入关注区间。")
    score = max(0.0, 65.0 - (cost_bps - 50.0) / 100.0 * 45.0)
    return _check("cost", "成本 bps", score, 0.7, "critical", "交易成本偏高。")


def _score_turnover(summary: dict[str, object]) -> dict[str, object]:
    average_entries = _float(summary, "average_entries_per_rebalance", default=0.0)
    average_exits = _float(summary, "average_exits_per_rebalance", default=0.0)
    average_changes = average_entries + average_exits
    if average_changes <= 1.0:
        return _check("turnover", "平均调仓变动数", 100.0, 0.7, "ok", "调仓变动较温和。")
    if average_changes <= 3.0:
        score = 95.0 - (average_changes - 1.0) / 2.0 * 30.0
        return _check("turnover", "平均调仓变动数", score, 0.7, "warning", "调仓变动较多，需要关注交易成本和信号稳定性。")
    score = max(0.0, 65.0 - (average_changes - 3.0) / 5.0 * 45.0)
    return _check("turnover", "平均调仓变动数", score, 0.7, "critical", "调仓变动过高，策略可能过度交易。")


def _score_holding_period(summary: dict[str, object]) -> dict[str, object]:
    realized_count = _float(summary, "realized_holding_count", default=0.0)
    if realized_count == 0:
        return _check("turnover", "平均持仓天数", 90.0, 0.5, "ok", "暂无已实现退出的持仓周期。")
    average_days = _float(summary, "average_realized_holding_days", default=0.0)
    if average_days >= 10.0:
        return _check("turnover", "平均持仓天数", 100.0, 0.5, "ok", "已实现持仓周期较稳定。")
    if average_days >= 3.0:
        score = 70.0 + (average_days - 3.0) / 7.0 * 25.0
        return _check("turnover", "平均持仓天数", score, 0.5, "warning", "已实现持仓周期较短，需观察信号抖动。")
    score = max(0.0, average_days / 3.0 * 70.0)
    return _check("turnover", "平均持仓天数", score, 0.5, "critical", "已实现持仓周期过短，策略可能过度交易。")


def _score_factor_correlation(summary: dict[str, object]) -> dict[str, object]:
    strongest_correlation = abs(_strongest_factor_correlation(summary))
    if strongest_correlation <= 0.70:
        return _check("factor", "Factor correlation", 100.0, 0.5, "ok", "Factor signals are reasonably diversified.")
    if strongest_correlation <= 0.90:
        score = 95.0 - (strongest_correlation - 0.70) / 0.20 * 30.0
        return _check("factor", "Factor correlation", score, 0.5, "warning", "Factor signals show elevated redundancy; review factor crowding.")
    score = max(0.0, 65.0 - (strongest_correlation - 0.90) / 0.10 * 45.0)
    return _check("factor", "Factor correlation", score, 0.5, "critical", "Factor signals are highly correlated; alpha sources may be redundant.")


def _score_attribution(summary: dict[str, object]) -> dict[str, object]:
    residual = abs(_float(summary, "total_residual_return", default=0.0))
    if residual <= 0.001:
        return _check("attribution", "收益归因残差", 100.0, 0.5, "ok", "收益归因残差较低。")
    if residual <= 0.01:
        score = 95.0 - (residual - 0.001) / 0.009 * 30.0
        return _check("attribution", "收益归因残差", score, 0.5, "warning", "收益归因残差需要关注。")
    score = max(0.0, 65.0 - (residual - 0.01) / 0.05 * 45.0)
    return _check("attribution", "收益归因残差", score, 0.5, "critical", "收益归因残差偏高。")


def _score_reconciliation(summary: dict[str, object]) -> dict[str, object]:
    if summary.get("reconciled") is True:
        return _check("ledger", "盈亏对账", 100.0, 1.0, "ok", "盈亏账本已对齐。")
    difference = abs(_float(summary, "max_abs_reconciliation_difference", default=0.0))
    if difference <= 0.01:
        return _check("ledger", "盈亏对账", 90.0, 1.0, "warning", "对账状态缺失但差异较低。")
    return _check("ledger", "盈亏对账", 0.0, 1.0, "critical", "盈亏账本未对齐。")


def _build_risk_gates(
    *,
    metrics: BacktestMetrics,
    drawdown_summary: dict[str, object],
    rolling_risk_summary: dict[str, object],
    relative_summary: dict[str, object],
    execution_summary: dict[str, object],
    data_quality_summary: dict[str, object],
    factor_score_quality_summary: dict[str, object],
    exposure_summary: dict[str, object],
    group_exposure_summary: dict[str, object],
    return_attribution_summary: dict[str, object],
    pnl_ledger_summary: dict[str, object],
    factor_correlation_summary: dict[str, object],
    turnover_summary: dict[str, object],
    thresholds: dict[str, float],
) -> list[dict[str, object]]:
    max_drawdown = thresholds["max_allowed_drawdown"]
    max_daily_var = thresholds["max_allowed_daily_var"]
    min_rolling_return = thresholds["min_allowed_rolling_return"]
    min_information_ratio = thresholds["min_allowed_information_ratio"]
    min_fill_rate = thresholds["min_allowed_fill_rate"]
    min_execution_price_coverage = thresholds["min_allowed_execution_price_coverage"]
    min_factor_score_coverage = thresholds["min_allowed_factor_score_coverage"]
    max_market_constraint_rate = thresholds["max_allowed_market_constraint_rate"]
    max_position_weight = thresholds["max_allowed_position_weight"]
    max_group_weight = thresholds["max_allowed_group_weight"]
    max_attribution_residual = thresholds["max_allowed_attribution_residual"]
    max_factor_correlation = thresholds["max_allowed_factor_correlation"]
    max_rebalance_changes = thresholds["max_allowed_rebalance_changes"]
    min_holding_days = thresholds["min_allowed_holding_days"]
    average_rebalance_changes = _float(
        turnover_summary,
        "average_entries_per_rebalance",
        default=0.0,
    ) + _float(
        turnover_summary,
        "average_exits_per_rebalance",
        default=0.0,
    )
    realized_holding_count = _float(turnover_summary, "realized_holding_count", default=0.0)
    average_holding_days = _float(turnover_summary, "average_realized_holding_days", default=0.0)
    return [
        _gate(
            name="盈亏对账必须通过",
            category="ledger",
            actual=0.0 if pnl_ledger_summary.get("reconciled") is True else 1.0,
            threshold=0.0,
            passed=pnl_ledger_summary.get("reconciled") is True,
            message="盈亏账本未对齐时不应进入实盘候选。",
        ),
        _gate(
            name=f"最大回撤不超过 {_pct_label(max_drawdown)}",
            category="risk",
            actual=abs(metrics.max_drawdown),
            threshold=max_drawdown,
            passed=abs(metrics.max_drawdown) <= max_drawdown,
            message="全周期最大回撤超过上线风险阈值。",
        ),
        _gate(
            name=f"Daily VaR no more than {_pct_label(max_daily_var)}",
            category="risk",
            actual=_float(drawdown_summary, "daily_var", default=0.0),
            threshold=max_daily_var,
            passed=_float(drawdown_summary, "daily_var", default=0.0) <= max_daily_var,
            message="Daily tail loss exceeds the allowed threshold.",
        ),
        _gate(
            name=f"最差滚动收益不低于 {_pct_label(min_rolling_return)}",
            category="stability",
            actual=_float(rolling_risk_summary, "worst_rolling_return", default=0.0),
            threshold=min_rolling_return,
            passed=_float(rolling_risk_summary, "worst_rolling_return", default=0.0) >= min_rolling_return,
            message="阶段性滚动亏损过深。",
        ),
        _gate(
            name=f"Information ratio at least {min_information_ratio:g}",
            category="relative",
            actual=_float(relative_summary, "information_ratio", default=0.0),
            threshold=min_information_ratio,
            passed=(
                relative_summary.get("has_benchmark") is not True
                or _float(relative_summary, "information_ratio", default=0.0) >= min_information_ratio
            ),
            message="Relative performance is below the required benchmark threshold.",
        ),
        _gate(
            name=f"成交率不低于 {_pct_label(min_fill_rate)}",
            category="execution",
            actual=_float(execution_summary, "fill_rate", default=1.0),
            threshold=min_fill_rate,
            passed=_float(execution_summary, "fill_rate", default=1.0) >= min_fill_rate,
            message="成交率过低，回测执行假设不稳定。",
        ),
        _gate(
            name=f"Execution price coverage at least {_pct_label(min_execution_price_coverage)}",
            category="data",
            actual=_float(data_quality_summary, "execution_price_coverage_rate", default=1.0),
            threshold=min_execution_price_coverage,
            passed=_float(data_quality_summary, "execution_price_coverage_rate", default=1.0) >= min_execution_price_coverage,
            message="Execution price field coverage is below the required threshold.",
        ),
        _gate(
            name=f"External factor score coverage at least {_pct_label(min_factor_score_coverage)}",
            category="data",
            actual=_float(factor_score_quality_summary, "score_coverage_rate", default=1.0),
            threshold=min_factor_score_coverage,
            passed=(
                not factor_score_quality_summary
                or (
                    _float(factor_score_quality_summary, "score_coverage_rate", default=1.0) >= min_factor_score_coverage
                    and _factor_score_invalid_rows(factor_score_quality_summary) == 0
                )
            ),
            message="External factor score coverage is below the required threshold or contains invalid rows.",
        ),
        _gate(
            name=f"Market constraint rejection rate no more than {_pct_label(max_market_constraint_rate)}",
            category="execution",
            actual=_float(execution_summary, "market_constraint_rate", default=0.0),
            threshold=max_market_constraint_rate,
            passed=_float(execution_summary, "market_constraint_rate", default=0.0) <= max_market_constraint_rate,
            message="Market microstructure constraints block too many rejected orders.",
        ),
        _gate(
            name=f"最大单票权重不超过 {_pct_label(max_position_weight)}",
            category="exposure",
            actual=_float(exposure_summary, "max_largest_position_weight", default=0.0),
            threshold=max_position_weight,
            passed=_float(exposure_summary, "max_largest_position_weight", default=0.0) <= max_position_weight,
            message="单票集中度超过上线阈值。",
        ),
        _gate(
            name=f"Maximum group weight no more than {_pct_label(max_group_weight)}",
            category="exposure",
            actual=_float(group_exposure_summary, "max_largest_group_weight", default=0.0),
            threshold=max_group_weight,
            passed=_float(group_exposure_summary, "max_largest_group_weight", default=0.0) <= max_group_weight,
            message="Group exposure concentration exceeds the launch threshold.",
        ),
        _gate(
            name=f"收益归因残差不超过 {_pct_label(max_attribution_residual)}",
            category="attribution",
            actual=abs(_float(return_attribution_summary, "total_residual_return", default=0.0)),
            threshold=max_attribution_residual,
            passed=abs(_float(return_attribution_summary, "total_residual_return", default=0.0)) <= max_attribution_residual,
            message="收益归因残差过高，需要先复核归因链路。",
        ),
        _gate(
            name=f"Average rebalance changes no more than {max_rebalance_changes:g}",
            category="turnover",
            actual=average_rebalance_changes,
            threshold=max_rebalance_changes,
            passed=average_rebalance_changes <= max_rebalance_changes,
            message="Average rebalance changes are too high; review signal churn and transaction cost drag.",
        ),
        _gate(
            name=f"Average realized holding days at least {min_holding_days:g}",
            category="turnover",
            actual=average_holding_days,
            threshold=min_holding_days,
            passed=realized_holding_count == 0 or average_holding_days >= min_holding_days,
            message="Average realized holding period is too short; review signal stability and execution feasibility.",
        ),
        _gate(
            name=f"Strongest average factor correlation no more than {max_factor_correlation:.2f}",
            category="factor",
            actual=abs(_strongest_factor_correlation(factor_correlation_summary)),
            threshold=max_factor_correlation,
            passed=abs(_strongest_factor_correlation(factor_correlation_summary)) <= max_factor_correlation,
            message="Factor correlation is too high; review redundant or crowded alpha signals.",
        ),
    ]


def _gate(
    *,
    name: str,
    category: str,
    actual: float,
    threshold: float,
    passed: bool,
    message: str,
) -> dict[str, object]:
    return {
        "name": name,
        "category": category,
        "actual": actual,
        "threshold": threshold,
        "passed": passed,
        "message": "通过" if passed else message,
    }


def _check(
    category: str,
    name: str,
    score: float,
    weight: float,
    severity: str,
    message: str,
) -> dict[str, object]:
    return {
        "category": category,
        "name": name,
        "score": round(_clamp(score), 2),
        "weight": weight,
        "severity": severity,
        "message": message,
    }


def _float(summary: dict[str, object], key: str, *, default: float) -> float:
    value = summary.get(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return default


def _factor_score_invalid_rows(summary: dict[str, object]) -> int:
    return int(
        _float(summary, "invalid_date_rows", default=0.0)
        + _float(summary, "invalid_symbol_rows", default=0.0)
        + _float(summary, "invalid_score_rows", default=0.0)
        + _float(summary, "blank_score_rows", default=0.0)
    )


def _strongest_factor_correlation(summary: dict[str, object]) -> float:
    strongest_pair = summary.get("strongest_pair")
    if not isinstance(strongest_pair, dict):
        return 0.0
    return _float(strongest_pair, "average_correlation", default=0.0)


def _strongest_factor_pair_label(summary: dict[str, object]) -> str:
    strongest_pair = summary.get("strongest_pair")
    if not isinstance(strongest_pair, dict):
        return ""
    factor = strongest_pair.get("factor")
    compared_factor = strongest_pair.get("compared_factor")
    if not isinstance(factor, str) or not isinstance(compared_factor, str):
        return ""
    return f"{factor} vs {compared_factor}"


def _row_float(row: dict[str, object], key: str) -> float:
    value = row[key]
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    raise TypeError(f"Health check field '{key}' must be numeric.")


def _clamp(value: float) -> float:
    return max(0.0, min(value, 100.0))


def _pct_label(value: float) -> str:
    return f"{value:.0%}"


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"


def _status(
    score: float,
    warnings: list[dict[str, object]],
    gate_failures: list[dict[str, object]],
) -> str:
    if gate_failures:
        return "blocked"
    if any(item["severity"] == "critical" for item in warnings):
        return "critical"
    if score < 70 or warnings:
        return "warning"
    return "ok"
