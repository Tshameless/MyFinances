from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path

from .config import BacktestConfig
from .models import BacktestMetrics, BenchmarkPoint, EquityPoint, RebalanceRecord
from .reporting_labels import chinese_label, display_label, format_symbol, metric_explanation
from .reporting_rank import float_metric, sort_rows_by_metric, validate_rank_metric
from .reporting_svg import build_bar_chart_svg, build_heatmap_svg

_HUMAN_READABLE_ENCODING = "utf-8-sig"


def save_single_run_report_html(
    *,
    output_dir: Path,
    config: BacktestConfig,
    metrics: BacktestMetrics,
    artifacts: dict[str, Path],
    latest_holdings: tuple[str, ...] = (),
    latest_rebalance: RebalanceRecord | None = None,
    symbol_names: dict[str, str] | None = None,
    equity_curve: list[EquityPoint] | None = None,
    benchmark_curve: list[BenchmarkPoint] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "report.html"
    
    json_dates = "[]"
    json_portfolio = "[]"
    json_benchmark = "[]"
    if equity_curve:
        dates = [point.date.isoformat() for point in equity_curve]
        portfolio = [point.equity for point in equity_curve]
        json_dates = json.dumps(dates)
        json_portfolio = json.dumps(portfolio)
    if benchmark_curve:
        benchmark = [point.equity for point in benchmark_curve]
        json_benchmark = json.dumps(benchmark)
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
        f"<tr><th>{escape(display_label(key))}</th><td>{escape(metric_explanation(key))}</td></tr>"
        for key in ("total_return", "annualized_return", "max_drawdown", "sharpe")
    )
    holdings_rows = "\n".join(
        f"<tr><th>{escape(symbol)}</th><td>{escape(format_symbol(symbol, symbol_names))}</td></tr>"
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
      <div id="echarts-container" style="width: 100%; height: 400px; display: none;"></div>
      <div id="svg-fallback-container">
        <img src="{escape(chart_name)}" alt="{escape(chart_title)}" />
      </div>
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
        <tr><th>{display_label("initial_cash")}</th><td>{config.initial_cash:,.2f}</td></tr>
        <tr><th>{display_label("top_n")}</th><td>{config.top_n}</td></tr>
        <tr><th>{display_label("selection_mode")}</th><td>{escape(config.selection_mode)}</td></tr>
        <tr><th>{display_label("score_source")}</th><td>{escape(config.score_source)}</td></tr>
        <tr><th>{display_label("lot_size")}</th><td>{config.lot_size}</td></tr>
        <tr><th>{display_label("max_group_positions")}</th><td>{_format_optional_int(config.max_group_positions)}</td></tr>
        <tr><th>{display_label("rolling_risk_window")}</th><td>{config.rolling_risk_window}</td></tr>
        <tr><th>{display_label("max_allowed_drawdown")}</th><td>{config.max_allowed_drawdown:.2%}</td></tr>
        <tr><th>{display_label("max_allowed_daily_var")}</th><td>{config.max_allowed_daily_var:.2%}</td></tr>
        <tr><th>{display_label("min_allowed_rolling_return")}</th><td>{config.min_allowed_rolling_return:.2%}</td></tr>
        <tr><th>{display_label("min_allowed_information_ratio")}</th><td>{config.min_allowed_information_ratio:.3f}</td></tr>
        <tr><th>{display_label("min_allowed_fill_rate")}</th><td>{config.min_allowed_fill_rate:.2%}</td></tr>
        <tr><th>{display_label("min_allowed_execution_price_coverage")}</th><td>{config.min_allowed_execution_price_coverage:.2%}</td></tr>
        <tr><th>{display_label("max_allowed_position_weight")}</th><td>{config.max_allowed_position_weight:.2%}</td></tr>
        <tr><th>{display_label("max_allowed_group_weight")}</th><td>{config.max_allowed_group_weight:.2%}</td></tr>
        <tr><th>{display_label("max_allowed_attribution_residual")}</th><td>{config.max_allowed_attribution_residual:.2%}</td></tr>
        <tr><th>{display_label("rebalance_every_n_days")}</th><td>{config.rebalance_every_n_days}</td></tr>
        <tr><th>{display_label("price_field")}</th><td>{escape(config.price_field)}</td></tr>
        <tr><th>{display_label("start_date")}</th><td>{_format_optional_date(config.start_date)}</td></tr>
        <tr><th>{display_label("end_date")}</th><td>{_format_optional_date(config.end_date)}</td></tr>
        <tr><th>{display_label("commission_rate")}</th><td>{config.commission_rate:.6f}</td></tr>
        <tr><th>{display_label("buy_commission_rate")}</th><td>{_format_optional_rate(config.buy_commission_rate)}</td></tr>
        <tr><th>{display_label("sell_commission_rate")}</th><td>{_format_optional_rate(config.sell_commission_rate)}</td></tr>
        <tr><th>{display_label("slippage_rate")}</th><td>{config.slippage_rate:.6f}</td></tr>
        <tr><th>{display_label("market_impact_coefficient")}</th><td>{config.market_impact_coefficient:.6f}</td></tr>
        <tr><th>{display_label("market_impact_exponent")}</th><td>{config.market_impact_exponent:.6f}</td></tr>
        <tr><th>{display_label("stamp_duty_rate")}</th><td>{config.stamp_duty_rate:.6f}</td></tr>
        <tr><th>{display_label("min_commission")}</th><td>{config.min_commission:.2f}</td></tr>
        <tr><th>{display_label("transfer_fee_rate")}</th><td>{config.transfer_fee_rate:.6f}</td></tr>
        <tr><th>{display_label("target_cash_weight")}</th><td>{config.target_cash_weight:.2%}</td></tr>
        <tr><th>{display_label("max_position_weight")}</th><td>{config.max_position_weight:.2%}</td></tr>
        <tr><th>{display_label("infer_limit_flags")}</th><td>{config.infer_limit_flags}</td></tr>
        <tr><th>{display_label("forward_fill_suspended_bars")}</th><td>{config.forward_fill_suspended_bars}</td></tr>
        <tr><th>{display_label("limit_up_down_rate")}</th><td>{config.limit_up_down_rate:.4f}</td></tr>
        <tr><th>{display_label("st_limit_up_down_rate")}</th><td>{config.st_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{display_label("growth_limit_up_down_rate")}</th><td>{config.growth_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{display_label("bse_limit_up_down_rate")}</th><td>{config.bse_limit_up_down_rate:.4f}</td></tr>
        <tr><th>{display_label("infer_limit_rate_by_symbol")}</th><td>{config.infer_limit_rate_by_symbol}</td></tr>
        <tr><th>{display_label("max_volume_participation")}</th><td>{config.max_volume_participation:.4f}</td></tr>
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
  </div>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <script>
  (function() {{
    if (typeof echarts !== 'undefined') {{
      var dates = {json_dates};
      var portfolio = {json_portfolio};
      var benchmark = {json_benchmark};
      
      var fallback = document.getElementById('svg-fallback-container');
      if (fallback) fallback.style.display = 'none';
      
      var container = document.getElementById('echarts-container');
      if (container) {{
        container.style.display = 'block';
        var chart = echarts.init(container);
        
        var series = [{{
          name: '策略净值',
          type: 'line',
          data: portfolio,
          showSymbol: false,
          smooth: true,
          lineStyle: {{ width: 2, color: '#1890ff' }},
          itemStyle: {{ color: '#1890ff' }}
        }}];
        
        var legendData = ['策略净值'];
        if (benchmark && benchmark.length > 0) {{
          series.push({{
            name: '基准净值',
            type: 'line',
            data: benchmark,
            showSymbol: false,
            smooth: true,
            lineStyle: {{ width: 1.5, color: '#ff4d4f', type: 'dashed' }},
            itemStyle: {{ color: '#ff4d4f' }}
          }});
          legendData.push('基准净值');
        }}
        
        var option = {{
          tooltip: {{
            trigger: 'axis',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            borderColor: '#d9e2ec',
            borderWidth: 1,
            textStyle: {{ color: '#1f2933' }},
            formatter: function(params) {{
              var res = '<div style="font-weight:600;margin-bottom:4px;">' + params[0].name + '</div>';
              params.forEach(function(item) {{
                res += '<div style="display:flex;justify-content:space-between;align-items:center;min-width:120px;margin:2px 0;">' +
                       '<span>' + item.marker + ' ' + item.seriesName + ':</span>' +
                       '<span style="font-weight:600;margin-left:8px;">' + Number(item.value).toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + '</span>' +
                       '</div>';
              }});
              return res;
            }}
          }},
          legend: {{
            data: legendData,
            bottom: 0,
            textStyle: {{ color: '#52606d' }}
          }},
          grid: {{
            left: '3%',
            right: '4%',
            top: '5%',
            bottom: '12%',
            containLabel: true
          }},
          xAxis: {{
            type: 'category',
            boundaryGap: false,
            data: dates,
            axisLine: {{ lineStyle: {{ color: '#d9e2ec' }} }},
            axisLabel: {{ color: '#52606d' }}
          }},
          yAxis: {{
            type: 'value',
            scale: true,
            axisLine: {{ show: false }},
            axisTick: {{ show: false }},
            splitLine: {{ lineStyle: {{ color: '#eef2f7' }} }},
            axisLabel: {{ color: '#52606d' }}
          }},
          series: series
        }};
        
        chart.setOption(option);
        window.addEventListener('resize', function() {{
          chart.resize();
        }});
      }}
    }}
  }})();
  </script>
</body>
</html>
"""
    target_path.write_text(html, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


def save_batch_report_html(
    *,
    output_dir: Path,
    rows: list[dict[str, object]],
    rank_by: str,
    artifacts: dict[str, Path],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    validate_rank_metric(rows, rank_by)
    target_path = output_dir / "batch_report.html"
    sorted_rows = sort_rows_by_metric(rows, rank_by)
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
  <style>{_report_base_css(include_images=True)}</style>
</head>
<body>
  <h1>A股参数扫描报告</h1>
  <p class="muted">生成时间：{escape(datetime.now().isoformat(timespec="seconds"))}。排序指标：{escape(display_label(rank_by))}。</p>
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
        <thead><tr>{"".join(f"<th>{escape(display_label(header))}</th>" for header in headers)}</tr></thead>
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
    chart_blocks = _build_walk_forward_chart_blocks(rows, summary, optimization=optimization)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <style>{_report_base_css(include_images=False)}</style>
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
    {"".join(chart_blocks)}
    <div class="card wide">
      <h2>窗口预览</h2>
      <table>
        <thead><tr>{"".join(f"<th>{escape(display_label(header))}</th>" for header in headers)}</tr></thead>
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
        f"排序指标 {display_label(rank_by)} 为 {best_value}。"
    )


def _report_base_css(*, include_images: bool) -> str:
    image_css = (
        "img { width: 100%; border: 1px solid #d9e2ec; border-radius: 10px; background: white; }\n"
        if include_images
        else ""
    )
    return f"""
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; background: #f8fafc; }}
    h1, h2 {{ margin: 0 0 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }}
    .card {{ background: white; border: 1px solid #d9e2ec; border-radius: 12px; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eef2f7; font-size: 14px; }}
    th {{ color: #52606d; font-weight: 600; }}
    ul {{ margin: 0; padding-left: 20px; }}
    {image_css}    .muted {{ color: #52606d; margin-bottom: 16px; }}
    .wide {{ grid-column: 1 / -1; }}
    .hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef6ff 100%); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }}
    .summary-tile {{ border: 1px solid #d9e2ec; border-radius: 12px; padding: 14px; background: #fff; }}
    .summary-label {{ color: #52606d; font-size: 12px; margin-bottom: 6px; }}
    .summary-value {{ font-size: 24px; font-weight: 700; color: #102a43; }}
    .lead {{ font-size: 16px; line-height: 1.7; color: #243b53; }}
    """


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


def _build_walk_forward_chart_blocks(
    rows: list[dict[str, object]],
    summary: dict[str, object],
    *,
    optimization: bool,
) -> list[str]:
    if optimization:
        chart_specs = [
            (
                "测试窗口年化收益",
                _chart_points(rows, "window_id", "test_annualized_return"),
                "#2f9e44",
                "年化收益",
            ),
            (
                "训练/测试年化差距",
                _chart_points(rows, "window_id", "train_test_annualized_gap"),
                "#f08c00",
                "年化差距",
            ),
            (
                "参数漂移次数",
                _count_chart_points(summary, "parameter_drift_counts"),
                "#5c7cfa",
                "漂移次数",
            ),
        ]
    else:
        chart_specs = [
            (
                "Walk-forward窗口年化收益",
                _chart_points(rows, "window_id", "annualized_return"),
                "#2f9e44",
                "年化收益",
            ),
            (
                "Walk-forward窗口最大回撤",
                _chart_points(rows, "window_id", "max_drawdown"),
                "#e03131",
                "最大回撤",
            ),
        ]
    return [
        f'<div class="card wide"><h2>{escape(title)}</h2>{svg}</div>'
        for title, points, color, y_label in chart_specs
        for svg in [
            build_bar_chart_svg(
                title=title,
                points=points,
                bar_color=color,
                y_axis_label=y_label,
            )
        ]
    ]


def _chart_points(rows: list[dict[str, object]], label_key: str, value_key: str) -> list[tuple[str, float]]:
    return [
        (str(row.get(label_key, index + 1)), _coerce_float(row.get(value_key, 0.0)))
        for index, row in enumerate(rows)
        if row.get(value_key) not in (None, "")
    ]


def _count_chart_points(summary: dict[str, object], key: str) -> list[tuple[str, float]]:
    counts = summary.get(key)
    if not isinstance(counts, dict):
        return []
    return [
        (str(name), _coerce_float(count))
        for name, count in sorted(counts.items())
    ]


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
            _summary_card(display_label(rank_by), _format_metric_value(rank_by, best_row.get(rank_by))),
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
        f"<tr><th>{escape(display_label(key))}</th><td>{escape(str(value))}</td></tr>"
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
                ("推荐参数匹配方案数", _format_recommended_match_count(sorted_rows)),
                ("推荐参数匹配率", _format_recommended_match_rate(sorted_rows)),
                ("最佳推荐参数匹配方案", _format_best_recommended_match(sorted_rows)),
                ("建议动作", _format_recommended_action_first(stability_summary)),
                ("建议动作数量", _format_list_count(stability_summary, "recommended_actions")),
            ]
        )
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


def _recommended_match_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if row.get("matches_recommended_parameters") is True
    ]


def _format_recommended_match_count(rows: list[dict[str, object]]) -> str:
    if not rows or not any("matches_recommended_parameters" in row for row in rows):
        return "-"
    return str(len(_recommended_match_rows(rows)))


def _format_recommended_match_rate(rows: list[dict[str, object]]) -> str:
    if not rows or not any("matches_recommended_parameters" in row for row in rows):
        return "-"
    return f"{len(_recommended_match_rows(rows)) / len(rows):.2%}"


def _format_best_recommended_match(rows: list[dict[str, object]]) -> str:
    matched_rows = _recommended_match_rows(rows)
    if not matched_rows:
        return "-"
    return _format_run_label(matched_rows[0], rows.index(matched_rows[0]) + 1)


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
            chinese_label(metric_name),
            metric_explanation(metric_name),
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
        (display_label("total_return"), f"{metrics.total_return:.2%}"),
        (display_label("annualized_return"), f"{metrics.annualized_return:.2%}"),
        (display_label("max_drawdown"), f"{metrics.max_drawdown:.2%}"),
        (display_label("volatility"), f"{metrics.volatility:.2%}"),
        (display_label("downside_volatility"), f"{metrics.downside_volatility:.2%}"),
        (display_label("sharpe"), f"{metrics.sharpe:.3f}"),
        (display_label("sortino"), f"{metrics.sortino:.3f}"),
        (display_label("calmar"), f"{metrics.calmar:.3f}"),
        (display_label("win_rate"), f"{metrics.win_rate:.2%}"),
        (display_label("average_turnover"), f"{metrics.average_turnover:.2%}"),
        (display_label("total_cost"), f"{metrics.total_cost:,.2f}"),
    ]
    if _has_benchmark_metrics(metrics):
        rows.extend(
            [
                (display_label("benchmark_total_return"), f"{metrics.benchmark_total_return:.2%}"),
                (display_label("excess_return"), f"{metrics.excess_return:.2%}"),
                (display_label("tracking_error"), f"{metrics.tracking_error:.2%}"),
                (display_label("information_ratio"), f"{metrics.information_ratio:.3f}"),
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
        f'<li><a href="{escape(path.name)}">{escape(display_label(name))}</a></li>'
        for name, path in artifacts.items()
    )


def _build_batch_chart_blocks(artifacts: dict[str, Path]) -> list[str]:
    chart_blocks: list[str] = []
    for key in ("batch_chart_svg", "batch_heatmap_svg"):
        if key in artifacts:
            chart_blocks.append(
                f'<div class="card"><h2>{escape(display_label(key))}</h2><img src="{escape(artifacts[key].name)}" alt="{escape(display_label(key))}" /></div>'
            )
    return chart_blocks


def _build_html_table_rows(rows: list[tuple[str, str]]) -> str:
    return "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )


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


def _format_recommendation_reason(reason: str) -> str:
    reason_map = {
        "highest_average_composite_score": "平均综合分最高",
        "best_passing_rate_tie_breaker": "同分下闸门通过率最高",
        "highest_average_metric": "平均排序指标最高",
        "only_value_with_passes": "唯一通过测试的取值",
        "fallback_highest_metric": "退化至排序指标最高",
        "insufficient_data": "数据不足",
    }
    return reason_map.get(reason, reason)


def _format_recommended_action_first(summary: dict[str, object]) -> str:
    actions = summary.get("recommended_actions")
    if not isinstance(actions, list) or not actions:
        return "-"
    return _format_recommended_action_text(str(actions[0]))


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


def _build_report_conclusion(metrics: BacktestMetrics) -> str:
    if metrics.total_return > 0 and metrics.annualized_return > 0.15 and metrics.max_drawdown > -0.15:
        base = f"本次回测表现优异。在 {metrics.periods} 个交易日内实现了 {metrics.annualized_return:.2%} 的年化收益率，且最大回撤控制在 {metrics.max_drawdown:.2%}。"
    elif metrics.total_return > 0:
        base = f"本次回测表现尚可。年化收益率为 {metrics.annualized_return:.2%}，但需注意最大回撤为 {metrics.max_drawdown:.2%}。"
    else:
        base = f"本次回测表现不佳。策略录得 {-metrics.total_return:.2%} 的亏损，最大回撤达到 {metrics.max_drawdown:.2%}。"
    
    benchmark = _build_benchmark_conclusion(metrics)
    return f"{base} {benchmark}".strip()


def _build_benchmark_conclusion(metrics: BacktestMetrics) -> str:
    if not _has_benchmark_metrics(metrics):
        return ""
    if metrics.excess_return is not None and metrics.excess_return > 0:
        return f"相比基准，策略创造了 {metrics.excess_return:.2%} 的超额收益，体现了显著的 Alpha 能力。"
    return f"未能跑赢基准（超额收益：{getattr(metrics, 'excess_return', 0.0):.2%}），Alpha 能力不足。"


def _summary_card(label: str, value: str) -> str:
    return f'<div class="summary-tile"><div class="summary-label">{escape(label)}</div><div class="summary-value">{escape(value)}</div></div>'


def _build_rebalance_summary_rows(record: RebalanceRecord) -> str:
    rows = [
        ("日期", record.date.isoformat()),
        ("目标持仓数量", str(len(record.target_positions))),
        ("卖出指令数量", str(len(record.sell_trades))),
        ("买入指令数量", str(len(record.buy_trades))),
        ("忽略指令数量", str(len(record.ignored_trades))),
        ("期初可用资金", _format_money(record.pre_rebalance_cash)),
        ("买入消耗资金", _format_money(record.total_buy_value)),
        ("卖出获得资金", _format_money(record.total_sell_value)),
        ("期末可用资金", _format_money(record.post_rebalance_cash)),
        ("总交易成本", _format_money(record.total_cost)),
    ]
    return _build_html_table_rows(rows)


def _build_benchmark_summary_rows(point: BenchmarkPoint) -> str:
    rows = [
        ("日期", point.date.isoformat()),
        ("基准每日收益", _format_pct(point.daily_return)),
        ("基准累计收益", _format_pct(point.cumulative_return)),
        ("基准高水位", _format_pct(point.high_water_mark)),
        ("基准回撤", _format_pct(point.drawdown)),
    ]
    return _build_html_table_rows(rows)


def _format_pct(value: float) -> str:
    return f"{value:.2%}"


def _format_money(value: float) -> str:
    return f"¥{value:,.2f}"


def _format_optional_date(value: str | None) -> str:
    return escape(value) if value else "-"


def _format_optional_rate(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "-"


def _format_optional_int(value: int | None) -> str:
    return str(value) if value is not None else "-"


def _build_equity_curve_benchmark_columns(points: list[EquityPoint]) -> str:
    if not points or getattr(points[0], "benchmark_cumulative_return", None) is None:
        return ""
    return "<th>基准累计收益</th><th>基准回撤</th><th>超额收益</th>"


def _equity_curve_note(points: list[EquityPoint]) -> str:
    if not points or getattr(points[0], "benchmark_cumulative_return", None) is None:
        return ""
    return "<tr><td colspan='7' class='muted'>包含基准对比数据</td></tr>"


def _rebalance_note(points: list[EquityPoint]) -> str:
    if not any(point.rebalance_record for point in points):
        return "<tr><td colspan='2' class='muted'>此区间无调仓记录</td></tr>"
    return ""


def _format_holdings(holdings: dict[str, float]) -> str:
    if not holdings:
        return "-"
    parts = [f"{symbol}: {_format_pct(weight)}" for symbol, weight in sorted(holdings.items())]
    return escape(", ".join(parts))


def _format_run_label(row: dict[str, object], default_index: int) -> str:
    scheme_label = row.get("scheme_label")
    if scheme_label:
        return str(scheme_label)
    run_id = str(row.get("run_id", "")).strip()
    if run_id.startswith("run_"):
        numeric_part = run_id.removeprefix("run_").lstrip("0") or "0"
        return f"方案{numeric_part}"
    if run_id:
        return run_id
    return str(row.get("scheme_label") or f"方案 {default_index:03d}")


def _build_batch_display_value(
    row: dict[str, object],
    header: str,
    row_index: int,
) -> object:
    if header == "scheme_label":
        return _format_run_label(row, row_index)
    value = row.get(header, "-")
    if header.startswith("param_") and isinstance(value, float):
        if value.is_integer():
            return int(value)
        return round(value, 6)
    if value in (None, ""):
        return "-"
    if header == "matches_recommended_parameters":
        return "⭐ 强烈推荐" if value is True else "-"
    if header in ("gate_failures", "health_warnings", "critical_warnings"):
        return "-" if _coerce_float(value) == 0 else int(_coerce_float(value))
    return _format_metric_value(header, value)


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
    return " | ".join(format_symbol(symbol, symbol_names) for symbol in holdings)

