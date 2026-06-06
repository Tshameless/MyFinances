from __future__ import annotations

from math import sqrt

from .config import BacktestConfig
from .factors import (
    align_history_to_calendar,
    build_intersection_calendar,
    calculate_factor_scores,
    group_prices_by_symbol,
)
from .models import BacktestMetrics, EquityPoint, PriceBar, RebalanceRecord
from .strategy import select_symbols


def run_backtest(
    bars: list[PriceBar],
    config: BacktestConfig | None = None,
) -> tuple[list[EquityPoint], list[RebalanceRecord], BacktestMetrics]:
    config = config or BacktestConfig()
    history_by_symbol = group_prices_by_symbol(bars)
    if not history_by_symbol:
        raise ValueError("No price data available for backtest.")

    calendar = build_intersection_calendar(history_by_symbol)
    aligned_history = align_history_to_calendar(history_by_symbol, calendar)
    common_length = len(calendar)
    if common_length < config.max_lookback + 2:
        raise ValueError("Not enough history to run the strategy.")

    equity = config.initial_cash
    equity_curve: list[EquityPoint] = []
    rebalance_records: list[RebalanceRecord] = []
    holdings: tuple[str, ...] = ()
    weights: dict[str, float] = {}
    total_cost = 0.0
    total_turnover = 0.0
    warmup = config.max_lookback

    for index in range(warmup, common_length - 1):
        current_date = calendar[index]
        next_date = calendar[index + 1]

        should_rebalance = not holdings or (index - warmup) % config.rebalance_every_n_days == 0
        if should_rebalance:
            scores = calculate_factor_scores(aligned_history, index, config)
            selected = tuple(select_symbols(scores, config.top_n))
            target_weights = _build_target_weights(selected)
            turnover = _calculate_turnover(weights, target_weights)
            turnover_cost = equity * turnover * config.per_side_cost_rate
            equity -= turnover_cost
            total_cost += turnover_cost
            total_turnover += turnover
            holdings = selected
            weights = target_weights
            rebalance_records.append(
                RebalanceRecord(
                    date=current_date,
                    holdings=holdings,
                    turnover=turnover,
                    cost=round(turnover_cost, 2),
                )
            )

        portfolio_return = 0.0
        for symbol, weight in weights.items():
            bars_for_symbol = aligned_history[symbol]
            today_close = bars_for_symbol[index].close
            next_close = bars_for_symbol[index + 1].close
            symbol_return = next_close / today_close - 1.0
            portfolio_return += weight * symbol_return

        equity *= 1.0 + portfolio_return
        equity_curve.append(
            EquityPoint(
                date=next_date,
                equity=round(equity, 2),
                daily_return=portfolio_return,
                holdings=holdings,
            )
        )

    metrics = _calculate_metrics(
        equity_curve,
        initial_cash=config.initial_cash,
        total_turnover=total_turnover,
        total_cost=total_cost,
        rebalance_count=len(rebalance_records),
    )
    return equity_curve, rebalance_records, metrics


def _build_target_weights(holdings: tuple[str, ...]) -> dict[str, float]:
    if not holdings:
        return {}
    weight = 1.0 / len(holdings)
    return {symbol: weight for symbol in holdings}


def _calculate_turnover(current_weights: dict[str, float], target_weights: dict[str, float]) -> float:
    symbols = set(current_weights) | set(target_weights)
    return sum(
        abs(target_weights.get(symbol, 0.0) - current_weights.get(symbol, 0.0))
        for symbol in symbols
    )


def _calculate_metrics(
    equity_curve: list[EquityPoint],
    *,
    initial_cash: float,
    total_turnover: float,
    total_cost: float,
    rebalance_count: int,
) -> BacktestMetrics:
    if not equity_curve:
        raise ValueError("Equity curve is too short to calculate metrics.")

    daily_returns = [point.daily_return for point in equity_curve]
    peak = initial_cash
    max_drawdown = 0.0

    for point in equity_curve:
        current = point.equity
        peak = max(peak, current)
        drawdown = current / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    total_return = equity_curve[-1].equity / initial_cash - 1.0
    mean_return = sum(daily_returns) / len(daily_returns)
    variance = (
        sum((daily - mean_return) ** 2 for daily in daily_returns)
        / max(len(daily_returns) - 1, 1)
    )
    volatility = sqrt(max(variance, 0.0)) * sqrt(252)
    annualized_return = (1.0 + total_return) ** (252 / len(daily_returns)) - 1.0
    sharpe = 0.0 if volatility == 0 else (mean_return * 252) / volatility
    wins = sum(1 for daily in daily_returns if daily > 0)
    average_turnover = total_turnover / rebalance_count if rebalance_count else 0.0

    return BacktestMetrics(
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=max_drawdown,
        volatility=volatility,
        sharpe=sharpe,
        win_rate=wins / len(daily_returns),
        average_turnover=average_turnover,
        total_cost=total_cost,
        periods=len(daily_returns),
    )
