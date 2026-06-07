from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path

from .config import BacktestConfig
from .market import is_a_share_symbol
from .models import BacktestMetrics, BenchmarkPoint, EquityPoint, RebalanceRecord

_ZH_LABELS = {
    "date": "日期",
    "equity": "权益",
    "daily_return": "单期收益",
    "holdings": "持仓",
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
    "periods": "周期数",
    "benchmark_total_return": "基准总收益",
    "benchmark_annualized_return": "基准年化收益",
    "benchmark_volatility": "基准波动率",
    "benchmark_max_drawdown": "基准最大回撤",
    "excess_return": "超额收益",
    "tracking_error": "跟踪误差",
    "information_ratio": "信息比率",
    "run_id": "内部编号",
    "scheme_label": "方案编号",
    "output_dir": "输出目录",
    "rank": "名次",
    "initial_cash": "初始资金",
    "top_n": "持仓数量TopN",
    "rebalance_every_n_days": "调仓间隔天数",
    "lookback_momentum": "动量回看窗口",
    "lookback_mean_reversion": "均值回归回看窗口",
    "lookback_volatility": "波动率回看窗口",
    "commission_rate": "佣金率",
    "slippage_rate": "滑点率",
    "stamp_duty_rate": "印花税率",
    "price_field": "价格字段",
    "equity_curve_csv": "净值曲线CSV",
    "run_manifest_json": "运行清单JSON",
    "equity_curve_svg": "净值曲线图",
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


def save_performance_summary_json(metrics: BacktestMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.json"
    payload = {
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
        "artifacts": {name: str(path) for name, path in artifacts.items()},
        "metrics": asdict(metrics),
    }
    with target_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
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
      <h2>配置摘要</h2>
      <table>
        <tr><th>{_display_label("initial_cash")}</th><td>{config.initial_cash:,.2f}</td></tr>
        <tr><th>{_display_label("top_n")}</th><td>{config.top_n}</td></tr>
        <tr><th>{_display_label("rebalance_every_n_days")}</th><td>{config.rebalance_every_n_days}</td></tr>
        <tr><th>{_display_label("price_field")}</th><td>{escape(config.price_field)}</td></tr>
        <tr><th>{_display_label("commission_rate")}</th><td>{config.commission_rate:.6f}</td></tr>
        <tr><th>{_display_label("slippage_rate")}</th><td>{config.slippage_rate:.6f}</td></tr>
        <tr><th>{_display_label("stamp_duty_rate")}</th><td>{config.stamp_duty_rate:.6f}</td></tr>
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
        "reader_friendly": _build_ranked_batch_json_summary(ranked_rows, rank_by),
        "rows": ranked_rows,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(leaderboard_payload, handle, ensure_ascii=False, indent=2)

    best_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rank_by": rank_by,
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
        "best_metric_value": None if best_row is None else _format_metric_value(rank_by, best_row.get(rank_by)),
        "worst_scheme": None if worst_row is None else _format_run_label(worst_row, len(ranked_rows)),
        "worst_internal_id": None if worst_row is None else str(worst_row.get("run_id", "")),
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
            "rank_metric": _display_label(rank_by),
            "best_metric_value": None,
        }
    return {
        "best_scheme": _format_run_label(best_row, 1),
        "best_internal_id": str(best_row.get("run_id", "")),
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
    target_path = output_dir / "batch_report.html"
    sorted_rows = _sort_rows_by_metric(rows, rank_by)
    top_rows = sorted_rows[:10]
    best_row = sorted_rows[0] if sorted_rows else None
    headers = [
        "scheme_label",
        "run_id",
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
    observation_rows = _build_batch_observation_rows(sorted_rows, rank_by)
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
        key=lambda row: _float_metric(row, rank_by, default=float("-inf")),
        reverse=True,
    )


def _serialize_config(config: BacktestConfig) -> dict[str, object]:
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
        "output_dir": str(config.output_dir),
        "symbol_name_csv": None if config.symbol_name_csv is None else str(config.symbol_name_csv),
        "factor_weights": config.factor_weights,
    }


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
