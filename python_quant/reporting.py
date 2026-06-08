from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path

from .config import BacktestConfig
from .market import is_a_share_symbol
from .models import (
    BacktestMetrics,
    BenchmarkPoint,
    EquityPoint,
    FactorScoreRecord,
    PositionPoint,
    RebalanceRecord,
    TradeAttemptRecord,
    TradeRecord,
)
from .reporting_csv import (
    save_factor_scores_csv,
    save_trade_attempts_csv,
    save_trades_csv,
)

_ZH_LABELS = {
    "date": "日期",
    "equity": "权益",
    "daily_return": "单期收益",
    "holdings": "持仓",
    "symbol": "代码",
    "shares": "股数",
    "price": "价格",
    "market_value": "市值",
    "weight": "权重",
    "cash": "现金",
    "total_equity": "总权益",
    "side": "方向",
    "target_shares": "目标股数",
    "gross_value": "成交金额",
    "commission": "佣金",
    "slippage": "滑点",
    "fixed_slippage": "固定滑点",
    "market_impact": "市场冲击",
    "transfer_fee": "过户费",
    "stamp_duty": "印花税",
    "cash_change": "现金变化",
    "reason": "原因",
    "momentum": "动量",
    "mean_reversion": "均值回归",
    "low_volatility": "低波动",
    "normalized_momentum": "标准化动量",
    "normalized_mean_reversion": "标准化均值回归",
    "normalized_low_volatility": "标准化低波动",
    "total_score": "总分",
    "selected": "入选",
    "benchmark_equity": "基准权益",
    "benchmark_daily_return": "基准单期收益",
    "excess_daily_return": "超额单期收益",
    "buy_turnover": "买入换手",
    "sell_turnover": "卖出换手",
    "turnover": "总换手",
    "cost": "交易成本",
    "metric": "指标代码",
    "label": "指标名称",
    "value": "数值",
    "total_return": "总收益",
    "annualized_return": "年化收益",
    "max_drawdown": "最大回撤",
    "volatility": "波动率",
    "downside_volatility": "下行波动率",
    "sharpe": "夏普比率",
    "sortino": "索提诺比率",
    "calmar": "卡玛比率",
    "win_rate": "胜率",
    "average_turnover": "平均换手",
    "total_cost": "总成本",
    "health_score": "策略健康评分",
    "health_grade": "策略健康等级",
    "gate_status": "策略闸门状态",
    "gate_failures": "策略闸门失败数",
    "health_warnings": "策略预警数",
    "critical_warnings": "严重预警数",
    "periods": "周期数",
    "benchmark_total_return": "基准总收益",
    "benchmark_annualized_return": "基准年化收益",
    "benchmark_volatility": "基准波动率",
    "benchmark_max_drawdown": "基准最大回撤",
    "excess_return": "超额收益",
    "tracking_error": "跟踪误差",
    "information_ratio": "信息比率",
    "beta": "Beta",
    "daily_alpha": "日度Alpha",
    "annualized_alpha": "年化Alpha",
    "correlation": "相关系数",
    "r_squared": "R平方",
    "run_id": "内部编号",
    "scheme_label": "方案编号",
    "output_dir": "输出目录",
    "rank": "名次",
    "initial_cash": "初始资金",
    "top_n": "持仓数量TopN",
    "selection_mode": "选股方向",
    "score_source": "评分来源",
    "lot_size": "每手股数",
    "max_group_positions": "单组最多入选数",
    "rebalance_every_n_days": "调仓间隔天数",
    "lookback_momentum": "动量回看窗口",
    "lookback_mean_reversion": "均值回归回看窗口",
    "lookback_volatility": "波动率回看窗口",
    "rolling_risk_window": "滚动风险窗口",
    "max_allowed_drawdown": "闸门最大回撤",
    "max_allowed_daily_var": "闸门最大日VaR",
    "min_allowed_rolling_return": "闸门最差滚动收益",
    "min_allowed_information_ratio": "闸门最低信息比率",
    "min_allowed_fill_rate": "闸门最低成交率",
    "min_allowed_execution_price_coverage": "闸门最低执行价覆盖率",
    "min_allowed_factor_score_coverage": "闸门最低外部评分覆盖率",
    "max_allowed_position_weight": "闸门最大单票权重",
    "max_allowed_group_weight": "闸门最大分组权重",
    "max_allowed_attribution_residual": "闸门最大归因残差",
    "commission_rate": "佣金率",
    "buy_commission_rate": "买入佣金率",
    "sell_commission_rate": "卖出佣金率",
    "slippage_rate": "滑点率",
    "market_impact_coefficient": "冲击成本系数",
    "market_impact_exponent": "冲击成本指数",
    "stamp_duty_rate": "印花税率",
    "min_commission": "最低佣金",
    "transfer_fee_rate": "过户费率",
    "target_cash_weight": "目标现金权重",
    "max_position_weight": "单票目标权重上限",
    "limit_up_down_rate": "涨跌停阈值",
    "st_limit_up_down_rate": "ST涨跌停阈值",
    "growth_limit_up_down_rate": "成长板涨跌停阈值",
    "bse_limit_up_down_rate": "北交所涨跌停阈值",
    "infer_limit_rate_by_symbol": "按代码推断涨跌停",
    "max_volume_participation": "最大成交量参与率",
    "infer_limit_flags": "自动推断涨跌停",
    "forward_fill_suspended_bars": "缺失行情前值停牌估值",
    "price_field": "价格字段",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "equity_curve_csv": "净值曲线CSV",
    "config_effective_json": "最终生效配置JSON",
    "run_manifest_json": "运行清单JSON",
    "equity_curve_svg": "净值曲线图",
    "positions_csv": "每日持仓账本CSV",
    "trades_csv": "逐笔交易明细CSV",
    "trade_attempts_csv": "未成交原因CSV",
    "factor_scores_csv": "因子评分明细CSV",
    "factor_ic_csv": "因子IC分析CSV",
    "factor_ic_json": "因子IC分析JSON",
    "factor_group_returns_csv": "因子分组收益CSV",
    "factor_group_returns_json": "因子分组收益JSON",
    "factor_decay_csv": "因子衰减分析CSV",
    "factor_decay_json": "因子衰减分析JSON",
    "factor_correlation_csv": "因子相关性矩阵CSV",
    "factor_correlation_json": "因子相关性矩阵JSON",
    "drawdown_csv": "回撤序列CSV",
    "drawdown_json": "回撤序列JSON",
    "monthly_returns_csv": "月度收益CSV",
    "monthly_returns_json": "月度收益JSON",
    "rolling_risk_csv": "滚动风险CSV",
    "rolling_risk_json": "滚动风险JSON",
    "relative_performance_csv": "相对基准表现CSV",
    "relative_performance_json": "相对基准表现JSON",
    "execution_quality_csv": "执行质量CSV",
    "execution_quality_json": "执行质量JSON",
    "exposure_csv": "持仓暴露CSV",
    "exposure_json": "持仓暴露JSON",
    "group_exposure_csv": "分组暴露CSV",
    "group_exposure_json": "分组暴露JSON",
    "return_attribution_csv": "收益归因CSV",
    "return_attribution_json": "收益归因JSON",
    "cost_attribution_csv": "成本归因CSV",
    "cost_attribution_json": "成本归因JSON",
    "pnl_ledger_csv": "盈亏对账CSV",
    "pnl_ledger_json": "盈亏对账JSON",
    "strategy_health_csv": "策略健康诊断CSV",
    "strategy_health_gates_csv": "策略风险闸门CSV",
    "strategy_health_json": "策略健康诊断JSON",
    "rebalance_log_csv": "调仓日志CSV",
    "performance_summary_csv": "绩效汇总CSV",
    "performance_summary_json": "绩效汇总JSON",
    "report_html": "单次回测报告",
    "batch_summary_csv": "参数扫描汇总CSV",
    "batch_summary_json": "参数扫描汇总JSON",
    "batch_leaderboard_csv": "最优结果排行CSV",
    "batch_leaderboard_json": "最优结果排行JSON",
    "best_run_json": "最佳方案JSON",
    "batch_chart_svg": "参数对比图",
    "batch_heatmap_svg": "参数热力图",
    "batch_stability_csv": "参数稳定性CSV",
    "batch_stability_json": "参数稳定性JSON",
    "parameter_sensitivity_csv": "参数敏感度CSV",
    "walk_forward_csv": "Walk-forward汇总CSV",
    "walk_forward_json": "Walk-forward汇总JSON",
    "walk_forward_report_html": "Walk-forward报告",
    "walk_forward_optimization_csv": "Walk-forward优化CSV",
    "walk_forward_optimization_json": "Walk-forward优化JSON",
    "walk_forward_optimization_report_html": "Walk-forward优化报告",
}

_HUMAN_READABLE_ENCODING = "utf-8-sig"

_METRIC_EXPLANATIONS = {
    "total_return": "总收益 = 期末权益 / 期初权益 - 1。",
    "annualized_return": "按 252 个交易日折算后的年化收益率。",
    "max_drawdown": "历史净值从阶段高点回落的最大幅度。",
    "volatility": "组合日收益率折算后的年化波动率。",
    "downside_volatility": "仅统计下跌收益后的年化波动率。",
    "sharpe": "年化平均超额收益与总波动率之比。",
    "sortino": "年化收益与下行波动率之比。",
    "calmar": "年化收益与最大回撤绝对值之比。",
    "win_rate": "收益为正的周期占全部周期的比例。",
    "average_turnover": "每次调仓的平均换手比例。",
    "total_cost": "全部调仓累计产生的交易成本。",
    "periods": "本次回测实际计算的收益周期数量。",
    "benchmark_total_return": "基准从期初到期末的总收益。",
    "benchmark_annualized_return": "基准按 252 个交易日折算后的年化收益率。",
    "benchmark_volatility": "基准日收益率折算后的年化波动率。",
    "benchmark_max_drawdown": "基准净值从阶段高点回落的最大幅度。",
    "excess_return": "组合总收益减去基准总收益。",
    "tracking_error": "组合相对基准的超额收益波动率。",
    "information_ratio": "平均超额收益与跟踪误差之比。",
    "beta": "组合日收益相对基准日收益的市场暴露。",
    "annualized_alpha": "在零无风险利率口径下，剔除 beta 暴露后的年化超额收益。",
    "r_squared": "基准日收益解释组合日收益波动的比例。",
}

_DEFAULT_A_SHARE_SYMBOL_NAMES = {
    "000001": "平安银行",
    "600036": "招商银行",
    "600519": "贵州茅台",
    "601318": "中国平安",
    "300750": "宁德时代",
}


def print_summary(
    curve: list[EquityPoint],
    rebalances: list[RebalanceRecord],
    metrics: BacktestMetrics,
    config: BacktestConfig,
) -> None:
    print("=" * 60)
    print("A股回测摘要")
    print(f"周期数:       {metrics.periods}")
    print(f"调仓次数:     {len(rebalances)}")
    print(f"期初权益:     {config.initial_cash:,.2f}")
    print(f"期末权益:     {curve[-1].equity:,.2f}")
    print(f"总收益:       {metrics.total_return:.2%}")
    print(f"年化收益:     {metrics.annualized_return:.2%}")
    print(f"最大回撤:     {metrics.max_drawdown:.2%}")
    print(f"波动率:       {metrics.volatility:.2%}")
    print(f"下行波动率:   {metrics.downside_volatility:.2%}")
    print(f"夏普比率:     {metrics.sharpe:.3f}")
    print(f"索提诺比率:   {metrics.sortino:.3f}")
    print(f"卡玛比率:     {metrics.calmar:.3f}")
    print(f"胜率:         {metrics.win_rate:.2%}")
    print(f"平均换手:     {metrics.average_turnover:.2%}")
    print(f"总成本:       {metrics.total_cost:,.2f}")
    if metrics.benchmark_total_return is not None:
        print(f"基准总收益:   {metrics.benchmark_total_return:.2%}")
        print(f"跟踪误差:     {metrics.tracking_error:.2%}")
        print(f"超额收益:     {metrics.excess_return:.2%}")
        print(f"信息比率:     {metrics.information_ratio:.3f}")
    print("=" * 60)


def save_equity_curve(
    curve: list[EquityPoint],
    output_dir: Path,
    benchmark_curve: list[BenchmarkPoint] | None = None,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "equity_curve.csv"
    benchmark_by_date = {point.date: point for point in benchmark_curve or []}

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                _display_label("date"),
                _display_label("equity"),
                "权益展示 / equity_display",
                _display_label("daily_return"),
                "单期收益率展示 / daily_return_pct",
                _display_label("holdings"),
                "持仓展示 / holdings_display",
                "持仓数量 / holding_count",
                _display_label("benchmark_equity"),
                "基准权益展示 / benchmark_equity_display",
                _display_label("benchmark_daily_return"),
                "基准单期收益率展示 / benchmark_daily_return_pct",
                _display_label("excess_daily_return"),
                "超额单期收益率展示 / excess_daily_return_pct",
                "备注 / note",
            ]
        )
        for point in curve:
            benchmark_point = benchmark_by_date.get(point.date)
            benchmark_columns = _build_equity_curve_benchmark_columns(point, benchmark_point)
            writer.writerow(
                [
                    point.date.isoformat(),
                    f"{point.equity:.2f}",
                    _format_money(point.equity),
                    f"{point.daily_return:.8f}",
                    _format_pct(point.daily_return),
                    "|".join(point.holdings),
                    _format_holdings(point.holdings, symbol_names),
                    str(len(point.holdings)),
                    *benchmark_columns,
                    _equity_curve_note(point, benchmark_point is not None),
                ]
            )

    return target_path


def save_rebalance_log(
    rebalances: list[RebalanceRecord],
    output_dir: Path,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "rebalance_log.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                _display_label("date"),
                _display_label("holdings"),
                "持仓展示 / holdings_display",
                "持仓数量 / holding_count",
                _display_label("buy_turnover"),
                "买入换手率展示 / buy_turnover_pct",
                _display_label("sell_turnover"),
                "卖出换手率展示 / sell_turnover_pct",
                _display_label("turnover"),
                "总换手率展示 / turnover_pct",
                _display_label("cost"),
                "交易成本展示 / cost_display",
                "备注 / note",
            ]
        )
        for record in rebalances:
            writer.writerow(
                [
                    record.date.isoformat(),
                    "|".join(record.holdings),
                    _format_holdings(record.holdings, symbol_names),
                    str(len(record.holdings)),
                    f"{record.buy_turnover:.8f}",
                    _format_pct(record.buy_turnover),
                    f"{record.sell_turnover:.8f}",
                    _format_pct(record.sell_turnover),
                    f"{record.turnover:.8f}",
                    _format_pct(record.turnover),
                    f"{record.cost:.2f}",
                    _format_money(record.cost),
                    _rebalance_note(record),
                ]
            )

    return target_path


def save_positions(
    positions: list[PositionPoint],
    output_dir: Path,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "positions.csv"

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                _display_label("date"),
                _display_label("symbol"),
                "代码展示 / symbol_display",
                _display_label("shares"),
                _display_label("price"),
                _display_label("market_value"),
                "市值展示 / market_value_display",
                _display_label("weight"),
                "权重展示 / weight_pct",
                _display_label("cash"),
                "现金展示 / cash_display",
                _display_label("total_equity"),
                "总权益展示 / total_equity_display",
            ]
        )
        for point in positions:
            writer.writerow(
                [
                    point.date.isoformat(),
                    point.symbol,
                    _format_symbol(point.symbol, symbol_names),
                    str(point.shares),
                    f"{point.price:.4f}",
                    f"{point.market_value:.2f}",
                    _format_money(point.market_value),
                    f"{point.weight:.8f}",
                    _format_pct(point.weight),
                    f"{point.cash:.2f}",
                    _format_money(point.cash),
                    f"{point.total_equity:.2f}",
                    _format_money(point.total_equity),
                ]
            )

    return target_path


def save_trades(
    trades: list[TradeRecord],
    output_dir: Path,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    return save_trades_csv(
        trades,
        output_dir,
        format_symbol=lambda symbol: _format_symbol(symbol, symbol_names),
        display_label=_display_label,
        format_money=_format_money,
    )


def save_trade_attempts(
    attempts: list[TradeAttemptRecord],
    output_dir: Path,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    return save_trade_attempts_csv(
        attempts,
        output_dir,
        format_symbol=lambda symbol: _format_symbol(symbol, symbol_names),
        display_label=_display_label,
        format_money=_format_money,
    )


def save_factor_scores(
    records: list[FactorScoreRecord],
    output_dir: Path,
    *,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    return save_factor_scores_csv(
        records,
        output_dir,
        format_symbol=lambda symbol: _format_symbol(symbol, symbol_names),
        display_label=_display_label,
    )


def save_performance_summary(metrics: BacktestMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.csv"

    summary_items = _build_performance_summary_items(metrics)

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                _display_label("metric"),
                _display_label("label"),
                "说明 / description",
                _display_label("value"),
            ]
        )
        writer.writerows(summary_items)

    return target_path


def save_performance_summary_json(
    metrics: BacktestMetrics,
    output_dir: Path,
    *,
    extra_payload: dict[str, object] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.json"
    payload: dict[str, object] = {
        "total_return": metrics.total_return,
        "annualized_return": metrics.annualized_return,
        "max_drawdown": metrics.max_drawdown,
        "volatility": metrics.volatility,
        "downside_volatility": metrics.downside_volatility,
        "sharpe": metrics.sharpe,
        "sortino": metrics.sortino,
        "calmar": metrics.calmar,
        "win_rate": metrics.win_rate,
        "average_turnover": metrics.average_turnover,
        "total_cost": metrics.total_cost,
        "periods": metrics.periods,
        "benchmark_total_return": metrics.benchmark_total_return,
        "benchmark_annualized_return": metrics.benchmark_annualized_return,
        "benchmark_volatility": metrics.benchmark_volatility,
        "benchmark_max_drawdown": metrics.benchmark_max_drawdown,
        "excess_return": metrics.excess_return,
        "tracking_error": metrics.tracking_error,
        "information_ratio": metrics.information_ratio,
    }
    if extra_payload:
        payload.update(extra_payload)
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return target_path


def save_run_manifest(
    *,
    output_dir: Path,
    config: BacktestConfig,
    inputs: dict[str, str | bool | None],
    artifacts: dict[str, Path],
    metrics: BacktestMetrics,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "run_manifest.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": _serialize_config(config),
        "inputs": inputs,
        "input_files": _build_input_file_metadata(inputs),
        "artifacts": {name: str(path) for name, path in artifacts.items()},
        "artifact_files": _build_artifact_file_metadata(artifacts),
        "metrics": asdict(metrics),
        "environment": _build_environment_metadata(),
        "git": _build_git_metadata(),
    }
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return target_path


def save_effective_config(
    *,
    output_dir: Path,
    config: BacktestConfig,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "config_effective.json"
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(_serialize_config(config), handle, ensure_ascii=False, indent=2)
    return target_path


def save_single_run_report_html(
    *,
    output_dir: Path,
    config: BacktestConfig,
    metrics: BacktestMetrics,
    artifacts: dict[str, Path],
    latest_holdings: tuple[str, ...] = (),
    latest_rebalance: RebalanceRecord | None = None,
    symbol_names: dict[str, str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "report.html"
    conclusion = _build_report_conclusion(metrics)
    holdings_summary = _format_holdings(latest_holdings, symbol_names)
    turnover_summary = _format_pct(metrics.average_turnover)
    rebalance_rows = _build_rebalance_summary_rows(latest_rebalance, symbol_names)
    has_benchmark = _has_benchmark_metrics(metrics)
    benchmark_section = ""
    rows = _build_single_run_metric_rows(metrics)
    review_rows = _build_single_run_review_rows(artifacts)
    trading_behavior_rows = _build_trading_behavior_rows(artifacts)
    data_quality_rows = _build_data_quality_rows(artifacts)

    artifact_links = _build_artifact_links(artifacts)
    summary_card_items = [
        _summary_card("总收益", f"{metrics.total_return:.2%}"),
        _summary_card("年化收益", f"{metrics.annualized_return:.2%}"),
        _summary_card("最大回撤", f"{metrics.max_drawdown:.2%}"),
        _summary_card("夏普比率", f"{metrics.sharpe:.3f}"),
    ]
    if has_benchmark:
        summary_card_items.append(_summary_card("超额收益", f"{metrics.excess_return:.2%}"))
        benchmark_section = f"""
    <div class="card">
      <h2>基准复盘</h2>
      <p class="lead">{escape(_build_benchmark_conclusion(metrics))}</p>
      <table>{_build_benchmark_summary_rows(metrics)}</table>
    </div>"""
    summary_cards = "\n".join(summary_card_items)
    metrics_rows = _build_html_table_rows(rows)
    review_table_rows = _build_html_table_rows(review_rows)
    trading_behavior_table_rows = _build_html_table_rows(trading_behavior_rows)
    data_quality_table_rows = _build_html_table_rows(data_quality_rows)
    factor_rows = "\n".join(
        f"<tr><th>因子 / {escape(name)}</th><td>{weight:.4f}</td></tr>"
        for name, weight in config.factor_weights.items()
    )
    explanation_rows = "\n".join(
        f"<tr><th>{escape(_display_label(key))}</th><td>{escape(_metric_explanation(key))}</td></tr>"
        for key in ("total_return", "annualized_return", "max_drawdown", "sharpe")
    )
    holdings_rows = "\n".join(
        f"<tr><th>{escape(symbol)}</th><td>{escape(_format_symbol(symbol, symbol_names))}</td></tr>"
        for symbol in latest_holdings
    )
    if not holdings_rows:
        holdings_rows = "<tr><th>-</th><td>当前结果没有持仓数据。</td></tr>"
    chart_name = artifacts["equity_curve_svg"].name if "equity_curve_svg" in artifacts else ""
    chart_title = "策略与基准净值" if has_benchmark else "策略净值走势"
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>回测报告</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; background: #f8fafc; }}
    h1, h2 {{ margin: 0 0 16px; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 24px; align-items: start; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 0; border-bottom: 1px solid #eef2f7; }}
    th {{ width: 55%; color: #52606d; font-weight: 600; }}
    ul {{ margin: 0; padding-left: 20px; }}
    img {{ width: 100%; border: 1px solid #d9e2ec; border-radius: 10px; background: white; }}
    .muted {{ color: #52606d; margin-bottom: 16px; }}
    .wide {{ grid-column: 1 / -1; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef6ff 100%); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-top: 20px; }}
    .summary-tile {{ border: 1px solid #d9e2ec; border-radius: 12px; padding: 14px; background: #fff; }}
    .summary-label {{ color: #52606d; font-size: 12px; margin-bottom: 6px; }}
    .summary-value {{ font-size: 24px; font-weight: 700; color: #102a43; }}
    .lead {{ font-size: 16px; line-height: 1.7; color: #243b53; }}
    .compact td, .compact th {{ font-size: 14px; }}
  </style>
</head>
<body>
  <h1>回测报告</h1>
  <p class="muted">生成时间：{escape(datetime.now().isoformat(timespec="seconds"))}</p>
  <div class="grid">
    <div class="card wide hero">
      <h2>核心结论</h2>
      <p class="lead">{escape(conclusion)}</p>
      <div class="summary-grid">{summary_cards}</div>
    </div>
    <div class="card">
      <h2>{chart_title}</h2>
      <img src="{escape(chart_name)}" alt="{escape(chart_title)}" />
    </div>
    <div class="card">
      <h2>当前持仓</h2>
      <table>
        <tr><th>持仓概览</th><td>{escape(holdings_summary)}</td></tr>
        <tr><th>持仓数量</th><td>{len(latest_holdings)}</td></tr>
        <tr><th>平均换手</th><td>{escape(turnover_summary)}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>调仓摘要</h2>
      <table>{rebalance_rows}</table>
    </div>
    {benchmark_section}
    <div class="card">
      <h2>指标明细</h2>
      <table>{metrics_rows}</table>
    </div>
    <div class="card">
      <h2>复盘摘要</h2>
      <table class="compact">{review_table_rows}</table>
    </div>
    <div class="card">
      <h2>Trading Behavior Diagnostics</h2>
      <table class="compact">{trading_behavior_table_rows}</table>
    </div>
    <div class="card">
      <h2>Data Quality Diagnostics</h2>
      <table class="compact">{data_quality_table_rows}</table>
    </div>
    <div class="card">
      <h2>配置摘要</h2>
      <table>
        <tr><th>{_display_label("initial_cash")}</th><td>{config.initial_cash:,.2f}</td></tr>
        <tr><th>{_display_label("top_n")}</th><td>{config.top_n}</td></tr>
        <tr><th>{_display_label("selection_mode")}</th><td>{escape(config.selection_mode)}</td></tr>
        <tr><th>{_display_label("score_source")}</th><td>{escape(config.score_source)}</td></tr>
        <tr><th>{_display_label("lot_size")}</th><td>{config.lot_size}</td></tr>
        <tr><th>{_display_label("max_group_positions")}</th><td>{_format_optional_int(config.max_group_positions)}</td></tr>
        <tr><th>{_display_label("rolling_risk_window")}</th><td>{config.rolling_risk_window}</td></tr>
        <tr><th>{_display_label("max_allowed_drawdown")}</th><td>{config.max_allowed_drawdown:.2%}</td></tr>
        <tr><th>{_display_label("max_allowed_daily_var")}</th><td>{config.max_allowed_daily_var:.2%}</td></tr>
        <tr><th>{_display_label("min_allowed_rolling_return")}</th><td>{config.min_allowed_rolling_return:.2%}</td></tr>
        <tr><th>{_display_label("min_allowed_information_ratio")}</th><td>{config.min_allowed_information_ratio:.3f}</td></tr>
        <tr><th>{_display_label("min_allowed_fill_rate")}</th><td>{config.min_allowed_fill_rate:.2%}</td></tr>
        <tr><th>{_display_label("min_allowed_execution_price_coverage")}</th><td>{config.min_allowed_execution_price_coverage:.2%}</td></tr>
        <tr><th>{_display_label("max_allowed_position_weight")}</th><td>{config.max_allowed_position_weight:.2%}</td></tr>
        <tr><th>{_display_label("max_allowed_group_weight")}</th><td>{config.max_allowed_group_weight:.2%}</td></tr>
        <tr><th>{_display_label("max_allowed_attribution_residual")}</th><td>{config.max_allowed_attribution_residual:.2%}</td></tr>
        <tr><th>{_display_label("rebalance_every_n_days")}</th><td>{config.rebalance_every_n_days}</td></tr>
        <tr><th>{_display_label("price_field")}</th><td>{escape(config.price_field)}</td></tr>
        <tr><th>{_display_label("start_date")}</th><td>{_format_optional_date(config.start_date)}</td></tr>
        <tr><th>{_display_label("end_date")}</th><td>{_format_optional_date(config.end_date)}</td></tr>
        <tr><th>{_display_label("commission_rate")}</th><td>{config.commission_rate:.6f}</td></tr>
        <tr><th>{_display_label("buy_commission_rate")}</th><td>{_format_optional_rate(config.buy_commission_rate)}</td></tr>
        <tr><th>{_display_label("sell_commission_rate")}</th><td>{_format_optional_rate(config.sell_commission_rate)}</td></tr>
        <tr><th>{_display_label("slippage_rate")}</th><td>{config.slippage_rate:.6f}</td></tr>
        <tr><th>{_display_label("market_impact_coefficient")}</th><td>{config.market_impact_coefficient:.6f}</td></tr>
        <tr><th>{_display_label("market_impact_exponent")}</th><td>{config.market_impact_exponent:.6f}</td></tr>
        <tr><th>{_display_label("stamp_duty_rate")}</th><td>{config.stamp_duty_rate:.6f}</td></tr>
        <tr><th>{_display_label("min_commission")}</th><td>{config.min_commission:.2f}</td></tr>
        <tr><th>{_display_label("transfer_fee_rate")}</th><td>{config.transfer_fee_rate:.6f}</td></tr>
        <tr><th>{_display_label("target_cash_weight")}</th><td>{config.target_cash_weight:.2%}</td></tr>
        <tr><th>{_display_label("max_position_weight")}</th><td>{config.max_position_weight:.2%}</td></tr>
        <tr><th>{_display_label("infer_limit_flags")}</th><td>{config.infer_limit_flags}</td></tr>
        <tr><th>{_display_label("forward_fill_suspended_bars")}</th><td>{config.forward_fill_suspended_bars}</td></tr>
        <tr><th>{_display_label("limit_up_down_rate")}</th><td>{config.limit_up_down_rate:.4f}</td></tr>
        <tr><th>{_display_label("st_limit_up_down_rate")}</th><td>{config.st_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{_display_label("growth_limit_up_down_rate")}</th><td>{config.growth_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{_display_label("bse_limit_up_down_rate")}</th><td>{config.bse_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{_display_label("infer_limit_rate_by_symbol")}</th><td>{config.infer_limit_rate_by_symbol}</td></tr>
        <tr><th>{_display_label("max_volume_participation")}</th><td>{config.max_volume_participation:.4f}</td></tr>
      </table>
      <h2 style="margin-top:20px;">因子权重</h2>
      <table>{factor_rows}</table>
    </div>
    <div class="card">
      <h2>产物清单</h2>
      <ul>{artifact_links}</ul>
    </div>
    <div class="card wide">
      <h2>指标怎么看</h2>
      <table>{explanation_rows}</table>
    </div>
    <div class="card wide">
      <h2>持仓代码说明</h2>
      <table>{holdings_rows}</table>
    </div>
  </div>
</body>
</html>
"""
    target_path.write_text(html, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def save_batch_summary(rows: list[dict[str, object]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "batch_summary.csv"
    json_path = output_dir / "batch_summary.json"

    if not rows:
        headers = ["scheme_label", "run_id"]
    else:
        headers = _build_batch_export_headers(list(rows[0].keys()))

    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([_display_label(header) for header in headers])
        for row_index, row in enumerate(rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, row_index))

    summary_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reader_friendly": _build_batch_json_summary(rows),
        "rows": rows,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, ensure_ascii=False, indent=2)

    return csv_path, json_path


def save_equity_chart_svg(
    curve: list[EquityPoint],
    output_dir: Path,
    benchmark_curve: list[BenchmarkPoint] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "equity_curve.svg"

    portfolio_points = [(point.date.isoformat(), point.equity) for point in curve]
    benchmark_points = (
        [(point.date.isoformat(), point.equity) for point in benchmark_curve]
        if benchmark_curve
        else []
    )
    title = "策略与基准净值" if benchmark_points else "策略净值走势"
    svg = _build_line_chart_svg(
        title=title,
        series=[
            ("策略净值", portfolio_points, "#0b7285"),
            ("基准净值", benchmark_points, "#e67700"),
        ],
        y_axis_label="净值",
    )
    target_path.write_text(svg, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def save_batch_rankings(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    rank_by: str = "annualized_return",
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_rank_metric(rows, rank_by)
    ranked_rows = _sort_rows_by_metric(rows, rank_by)
    for index, row in enumerate(ranked_rows, start=1):
        row["rank"] = index

    csv_path = output_dir / "batch_leaderboard.csv"
    json_path = output_dir / "batch_leaderboard.json"
    best_run_path = output_dir / "best_run.json"

    headers = _build_batch_export_headers(list(ranked_rows[0].keys())) if ranked_rows else ["rank", "scheme_label", "run_id"]
    with csv_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([_display_label(header) for header in headers])
        for row_index, row in enumerate(ranked_rows, start=1):
            writer.writerow(_build_batch_export_row(row, headers, row_index))

    leaderboard_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rank_by": rank_by,
        "ranking_policy": "gate_pass_first_then_metric",
        "reader_friendly": _build_ranked_batch_json_summary(ranked_rows, rank_by),
        "rows": ranked_rows,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(leaderboard_payload, handle, ensure_ascii=False, indent=2)

    best_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rank_by": rank_by,
        "ranking_policy": "gate_pass_first_then_metric",
        "reader_friendly": _build_best_run_json_summary(ranked_rows[0] if ranked_rows else None, rank_by),
        "best_run": ranked_rows[0] if ranked_rows else None,
    }
    with best_run_path.open("w", encoding="utf-8") as handle:
        json.dump(best_payload, handle, ensure_ascii=False, indent=2)

    return csv_path, json_path, best_run_path


def _build_batch_export_headers(headers: list[str]) -> list[str]:
    ordered_headers = [header for header in headers if header != "run_id"]
    insert_at = ordered_headers.index("rank") + 1 if "rank" in ordered_headers else 0
    ordered_headers[insert_at:insert_at] = ["scheme_label", "run_id"]
    return ordered_headers


def _build_batch_json_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "trial_count": len(rows),
        "trial_labels": [
            _format_run_label(row, row_index)
            for row_index, row in enumerate(rows, start=1)
        ],
        "notes": "rows 字段保留完整机器可读结果；reader_friendly 字段用于直接阅读。",
    }


def _build_ranked_batch_json_summary(
    ranked_rows: list[dict[str, object]],
    rank_by: str,
) -> dict[str, object]:
    best_row = ranked_rows[0] if ranked_rows else None
    worst_row = ranked_rows[-1] if ranked_rows else None
    return {
        "rank_metric": _display_label(rank_by),
        "best_scheme": None if best_row is None else _format_run_label(best_row, 1),
        "best_internal_id": None if best_row is None else str(best_row.get("run_id", "")),
        "best_gate_status": None if best_row is None else str(best_row.get("gate_status", "")),
        "best_health_score": None if best_row is None else _format_metric_value("health_score", best_row.get("health_score")),
        "best_metric_value": None if best_row is None else _format_metric_value(rank_by, best_row.get(rank_by)),
        "worst_scheme": None if worst_row is None else _format_run_label(worst_row, len(ranked_rows)),
        "worst_internal_id": None if worst_row is None else str(worst_row.get("run_id", "")),
        "worst_gate_status": None if worst_row is None else str(worst_row.get("gate_status", "")),
        "worst_metric_value": None if worst_row is None else _format_metric_value(rank_by, worst_row.get(rank_by)),
        "notes": "rows 字段按排序后的完整结果保留。",
    }


def _build_best_run_json_summary(
    best_row: dict[str, object] | None,
    rank_by: str,
) -> dict[str, object]:
    if best_row is None:
        return {
            "best_scheme": None,
            "best_internal_id": None,
            "best_gate_status": None,
            "best_health_score": None,
            "rank_metric": _display_label(rank_by),
            "best_metric_value": None,
        }
    return {
        "best_scheme": _format_run_label(best_row, 1),
        "best_internal_id": str(best_row.get("run_id", "")),
        "best_gate_status": str(best_row.get("gate_status", "")),
        "best_health_score": _format_metric_value("health_score", best_row.get("health_score")),
        "rank_metric": _display_label(rank_by),
        "best_metric_value": _format_metric_value(rank_by, best_row.get(rank_by)),
    }


def _build_batch_export_row(
    row: dict[str, object],
    headers: list[str],
    row_index: int,
) -> list[object]:
    return [_build_batch_display_value(row, header, row_index) for header in headers]


def _build_batch_display_value(row: dict[str, object], header: str, row_index: int) -> object:
    if header == "scheme_label":
        return _format_run_label(row, row_index)
    return row.get(header, "")


def save_batch_chart_svg(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    metric: str = "annualized_return",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_rank_metric(rows, metric)
    target_path = output_dir / f"batch_{metric}.svg"
    points = [
        (_format_run_label(row, row_index), _float_metric(row, metric))
        for row_index, row in enumerate(rows, start=1)
        if metric in row and row[metric] not in ("", None)
    ]
    svg = _build_bar_chart_svg(
        title=f"{_chinese_label(metric)}参数对比图",
        points=points,
        bar_color="#5c7cfa",
        y_axis_label=_display_label(metric),
    )
    target_path.write_text(svg, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def _format_run_label(row: dict[str, object], row_index: int) -> str:
    run_id = str(row.get("run_id", "")).strip()
    if run_id.startswith("run_"):
        numeric_part = run_id.removeprefix("run_").lstrip("0") or "0"
        return f"方案{numeric_part}"
    if run_id:
        return run_id
    return f"方案{row_index}"


def save_batch_heatmap_svg(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    x_field: str,
    y_field: str,
    metric: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_rank_metric(rows, metric)
    target_path = output_dir / f"batch_{metric}_heatmap.svg"

    points = [
        (str(row[x_field]), str(row[y_field]), _float_metric(row, metric))
        for row in rows
        if x_field in row and y_field in row and metric in row
    ]
    svg = _build_heatmap_svg(
        title=f"{_chinese_label(metric)}参数热力图",
        x_label=_display_label(x_field),
        y_label=_display_label(y_field),
        points=points,
    )
    target_path.write_text(svg, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def save_batch_report_html(
    *,
    output_dir: Path,
    rows: list[dict[str, object]],
    rank_by: str,
    artifacts: dict[str, Path],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    _validate_rank_metric(rows, rank_by)
    target_path = output_dir / "batch_report.html"
    sorted_rows = _sort_rows_by_metric(rows, rank_by)
    top_rows = sorted_rows[:10]
    best_row = sorted_rows[0] if sorted_rows else None
    headers = [
        "scheme_label",
        "run_id",
        "gate_status",
        "health_score",
        "gate_failures",
        rank_by,
        "total_return",
        "sharpe",
        "sortino",
        "calmar",
    ]
    table_rows = "\n".join(
        "<tr>"
        + "".join(
            f"<td>{escape(str(_build_batch_display_value(row, header, row_index)))}</td>"
            for header in headers
        )
        + "</tr>"
        for row_index, row in enumerate(top_rows, start=1)
    )
    summary_cards = _build_batch_summary_cards(best_row, rank_by, len(sorted_rows))
    parameter_rows = _build_batch_parameter_rows(best_row)
    observation_rows = _build_batch_observation_rows(sorted_rows, rank_by, artifacts)
    artifact_links = _build_artifact_links(artifacts)
    chart_blocks = _build_batch_chart_blocks(artifacts)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>A股参数研究报告</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; background: #f8fafc; }}
    h1, h2 {{ margin: 0 0 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef2f7; font-size: 14px; }}
    th {{ color: #52606d; font-weight: 600; }}
    ul {{ margin: 0; padding-left: 20px; }}
    img {{ width: 100%; border: 1px solid #d9e2ec; border-radius: 10px; background: white; }}
    .muted {{ color: #52606d; margin-bottom: 16px; }}
    .wide {{ grid-column: 1 / -1; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef6ff 100%); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }}
    .summary-tile {{ border: 1px solid #d9e2ec; border-radius: 12px; padding: 14px; background: #fff; }}
    .summary-label {{ color: #52606d; font-size: 12px; margin-bottom: 6px; }}
    .summary-value {{ font-size: 24px; font-weight: 700; color: #102a43; }}
    .lead {{ font-size: 16px; line-height: 1.7; color: #243b53; }}
  </style>
</head>
<body>
  <h1>A股参数扫描报告</h1>
  <p class="muted">生成时间：{escape(datetime.now().isoformat(timespec="seconds"))}。排序指标：{escape(_display_label(rank_by))}。</p>
  <div class="grid">
    <div class="card wide hero">
      <h2>研究结论</h2>
      <p class="lead">{escape(_build_batch_conclusion(best_row, rank_by, len(sorted_rows)))}</p>
      <div class="summary-grid">{summary_cards}</div>
    </div>
    <div class="card">
      <h2>最优参数</h2>
      <table>{parameter_rows}</table>
    </div>
    <div class="card">
      <h2>结果观察</h2>
      <table>{observation_rows}</table>
    </div>
    <div class="card">
      <h2>最优结果</h2>
      <table>
        <thead><tr>{"".join(f"<th>{escape(_display_label(header))}</th>" for header in headers)}</tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>产物清单</h2>
      <ul>{artifact_links}</ul>
    </div>
    {"".join(chart_blocks)}
  </div>
</body>
</html>
"""
    target_path.write_text(html, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def save_walk_forward_report_html(
    *,
    output_dir: Path,
    analysis: dict[str, object],
    optimization: bool = False,
    artifacts: dict[str, Path] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_name = "walk_forward_optimization_report.html" if optimization else "walk_forward_report.html"
    target_path = output_dir / target_name
    rows = _analysis_rows(analysis)
    summary = _analysis_summary_dict(analysis)
    title = "A股Walk-forward优化报告" if optimization else "A股Walk-forward验证报告"
    conclusion = (
        _build_walk_forward_optimization_conclusion(summary)
        if optimization
        else _build_walk_forward_conclusion(summary)
    )
    summary_cards = (
        _build_walk_forward_optimization_summary_cards(summary)
        if optimization
        else _build_walk_forward_summary_cards(summary)
    )
    observation_rows = (
        _build_walk_forward_optimization_observation_rows(summary)
        if optimization
        else _build_walk_forward_observation_rows(summary)
    )
    headers = (
        [
            "window_id",
            "train_start_date",
            "test_end_date",
            "train_annualized_return",
            "test_annualized_return",
            "train_test_annualized_gap",
            "test_to_train_efficiency",
            "is_degraded_out_of_sample",
            "test_max_drawdown",
        ]
        if optimization
        else [
            "window_id",
            "start_date",
            "end_date",
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe",
            "win_rate",
        ]
    )
    table_rows = _build_analysis_preview_rows(rows, headers)
    artifact_links = _build_artifact_links(artifacts or {})
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; background: #f8fafc; }}
    h1, h2 {{ margin: 0 0 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef2f7; font-size: 14px; }}
    th {{ color: #52606d; font-weight: 600; }}
    ul {{ margin: 0; padding-left: 20px; }}
    .muted {{ color: #52606d; margin-bottom: 16px; }}
    .wide {{ grid-column: 1 / -1; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef6ff 100%); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }}
    .summary-tile {{ border: 1px solid #d9e2ec; border-radius: 12px; padding: 14px; background: #fff; }}
    .summary-label {{ color: #52606d; font-size: 12px; margin-bottom: 6px; }}
    .summary-value {{ font-size: 24px; font-weight: 700; color: #102a43; }}
    .lead {{ font-size: 16px; line-height: 1.7; color: #243b53; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  <p class="muted">生成时间：{escape(datetime.now().isoformat(timespec="seconds"))}。</p>
  <div class="grid">
    <div class="card wide hero">
      <h2>验证结论</h2>
      <p class="lead">{escape(conclusion)}</p>
      <div class="summary-grid">{summary_cards}</div>
    </div>
    <div class="card">
      <h2>结果观察</h2>
      <table>{observation_rows}</table>
    </div>
    <div class="card">
      <h2>产物清单</h2>
      <ul>{artifact_links}</ul>
    </div>
    <div class="card wide">
      <h2>窗口预览</h2>
      <table>
        <thead><tr>{"".join(f"<th>{escape(_display_label(header))}</th>" for header in headers)}</tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
    target_path.write_text(html, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def _build_batch_conclusion(
    best_row: dict[str, object] | None,
    rank_by: str,
    run_count: int,
) -> str:
    if best_row is None:
        return "本次参数扫描没有产生可用结果。"
    best_value = _format_metric_value(rank_by, best_row.get(rank_by))
    run_label = _format_run_label(best_row, 1)
    run_id = str(best_row.get("run_id", "-"))
    return (
        f"本次共完成 {run_count} 组 A 股参数试验，当前最佳方案为 {run_label}（{run_id}），"
        f"排序指标 {_display_label(rank_by)} 为 {best_value}。"
    )


def _build_walk_forward_conclusion(summary: dict[str, object]) -> str:
    windows = _coerce_float(summary.get("windows", 0.0))
    positive_rate = _coerce_float(summary.get("positive_window_rate", 0.0))
    average_return = _coerce_float(summary.get("average_annualized_return", 0.0))
    worst_drawdown = _coerce_float(summary.get("worst_max_drawdown", 0.0))
    return (
        f"本次共完成 {windows:.0f} 个滚动验证窗口，正收益窗口占比 {positive_rate:.2%}，"
        f"平均年化收益 {average_return:.2%}，最差最大回撤 {worst_drawdown:.2%}。"
    )


def _build_walk_forward_optimization_conclusion(summary: dict[str, object]) -> str:
    windows = _coerce_float(summary.get("windows", 0.0))
    grade = _format_summary_field(summary, "oos_stability_grade")
    risk = _format_summary_field(summary, "overfit_risk")
    degraded_rate = _coerce_float(summary.get("degraded_test_window_rate", 0.0))
    drift_rate = _coerce_float(summary.get("parameter_drift_rate", 0.0))
    return (
        f"本次共完成 {windows:.0f} 个训练/测试窗口，样本外稳定等级为 {grade}，"
        f"过拟合风险为 {risk}，退化窗口占比 {degraded_rate:.2%}，参数漂移率 {drift_rate:.2%}。"
    )


def _build_walk_forward_summary_cards(summary: dict[str, object]) -> str:
    cards = [
        ("窗口数", _format_summary_number(summary, "windows", decimals=0)),
        ("正收益窗口占比", _format_summary_pct(summary, "positive_window_rate")),
        ("平均年化收益", _format_summary_pct(summary, "average_annualized_return")),
        ("平均夏普", _format_summary_number(summary, "average_sharpe")),
        ("最差最大回撤", _format_summary_pct(summary, "worst_max_drawdown")),
        ("最佳窗口", _format_summary_field(summary, "best_window_id")),
    ]
    return "".join(_summary_card(label, value) for label, value in cards)


def _build_walk_forward_optimization_summary_cards(summary: dict[str, object]) -> str:
    cards = [
        ("窗口数", _format_summary_number(summary, "windows", decimals=0)),
        ("样本外稳定等级", _format_summary_field(summary, "oos_stability_grade")),
        ("过拟合风险", _format_summary_field(summary, "overfit_risk")),
        ("正测试窗口占比", _format_summary_pct(summary, "positive_test_window_rate")),
        ("退化窗口占比", _format_summary_pct(summary, "degraded_test_window_rate")),
        ("参数漂移率", _format_summary_pct(summary, "parameter_drift_rate")),
    ]
    return "".join(_summary_card(label, value) for label, value in cards)


def _build_walk_forward_observation_rows(summary: dict[str, object]) -> str:
    rows = [
        ("最佳窗口", _format_summary_field(summary, "best_window_id")),
        ("最弱窗口", _format_summary_field(summary, "worst_window_id")),
        ("平均总收益", _format_summary_pct(summary, "average_total_return")),
        ("平均夏普", _format_summary_number(summary, "average_sharpe")),
        ("最差最大回撤", _format_summary_pct(summary, "worst_max_drawdown")),
    ]
    return _build_html_table_rows(rows)


def _build_walk_forward_optimization_observation_rows(summary: dict[str, object]) -> str:
    rows = [
        ("最佳测试窗口", _format_summary_field(summary, "best_test_window_id")),
        ("最弱测试窗口", _format_summary_field(summary, "worst_test_window_id")),
        ("最严重退化窗口", _format_summary_field(summary, "worst_degradation_window_id")),
        ("最严重年化差距", _format_summary_pct(summary, "worst_train_test_annualized_gap")),
        ("主导参数组合", _format_summary_field(summary, "dominant_parameter_set")),
        ("主导参数组合占比", _format_summary_pct(summary, "dominant_parameter_set_rate")),
        ("漂移最频繁参数", _format_summary_field(summary, "most_drifting_parameter")),
        ("参数漂移明细", _format_count_map(summary, "parameter_drift_counts")),
        ("退化窗口参数组合", _format_degraded_parameter_sets(summary)),
    ]
    return _build_html_table_rows(rows)


def _build_analysis_preview_rows(rows: list[dict[str, object]], headers: list[str]) -> str:
    preview_rows = rows[:20]
    if not preview_rows:
        return f'<tr><td colspan="{len(headers)}">暂无窗口结果</td></tr>'
    return "\n".join(
        "<tr>"
        + "".join(
            f"<td>{escape(_format_analysis_cell(header, row.get(header)))}</td>"
            for header in headers
        )
        + "</tr>"
        for row in preview_rows
    )


def _format_analysis_cell(header: str, value: object) -> str:
    if value in (None, ""):
        return "-"
    if header.startswith("is_"):
        return "是" if bool(value) else "否"
    return _format_metric_value(header, value)


def _format_count_map(summary: dict[str, object], key: str) -> str:
    counts = summary.get(key)
    if not isinstance(counts, dict) or not counts:
        return "-"
    return "; ".join(f"{name}: {count}" for name, count in sorted(counts.items()))


def _format_degraded_parameter_sets(summary: dict[str, object]) -> str:
    values = summary.get("degraded_parameter_sets")
    if not isinstance(values, list) or not values:
        return "-"
    parts = []
    for item in values[:3]:
        if not isinstance(item, dict):
            continue
        parts.append(
            f"{item.get('window_id', '-')}: {item.get('parameter_set', '-')} "
            f"({ _coerce_float(item.get('train_test_annualized_gap', 0.0)):.2%})"
        )
    return "; ".join(parts) if parts else "-"


def _analysis_rows(analysis: dict[str, object]) -> list[dict[str, object]]:
    rows = analysis.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _analysis_summary_dict(analysis: dict[str, object]) -> dict[str, object]:
    summary = analysis.get("summary")
    return summary if isinstance(summary, dict) else {}


def _build_batch_summary_cards(
    best_row: dict[str, object] | None,
    rank_by: str,
    run_count: int,
) -> str:
    if best_row is None:
        return "\n".join(
            [
                _summary_card("试验组数", str(run_count)),
                _summary_card("最佳运行", "-"),
                _summary_card("最佳指标", "-"),
            ]
        )
    return "\n".join(
        [
            _summary_card("试验组数", str(run_count)),
            _summary_card("最佳方案", _format_run_label(best_row, 1)),
            _summary_card("内部编号", str(best_row.get("run_id", "-"))),
            _summary_card("Gate status", str(best_row.get("gate_status", "-"))),
            _summary_card("Health score", _format_metric_value("health_score", best_row.get("health_score"))),
            _summary_card(_display_label(rank_by), _format_metric_value(rank_by, best_row.get(rank_by))),
        ]
    )


def _build_batch_parameter_rows(best_row: dict[str, object] | None) -> str:
    if best_row is None:
        return "<tr><th>参数</th><td>暂无结果</td></tr>"
    parameter_items = [
        (key, value)
        for key, value in best_row.items()
        if key.startswith("param_")
    ]
    if not parameter_items:
        return "<tr><th>参数</th><td>本次没有参数扫描字段</td></tr>"
    return "\n".join(
        f"<tr><th>{escape(_display_label(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in parameter_items
    )


def _build_batch_observation_rows(
    sorted_rows: list[dict[str, object]],
    rank_by: str,
    artifacts: dict[str, Path],
) -> str:
    if not sorted_rows:
        return "<tr><th>观察</th><td>暂无结果</td></tr>"
    best_row = sorted_rows[0]
    worst_row = sorted_rows[-1]
    rows = [
        ("最佳方案", _format_run_label(best_row, 1)),
        ("最佳方案内部编号", str(best_row.get("run_id", "-"))),
        ("最优排序指标", _format_metric_value(rank_by, best_row.get(rank_by))),
        ("最弱方案", _format_run_label(worst_row, len(sorted_rows))),
        ("最弱方案内部编号", str(worst_row.get("run_id", "-"))),
        ("最弱排序指标", _format_metric_value(rank_by, worst_row.get(rank_by))),
    ]
    stability_summary = _load_artifact_summary(artifacts, "batch_stability_json")
    if stability_summary:
        rows.extend(
            [
                ("稳健热区数量", _format_summary_number(stability_summary, "robust_region_run_count", decimals=0)),
                ("稳健热区占比", _format_summary_pct(stability_summary, "robust_region_rate")),
                ("热区平均指标", _format_summary_number(stability_summary, "robust_region_average_metric", decimals=3)),
                ("参数孤岛", _format_summary_field(stability_summary, "is_parameter_island")),
                ("闸门通过运行数", _format_summary_number(stability_summary, "gate_passing_run_count", decimals=0)),
                ("闸门失败运行数", _format_summary_number(stability_summary, "gate_failing_run_count", decimals=0)),
                ("最常失败闸门类别", _format_count_map_top(stability_summary, "failed_gate_category_counts")),
                ("最常失败闸门", _format_count_map_top(stability_summary, "failed_gate_name_counts")),
                ("影响最强参数", _format_summary_field(stability_summary, "strongest_parameter")),
                ("推荐参数档位", _format_best_parameter_values(stability_summary)),
                ("参数推荐依据", _format_parameter_recommendation_rationale(stability_summary)),
                ("参数推荐总结", _format_parameter_recommendation_summary(stability_summary)),
                ("建议动作", _format_recommended_action_first(stability_summary)),
                ("建议动作数量", _format_list_count(stability_summary, "recommended_actions")),
            ]
        )
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _format_metric_value(metric: str, value: object) -> str:
    if value in (None, ""):
        return "-"
    numeric_metrics_as_pct = {
        "total_return",
        "annualized_return",
        "max_drawdown",
        "volatility",
        "downside_volatility",
        "average_turnover",
        "benchmark_total_return",
        "benchmark_annualized_return",
        "benchmark_volatility",
        "benchmark_max_drawdown",
        "excess_return",
        "tracking_error",
    }
    if not isinstance(value, (int, float, str)):
        return str(value)
    try:
        numeric_value = float(value)
    except ValueError:
        return str(value)
    if metric in numeric_metrics_as_pct:
        return _format_pct(numeric_value)
    return f"{numeric_value:.3f}"


def _build_performance_summary_items(
    metrics: BacktestMetrics,
) -> list[tuple[str, str, str, str]]:
    metric_order = [
        "total_return",
        "annualized_return",
        "max_drawdown",
        "volatility",
        "downside_volatility",
        "sharpe",
        "sortino",
        "calmar",
        "win_rate",
        "average_turnover",
        "total_cost",
        "periods",
        "benchmark_total_return",
        "benchmark_annualized_return",
        "benchmark_volatility",
        "benchmark_max_drawdown",
        "excess_return",
        "tracking_error",
        "information_ratio",
    ]
    return [
        (
            metric_name,
            _chinese_label(metric_name),
            _metric_explanation(metric_name),
            _format_performance_summary_value(metrics, metric_name),
        )
        for metric_name in metric_order
    ]


def _format_performance_summary_value(metrics: BacktestMetrics, metric_name: str) -> str:
    value = getattr(metrics, metric_name)
    if value is None:
        return ""
    if metric_name == "total_cost":
        return f"{value:.2f}"
    if metric_name == "periods":
        return str(value)
    return f"{value:.8f}"


def _has_benchmark_metrics(metrics: BacktestMetrics) -> bool:
    return metrics.benchmark_total_return is not None and metrics.excess_return is not None


def _build_single_run_metric_rows(metrics: BacktestMetrics) -> list[tuple[str, str]]:
    rows = [
        (_display_label("total_return"), f"{metrics.total_return:.2%}"),
        (_display_label("annualized_return"), f"{metrics.annualized_return:.2%}"),
        (_display_label("max_drawdown"), f"{metrics.max_drawdown:.2%}"),
        (_display_label("volatility"), f"{metrics.volatility:.2%}"),
        (_display_label("downside_volatility"), f"{metrics.downside_volatility:.2%}"),
        (_display_label("sharpe"), f"{metrics.sharpe:.3f}"),
        (_display_label("sortino"), f"{metrics.sortino:.3f}"),
        (_display_label("calmar"), f"{metrics.calmar:.3f}"),
        (_display_label("win_rate"), f"{metrics.win_rate:.2%}"),
        (_display_label("average_turnover"), f"{metrics.average_turnover:.2%}"),
        (_display_label("total_cost"), f"{metrics.total_cost:,.2f}"),
    ]
    if _has_benchmark_metrics(metrics):
        rows.extend(
            [
                (_display_label("benchmark_total_return"), f"{metrics.benchmark_total_return:.2%}"),
                (_display_label("excess_return"), f"{metrics.excess_return:.2%}"),
                (_display_label("tracking_error"), f"{metrics.tracking_error:.2%}"),
                (_display_label("information_ratio"), f"{metrics.information_ratio:.3f}"),
            ]
        )
    return rows


def _build_single_run_review_rows(artifacts: dict[str, Path]) -> list[tuple[str, str]]:
    drawdown_summary = _load_artifact_summary(artifacts, "drawdown_json")
    exposure_summary = _load_artifact_summary(artifacts, "exposure_json")
    group_exposure_summary = _load_artifact_summary(artifacts, "group_exposure_json")
    rolling_risk_summary = _load_artifact_summary(artifacts, "rolling_risk_json")
    relative_summary = _load_artifact_summary(artifacts, "relative_performance_json")
    factor_ic_summary = _load_artifact_summary(artifacts, "factor_ic_json")
    factor_decay_summary = _load_artifact_summary(artifacts, "factor_decay_json")
    factor_correlation_summary = _load_artifact_summary(artifacts, "factor_correlation_json")
    execution_summary = _load_artifact_summary(artifacts, "execution_quality_json")
    return_attribution_summary = _load_artifact_summary(artifacts, "return_attribution_json")
    cost_attribution_summary = _load_artifact_summary(artifacts, "cost_attribution_json")
    pnl_ledger_summary = _load_artifact_summary(artifacts, "pnl_ledger_json")
    strategy_health_summary = _load_artifact_summary(artifacts, "strategy_health_json")

    return [
        ("策略健康评分", _format_summary_number(strategy_health_summary, "score")),
        ("策略健康等级", _format_summary_field(strategy_health_summary, "grade")),
        ("策略闸门状态", _format_summary_field(strategy_health_summary, "gate_status")),
        ("策略闸门失败数", _format_summary_number(strategy_health_summary, "gate_failures", decimals=0)),
        ("策略预警数量", _format_summary_number(strategy_health_summary, "warnings", decimals=0)),
        ("因子相关风险", _format_summary_pct(strategy_health_summary, "strongest_factor_correlation")),
        ("最强相关因子对", _format_summary_field(strategy_health_summary, "strongest_factor_correlation_pair")),
        ("最大回撤日期", _format_summary_field(drawdown_summary, "max_drawdown_date")),
        ("最长水下天数", _format_summary_number(drawdown_summary, "longest_underwater_days")),
        ("回撤是否修复", _format_summary_bool(drawdown_summary, "is_recovered")),
        ("滚动最差收益", _format_summary_pct(rolling_risk_summary, "worst_rolling_return")),
        ("滚动最差收益日", _format_summary_field(rolling_risk_summary, "worst_rolling_return_date")),
        ("滚动平均夏普", _format_summary_number(rolling_risk_summary, "average_rolling_sharpe")),
        ("滚动最大回撤", _format_summary_pct(rolling_risk_summary, "worst_rolling_drawdown")),
        ("平均股票仓位", _format_summary_pct(exposure_summary, "average_stock_weight")),
        ("平均持仓数量", _format_summary_number(exposure_summary, "average_holding_count")),
        ("有效持仓数", _format_summary_number(exposure_summary, "average_effective_position_count")),
        ("最大单票权重", _format_summary_pct(exposure_summary, "max_largest_position_weight")),
        ("最大持仓集中度", _format_summary_number(exposure_summary, "max_hhi_concentration")),
        ("最大风险贡献标的", _format_summary_field(exposure_summary, "max_largest_risk_contribution_symbol")),
        ("最大风险贡献占比", _format_summary_pct(exposure_summary, "max_largest_risk_contribution_share")),
        ("最大分组风险贡献", _format_summary_field(group_exposure_summary, "max_group_risk_contribution_group")),
        ("最大分组贡献占比", _format_summary_pct(group_exposure_summary, "max_group_risk_contribution_share")),
        ("总分平均IC", _format_nested_summary_number(factor_ic_summary, "total_score", "mean_ic")),
        ("总分ICIR", _format_nested_summary_number(factor_ic_summary, "total_score", "ic_ir")),
        ("总分IC t值", _format_nested_summary_number(factor_ic_summary, "total_score", "ic_t_stat")),
        ("总分稳定性", _format_nested_summary_number(factor_decay_summary, "total_score", "average_rank_correlation")),
        ("入选留存率", _format_nested_summary_pct(factor_decay_summary, "total_score", "average_selected_retention_rate")),
        ("最强因子相关", _format_factor_pair(factor_correlation_summary, "strongest_pair")),
        ("最强排序相关", _format_factor_pair(factor_correlation_summary, "strongest_rank_pair")),
        ("累计主动收益", _format_summary_pct(relative_summary, "total_active_return")),
        ("年化Alpha", _format_summary_pct(relative_summary, "annualized_alpha")),
        ("Beta", _format_summary_number(relative_summary, "beta")),
        ("R平方", _format_summary_pct(relative_summary, "r_squared")),
        ("主动胜率", _format_summary_pct(relative_summary, "active_win_rate")),
        ("最差主动日", _format_summary_field(relative_summary, "worst_active_return_date")),
        ("主动最大回撤", _format_summary_pct(relative_summary, "max_active_drawdown")),
        ("成交率", _format_summary_pct(execution_summary, "fill_rate")),
        ("执行成本", _format_summary_bps(execution_summary, "cost_bps")),
        ("主要执行约束", _format_summary_field(execution_summary, "dominant_constraint_category")),
        ("市场约束拒单占比", _format_summary_pct(execution_summary, "market_constraint_rate")),
        ("最严重执行阻塞日", _format_summary_field(execution_summary, "worst_constraint_date")),
        ("阻塞日主要约束", _format_summary_field(execution_summary, "worst_constraint_dominant_category")),
        ("收益归因残差", _format_summary_pct(return_attribution_summary, "total_residual_return")),
        ("成本拖累", _format_summary_pct(return_attribution_summary, "total_cost_drag")),
        ("总成本", _format_summary_money(cost_attribution_summary, "total_cost")),
        ("固定滑点成本", _format_summary_money(cost_attribution_summary, "fixed_slippage_cost")),
        ("市场冲击成本", _format_summary_money(cost_attribution_summary, "market_impact_cost")),
        ("成本归因 bps", _format_summary_bps(cost_attribution_summary, "cost_bps")),
        ("最大对账差异", _format_summary_money(pnl_ledger_summary, "max_abs_reconciliation_difference")),
        ("对账状态", _format_reconciliation_status(pnl_ledger_summary)),
    ]


def _build_trading_behavior_rows(artifacts: dict[str, Path]) -> list[tuple[str, str]]:
    turnover_summary = _load_artifact_summary(artifacts, "turnover_analysis_json")
    strategy_health_summary = _load_artifact_summary(artifacts, "strategy_health_json")
    average_entries = _summary_float(turnover_summary, "average_entries_per_rebalance")
    average_exits = _summary_float(turnover_summary, "average_exits_per_rebalance")
    average_rebalance_changes = (
        None if average_entries is None or average_exits is None else average_entries + average_exits
    )
    return [
        ("Average entries per rebalance", _format_summary_number(turnover_summary, "average_entries_per_rebalance")),
        ("Average exits per rebalance", _format_summary_number(turnover_summary, "average_exits_per_rebalance")),
        ("Average rebalance changes", _format_optional_number(average_rebalance_changes)),
        ("Realized holding periods", _format_summary_number(turnover_summary, "realized_holding_count", decimals=0)),
        ("Average realized holding days", _format_summary_number(turnover_summary, "average_realized_holding_days")),
        ("Open positions after final bar", _format_summary_number(turnover_summary, "open_position_count", decimals=0)),
        ("Turnover gate status", _format_summary_field(strategy_health_summary, "gate_status")),
        ("Health warnings", _format_summary_number(strategy_health_summary, "warnings", decimals=0)),
    ]


def _build_data_quality_rows(artifacts: dict[str, Path]) -> list[tuple[str, str]]:
    summary = _load_artifact_summary(artifacts, "price_data_quality_report_json")
    return [
        ("Price rows", _format_summary_number(summary, "row_count", decimals=0)),
        ("Symbols", _format_summary_number(summary, "symbol_count", decimals=0)),
        ("Trading dates", _format_summary_number(summary, "date_count", decimals=0)),
        ("Date range", _format_date_range(summary)),
        ("Symbols missing adjusted close", _format_summary_number(summary, "symbols_with_missing_adjusted_close", decimals=0)),
        ("Execution price field", _format_summary_field(summary, "execution_price_field")),
        ("Missing execution price rows", _format_summary_number(summary, "missing_execution_price_rows", decimals=0)),
        ("Execution price coverage", _format_summary_pct(summary, "execution_price_coverage_rate")),
        ("Missing open rows", _format_summary_number(summary, "missing_open_rows", decimals=0)),
        ("Missing VWAP rows", _format_summary_number(summary, "missing_vwap_rows", decimals=0)),
        ("Suspended rows", _format_summary_number(summary, "suspended_days", decimals=0)),
        ("Limit-up rows", _format_summary_number(summary, "limit_up_days", decimals=0)),
        ("Limit-down rows", _format_summary_number(summary, "limit_down_days", decimals=0)),
        ("ST rows", _format_summary_number(summary, "st_days", decimals=0)),
        ("Custom limit-rate rows", _format_summary_number(summary, "custom_limit_rate_days", decimals=0)),
        ("Untradable rows", _format_summary_number(summary, "untradable_days", decimals=0)),
        ("Cannot-buy rows", _format_summary_number(summary, "cannot_buy_days", decimals=0)),
        ("Cannot-sell rows", _format_summary_number(summary, "cannot_sell_days", decimals=0)),
    ]


def _load_artifact_summary(artifacts: dict[str, Path], artifact_key: str) -> dict[str, object]:
    path = artifacts.get(artifact_key)
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _format_summary_field(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    return "-" if value in (None, "") else str(value)


def _format_date_range(summary: dict[str, object]) -> str:
    start_date = _format_summary_field(summary, "start_date")
    end_date = _format_summary_field(summary, "end_date")
    if start_date == "-" and end_date == "-":
        return "-"
    return f"{start_date} to {end_date}"


def _summary_float(summary: dict[str, object], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None


def _format_summary_number(
    summary: dict[str, object],
    key: str,
    *,
    decimals: int = 2,
) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:,.{decimals}f}"


def _format_summary_bool(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if value is True:
        return "是"
    if value is False:
        return "否"
    return "-"


def _format_nested_summary_number(
    summary: dict[str, object],
    section: str,
    key: str,
    *,
    decimals: int = 3,
) -> str:
    section_payload = summary.get(section)
    if not isinstance(section_payload, dict):
        return "-"
    value = section_payload.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:,.{decimals}f}"


def _format_nested_summary_pct(
    summary: dict[str, object],
    section: str,
    key: str,
) -> str:
    section_payload = summary.get(section)
    if not isinstance(section_payload, dict):
        return "-"
    value = section_payload.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:.2%}"


def _format_factor_pair(summary: dict[str, object], key: str) -> str:
    pair = summary.get(key)
    if not isinstance(pair, dict):
        return "-"
    factor = pair.get("factor")
    compared_factor = pair.get("compared_factor")
    if not isinstance(factor, str) or not isinstance(compared_factor, str):
        return "-"
    correlation = pair.get("average_correlation", pair.get("average_rank_correlation"))
    if not isinstance(correlation, int | float):
        return f"{factor} vs {compared_factor}"
    return f"{factor} vs {compared_factor}: {correlation:.3f}"


def _format_count_map_top(summary: dict[str, object], key: str) -> str:
    counts = summary.get(key)
    if not isinstance(counts, dict) or not counts:
        return "-"
    top_key, top_count = max(
        counts.items(),
        key=lambda item: (_coerce_float(item[1]), str(item[0])),
    )
    return f"{top_key}: {_coerce_float(top_count):.0f}"


def _format_best_parameter_values(summary: dict[str, object]) -> str:
    values = summary.get("best_parameter_values")
    if not isinstance(values, dict) or not values:
        return "-"
    parts = [
        f"{key}={value}"
        for key, value in sorted(values.items())
    ]
    return "; ".join(parts)


def _format_parameter_recommendation_rationale(summary: dict[str, object]) -> str:
    rationale = summary.get("parameter_recommendation_rationale")
    if not isinstance(rationale, dict) or not rationale:
        return "-"
    parts = []
    for parameter, payload in sorted(rationale.items()):
        if not isinstance(payload, dict):
            continue
        recommended_value = payload.get("recommended_value", "-")
        reason = _format_recommendation_reason(payload.get("reason", "-"))
        best_by_metric = payload.get("best_value_by_metric", "-")
        composite = _coerce_float(payload.get("average_composite_score", 0.0))
        gate_rate = _coerce_float(payload.get("gate_passing_rate", 0.0))
        metric_note = ""
        if not payload.get("is_also_best_by_metric", False):
            metric_note = f", 排序指标最优={best_by_metric}"
        parts.append(
            f"{parameter}={recommended_value} ({reason}{metric_note}, 综合分={composite:.3f}, 通过率={gate_rate:.2%})"
        )
    return "; ".join(parts) if parts else "-"


def _format_parameter_recommendation_summary(summary: dict[str, object]) -> str:
    value = summary.get("parameter_recommendation_summary")
    if not isinstance(value, str) or not value:
        return "-"
    return _format_recommendation_summary_text(value)


def _format_recommendation_reason(reason: object) -> str:
    reason_key = str(reason)
    labels = {
        "highest_average_composite_score": "平均综合分最高",
    }
    return labels.get(reason_key, reason_key)


def _format_recommended_action_first(summary: dict[str, object]) -> str:
    values = summary.get("recommended_actions")
    if not isinstance(values, list) or not values:
        return "-"
    return _format_recommended_action_text(str(values[0]))


def _format_recommendation_summary_text(value: str) -> str:
    text = value.replace(
        "Recommended parameter values by average composite score:",
        "按平均综合分推荐参数：",
    )
    text = text.replace(
        "Metric and composite recommendations diverge for:",
        "排序指标最优与综合分推荐不一致：",
    )
    text = text.replace("composite ", "综合分 ")
    text = text.replace("gate pass ", "闸门通过率 ")
    text = text.replace("metric-best=", "排序指标最优=")
    return text


def _format_recommended_action_text(value: str) -> str:
    translations = {
        "Most parameter sets passed health gates; focus on robustness, live trading assumptions, and out-of-sample validation.": "多数参数组合通过健康闸门；下一步重点检查稳健性、实盘交易假设和样本外验证。",
        "Risk gates fail often: reduce position concentration, raise cash buffer, shorten rebalance exposure, or add drawdown-aware filters.": "风险闸门频繁失败：降低持仓集中度、提高现金缓冲、缩短调仓暴露，或加入回撤感知过滤。",
        "Stability gates fail often: prefer parameter regions with smoother rolling returns and validate on longer walk-forward windows.": "稳定性闸门频繁失败：优先选择滚动收益更平滑的参数区域，并用更长 walk-forward 窗口验证。",
        "Execution gates fail often: reduce volume participation, avoid illiquid names, increase cash buffer, or relax target turnover.": "执行闸门频繁失败：降低成交量参与率、避开低流动性标的、增加现金缓冲，或放宽目标换手。",
        "Exposure gates fail often: tighten max_position_weight or add group constraints to reduce concentration.": "暴露闸门频繁失败：收紧 max_position_weight，或增加分组约束以降低集中度。",
        "Attribution gates fail often: inspect return attribution residuals before trusting parameter rankings.": "归因闸门频繁失败：在信任参数排名前，先检查收益归因残差。",
        "Turnover gates fail often: lengthen rebalance interval, require stronger signal changes, or raise holding-period constraints.": "换手闸门频繁失败：拉长调仓间隔、要求更强信号变化，或提高持仓周期约束。",
        "Factor gates fail often: remove redundant factors, lower highly correlated factor weights, or add orthogonal signals.": "因子闸门频繁失败：移除冗余因子、降低高相关因子权重，或加入正交信号。",
        "Ledger gates fail often: resolve accounting reconciliation issues before comparing parameter performance.": "对账闸门频繁失败：先解决账务对齐问题，再比较参数表现。",
    }
    translated = translations.get(value)
    if translated is not None:
        return translated
    prefix = "Most common failed gate is '"
    suffix = "'; review the single-run strategy_health_gates.csv files for affected runs first."
    if value.startswith(prefix) and value.endswith(suffix):
        gate_name = value[len(prefix):-len(suffix)]
        return f"最常失败闸门是“{gate_name}”；请优先查看受影响运行的 strategy_health_gates.csv。"
    return value


def _format_list_first(summary: dict[str, object], key: str) -> str:
    values = summary.get(key)
    if not isinstance(values, list) or not values:
        return "-"
    return str(values[0])


def _format_list_count(summary: dict[str, object], key: str) -> str:
    values = summary.get(key)
    if not isinstance(values, list):
        return "0"
    return str(len(values))


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _format_optional_number(value: float | None, *, decimals: int = 2) -> str:
    return "-" if value is None else f"{value:,.{decimals}f}"


def _format_summary_pct(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:.2%}"


def _format_summary_bps(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:.2f} bps"


def _format_summary_money(summary: dict[str, object], key: str) -> str:
    value = summary.get(key)
    if not isinstance(value, int | float):
        return "-"
    return f"{value:,.2f}"


def _format_reconciliation_status(summary: dict[str, object]) -> str:
    value = summary.get("reconciled")
    if value is True:
        return "已对齐"
    if value is False:
        return "存在差异"
    return "-"


def _build_artifact_links(artifacts: dict[str, Path]) -> str:
    return "\n".join(
        f'<li><a href="{escape(path.name)}">{escape(_display_label(name))}</a></li>'
        for name, path in artifacts.items()
    )


def _build_batch_chart_blocks(artifacts: dict[str, Path]) -> list[str]:
    chart_blocks: list[str] = []
    for key in ("batch_chart_svg", "batch_heatmap_svg"):
        if key in artifacts:
            chart_blocks.append(
                f'<div class="card"><h2>{escape(_display_label(key))}</h2><img src="{escape(artifacts[key].name)}" alt="{escape(_display_label(key))}" /></div>'
            )
    return chart_blocks


def _build_html_table_rows(rows: list[tuple[str, str]]) -> str:
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _sort_rows_by_metric(rows: list[dict[str, object]], rank_by: str) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            _gate_rank_value(row),
            -_float_metric(row, "gate_failures", default=0.0),
            -_float_metric(row, "critical_warnings", default=0.0),
            -_float_metric(row, "health_warnings", default=0.0),
            _float_metric(row, rank_by, default=float("-inf")),
        ),
        reverse=True,
    )


def _gate_rank_value(row: dict[str, object]) -> float:
    gate_status = str(row.get("gate_status", "")).lower()
    if gate_status == "pass":
        return 1.0
    if gate_status == "":
        return 0.5
    return 0.0


def _validate_rank_metric(rows: list[dict[str, object]], rank_by: str) -> None:
    if not rows:
        return

    available_metrics = sorted(
        {
            key
            for row in rows
            for key, value in row.items()
            if _is_numeric_metric_value(value)
        }
    )
    if rank_by not in available_metrics:
        available_text = ", ".join(available_metrics) or "<none>"
        raise ValueError(
            f"Rank metric '{rank_by}' is not available. "
            f"Available numeric metrics: {available_text}."
        )


def _is_numeric_metric_value(value: object) -> bool:
    if value in ("", None):
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return False


def _serialize_config(config: BacktestConfig) -> dict[str, object]:
    return {
        "initial_cash": config.initial_cash,
        "top_n": config.top_n,
        "selection_mode": config.selection_mode,
        "score_source": config.score_source,
        "lot_size": config.lot_size,
        "max_group_positions": config.max_group_positions,
        "lookback_momentum": config.lookback_momentum,
        "lookback_mean_reversion": config.lookback_mean_reversion,
        "lookback_volatility": config.lookback_volatility,
        "rolling_risk_window": config.rolling_risk_window,
        "execution_delay_days": config.execution_delay_days,
        "max_allowed_drawdown": config.max_allowed_drawdown,
        "max_allowed_daily_var": config.max_allowed_daily_var,
        "min_allowed_rolling_return": config.min_allowed_rolling_return,
        "min_allowed_information_ratio": config.min_allowed_information_ratio,
        "min_allowed_fill_rate": config.min_allowed_fill_rate,
        "min_allowed_execution_price_coverage": config.min_allowed_execution_price_coverage,
        "min_allowed_factor_score_coverage": config.min_allowed_factor_score_coverage,
        "max_allowed_position_weight": config.max_allowed_position_weight,
        "max_allowed_group_weight": config.max_allowed_group_weight,
        "max_allowed_attribution_residual": config.max_allowed_attribution_residual,
        "rebalance_every_n_days": config.rebalance_every_n_days,
        "commission_rate": config.commission_rate,
        "buy_commission_rate": config.buy_commission_rate,
        "sell_commission_rate": config.sell_commission_rate,
        "slippage_rate": config.slippage_rate,
        "market_impact_coefficient": config.market_impact_coefficient,
        "market_impact_exponent": config.market_impact_exponent,
        "stamp_duty_rate": config.stamp_duty_rate,
        "min_commission": config.min_commission,
        "transfer_fee_rate": config.transfer_fee_rate,
        "target_cash_weight": config.target_cash_weight,
        "max_position_weight": config.max_position_weight,
        "infer_limit_flags": config.infer_limit_flags,
        "forward_fill_suspended_bars": config.forward_fill_suspended_bars,
        "limit_up_down_rate": config.limit_up_down_rate,
        "st_limit_up_down_rate": config.st_limit_up_down_rate,
        "growth_limit_up_down_rate": config.growth_limit_up_down_rate,
        "bse_limit_up_down_rate": config.bse_limit_up_down_rate,
        "infer_limit_rate_by_symbol": config.infer_limit_rate_by_symbol,
        "max_volume_participation": config.max_volume_participation,
        "price_field": config.price_field,
        "execution_price_field": config.execution_price_field,
        "execution_price_field_effective": config.execution_price_field_effective,
        "start_date": None if config.start_date is None else config.start_date.isoformat(),
        "end_date": None if config.end_date is None else config.end_date.isoformat(),
        "output_dir": str(config.output_dir),
        "symbol_name_csv": None if config.symbol_name_csv is None else str(config.symbol_name_csv),
        "stock_pool_csv": None if config.stock_pool_csv is None else str(config.stock_pool_csv),
        "symbol_group_csv": None if config.symbol_group_csv is None else str(config.symbol_group_csv),
        "factor_score_csv": None if config.factor_score_csv is None else str(config.factor_score_csv),
        "factor_weights": config.factor_weights,
    }


def _build_input_file_metadata(
    inputs: dict[str, str | bool | None],
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for key in ("csv", "benchmark_csv", "stock_pool_csv", "symbol_group_csv", "factor_score_csv", "config"):
        raw_path = inputs.get(key)
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists() or not path.is_file():
            continue
        metadata[key] = _file_metadata(path)
    return metadata


def _build_artifact_file_metadata(
    artifacts: dict[str, Path],
) -> dict[str, dict[str, object]]:
    metadata: dict[str, dict[str, object]] = {}
    for name, path in artifacts.items():
        if path.exists() and path.is_file():
            metadata[name] = _file_metadata(path)
    return metadata


def _build_environment_metadata() -> dict[str, str]:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def _build_git_metadata() -> dict[str, object]:
    repo_root = Path(__file__).resolve().parent.parent
    try:
        commit = _run_git_command(repo_root, "rev-parse", "HEAD")
        branch = _run_git_command(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        status_short = _run_git_command(repo_root, "status", "--short")
    except (OSError, subprocess.SubprocessError):
        return {"available": False}

    return {
        "available": True,
        "commit": commit,
        "branch": branch,
        "is_dirty": bool(status_short),
        "status_short": status_short.splitlines(),
    }


def _run_git_command(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _file_metadata(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_symbol_name_mapping(symbol_name_csv: Path | None) -> dict[str, str]:
    if symbol_name_csv is None:
        return {}
    if not symbol_name_csv.exists():
        raise FileNotFoundError(f"Symbol name CSV not found: {symbol_name_csv}")

    mapping: dict[str, str] = {}
    with symbol_name_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"symbol", "name"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"Symbol name CSV missing required columns: {missing_str}")
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            name = (row.get("name") or "").strip()
            if symbol and name:
                if not is_a_share_symbol(symbol):
                    raise ValueError(f"Unsupported A-share symbol format: {symbol}")
                mapping[symbol] = name
    return mapping


def load_symbol_group_mapping(symbol_group_csv: Path | None) -> dict[str, str]:
    if symbol_group_csv is None:
        return {}
    if not symbol_group_csv.exists():
        raise FileNotFoundError(f"Symbol group CSV not found: {symbol_group_csv}")

    mapping: dict[str, str] = {}
    with symbol_group_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"symbol", "group"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise ValueError(f"Symbol group CSV missing required columns: {missing_str}")
        for row in reader:
            symbol = (row.get("symbol") or "").strip()
            group = (row.get("group") or "").strip()
            if symbol and group:
                if not is_a_share_symbol(symbol):
                    raise ValueError(f"Unsupported A-share symbol format: {symbol}")
                mapping[symbol] = group
    return mapping


def _float_metric(
    row: dict[str, object],
    key: str,
    *,
    default: float | None = None,
) -> float:
    value = row.get(key)
    if value in ("", None):
        if default is not None:
            return default
        raise ValueError(f"Metric '{key}' is missing from row.")
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Metric '{key}' must be numeric, got {type(value).__name__}.")


def _display_label(key: str) -> str:
    return f"{_chinese_label(key)} / {key}"


def _chinese_label(key: str) -> str:
    if key.startswith("param_"):
        param_name = key.removeprefix("param_")
        return f"参数_{_chinese_label(param_name)}"
    return _ZH_LABELS.get(key, key)


def _metric_explanation(key: str) -> str:
    return _METRIC_EXPLANATIONS.get(key, "")


def _build_report_conclusion(metrics: BacktestMetrics) -> str:
    conclusion = (
        f"本次回测总收益为 {metrics.total_return:.2%}，年化收益为 "
        f"{metrics.annualized_return:.2%}，最大回撤控制在 {metrics.max_drawdown:.2%}。"
    )
    if metrics.benchmark_total_return is None or metrics.excess_return is None:
        return conclusion
    return f"{conclusion}{_build_benchmark_conclusion(metrics)}"


def _build_benchmark_conclusion(metrics: BacktestMetrics) -> str:
    if metrics.benchmark_total_return is None or metrics.excess_return is None:
        return "本次回测未提供基准对比。"
    benchmark_return = f"{metrics.benchmark_total_return:.2%}"
    excess_return = abs(metrics.excess_return)
    if metrics.excess_return >= 0:
        return f"同期基准收益为 {benchmark_return}，策略跑赢基准 {excess_return:.2%}。"
    return f"同期基准收益为 {benchmark_return}，策略跑输基准 {excess_return:.2%}。"


def _summary_card(label: str, value: str) -> str:
    return (
        '<div class="summary-tile">'
        f'<div class="summary-label">{escape(label)}</div>'
        f'<div class="summary-value">{escape(value)}</div>'
        "</div>"
    )


def _build_rebalance_summary_rows(
    latest_rebalance: RebalanceRecord | None,
    symbol_names: dict[str, str] | None,
) -> str:
    if latest_rebalance is None:
        return "<tr><th>最近调仓</th><td>本次回测没有发生调仓。</td></tr>"

    rows = [
        ("最近调仓日期", latest_rebalance.date.isoformat()),
        ("调仓后持仓", _format_holdings(latest_rebalance.holdings, symbol_names)),
        ("买入换手", _format_pct(latest_rebalance.buy_turnover)),
        ("卖出换手", _format_pct(latest_rebalance.sell_turnover)),
        ("总换手", _format_pct(latest_rebalance.turnover)),
        ("交易成本", _format_money(latest_rebalance.cost)),
        ("调仓备注", _rebalance_note(latest_rebalance)),
    ]
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _build_benchmark_summary_rows(metrics: BacktestMetrics) -> str:
    rows = [
        ("基准总收益", "-" if metrics.benchmark_total_return is None else f"{metrics.benchmark_total_return:.2%}"),
        ("基准年化收益", "-" if metrics.benchmark_annualized_return is None else f"{metrics.benchmark_annualized_return:.2%}"),
        ("超额收益", "-" if metrics.excess_return is None else f"{metrics.excess_return:.2%}"),
        ("跟踪误差", "-" if metrics.tracking_error is None else f"{metrics.tracking_error:.2%}"),
        ("信息比率", "-" if metrics.information_ratio is None else f"{metrics.information_ratio:.3f}"),
        ("基准最大回撤", "-" if metrics.benchmark_max_drawdown is None else f"{metrics.benchmark_max_drawdown:.2%}"),
    ]
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _format_pct(value: float) -> str:
    return f"{value:.2%}"


def _format_money(value: float) -> str:
    return f"{value:,.2f}"


def _format_optional_date(value: object) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _format_optional_rate(value: float | None) -> str:
    return "-" if value is None else f"{value:.6f}"


def _format_optional_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _build_equity_curve_benchmark_columns(
    point: EquityPoint,
    benchmark_point: BenchmarkPoint | None,
) -> tuple[str, str, str, str, str, str]:
    if benchmark_point is None:
        return ("", "", "", "", "", "")
    excess_daily_return = point.daily_return - benchmark_point.daily_return
    return (
        f"{benchmark_point.equity:.2f}",
        _format_money(benchmark_point.equity),
        f"{benchmark_point.daily_return:.8f}",
        _format_pct(benchmark_point.daily_return),
        f"{excess_daily_return:.8f}",
        _format_pct(excess_daily_return),
    )


def _equity_curve_note(point: EquityPoint, has_benchmark: bool) -> str:
    benchmark_note = "含基准对比" if has_benchmark else "无基准对比"
    if not point.holdings:
        return f"空仓；{benchmark_note}"
    return f"{len(point.holdings)}只持仓；{benchmark_note}"


def _rebalance_note(record: RebalanceRecord) -> str:
    if record.buy_turnover > 0 and record.sell_turnover > 0:
        return "有买有卖"
    if record.buy_turnover > 0:
        return "仅买入"
    if record.sell_turnover > 0:
        return "仅卖出"
    return "无实际换手"


def _format_holdings(holdings: tuple[str, ...], symbol_names: dict[str, str] | None = None) -> str:
    if not holdings:
        return "空仓"
    return " | ".join(_format_symbol(symbol, symbol_names) for symbol in holdings)


def _format_symbol(symbol: str, symbol_names: dict[str, str] | None = None) -> str:
    if symbol_names and symbol in symbol_names:
        return f"{symbol}（{symbol_names[symbol]}）"
    if symbol in _DEFAULT_A_SHARE_SYMBOL_NAMES:
        return f"{symbol}（{_DEFAULT_A_SHARE_SYMBOL_NAMES[symbol]}）"
    return symbol
def _build_line_chart_svg(
    *,
    title: str,
    series: list[tuple[str, list[tuple[str, float]], str]],
    y_axis_label: str,
) -> str:
    width = 960
    height = 540
    margin_left = 80
    margin_right = 40
    margin_top = 60
    margin_bottom = 80

    non_empty_series = [item for item in series if item[1]]
    if not non_empty_series:
        return _empty_chart_svg(title, width, height)

    all_values = [value for _, points, _ in non_empty_series for _, value in points]
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value *= 0.99
        max_value *= 1.01

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    def x_position(index: int, total: int) -> float:
        if total <= 1:
            return margin_left + plot_width / 2
        return margin_left + plot_width * index / (total - 1)

    def y_position(value: float) -> float:
        scale = (value - min_value) / (max_value - min_value)
        return margin_top + plot_height * (1 - scale)

    grid_lines = []
    labels = []
    for step in range(5):
        ratio = step / 4
        y = margin_top + plot_height * ratio
        value = max_value - (max_value - min_value) * ratio
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#d0d7de" stroke-width="1" />'
        )
        labels.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{value:.2f}</text>'
        )

    line_paths: list[str] = []
    legend_items: list[str] = []
    for index, (label, points, color) in enumerate(non_empty_series):
        commands = []
        for point_index, (_, value) in enumerate(points):
            x = x_position(point_index, len(points))
            y = y_position(value)
            prefix = "M" if point_index == 0 else "L"
            commands.append(f"{prefix} {x:.1f} {y:.1f}")
        line_paths.append(
            f'<path d="{" ".join(commands)}" fill="none" stroke="{color}" stroke-width="3" />'
        )
        legend_y = margin_top - 18 + index * 18
        legend_items.append(
            f'<rect x="{width - 180}" y="{legend_y - 10}" width="12" height="12" fill="{color}" />'
            f'<text x="{width - 160}" y="{legend_y}" font-size="12" fill="#212529">{label}</text>'
        )

    first_series_points = non_empty_series[0][1]
    x_labels = []
    label_indexes = sorted({0, len(first_series_points) // 2, len(first_series_points) - 1})
    for label_index in label_indexes:
        x = x_position(label_index, len(first_series_points))
        label = first_series_points[label_index][0]
        x_labels.append(
            f'<text x="{x:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{label}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *grid_lines,
            f'<line x1="{margin_left}" y1="{height - margin_bottom}" x2="{width - margin_right}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            *labels,
            *line_paths,
            *legend_items,
            *x_labels,
            f'<text x="24" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 24 {margin_top + plot_height / 2:.1f})">{y_axis_label}</text>',
            "</svg>",
        ]
    )


def _build_bar_chart_svg(
    *,
    title: str,
    points: list[tuple[str, float]],
    bar_color: str,
    y_axis_label: str,
) -> str:
    width = 960
    height = 540
    margin_left = 80
    margin_right = 40
    margin_top = 60
    margin_bottom = 100
    if not points:
        return _empty_chart_svg(title, width, height)

    values = [value for _, value in points]
    max_value = max(max(values), 0.0)
    min_value = min(min(values), 0.0)
    if min_value == max_value:
        max_value = max_value + 1.0
        min_value = min_value - 1.0

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    zero_y = margin_top + plot_height * (max_value / (max_value - min_value))

    def y_position(value: float) -> float:
        scale = (value - min_value) / (max_value - min_value)
        return margin_top + plot_height * (1 - scale)

    bar_width = plot_width / max(len(points), 1) * 0.65
    gap = plot_width / max(len(points), 1)

    grid_lines = []
    labels = []
    for step in range(5):
        ratio = step / 4
        y = margin_top + plot_height * ratio
        value = max_value - (max_value - min_value) * ratio
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#d0d7de" stroke-width="1" />'
        )
        labels.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{value:.2f}</text>'
        )

    bars = []
    x_labels = []
    for index, (label, value) in enumerate(points):
        x = margin_left + index * gap + (gap - bar_width) / 2
        y = y_position(max(value, 0.0))
        bar_base = y_position(min(value, 0.0))
        bar_height = abs(bar_base - y)
        bars.append(
            f'<rect x="{x:.1f}" y="{min(y, bar_base):.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{bar_color}" rx="4" />'
        )
        x_labels.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{label}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *grid_lines,
            f'<line x1="{margin_left}" y1="{zero_y:.1f}" x2="{width - margin_right}" y2="{zero_y:.1f}" stroke="#495057" stroke-width="1.5" />',
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height - margin_bottom}" stroke="#495057" stroke-width="1.5" />',
            *labels,
            *bars,
            *x_labels,
            f'<text x="24" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 24 {margin_top + plot_height / 2:.1f})">{y_axis_label}</text>',
            "</svg>",
        ]
    )


def _empty_chart_svg(title: str, width: int, height: int) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="40" y="40" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            '<text x="40" y="90" font-size="16" fill="#6c757d">暂无可展示数据</text>',
            "</svg>",
        ]
    )


def _build_heatmap_svg(
    *,
    title: str,
    x_label: str,
    y_label: str,
    points: list[tuple[str, str, float]],
) -> str:
    width = 960
    height = 540
    margin_left = 120
    margin_right = 120
    margin_top = 60
    margin_bottom = 100
    if not points:
        return _empty_chart_svg(title, width, height)

    x_values = sorted({x for x, _, _ in points})
    y_values = sorted({y for _, y, _ in points})
    value_map = {(x, y): value for x, y, value in points}
    all_values = list(value_map.values())
    min_value = min(all_values)
    max_value = max(all_values)
    if min_value == max_value:
        min_value -= 1.0
        max_value += 1.0

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    cell_width = plot_width / max(len(x_values), 1)
    cell_height = plot_height / max(len(y_values), 1)

    cells: list[str] = []
    x_labels: list[str] = []
    y_labels: list[str] = []

    for x_index, x_value in enumerate(x_values):
        x = margin_left + x_index * cell_width
        x_labels.append(
            f'<text x="{x + cell_width / 2:.1f}" y="{height - margin_bottom + 24}" font-size="12" text-anchor="middle" fill="#495057">{x_value}</text>'
        )

    for y_index, y_value in enumerate(y_values):
        y = margin_top + y_index * cell_height
        y_labels.append(
            f'<text x="{margin_left - 10}" y="{y + cell_height / 2 + 4:.1f}" font-size="12" text-anchor="end" fill="#495057">{y_value}</text>'
        )
        for x_index, x_value in enumerate(x_values):
            x = margin_left + x_index * cell_width
            value = value_map.get((x_value, y_value))
            if value is None:
                fill = "#f1f3f5"
                label = ""
            else:
                fill = _heatmap_color(value, min_value, max_value)
                label = f"{value:.2f}"
            cells.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_width:.1f}" height="{cell_height:.1f}" fill="{fill}" stroke="#ffffff" stroke-width="2" />'
            )
            if label:
                cells.append(
                    f'<text x="{x + cell_width / 2:.1f}" y="{y + cell_height / 2 + 4:.1f}" font-size="12" text-anchor="middle" fill="#212529">{label}</text>'
                )

    legend_x = width - margin_right + 20
    legend_items = []
    for index in range(5):
        ratio = index / 4
        value = min_value + (max_value - min_value) * ratio
        y = margin_top + plot_height - (plot_height * ratio)
        legend_items.append(
            f'<rect x="{legend_x}" y="{y - 10:.1f}" width="20" height="20" fill="{_heatmap_color(value, min_value, max_value)}" />'
        )
        legend_items.append(
            f'<text x="{legend_x + 28}" y="{y + 5:.1f}" font-size="12" fill="#495057">{value:.2f}</text>'
        )

    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#ffffff" />',
            f'<text x="{margin_left}" y="30" font-size="24" font-weight="bold" fill="#212529">{title}</text>',
            *cells,
            *x_labels,
            *y_labels,
            *legend_items,
            f'<text x="{margin_left + plot_width / 2:.1f}" y="{height - 28}" font-size="12" text-anchor="middle" fill="#495057">{x_label}</text>',
            f'<text x="30" y="{margin_top + plot_height / 2:.1f}" font-size="12" fill="#495057" transform="rotate(-90 30 {margin_top + plot_height / 2:.1f})">{y_label}</text>',
            "</svg>",
        ]
    )


def _heatmap_color(value: float, min_value: float, max_value: float) -> str:
    ratio = (value - min_value) / (max_value - min_value)
    red = int(240 - 120 * ratio)
    green = int(245 - 40 * ratio)
    blue = int(255 - 180 * ratio)
    return f"rgb({red},{green},{blue})"
