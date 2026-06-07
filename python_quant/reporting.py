from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path

from .config import BacktestConfig
from .models import BacktestMetrics, BenchmarkPoint, EquityPoint, RebalanceRecord


def print_summary(
    curve: list[EquityPoint],
    rebalances: list[RebalanceRecord],
    metrics: BacktestMetrics,
    config: BacktestConfig,
) -> None:
    print("=" * 60)
    print("MyFinances Python Quant Backtest Summary")
    print(f"Periods: {metrics.periods}")
    print(f"Rebalances:   {len(rebalances)}")
    print(f"Start equity: {config.initial_cash:,.2f}")
    print(f"End equity:   {curve[-1].equity:,.2f}")
    print(f"Total return: {metrics.total_return:.2%}")
    print(f"Annualized:   {metrics.annualized_return:.2%}")
    print(f"Max drawdown: {metrics.max_drawdown:.2%}")
    print(f"Volatility:   {metrics.volatility:.2%}")
    print(f"Downside vol: {metrics.downside_volatility:.2%}")
    print(f"Sharpe:       {metrics.sharpe:.3f}")
    print(f"Sortino:      {metrics.sortino:.3f}")
    print(f"Calmar:       {metrics.calmar:.3f}")
    print(f"Win rate:     {metrics.win_rate:.2%}")
    print(f"Avg turnover: {metrics.average_turnover:.2%}")
    print(f"Total cost:   {metrics.total_cost:,.2f}")
    if metrics.benchmark_total_return is not None:
        print(f"Benchmark:    {metrics.benchmark_total_return:.2%}")
        print(f"Track error:  {metrics.tracking_error:.2%}")
        print(f"Excess return:{metrics.excess_return:.2%}")
        print(f"Info ratio:   {metrics.information_ratio:.3f}")
    print("=" * 60)


def save_equity_curve(
    curve: list[EquityPoint],
    output_dir: Path,
    benchmark_curve: list[BenchmarkPoint] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "equity_curve.csv"
    benchmark_by_date = {point.date: point for point in benchmark_curve or []}

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "equity",
                "daily_return",
                "holdings",
                "benchmark_equity",
                "benchmark_daily_return",
                "excess_daily_return",
            ]
        )
        for point in curve:
            benchmark_point = benchmark_by_date.get(point.date)
            benchmark_equity = ""
            benchmark_return = ""
            excess_daily_return = ""
            if benchmark_point is not None:
                benchmark_equity = f"{benchmark_point.equity:.2f}"
                benchmark_return = f"{benchmark_point.daily_return:.8f}"
                excess_daily_return = f"{point.daily_return - benchmark_point.daily_return:.8f}"
            writer.writerow(
                [
                    point.date.isoformat(),
                    f"{point.equity:.2f}",
                    f"{point.daily_return:.8f}",
                    "|".join(point.holdings),
                    benchmark_equity,
                    benchmark_return,
                    excess_daily_return,
                ]
            )

    return target_path


def save_rebalance_log(rebalances: list[RebalanceRecord], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "rebalance_log.csv"

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "holdings", "buy_turnover", "sell_turnover", "turnover", "cost"])
        for record in rebalances:
            writer.writerow(
                [
                    record.date.isoformat(),
                    "|".join(record.holdings),
                    f"{record.buy_turnover:.8f}",
                    f"{record.sell_turnover:.8f}",
                    f"{record.turnover:.8f}",
                    f"{record.cost:.2f}",
                ]
            )

    return target_path


def save_performance_summary(metrics: BacktestMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.csv"

    summary_items = [
        ("total_return", f"{metrics.total_return:.8f}"),
        ("annualized_return", f"{metrics.annualized_return:.8f}"),
        ("max_drawdown", f"{metrics.max_drawdown:.8f}"),
        ("volatility", f"{metrics.volatility:.8f}"),
        ("downside_volatility", f"{metrics.downside_volatility:.8f}"),
        ("sharpe", f"{metrics.sharpe:.8f}"),
        ("sortino", f"{metrics.sortino:.8f}"),
        ("calmar", f"{metrics.calmar:.8f}"),
        ("win_rate", f"{metrics.win_rate:.8f}"),
        ("average_turnover", f"{metrics.average_turnover:.8f}"),
        ("total_cost", f"{metrics.total_cost:.2f}"),
        ("periods", str(metrics.periods)),
        (
            "benchmark_total_return",
            "" if metrics.benchmark_total_return is None else f"{metrics.benchmark_total_return:.8f}",
        ),
        (
            "benchmark_annualized_return",
            ""
            if metrics.benchmark_annualized_return is None
            else f"{metrics.benchmark_annualized_return:.8f}",
        ),
        (
            "benchmark_volatility",
            "" if metrics.benchmark_volatility is None else f"{metrics.benchmark_volatility:.8f}",
        ),
        (
            "benchmark_max_drawdown",
            ""
            if metrics.benchmark_max_drawdown is None
            else f"{metrics.benchmark_max_drawdown:.8f}",
        ),
        ("excess_return", "" if metrics.excess_return is None else f"{metrics.excess_return:.8f}"),
        ("tracking_error", "" if metrics.tracking_error is None else f"{metrics.tracking_error:.8f}"),
        (
            "information_ratio",
            "" if metrics.information_ratio is None else f"{metrics.information_ratio:.8f}",
        ),
    ]

    with target_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
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
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "report.html"
    rows = [
        ("Total return", f"{metrics.total_return:.2%}"),
        ("Annualized return", f"{metrics.annualized_return:.2%}"),
        ("Max drawdown", f"{metrics.max_drawdown:.2%}"),
        ("Volatility", f"{metrics.volatility:.2%}"),
        ("Downside volatility", f"{metrics.downside_volatility:.2%}"),
        ("Sharpe", f"{metrics.sharpe:.3f}"),
        ("Sortino", f"{metrics.sortino:.3f}"),
        ("Calmar", f"{metrics.calmar:.3f}"),
        ("Win rate", f"{metrics.win_rate:.2%}"),
        ("Average turnover", f"{metrics.average_turnover:.2%}"),
        ("Total cost", f"{metrics.total_cost:,.2f}"),
    ]
    if metrics.benchmark_total_return is not None:
        rows.extend(
            [
                ("Benchmark total return", f"{metrics.benchmark_total_return:.2%}"),
                ("Excess return", f"{metrics.excess_return:.2%}"),
                ("Tracking error", f"{metrics.tracking_error:.2%}"),
                ("Information ratio", f"{metrics.information_ratio:.3f}"),
            ]
        )

    artifact_links = "\n".join(
        f'<li><a href="{escape(path.name)}">{escape(name)}</a></li>'
        for name, path in artifacts.items()
    )
    metrics_rows = "\n".join(
        f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>"
        for label, value in rows
    )
    factor_rows = "\n".join(
        f"<tr><th>{escape(name)}</th><td>{weight:.4f}</td></tr>"
        for name, weight in config.factor_weights.items()
    )
    chart_name = artifacts["equity_curve_svg"].name if "equity_curve_svg" in artifacts else ""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>MyFinances Report</title>
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
  </style>
</head>
<body>
  <h1>MyFinances Backtest Report</h1>
  <p class="muted">Generated at {escape(datetime.now().isoformat(timespec="seconds"))}</p>
  <div class="grid">
    <div class="card">
      <h2>Equity Curve</h2>
      <img src="{escape(chart_name)}" alt="Equity Curve" />
    </div>
    <div class="card">
      <h2>Metrics</h2>
      <table>{metrics_rows}</table>
    </div>
    <div class="card">
      <h2>Configuration</h2>
      <table>
        <tr><th>Initial cash</th><td>{config.initial_cash:,.2f}</td></tr>
        <tr><th>Top N</th><td>{config.top_n}</td></tr>
        <tr><th>Rebalance days</th><td>{config.rebalance_every_n_days}</td></tr>
        <tr><th>Price field</th><td>{escape(config.price_field)}</td></tr>
        <tr><th>Commission rate</th><td>{config.commission_rate:.6f}</td></tr>
        <tr><th>Slippage rate</th><td>{config.slippage_rate:.6f}</td></tr>
        <tr><th>Stamp duty rate</th><td>{config.stamp_duty_rate:.6f}</td></tr>
      </table>
      <h2 style="margin-top:20px;">Factor Weights</h2>
      <table>{factor_rows}</table>
    </div>
    <div class="card">
      <h2>Artifacts</h2>
      <ul>{artifact_links}</ul>
    </div>
  </div>
</body>
</html>
"""
    target_path.write_text(html, encoding="utf-8")
    return target_path


def save_batch_summary(rows: list[dict[str, object]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "batch_summary.csv"
    json_path = output_dir / "batch_summary.json"

    if not rows:
        headers = ["run_id"]
    else:
        headers = list(rows[0].keys())

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)

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
    svg = _build_line_chart_svg(
        title="Equity Curve",
        series=[
            ("Portfolio", portfolio_points, "#0b7285"),
            ("Benchmark", benchmark_points, "#e67700"),
        ],
        y_axis_label="Equity",
    )
    target_path.write_text(svg, encoding="utf-8")
    return target_path


def save_batch_rankings(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    rank_by: str = "annualized_return",
) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked_rows = sorted(
        rows,
        key=lambda row: _float_metric(row, rank_by, default=float("-inf")),
        reverse=True,
    )
    for index, row in enumerate(ranked_rows, start=1):
        row["rank"] = index

    csv_path = output_dir / "batch_leaderboard.csv"
    json_path = output_dir / "batch_leaderboard.json"
    best_run_path = output_dir / "best_run.json"

    headers = list(ranked_rows[0].keys()) if ranked_rows else ["rank", "run_id"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(ranked_rows)

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(ranked_rows, handle, ensure_ascii=False, indent=2)

    best_payload = {
        "rank_by": rank_by,
        "best_run": ranked_rows[0] if ranked_rows else None,
    }
    with best_run_path.open("w", encoding="utf-8") as handle:
        json.dump(best_payload, handle, ensure_ascii=False, indent=2)

    return csv_path, json_path, best_run_path


def save_batch_chart_svg(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    metric: str = "annualized_return",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"batch_{metric}.svg"
    points = [
        (str(row["run_id"]), _float_metric(row, metric))
        for row in rows
        if metric in row and row[metric] not in ("", None)
    ]
    svg = _build_bar_chart_svg(
        title=f"Batch {metric}",
        points=points,
        bar_color="#5c7cfa",
        y_axis_label=metric,
    )
    target_path.write_text(svg, encoding="utf-8")
    return target_path


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
        title=f"{metric} Heatmap",
        x_label=x_field,
        y_label=y_field,
        points=points,
    )
    target_path.write_text(svg, encoding="utf-8")
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
    sorted_rows = sorted(
        rows,
        key=lambda row: _float_metric(row, rank_by, default=float("-inf")),
        reverse=True,
    )
    top_rows = sorted_rows[:10]
    headers = [
        "run_id",
        rank_by,
        "total_return",
        "sharpe",
        "sortino",
        "calmar",
    ]
    table_rows = "\n".join(
        "<tr>" + "".join(f"<td>{escape(str(row.get(header, '')))}</td>" for header in headers) + "</tr>"
        for row in top_rows
    )
    artifact_links = "\n".join(
        f'<li><a href="{escape(path.name)}">{escape(name)}</a></li>'
        for name, path in artifacts.items()
    )
    chart_blocks = []
    for key in ("batch_chart_svg", "batch_heatmap_svg"):
        if key in artifacts:
            chart_blocks.append(
                f'<div class="card"><h2>{escape(key)}</h2><img src="{escape(artifacts[key].name)}" alt="{escape(key)}" /></div>'
            )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>MyFinances Batch Report</title>
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
  </style>
</head>
<body>
  <h1>MyFinances Batch Sweep Report</h1>
  <p class="muted">Generated at {escape(datetime.now().isoformat(timespec="seconds"))}. Ranked by {escape(rank_by)}.</p>
  <div class="grid">
    <div class="card">
      <h2>Top Runs</h2>
      <table>
        <thead><tr>{"".join(f"<th>{escape(header)}</th>" for header in headers)}</tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
    <div class="card">
      <h2>Artifacts</h2>
      <ul>{artifact_links}</ul>
    </div>
    {"".join(chart_blocks)}
  </div>
</body>
</html>
"""
    target_path.write_text(html, encoding="utf-8")
    return target_path


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
        "factor_weights": config.factor_weights,
    }


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
            '<text x="40" y="90" font-size="16" fill="#6c757d">No data available</text>',
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
