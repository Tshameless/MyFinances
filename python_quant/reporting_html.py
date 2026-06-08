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
    run_id: str,
    metrics: BacktestMetrics,
    artifacts: dict[str, Path],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"{run_id}_report.html"

    conclusion = _build_report_conclusion(metrics)
    metric_rows = _build_html_table_rows(_build_single_run_metric_rows(metrics))
    review_rows = _build_html_table_rows(_build_single_run_review_rows(artifacts))
    behavior_rows = _build_html_table_rows(_build_trading_behavior_rows(artifacts))
    quality_rows = _build_html_table_rows(_build_data_quality_rows(artifacts))
    artifact_links = _build_artifact_links(artifacts)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>A股单次运行报告 - {escape(run_id)}</title>
  <style>{_report_base_css(include_images=True)}</style>
</head>
<body>
  <h1>A股回测单次运行报告：{escape(run_id)}</h1>
  <p class="muted">生成时间：{escape(datetime.now().isoformat(timespec="seconds"))}</p>
  <div class="grid">
    <div class="card wide hero">
      <h2>回测结论</h2>
      <p class="lead">{escape(conclusion)}</p>
    </div>
    <div class="card">
      <h2>核心指标</h2>
      <table>{metric_rows}</table>
    </div>
    <div class="card">
      <h2>诊断审查</h2>
      <table>{review_rows}</table>
    </div>
    <div class="card">
      <h2>交易行为</h2>
      <table>{behavior_rows}</table>
    </div>
    <div class="card">
      <h2>数据质量</h2>
      <table>{quality_rows}</table>
    </div>
    <div class="card wide">
      <h2>资产曲线</h2>
      <img src="equity_curve.svg" alt="资产曲线图" />
    </div>
    <div class="card wide">
      <h2>产物清单</h2>
      <ul>{artifact_links}</ul>
    </div>
  </div>
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
    rationale = summary.get("parameter_recommendation_rationale")
    if not isinstance(rationale, dict) or not rationale:
        return "-"
    reasons = [
        _format_recommendation_summary_text(payload.get("reason", "-"))
        for payload in rationale.values()
        if isinstance(payload, dict)
    ]
    if not reasons:
        return "-"
    return "; ".join(sorted(set(reasons)))


def _format_recommendation_reason(reason: str) -> str:
    reason_map = {
        "highest_average_composite_score": "综合平均分最高",
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


def _format_recommendation_summary_text(reason: str) -> str:
    summary_map = {
        "highest_average_composite_score": "基于综合多维评分优选",
        "best_passing_rate_tie_breaker": "在多项表现相近时考虑了抗跌存活率",
        "highest_average_metric": "基于目标优化指标最大化优选",
        "only_value_with_passes": "排除了导致严重亏损或违规的参数域",
        "fallback_highest_metric": "在缺乏稳定性特征时基于绝对收益优选",
        "insufficient_data": "样本量不足以支持参数稳定性推断",
    }
    return summary_map.get(reason, reason)


def _format_recommended_action_text(action: str) -> str:
    action_map = {
        "deploy_with_recommended_parameters": "考虑使用推荐的稳健参数档位实盘部署。",
        "further_optimize_strongest_parameter": "强烈建议围绕最具影响力的参数进行细粒度二次网格搜索。",
        "review_gate_failures": "策略在健康检查闸门上的失败率极高，请立刻检查导致失败的主要原因（见诊断面板）。",
        "beware_parameter_island": "警告：当前的最佳参数表现出孤岛特征，周围参数效果大幅劣化，过拟合风险极高！",
        "insufficient_data_for_island_detection": "扫描的参数组合太少，无法判断是否存在参数孤岛过拟合风险。",
    }
    return action_map.get(action, action)


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

