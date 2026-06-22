from __future__ import annotations

import csv
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
from .reporting_labels import (
    chinese_label,
    display_label,
    format_symbol,
    metric_explanation,
)
from .reporting_svg import build_line_chart_svg

_HUMAN_READABLE_ENCODING = "utf-8-sig"


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
                display_label("date"),
                display_label("equity"),
                "权益展示 / equity_display",
                display_label("daily_return"),
                "单期收益率展示 / daily_return_pct",
                display_label("holdings"),
                "持仓展示 / holdings_display",
                "持仓数量 / holding_count",
                display_label("benchmark_equity"),
                "基准权益展示 / benchmark_equity_display",
                display_label("benchmark_daily_return"),
                "基准单期收益率展示 / benchmark_daily_return_pct",
                display_label("excess_daily_return"),
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
                display_label("date"),
                display_label("holdings"),
                "持仓展示 / holdings_display",
                "持仓数量 / holding_count",
                display_label("buy_turnover"),
                "买入换手率展示 / buy_turnover_pct",
                display_label("sell_turnover"),
                "卖出换手率展示 / sell_turnover_pct",
                display_label("turnover"),
                "总换手率展示 / turnover_pct",
                display_label("cost"),
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
                display_label("date"),
                display_label("symbol"),
                "代码展示 / symbol_display",
                display_label("shares"),
                display_label("price"),
                display_label("market_value"),
                "市值展示 / market_value_display",
                display_label("weight"),
                "权重展示 / weight_pct",
                display_label("cash"),
                "现金展示 / cash_display",
                display_label("total_equity"),
                "总权益展示 / total_equity_display",
            ]
        )
        for point in positions:
            writer.writerow(
                [
                    point.date.isoformat(),
                    point.symbol,
                    format_symbol(point.symbol, symbol_names),
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
        format_symbol=lambda symbol: format_symbol(symbol, symbol_names),
        display_label=display_label,
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
        format_symbol=lambda symbol: format_symbol(symbol, symbol_names),
        display_label=display_label,
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
        format_symbol=lambda symbol: format_symbol(symbol, symbol_names),
        display_label=display_label,
    )


def save_performance_summary(metrics: BacktestMetrics, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "performance_summary.csv"

    summary_items = _build_performance_summary_items(metrics)

    with target_path.open("w", encoding=_HUMAN_READABLE_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                display_label("metric"),
                display_label("label"),
                "说明 / description",
                display_label("value"),
            ]
        )
        writer.writerows(summary_items)

    return target_path


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
    svg = build_line_chart_svg(
        title=title,
        series=[
            ("策略净值", portfolio_points, "#0b7285"),
            ("基准净值", benchmark_points, "#e67700"),
        ],
        y_axis_label="净值",
    )
    target_path.write_text(svg, encoding=_HUMAN_READABLE_ENCODING)
    return target_path


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
    if symbol_group_csv.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        from .data_store import load_symbol_groups_from_sqlite

        return load_symbol_groups_from_sqlite(symbol_group_csv)
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


def _format_pct(value: float) -> str:
    return f"{value:.2%}"


def _format_money(value: float) -> str:
    return f"{value:,.2f}"


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


def _format_run_label(row: dict[str, object], row_index: int) -> str:
    run_id = str(row.get("run_id", "")).strip()
    if run_id.startswith("run_"):
        numeric_part = run_id.removeprefix("run_").lstrip("0") or "0"
        return f"方案{numeric_part}"
    if run_id:
        return run_id
    return f"方案{row_index}"
