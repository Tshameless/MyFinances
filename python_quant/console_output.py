from __future__ import annotations

from pathlib import Path

_SINGLE_RUN_ARTIFACT_MESSAGES = (
    ("净值曲线 CSV", "equity_curve_csv"),
    ("调仓日志 CSV", "rebalance_log_csv"),
    ("每日持仓账本 CSV", "positions_csv"),
    ("逐笔交易明细 CSV", "trades_csv"),
    ("未成交原因 CSV", "trade_attempts_csv"),
    ("因子评分明细 CSV", "factor_scores_csv"),
    ("因子 IC 分析 CSV", "factor_ic_csv"),
    ("因子分组收益 CSV", "factor_group_returns_csv"),
    ("因子衰减分析 CSV", "factor_decay_csv"),
    ("因子相关性矩阵 CSV", "factor_correlation_csv"),
    ("回撤序列 CSV", "drawdown_csv"),
    ("月度收益 CSV", "monthly_returns_csv"),
    ("滚动风险 CSV", "rolling_risk_csv"),
    ("相对基准表现 CSV", "relative_performance_csv"),
    ("执行质量 CSV", "execution_quality_csv"),
    ("持仓暴露 CSV", "exposure_csv"),
    ("分组暴露 CSV", "group_exposure_csv"),
    ("收益归因 CSV", "return_attribution_csv"),
    ("成本归因 CSV", "cost_attribution_csv"),
    ("盈亏对账 CSV", "pnl_ledger_csv"),
    ("策略健康诊断 CSV", "strategy_health_csv"),
    ("策略风险闸门 CSV", "strategy_health_gates_csv"),
    ("绩效摘要 CSV", "performance_summary_csv"),
    ("绩效摘要 JSON", "performance_summary_json"),
    ("最终生效配置 JSON", "config_effective_json"),
    ("配置来源 JSON", "config_sources_json"),
    ("运行清单 JSON", "run_manifest_json"),
    ("净值图 SVG", "equity_curve_svg"),
    ("HTML 报告", "report_html"),
    ("停牌分析 CSV", "suspension_analysis_csv"),
    ("停牌日汇总 CSV", "suspension_daily_csv"),
)


def print_single_run_artifacts(artifact_paths: dict[str, Path]) -> None:
    for label, artifact_key in _SINGLE_RUN_ARTIFACT_MESSAGES:
        separator = "" if label.endswith("报告") else " "
        print(f"{label}{separator}已保存：{artifact_paths[artifact_key]}")


def print_walk_forward_optimization_artifacts(
    *,
    row_count: int,
    paths: dict[str, Path],
    report_path: Path,
) -> None:
    print(f"Walk-forward 优化完成，共运行 {row_count} 个训练/测试窗口。")
    print(f"Walk-forward 优化 CSV 已保存：{paths['walk_forward_optimization_csv']}")
    print(f"Walk-forward 优化 JSON 已保存：{paths['walk_forward_optimization_json']}")
    print(f"Walk-forward 优化 HTML 报告已保存：{report_path}")
