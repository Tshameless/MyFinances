from __future__ import annotations

from math import sqrt
from typing import cast

from .models import BenchmarkPoint, EquityPoint


def build_drawdown_analysis(curve: list[EquityPoint]) -> dict[str, object]:
    if not curve:
        return {"rows": [], "summary": {}}

    initial_equity = curve[0].equity / (1.0 + curve[0].daily_return)
    peak_equity = initial_equity
    peak_date = curve[0].date
    rows: list[dict[str, str | float | int | bool]] = []
    max_drawdown_row: dict[str, str | float] | None = None
    current_underwater_days = 0
    current_underwater_start_date = ""
    longest_underwater_days = 0
    longest_underwater_start_date = ""
    longest_underwater_end_date = ""

    for point in curve:
        if point.equity > peak_equity:
            peak_equity = point.equity
            peak_date = point.date
        drawdown = point.equity / peak_equity - 1.0
        is_underwater = drawdown < 0.0
        if is_underwater:
            if current_underwater_days == 0:
                current_underwater_start_date = point.date.isoformat()
            current_underwater_days += 1
            if current_underwater_days > longest_underwater_days:
                longest_underwater_days = current_underwater_days
                longest_underwater_start_date = current_underwater_start_date
                longest_underwater_end_date = point.date.isoformat()
        else:
            current_underwater_days = 0
            current_underwater_start_date = ""
        row: dict[str, str | float | int | bool] = {
            "date": point.date.isoformat(),
            "equity": point.equity,
            "peak_date": peak_date.isoformat(),
            "peak_equity": peak_equity,
            "drawdown": drawdown,
            "is_underwater": is_underwater,
            "underwater_days": current_underwater_days,
            "underwater_start_date": current_underwater_start_date,
            "daily_return": point.daily_return,
        }
        rows.append(row)
        if max_drawdown_row is None or drawdown < float(max_drawdown_row["drawdown"]):
            max_drawdown_row = cast(dict[str, str | float], row)

    summary = {
        "max_drawdown": 0.0 if max_drawdown_row is None else cast(float, max_drawdown_row["drawdown"]),
        "max_drawdown_date": None if max_drawdown_row is None else cast(str, max_drawdown_row["date"]),
        "peak_date": None if max_drawdown_row is None else cast(str, max_drawdown_row["peak_date"]),
        "ending_drawdown": rows[-1]["drawdown"],
        "underwater_days": rows[-1]["underwater_days"],
        "is_recovered": not bool(rows[-1]["is_underwater"]),
        "longest_underwater_days": longest_underwater_days,
        "longest_underwater_start_date": longest_underwater_start_date,
        "longest_underwater_end_date": longest_underwater_end_date,
        **_tail_risk_summary([point.daily_return for point in curve], confidence=0.95),
    }
    return {"rows": rows, "summary": summary}


def build_monthly_return_analysis(curve: list[EquityPoint]) -> dict[str, object]:
    if not curve:
        return {"rows": [], "summary": {}}

    by_month: dict[str, list[EquityPoint]] = {}
    for point in curve:
        by_month.setdefault(point.date.strftime("%Y-%m"), []).append(point)

    rows: list[dict[str, str | float | int]] = []
    for month, points in sorted(by_month.items()):
        starting_equity = points[0].equity / (1.0 + points[0].daily_return)
        ending_equity = points[-1].equity
        monthly_return = ending_equity / starting_equity - 1.0
        rows.append(
            {
                "month": month,
                "start_date": points[0].date.isoformat(),
                "end_date": points[-1].date.isoformat(),
                "periods": len(points),
                "starting_equity": starting_equity,
                "ending_equity": ending_equity,
                "monthly_return": monthly_return,
            }
        )

    monthly_returns = [float(row["monthly_return"]) for row in rows]
    summary = {
        "months": len(rows),
        "positive_months": sum(1 for value in monthly_returns if value > 0),
        "negative_months": sum(1 for value in monthly_returns if value < 0),
        "best_month": max(rows, key=lambda row: float(row["monthly_return"]))["month"],
        "worst_month": min(rows, key=lambda row: float(row["monthly_return"]))["month"],
        "best_month_return": max(monthly_returns),
        "worst_month_return": min(monthly_returns),
        "average_monthly_return": sum(monthly_returns) / len(monthly_returns),
    }
    return {"rows": rows, "summary": summary}


def _tail_risk_summary(returns: list[float], *, confidence: float) -> dict[str, float]:
    if not returns:
        return {
            "tail_risk_confidence": confidence,
            "daily_var": 0.0,
            "daily_expected_shortfall": 0.0,
            "worst_daily_return": 0.0,
        }
    sorted_returns = sorted(returns)
    tail_count = max(1, int(round(len(sorted_returns) * (1.0 - confidence))))
    tail_returns = sorted_returns[:tail_count]
    var_return = tail_returns[-1]
    return {
        "tail_risk_confidence": confidence,
        "daily_var": abs(min(var_return, 0.0)),
        "daily_expected_shortfall": abs(min(sum(tail_returns) / len(tail_returns), 0.0)),
        "worst_daily_return": sorted_returns[0],
    }


def build_rolling_risk_analysis(
    curve: list[EquityPoint],
    *,
    window: int = 20,
) -> dict[str, object]:
    if window <= 1 or len(curve) < window:
        return {
            "rows": [],
            "summary": {
                "window": window,
                "periods": 0,
            },
        }

    rows: list[dict[str, str | float | int]] = []
    for end_index in range(window - 1, len(curve)):
        segment = curve[end_index - window + 1 : end_index + 1]
        returns = [point.daily_return for point in segment]
        rolling_return = 1.0
        for value in returns:
            rolling_return *= 1.0 + value
        rolling_return -= 1.0

        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / max(len(returns) - 1, 1)
        volatility = sqrt(max(variance, 0.0)) * sqrt(252)
        annualized_return = (1.0 + rolling_return) ** (252 / len(segment)) - 1.0
        sharpe = 0.0 if volatility == 0.0 else annualized_return / volatility
        max_drawdown = _window_max_drawdown(segment)
        win_rate = sum(1 for value in returns if value > 0) / len(returns)

        rows.append(
            {
                "date": segment[-1].date.isoformat(),
                "start_date": segment[0].date.isoformat(),
                "end_date": segment[-1].date.isoformat(),
                "window": window,
                "periods": len(segment),
                "rolling_return": rolling_return,
                "rolling_annualized_return": annualized_return,
                "rolling_volatility": volatility,
                "rolling_sharpe": sharpe,
                "rolling_max_drawdown": max_drawdown,
                "rolling_win_rate": win_rate,
            }
        )

    rolling_returns = [float(row["rolling_return"]) for row in rows]
    rolling_volatilities = [float(row["rolling_volatility"]) for row in rows]
    rolling_sharpes = [float(row["rolling_sharpe"]) for row in rows]
    best_return_row = max(rows, key=lambda row: float(row["rolling_return"]))
    worst_return_row = min(rows, key=lambda row: float(row["rolling_return"]))
    worst_drawdown_row = min(rows, key=lambda row: float(row["rolling_max_drawdown"]))
    summary = {
        "window": window,
        "periods": len(rows),
        "best_rolling_return": cast(float, best_return_row["rolling_return"]),
        "best_rolling_return_date": cast(str, best_return_row["date"]),
        "worst_rolling_return": cast(float, worst_return_row["rolling_return"]),
        "worst_rolling_return_date": cast(str, worst_return_row["date"]),
        "average_rolling_return": sum(rolling_returns) / len(rolling_returns),
        "average_rolling_volatility": sum(rolling_volatilities) / len(rolling_volatilities),
        "average_rolling_sharpe": sum(rolling_sharpes) / len(rolling_sharpes),
        "worst_rolling_drawdown": cast(float, worst_drawdown_row["rolling_max_drawdown"]),
        "worst_rolling_drawdown_date": cast(str, worst_drawdown_row["date"]),
        "positive_window_rate": sum(1 for value in rolling_returns if value > 0) / len(rolling_returns),
    }
    return {"rows": rows, "summary": summary}


def build_relative_performance_analysis(
    curve: list[EquityPoint],
    benchmark_curve: list[BenchmarkPoint] | None,
) -> dict[str, object]:
    if not curve or not benchmark_curve:
        return {"rows": [], "summary": {"has_benchmark": False}}

    benchmark_by_date = {point.date: point for point in benchmark_curve}
    active_equity = 1.0
    active_peak = 1.0
    active_peak_date: str | None = None
    rows: list[dict[str, str | float]] = []
    max_active_drawdown_row: dict[str, str | float] | None = None

    for point in curve:
        benchmark_point = benchmark_by_date.get(point.date)
        if benchmark_point is None:
            continue
        active_return = point.daily_return - benchmark_point.daily_return
        active_equity *= 1.0 + active_return
        if active_equity >= active_peak:
            active_peak = active_equity
            active_peak_date = point.date.isoformat()
        active_drawdown = active_equity / active_peak - 1.0
        row: dict[str, str | float] = {
            "date": point.date.isoformat(),
            "strategy_daily_return": point.daily_return,
            "benchmark_daily_return": benchmark_point.daily_return,
            "active_return": active_return,
            "cumulative_strategy_equity": point.equity,
            "cumulative_benchmark_equity": benchmark_point.equity,
            "active_equity": active_equity,
            "cumulative_active_return": active_equity - 1.0,
            "active_drawdown": active_drawdown,
        }
        rows.append(row)
        if max_active_drawdown_row is None or active_drawdown < float(max_active_drawdown_row["active_drawdown"]):
            max_active_drawdown_row = row

    if not rows:
        return {"rows": [], "summary": {"has_benchmark": False}}

    active_returns = [float(row["active_return"]) for row in rows]
    strategy_returns = [float(row["strategy_daily_return"]) for row in rows]
    benchmark_returns = [float(row["benchmark_daily_return"]) for row in rows]
    mean_active_return = sum(active_returns) / len(active_returns)
    mean_strategy_return = sum(strategy_returns) / len(strategy_returns)
    mean_benchmark_return = sum(benchmark_returns) / len(benchmark_returns)
    variance = sum((value - mean_active_return) ** 2 for value in active_returns) / max(len(active_returns) - 1, 1)
    tracking_error = sqrt(max(variance, 0.0)) * sqrt(252)
    benchmark_variance = sum((value - mean_benchmark_return) ** 2 for value in benchmark_returns) / max(
        len(benchmark_returns) - 1,
        1,
    )
    strategy_variance = sum((value - mean_strategy_return) ** 2 for value in strategy_returns) / max(
        len(strategy_returns) - 1,
        1,
    )
    covariance = sum(
        (strategy_return - mean_strategy_return) * (benchmark_return - mean_benchmark_return)
        for strategy_return, benchmark_return in zip(strategy_returns, benchmark_returns, strict=True)
    ) / max(len(rows) - 1, 1)
    beta = 0.0 if benchmark_variance == 0.0 else covariance / benchmark_variance
    daily_alpha = mean_strategy_return - beta * mean_benchmark_return
    annualized_alpha = daily_alpha * 252
    correlation_denominator = sqrt(max(strategy_variance, 0.0) * max(benchmark_variance, 0.0))
    correlation = 0.0 if correlation_denominator == 0.0 else covariance / correlation_denominator
    ending_active_equity = float(rows[-1]["active_equity"])
    annualized_active_return = ending_active_equity ** (252 / len(rows)) - 1.0
    best_active_day = max(rows, key=lambda row: float(row["active_return"]))
    worst_active_day = min(rows, key=lambda row: float(row["active_return"]))
    best_active_equity_day = max(rows, key=lambda row: float(row["active_equity"]))
    worst_active_equity_day = min(rows, key=lambda row: float(row["active_equity"]))
    positive_active_days = sum(1 for value in active_returns if value > 0)
    negative_active_days = sum(1 for value in active_returns if value < 0)
    summary = {
        "has_benchmark": True,
        "periods": len(rows),
        "total_active_return": ending_active_equity - 1.0,
        "annualized_active_return": annualized_active_return,
        "average_active_return": mean_active_return,
        "tracking_error": tracking_error,
        "information_ratio": 0.0 if tracking_error == 0 else annualized_active_return / tracking_error,
        "beta": beta,
        "daily_alpha": daily_alpha,
        "annualized_alpha": annualized_alpha,
        "correlation": correlation,
        "r_squared": correlation**2,
        "active_win_rate": positive_active_days / len(active_returns),
        "positive_active_days": positive_active_days,
        "negative_active_days": negative_active_days,
        "best_active_return_date": cast(str, best_active_day["date"]),
        "best_active_return": cast(float, best_active_day["active_return"]),
        "worst_active_return_date": cast(str, worst_active_day["date"]),
        "worst_active_return": cast(float, worst_active_day["active_return"]),
        "best_active_equity_date": cast(str, best_active_equity_day["date"]),
        "best_active_equity": cast(float, best_active_equity_day["active_equity"]),
        "worst_active_equity_date": cast(str, worst_active_equity_day["date"]),
        "worst_active_equity": cast(float, worst_active_equity_day["active_equity"]),
        "max_active_drawdown": (
            0.0
            if max_active_drawdown_row is None
            else cast(float, max_active_drawdown_row["active_drawdown"])
        ),
        "max_active_drawdown_date": (
            None
            if max_active_drawdown_row is None
            else cast(str, max_active_drawdown_row["date"])
        ),
        "active_peak_date": active_peak_date,
    }
    return {"rows": rows, "summary": summary}


def _window_max_drawdown(segment: list[EquityPoint]) -> float:
    if not segment:
        return 0.0
    initial_equity = segment[0].equity / (1.0 + segment[0].daily_return)
    peak = initial_equity
    max_drawdown = 0.0
    for point in segment:
        peak = max(peak, point.equity)
        max_drawdown = min(max_drawdown, point.equity / peak - 1.0)
    return max_drawdown


def build_split_performance(curve: list[EquityPoint]) -> dict[str, dict[str, float | int | str]]:
    if len(curve) < 4:
        return {}
    midpoint = len(curve) // 2
    return {
        "in_sample": _segment_metrics(curve[:midpoint]),
        "out_of_sample": _segment_metrics(curve[midpoint:]),
    }


def _segment_metrics(segment: list[EquityPoint]) -> dict[str, float | int | str]:
    if not segment:
        return {}
    initial_equity = segment[0].equity / (1.0 + segment[0].daily_return)
    ending_equity = segment[-1].equity
    total_return = ending_equity / initial_equity - 1.0
    annualized_return = (1.0 + total_return) ** (252 / len(segment)) - 1.0
    peak = initial_equity
    max_drawdown = 0.0
    for point in segment:
        peak = max(peak, point.equity)
        max_drawdown = min(max_drawdown, point.equity / peak - 1.0)
    returns = [point.daily_return for point in segment]
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / max(len(returns) - 1, 1)
    volatility = sqrt(max(variance, 0.0)) * sqrt(252)
    return {
        "start_date": segment[0].date.isoformat(),
        "end_date": segment[-1].date.isoformat(),
        "periods": len(segment),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
    }
